"""Metadata and empty annotation forms for variable-occupancy test recordings."""
import csv
import json
import os
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
PEOPLE_RANGE = [0, 4]


def write_json(path, value):
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")


def write_artifacts(session_dir, runtime, csi_file, video_file):
    """Preserve unknown labels, including partial/failed runs; never invent truth."""
    annotation_dir = os.path.join(session_dir, "annotations")
    os.makedirs(annotation_dir, exist_ok=True)
    csv_path = os.path.join(annotation_dir, "ground_truth_intervals.csv")
    if not os.path.exists(csv_path):
        with open(csv_path, "w", encoding="utf-8", newline="") as stream:
            csv.writer(stream).writerow([
                "video_start_sec", "video_end_sec", "num_people", "verified", "notes"
            ])
    readme = os.path.join(annotation_dir, "README.md")
    if not os.path.exists(readme):
        with open(readme, "w", encoding="utf-8") as stream:
            stream.write("""# 자유 테스트 실제 인원 정답 작성

이 CSV는 헤더만 있는 빈 서식입니다. 현재 인원, 입퇴실 순서, 시작 인원을 가정하지 않습니다.
영상 검수 후 인원수가 일정한 실제 구간을 한 행씩 입력하세요.

- `video_start_sec`, `video_end_sec`: 저장 영상의 처음을 0초로 한 재생 시각(초).
- 구간은 [시작, 끝)입니다. 실제 문턱 통과를 기준으로 인원이 바뀔 때마다 행을 나누세요.
- `num_people`: 영상으로 확인한 실제 인원. 계획 범위는 0~4명이지만 초과가 발생해도 실제 값을 기록하세요.
- `verified`: 검수한 구간에만 true. 가림 등으로 확인할 수 없으면 인원을 비워 두고 notes에 사유를 쓰세요.
- 조작자나 관찰자가 방 안에 있으면 그 사람도 포함합니다. P/Z 자리 번호는 필요하지 않습니다.

영상은 준비 시간부터 녹화되므로 영상 0초와 CSI/수집 타이머 0초는 다릅니다.
영상 왼쪽 위의 RX PC 시각과 ../time_alignment.json, ../capture_runtime.json을 함께 확인하세요.
time_alignment.json의 estimated 값은 프로세스 시작 시각으로 계산한 추정치이며 프레임 동기 검증값이 아닙니다.
CSI 특징은 첫 CSI 레코드를 0초로 사용합니다. 첫 UDP 패킷이나 logger 시작 시각과 같다고 가정하지 마세요.
CSI 예측 그래프와 겹치기 전에 실제 영상-CSI 오프셋과 오차를 확인해 별도 기록해야 합니다.
영상에 표시한 시각은 초 단위이며 정밀한 입퇴실 시각은 영상 프레임으로 구분하세요.

이 세션은 평가용이며 자동 학습에 포함하지 않습니다. 정답 CSV와 영상은 추론 입력이 아닙니다.
실패/중단 여부를 ../session_control.json과 ../capture_runtime.json에서 확인하세요.
""")

    udp = runtime.get("udp", {})
    camera = runtime.get("camera", {})
    timed = runtime.get("timed_capture", {})
    anchor = timed.get("first_packet_wall_epoch", udp.get("first_packet_wall_epoch"))
    video_start = camera.get("started_wall_epoch")
    alignment = {
        "schema_version": "1.0-free-test-timing",
        "session_id": runtime["session_id"],
        "verification_status": "unverified",
        "timezone": "Asia/Seoul",
        "timer_origin": "first_valid_session_udp_packet",
        "timer_zero_wall_epoch": anchor,
        "timer_zero_monotonic_sec": udp.get("first_packet_monotonic_sec"),
        "camera_process_started_wall_epoch": video_start,
        "camera_process_started_monotonic_sec": camera.get("started_monotonic_sec"),
        "camera_process_stopped_wall_epoch": camera.get("stopped_wall_epoch"),
        "camera_wall_clock_overlay": camera.get("wall_clock_overlay", False),
        "logger_started_wall_epoch": runtime.get("logger_started_wall_epoch"),
        "logger_stopped_wall_epoch": runtime.get("logger_stopped_wall_epoch"),
        "csi_timestamp_summary": runtime.get("csi_validation", {}).get("timestamp", {}),
        "estimated_timer_zero_video_sec": anchor - video_start if anchor is not None and video_start is not None else None,
        "verified_csi_zero_video_sec": None,
        "verified_alignment_error_sec": None,
        "note": "Process start and first UDP are not first video/CSI frames. Verify the offset before joining video annotations to CSI windows. Clock overlay is RX local wall time at video processing, in whole seconds.",
    }
    write_json(os.path.join(session_dir, "time_alignment.json"), alignment)

    meta_path = os.path.join(session_dir, "meta.json")
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as stream:
            meta = json.load(stream)
    else:
        meta = {"schema_version": "1.0", "session_id": runtime["session_id"],
                "quality_status": "needs_review"}
    failed = bool(runtime.get("aborted") or runtime.get("postprocess_error"))
    meta.update(dataset_role="failure_history" if failed else "test_candidate", use_for_final_training=False)
    if failed:
        meta["quality_status"] = "failed"
    meta.setdefault("label", {}).update(num_people=None, label_status="unknown", activity="free_test")
    meta.setdefault("environment", {}).update({key: runtime.get(key) for key in
        ("room", "setup_id", "empty_reference_session_id")})
    capture = meta.setdefault("capture", {})
    capture.update(csi_file=csi_file, video_file=video_file,
                   csi_file_bytes=runtime.get("csi_file_bytes", 0),
                   csi_record_count=runtime.get("csi_validation", {}).get("record_count"),
                   planned_duration_sec=runtime["planned_duration_sec"],
                   time_reference="first_valid_session_udp_packet",
                   start_time_local=(datetime.fromtimestamp(anchor, KST).strftime("%Y-%m-%d %H:%M:%S")
                                     if anchor is not None else None),
                   end_time_local=None)
    # The end of the requested timer is distinct from logger/camera shutdown.
    if runtime.get("completed") and anchor is not None:
        capture["end_time_local"] = datetime.fromtimestamp(
            anchor + runtime["planned_duration_sec"], KST).strftime("%Y-%m-%d %H:%M:%S")
    meta["free_test"] = {"planned_people_range": PEOPLE_RANGE, "actual_people": "unknown_until_video_review",
                         "ground_truth_file": "annotations/ground_truth_intervals.csv",
                         "ground_truth_time_reference": "video_playback_seconds",
                         "time_alignment_file": "time_alignment.json",
                         "ground_truth_status": "pending_video_review",
                         "schedule": "none; voluntary movements and entries/exits"}
    write_json(meta_path, meta)
