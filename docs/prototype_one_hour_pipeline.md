# 거치대 제작 전 1시간 프로토타입 파이프라인

## 목적

이 수집은 최종 학습 데이터를 만들기 위한 실험이 아니다. 거치대 완성 후 사용할 실제 코드의 초안을 검증하기 위한 프로토타입이다.

- 실제 측정 링크: 휴대폰 핫스팟/AP -> 수신 PC Intel 5300
- 송신 PC 역할: UDP 트래픽 생성
- 수신 PC 역할: UDP 수신 및 CSI 기록
- 데이터 역할: `verification_only`
- 최종 학습 사용: `false`

## 생성되는 파일

```text
data/raw/session_YYYYMMDD_HHMMSS/
  csi.dat
  udp_packets.csv
  capture_runtime.json
  meta.json

data/structured/session_YYYYMMDD_HHMMSS/
  window_features.csv
  manifest.json
```

`window_features.csv`는 실제 Intel 5300 타임스탬프를 기준으로 2초 window, 1초 stride로 생성된다. scaled CSI 진폭, 안테나 조합별 통계, 30개 subcarrier 통계, RSSI/noise/AGC와 window 품질 정보가 들어간다.

## 1. 송신 PC 연결 확인

송신 PC를 수신 PC와 같은 휴대폰 핫스팟에 연결한 뒤 실행한다.

```bash
iw dev wlp4s0 link
ip -4 addr show wlp4s0
ping -c 4 10.72.159.105
```

ping이 성공해야 다음 단계로 진행한다. 수신 PC IP가 바뀌었다면 실제 주소를 사용한다.

## 2. 10초 smoke test

수신 PC에서 현재 방 안에 유지되는 실제 인원 수를 `N`에 넣는다.

```bash
python3 scripts/capture/capture_prototype.py \
  --duration 10 \
  --num-people N \
  --room prototype_room
```

스크립트가 `READY`와 송신 명령을 출력하면, 송신 PC에서 출력된 명령을 실행한다.

수집 종료 후 다음 조건을 확인한다.

- `csi.dat`가 0 byte가 아님
- `capture_runtime.json`의 `completed`가 `true`
- `meta.json` 생성
- `window_features.csv` 생성
- `manifest.json`의 window 수가 0보다 큼

## 3. 1시간 수집

10초 smoke test가 통과한 뒤 수신 PC에서 실행한다.

```bash
python3 scripts/capture/capture_prototype.py \
  --duration 3600 \
  --num-people N \
  --activity natural \
  --room prototype_room
```

수신 스크립트는 첫 UDP 패킷을 받은 순간부터 3,600초를 계산한다. 송신 PC에서는 `READY` 뒤에 수신 화면에 출력된 명령을 실행한다. 기본 설정에서는 송신이 수집보다 10초 더 길게 실행된다.

## 4. 전체 프로토타입 데이터셋 결합

```bash
python3 scripts/dataset/assemble_structured_dataset.py \
  --include-prototype \
  --include-needs-review \
  --out-csv data/processed/structured_dataset_prototype.csv \
  --out-manifest data/processed/structured_dataset_prototype_manifest.json
```

## 5. 학습 코드 연결 확인

```bash
python3 scripts/train/train_baseline.py \
  --features-csv data/processed/structured_dataset_prototype.csv \
  --model-out outputs/models/structured_prototype_model.json \
  --split-out outputs/models/structured_prototype_split.json \
  --predictions-out outputs/evaluation/structured_prototype_predictions.csv \
  --metrics-out outputs/evaluation/structured_prototype_metrics.json
```

현재처럼 한 가지 인원 수 라벨만 있으면 정확도는 모델 성능을 의미하지 않는다. 이 단계의 성공 조건은 입력 CSV부터 모델 및 평가 파일 생성까지 오류 없이 끝나는 것이다.

## 주의

- 한 시간 동안 인원 수가 바뀌면 하나의 고정 라벨로 사용할 수 없다.
- 사람이 입장하거나 퇴장했다면 해당 시각을 별도로 기록하거나 세션 전체를 학습에서 제외한다.
- 휴대폰 핫스팟의 위치와 방향을 바꾸지 않는다.
- 수신 PC와 안테나 위치를 수집 중 움직이지 않는다.
- 거치대 제작 전 데이터이므로 `use_for_final_training=false`를 유지한다.
