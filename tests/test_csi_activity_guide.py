#!/usr/bin/env python3
"""Timing, terminal restoration and acquisition-order checks for RX guidance."""
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import csi_activity_guide as guide
import csi_capture_rx_launcher as rx
import csi_capture_common as common
import capture_prototype as capture


class FakeClock:
    def __init__(self):
        self.value = 100.0

    def now(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


class ActivityGuideTests(unittest.TestCase):
    def make_guide(self, count=3, activity="mixed", repetitions=2):
        self.events = []
        self.clock = FakeClock()
        self.panel = mock.Mock()
        self.collection = {"room": "G304", "setup_id": "A", "activity": activity,
                           "empty_reference_session_id": None}
        participants = guide.participant_input(" ".join("P{0}:Z{0}".format(i + 1) for i in range(count)), count)
        segments = guide.build_segments(activity, 300, repetitions)
        guide.assign_walking_order(segments, participants)
        self.settings = {"participants": participants, "prepare_sec": 30, "settle_sec": 60, "segments": segments}
        self.config = {"num_people": count, "duration_sec": segments[-1]["end_sec"], "session_id": "session_guide"}
        return guide.ActivityGuide(self.config, self.collection, self.settings,
            lambda name, **details: self.events.append(dict(event=name, **details)), panel=self.panel,
            monotonic=self.clock.now, sleep=self.clock.sleep)

    def test_default_schedule_is_30_minutes_with_five_minute_actions(self):
        with mock.patch("sys.stdin", io.StringIO("\n\n")), mock.patch("sys.stdout", io.StringIO()):
            segments = rx.capture_schedule("mixed")
        self.assertEqual([s["activity"] for s in segments], ["sitting", "standing", "walking"] * 2)
        self.assertEqual([s["start_sec"] for s in segments], [0, 300, 600, 900, 1200, 1500])
        self.assertEqual(segments[-1]["end_sec"], 1800)
        with mock.patch("sys.stdin", io.StringIO("20\n")), mock.patch("sys.stdout", io.StringIO()):
            empty = rx.capture_schedule("empty")
        self.assertEqual(empty, [{"index": 1, "repeat": 1, "activity": "empty", "start_sec": 0, "end_sec": 1200}])

    def test_actions_switch_on_packet_elapsed_time_and_walker_rotates(self):
        live = self.make_guide(count=4)
        cases = [(0, "sitting", None), (299.9, "sitting", None), (300, "standing", None),
                 (599.9, "standing", None), (600, "walking", "P1"), (607, "walking", "P1"),
                 (660, "walking", "P2"), (899.9, "walking", "P1"), (900, "sitting", None),
                 (1500, "walking", "P2")]
        for elapsed, activity, person in cases:
            live.progress("recording", elapsed_sec=elapsed, first_packet_wall_epoch=1234.5, packets=10)
            cue = [e for e in self.events if e["event"] == "GUIDE_CUE"][-1]
            self.assertEqual((cue["activity"], cue.get("person")), (activity, person))
            self.assertLessEqual(cue["scheduled_elapsed_sec"], elapsed)
        anchors = [e for e in self.events if e["event"] == "GUIDE_TIME_ANCHOR"]
        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0]["first_packet_wall_epoch"], 1234.5)
        # Time advancement between UI calls emits only cues actually presented.
        self.assertFalse(any(e.get("scheduled_elapsed_sec") == 610 for e in self.events))

    def test_walking_phases_and_short_fractional_sessions(self):
        participants = guide.participant_input("P3:Z1 P1:Z2", 2)
        for elapsed, fragment in ((0, "W0 → W1"), (5, "W1에서"), (10, "W1 → W0"), (15, "W0에서")):
            cue = guide.action_at("walking", participants, 300, elapsed)
            self.assertIn(fragment, cue["action"])
            self.assertIn("P3", cue["action"])
        self.assertIn("P1", guide.action_at("walking", participants, 300, 60)["action"])
        self.assertEqual(guide.action_at("walking", participants, 2.5, 2.5)["key"], "ended")
        self.assertIn("앉아", guide.action_at("sit_stand", participants, 67.5, 33.749)["action"])
        self.assertIn("서서", guide.action_at("sit_stand", participants, 67.5, 33.75)["action"])

    def test_prepare_and_settle_do_not_consume_capture_duration(self):
        live = self.make_guide(count=0, activity="empty", repetitions=1)
        health = mock.Mock()
        live.prepare(health)
        self.assertAlmostEqual(self.clock.value, 190)
        self.assertGreater(health.call_count, 800)
        self.assertFalse(any(e["event"] == "GUIDE_TIME_ANCHOR" for e in self.events))
        self.assertEqual(live.duration, 300)
        self.assertEqual(self.events[-1]["cue_key"], "waiting")
        self.assertTrue(any("모두 퇴실" in e.get("instruction", "") for e in self.events))
        live.progress("recording", elapsed_sec=0.2, first_packet_wall_epoch=999, packets=1)
        self.assertEqual(self.events[-1]["observed_elapsed_sec"], 0.2)

    def test_disconnect_or_cancel_aborts_countdown_without_start_cue(self):
        for error in (KeyboardInterrupt(), common.Failure("disconnected")):
            live = self.make_guide()
            def health():
                if self.clock.now() >= 101:
                    raise error
            with self.assertRaises(type(error)):
                live.prepare(health)
            self.assertLess(self.clock.now(), 102)
            self.assertFalse(any(e.get("cue_key") == "waiting" for e in self.events))

    def test_input_validation_and_guidance_are_rx_only(self):
        for value in ("-1", "1.5", "NaN", "121", ""):
            with self.assertRaises(ValueError):
                guide.seconds_input(value)
        for value in ("P1:Z1 P1:Z2", "P1:Z1 P2:Z1", "P1", "P1:Z1"):
            with self.assertRaises(ValueError):
                guide.participant_input(value, 2)
        for value in ("0", "21", "1.1"):
            with self.assertRaises(ValueError):
                guide.repetitions_input(value)
        segments = guide.build_segments("mixed", 300, 2)
        with mock.patch("sys.stdin", io.StringIO("P2:Z1 P4:Z2\n\n\n")), mock.patch("sys.stdout", io.StringIO()):
            settings = rx.guidance_settings(2, segments)
        self.assertEqual(settings["segments"][2]["walking_order"], ["P2", "P4"])
        self.assertEqual(settings["segments"][5]["walking_order"], ["P4", "P2"])
        config = {"num_people": 2, "duration_sec": 1800, "sender_duration_sec": 1810,
                  "profile": {"display_name": common.PROFILE, "ssid": common.SSID, "verified": True,
                              "frequency_confirmed": True},
                  "camera": {"enabled": False, "preview": False}, "rate": 100, "size": 512,
                  "data_port": 5005, "session_id": "session_guide"}
        common.validate_config(config)  # No new fields in the existing TX wire schema.

    def test_terminal_restoration_and_plain_output(self):
        for tty in (False, True):
            stream = io.StringIO()
            stream.isatty = lambda: tty
            with mock.patch.dict("os.environ", {"TERM": "xterm"}):
                panel = guide.TerminalPanel(stream)
            panel.show(["G304", "지금: P1은 W0 → W1로 이동하세요."], changed=True)
            panel.close()
            panel.close()
            output = stream.getvalue()
            self.assertIn("G304", output)
            if tty:
                self.assertEqual(output.count("\033[?1049h"), 1)
                self.assertEqual(output.count("\033[?1049l"), 1)
                self.assertIn("\033[?25h", output)
            else:
                self.assertNotIn("\033", output)
        live = self.make_guide()
        live.progress("failed", reason="UDP stopped")
        self.panel.close.assert_called_once_with()
        self.assertEqual(self.events[-1]["reason"], "UDP stopped")

    def test_segments_and_actual_anchor_are_saved_even_after_failure(self):
        live = self.make_guide()
        for completed in (True, False):
            with tempfile.TemporaryDirectory() as temp, mock.patch.object(rx, "ROOT", Path(temp)):
                session = Path(temp) / "data/3_people/META_DATA/session_guide"
                common.save(session / "meta.json", {"label": {"num_people": 3, "activity": "mixed"}})
                common.save(session / "capture_runtime.json", {"completed": True})
                manifest = Path(temp) / "data/structured/session_guide/manifest.json"
                common.save(manifest, {"quality": {"final_training_allowed": True}})
                journal = mock.Mock(data={"completed": completed, "abort_reason": "" if completed else "cancel",
                    "activity_guidance": self.settings,
                    "events": [{"event": "GUIDE_TIME_ANCHOR", "first_packet_wall_epoch": 1234.5}]})
                rx.attach_control(self.config, journal, self.collection)
                saved = json.loads((session / "activity_segments.json").read_text())
                self.assertEqual(saved["first_packet_wall_epoch"], 1234.5)
                self.assertEqual(saved["segments"][-1]["end_sec"], 1800)
                self.assertEqual(saved["completed"], completed)
                self.assertEqual(json.loads((session / "meta.json").read_text())["label"]["activity"], "mixed")
                if not completed:
                    self.assertFalse(json.loads(manifest.read_text())["quality"]["final_training_allowed"])


