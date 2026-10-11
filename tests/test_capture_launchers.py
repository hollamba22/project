#!/usr/bin/env python3
"""No hardware/network configuration required; real loopback TCP/UDP and child processes."""
import copy
import csv
import errno
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import csi_capture_common as common
import csi_capture_rx_launcher as rx
import csi_capture_tx_launcher as tx
import install_csi_capture_launchers as installer
import capture_prototype as capture

NONCE = "a" * 64
SID = "session_test_1234"


def config(duration=3, num_people=4):
    return {"num_people": num_people, "duration_sec": duration, "sender_duration_sec": duration + 10,
            "profile": {"display_name": common.PROFILE, "ssid": common.SSID, "verified": True,
                        "frequency_confirmed": True},
            "camera": {"enabled": False, "device": None, "preview": False, "label_video_missing": True},
            "rate": 100, "size": 512, "data_port": 5005, "session_id": SID}


def report(ip="127.0.0.1"):
    return {"interface": "wlan-test", "ssid": common.SSID, "bssid": "02:01:02:03:04:05",
            "frequency": 2437, "channel": 6, "ip": ip, "cidr": ip + "/8",
            "mac": "02:11:22:33:44:55", "power_save": "Power save: off"}


def sockets():
    with socket.socket() as listener:
        listener.settimeout(3)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        client = socket.socket()
        client.settimeout(3)
        client.connect(listener.getsockname())
        server, _ = listener.accept()
    return server, client


class MemoryJournal:
    def __init__(self):
        self.events = []

    def event(self, name, **details):
        self.events.append(name)


