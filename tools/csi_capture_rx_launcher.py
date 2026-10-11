#!/usr/bin/env python3
"""RX wizard and coordinator; capture_prototype remains the acquisition engine."""
import errno
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

from csi_capture_common import (ROOT, Failure, require, ask, people, minutes, hotspot,
    camera_policy, wifi, command, validate_config, check_pair, packet, Wire, Channel,
    Gate, Journal, save, confirm, config_summary, entry)
import capture_prototype as capture
from csi_activity_guide import (ActivityGuide, FreeTestGuide, participant_input, seconds_input,
                                build_segments, repetitions_input, assign_walking_order, ACTIVITY_NAMES)


ACTIVITIES = {
    "0": ("mixed", "자동 진행: 앉기 → 서기 → 교대 걷기 (동작당 기본 5분, 반복 횟수 선택)"),
    "1": ("sitting", "지정 자리 앉기: 작은 손동작·자세 조절 허용, 자리 이동 없음"),
    "2": ("standing", "지정 자리 서기: 자연스러운 자세 조절 허용, 자리 이동 없음"),
    "3": ("walking", "1명씩 교대 걷기: 2m 왕복, 이동 5초/정지 5초, 60초마다 교대; 나머지는 앉기"),
    "4": ("sit_stand", "전반 앉기 / 후반 서기: 5분 수집이면 150초씩, 인원 유지"),
    "5": ("natural", "자연스러운 활동: 위의 고정 행동 프로토콜을 사용하지 않을 때만 선택"),
}


def capture_mode(value):
    require(value in ("1", "2"), "수집 종류는 1 또는 2를 선택하세요.")
    return "free_test" if value == "2" else "training"


def is_free_test(collection):
    return (collection or {}).get("capture_mode") == "free_test"


def collection_root(config, collection=None):
    return ROOT / "data" / ("free_test" if is_free_test(collection) else str(config["num_people"]) + "_people")


