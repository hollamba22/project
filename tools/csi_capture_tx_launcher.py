#!/usr/bin/env python3
"""TX wizard: RX owns settings; START is the only transition that launches UDP."""
import json
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from csi_capture_common import (ROOT, Failure, require, ask, ipv4, wifi, hotspot, command,
    validate_config, check_pair, packet, Wire, Channel, Journal, confirm, config_summary,
    entry, stop_child)


def sender_command(config, rx_ip, tx_ip, nonce, result_path):
    return [sys.executable, str(ROOT / "scripts/sender/safe_sender.py"),
            "--target", rx_ip, "--bind", tx_ip, "--mode", "udp", "--port", str(config["data_port"]),
            "--duration", str(config["sender_duration_sec"]), "--rate", str(config["rate"]),
            "--size", str(config["size"]), "--session-nonce", nonce, "--result-json", str(result_path)]


def transmit(channel, config, journal, spawn, read_result, verify_start=lambda: None):
    child = None
    started_at = None
    done = False
    deadline = time.monotonic() + 900
    try:
        while True:
            channel.check()
            require(time.monotonic() < deadline, "RX 제어 상태 대기 시간 초과")
            msg = channel.receive(0.1)
            if msg:
                kind = msg["type"]
                if kind == "START":
                    if started_at is None:
                        verify_start()
                        channel.send("START_ACK")
                        journal.event("START_ACK")
                        child = spawn()
                        started_at = time.monotonic()
                        deadline = started_at + config["sender_duration_sec"] + 300
                        journal.event("SENDER_STARTED")
                    else:
                        # Never spawn twice, including after the first sender has finished.
                        channel.send("START_ACK")
                elif kind == "COMPLETE":
                    require(done, "sender 완료 전 COMPLETE 수신")
                    channel.send("COMPLETE_ACK")
                    channel.completed = True
                    journal.event("COMPLETE_ACK")
                    return
                else:
                    raise Failure("TX 상태에서 허용하지 않은 메시지: " + kind)
            if child is not None and not done and child.poll() is not None:
                require(child.returncode == 0, "UDP sender 비정상 종료: {}".format(child.returncode))
                require(time.monotonic() - started_at >= config["sender_duration_sec"] - 0.1,
                        "UDP sender가 계획 시간 전에 종료했습니다.")
                result = read_result()
                channel.send("DONE", result=result)
                journal.event("SENDER_DONE", result=result)
                done = True
    finally:
        stop_child(child)


def run(args):
    journal = Journal("TX", "session_" + time.strftime("%Y%m%d_%H%M%S") + "_" + secrets.token_hex(4))
    channel = sock = None
    success, reason = False, "TX 준비 중 취소"
    try:
        network = wifi(args.interface)
        profile = hotspot(network)
        target = ask("[3] RX 화면의 현재 IPv4", ipv4)
        network = wifi(network["interface"], target)
        pin = ask("RX 화면의 일회용 연결 PIN")
        require(len(pin) == 6 and pin.isdigit(), "PIN은 6자리 숫자입니다.")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.bind((network["ip"], 0))
        sock.connect((target, args.control_port))
        wire = Wire(sock)
        wire.send(packet("HELLO", pin=pin, role="TX", network=network, profile=profile))
        msg = wire.receive(15)
        require(msg["type"] == "CONFIG" and msg["body"]["role"] == "RX", "RX CONFIG 응답이 필요합니다.")
        config, rx = msg["body"]["config"], msg["body"]["network"]
        validate_config(config)
        require(config["session_id"] == msg["session_id"], "설정 세션 ID 불일치")
        require(rx["ip"] == sock.getpeername()[0] == target, "RX peer 주소 불일치")
        require(sock.getsockname()[0] == network["ip"], "TX 실제 연결 주소 불일치")
        check_pair(rx, network, profile, network["ip"])
        require(config["profile"]["ssid"] == profile["ssid"], "설정 핫스팟 불일치")
        channel = Channel(wire, msg["session_id"], msg["nonce"])
        journal.data["negotiated_session_id"] = msg["session_id"]
        journal.event("CONFIG", config=config, rx=rx, tx=network)
        config_summary(config)
        confirm("[4] RX가 정한 위 설정을 승인하려면 Y", channel.check)
        ping = command(["ping", "-n", "-c", "4", "-W", "2", "-I", network["interface"], target], 12)
        import re
        require(re.search(r"\b4 (?:packets )?received\b", ping) is not None, "ping 4회 모두 성공해야 합니다.")
        channel.send("TX_READY", role="TX", config=config, ping={"ok": True, "output": ping[:2000]})
        channel.expect("READY_ACK")
        print("[5][대기] 양방향 통신 통과. RX 최종 승인과 capture READY/START를 기다립니다.")
        journal.event("TX_READY")
        with tempfile.TemporaryDirectory(prefix="csi_sender_") as temp:
            result_path = Path(temp) / "result.json"
            transmit(channel, config, journal,
                     lambda: subprocess.Popen(sender_command(config, target, network["ip"], msg["nonce"], result_path),
                                              start_new_session=True),
                     lambda: json.loads(result_path.read_text()),
                     lambda: require(wifi(network["interface"], target) == network, "TX 네트워크가 변경되었습니다."))
        success, reason = True, ""
    except BaseException as exc:
        reason = "운영자 취소/Ctrl+C" if isinstance(exc, KeyboardInterrupt) else str(exc)
        if channel:
            try:
                channel.send("FAILED", reason=reason[:300])
            except Exception:
                pass
        raise
    finally:
        if channel:
            channel.close()
        elif sock:
            sock.close()
        journal.finish(success, reason)
        print("제어 기록: " + str(journal.path))


if __name__ == "__main__":
    sys.exit(entry(run, "TX"))