class InputTests(unittest.TestCase):
    def test_room_context_reaches_capture_and_postprocess_without_changing_wire_config(self):
        for room, count, activity in (("G304", 0, "empty"), ("G304", 4, "walking"), ("G308", 1, "standing")):
            with self.subTest(room=room, count=count):
                settings = config(300, count)
                original = copy.deepcopy(settings)
                context = {"room": room, "setup_id": "A", "activity": activity,
                           "empty_reference_session_id": "session_empty_1234"}
                args = rx.capture_args(settings, report(), collection=context)
                self.assertEqual((args.room, args.setup_id, args.activity), (room, "A", activity))
                self.assertEqual(settings, original)  # Existing TX's exact schema stays compatible.
                common.validate_config(settings)
                with mock.patch.object(capture, "run_checked") as run:
                    capture.postprocess(args, "/unused/" + SID, {}, "csi.dat", None)
                cmd = run.call_args_list[0][0][0]
                for flag, value in (("--room", room), ("--setup-id", "A"), ("--activity", activity),
                                    ("--empty-reference-session-id", "session_empty_1234")):
                    self.assertEqual(cmd[cmd.index(flag) + 1], value)

    def test_room_input_is_required_and_normalized(self):
        self.assertEqual(rx.collection_id("g304"), "G304")
        for value in ("", "unknown", "project_room", "../../G304", "G304\nG308", "G 304"):
            with self.subTest(value=value), self.assertRaises(common.Failure):
                rx.collection_id(value)
        with mock.patch("sys.stdin", io.StringIO("\ng304\n")), mock.patch("sys.stdout", io.StringIO()):
            self.assertEqual(common.ask("room", rx.collection_id), "G304")

    def test_empty_reference_filters_other_rooms_setups_and_failures(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(rx, "ROOT", Path(temp)):
            def add(name, room="G304", setup="A", completed=True, quality="needs_review", count=0):
                session = Path(temp) / "data/0_people/META_DATA" / name
                common.save(session / "meta.json", {
                    "session_id": name, "environment": {"room": room, "setup_id": setup},
                    "label": {"num_people": count, "activity": "empty"}, "quality_status": "valid_csi",
                    "capture": {"csi_file": "csi.dat"}})
                (session / "csi.dat").write_bytes(b"test")
                common.save(session / "capture_runtime.json", {"completed": completed, "room": room,
                            "setup_id": setup, "num_people": count})
                common.save(session / "session_control.json", {"completed": completed})
                common.save(Path(temp) / "data/structured" / name / "manifest.json",
                            {"quality": {"status": quality, "final_training_allowed": False}})
            add("session_match")
            add("session_other_room", room="G308")
            add("session_other_setup", setup="B")
            add("session_aborted", completed=False)
            add("session_failed", quality="failed")
            add("session_occupied", count=1)
            self.assertEqual(rx.empty_room_candidates("G304", "A"), [("session_match", "needs_review")])
            with mock.patch("sys.stdin", io.StringIO("\n3\n\n")), mock.patch("sys.stdout", io.StringIO()):
                context = rx.collection_settings("G304", 4, SID)
            self.assertEqual(context, {"room": "G304", "setup_id": "A", "activity": "walking",
                                      "empty_reference_session_id": "session_match"})
            with mock.patch("sys.stdin", io.StringIO("B\n")), mock.patch("sys.stdout", io.StringIO()):
                context = rx.collection_settings("G304", 0, SID)
            self.assertEqual(context["empty_reference_session_id"], SID)
            self.assertEqual(context["activity"], "empty")

    def test_people(self):
        for value in (0, 1, 2, 3, 4, 5, 12):
            self.assertEqual(common.people(str(value)), value)
        for value in ("-1", "-0", "0.0", "1.2", "../../x", "1; echo x", "", "NaN"):
            with self.assertRaises(common.Failure):
                common.people(value)

    def test_zero_people_input_and_summary(self):
        output = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO("0\n")), mock.patch("sys.stdout", output):
            self.assertEqual(common.ask("인원", common.people), 0)
            common.config_summary(config(1200, num_people=0))
        self.assertIn("0명", output.getvalue())
        self.assertIn("빈 방", output.getvalue())
        self.assertIn("TX 1210초", output.getvalue())

    def test_people_config_accepts_zero_but_not_bool_or_fraction(self):
        for value in (0, 1, 2, 3, 4, 5):
            common.validate_config(config(num_people=value))
            tx.validate_config(config(num_people=value))
        for value in (-1, True, False, 0.0, 1.5, "0", None):
            with self.subTest(value=value), self.assertRaises(common.Failure):
                common.validate_config(config(num_people=value))

    def test_people_capture_paths_activity_and_camera(self):
        for count in (0, 1, 4):
            for camera_enabled in (False, True):
                with self.subTest(count=count, camera=camera_enabled):
                    settings = config(1200, num_people=count)
                    if camera_enabled:
                        settings["camera"] = {"enabled": True, "device": "/dev/video0", "preview": True,
                                              "width": 640, "height": 480, "fps": 10,
                                              "label_video_missing": False}
                    common.validate_config(settings)
                    args = rx.capture_args(settings, report(), "127.0.0.1", NONCE)
                    self.assertEqual(args.num_people, count)
                    self.assertEqual(args.activity, "empty" if count == 0 else "natural")
                    self.assertEqual(Path(args.collection_root), ROOT / "data" / (str(count) + "_people"))
                    self.assertEqual(args.duration, 1200)
                    self.assertEqual(args.camera_device, "/dev/video0" if camera_enabled else None)
                    self.assertFalse(args.camera_no_preview)
                    self.assertEqual((args.sender_rate, args.sender_size, args.port), (100, 512, 5005))
                    self.assertEqual((args.expected_source, args.session_nonce), ("127.0.0.1", NONCE))

    def test_zero_people_postprocess_arguments(self):
        args = rx.capture_args(config(1200, num_people=0), report())
        runtime = {"receiver_ip": "127.0.0.1"}
        with mock.patch.object(capture, "run_checked") as run:
            capture.postprocess(args, "/unused/" + SID, runtime, "../../CSI_DATA/" + SID + ".dat", None)
        self.assertEqual(run.call_count, 2)
        for call in run.call_args_list:
            command = call[0][0]
            self.assertEqual(command[command.index("--num-people") + 1], "0")
        meta_command = run.call_args_list[0][0][0]
        self.assertEqual(meta_command[meta_command.index("--activity") + 1], "empty")
        self.assertEqual(meta_command[meta_command.index("--label-status") + 1], "stable_full_session")
        self.assertEqual(meta_command[meta_command.index("--planned-duration-sec") + 1], "1200.0")

    def test_minutes(self):
        self.assertEqual(common.minutes("0.05"), 3)
        self.assertEqual(common.minutes("1.125"), 67.5)
        for value in ("0", "-1", "nan", "Infinity", "1e10000", "1e-10000", "bad"):
            with self.assertRaises(common.Failure):
                common.minutes(value)

    def test_camera_and_cancel(self):
        for value in ("yes", "", "1"):
            with self.assertRaises(common.Failure):
                common.yesno(value)
        for value in ("Q\n", "q\n", ""):
            with mock.patch("sys.stdin", io.StringIO(value)), self.assertRaises(KeyboardInterrupt):
                common.ask("test")
        with mock.patch.object(common, "discover_devices", return_value=[]), mock.patch("sys.stdin", io.StringIO("N\nY\n")):
            policy = common.camera_policy()
        self.assertFalse(policy["enabled"])
        self.assertTrue(policy["label_video_missing"])
        args = rx.capture_args(config(), report())
        self.assertIsNone(args.camera_device)
        self.assertFalse(args.camera_no_preview)

    def test_camera_decline_and_selected(self):
        with mock.patch.object(common, "discover_devices", return_value=[]), mock.patch("sys.stdin", io.StringIO("N\nN\n")):
            with self.assertRaises(common.Failure):
                common.camera_policy()
        devices = [{"path": "/dev/video0", "name": "mock"}]
        with mock.patch.object(common, "discover_devices", return_value=devices), \
                mock.patch.object(common, "inspect_device"), mock.patch.object(common, "command", return_value="raw formats"), \
                mock.patch.dict(os.environ, {"DISPLAY": ":0"}), mock.patch("sys.stdin", io.StringIO("Y\n/dev/video0\n")):
            camera = common.camera_policy()
        settings = config()
        settings["camera"] = camera
        args = rx.capture_args(settings, report())
        self.assertEqual(args.camera_device, "/dev/video0")
        self.assertFalse(args.camera_no_preview)

    def test_hotspot(self):
        with mock.patch("sys.stdin", io.StringIO("\n")):
            self.assertTrue(common.hotspot(report())["verified"])
        other = report()
        other["ssid"] = "another AP"
        with mock.patch("sys.stdin", io.StringIO("Y\n")):
            profile = common.hotspot(other)
            self.assertFalse(profile["verified"])
            self.assertEqual(profile["ssid"], "another AP")
            self.assertEqual(profile["display_name"], "another AP")
        with mock.patch("sys.stdin", io.StringIO("N\n")), self.assertRaises(common.Failure):
            common.hotspot(other)

    def test_auto_ssid_channel_warning_and_cancel(self):
        other = report()
        other.update(ssid="실험실 Wi-Fi", frequency=2462, channel=11)
        with mock.patch("sys.stdin", io.StringIO("Y\nY\n")):
            profile = common.hotspot(other)
        settings = config()
        settings["profile"] = profile
        common.validate_config(settings)
        self.assertEqual(profile["ssid"], other["ssid"])
        self.assertFalse(profile["verified"])
        common.check_pair(other, other, profile, other["ip"], True)
        with self.assertRaises(common.Failure):
            common.check_pair(other, report(), profile, other["ip"], True)
        with mock.patch("sys.stdin", io.StringIO("Y\nN\n")), self.assertRaises(common.Failure):
            common.hotspot(other)
        with mock.patch("sys.stdin", io.StringIO("Q\n")), self.assertRaises(KeyboardInterrupt):
            common.hotspot(other)
        for ssid in (None, "", "   "):
            other["ssid"] = ssid
            with self.assertRaises(common.Failure):
                common.hotspot(other)

    def test_state_guards(self):
        gate = common.Gate()
        for action in (gate.approve, gate.capture_ready, gate.start):
            with self.assertRaises(common.Failure):
                action()
        changed = config(4)
        with self.assertRaises(common.Failure):
            gate.ready(config(), changed)
        gate.ready(config(), config())
        with self.assertRaises(common.Failure):
            gate.start()
        gate.approve()
        with self.assertRaises(common.Failure):
            gate.start()
        gate.capture_ready()
        self.assertTrue(gate.start())
        self.assertFalse(gate.start())
        self.assertEqual(config()["sender_duration_sec"] - config()["duration_sec"], 10)

    def test_pair(self):
        common.check_pair(report(), report(), config()["profile"], "127.0.0.1", True)
        for field, value in (("ssid", "wrong"), ("bssid", "02:00:00:00:00:00"),
                             ("ip", "127.0.0.2"), ("channel", 11)):
            changed = report()
            changed[field] = value
            with self.assertRaises(common.Failure):
                common.check_pair(report(), changed, config()["profile"], "127.0.0.1", True)
        with self.assertRaises(common.Failure):
            common.ipv4("127.0.0.1")