def collection_id(value):
    value = value.strip().upper()
    require(bool(re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{0,39}", value)) and
            value not in {"UNKNOWN", "PROJECT_ROOM", "PROTOTYPE_ROOM", "ROOM_NAME"},
            "실제 ID를 영문·숫자·밑줄·하이픈으로 입력하세요. 예: G304, A, 20260917_A")
    return value


def activity_choice(value):
    require(value in ACTIVITIES, "행동은 0~5 중에서 선택하세요.")
    return ACTIVITIES[value][0]


def empty_room_candidates(room, setup_id):
    """Only completed, nonfailed empty sessions in this room and setup are offered."""
    candidates = []
    for path in sorted((ROOT / "data/0_people/META_DATA").glob("session_*/meta.json"), reverse=True):
        try:
            meta = json.loads(path.read_text())
            runtime = json.loads((path.parent / "capture_runtime.json").read_text())
            control = json.loads((path.parent / "session_control.json").read_text())
            env = meta.get("environment", {})
            label = meta.get("label", {})
            if (env.get("room"), env.get("setup_id")) != (room, setup_id):
                continue
            if type(label.get("num_people")) is not int or label["num_people"] != 0:
                continue
            if meta.get("quality_status") != "valid_csi" or label.get("activity") != "empty":
                continue
            if runtime.get("completed") is not True or control.get("completed") is not True:
                continue
            if runtime.get("room") != room or runtime.get("setup_id") != setup_id:
                continue
            if runtime.get("num_people") != 0 or meta.get("session_id") != path.parent.name:
                continue
            csi = path.parent / meta["capture"]["csi_file"]
            if not csi.is_file() or csi.stat().st_size == 0:
                continue
            manifest = json.loads((ROOT / "data/structured" / path.parent.name / "manifest.json").read_text())
            if manifest.get("quality", {}).get("status") == "failed":
                continue
            candidates.append((path.parent.name, manifest.get("quality", {}).get("status", "needs_review")))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return candidates


def collection_settings(room, count, session_id, free_test=False):
    print("[안내] 같은 강의실에서도 AP/RX·안테나·가구 배치가 달라지면 새 배치 ID를 쓰고 0명을 다시 수집하세요.")
    setup = ask("[1-1] 배치 ID (기준 A / 변경 B 등)", collection_id, "A")
    activity = "empty"
    reference = session_id if count == 0 and not free_test else None
    if count or free_test:
        if free_test:
            activity = "free_test"
            print("[자유 테스트] 0~4명 범위에서 자유롭게 활동·입퇴실합니다. 인원·자리·행동 순서를 지정하지 않습니다.")
        else:
            for key in sorted(ACTIVITIES):
                print("  {}: {}".format(key, ACTIVITIES[key][1]))
            activity = ask("[1-2] 이번 파일의 행동", activity_choice, "0")
        candidates = empty_room_candidates(room, setup)
        if candidates:
            print("[1-3] {} / {}의 완료된 0명 세션 (영상·품질 검수는 별도):".format(room, setup))
            for index, (sid, quality) in enumerate(candidates, 1):
                print("  {}: {} [{}]".format(index, sid, quality))
            def select_reference(value):
                require(value.isdigit() and 0 <= int(value) <= len(candidates), "목록의 번호를 입력하세요.")
                return candidates[int(value) - 1][0] if int(value) else None
            reference = ask("연결할 0명 기준 번호 (0: 연결 보류)", select_reference, "1")
        else:
            print("[안내] {} / {}의 완료된 0명 기준이 없습니다. 오늘은 0명을 먼저 수집하세요. "
                  "계속하면 기준 미연결로 기록됩니다.".format(room, setup))
    result = {"room": room, "setup_id": setup, "activity": activity,
              "empty_reference_session_id": reference}
    if free_test:
        result.update(capture_mode="free_test", planned_people_range=[0, 4])
    return result


def collection_summary(collection):
    print("[수집 장소 확인] 강의실 {} / 배치 {} / 행동 {}".format(
        collection["room"], collection["setup_id"], collection["activity"]))
    print("[0명 기준 연결] " + (collection["empty_reference_session_id"] or "미연결"))
    if is_free_test(collection):
        print("[자유 테스트] 0~4명 자유 입퇴실 / 실제 인원 미확정 / 영상 검수 후 정답 작성")
        print("[저장] data/free_test — 기존 인원별 학습 자료와 분리합니다.")
        print("[TX 안내] TX 화면의 4명은 자유 테스트 범위의 최대 인원입니다.")
    elif collection["activity"] == "empty":
        print("[안내] 이번 파일은 빈 방 기준 후보입니다. 조작자도 퇴실하고 실제 퇴실 전 구간은 검수에서 제외하세요.")
    else:
        print("[행동 안내] " + next(info for code, info in ACTIVITIES.values() if code == collection["activity"]))


def capture_schedule(activity):
    if activity == "mixed":
        seconds = ask("[3] 한 동작당 수집 시간(분)", minutes, "5")
        repeat = ask("[3-1] 앉기→서기→걷기 반복 횟수 (1회=15분, 2회=30분: 동작당 5분 기준)",
                     repetitions_input, "2")
    elif activity == "free_test":
        seconds = ask("[3] 자유 테스트 수집 시간(분)", minutes, "40")
        repeat = 1
    else:
        seconds = ask("[3] 수집 시간(분)", minutes, "5")
        repeat = 1
    segments = build_segments(activity, seconds, repeat)
    if activity == "free_test":
        print("[수집 계획] 총 {}분 연속 CSI·영상 / 0~4명 자유 활동·입퇴실 / 정답은 추후 영상으로 작성".format(
              segments[-1]["end_sec"] / 60))
    else:
        print("[수집 계획] {}개 구간 / 총 {}분 / 인원수는 파일 전체에서 고정".format(
              len(segments), segments[-1]["end_sec"] / 60))
    return segments


def guidance_settings(count, segments):
    free_test = segments[0]["activity"] == "free_test"
    participants = []
    if count and not free_test:
        default = " ".join("P{0}:Z{0}".format(i + 1) for i in range(count))
        participants = ask("[4-1] 참가자:자리 (입력 순서대로 걷기 교대)",
                           lambda value: participant_input(value, count), default)
    prepare = ask("[4-2] 촬영 준비 시간(초, 0~120)" if free_test else "[4-2] 퇴실·자리 준비 시간(초, 0~120)", seconds_input, "30")
    settle = ask("[4-3] 추가 시작 대기(초, 0~120)" if free_test else "[4-3] 안정화 시간(초, 0~120)", seconds_input, "0" if free_test else "60")
    assign_walking_order(segments, participants)
    return {"version": 2, "participants": participants, "prepare_sec": prepare, "settle_sec": settle,
            "segments": segments,
            "walking_phase_sec": 5, "walking_cycle_sec": 20, "walking_rotation_sec": 60,
            "timing_reference": "first_valid_session_udp_packet",
            "annotation_kind": "unlabeled_free_test" if free_test else "planned_instructions_not_verified_actions"}


def open_control_listener(bind_ip, port):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # Reuse a completed connection's TIME_WAIT address. SO_REUSEPORT is
        # intentionally absent: an active RX listener must still block another.
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.settimeout(1)
        listener.bind((bind_ip, port))
        listener.listen(1)
        return listener
    except OSError as exc:
        listener.close()
        if exc.errno == errno.EADDRINUSE:
            reason = ("이미 사용 중이거나 이전 연결의 종료 대기 상태입니다. "
                      "기존 RX의 완료 여부를 확인하세요. 이전 버전 종료 직후라면 "
                      "약 1분 후 다시 실행하세요.")
        elif exc.errno == errno.EADDRNOTAVAIL:
            reason = "RX Wi-Fi 주소가 변경되었거나 해제되었습니다. 현재 연결을 확인하고 다시 실행하세요."
        else:
            reason = "소켓 오류 {}: {}".format(exc.errno, exc.strerror)
        raise Failure("TCP {}:{} 제어 포트 열기 실패: {}".format(bind_ip, port, reason))


def capture_activity(config, collection=None):
    if is_free_test(collection):
        return "free_test"
    return "empty" if config["num_people"] == 0 else (collection or {}).get("activity", "natural")


def capture_args(config, network, tx_ip=None, nonce=None, collection=None):
    collection = collection or {}
    free_test = is_free_test(collection)
    if free_test:
        require(config["camera"]["enabled"], "자유 테스트에는 영상 녹화가 필요합니다.")
    args = ["--duration", str(config["duration_sec"]),
            "--session-id", config["session_id"], "--collection-root",
            str(collection_root(config, collection)),
            "--interface", network["interface"], "--bind-ip", network["ip"],
            "--capture-purpose", "free_test" if free_test else "training", "--antenna-holder", "3d_printed_v1",
            "--activity", capture_activity(config, collection), "--room", collection.get("room", "unknown"),
            "--setup-id", collection.get("setup_id", "unknown"), "--sender-rate", "100",
            "--sender-size", "512", "--port", "5005", "--progress-interval", "60",
            "--first-packet-timeout", "20", "--stall-timeout", "5"]
    if free_test:
        args.append("--camera-clock-overlay")
    else:
        args += ["--num-people", str(config["num_people"])]
    if collection.get("empty_reference_session_id"):
        args += ["--empty-reference-session-id", collection["empty_reference_session_id"]]
    if config["camera"]["enabled"]:
        args += ["--camera-device", config["camera"]["device"], "--camera-width", "640",
                 "--camera-height", "480", "--camera-fps", "10"]
    if tx_ip:
        args += ["--expected-source", tx_ip, "--session-nonce", nonce]
    return capture.build_parser().parse_args(args)


def preflight(config, network, collection=None):
    state = capture.preflight(capture_args(config, network, collection=collection))
    require(not state["problems"], "수집 사전 점검 실패: " + "; ".join(state["problems"]))
    require(state["kernel"] == "4.15.0-213-generic", "성공 기준 커널 4.15.0-213-generic이 아닙니다.")
    require(network["interface"] == "wlp4s0" and network["mac"].lower() == "00:16:ea:ed:a9:80",
            "RX 인터페이스/MAC가 성공 기준과 다릅니다.")
    require("Power save: off" in network["power_save"], "Wi-Fi power save가 off가 아닙니다.")
    module = command(["modinfo", "-n", "iwlwifi"])
    require(module == "/lib/modules/4.15.0-213-generic/updates/iwlwifi.ko" and Path(module).is_file(),
            "수정 iwlwifi 모듈 경로를 확인하세요.")
    firmware = Path("/lib/firmware/iwlwifi-5000-2.ucode")
    require(str(firmware.resolve()) == "/lib/firmware/iwlwifi-5000-2.ucode.sigcomm2010" and firmware.is_file(),
            "CSI 펌웨어가 성공 기준과 다릅니다.")
    for tool in (capture.LOG_TOOL, str(ROOT / "third_party/linux-80211n-csitool-supplementary-master/netlink/parse_log")):
        require(os.access(tool, os.X_OK), "CSI 도구 실행 권한이 없습니다: " + tool)
    state.update(driver_module=module, firmware=str(firmware.resolve()), power_save=network["power_save"])
    return state


def attach_control(config, journal, collection=None):
    """Keep acquisition metadata separate from the stricter two-PC final verdict."""
    free_test = is_free_test(collection)
    session = collection_root(config, collection) / "META_DATA" / config["session_id"]
    if not session.is_dir():
        return
    save(session / "session_control.json", journal.data)
    guidance = journal.data.get("activity_guidance")
    if guidance:
        anchor = next((event["first_packet_wall_epoch"] for event in journal.data["events"]
                       if event["event"] == "GUIDE_TIME_ANCHOR"), None)
        save(session / "activity_segments.json", {
            "schema_version": "1.0-guide", "session_id": config["session_id"],
            "time_reference": "first_valid_session_udp_packet", "first_packet_wall_epoch": anchor,
            "segments": guidance["segments"], "completed": journal.data["completed"],
            "instruction_events_file": "session_control.json", "instruction_event_name": "GUIDE_CUE",
            "label_status": "unlabeled_free_test" if free_test else "planned_instructions_not_verified_actions",
            "alignment_note": "CSI feature-window seconds use the first CSI record, not this UDP anchor; verify alignment before joining."})
    if not (session / "meta.json").exists() and not journal.data["completed"]:
        save(session / "meta.json", {"schema_version": "1.0", "session_id": config["session_id"],
             "quality_status": "failed", "dataset_role": "failure_history", "use_for_final_training": False,
             "label": {"num_people": None if free_test else config["num_people"], "activity": capture_activity(config, collection),
                       "label_status": "unknown"},
             "capture": {"planned_duration_sec": config["duration_sec"]}})
    for name in ("capture_runtime.json", "meta.json"):
        path = session / name
        if path.exists():
            data = json.loads(path.read_text())
            data["session_control"] = {"file": "session_control.json", "completed": journal.data["completed"],
                                       "abort_reason": journal.data["abort_reason"]}
            if "activity_guidance" in journal.data:
                data["activity_guidance"] = {"file": "session_control.json", "events": "GUIDE_*",
                                             "segments_file": "activity_segments.json",
                                             "settings": journal.data["activity_guidance"]}
            if name == "meta.json":
                data.setdefault("capture", {})["planned_duration_sec"] = config["duration_sec"]
                if collection:
                    data.setdefault("environment", {}).update({key: collection[key] for key in
                        ("room", "setup_id", "empty_reference_session_id")})
            elif collection:
                data.update(collection)
            if free_test:
                data.update(dataset_role="test_candidate", use_for_final_training=False)
                if name == "meta.json":
                    data.setdefault("label", {}).update(num_people=None, label_status="unknown", activity="free_test")
                else:
                    data.update(num_people=None, label_status="unknown", capture_purpose="free_test")
            if not journal.data["completed"]:
                if name == "capture_runtime.json":
                    data.update(completed=False, aborted=True, abort_reason=journal.data["abort_reason"])
                else:
                    data.update(quality_status="failed", dataset_role="failure_history", use_for_final_training=False)
            save(path, data)
    structured_root = ROOT / "data/free_test/STRUCTURED" if free_test else ROOT / "data/structured"
    manifest = structured_root / config["session_id"] / "manifest.json"
    if manifest.exists() and (guidance or free_test or not journal.data["completed"]):
        data = json.loads(manifest.read_text())
        if guidance:
            data["activity_guidance"] = {
                "segments_file": str((session / "activity_segments.json").relative_to(ROOT)),
                "events_file": str((session / "session_control.json").relative_to(ROOT)),
                "label_status": "unlabeled_free_test" if free_test else "planned_instructions_not_verified_actions"}
        if free_test:
            data.setdefault("label", {}).update(num_people=None, label_status="unknown", has_trainable_label=False)
            data.setdefault("quality", {})["final_training_allowed"] = False
        if not journal.data["completed"]:
            data.setdefault("quality", {}).update(final_training_allowed=False, status="failed")
            data["session_control_failed"] = True
        save(manifest, data)


def coordinate(channel, config, gate, journal, acquire, approve, summary=None):
    """Hardware-independent RX state machine, exercised with real localhost sockets."""
    ready = channel.expect("TX_READY", 600)
    require(ready["role"] == "TX" and ready["ping"].get("ok") is True, "TX 역할 또는 ping 검사 실패")
    gate.ready(config, ready["config"])
    journal.event("TX_READY", ping=ready["ping"])
    channel.send("READY_ACK")
    (summary or config_summary)(config)
    approve()
    gate.approve()
    journal.event("RX_APPROVED")
    sender_result = []

    def health():
        channel.check()
        msg = channel.receive(0)
        if msg:
            if msg["type"] == "START_ACK":
                return  # ACK to a retried START; sender creation remains idempotent.
            require(msg["type"] == "DONE", "수집 중 예상하지 않은 메시지: " + msg["type"])
            require(not sender_result, "중복 DONE 메시지")
            result = msg["body"]["result"]
            require(isinstance(result, dict) and result.get("exit_code") == 0 and
                    result.get("duration_sec") == config["sender_duration_sec"] and
                    result.get("rate") == 100 and result.get("size") == 512 and
                    type(result.get("sent")) is int and result["sent"] > 0 and
                    result.get("elapsed_sec", 0) >= config["sender_duration_sec"] - 0.1,
                    "TX sender 결과/시간/설정 검증 실패")
            sender_result.append(result)
            journal.event("SENDER_DONE", result=result)

    def on_ready():
        channel.check()
        gate.capture_ready()
        journal.event("CAPTURE_READY")
        gate.start()
        # TCP is reliable. Retry START only, with exactly-once sender creation on TX.
        for attempt in range(3):
            channel.send("START")
            journal.event("START", attempt=attempt + 1)
            try:
                channel.expect("START_ACK", 3)
                journal.event("START_ACK")
                return
            except Failure as exc:
                if str(exc) != "START_ACK 대기 시간 초과":
                    raise
        raise Failure("START_ACK를 받지 못했습니다.")

    require(acquire(on_ready, health) == 0, "CSI 수집 또는 후처리 실패")
    journal.event("CAPTURE_DONE")
    deadline = time.monotonic() + 30
    while not sender_result:
        require(time.monotonic() < deadline, "TX 완료 대기 시간 초과")
        health()
        time.sleep(0.1)
    channel.send("COMPLETE")
    channel.expect("COMPLETE_ACK", 15)
    journal.event("COMPLETE_ACK")


def run(args):
    session_id = "session_" + time.strftime("%Y%m%d_%H%M%S") + "_" + secrets.token_hex(4)
    journal = Journal("RX", session_id)
    channel = listener = connection = None
    config = None
    collection = None
    guide = None
    success, reason = False, "수집 준비 중 취소"
    try:
        room = ask("[0] 수집 강의실 ID (예: G304 / G308, 직접 입력)", collection_id)
        print("  1: 기존 고정 인원 학습 수집")
        print("  2: 자유 테스트 — 0~4명 자유 활동·입퇴실, CSI+영상, 기본 40분")
        mode = ask("[0-1] 수집 종류", capture_mode, "1")
        free_test = mode == "free_test"
        # Old TX validates a nonnegative integer here. In free_test this is only
        # the protocol-compatible upper bound; it is NEVER the acquisition label.
        count = 4 if free_test else ask("[1] 수집 인원 수 (0: 빈 방)", people)
        collection = collection_settings(room, count, session_id, free_test=free_test)
        journal.data["collection_context"] = collection
        if free_test:
            journal.data["wire_num_people_meaning"] = "planned_upper_bound_not_actual_count; RX data labels are unknown"
        journal.event("COLLECTION_SELECTED", **collection)
        collection_summary(collection)
        network = wifi(args.interface)
        profile = hotspot(network)
        segments = capture_schedule(collection["activity"])
        duration = segments[-1]["end_sec"]
        camera = camera_policy(required=True) if free_test else camera_policy()
        guidance = guidance_settings(count, segments)
        config = {"num_people": count, "duration_sec": duration, "sender_duration_sec": duration + 10,
                  "profile": profile, "camera": camera, "rate": 100, "size": 512,
                  "data_port": 5005, "session_id": session_id}
        validate_config(config)
        journal.data["activity_guidance"] = guidance
        journal.event("GUIDE_CONFIGURED", settings=guidance)
        guide = (FreeTestGuide if free_test else ActivityGuide)(config, collection, guidance, journal.event)
        state = preflight(config, network, collection)
        journal.event("PREFLIGHT", config=config, rx=network, checks=state)
        listener = open_control_listener(network["ip"], args.control_port)
        pin, nonce = "{:06d}".format(secrets.randbelow(1000000)), secrets.token_hex(32)
        print("[5][대기] LISTENING: RX {} / TCP {} / 일회용 PIN {}".format(network["ip"], args.control_port, pin))
        print("TX 실행기에서 이 현재 IP와 PIN을 입력하세요. Q 또는 Ctrl+C로 취소할 수 있습니다.")
        deadline = time.monotonic() + 600
        while True:
            require(time.monotonic() < deadline, "TX 접속 대기 10분 초과")
            if select_input_cancel():
                raise KeyboardInterrupt()
            try:
                connection, peer = listener.accept()
                break
            except socket.timeout:
                continue
        wire = Wire(connection)
        hello = wire.receive(15)
        require(hello["type"] == "HELLO" and hello["body"]["role"] == "TX", "TX HELLO가 필요합니다.")
        body = hello["body"]
        require(isinstance(body["pin"], str) and secrets.compare_digest(body["pin"], pin), "일회용 PIN이 다릅니다. 새 세션으로 재시도하세요.")
        require(body["profile"]["ssid"] == profile["ssid"], "RX/TX 핫스팟 선택이 다릅니다.")
        check_pair(network, body["network"], profile, peer[0])
        # Re-read to reject a hotspot/DHCP change during the wizard.
        require(wifi(network["interface"]) == network, "RX 네트워크가 준비 중 변경되었습니다. 다시 실행하세요.")
        wire.send(packet("CONFIG", session_id, nonce, role="RX", network=network, config=config))
        channel = Channel(wire, session_id, nonce)
        journal.event("HANDSHAKE", tx=body["network"], peer_ip=peer[0])
        def approve():
            collection_summary(collection)
            if free_test:
                print("[촬영 안내] 출입문과 방 안 인원이 보이도록 카메라를 고정하세요. 자리·행동 순서는 자유입니다.")
                print("[촬영 안내] 방 안 조작자도 실제 인원에 포함됩니다. 종료 전까지 카메라·AP·RX 배치를 유지하세요.")
            else:
                print("[행동 안내] 참가자/자리: " + (" / ".join("{}:{}".format(p["person"], p["position"])
                      for p in guidance["participants"]) or "전원 퇴실"))
            print("[행동 안내] 장비 준비 후 {}초 자리 준비 + {}초 안정화, 첫 패킷부터 {}분 수집".format(
                guidance["prepare_sec"], guidance["settle_sec"], duration / 60))
            for segment in segments:
                print("  {}회차 {}: {:.2f}~{:.2f}분".format(segment["repeat"],
                    ACTIVITY_NAMES[segment["activity"]], segment["start_sec"] / 60, segment["end_sec"] / 60))
            confirm('[6] 강의실·배치·촬영 범위를 확인했습니다. 자유 테스트를 시작하려면 Y' if free_test else
                    '[6] 강의실·배치·인원·행동을 확인했습니다. 수집을 시작하려면 Y', channel.check)
            require(wifi(network["interface"]) == network, "RX 네트워크가 변경되었습니다.")
        def acquire(ready, health):
            result = capture.capture(capture_args(config, network, peer[0], nonce, collection),
                                     ready, health, prepare_callback=guide.prepare,
                                     progress_callback=guide.progress)
            if result == 0:
                guide.progress("confirming")
            return result
        coordinate(channel, config, Gate(), journal,
                   acquire, approve,
                   summary=(lambda settings: print("[통과] 자유 테스트 {}분 / 실제 인원 미확정 / CSI+영상".format(
                       settings["duration_sec"] / 60))) if free_test else None)
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
        try:
            if channel:
                channel.close()
            elif connection:
                connection.close()
            if listener:
                listener.close()
            if guide:
                journal.event("GUIDE_RESULT", completed=success, reason=reason)
            journal.finish(success, reason)
            if config:
                attach_control(config, journal, collection)
        finally:
            if guide:
                guide.close()
        if guide:
            guide.result(success, reason)
        print("제어 기록: " + str(journal.path))


def select_input_cancel():
    import select
    if select.select([sys.stdin], [], [], 0)[0]:
        value = sys.stdin.readline()
        return not value or value.strip().upper() == "Q"
    return False


if __name__ == "__main__":
    result = entry(run, "RX")
    if sys.stdin.isatty():
        try:
            input("결과 확인 후 Enter를 누르면 RX 창을 닫습니다. ")
        except (KeyboardInterrupt, EOFError):
            pass
    sys.exit(result)
