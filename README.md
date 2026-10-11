# WiFi CSI 기반 실내 인원 수 추정 프로젝트

이 프로젝트는 Intel 5300 CSI Tool로 수집한 WiFi CSI 데이터를 이용해 실내 사람 수를 추정하는 졸업 프로젝트다.

최종 목표는 카메라 없이 CSI만으로 `0명`, `1명`, `2명`, `3명` class를 분류하는 것이다. 비디오는 최종 추론 입력이 아니라 학습 라벨 확인용으로만 사용한다.

**2026-09-17 수집 갱신:** 지금까지의 데이터는 **G308 강의실**이다. 오늘은 **G304에서
0→1→2→3→4명**을 수집하며, RX 실행기에서 강의실·배치·행동·0명 기준 세션을 확인한다.
확장 목표는 새 강의실의 0명 기준만으로 환경을 보정해 인원수를 추정하는 것으로,
현재는 이를 검증할 데이터와 라벨을 준비하는 단계다.
[오늘 수집 절차와 기존 데이터 표기 이력](docs/csi_collection_G304_20260917.md)을 따른다.
RX CMD가 준비·안정화와 실시간 행동을 안내한다. 1명 이상 기본 수집은 **앉기 5분 → 서기 5분 →
교대 걷기 5분을 2회 반복하는 인원별 30분**이며, 반복 횟수를 변경할 수 있다.
한 파일 동안 인원수는 고정하고 행동 구간과 안내 시각을 별도로 기록한다.

**2026-09-29 자유 테스트 추가:** RX의 수집 종류 `2`를 선택하면 **0~4명 자유 활동·입퇴실을
기본 40분 동안 CSI와 영상으로 기록**한다. 인원·자리·행동 순서를 지정하지 않고 실제 인원 라벨은
영상 검수 전까지 미확정으로 둔다. 자료는 `data/free_test`에 저장하며 자동 학습에서 제외한다.
[실행 방법과 정답 작성 서식](docs/csi_free_test_capture.md)을 참고한다.

## 현재 상태

현재까지 완료된 작업:

- 수신 PC에서 CSI 수집 가능한 커널/드라이버 확인
- 핫스팟/AP 기반 TX -> RX 통신 성공
- `csi.dat` 비어 있지 않은 파일 반복 생성 성공
- CSI 레코드 `code=0xBB` 확인
- 성공/실패 데이터 분류 기준 문서화
- `meta.json` 템플릿 작성
- CSI 파싱/시각화 코드 작성
- 기존 성공 세션 2개에 `meta.json` 추가
- 전체 raw session 인덱스 생성

현재 성공 파일:

```text
data/raw/session_20260710_145820/csi.dat  1.8 MB, 4690 CSI records
data/raw/session_20260710_153743/csi.dat  1.9 MB, 4916 CSI records
```

이 두 파일은 3D 프린터 안테나 거치대 완성 전 데이터이므로 최종 학습용이 아니라 검증/파서/시각화 개발용이다.

## 성공 조건 요약 (2026-07-10 기록)

수신 PC:

```text
kernel: 4.15.0-213-generic
driver: patched iwlwifi
connector_log: 1
interface: wlp4s0
RX IP: 10.27.219.22
```

네트워크:

```text
AP/hotspot: Minhyuck S24+
channel: 6
frequency: 2437 MHz
band: 2.4 GHz
```

송신 명령:

```bash
python3 scripts/sender/safe_sender.py --target 10.27.219.22 --mode udp --duration 60 --rate 100 --size 512
```

`10.27.219.22`는 당시 DHCP 주소다. 다음 실험에서는 이 값을 재사용하지 말고 `ip -4 addr show wlp4s0`으로 확인한 현재 RX 주소를 사용한다.

## 실험 재개 전 기준 점검

2026-08-14에 S24+ 핫스팟으로 복구한 네트워크 기준과 다음 실험 전 비교 절차는 아래 문서에 기록되어 있다.

```text
docs/s24_capture_baseline_20260814.md
docs/s24_capture_baseline_20260814.json
```

수신 PC에서 자동 점검:

```bash
python3 scripts/capture/check_baseline.py
python3 scripts/capture/check_baseline.py --sender-ip <현재_TX_IP>
```

핫스팟 재시작 후 BSSID와 IP 대역은 바뀔 수 있으므로 과거 주소를 강제로 사용하지 않는다. 필수 상태와 통신 검사를 모두 통과한 뒤 CSI 로깅을 시작한다.

## 주요 문서

```text
docs/csi_capture_success_conditions_20260710.md
docs/csi_capture_success_conditions_20260710.pdf
docs/data_success_failure_criteria.md
docs/data_success_failure_criteria.pdf
docs/meta_json_schema.md
docs/csi_parsing_visualization.md
docs/training_pipeline_skeleton.md
```

## 주요 코드

CSI 파싱/시각화:

```text
scripts/csi/csi_parser.py
scripts/csi/visualize_csi.py
```

데이터셋 관리:

```text
scripts/dataset/create_meta.py
scripts/dataset/validate_sessions.py
```

전처리/학습/평가:

