#!/usr/bin/env python3
"""Capture a timed CSI prototype session and build structured features.

Run this on the CSI receiver. The timer starts with the first UDP datagram, so
the operator can start the traffic generator after the logger reports READY.
"""

import argparse
import csv
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import math
import re
import select
from collections import Counter
from datetime import datetime, timedelta, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from webcam_recorder import WebcamError, WebcamRecorder, inspect_device
from free_test_recording import write_artifacts as write_free_test_artifacts


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CSI_SCRIPT_DIR = os.path.join(PROJECT_ROOT, "scripts", "csi")
if CSI_SCRIPT_DIR not in sys.path:
    sys.path.insert(0, CSI_SCRIPT_DIR)

from csi_parser import summarize_file


LOG_TOOL = os.path.join(
    PROJECT_ROOT,
    "third_party",
    "linux-80211n-csitool-supplementary-master",
    "netlink",
    "log_to_file",
)
CREATE_META = os.path.join(PROJECT_ROOT, "scripts", "dataset", "create_meta.py")
BUILD_DATASET = os.path.join(
    PROJECT_ROOT, "scripts", "preprocess", "build_structured_dataset.py"
)
LOGGER_GUARD = os.path.join(SCRIPT_DIR, "csi_logger_guard.py")
KST = timezone(timedelta(hours=9))
CAPTURE_ROLES = {"prototype": "verification_only", "training": "training_candidate",
                 "free_test": "test_candidate"}


def capture_mode_error(args):
    if args.capture_purpose == "free_test":
        if args.num_people is not None:
            return "free_test records unknown occupancy; do not supply --num-people"
        if not args.camera_device:
            return "free_test requires --camera-device for later ground-truth annotation"
        if args.activity != "free_test":
            return "free_test requires --activity free_test"
    elif args.num_people is None or args.num_people < 0:
        return "--num-people must be a nonnegative integer for fixed-count captures"
    return None


def structured_output_dir(args, session_id):
    if args.capture_purpose == "free_test":
        return os.path.join(PROJECT_ROOT, "data", "free_test", "STRUCTURED", session_id)
    return os.path.join(PROJECT_ROOT, "data", "structured", session_id)


def run_text(command):
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=5,
            check=False,
        )
    except Exception:
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


class UDPRecorder(object):

    def __init__(self, bind_ip, port, csv_path, expected_source=None, session_nonce=None):
        self.bind_ip = bind_ip
        self.port = int(port)
        self.csv_path = csv_path
        self.first_packet_event = threading.Event()
        self.stop_event = threading.Event()
        self.thread = None
        self.socket = None
        self.first_packet_monotonic = None
        self.first_packet_wall = None
        self.last_packet_wall = None
        self.packet_count = 0
        self.byte_count = 0
        self.sources = Counter()
        self.error = None
        self.expected_source = expected_source
        self.packet_prefix = (b"CSI1:" + session_nonce.encode("ascii") + b":") if session_nonce else None
        self.last_packet_monotonic = None
        self.rejected_packets = 0

    def start(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((self.bind_ip, self.port))
        self.socket.settimeout(0.5)
        self.thread = threading.Thread(target=self._run, name="udp-recorder")
        self.thread.daemon = True
        self.thread.start()

    def _run(self):
        try:
            with open(self.csv_path, "w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow([
                    "packet_index",
                    "wall_time_epoch",
                    "relative_sec",
                    "source_ip",
                    "source_port",
                    "payload_bytes",
                ])
                while not self.stop_event.is_set():
                    try:
                        payload, address = self.socket.recvfrom(65535)
                    except socket.timeout:
                        continue
                    except OSError:
                        if self.stop_event.is_set():
                            break
                        raise

                    if ((self.expected_source and address[0] != self.expected_source) or
                            (self.packet_prefix and (len(payload) != 512 or
                             not payload.startswith(self.packet_prefix)))):
                        self.rejected_packets += 1
                        continue
                    monotonic_now = time.monotonic()
                    self.last_packet_monotonic = monotonic_now
                    wall_now = time.time()
                    if self.first_packet_monotonic is None:
                        self.first_packet_monotonic = monotonic_now
                        self.first_packet_wall = wall_now
                        self.first_packet_event.set()
                    relative_sec = monotonic_now - self.first_packet_monotonic
                    self.packet_count += 1
                    self.byte_count += len(payload)
                    self.last_packet_wall = wall_now
                    self.sources[address[0]] += 1
                    writer.writerow([
                        self.packet_count - 1,
                        "{:.6f}".format(wall_now),
                        "{:.6f}".format(relative_sec),
                        address[0],
                        address[1],
                        len(payload),
                    ])
                    if self.packet_count % 1000 == 0:
                        handle.flush()
        except Exception as exc:
            self.error = str(exc)
            self.first_packet_event.set()

    def stop(self):
        self.stop_event.set()
        if self.socket is not None:
            try:
                self.socket.close()
            except OSError:
                pass
        if self.thread is not None:
            self.thread.join(timeout=3)

    def summary(self):
        observed_duration = 0.0
        if self.first_packet_wall is not None and self.last_packet_wall is not None:
            observed_duration = max(0.0, self.last_packet_wall - self.first_packet_wall)
        return {
            "packet_count": self.packet_count,
            "payload_bytes": self.byte_count,
            "first_packet_wall_epoch": self.first_packet_wall,
            "first_packet_monotonic_sec": self.first_packet_monotonic,
            "last_packet_wall_epoch": self.last_packet_wall,
            "observed_duration_sec": observed_duration,
            "sources": dict(self.sources),
            "error": self.error,
            "rejected_packets": self.rejected_packets,
        }


