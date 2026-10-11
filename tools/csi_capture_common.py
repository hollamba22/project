#!/usr/bin/env python3
"""CSI desktop launchers: Python 3.6+, bounded JSONL control and shared checks."""
import argparse
import ipaddress
import json
import math
import os
from pathlib import Path
import queue
import re
import secrets
import select
import signal
import socket
import subprocess
import sys
import threading
import time
from decimal import Decimal, InvalidOperation

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/capture"))
from webcam_recorder import discover_devices, inspect_device, WebcamRecorder

VERSION = 1
CONTROL_PORT = 5006
SSID = "Minhyuck S24+"
PROFILE = "김민혁 핫스팟"
MAX_MESSAGE = 16384
TYPES = {"HELLO", "CONFIG", "TX_READY", "READY_ACK", "START", "START_ACK",
         "HEARTBEAT", "STOP", "FAILED", "DONE", "COMPLETE", "COMPLETE_ACK"}


class Failure(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise Failure(message)


def people(value):
    require(bool(re.fullmatch(r"[0-9]+", value)) and int(value) >= 0,
            "인원 수는 0 이상의 정수여야 합니다. 빈 방은 0을 입력하세요.")
    return int(value)


def minutes(value):
    try:
        number = Decimal(value)
        seconds = number * 60
        require(number.is_finite() and number > 0 and math.isfinite(float(seconds))
                and float(seconds) > 0, "수집 시간은 유한한 양수여야 합니다.")
        return float(seconds)
    except (InvalidOperation, ValueError, OverflowError):
        raise Failure("수집 시간은 양의 숫자(분)여야 합니다.")


def yesno(value):
    require(value.upper() in ("Y", "N"), "Y 또는 N을 입력하세요.")
    return value.upper() == "Y"


def ask(prompt, convert=str, default=None, health=None):
    while True:
        print(prompt + (" [{}]".format(default) if default is not None else "") + " (Q: 취소): ",
              end="", flush=True)
        if health:
            while not select.select([sys.stdin], [], [], 0.2)[0]:
                health()
            health()
        value = sys.stdin.readline()
        if not value or value.strip().upper() == "Q":
            raise KeyboardInterrupt()
        value = value.strip() or default
        try:
            return convert(value if value is not None else "")
        except (Failure, ValueError) as exc:
            print("[실패] {}".format(exc))


def confirm(prompt, health=None):
    require(ask(prompt, yesno, "N", health), "운영자가 승인하지 않아 안전 종료합니다.")


def command(args, timeout=8):
    try:
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                universal_newlines=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Failure("명령 실행 실패 {}: {}".format(args[0], exc))
    require(result.returncode == 0, "명령 실패: {}: {}".format(" ".join(args), result.stderr.strip()))
    return result.stdout.strip()


def ipv4(value, allow_loopback=False):
    try:
        ip = ipaddress.IPv4Address(value)
        require(not ip.is_unspecified and not ip.is_multicast and
                (allow_loopback or not ip.is_loopback), "사용할 수 없는 IPv4 주소입니다.")
        return str(ip)
    except ipaddress.AddressValueError:
        raise Failure("유효한 IPv4 주소를 입력하세요.")


def wifi(interface=None, target=None):
    interfaces = re.findall(r"Interface\s+(\S+)", command(["iw", "dev"]))
    if target:
        route = command(["ip", "-4", "route", "get", ipv4(target)])
        match = re.search(r"\bdev\s+(\S+)", route)
        require(match is not None and match.group(1) in interfaces,
                "RX 경로가 Wi-Fi를 통하지 않습니다. ip route get으로 확인하세요.")
        require(not interface or interface == match.group(1), "지정 인터페이스와 RX 경로가 다릅니다.")
        interface = match.group(1)
    connected = []
    for candidate in interfaces:
        if interface and candidate != interface:
            continue
        link = command(["iw", "dev", candidate, "link"])
        if "Connected to" in link:
            connected.append((candidate, link))
    require(len(connected) == 1, "연결된 Wi-Fi를 하나로 특정할 수 없습니다. NetworkManager에서 먼저 연결하고 --interface를 지정하세요.")
    interface, link = connected[0]
    def match(pattern, text):
        found = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
        require(found is not None, "현재 Wi-Fi 정보를 읽을 수 없습니다.")
        return found.group(1).strip()
    address = command(["ip", "-4", "-o", "addr", "show", "dev", interface, "scope", "global"])
    cidr = match(r"\binet\s+(\S+)", address)
    info = command(["iw", "dev", interface, "info"])
    result = {"interface": interface, "ssid": match(r"^\s*SSID:\s*(.+)$", link),
              "bssid": match(r"Connected to\s+([0-9a-f:]+)", link).lower(),
              "frequency": int(match(r"^\s*freq:\s*(\d+)", link)),
              "channel": int(match(r"channel\s+(\d+)", info)),
              "ip": ipv4(cidr.split("/")[0]), "cidr": cidr,
              "mac": Path("/sys/class/net/{}/address".format(interface)).read_text().strip(),
              "power_save": command(["iw", "dev", interface, "get", "power_save"])}
    if target:
        require(re.search(r"\bsrc\s+" + re.escape(result["ip"]) + r"(?:\s|$)", route),
                "RX 경로의 송신 IP가 Wi-Fi IP와 다릅니다.")
    return result


def hotspot(network):
    selected = network.get("ssid")
    require(isinstance(selected, str) and bool(selected.strip()),
            "연결된 Wi-Fi의 SSID를 확인할 수 없습니다. NetworkManager에서 먼저 연결하세요.")
    verified = selected == SSID
    print("[2][통과] 현재 연결된 Wi-Fi SSID: {}".format(selected))
    print("[안내] 이 SSID를 수집 프로필에 자동 반영했습니다.")
    if not verified:
        confirm("[경고] 김민혁 핫스팟과 다른 성공 검증 전 환경입니다. 현재 Wi-Fi로 진행하려면 Y")
    else:
        require(ask("김민혁 핫스팟으로 계속할까요? Y/N", yesno, "Y"),
                "운영자가 승인하지 않아 안전 종료합니다.")
    if network["frequency"] != 2437 or network["channel"] != 6:
        confirm("[경고] 성공 기준 2437 MHz/채널 6과 다릅니다. 현재 채널을 유지하고 진행하려면 Y")
    return {"display_name": PROFILE if verified else selected,
            "ssid": selected, "verified": verified,
            "frequency_confirmed": True}


def camera_policy(required=False):
    devices = discover_devices()
    print("[4] V4L2 장치: " + (", ".join(d["path"] + " (" + d["name"] + ")" for d in devices) or "없음"))
    if required:
        require(bool(devices), "자유 테스트는 정답 검수용 카메라가 필요합니다. 카메라를 연결한 뒤 다시 실행하세요.")
        print("[안내] 자유 테스트는 실제 인원 검수를 위해 영상 녹화를 사용합니다.")
    enabled = True if required else ask("카메라를 사용합니까? Y/N", yesno, "Y" if devices else "N")
    if not enabled:
        confirm("[경고] 라벨 검증 영상이 없습니다. 영상 없이 계속하려면 Y")
        return {"enabled": False, "device": None, "preview": False, "label_video_missing": True}
    device = ask("카메라 장치", default="/dev/video0")
    require(device in [d["path"] for d in devices], "목록에 있는 V4L2 장치를 선택하세요.")
    inspect_device(device)
    require(bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")),
            "미리보기 디스플레이가 없습니다. 데스크톱 터미널에서 실행하세요.")
    # Inspect plugins and supported formats; actual preview/encoding is checked before START.
    for plugin in ("v4l2src", "videoconvert", "videoscale", "videorate", "tee", "queue",
                   "autovideosink", "vp8enc", "webmmux", "filesink"):
        command(["gst-inspect-1.0", plugin])
    if required:
        command(["gst-inspect-1.0", "clockoverlay"])
    formats = command(["v4l2-ctl", "-d", device, "--list-formats-ext"])
    require(bool(formats), "카메라 포맷을 확인하지 못했습니다.")
    return {"enabled": True, "device": device, "preview": True, "width": 640,
            "height": 480, "fps": 10, "label_video_missing": False, "formats": formats[:4000]}


def validate_config(config):
    require(isinstance(config, dict), "설정 형식 오류")
    require(set(config) == {"num_people", "duration_sec", "sender_duration_sec", "profile",
                            "camera", "rate", "size", "data_port", "session_id"}, "설정 필드 오류")
    require(type(config["num_people"]) is int and config["num_people"] >= 0,
            "인원 설정 오류: 0 이상의 정수여야 합니다. (0명: 빈 방)")
    duration = config["duration_sec"]
    require(type(duration) in (int, float) and math.isfinite(duration) and duration > 0, "시간 설정 오류")
    require(config["sender_duration_sec"] == duration + 10, "TX 시간은 RX보다 정확히 10초 길어야 합니다.")
    require(config["rate"] == 100 and config["size"] == 512 and config["data_port"] == 5005,
            "트래픽 설정이 성공 기준과 다릅니다.")
    require(bool(re.fullmatch(r"session_[A-Za-z0-9_]{1,80}", config["session_id"])), "세션 ID 오류")
    profile, camera = config["profile"], config["camera"]
    require(isinstance(profile, dict) and isinstance(profile.get("ssid"), str) and
            type(profile.get("verified")) is bool and profile.get("frequency_confirmed") is True,
            "핫스팟 설정 오류")
    require(profile["verified"] == (profile["ssid"] == SSID), "검증 프로필 설정 오류")
    require(isinstance(camera, dict) and type(camera.get("enabled")) is bool and
            camera.get("preview") == camera["enabled"], "카메라 정책 오류")
    if camera["enabled"]:
        require((camera.get("width"), camera.get("height"), camera.get("fps")) == (640, 480, 10)
                and bool(re.fullmatch(r"/dev/video[0-9]+", camera.get("device", ""))), "카메라 설정 오류")


def check_pair(rx, tx, profile, peer, allow_loopback=False):
    for report in (rx, tx):
        require(isinstance(report, dict), "네트워크 보고 형식 오류")
        ipv4(report["ip"], allow_loopback)
        require(report["ssid"] == profile["ssid"], "실제 SSID와 선택 프로필이 다릅니다.")
        require(bool(re.fullmatch(r"[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}", report["bssid"])), "BSSID 형식 오류")
    require(rx["bssid"].lower() == tx["bssid"].lower(), "RX/TX BSSID가 다릅니다.")
    require(rx["frequency"] == tx["frequency"] and rx["channel"] == tx["channel"], "RX/TX 채널이 다릅니다.")
    require(tx["ip"] == peer, "제어 peer IP와 TX 보고 IP가 다릅니다.")
    require(ipaddress.ip_address(tx["ip"]) in ipaddress.ip_network(rx["cidr"], strict=False),
            "TX가 RX Wi-Fi 서브넷에 없습니다.")


def packet(kind, session_id="", nonce="", **body):
    return {"protocol_version": VERSION, "session_id": session_id,
            "nonce": nonce, "type": kind, "body": body}


def validate_message(message):
    require(isinstance(message, dict) and set(message) ==
            {"protocol_version", "session_id", "nonce", "type", "body"}, "제어 메시지 스키마 오류")
    require(type(message["protocol_version"]) is int and message["protocol_version"] == VERSION,
            "제어 프로토콜 버전이 다릅니다.")
    require(isinstance(message["type"], str) and message["type"] in TYPES and isinstance(message["body"], dict),
            "제어 메시지 종류/본문 오류")
    if message["type"] == "HELLO":
        require(message["session_id"] == "" and message["nonce"] == "", "HELLO 세션 오류")
    else:
        require(isinstance(message["session_id"], str) and
                bool(re.fullmatch(r"session_[A-Za-z0-9_]{1,80}", message["session_id"])) and
                isinstance(message["nonce"], str) and bool(re.fullmatch(r"[0-9a-f]{64}", message["nonce"])),
                "세션 ID/nonce 형식 오류")
    fields = {"HELLO": {"pin", "role", "network", "profile"},
              "CONFIG": {"role", "network", "config"}, "TX_READY": {"role", "config", "ping"},
              "READY_ACK": set(), "START": set(), "START_ACK": set(), "HEARTBEAT": set(),
              "STOP": {"reason"}, "FAILED": {"reason"}, "DONE": {"result"},
              "COMPLETE": set(), "COMPLETE_ACK": set()}
    require(set(message["body"]) == fields[message["type"]], "메시지 본문 필드 오류")
    return message


class Wire:
    def __init__(self, sock):
        self.sock = sock
        self.sock.settimeout(1)
        self.buffer = b""
        self.lock = threading.Lock()

    def send(self, message):
        validate_message(message)
        raw = json.dumps(message, ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n"
        require(len(raw) <= MAX_MESSAGE, "제어 메시지 크기 초과")
        with self.lock:
            self.sock.sendall(raw)

    def receive(self, timeout=15):
        end = time.monotonic() + timeout
        while b"\n" not in self.buffer:
            require(len(self.buffer) < MAX_MESSAGE, "제어 메시지 크기 초과")
            require(time.monotonic() < end, "제어 메시지 대기 시간 초과")
            try:
                data = self.sock.recv(min(4096, MAX_MESSAGE - len(self.buffer)))
            except socket.timeout:
                continue
            require(bool(data), "제어 연결이 끊겼습니다.")
            self.buffer += data
        raw, self.buffer = self.buffer.split(b"\n", 1)
        require(len(raw) + 1 <= MAX_MESSAGE, "제어 메시지 크기 초과")
        try:
            return validate_message(json.loads(raw.decode("utf-8")))
        except (ValueError, UnicodeError, TypeError):
            raise Failure("잘못된 JSON 제어 메시지입니다.")


class Channel:
    """One reader + serialized writer; heartbeat remains live during operator input."""
    def __init__(self, wire, session_id, nonce, timeout=15):
        self.wire, self.session_id, self.nonce = wire, session_id, nonce
        self.timeout = timeout
        self.inbox = queue.Queue(32)
        self.closed = threading.Event()
        self.error = None
        self.completed = False
        self.thread = threading.Thread(target=self._read, name="csi-control")
        self.beater = threading.Thread(target=self._beat, name="csi-heartbeat")
        self.thread.daemon = self.beater.daemon = True
        self.thread.start()
        self.beater.start()

    def send(self, kind, **body):
        self.wire.send(packet(kind, self.session_id, self.nonce, **body))

    def _read(self):
        try:
            while not self.closed.is_set():
                msg = self.wire.receive(self.timeout)
                require(msg["session_id"] == self.session_id and msg["nonce"] == self.nonce,
                        "다른 세션의 제어 메시지입니다.")
                if msg["type"] in ("FAILED", "STOP"):
                    raise Failure("상대가 중단했습니다: " + str(msg["body"]["reason"])[:300])
                if msg["type"] == "COMPLETE_ACK":
                    self.completed = True
                if msg["type"] != "HEARTBEAT":
                    self.inbox.put_nowait(msg)
        except Exception as exc:
            if not self.closed.is_set() and not self.completed:
                self.error = Failure(str(exc))

    def _beat(self):
        while not self.closed.wait(2):
            try:
                self.send("HEARTBEAT")
            except Exception as exc:
                if not self.completed:
                    self.error = Failure("heartbeat 전송 실패: " + str(exc))
                return

    def check(self):
        if self.error:
            raise self.error

    def receive(self, timeout=0.2):
        try:
            return self.inbox.get(timeout=timeout)
        except queue.Empty:
            self.check()
            return None

    def expect(self, kind, timeout=30):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            msg = self.receive()
            if msg:
                require(msg["type"] == kind, "예상하지 않은 상태: " + msg["type"])
                return msg["body"]
        raise Failure(kind + " 대기 시간 초과")

    def close(self):
        self.closed.set()
        try:
            self.wire.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.wire.sock.close()
        self.thread.join(2)
        self.beater.join(2)


class Gate:
    def __init__(self):
        self.state = "LISTENING"

    def ready(self, expected, actual):
        validate_config(actual)
        require(expected == actual and self.state == "LISTENING", "RX/TX 설정 또는 준비 상태 불일치")
        self.state = "TX_READY"

    def approve(self):
        require(self.state == "TX_READY", "TX_READY 이전에는 RX 승인 불가")
        self.state = "APPROVED"

    def capture_ready(self):
        require(self.state == "APPROVED", "RX 승인 이전에는 START 불가")
        self.state = "CAPTURE_READY"

    def start(self):
        if self.state == "STARTED":
            return False
        require(self.state == "CAPTURE_READY", "capture READY 이전에는 송신 불가")
        self.state = "STARTED"
        return True


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    os.replace(str(temp), str(path))


class Journal:
    def __init__(self, role, session_id):
        self.path = ROOT / "outputs/launcher" / (session_id + "_" + role.lower() + ".json")
        require(not self.path.exists(), "제어 로그가 이미 존재합니다.")
        self.data = {"schema_version": "1.0-control", "role": role, "session_id": session_id,
                     "completed": False, "events": []}
        self.event("OPEN")

    def event(self, event, **details):
        self.data["events"].append(dict({"event": event, "wall_epoch": time.time()}, **details))
        save(self.path, self.data)

    def finish(self, success, reason=""):
        self.data.update(completed=success, abort_reason=reason)
        self.event("COMPLETE" if success else "FAILED")


def stop_child(child):
    if child is None or child.poll() is not None:
        return
    for sig, timeout in ((signal.SIGINT, 3), (signal.SIGTERM, 3), (signal.SIGKILL, 3)):
        try:
            child.send_signal(sig)
            child.wait(timeout=timeout)
            return
        except subprocess.TimeoutExpired:
            continue
        except ProcessLookupError:
            return
    raise Failure("자식 프로세스 종료 확인 실패")


def config_summary(config):
    print("[통과] RX 확정 설정: {}명 / {}분 (RX {}초, TX {}초) / {} / 카메라 {} / 100 pkt/s, 512 B, UDP 5005".format(
        config["num_people"], config["duration_sec"] / 60, config["duration_sec"],
        config["sender_duration_sec"], config["profile"]["display_name"], config["camera"]["enabled"]))
    if config["num_people"] == 0:
        print("[안내] 0명은 빈 방 기준 데이터입니다. RX/TX와 핫스팟은 켜 두고, "
              "수집 시작부터 종료까지 방에 사람이 없어야 합니다.")


def parser(role):
    result = argparse.ArgumentParser(description="CSI {} 대화형 실행기".format(role))
    result.add_argument("--interface", default=None)
    result.add_argument("--control-port", type=int, default=CONTROL_PORT)
    return result


def entry(run, role):
    args = parser(role).parse_args()
    require(1 <= args.control_port <= 65535 and args.control_port != 5005, "제어 포트는 UDP 5005와 다른 유효 포트여야 합니다.")
    def interrupt(_signum, _frame):
        raise KeyboardInterrupt()
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, interrupt)
    while True:
        try:
            run(args)
            print("[통과] 양쪽 COMPLETE 확인 완료")
            return 0
        except KeyboardInterrupt:
            print("\n[실패] 취소됨. 이번 세션은 성공 처리하지 않습니다.")
            return 130
        except Exception as exc:
            print("[실패] {}".format(exc))
            print("[점검] NetworkManager 연결, iw dev <인터페이스> link, ip -4 addr, ip route get <현재_RX_IP>, ping -c 4 <현재_RX_IP>")
            print("[점검] TCP {} / UDP 5005와 AP client isolation·방화벽을 확인하세요. 네트워크 설정은 자동 변경하지 않습니다.".format(args.control_port))
            try:
                if ask("처음부터 새 세션으로 재시도하려면 R", default="Q").upper() != "R":
                    return 1
            except KeyboardInterrupt:
                return 1
