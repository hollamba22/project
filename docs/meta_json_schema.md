# 세션 meta.json 작성 기준

이 문서는 각 CSI 수집 세션 폴더에 저장할 `meta.json` 파일의 작성 기준을 정의한다.

템플릿 파일:

```text
templates/session_meta_template.json
```

각 수집 세션은 다음 구조를 따른다.

```text
data/raw/session_YYYYMMDD_HHMMSS/
  csi.dat
  meta.json
  video.mp4        # 선택 사항
```

## 목적

`csi.dat` 파일 자체에는 사람 수, 실험 위치, 핫스팟 정보, 수신 PC 상태 같은 정보가 들어 있지 않다.

따라서 각 세션마다 `meta.json`을 반드시 남겨야 나중에 다음 작업이 가능하다.

- 사람 수 라벨 확인
- 실패/성공 데이터 구분
- 같은 조건의 데이터만 학습에 사용
- train/test split 시 세션 단위 관리
- 보고서에 실험 조건 정리

## 최상위 필드

### `schema_version`

metadata 형식 버전이다.

현재는 다음 값을 사용한다.

```json
"schema_version": "1.0"
```

### `session_id`

세션 폴더 이름과 같아야 한다.

예시:

```json
"session_id": "session_20260710_153743"
```

### `created_at`

metadata 파일을 작성한 시간이다. 한국 시간 기준 ISO 형식을 사용한다.

예시:

```json
"created_at": "2026-07-10T15:37:43+09:00"
```

### `quality_status`

CSI 데이터 품질 상태를 나타낸다.

허용 값:

```text
failed
valid_csi
needs_review
```

기준:

- `failed`: 0 byte, parser 실패, CSI 레코드 없음
- `valid_csi`: `code=0xBB` CSI 레코드 확인
- `needs_review`: CSI는 있지만 라벨이나 실험 조건이 애매함

### `dataset_role`

데이터셋 안에서의 역할이다.

허용 값:

```text
failure_history
verification_only
training_candidate
test_candidate
excluded
```

현재 성공 파일처럼 거치대 완성 전 수집한 파일은 다음으로 둔다.

```json
"dataset_role": "verification_only"
```

거치대 완성 후 본격 수집한 파일은 다음으로 둔다.

```json
"dataset_role": "training_candidate"
```

### `use_for_final_training`

최종 모델 학습에 사용할지 여부다.

거치대 완성 전 검증용 데이터:

```json
"use_for_final_training": false
```

거치대 완성 후 고정 조건에서 수집한 학습 후보 데이터:

```json
"use_for_final_training": true
```

## `label`

사람 수 라벨과 활동 상태를 기록한다.

예시:

```json
"label": {
  "num_people": 2,
  "label_status": "stable_full_session",
  "activity": "standing",
  "people_description": "two people standing between TX and RX",
  "notes": ""
}
```

### `num_people`

방 안 사람 수다.

초기 프로젝트에서는 다음 class를 사용한다.

```text
0, 1, 2, 3
```

중요: `csi.dat`에는 이 값이 들어 있지 않다. 실험자가 직접 기록해야 한다.

### `label_status`

라벨이 얼마나 믿을 수 있는지 나타낸다.

권장 값:

```text
stable_full_session
changed_during_session
unknown
```

최종 학습에는 `stable_full_session`만 사용하는 것을 원칙으로 한다.

### `activity`

사람의 상태를 간단히 기록한다.

예시:

```text
empty
standing
sitting
walking
natural
mixed
```

처음에는 복잡하게 나누지 말고 `standing`, `sitting`, `natural` 정도만 사용한다.

## `capture`

수집 시간과 파일 정보를 기록한다.

주요 필드:

- `duration_sec`: 실제 수집 시간
- `planned_duration_sec`: 계획한 수집 시간
- `csi_file`: 보통 `csi.dat`
- `csi_file_bytes`: 수집 후 파일 크기
- `csi_record_count`: `parse_log | wc -l` 결과
- `video_file`: 비디오를 찍었다면 파일명, 없으면 `null`