def connector_log_value():
    path = "/sys/module/iwlwifi/parameters/connector_log"
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return None


def preflight(args):
    problems = []
    mode_error = capture_mode_error(args)
    if mode_error:
        problems.append(mode_error)
    kernel = run_text(["uname", "-r"])
    connector = connector_log_value()
    link = run_text(["iw", "dev", args.interface, "link"])
    address = run_text(["ip", "-4", "addr", "show", args.interface])
    free_bytes = shutil.disk_usage(PROJECT_ROOT).free
    camera_state = {"enabled": False}
    active_logger_pids = run_text(["pgrep", "-x", "log_to_file"])

    if not os.path.isfile(LOG_TOOL) or not os.access(LOG_TOOL, os.X_OK):
        problems.append("missing executable log_to_file")
    if not os.path.isfile(LOGGER_GUARD):
        problems.append("missing CSI logger guard")
    if connector != "1":
        problems.append("connector_log must be 1 (current={!r})".format(connector))
    if not kernel.startswith("4.15."):
        problems.append("expected 4.15 CSI kernel (current={!r})".format(kernel))
    if "Connected to" not in link:
        problems.append("{} is not connected to a WiFi AP".format(args.interface))
    if " inet " not in address:
        problems.append("{} has no IPv4 address".format(args.interface))
    if free_bytes < args.min_free_gb * (1024 ** 3):
        problems.append("less than {} GiB free".format(args.min_free_gb))
    if active_logger_pids:
        problems.append(
            "another log_to_file process is already running (PID={})".format(
                ",".join(active_logger_pids.split())
            )
        )
    if args.camera_device:
        try:
            camera_state = inspect_device(args.camera_device)
            camera_state["enabled"] = True
        except WebcamError as exc:
            camera_state = {
                "enabled": True,
                "device": args.camera_device,
                "error": str(exc),
            }
            problems.append("webcam preflight failed: {}".format(exc))

    return {
        "kernel": kernel,
        "connector_log": connector,
        "iw_link": link,
        "ip_address": address,
        "free_bytes": free_bytes,
        "active_logger_pids": active_logger_pids.split(),
        "camera": camera_state,
        "problems": problems,
    }