```text
scripts/preprocess/make_windows.py
scripts/preprocess/extract_features.py
scripts/train/train_baseline.py
scripts/evaluate/evaluate_model.py
```

송신 트래픽 생성:

```text
scripts/sender/safe_sender.py
```

CSI 수집:

```text
scripts/capture/webcam_recorder.py
tools/start_csi_logging.sh
tools/verify_csitool.sh
tools/reload_csitool.sh
```

웹캠 연결, 단독 녹화 시험, CSI 동시 녹화 방법은 다음 문서에 정리되어 있다.

```text
docs/webcam_capture.md
```

## 세션 metadata

각 세션 폴더는 다음 구조를 목표로 한다.

```text
data/raw/session_YYYYMMDD_HHMMSS/
  csi.dat
  meta.json
  video.webm       # 선택 사항, 웹캠 라벨 검증용
```

템플릿:

```text
templates/session_meta_template.json
```

기존 성공 세션에는 이미 metadata가 추가되어 있다.

```text
data/raw/session_20260710_145820/meta.json
data/raw/session_20260710_153743/meta.json
```

## 새 세션 meta.json 생성

예시:

```bash
python3 scripts/dataset/create_meta.py data/raw/session_YYYYMMDD_HHMMSS \
  --dataset-role training_candidate \
  --quality-status valid_csi \
  --use-for-final-training true \
  --num-people 2 \
  --label-status stable_full_session \
  --activity natural \
  --room room_name \
  --antenna-holder 3d_printed_v1
```

거치대 완성 전 검증 데이터는 다음처럼 학습 제외로 둔다.

```bash
python3 scripts/dataset/create_meta.py data/raw/session_YYYYMMDD_HHMMSS \
  --dataset-role verification_only \
  --use-for-final-training false
```

## 전체 세션 검증/인덱스 생성

```bash
python3 scripts/dataset/validate_sessions.py
```

생성 파일:

```text
outputs/dataset/session_index.csv
outputs/dataset/session_index.json
```

현재 인덱스 기준:

```text
failed: 6 sessions
valid_csi: 2 sessions
verification_only: 2 sessions
use_for_final_training=true: 0 sessions
```

## CSI 시각화

새 CSI 파일을 시각화하려면:

```bash
python3 scripts/csi/visualize_csi.py data/raw/session_YYYYMMDD_HHMMSS/csi.dat
```

생성 파일:

```text
outputs/csi_visualizations/session_YYYYMMDD_HHMMSS/
  summary.json
  packet_amplitude_summary.csv
  amplitude_over_time.svg
  subcarrier_heatmap.svg
  antenna_pair_mean.svg
  index.html
```

현재 생성된 시각화:

```text
outputs/csi_visualizations/session_20260710_145820/
outputs/csi_visualizations/session_20260710_153743/
```

## 본격 데이터 수집 전 남은 일

아직 나중에 정할 항목:

- 실험 프로토콜
- 3D 프린터 안테나 거치대 설계 기준
- class별 세션 수
- 사람 위치/자세/활동 조건
- 비디오 라벨링 방식

거치대 완성 후 본격 수집이 시작되면 다음을 추가로 구현한다.

- scikit-learn 기반 RandomForest/SVM/LogisticRegression 학습
- confusion matrix 이미지 생성
- phase 보정 feature
- session/group 기반 cross validation

현재는 표준 라이브러리 기반 뼈대 코드가 구현되어 있다.

```bash
python3 scripts/dataset/validate_sessions.py
python3 scripts/preprocess/make_windows.py
python3 scripts/preprocess/extract_features.py
python3 scripts/train/train_baseline.py
python3 scripts/evaluate/evaluate_model.py
```

현재 검증용 데이터로 dry-run하려면:

```bash
python3 scripts/preprocess/make_windows.py --include-verification \
  --out-csv data/processed/windows_verification.csv \
  --out-json data/processed/windows_verification.json

python3 scripts/preprocess/extract_features.py \
  --windows-csv data/processed/windows_verification.csv \
  --out-csv data/processed/features_verification.csv

python3 scripts/train/train_baseline.py \
  --features-csv data/processed/features_verification.csv \
  --model-out outputs/models/baseline_verification_model.json \
  --split-out outputs/models/baseline_verification_split.json \
  --predictions-out outputs/evaluation/baseline_verification_predictions.csv \
  --metrics-out outputs/evaluation/baseline_verification_metrics.json
```

주의: 검증용 데이터는 `2명` class만 있으므로 이 dry-run 성능은 실제 모델 성능으로 해석하면 안 된다.

## 주의

현재 `data/raw`에는 실패했던 0 byte 파일도 남아 있다. 삭제하지 말고 실패 기록으로 보존한다.

최종 학습에는 다음 조건을 만족하는 세션만 사용한다.

```text
quality_status=valid_csi
dataset_role=training_candidate
use_for_final_training=true
meta.json 존재
사람 수 라벨이 stable_full_session
3D 프린터 안테나 거치대 사용
```

## GitHub 저장소

비공개 저장소 복제, Git LFS와 협업자 초대 방법은 [GitHub 저장소 사용 안내](docs/github_repository.md)를 참고한다.
