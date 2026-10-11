#!/usr/bin/env python3
"""Record a V4L2 webcam to WebM using the system GStreamer tools."""

import argparse
import glob
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import time


class WebcamError(RuntimeError):
    pass


def device_name(device):
    name_path = os.path.join(
        "/sys/class/video4linux", os.path.basename(device), "name"
    )
    try:
        with open(name_path, "r", encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return "unknown"


def discover_devices():
    devices = []
    for path in sorted(glob.glob("/dev/video*")):
        devices.append({
            "path": path,
            "real_path": os.path.realpath(path),
            "name": device_name(path),
            "readable": os.access(path, os.R_OK),
            "writable": os.access(path, os.W_OK),
        })
    return devices


def inspect_device(device):
    gst_launch = shutil.which("gst-launch-1.0")
    if not gst_launch:
        raise WebcamError("gst-launch-1.0 is missing; install gstreamer1.0-tools")
    if not os.path.exists(device):
        raise WebcamError("webcam device does not exist: {}".format(device))
    try:
        mode = os.stat(device).st_mode
    except OSError as exc:
        raise WebcamError("cannot inspect webcam {}: {}".format(device, exc))
    if not stat.S_ISCHR(mode):
        raise WebcamError("webcam path is not a character device: {}".format(device))
    if not os.access(device, os.R_OK | os.W_OK):
        raise WebcamError(
            "no read/write permission for {}; check the video group or device ACL".format(
                device
            )
        )
    return {
        "device": device,
        "real_path": os.path.realpath(device),
        "name": device_name(device),
        "gst_launch": gst_launch,
    }


class WebcamRecorder(object):

    def __init__(
        self,
        device,
        output_path,
        log_path,
        width=640,
        height=480,
        fps=10,
        preview=True,
        clock_overlay=False,
    ):
        self.device = device
        self.output_path = os.path.abspath(output_path)
        self.log_path = os.path.abspath(log_path)
        self.width = int(width)
        self.height = int(height)
        self.fps = int(fps)
        self.preview = bool(preview)
        self.clock_overlay = bool(clock_overlay)
        self.process = None
        self.log_handle = None
        self.command = None
        self.started_wall = None
        self.started_monotonic = None
        self.stopped_wall = None
        self.device_info = None

    def build_command(self):
        gst_launch = self.device_info["gst_launch"] if self.device_info else (
            shutil.which("gst-launch-1.0") or "gst-launch-1.0"
        )
        caps = "video/x-raw,width={},height={},framerate={}/1".format(
            self.width, self.height, self.fps
        )
        command = [
            gst_launch,
            "-q",
            "-e",
            "v4l2src",
            "device={}".format(self.device),
            "do-timestamp=true",
            "!",
            "videoconvert",
            "!",
            "videoscale",
            "!",
            "videorate",
            "!",
            caps,
            "!",
        ]
        if self.clock_overlay:
            command.extend(["clockoverlay", "time-format=%Y-%m-%d %H:%M:%S",
                            "halignment=left", "valignment=top", "shaded-background=true",
                            "font-desc=Sans 12", "!"])
        command.extend(["tee", "name=webcam_tee"])
        if self.preview:
            command.extend([
                "webcam_tee.",
                "!",
                "queue",
                "leaky=downstream",
                "max-size-buffers=2",
                "!",
                "autovideosink",
                "sync=false",
            ])
        command.extend([
            "webcam_tee.",
            "!",
            "queue",
            "!",
            "vp8enc",
            "deadline=1",
            "cpu-used=8",
            "threads=2",
            "target-bitrate=1000000",
            "!",
            "webmmux",
            "!",
            "filesink",
            "location={}".format(self.output_path),
        ])
        return command

    def start(self):
        if self.process is not None:
            raise WebcamError("webcam recorder has already been started")
        self.device_info = inspect_device(self.device)
        output_parent = os.path.dirname(self.output_path)
        log_parent = os.path.dirname(self.log_path)
        if output_parent:
            os.makedirs(output_parent, exist_ok=True)
        if log_parent:
            os.makedirs(log_parent, exist_ok=True)
        if os.path.exists(self.output_path):
            raise WebcamError("webcam output already exists: {}".format(self.output_path))

        self.command = self.build_command()
        self.log_handle = open(self.log_path, "w", encoding="utf-8")
        self.started_wall = time.time()
        self.started_monotonic = time.monotonic()
        try:
            self.process = subprocess.Popen(
                self.command,
                stdout=self.log_handle,
                stderr=subprocess.STDOUT,
            )
        except Exception:
            self.log_handle.close()
            self.log_handle = None
            raise

    def ensure_running(self, context="recording"):
        if self.process is None:
            raise WebcamError("webcam recorder has not been started")
        exit_code = self.process.poll()
        if exit_code is not None:
            raise WebcamError(
                "webcam recorder exited during {} (code={}); see {}".format(
                    context, exit_code, self.log_path
                )
            )

    def wait_running(self, duration, context="recording"):
        deadline = time.monotonic() + max(0.0, float(duration))
        while time.monotonic() < deadline:
            self.ensure_running(context)
            time.sleep(min(0.2, max(0.0, deadline - time.monotonic())))

    def stop(self):
        if self.process is None:
            return
        if self.process.poll() is None:
            try:
                self.process.send_signal(signal.SIGINT)
                self.process.wait(timeout=10)
            except Exception:
                try:
                    self.process.terminate()
                    self.process.wait(timeout=5)
                except Exception:
                    try:
                        self.process.kill()
                        self.process.wait(timeout=3)
                    except Exception:
                        pass
        self.stopped_wall = time.time()
        if self.log_handle is not None:
            self.log_handle.close()
            self.log_handle = None

    def summary(self):
        file_bytes = (
            os.path.getsize(self.output_path) if os.path.exists(self.output_path) else 0
        )
        elapsed = None
        if self.started_wall is not None:
            end = self.stopped_wall if self.stopped_wall is not None else time.time()
            elapsed = max(0.0, end - self.started_wall)
        return {
            "enabled": True,
            "device": self.device,
            "device_name": (
                self.device_info.get("name") if self.device_info else device_name(self.device)
            ),
            "output_file": self.output_path,
            "log_file": self.log_path,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "codec": "VP8",
            "container": "WebM",
            "audio_recorded": False,
            "preview_enabled": self.preview,
            "started_wall_epoch": self.started_wall,
            "started_monotonic_sec": self.started_monotonic,
            "wall_clock_overlay": self.clock_overlay,
            "stopped_wall_epoch": self.stopped_wall,
            "observed_duration_sec": elapsed,
            "file_bytes": file_bytes,
            "exit_code": self.process.poll() if self.process is not None else None,
            "command": self.command,
        }


def build_parser():
    parser = argparse.ArgumentParser(
        description="Check or record a V4L2 webcam using GStreamer"
    )
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument("--device", default="/dev/video0")
    parser.add_argument("--output", default="webcam_test.webm")
    parser.add_argument("--log", default="webcam_test.log")
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="record without opening a live preview window",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.list_devices:
        devices = discover_devices()
        print(json.dumps(devices, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if devices else 1
    if args.duration <= 0:
        parser.error("--duration must be positive")
    if args.width <= 0 or args.height <= 0 or args.fps <= 0:
        parser.error("width, height, and fps must be positive")

    output_path = os.path.abspath(args.output)
    if os.path.exists(output_path):
        if not args.overwrite:
            parser.error("output already exists; use --overwrite")
        os.unlink(output_path)

    recorder = WebcamRecorder(
        args.device,
        output_path,
        os.path.abspath(args.log),
        width=args.width,
        height=args.height,
        fps=args.fps,
        preview=not args.no_preview,
    )
    try:
        recorder.start()
        startup_check_sec = min(1.0, args.duration)
        recorder.wait_running(startup_check_sec, context="startup check")
        print("Webcam recording started: {}".format(output_path))
        recorder.wait_running(max(0.0, args.duration - startup_check_sec))
    except KeyboardInterrupt:
        print("Webcam recording interrupted.", file=sys.stderr)
    except WebcamError as exc:
        print("Webcam error: {}".format(exc), file=sys.stderr)
        return 1
    finally:
        recorder.stop()

    summary = recorder.summary()
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    if summary["file_bytes"] <= 0:
        print("Webcam recording produced an empty file.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