class WireTests(unittest.TestCase):
    def test_control_port_restart_after_connection_close(self):
        listener = rx.open_control_listener("127.0.0.1", 0)
        address = listener.getsockname()
        try:
            with socket.create_connection(address, timeout=3) as client:
                connection, _ = listener.accept()
                with connection:
                    connection.settimeout(3)
                    # RX initiates close; receiving both FINs creates TIME_WAIT
                    # on RX, as can happen after COMPLETE_ACK in a real session.
                    connection.shutdown(socket.SHUT_WR)
                    self.assertEqual(client.recv(1), b"")
                    client.shutdown(socket.SHUT_WR)
                    self.assertEqual(connection.recv(1), b"")
        finally:
            listener.close()
        # The old implementation could not bind this address until TIME_WAIT
        # expired, even though there was no live RX listener.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as old_listener:
            with self.assertRaises(OSError) as caught:
                old_listener.bind(address)
            self.assertEqual(caught.exception.errno, errno.EADDRINUSE)
        with rx.open_control_listener(*address) as restarted:
            with socket.create_connection(address, timeout=3):
                accepted, _ = restarted.accept()
                accepted.close()

    def test_control_port_still_blocks_active_duplicate(self):
        with rx.open_control_listener("127.0.0.1", 0) as listener:
            address = listener.getsockname()
            with self.assertRaisesRegex(common.Failure, "이미 사용 중"):
                rx.open_control_listener(*address)
            # The failed duplicate did not disturb the original listener.
            with socket.create_connection(address, timeout=3):
                accepted, _ = listener.accept()
                accepted.close()

    def test_control_bind_address_error_is_specific_and_closed(self):
        listener = mock.Mock()
        listener.bind.side_effect = OSError(errno.EADDRNOTAVAIL, "Cannot assign requested address")
        with mock.patch.object(rx.socket, "socket", return_value=listener):
            with self.assertRaisesRegex(common.Failure, "Wi-Fi 주소가 변경"):
                rx.open_control_listener("192.0.2.1", 5006)
        listener.close.assert_called_once_with()

    def test_handshake_loopback(self):
        server, client = sockets()
        try:
            a, b = common.Wire(server), common.Wire(client)
            b.send(common.packet("HELLO", pin="123456", role="TX", network=report(), profile=config()["profile"]))
            self.assertEqual(a.receive()["type"], "HELLO")
            a.send(common.packet("CONFIG", SID, NONCE, role="RX", network=report(), config=config()))
            received = b.receive()
            self.assertEqual(received["body"]["config"], config())
            b.send(common.packet("TX_READY", SID, NONCE, role="TX", config=config(), ping={"ok": True}))
            self.assertEqual(a.receive()["type"], "TX_READY")
        finally:
            server.close()
            client.close()

    def test_zero_people_handshake_preserves_integer_label(self):
        settings = config(num_people=0)
        server, client = sockets()
        try:
            a, b = common.Wire(server), common.Wire(client)
            a.send(common.packet("CONFIG", SID, NONCE, role="RX", network=report(), config=settings))
            received = b.receive()["body"]["config"]
            tx.validate_config(received)
            self.assertIs(type(received["num_people"]), int)
            self.assertEqual(received["num_people"], 0)
            b.send(common.packet("TX_READY", SID, NONCE, role="TX", config=received, ping={"ok": True}))
            ready = a.receive()["body"]["config"]
            gate = common.Gate()
            gate.ready(settings, ready)
            self.assertEqual(gate.state, "TX_READY")
        finally:
            server.close()
            client.close()

    def test_version_size_json_timeout_disconnect(self):
        wrong = common.packet("START", SID, NONCE)
        wrong["protocol_version"] = 999
        for raw in (json.dumps(wrong).encode() + b"\n", b"x" * common.MAX_MESSAGE,
                    b"{bad}\n", b"[]\n"):
            server, client = sockets()
            try:
                client.sendall(raw)
                with self.assertRaises(common.Failure):
                    common.Wire(server).receive(1)
            finally:
                server.close()
                client.close()
        server, client = sockets()
        try:
            wire = common.Wire(server)
            with self.assertRaises(common.Failure):
                wire.receive(0.05)
            client.close()
            with self.assertRaises(common.Failure):
                wire.receive()
        finally:
            server.close()
            client.close()

    def test_heartbeat_and_wrong_nonce(self):
        server, client = sockets()
        channel = common.Channel(common.Wire(server), SID, NONCE, timeout=0.2)
        try:
            common.Wire(client).send(common.packet("START", SID, "b" * 64))
            deadline = time.monotonic() + 2
            while channel.error is None and time.monotonic() < deadline:
                time.sleep(0.02)
            with self.assertRaises(common.Failure):
                channel.check()
        finally:
            client.close()
            channel.close()
        server, client = sockets()
        channel = common.Channel(common.Wire(server), SID, NONCE, timeout=0.1)
        try:
            time.sleep(1.2)
            with self.assertRaises(common.Failure):
                channel.check()
        finally:
            client.close()
            channel.close()


