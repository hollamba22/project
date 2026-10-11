# CSI 데이터 성공/실패 구분 기준

이 문서는 raw CSI 수집 세션을 전처리나 모델 학습에 사용하기 전에 어떻게 분류할지 정의한다.

## 목적

`data/raw/session_*/csi.dat`에는 실패한 수집 파일, 환경 검증용 수집 파일, 그리고 앞으로 만들 학습용 수집 파일이 섞일 수 있다. 따라서 이 파일들을 무작정 함께 사용하면 안 된다.

가장 중요한 원칙은 다음과 같다.

```text
최종 모델 학습/평가에는 안테나 거치대 완성 후, 고정된 실험 조건에서 수집되고 라벨까지 명확한 유효 CSI 세션만 사용한다.
```

## 데이터 분류

### 1. 실패한 수집

다음 중 하나라도 해당하면 실패한 세션으로 분류한다.

- `csi.dat`가 없다.
- `csi.dat`가 `0 bytes`이다.
- `parse_log`로 파일을 읽을 수 없다.
- 파일 안에 `code=0xBB` CSI 레코드가 없다.
- `connector_log`가 없거나 비활성화된 상태에서 로깅을 시작했다.
- 수신 PC가 CSI 호환 커널로 부팅되지 않았다.
- 수집 전 TX -> RX ping이 실패했다.
- 유의미한 데이터가 쓰이기 전에 수집이 중단되었다.

실패한 세션은 전처리, 시각화 통계, 모델 학습에 사용하지 않는다.

현재 실패한 수집 파일은 다음과 같다.

```text
data/raw/session_20260615_203420/csi.dat 0 bytes
data/raw/session_20260615_203722/csi.dat 0 bytes
data/raw/session_20260615_205335/csi.dat 0 bytes
data/raw/session_20260703_151554/csi.dat 0 bytes
data/raw/session_20260703_151951/csi.dat 0 bytes
data/raw/session_20260703_172027/csi.dat 0 bytes
```

권장 상태 표기는 다음과 같다.

```text
quality_status: failed
use_for_training: false
use_for_visualization: false
keep_reason: failure history / report evidence
```

### 2. 유효 CSI, 검증 전용

다음 조건을 만족하면 유효 CSI이지만 검증 전용 세션으로 분류한다.

- `csi.dat`가 비어 있지 않다.
- `parse_log`가 CSI 레코드를 읽을 수 있다.
- 레코드가 `code=0xBB`로 표시된다.
- 최종 안테나 거치대나 최종 실험 배치가 고정되기 전에 수집되었다.

이런 파일은 CSI 수집이 가능하다는 것을 증명한다. 또한 파서 개발과 시각화 개발에는 유용하다. 하지만 나중에 안테나 거치대나 물리적 배치가 바뀌면 최종 학습 데이터셋에는 섞지 않는다.

현재 검증 전용 성공 파일은 다음과 같다.

```text
data/raw/session_20260710_145820/csi.dat 1843190 bytes, 4690 CSI records
data/raw/session_20260710_153743/csi.dat 1941820 bytes, 4916 CSI records
```

권장 상태 표기는 다음과 같다.

```text
quality_status: valid_csi
dataset_role: verification_only
use_for_parser_development: true
use_for_visualization_development: true
use_for_final_training: false
reason: collected before final 3D-printed antenna holder
```

### 3. 학습 후보 데이터

앞으로 수집할 세션이 다음 조건을 모두 만족하면 학습 후보 데이터로 분류한다.

- 안테나 거치대가 완성되었고 실제로 사용되었다.
- TX/RX/핫스팟 위치가 고정되어 있고 문서화되어 있다.
- 안테나 방향이 고정되어 있고 문서화되어 있다.
- 세션 중 방 배치가 유지되었다.
- 사람 수 라벨이 명확하고 전체 수집 구간 동안 변하지 않았다.
- `csi.dat`가 비어 있지 않다.
- `parse_log`로 `code=0xBB` CSI 레코드가 확인된다.
- 세션 길이가 계획한 길이와 일치한다. 기본값은 60초다.
- 수집 전 TX -> RX ping이 성공했다.
- 수신 PC가 `4.15.0-213-generic` 커널로 부팅되어 있다.
- 수신 PC의 `connector_log`가 `1`이다.
- 수신 PC가 수집 중 MCS rate 트래픽을 받고 있다.
- `meta.json`이 존재하고 필요한 정보가 채워져 있다.