def stop_process_group(process):
    result = {
        "pid": None,
        "stopped": True,
        "method": None,
        "exit_code": None,
        "error": "",
    }
    if process is None:
        return result

    result["pid"] = process.pid
    if process.poll() is not None:
        result["exit_code"] = process.returncode
        return result

    try:
        process.stdin.write("STOP\n")
        process.stdin.flush()
        process.stdin.close()
        result["method"] = "guard_stdin"
        result["exit_code"] = process.wait(timeout=12)
    except Exception as exc:
        # Closing the guard pipe is also a STOP request. Reap the sudo monitor,
        # which forwards termination to its own guarded child if needed.
        try:
            if process.stdin and not process.stdin.closed:
                process.stdin.close()
            process.wait(timeout=12)
        except Exception:
            try:
                process.terminate()
                process.wait(timeout=12)
            except Exception:
                pass
        result["exit_code"] = process.poll()
        result["stopped"] = result["exit_code"] is not None
        if not result["stopped"]:
            result["error"] = str(exc)
    return result


def wait_for_stable_file(path, timeout_sec=3.0, interval_sec=0.25):
    deadline = time.monotonic() + timeout_sec
    previous_size = None
    stable_checks = 0
    while time.monotonic() < deadline:
        current_size = os.path.getsize(path) if os.path.exists(path) else 0
        if current_size == previous_size:
            stable_checks += 1
            if stable_checks >= 3:
                return current_size
        else:
            stable_checks = 0
            previous_size = current_size
        time.sleep(interval_sec)
    raise RuntimeError("CSI file size did not stabilize after logger shutdown")


def run_checked(command, health_callback=None, timeout=None):
    print("Running: {}".format(" ".join(command)))
    child = subprocess.Popen(command)
    started = time.monotonic()
    try:
        while child.poll() is None:
            if health_callback:
                health_callback()
            if timeout and time.monotonic() - started > timeout:
                raise RuntimeError("명령 대기 시간 초과: " + command[0])
            time.sleep(0.2)
        if child.returncode != 0:
            raise RuntimeError("command failed with exit code {}".format(child.returncode))
    finally:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=3)


def postprocess(args, session_dir, runtime, csi_file, video_file, health_callback=None):
    training_capture = args.capture_purpose == "training"
    free_test = args.capture_purpose == "free_test"
    dataset_role = CAPTURE_ROLES[args.capture_purpose]
    use_for_final_training = "true" if training_capture else "false"
    antenna_holder = args.antenna_holder or (
        "3d_printed_v1" if training_capture else "not_used_pre_holder"
    )
    comments = args.comments
    sender_command = (
        "python3 scripts/sender/safe_sender.py --target {} --mode udp "
        "--duration {} --rate {} --size {}"
    ).format(
        runtime.get("receiver_ip", "<RX_IP>"),
        args.duration + 10,
        args.sender_rate,
        args.sender_size,
    )
    if not comments:
        if free_test:
            comments = "Free-entry test recording, planned range 0-4; actual occupancy is unknown until video review. Excluded from training."
        elif training_capture:
            comments = (
                "Training-candidate capture using the fixed 3D-printed antenna holder. "
                "RF transmitter is the phone hotspot/AP; sender PC is the traffic generator."
            )
        else:
            comments = (
                "Prototype-only capture without the final antenna holder. "
                "RF transmitter is the phone hotspot/AP; sender PC is the traffic generator."
            )

    meta_command = [
        sys.executable,
        CREATE_META,
        session_dir,
        "--quality-status", "auto",
        "--dataset-role", dataset_role,
        "--use-for-final-training", use_for_final_training,
        "--label-status", "unknown" if free_test else "stable_full_session",
        "--activity", args.activity,
        "--duration-sec", str(args.duration),
        "--planned-duration-sec", str(args.duration),
        "--room", args.room,
        "--setup-id", args.setup_id,
        "--antenna-holder", antenna_holder,
        "--interface", args.interface,
        "--sender-rate", str(args.sender_rate),
        "--sender-size", str(args.sender_size),
        "--sender-command", sender_command,
        "--csi-file", csi_file,
        "--comments", comments,
    ]
    if args.num_people is not None:
        meta_command.extend(["--num-people", str(args.num_people)])
    if free_test:
        # This session's initial unknown-label metadata is written before capture.
        meta_command.append("--overwrite")
    if args.empty_reference_session_id:
        meta_command.extend(["--empty-reference-session-id", args.empty_reference_session_id])
    if args.camera_device:
        meta_command.extend(["--video-file", video_file])
    run_checked(meta_command, health_callback)

    structured_dir = structured_output_dir(args, os.path.basename(session_dir))
    dataset_command = [
        sys.executable,
        BUILD_DATASET,
        session_dir,
        "--output-dir", structured_dir,
        "--csi-file", csi_file,
        "--csi-mode", args.csi_mode,
        "--expected-nrx", str(args.expected_nrx),
        "--expected-ntx", str(args.expected_ntx),
        "--window-size-sec", str(args.window_size_sec),
        "--stride-sec", str(args.stride_sec),
        "--min-packets", str(args.min_packets),
        "--overwrite",
    ]
    if args.num_people is not None:
        dataset_command.extend(["--num-people", str(args.num_people)])
    run_checked(dataset_command, health_callback)
    runtime["structured_output_dir"] = os.path.relpath(structured_dir, PROJECT_ROOT)