class RecorderTests(unittest.TestCase):
    def test_only_matching_source_nonce_starts_timer(self):
        with tempfile.TemporaryDirectory() as temp:
            recorder = capture.UDPRecorder("127.0.0.1", 0, str(Path(temp) / "udp.csv"), "127.0.0.1", NONCE)
            recorder.start()
            target = recorder.socket.getsockname()
            valid = b"CSI1:" + NONCE.encode() + b":" + b"x" * 442
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                    sender.sendto(b"legacy" * 80, target)
                    sender.sendto(valid.replace(b"a", b"b"), target)
                    sender.sendto(valid[:-1], target)
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as wrong:
                        wrong.bind(("127.0.0.2", 0))
                        wrong.sendto(valid, target)
                    time.sleep(0.15)
                    self.assertFalse(recorder.first_packet_event.is_set())
                    sender.sendto(valid, target)
                    self.assertTrue(recorder.first_packet_event.wait(2))
                self.assertEqual(recorder.rejected_packets, 4)
            finally:
                recorder.stop()
            self.assertFalse(recorder.thread.is_alive())
            self.assertEqual(recorder.summary()["packet_count"], 1)

    def test_legacy_and_port_conflict(self):
        with tempfile.TemporaryDirectory() as temp:
            recorder = capture.UDPRecorder("127.0.0.1", 0, str(Path(temp) / "udp.csv"))
            recorder.start()
            other = capture.UDPRecorder("127.0.0.1", recorder.socket.getsockname()[1], str(Path(temp) / "other.csv"))
            try:
                with self.assertRaises(OSError):
                    other.start()
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                    sender.sendto(b"legacy", recorder.socket.getsockname())
                self.assertTrue(recorder.first_packet_event.wait(2))
            finally:
                recorder.stop()
                other.stop()


