#!/usr/bin/env python3
"""Variable-occupancy capture must never acquire a fixed training label."""
import copy
import csv
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import csi_capture_common as common
import csi_capture_rx_launcher as rx
import csi_activity_guide as guide
import capture_prototype as capture
from free_test_recording import write_artifacts
from webcam_recorder import WebcamRecorder

SID = "session_free_test_1234"
CONTEXT = {"room": "G304", "setup_id": "0929G304", "capture_mode": "free_test",
           "activity": "free_test", "empty_reference_session_id": None, "planned_people_range": [0, 4]}
NETWORK = {"interface": "wlan-test", "ip": "127.0.0.1"}


def config(duration=2400):
    return {"num_people": 4, "duration_sec": duration, "sender_duration_sec": duration + 10,
            "profile": {"display_name": common.PROFILE, "ssid": common.SSID,
                        "verified": True, "frequency_confirmed": True},
            "camera": {"enabled": True, "device": "/dev/video0", "preview": True,
                       "width": 640, "height": 480, "fps": 10, "label_video_missing": False},
            "rate": 100, "size": 512, "data_port": 5005, "session_id": SID}


def load_script(name, path):
    spec = importlib.util.spec_from_file_location(name, str(ROOT / path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def synthetic_csi(path, count=301):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        for index in range(count):
            header = bytearray(20)
            struct.pack_into("<IH", header, 0, index * 10000, index)
            header[8:16] = bytes([3, 2, 40, 41, 39, 164, 20, 0x24])
            struct.pack_into("<HH", header, 16, 372, 0x210f)
            payload = b"\xbb" + header + b"\x11" * 372
            stream.write(struct.pack(">H", len(payload)) + payload)


class FreeTestSettingsTests(unittest.TestCase):
    def test_default_40_minutes_without_people_positions_or_action_prompts(self):
        self.assertEqual(rx.capture_mode("1"), "training")
        self.assertEqual(rx.capture_mode("2"), "free_test")
        with self.assertRaises(common.Failure):
            rx.capture_mode("3")
        output = io.StringIO()
        with mock.patch.object(rx, "empty_room_candidates", return_value=[]), \
                mock.patch("sys.stdin", io.StringIO("0929G304\n\n\n\n")), mock.patch("sys.stdout", output):
            context = rx.collection_settings("G304", 4, SID, free_test=True)
            segments = rx.capture_schedule(context["activity"])
            settings = rx.guidance_settings(4, segments)
            rx.collection_summary(context)
        self.assertEqual(context, CONTEXT)
        self.assertEqual(segments[-1]["end_sec"], 2400)
        self.assertEqual(len(segments), 1)
        self.assertEqual(settings["participants"], [])
        self.assertEqual((settings["prepare_sec"], settings["settle_sec"]), (30, 0))
        self.assertNotIn("참가자:자리", output.getvalue())
        self.assertNotIn("인원수는 파일 전체에서 고정", output.getvalue())

    def test_unknown_label_separate_paths_camera_and_unchanged_tx_schema(self):
        wire = config()
        original = copy.deepcopy(wire)
        args = rx.capture_args(wire, NETWORK, collection=CONTEXT)
        common.validate_config(wire)
        self.assertEqual(wire, original)
        self.assertEqual(wire["sender_duration_sec"], 2410)
        self.assertIsNone(args.num_people)
        self.assertEqual((args.capture_purpose, args.activity), ("free_test", "free_test"))
        self.assertEqual(Path(args.collection_root), ROOT / "data/free_test")
        self.assertTrue(args.camera_clock_overlay)
        self.assertIsNone(capture.capture_mode_error(args))
        wire["camera"] = {"enabled": False, "preview": False}
        with self.assertRaises(common.Failure):
            rx.capture_args(wire, NETWORK, collection=CONTEXT)
        with mock.patch.object(common, "discover_devices", return_value=[]):
            with self.assertRaises(common.Failure):
                common.camera_policy(required=True)

    def test_cli_rejects_fixed_count_in_free_mode_and_missing_fixed_count(self):
        args = rx.capture_args(config(), NETWORK, collection=CONTEXT)
        for field, value in (("num_people", 0), ("num_people", 4), ("camera_device", None), ("activity", "empty")):
            invalid = copy.copy(args)
            setattr(invalid, field, value)
            self.assertIsNotNone(capture.capture_mode_error(invalid))
        missing_count = capture.build_parser().parse_args([])
        self.assertIsNotNone(capture.capture_mode_error(missing_count))

    def test_camera_overlay_is_only_enabled_for_selected_recording(self):
        ordinary = WebcamRecorder("/dev/video0", "/tmp/unused.webm", "/tmp/unused.log")
        free = WebcamRecorder("/dev/video0", "/tmp/unused.webm", "/tmp/unused.log", clock_overlay=True)
        self.assertNotIn("clockoverlay", ordinary.build_command())
        command = free.build_command()
        self.assertLess(command.index("clockoverlay"), command.index("tee"))
        self.assertIn("time-format=%Y-%m-%d %H:%M:%S", command)


class FreeTestGuideTests(unittest.TestCase):
    def test_no_fixed_occupancy_instructions_and_packet_clock_drives_progress(self):
        events, panel, now = [], mock.Mock(), [10.0]
        settings = {"participants": [], "prepare_sec": 1, "settle_sec": 0,
                    "segments": guide.build_segments("free_test", 2400)}
        def sleep(seconds):
            now[0] += seconds
        live = guide.FreeTestGuide(config(), CONTEXT, settings,
            lambda name, **values: events.append(dict(event=name, **values)), panel=panel,
            monotonic=lambda: now[0], sleep=sleep)
        live.prepare(mock.Mock())
        self.assertAlmostEqual(now[0], 11)
        for elapsed in (0, 300, 1200, 2399):
            live.progress("recording", elapsed_sec=elapsed, first_packet_wall_epoch=1234.5, packets=100)
        self.assertEqual(sum(e["event"] == "GUIDE_TIME_ANCHOR" for e in events), 1)
        text = "\n".join("\n".join(call[0][0]) for call in panel.show.call_args_list)
        self.assertIn("39:59", text)
        self.assertIn("실제 인원 미확정", text)
        for forbidden in ("4명 유지", "전원 퇴실", "빈 방 유지", "지정 자리에", "다음 동작"):
            self.assertNotIn(forbidden, text)
        with mock.patch("sys.stdout", io.StringIO()) as output:
            live.result(True)
        self.assertNotIn("다음 파일", output.getvalue())
        live.close()
        self.assertGreaterEqual(panel.close.call_count, 2)


class FreeTestDatasetTests(unittest.TestCase):
    def test_real_postprocess_keeps_truth_blank_and_excludes_training(self):
        metadata = load_script("free_meta", "scripts/dataset/create_meta.py")
        structured = load_script("free_structured", "scripts/preprocess/build_structured_dataset.py")
        assembler = load_script("free_assembler", "scripts/dataset/assemble_structured_dataset.py")
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(capture, "PROJECT_ROOT", temp), \
                mock.patch.object(rx, "ROOT", Path(temp)):
            args = rx.capture_args(config(3), NETWORK, collection=CONTEXT)
            session = Path(args.collection_root) / "META_DATA" / SID
            session.mkdir(parents=True)
            csi = Path(args.collection_root) / "CSI_DATA" / (SID + ".dat")
            synthetic_csi(csi)
            relative_csi = os.path.relpath(str(csi), str(session))
            runtime = dict(CONTEXT, session_id=SID, completed=True, num_people=None,
                           planned_duration_sec=3, csi_file_bytes=csi.stat().st_size,
                           csi_validation={"record_count": 301},
                           timed_capture={"first_packet_wall_epoch": 2000.0},
                           udp={"first_packet_monotonic_sec": 500.0},
                           camera={"started_wall_epoch": 1970.0, "started_monotonic_sec": 470.0,
                                   "wall_clock_overlay": True})
            write_artifacts(str(session), runtime, relative_csi, "../../Web_Cam/" + SID + ".webm")
            def run(command, *_args):
                if command[1] == capture.CREATE_META:
                    self.assertNotIn("--num-people", command)
                    return metadata.main(command[2:] + ["--no-system-probe"])
                self.assertEqual(command[1], capture.BUILD_DATASET)
                self.assertNotIn("--num-people", command)
                return structured.main(command[2:])
            with mock.patch.object(capture, "run_checked", side_effect=run):
                capture.postprocess(args, str(session), runtime, relative_csi, "../../Web_Cam/" + SID + ".webm")
            write_artifacts(str(session), runtime, relative_csi, "../../Web_Cam/" + SID + ".webm")
            common.save(session / "capture_runtime.json", runtime)
            journal = mock.Mock(data={"completed": True, "abort_reason": "", "events": []})
            rx.attach_control(config(3), journal, CONTEXT)
            meta = json.loads((session / "meta.json").read_text())
            self.assertIsNone(meta["label"]["num_people"])
            self.assertEqual(meta["label"]["label_status"], "unknown")
            self.assertEqual(meta["dataset_role"], "test_candidate")
            self.assertFalse(meta["use_for_final_training"])
            self.assertEqual(meta["capture"]["start_time_local"], "1970-01-01 09:33:20")
            out = Path(temp) / runtime["structured_output_dir"]
            self.assertEqual(out, Path(temp) / "data/free_test/STRUCTURED" / SID)
            manifest = json.loads((out / "manifest.json").read_text())
            self.assertIsNone(manifest["label"]["num_people"])
            self.assertFalse(manifest["label"]["has_trainable_label"])
            self.assertFalse(manifest["quality"]["final_training_allowed"])
            self.assertFalse(assembler.should_include(manifest, mock.Mock(
                include_prototype=False, include_needs_review=False))[0])
            with (out / "window_features.csv").open() as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(r["num_people"] == "" and r["dataset_role"] == "test_candidate" and
                                r["use_for_final_training"] == "False" for r in rows))
            annotation = session / "annotations/ground_truth_intervals.csv"
            with annotation.open() as stream:
                self.assertEqual(list(csv.DictReader(stream)), [])
            annotation.write_text(annotation.read_text() + "1,2,3,true,reviewed\n")
            write_artifacts(str(session), runtime, relative_csi, "video.webm")
            self.assertIn("reviewed", annotation.read_text())  # Rewriting timing never erases annotation.
            alignment = json.loads((session / "time_alignment.json").read_text())
            self.assertEqual(alignment["estimated_timer_zero_video_sec"], 30)
            self.assertIsNone(alignment["verified_csi_zero_video_sec"])
            self.assertEqual(alignment["verification_status"], "unverified")
            self.assertFalse((Path(temp) / "data/4_people").exists())
            self.assertFalse((Path(temp) / "data/structured").exists())

    def test_failed_control_retains_unknown_label_and_excludes_features(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(rx, "ROOT", Path(temp)):
            session = Path(temp) / "data/free_test/META_DATA" / SID
            common.save(session / "capture_runtime.json", {"completed": True, "num_people": None})
            manifest = Path(temp) / "data/free_test/STRUCTURED" / SID / "manifest.json"
            common.save(manifest, {"quality": {"final_training_allowed": False}})
            journal = mock.Mock(data={"completed": False, "abort_reason": "disconnect", "events": []})
            rx.attach_control(config(), journal, CONTEXT)
            meta = json.loads((session / "meta.json").read_text())
            self.assertIsNone(meta["label"]["num_people"])
            self.assertEqual(meta["dataset_role"], "failure_history")
            self.assertEqual(meta["quality_status"], "failed")
            self.assertFalse(json.loads((session / "capture_runtime.json").read_text())["completed"])
            self.assertFalse(json.loads(manifest.read_text())["quality"]["final_training_allowed"])


class FreeTestAcquisitionTests(unittest.TestCase):
    def scenario(self, abort=False):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(rx, "ROOT", Path(temp)):
            args = rx.capture_args(config(0.2), NETWORK, collection=CONTEXT)
            args.port, args.skip_postprocess = 0, True
            session = Path(args.collection_root) / "META_DATA" / SID
            children, recorders, cameras = [], [], []
            actual_popen, recorder_class = subprocess.Popen, capture.UDPRecorder
            class Camera:
                def __init__(self, device, output, log, **options):
                    self.output, self.options = Path(output), options
                    self.started = None
                    self.stopped = False
                    cameras.append(self)
                def start(self):
                    self.started = time.time()
                    self.output.write_bytes(b"synthetic-camera")
                def wait_running(self, *_args, **_kwargs):
                    pass
                def ensure_running(self, *_args):
                    if self.stopped:
                        raise RuntimeError("camera stopped")
                def stop(self):
                    self.stopped = True
                def summary(self):
                    return {"enabled": True, "file_bytes": self.output.stat().st_size if self.output.exists() else 0,
                            "started_wall_epoch": self.started, "wall_clock_overlay": self.options["clock_overlay"]}
            def popen(command, **kwargs):
                synthetic_csi(Path(command[-1]), count=51)
                child = actual_popen([sys.executable, "-c",
                    'import sys; print(\'{"ready": true}\', flush=True); sys.stdin.readline()'], **kwargs)
                children.append(child)
                return child
            def recorder(*values, **options):
                instance = recorder_class(*values, **options)
                recorders.append(instance)
                return instance
            def ready():
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                    sender.sendto(b"synthetic", recorders[0].socket.getsockname())
            def prepare(health):
                health()
                if abort:
                    raise KeyboardInterrupt()
            state = {"kernel": "4.15.0-213-generic", "connector_log": "1", "free_bytes": 10**10,
                     "problems": [], "ip_address": "inet 127.0.0.1/8"}
            with mock.patch.object(capture, "preflight", return_value=state), \
                    mock.patch.object(capture, "run_checked"), \
                    mock.patch.object(capture, "UDPRecorder", side_effect=recorder), \
                    mock.patch.object(capture, "WebcamRecorder", Camera), \
                    mock.patch.object(capture.subprocess, "Popen", side_effect=popen), \
                    mock.patch.object(capture, "wait_for_stable_file", side_effect=lambda path: Path(path).stat().st_size):
                result = capture.capture(args, ready, lambda: None, prepare)
            self.assertEqual(result, 1 if abort else 0)
            self.assertTrue(all(child.poll() is not None for child in children))
            self.assertTrue(cameras[0].stopped)
            runtime = json.loads((session / "capture_runtime.json").read_text())
            meta = json.loads((session / "meta.json").read_text())
            self.assertIsNone(runtime["num_people"])
            self.assertIsNone(meta["label"]["num_people"])
            self.assertFalse(meta["use_for_final_training"])
            self.assertTrue((session / "annotations/ground_truth_intervals.csv").exists())
            alignment = json.loads((session / "time_alignment.json").read_text())
            if abort:
                self.assertFalse(children)
                self.assertFalse(runtime["completed"])
                self.assertEqual(meta["quality_status"], "failed")
                self.assertIsNone(alignment["timer_zero_wall_epoch"])
            else:
                self.assertTrue(runtime["completed"])
                self.assertEqual(alignment["timer_zero_wall_epoch"], runtime["udp"]["first_packet_wall_epoch"])
                self.assertIsNotNone(alignment["timer_zero_monotonic_sec"])
                self.assertGreater(alignment["estimated_timer_zero_video_sec"], 0)

    def test_complete_capture_with_real_udp_and_child_cleanup(self):
        self.scenario()

    def test_cancel_before_capture_preserves_partial_video_and_unknown_truth(self):
        self.scenario(abort=True)


if __name__ == "__main__":
    unittest.main()