class GuidedCaptureTests(unittest.TestCase):
    def scenario(self, abort=False):
        with tempfile.TemporaryDirectory() as temp:
            session = Path(temp) / "session_guided"
            args = capture.build_parser().parse_args(["--num-people", "0", "--activity", "empty", "--room", "G304",
                "--duration", "0.3", "--session-dir", str(session), "--bind-ip", "127.0.0.1", "--port", "0",
                "--skip-postprocess", "--first-packet-timeout", "1"])
            children, recorders, stages, frames = [], [], [], []
            actual_popen, recorder_class = subprocess.Popen, capture.UDPRecorder
            def popen(command, **kwargs):
                self.assertEqual(stages[-1], "prepared")
                stages.append("logger")
                (session / "csi.dat").write_bytes(b"synthetic")
                child = actual_popen([sys.executable, "-c",
                    'import sys; print(\'{"ready": true}\', flush=True); sys.stdin.readline()'], **kwargs)
                children.append(child)
                return child
            def recorder(*values, **options):
                instance = recorder_class(*values, **options)
                recorders.append(instance)
                return instance
            def prepare(health):
                self.assertFalse(children)
                self.assertFalse((session / "csi.dat").exists())
                health()
                if abort:
                    raise KeyboardInterrupt()
                stages.append("prepared")
            def ready():
                self.assertEqual(stages, ["prepared", "logger"])
                stages.append("START")
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                    sender.sendto(b"test", recorders[0].socket.getsockname())
            def progress(stage, **details):
                frames.append((stage, details))
            state = {"kernel": "4.15.0-213-generic", "connector_log": "1", "free_bytes": 10**10,
                     "problems": [], "ip_address": "inet 127.0.0.1/8"}
            with mock.patch.object(capture, "preflight", return_value=state), \
                    mock.patch.object(capture, "run_checked"), \
                    mock.patch.object(capture, "UDPRecorder", side_effect=recorder), \
                    mock.patch.object(capture.subprocess, "Popen", side_effect=popen), \
                    mock.patch.object(capture, "wait_for_stable_file", return_value=9), \
                    mock.patch.object(capture, "summarize_file", return_value={"record_count": 1,
                        "timestamp": {"duration_sec": 0.3}, "antenna_dimensions": {"3x2": 1}}):
                result = capture.capture(args, ready, lambda: None, prepare, progress)
            runtime = json.loads((session / "capture_runtime.json").read_text())
            self.assertTrue(all(child.poll() is not None for child in children))
            if abort:
                self.assertEqual(result, 1)
                self.assertFalse(children)
                self.assertNotIn("START", stages)
                self.assertFalse(runtime["completed"])
                self.assertEqual(frames[-1], ("failed", {"reason": "keyboard interrupt"}))
            else:
                self.assertEqual(result, 0)
                recording = [details for stage, details in frames if stage == "recording"]
                self.assertTrue(recording)
                self.assertEqual(recording[0]["first_packet_wall_epoch"], runtime["udp"]["first_packet_wall_epoch"])
                self.assertGreaterEqual(recording[0]["elapsed_sec"], 0)
                self.assertLess(recording[0]["elapsed_sec"], args.duration)
                self.assertEqual([stage for stage, _ in frames if stage != "recording"],
                                 ["waiting", "finishing", "processing"])

    def test_preparation_precedes_logger_and_start_and_uses_actual_packet_clock(self):
        self.scenario()

    def test_cancel_during_preparation_never_starts_logger_or_sender(self):
        self.scenario(abort=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