예시:

```json
"capture": {
  "duration_sec": 60,
  "planned_duration_sec": 60,
  "csi_file": "csi.dat",
  "csi_file_bytes": 1941820,
  "csi_record_count": 4916,
  "video_file": null
}
```

## `environment`

2026-09-17부터 강의실은 `room`에 실제 ID(예: `G304`, `G308`)로 기록한다.
`setup_id`는 그 강의실의 AP/RX·안테나·가구 배치 ID이며, 과거 미확인 배치는 `unknown` 또는 미기재다.
`empty_reference_session_id`는 같은 강의실·배치의 0명 기준 세션 ID다.
0명 수집은 자신의 ID, 미연결 수집은 `null`이며, 참조가 있어도 실제 완료 여부와 품질은 별도 확인한다.
이 값들은 정형화 manifest로 전달되고 `session_id`로 수치 특징 CSV와 연결한다.
과거 위치 보완의 `room_annotation`에는 확인 근거와 이전 room 값이 기록된다.

RX 실시간 안내를 사용한 세션은 `activity_guidance`에 안내 설정과 파일 참조를 저장한다.
자동 진행 세션의 `label.activity`는 `mixed`이며, `activity_segments.json`에서 각 동작의
예정 구간을 확인한다. 실제 안내 시각은 `session_control.json`의 `GUIDE_CUE` 이벤트다.
기준 시각은 `GUIDE_TIME_ANCHOR.first_packet_wall_epoch`와 runtime의
`timed_capture.first_packet_wall_epoch`다. 예정 지시는 영상으로 확인한 실제 행동 정답과 구분한다.

방과 주변 WiFi 환경을 기록한다.

현재처럼 WiFi 랙 장비가 있고 주변 AP가 많은 경우:

```json
"environment": {
  "room": "school_lounge_or_lab_room",
  "room_shape": "rectangle",
  "room_has_wifi_rack": true,
  "nearby_aps": "many",
  "environment_note": "high_wifi_interference",
  "door_state": "closed",
  "large_objects_moved": false,
  "notes": ""
}
```

이 정보는 나중에 보고서의 한계 분석에 중요하다.

## `layout`

TX/RX/핫스팟/안테나 위치를 기록한다.

중요한 원칙:

- TX 위치 고정
- RX 위치 고정
- 핫스팟 휴대폰 위치 고정
- 안테나 방향 고정
- 거치대 버전 기록

예시:

```json
"layout": {
  "tx_position": "short_wall_A_center",
  "rx_position": "short_wall_B_center",
  "hotspot_position": "side_table_center_mark",
  "tx_rx_distance_m": 4.2,
  "tx_height_m": 0.9,
  "rx_height_m": 0.9,
  "hotspot_height_m": 0.8,
  "antenna_holder": "3d_printed_v1",
  "antenna_direction_fixed": true,
  "antenna_notes": "all antennas mounted vertically"
}
```

정확한 거리를 모르면 `null`로 두고, 대신 위치 표시를 명확히 적는다.

## `receiver`

수신 PC 상태를 기록한다.

예시:

```json
"receiver": {
  "hostname": "RXPC",
  "role": "receiver",
  "interface": "wlp4s0",
  "mac": "00:16:ea:ed:a9:80",
  "ip": "10.27.219.22",
  "kernel": "4.15.0-213-generic",
  "driver": "patched_iwlwifi",
  "connector_log": 1,
  "rx_bitrate_observed": "144.4 MBit/s MCS 15 short GI",
  "signal_dbm": -42
}
```

필수 확인:

```bash
uname -r
cat /sys/module/iwlwifi/parameters/connector_log
iw dev wlp4s0 link
ip -4 addr show wlp4s0
iw dev wlp4s0 station dump
```

## `sender`

송신 PC 상태와 송신 명령을 기록한다.

예시:

```json
"sender": {
  "hostname": "hollamba-TX",
  "role": "sender",
  "interface": "wlp4s0",
  "mac": "00:21:6a:6d:30:40",
  "ip": "10.27.219.xxx",
  "kernel": "5.4.0-84-generic",
  "ping_to_receiver_before_capture": "pass",
  "sender_command": "python3 scripts/sender/safe_sender.py --target 10.27.219.22 --mode udp --duration 60 --rate 100 --size 512"
}
```

송신 PC는 CSI 드라이버가 필수는 아니다. 수신 PC로 안정적으로 패킷을 보내는 것이 핵심이다.

## `network`

AP/핫스팟 정보를 기록한다.

예시:

```json
"network": {
  "ap_type": "phone_hotspot",
  "ap_ssid": "Minhyuck S24+",
  "ap_bssid": "92:91:d6:68:b5:14",
  "ap_channel": 6,
  "ap_frequency_mhz": 2437,
  "ap_band": "2.4GHz",
  "ap_security": "open",
  "network_cidr": "10.27.219.0/24"
}
```

확인 명령:

```bash
iw dev wlp4s0 link
nmcli device wifi list
ip route
```

## `validation`

수집 후 검증 결과를 기록한다.

예시:

```json
"validation": {
  "file_size_checked": true,
  "parse_log_checked": true,
  "parse_log_code": "0xBB",
  "record_count_checked": true,
  "valid_csi": true,
  "review_reason": ""
}
```

검증 명령:

```bash
ls -lh data/raw/session_YYYYMMDD_HHMMSS/csi.dat
third_party/linux-80211n-csitool-supplementary-master/netlink/parse_log data/raw/session_YYYYMMDD_HHMMSS/csi.dat | head -10
third_party/linux-80211n-csitool-supplementary-master/netlink/parse_log data/raw/session_YYYYMMDD_HHMMSS/csi.dat | wc -l
```

## 작성 규칙

본격 데이터셋 수집 시 다음 규칙을 따른다.

1. `csi.dat`만 저장하지 말고 반드시 `meta.json`을 같이 저장한다.
2. 세션이 끝난 직후 파일 크기와 레코드 수를 기록한다.
3. 사람 수가 세션 중 바뀌면 `training_candidate`로 두지 않는다.
4. TX/RX/핫스팟/안테나 위치가 바뀌면 다른 실험 조건으로 취급한다.
5. 거치대 버전이 바뀌면 이전 데이터와 섞지 않는다.
6. 최종 학습에는 `use_for_final_training=true`인 세션만 사용한다.

## 바탕화면 동기화 실행기의 추가 필드 (하위 호환)

`meta.json`과 `capture_runtime.json`은 선택 필드 `session_control`을 가질 수 있다.
`file`은 같은 세션 폴더의 `session_control.json`, `completed`는 RX/TX 최종 완료 확인,
`abort_reason`은 실패 이유다. 기존 필드/스키마 버전은 유지한다.
동기화 제어 실패 세션은 `quality_status=failed`, `dataset_role=failure_history`,
`use_for_final_training=false`로 기록한다. runtime의 completed도 false가 된다.

제어 로그에는 실제 SSID/BSSID·주파수/채널·IP/MAC, 프로필 검증 여부,
카메라 사용/미리보기/영상 부재 정책, 요청 인원·계획 시간, handshake·승인·START 시각,
ping·사전 검사, sender 결과와 최종 상태가 있다. PIN과 nonce는 저장하지 않는다.
`capture.duration_sec`/`planned_duration_sec`는 기존 정수 외에 소수 초도 허용한다.
실행기는 0 이상의 정수 인원 N을 `data/<N>_people`로 저장하며 4명 이상도 지원한다.
0명은 빈 방 라벨로 `data/0_people`에 저장하고 `label.activity=empty`를 기록한다.
숫자 0은 미입력 값이 아니며, 1명 이상은 기존 `label.activity=natural`을 유지한다.
자세한 프로토콜과 운영 절차는 `csi_desktop_capture_launchers.md`를 참조한다.