권장 상태 표기는 다음과 같다.

```text
quality_status: valid_csi
dataset_role: training_candidate
use_for_final_training: true
```

### 4. 검토 필요 데이터

CSI 레코드는 있지만 라벨이나 실험 조건이 불명확하면 검토 필요 세션으로 분류한다.

예시는 다음과 같다.

- 60초 수집 중 사람이 들어오거나 나갔다.
- 수집 중 TX/RX/핫스팟이 움직였다.
- 안테나 방향이 바뀌었다.
- 문이 열리거나 닫혀서 환경이 바뀌었다.
- 세션 라벨을 모른다.
- `csi.dat`가 예상보다 너무 작다.
- 송신 rate에 비해 레코드 수가 너무 적다.
- AP나 channel이 예상과 다르게 바뀌었다.

권장 상태 표기는 다음과 같다.

```text
quality_status: needs_review
use_for_final_training: false
review_reason: <구체적인 이유>
```

## 최소 검증 명령

0 byte 실패 파일 목록 확인:

```bash
find data/raw -name csi.dat -size 0 -print
```

비어 있지 않은 파일 목록 확인:

```bash
find data/raw -name csi.dat ! -size 0 -print
```

파일 크기 확인:

```bash
ls -lh data/raw/session_*/csi.dat
```

CSI 레코드 확인:

```bash
third_party/linux-80211n-csitool-supplementary-master/netlink/parse_log data/raw/<session_id>/csi.dat | head -10
```

정상 출력 예시는 다음과 같다.

```text
Entry size=393, code=0xBB
Entry size=393, code=0xBB
...
```

CSI 레코드 수 확인:

```bash
third_party/linux-80211n-csitool-supplementary-master/netlink/parse_log data/raw/<session_id>/csi.dat | wc -l
```

## 권장 metadata 항목

앞으로 각 세션에는 최소한 다음 필드를 포함한 `meta.json` 파일을 둔다.

```json
{
  "session_id": "session_YYYYMMDD_HHMMSS",
  "quality_status": "valid_csi",
  "dataset_role": "training_candidate",
  "use_for_final_training": true,
  "num_people": 2,
  "label_status": "stable_full_session",
  "duration_sec": 60,
  "room": "room_name",
  "room_has_wifi_rack": true,
  "environment_note": "high_wifi_interference",
  "tx_position": "opposite_short_wall_left_or_marked_position",
  "rx_position": "opposite_short_wall_right_or_marked_position",
  "hotspot_position": "fixed_marked_position",
  "antenna_holder": "3d_printed_v1",
  "antenna_direction_fixed": true,
  "ap_ssid": "Minhyuck S24+",
  "ap_channel": 6,
  "ap_frequency_mhz": 2437,
  "rx_kernel": "4.15.0-213-generic",
  "rx_connector_log": 1,
  "rx_ip": "10.27.219.22",
  "sender_command": "python3 scripts/sender/safe_sender.py --target 10.27.219.22 --mode udp --duration 60 --rate 100 --size 512",
  "csi_file": "csi.dat",
  "csi_file_bytes": null,
  "csi_record_count": null,
  "notes": ""
}
```

## 현재 데이터 요약

실패한 파일은 아직 삭제하지 않는다. 프로젝트 진행 기록과 보고서 근거로 사용할 수 있기 때문이다.

현재 데이터는 다음처럼 해석한다.

| 세션 | 상태 | 데이터셋 역할 | 최종 학습 사용 여부 |
| --- | --- | --- | --- |
| `session_20260615_203420` | 실패 | 실패 기록 | 아니오 |
| `session_20260615_203722` | 실패 | 실패 기록 | 아니오 |
| `session_20260615_205335` | 실패 | 실패 기록 | 아니오 |
| `session_20260703_151554` | 실패 | 실패 기록 | 아니오 |
| `session_20260703_151951` | 실패 | 실패 기록 | 아니오 |
| `session_20260703_172027` | 실패 | 실패 기록 | 아니오 |
| `session_20260710_145820` | 유효 CSI | 검증 전용 | 아니오 |
| `session_20260710_153743` | 유효 CSI | 검증 전용 | 아니오 |

최종 모델용 데이터셋 수집은 안테나 거치대가 완성된 뒤 시작한다.