def capture(args, ready_callback=None, health_callback=None,
            prepare_callback=None, progress_callback=None):
    state = preflight(args)
    print("kernel={}".format(state["kernel"]))
    print("connector_log={}".format(state["connector_log"]))
    print("free_gib={:.2f}".format(state["free_bytes"] / float(1024 ** 3)))
    if state["problems"]:
        for problem in state["problems"]:
            print("ERROR: {}".format(problem), file=sys.stderr)
        return 2

    rx_ip = "<RX_IP>"
    for token_index, token in enumerate(state["ip_address"].split()):
        if token == "inet" and token_index + 1 < len(state["ip_address"].split()):
            rx_ip = state["ip_address"].split()[token_index + 1].split("/", 1)[0]
            break

    if args.dry_run:
        print("Preflight passed. No files or processes were started.")
        print("Sender command after READY:")
        print(
            "python3 scripts/sender/safe_sender.py --target {} --mode udp "
            "--duration {} --rate {} --size {}".format(
                rx_ip, int(args.duration + 10), args.sender_rate, args.sender_size
            )
        )
        return 0

    if health_callback:
        run_checked(["sudo", "-v"], health_callback, timeout=120)
    elif subprocess.run(["sudo", "-v"], check=False).returncode != 0:
        print("sudo authentication failed", file=sys.stderr)
        return 2

    session_id = args.session_id or "session_{}".format(datetime.now(KST).strftime("%Y%m%d_%H%M%S"))
    if args.collection_root:
        collection_root = os.path.abspath(args.collection_root)
        session_dir = os.path.join(collection_root, "META_DATA", session_id)
        csi_path = os.path.join(collection_root, "CSI_DATA", session_id + ".dat")
        video_extension = os.path.splitext(args.camera_file)[1] or ".webm"
        video_path = os.path.join(
            collection_root, "Web_Cam", session_id + video_extension
        )
    else:
        session_dir = os.path.abspath(args.session_dir or os.path.join(
            PROJECT_ROOT,
            "data",
            "raw",
            session_id,
        ))
        session_id = os.path.basename(session_dir.rstrip(os.sep))
        csi_path = os.path.join(session_dir, "csi.dat")
        video_path = os.path.join(session_dir, args.camera_file)

    output_paths = [session_dir, csi_path]
    if args.camera_device:
        output_paths.append(video_path)
    existing_paths = [path for path in output_paths if os.path.exists(path)]
    if existing_paths:
        print("Capture output already exists: {}".format(existing_paths[0]), file=sys.stderr)
        return 2
    os.makedirs(session_dir)
    os.makedirs(os.path.dirname(csi_path), exist_ok=True)
    if args.camera_device:
        os.makedirs(os.path.dirname(video_path), exist_ok=True)

    csi_file_for_meta = os.path.relpath(csi_path, session_dir)
    video_file_for_meta = (
        os.path.relpath(video_path, session_dir) if args.camera_device else None
    )
    udp_csv_path = os.path.join(session_dir, "udp_packets.csv")
    runtime_path = os.path.join(session_dir, "capture_runtime.json")
    camera_log_path = os.path.join(session_dir, "webcam_gstreamer.log")
    logger_log_path = os.path.join(session_dir, "csi_logger.log")

    recorder = UDPRecorder(args.bind_ip, args.port, udp_csv_path,
                           args.expected_source, args.session_nonce)
    logger = None
    logger_log_handle = None
    logger_stop = None
    camera = None
    if args.camera_device:
        camera_options = {"clock_overlay": True} if args.camera_clock_overlay else {}
        camera = WebcamRecorder(
            args.camera_device,
            video_path,
            camera_log_path,
            width=args.camera_width,
            height=args.camera_height,
            fps=args.camera_fps,
            preview=not args.camera_no_preview,
            **camera_options
        )
    runtime = {
        "schema_version": "1.0-prototype",
        "session_id": session_id,
        "capture_purpose": args.capture_purpose,
        "dataset_role": CAPTURE_ROLES[args.capture_purpose],
        "files": {
            "csi": os.path.relpath(csi_path, PROJECT_ROOT),
            "video": (
                os.path.relpath(video_path, PROJECT_ROOT)
                if args.camera_device else None
            ),
            "metadata_dir": os.path.relpath(session_dir, PROJECT_ROOT),
            "csi_logger_log": os.path.relpath(logger_log_path, PROJECT_ROOT),
        },
        "topology": {
            "traffic_generator": "sender PC",
            "rf_transmitter": "phone hotspot/AP",
            "csi_receiver": "Intel 5300 receiver PC",
        },
        "planned_duration_sec": args.duration,
        "num_people": args.num_people,
        "activity": args.activity,
        "room": args.room,
        "setup_id": args.setup_id,
        "empty_reference_session_id": args.empty_reference_session_id,
        "receiver_ip": rx_ip,
        "udp_port": args.port,
        "camera_requested": bool(args.camera_device),
        "preflight": state,
        "started_at": datetime.now(KST).isoformat(timespec="seconds"),
        "completed": False,
    }
    if args.capture_purpose == "free_test":
        runtime.update(label_status="unknown", use_for_final_training=False,
                       planned_people_range=[0, 4], ground_truth_status="pending_video_review")
        write_json(runtime_path, runtime)
        write_free_test_artifacts(session_dir, runtime, csi_file_for_meta, video_file_for_meta)

    try:
        recorder.start()
        if camera is not None:
            camera.start()
            camera.wait_running(1.0, context="startup check")
            camera.wait_running(
                max(0.0, args.camera_preroll - 1.0), context="pre-roll"
            )
            print(
                "Webcam recording: {} ({}x{} at {} fps)".format(
                    os.path.relpath(video_path, PROJECT_ROOT),
                    args.camera_width,
                    args.camera_height,
                    args.camera_fps,
                )
            )
        if prepare_callback:
            if not ready_callback:
                raise RuntimeError("준비 카운트다운에는 TX START를 제어하는 실행기가 필요합니다.")
            def preparation_health():
                if health_callback:
                    health_callback()
                if recorder.error or not recorder.thread.is_alive():
                    raise RuntimeError("준비 중 UDP 수신기 오류")
                if recorder.first_packet_monotonic is not None:
                    raise RuntimeError("준비 완료/START 이전에 세션 UDP가 도착했습니다.")
                if camera is not None:
                    camera.ensure_running("operator preparation")
            prepare_callback(preparation_health)
            preparation_health()
        # Operator departure/settling happens before CSI logging and TX START.
        logger_log_handle = open(logger_log_path, "w", encoding="utf-8")
        runtime["logger_started_wall_epoch"] = time.time()
        logger_command = ["sudo", "-n", sys.executable, LOGGER_GUARD]
        if ready_callback:
            logger_command.append("--ready-json")
        logger = subprocess.Popen(
            logger_command + [LOG_TOOL, csi_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE if ready_callback else logger_log_handle,
            stderr=logger_log_handle,
            universal_newlines=True,
        )
        time.sleep(0.5)
        if logger.poll() is not None:
            raise RuntimeError("CSI logger exited before capture started")
        if ready_callback:
            readable, _, _ = select.select([logger.stdout], [], [], 10)
            if not readable or logger.stdout.readline().strip() != '{"ready": true}':
                raise RuntimeError("CSI logger netlink READY 확인 실패")
            if recorder.error or not recorder.thread.is_alive():
                raise RuntimeError("UDP receiver READY 확인 실패")
            if camera:
                camera.ensure_running("READY")
            ready_callback()

        if ready_callback:
            print("[통과] CSI/UDP READY 및 TX START_ACK 확인. 세션 UDP를 기다립니다.")
        else:
            print("READY: CSI logger and UDP receiver are running.")
            print("Run this on the sender PC now:")
            print(
                "python3 scripts/sender/safe_sender.py --target {} --mode udp "
                "--duration {} --rate {} --size {}".format(
                    rx_ip, args.duration + 10, args.sender_rate, args.sender_size
                )
            )
        print("The {} second timer starts with the first UDP packet.".format(args.duration))
        if progress_callback:
            progress_callback("waiting")

        waiting_since = time.monotonic()
        while not recorder.first_packet_event.wait(timeout=0.5):
            if health_callback:
                health_callback()
            if args.first_packet_timeout and time.monotonic() - waiting_since > args.first_packet_timeout:
                raise RuntimeError("유효 UDP 첫 패킷 대기 시간 초과")
            if logger.poll() is not None:
                raise RuntimeError("CSI logger exited while waiting for UDP traffic")
            if camera is not None:
                camera.ensure_running("waiting for UDP traffic")
        if recorder.error:
            raise RuntimeError("UDP receiver failed: {}".format(recorder.error))

        capture_started = time.monotonic()
        deadline = recorder.first_packet_monotonic + args.duration
        runtime["timed_capture"] = {"first_packet_wall_epoch": recorder.first_packet_wall,
                                    "first_packet_monotonic_sec": recorder.first_packet_monotonic,
                                    "clock": "first_valid_session_udp_packet",
                                    "duration_sec": args.duration}
        print("First UDP packet received. Timed capture started.")
        next_progress = capture_started + args.progress_interval
        while time.monotonic() < deadline:
            if health_callback:
                health_callback()
            if recorder.error:
                raise RuntimeError("UDP receiver failed: {}".format(recorder.error))
            if args.stall_timeout and time.monotonic() - recorder.last_packet_monotonic > args.stall_timeout:
                raise RuntimeError("UDP 패킷 수신 중단")
            if logger.poll() is not None:
                raise RuntimeError("CSI logger exited during capture")
            if camera is not None:
                camera.ensure_running("timed CSI capture")
            now = time.monotonic()
            if progress_callback:
                progress_callback("recording", elapsed_sec=max(0, now - recorder.first_packet_monotonic),
                                  first_packet_wall_epoch=recorder.first_packet_wall, packets=recorder.packet_count)
            elif now >= next_progress:
                remaining = max(0, int(round(deadline - now)))
                print("capture progress: packets={}, remaining={}s".format(
                    recorder.packet_count, remaining
                ))
                next_progress += args.progress_interval
            time.sleep(min(0.1 if progress_callback else 0.5, max(0.0, deadline - time.monotonic())))

        if progress_callback:
            progress_callback("finishing")
        recorder.stop()
        logger_stop = stop_process_group(logger)
        if not logger_stop["stopped"]:
            raise RuntimeError(
                "CSI logger did not stop: {}".format(logger_stop["error"])
            )
        if logger_stop["exit_code"] != 0:
            raise RuntimeError("CSI logger 종료 코드가 0이 아닙니다.")
        runtime["logger_stopped_wall_epoch"] = time.time()
        stable_csi_bytes = wait_for_stable_file(csi_path)
        csi_summary = summarize_file(csi_path)
        csi_record_count = int(csi_summary.get("record_count") or 0)
        csi_duration_sec = float(
            csi_summary.get("timestamp", {}).get("duration_sec") or 0.0
        )
        logger_wall_duration_sec = max(
            0.0,
            runtime["logger_stopped_wall_epoch"]
            - runtime["logger_started_wall_epoch"],
        )
        runtime["csi_validation"] = {
            "file_bytes": stable_csi_bytes,
            "record_count": csi_record_count,
            "duration_sec": csi_duration_sec,
            "logger_wall_duration_sec": logger_wall_duration_sec,
            "antenna_dimensions": csi_summary.get("antenna_dimensions", {}),
            "timestamp": csi_summary.get("timestamp", {}),
        }
        if stable_csi_bytes <= 0 or csi_record_count <= 0:
            raise RuntimeError("CSI logger produced no parseable CSI records")
        if csi_duration_sec > logger_wall_duration_sec + 5.0:
            raise RuntimeError(
                "CSI duration {:.3f}s exceeds logger wall duration {:.3f}s".format(
                    csi_duration_sec, logger_wall_duration_sec
                )
            )
        if camera is not None:
            camera.wait_running(args.camera_postroll, context="post-roll")
            camera.stop()
            if camera.summary()["file_bytes"] <= 0:
                raise RuntimeError("webcam recording produced an empty file")
        runtime["completed"] = True
        runtime["finished_at"] = datetime.now(KST).isoformat(timespec="seconds")
    except KeyboardInterrupt:
        runtime["aborted"] = True
        runtime["abort_reason"] = "keyboard interrupt"
        if progress_callback:
            try:
                progress_callback("failed", reason=runtime["abort_reason"])
            except Exception:
                pass  # A failed UI/log writer must not interrupt child cleanup.
        print("Capture interrupted; cleaning up.", file=sys.stderr)
    except Exception as exc:
        runtime["aborted"] = True
        runtime["abort_reason"] = str(exc)
        if progress_callback:
            try:
                progress_callback("failed", reason=runtime["abort_reason"])
            except Exception:
                pass
        print("Capture failed: {}".format(exc), file=sys.stderr)
    finally:
        recorder.stop()
        final_logger_stop = stop_process_group(logger)
        if logger_stop is None or not logger_stop.get("stopped"):
            logger_stop = final_logger_stop
        if logger_log_handle is not None:
            logger_log_handle.close()
        if logger is not None:
            for stream in (logger.stdin, logger.stdout):
                if stream is not None and not stream.closed:
                    stream.close()
        if camera is not None:
            camera.stop()
        runtime["udp"] = recorder.summary()
        runtime["csi_file_bytes"] = os.path.getsize(csi_path) if os.path.exists(csi_path) else 0
        runtime["logger"] = logger_stop
        runtime["logger_exit_code"] = (
            logger_stop.get("exit_code") if logger_stop is not None else None
        )
        runtime["camera"] = camera.summary() if camera is not None else {"enabled": False}
        write_json(runtime_path, runtime)
        if args.capture_purpose == "free_test":
            write_free_test_artifacts(session_dir, runtime, csi_file_for_meta, video_file_for_meta)

    if not runtime.get("completed"):
        print("Partial session metadata retained at {}".format(session_dir))
        print("Partial CSI file: {}".format(csi_path))
        if args.camera_device:
            print("Partial video file: {}".format(video_path))
        return 1

    print("Capture complete: {} UDP packets, {} CSI bytes".format(
        recorder.packet_count, runtime["csi_file_bytes"]
    ))
    if camera is not None:
        print("Video complete: {} bytes ({})".format(
            runtime["camera"]["file_bytes"],
            os.path.relpath(video_path, PROJECT_ROOT),
        ))
    if progress_callback:
        progress_callback("processing")
    if not args.skip_postprocess:
        try:
            postprocess(
                args,
                session_dir,
                runtime,
                csi_file_for_meta,
                video_file_for_meta,
                health_callback,
            )
            write_json(runtime_path, runtime)
        except Exception as exc:
            runtime["postprocess_error"] = str(exc)
            write_json(runtime_path, runtime)
            if args.capture_purpose == "free_test":
                write_free_test_artifacts(session_dir, runtime, csi_file_for_meta, video_file_for_meta)
            print("Postprocessing failed: {}".format(exc), file=sys.stderr)
            return 1

    if args.capture_purpose == "free_test":
        write_free_test_artifacts(session_dir, runtime, csi_file_for_meta, video_file_for_meta)

    print("CSI: {}".format(os.path.relpath(csi_path, PROJECT_ROOT)))
    if args.camera_device:
        print("Video: {}".format(os.path.relpath(video_path, PROJECT_ROOT)))
    print("Metadata: {}".format(os.path.relpath(session_dir, PROJECT_ROOT)))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        description="Capture a timed prototype CSI session on the receiver PC"
    )
    parser.add_argument("--duration", type=float, default=3600.0)
    parser.add_argument("--num-people", type=int, default=None,
                        help="required for fixed-count capture; omit for free_test")
    parser.add_argument("--activity", default="natural")
    parser.add_argument("--room", default="prototype_room")
    parser.add_argument("--setup-id", default="unknown")
    parser.add_argument("--empty-reference-session-id", default=None)
    parser.add_argument("--interface", default="wlp4s0")
    parser.add_argument("--bind-ip", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5005)
    parser.add_argument("--session-dir", default=None)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--expected-source", default=None)
    parser.add_argument("--session-nonce", default=None)
    parser.add_argument("--first-packet-timeout", type=float, default=0)
    parser.add_argument("--stall-timeout", type=float, default=0)
    parser.add_argument(
        "--collection-root",
        default=None,
        help=(
            "optional labeled collection root; writes matching session IDs under "
            "CSI_DATA, Web_Cam, and META_DATA"
        ),
    )
    parser.add_argument(
        "--capture-purpose",
        choices=["prototype", "training", "free_test"],
        default="prototype",
        help="training marks valid output as a final-dataset training candidate",
    )
    parser.add_argument(
        "--antenna-holder",
        default=None,
        help="antenna fixture identifier (training default: 3d_printed_v1)",
    )
    parser.add_argument("--comments", default="")
    parser.add_argument("--sender-rate", type=int, default=100)
    parser.add_argument("--sender-size", type=int, default=512)
    parser.add_argument("--csi-mode", choices=["raw", "scaled"], default="scaled")
    parser.add_argument("--expected-nrx", type=int, default=3)
    parser.add_argument("--expected-ntx", type=int, default=2)
    parser.add_argument("--window-size-sec", type=float, default=2.0)
    parser.add_argument("--stride-sec", type=float, default=1.0)
    parser.add_argument("--min-packets", type=int, default=40)
    parser.add_argument("--min-free-gb", type=float, default=2.0)
    parser.add_argument("--progress-interval", type=float, default=300.0)
    parser.add_argument(
        "--camera-device",
        default=None,
        help="optional V4L2 webcam device, for example /dev/video0",
    )
    parser.add_argument("--camera-file", default="video.webm")
    parser.add_argument("--camera-width", type=int, default=640)
    parser.add_argument("--camera-height", type=int, default=480)
    parser.add_argument("--camera-fps", type=int, default=10)
    parser.add_argument("--camera-clock-overlay", action="store_true",
                        help="record RX local wall time on the video for annotation alignment")
    parser.add_argument(
        "--camera-no-preview",
        action="store_true",
        help="record webcam video without opening a preview window",
    )
    parser.add_argument("--camera-preroll", type=float, default=5.0)
    parser.add_argument("--camera-postroll", type=float, default=5.0)
    parser.add_argument("--skip-postprocess", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    mode_error = capture_mode_error(args)
    if mode_error:
        parser.error(mode_error)
    if not math.isfinite(args.duration) or args.duration <= 0:
        parser.error("--duration must be positive")
    if args.sender_rate <= 0 or args.sender_size <= 0:
        parser.error("sender rate and size must be positive")
    if args.camera_width <= 0 or args.camera_height <= 0 or args.camera_fps <= 0:
        parser.error("camera width, height, and fps must be positive")
    if args.camera_preroll < 0 or args.camera_postroll < 0:
        parser.error("camera pre-roll and post-roll cannot be negative")
    if args.session_dir and args.collection_root:
        parser.error("--session-dir and --collection-root cannot be used together")
    if os.path.basename(args.camera_file) != args.camera_file:
        parser.error("--camera-file must be a file name, not a path")
    if args.session_id and not re.fullmatch(r"session_[A-Za-z0-9_]+", args.session_id):
        parser.error("invalid --session-id")
    if args.session_nonce and not re.fullmatch(r"[0-9a-f]{64}", args.session_nonce):
        parser.error("invalid --session-nonce")
    return capture(args)


if __name__ == "__main__":
    sys.exit(main())