class IntegrationTests(unittest.TestCase):
    def test_three_second_capture_real_sender_complete(self):
        self.real_sender_capture(num_people=4)

    def test_zero_people_capture_real_sender_complete(self):
        self.real_sender_capture(num_people=0)

    def real_sender_capture(self, num_people):
        settings = config(3, num_people=num_people)
        server, client = sockets()
        a = common.Channel(common.Wire(server), SID, NONCE)
        b = common.Channel(common.Wire(client), SID, NONCE)
        journal = MemoryJournal()
        errors, children, approved = [], [], []
        with tempfile.TemporaryDirectory() as temp:
            recorder = capture.UDPRecorder("127.0.0.1", 0, str(Path(temp) / "udp.csv"), "127.0.0.1", NONCE)
            result_path = Path(temp) / "result.json"
            def acquire(ready, health):
                self.assertTrue(approved)
                self.assertFalse(children)
                recorder.start()
                ready()
                while not recorder.first_packet_event.wait(0.1):
                    health()
                while time.monotonic() < recorder.first_packet_monotonic + settings["duration_sec"]:
                    health()
                    time.sleep(0.02)
                recorder.stop()
                return 0
            def spawn():
                args = tx.sender_command(settings, "127.0.0.1", "127.0.0.1", NONCE, result_path)
                args[args.index("--port") + 1] = str(recorder.socket.getsockname()[1])
                child = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                children.append(child)
                return child
            def transmit():
                try:
                    b.send("TX_READY", role="TX", config=settings, ping={"ok": True})
                    b.expect("READY_ACK")
                    tx.transmit(b, settings, journal, spawn, lambda: json.loads(result_path.read_text()))
                except BaseException as exc:
                    errors.append(exc)
            thread = threading.Thread(target=transmit)
            thread.start()
            try:
                rx.coordinate(a, settings, common.Gate(), journal, acquire, lambda: approved.append(True))
                thread.join(5)
                self.assertFalse(thread.is_alive())
                self.assertEqual(errors, [])
                self.assertEqual(len(children), 1)
                self.assertEqual(children[0].poll(), 0)
                result = json.loads(result_path.read_text())
                self.assertEqual(result["duration_sec"], 13)
                self.assertTrue(280 <= recorder.packet_count <= 330, recorder.packet_count)
                self.assertEqual(recorder.byte_count, recorder.packet_count * 512)
                self.assertTrue(1280 <= result["sent"] <= 1320, result)
                self.assertIn("COMPLETE_ACK", journal.events)
                print("\nMOCK COMPLETE: people={} RX=3s TX=13s RX packets={} TX packets={} payload=512B".format(
                    num_people, recorder.packet_count, result["sent"]))
            finally:
                a.close()
                b.close()
                recorder.stop()
                thread.join(5)
                for child in children:
                    common.stop_child(child)

    def test_duplicate_start_and_disconnect_kills_sender(self):
        server, client = sockets()
        a = common.Channel(common.Wire(server), SID, NONCE)
        b = common.Channel(common.Wire(client), SID, NONCE)
        children, errors = [], []
        def spawn():
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(100)"], stderr=subprocess.DEVNULL)
            children.append(child)
            return child
        def worker():
            try:
                tx.transmit(b, config(), MemoryJournal(), spawn, lambda: {})
            except common.Failure as exc:
                errors.append(str(exc))
        thread = threading.Thread(target=worker)
        thread.start()
        try:
            a.send("START")
            a.expect("START_ACK")
            a.send("START")
            a.expect("START_ACK")
            self.assertEqual(len(children), 1)
            a.close()
            thread.join(5)
            self.assertFalse(thread.is_alive())
            self.assertTrue(errors)
            self.assertIsNotNone(children[0].poll())
        finally:
            a.close()
            b.close()
            thread.join(5)
            for child in children:
                common.stop_child(child)

    def test_sender_early_exit(self):
        server, client = sockets()
        a = common.Channel(common.Wire(server), SID, NONCE)
        b = common.Channel(common.Wire(client), SID, NONCE)
        a.send("START")
        child = subprocess.Popen([sys.executable, "-c", "pass"])
        try:
            with self.assertRaisesRegex(common.Failure, "계획 시간 전에"):
                tx.transmit(b, config(), MemoryJournal(), lambda: child, lambda: {})
        finally:
            common.stop_child(child)
            a.close()
            b.close()


class CaptureFailureTests(unittest.TestCase):
    def scenario(self, mode):
        with tempfile.TemporaryDirectory() as temp:
            args = capture.build_parser().parse_args(["--num-people", "4", "--duration", "0.15",
                "--session-dir", str(Path(temp) / "session"), "--bind-ip", "127.0.0.1", "--port", "0",
                "--skip-postprocess", "--first-packet-timeout", "0.1", "--camera-preroll", "0", "--camera-postroll", "0"])
            if mode == "stall":
                args.duration = 1
                args.stall_timeout = 0.1
            if mode == "camera":
                args.camera_device = "/dev/video0"
            actual_popen = subprocess.Popen
            children = []
            def popen(command, **kwargs):
                # Fake privileged logger exposes the same JSON READY and stdin STOP lifecycle.
                code = 'import sys; print(\'{"ready": true}\', flush=True); sys.stdin.readline()'
                if mode == "logger":
                    code = "pass"
                child = actual_popen([sys.executable, "-c", code], **kwargs)
                children.append(child)
                return child
            camera = mock.Mock()
            camera.summary.return_value = {"file_bytes": 0, "enabled": True}
            camera.ensure_running.side_effect = RuntimeError("camera early exit")
            def ready():
                if mode == "interrupt":
                    raise KeyboardInterrupt()
                if mode == "stall":
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                        sender.sendto(b"test", active_recorder[0].socket.getsockname())
            def health():
                if mode == "disconnect":
                    raise common.Failure("control disconnected")
            state = {"kernel": "4.15.0-213-generic", "connector_log": "1", "free_bytes": 10**10,
                     "problems": [], "ip_address": "inet 127.0.0.1/8"}
            active_recorder = []
            recorder_class = capture.UDPRecorder
            def recorder(*values, **options):
                instance = recorder_class(*values, **options)
                active_recorder.append(instance)
                return instance
            with mock.patch.object(capture, "preflight", return_value=state), \
                    mock.patch.object(capture, "run_checked"), \
                    mock.patch.object(capture, "UDPRecorder", side_effect=recorder), \
                    mock.patch.object(capture.subprocess, "run", return_value=mock.Mock(returncode=0)), \
                    mock.patch.object(capture.subprocess, "Popen", side_effect=popen), \
                    mock.patch.object(capture, "WebcamRecorder", return_value=camera):
                result = capture.capture(args, ready, health)
            self.assertEqual(result, 1)
            runtime = json.loads((Path(temp) / "session/capture_runtime.json").read_text())
            self.assertFalse(runtime["completed"])
            self.assertTrue(runtime["aborted"])
            self.assertTrue(all(child.poll() is not None for child in children))
            self.assertFalse(any(t.name == "udp-recorder" for t in threading.enumerate()))
            if mode == "camera":
                camera.stop.assert_called()

    def test_logger_early_exit(self):
        self.scenario("logger")

    def test_camera_early_exit(self):
        self.scenario("camera")

    def test_ctrl_c_cleanup(self):
        self.scenario("interrupt")

    def test_disconnect_failure_record(self):
        self.scenario("disconnect")

    def test_first_packet_timeout(self):
        self.scenario("timeout")

    def test_packet_stall(self):
        self.scenario("stall")

    def test_failed_control_disables_training(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(rx, "ROOT", Path(temp)):
            session = Path(temp) / "data/4_people/META_DATA" / SID
            session.mkdir(parents=True)
            common.save(session / "capture_runtime.json", {"completed": True})
            manifest = Path(temp) / "data/structured" / SID / "manifest.json"
            common.save(manifest, {"quality": {"final_training_allowed": True}})
            journal = mock.Mock(data={"completed": False, "abort_reason": "TX disconnected"})
            rx.attach_control(config(), journal)
            self.assertFalse(json.loads((session / "meta.json").read_text())["use_for_final_training"])
            self.assertFalse(json.loads(manifest.read_text())["quality"]["final_training_allowed"])
            self.assertFalse(json.loads((session / "capture_runtime.json").read_text())["completed"])

    def test_failed_zero_people_control_retains_empty_label(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(rx, "ROOT", Path(temp)):
            session = Path(temp) / "data/0_people/META_DATA" / SID
            session.mkdir(parents=True)
            common.save(session / "capture_runtime.json", {"num_people": 0, "activity": "empty", "completed": True})
            journal = mock.Mock(data={"completed": False, "abort_reason": "TX disconnected"})
            rx.attach_control(config(num_people=0), journal)
            meta = json.loads((session / "meta.json").read_text())
            self.assertEqual(meta["label"], {"num_people": 0, "activity": "empty", "label_status": "unknown"})
            self.assertEqual(meta["dataset_role"], "failure_history")
            self.assertFalse(meta["use_for_final_training"])
            runtime = json.loads((session / "capture_runtime.json").read_text())
            self.assertEqual(runtime["num_people"], 0)
            self.assertFalse(runtime["completed"])

    def test_failed_capture_keeps_room_and_reference_context(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(rx, "ROOT", Path(temp)):
            session = Path(temp) / "data/4_people/META_DATA" / SID
            session.mkdir(parents=True)
            common.save(session / "capture_runtime.json", {"completed": False})
            context = {"room": "G304", "setup_id": "A", "activity": "walking",
                       "empty_reference_session_id": "session_empty_1234"}
            journal = mock.Mock(data={"completed": False, "abort_reason": "interrupted",
                                     "collection_context": context})
            rx.attach_control(config(), journal, context)
            meta = json.loads((session / "meta.json").read_text())
            runtime = json.loads((session / "capture_runtime.json").read_text())
            self.assertEqual(meta["environment"], {key: context[key] for key in
                ("room", "setup_id", "empty_reference_session_id")})
            self.assertEqual(meta["label"]["activity"], "walking")
            self.assertEqual(runtime["room"], "G304")
            self.assertFalse(meta["use_for_final_training"])

    def test_coordinator_mismatch_and_denied_approval(self):
        for mismatch in (True, False):
            channel = mock.Mock()
            channel.expect.return_value = {"role": "TX", "config": config(4) if mismatch else config(), "ping": {"ok": True}}
            acquire = mock.Mock()
            def deny():
                raise KeyboardInterrupt()
            with self.assertRaises(common.Failure if mismatch else KeyboardInterrupt):
                rx.coordinate(channel, config(), common.Gate(), MemoryJournal(), acquire, deny)
            acquire.assert_not_called()

    def test_postprocess_interrupt_reaps_child(self):
        children = []
        actual_popen = subprocess.Popen
        def spawn(*args, **kwargs):
            child = actual_popen(*args, **kwargs)
            children.append(child)
            return child
        def interrupt():
            raise KeyboardInterrupt()
        with mock.patch.object(capture.subprocess, "Popen", side_effect=spawn):
            with self.assertRaises(KeyboardInterrupt):
                capture.run_checked([sys.executable, "-c", "import time; time.sleep(100)"], interrupt)
        self.assertIsNotNone(children[0].poll())

    def test_logger_guard_eof_reaps_real_child(self):
        guard = subprocess.Popen([sys.executable, str(ROOT / "scripts/capture/csi_logger_guard.py"),
                                  sys.executable, "-c", "import time; time.sleep(100)"],
                                 stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        guard.stdin.close()
        self.assertEqual(guard.wait(timeout=12), 0)


class ZeroPeopleDatasetTests(unittest.TestCase):
    def test_zero_label_survives_real_metadata_and_feature_generation(self):
        def load_script(name, relative_path):
            spec = importlib.util.spec_from_file_location(name, str(ROOT / relative_path))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module

        metadata = load_script("test_zero_metadata", "scripts/dataset/create_meta.py")
        structured = load_script("test_zero_structured", "scripts/preprocess/build_structured_dataset.py")
        assembler = load_script("test_zero_assembler", "scripts/dataset/assemble_structured_dataset.py")
        with tempfile.TemporaryDirectory(prefix="csi_zero_test_") as temp:
            session = Path(temp) / "data/0_people/META_DATA" / SID
            session.mkdir(parents=True)
            csi_path = Path(temp) / "data/0_people/CSI_DATA" / (SID + ".dat")
            csi_path.parent.mkdir(parents=True)
            # Synthetic Intel 5300 frames only: real parser, scaling and CSV
            # generation are exercised without copying any collected session.
            with csi_path.open("wb") as handle:
                for index in range(301):
                    header = bytearray(20)
                    struct.pack_into("<IH", header, 0, index * 10000, index)
                    header[8:16] = bytes([3, 2, 40, 41, 39, 164, 20, 0x24])
                    struct.pack_into("<HH", header, 16, 372, 0x210f)
                    payload = b"\xbb" + header + b"\x11" * 372
                    handle.write(struct.pack(">H", len(payload)) + payload)
            relative_csi = os.path.relpath(str(csi_path), str(session))
            self.assertEqual(metadata.main([str(session), "--no-system-probe", "--csi-file", relative_csi,
                "--num-people", "0", "--activity", "empty", "--label-status", "stable_full_session",
                "--room", "G304", "--setup-id", "A", "--empty-reference-session-id", SID,
                "--duration-sec", "3", "--planned-duration-sec", "3", "--dataset-role", "training_candidate",
                "--use-for-final-training", "true"]), 0)
            meta = json.loads((session / "meta.json").read_text())
            self.assertIs(type(meta["label"]["num_people"]), int)
            self.assertEqual(meta["label"]["num_people"], 0)
            self.assertEqual(meta["label"]["activity"], "empty")
            self.assertEqual(meta["environment"]["room"], "G304")
            self.assertEqual(meta["capture"]["csi_record_count"], 301)

            output = Path(temp) / "structured" / SID
            self.assertEqual(structured.main([str(session), "--csi-file", relative_csi,
                                             "--output-dir", str(output), "--strict"]), 0)
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["label"]["num_people"], 0)
            self.assertTrue(manifest["label"]["has_trainable_label"])
            self.assertEqual(manifest["environment"], {"room": "G304", "setup_id": "A",
                                                     "empty_reference_session_id": SID})
            self.assertEqual(manifest["windows"], {"kept": 2, "dropped_short": 0, "feature_count": 88})
            self.assertTrue(manifest["quality"]["final_training_allowed"])
            self.assertEqual(assembler.should_include(manifest, mock.Mock(
                include_prototype=False, include_needs_review=False)), (True, "final training"))
            with (output / "window_features.csv").open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(row["num_people"] == "0" and row["activity"] == "empty" for row in rows))
            assembled_manifest = Path(temp) / "assembled_manifest.json"
            self.assertEqual(assembler.main([
                "--structured-dir", str(output.parent), "--out-csv", str(Path(temp) / "assembled.csv"),
                "--out-manifest", str(assembled_manifest)]), 0)
            combined = json.loads(assembled_manifest.read_text())
            self.assertEqual(combined["selected_sessions"][0]["environment"], manifest["environment"])
            self.assertEqual(combined["row_count"], 2)


class InstallerTests(unittest.TestCase):
    def test_installer_repeat_and_preserve(self):
        with tempfile.TemporaryDirectory(prefix="한글 desktop ") as temp:
            destination = Path(temp)
            installer.install("both", destination)
            installer.install("both", destination)
            for role in ("rx", "tx"):
                path = destination / ("csi-capture-" + role + ".desktop")
                text = path.read_text()
                self.assertIn("Terminal=true", text)
                self.assertIn("Path=" + str(ROOT), text)
                self.assertIn(str(ROOT / "tools" / ("csi_capture_" + role + "_launcher.py")), text)
                self.assertNotIn("@PROJECT_ROOT@", text)
                self.assertTrue(os.access(str(path), os.X_OK))
            target = destination / "csi-capture-rx.desktop"
            target.write_text("user file")
            with self.assertRaises(RuntimeError):
                installer.install("rx", destination)
            self.assertEqual(target.read_text(), "user file")

    def test_cli_compatibility(self):
        for script in ("scripts/sender/safe_sender.py", "scripts/capture/capture_prototype.py",
                       "tools/csi_capture_rx_launcher.py", "tools/csi_capture_tx_launcher.py"):
            result = subprocess.run([sys.executable, str(ROOT / script), "--help"], cwd="/tmp", stdout=subprocess.PIPE)
            self.assertEqual(result.returncode, 0)
        result = subprocess.run(["bash", "-n", str(ROOT / "tools/start_4_people_20min_capture.sh")])
        self.assertEqual(result.returncode, 0)
        args = capture.build_parser().parse_args(["--duration", "1200", "--num-people", "4", "--camera-device", "/dev/video0"])
        self.assertEqual(args.duration, 1200)
        self.assertFalse(args.camera_no_preview)


if __name__ == "__main__":
    unittest.main(verbosity=2)
