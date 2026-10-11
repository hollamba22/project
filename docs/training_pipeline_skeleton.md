# 전처리/학습/평가 파이프라인 뼈대

이 문서는 거치대 완성 후 본격 데이터셋이 들어왔을 때 사용할 전처리/학습/평가 코드 흐름을 정리한다.

현재 코드는 최종 성능을 내기 위한 코드가 아니라, 데이터가 생겼을 때 바로 연결할 수 있는 뼈대다.

## 추가된 스크립트

```text
scripts/preprocess/make_windows.py
scripts/preprocess/extract_features.py
scripts/train/train_baseline.py
scripts/evaluate/evaluate_model.py
```

모든 스크립트는 Python 표준 라이브러리만 사용한다. 현재 수신 PC에 `numpy`, `matplotlib`, `scikit-learn`이 없어도 실행된다.

## 전체 흐름

```text
data/raw/session_*/csi.dat + meta.json
        |
        v
outputs/dataset/session_index.csv
        |
        v
data/processed/windows.csv
        |
        v
data/processed/features.csv
        |
        v
outputs/models/baseline_model.json
        |
        v
outputs/evaluation/*_metrics.json
```

## 1. 세션 인덱스 생성

먼저 전체 raw session을 검증한다.

```bash
python3 scripts/dataset/validate_sessions.py
```

생성 파일:

```text
outputs/dataset/session_index.csv
outputs/dataset/session_index.json
```

## 2. Window 생성

최종 학습용 세션만 사용할 때:

```bash
python3 scripts/preprocess/make_windows.py
```

기본 조건:

```text
quality_status=valid_csi
dataset_role=training_candidate 또는 test_candidate
use_for_final_training=true
```

현재는 최종 학습용 세션이 없으므로 기본 실행 결과는 window 0개가 정상이다.

검증용 세션까지 포함한 dry-run:

```bash
python3 scripts/preprocess/make_windows.py \
  --include-verification \
  --out-csv data/processed/windows_verification.csv \
  --out-json data/processed/windows_verification.json
```

현재 검증 결과:

```text
window_count=118
```

기본 window 설정:

```text
window size: 2초
stride: 1초
```

## 3. Feature 추출

최종 학습용:

```bash
python3 scripts/preprocess/extract_features.py
```

검증용 dry-run:

```bash
python3 scripts/preprocess/extract_features.py \
  --windows-csv data/processed/windows_verification.csv \
  --out-csv data/processed/features_verification.csv
```

현재 검증 결과:

```text
feature_rows=118
```

추출 feature 예시:

- 전체 amplitude mean/std/min/max/median/energy
- packet 평균 amplitude 변화량
- RSSI A/B/C 평균
- noise 평균
- AGC 평균
- antenna pair별 mean/std
- 30개 subcarrier별 mean/std

## 4. Baseline 학습

최종 학습용:

```bash
python3 scripts/train/train_baseline.py
```

검증용 dry-run:

```bash
python3 scripts/train/train_baseline.py \
  --features-csv data/processed/features_verification.csv \
  --model-out outputs/models/baseline_verification_model.json \
  --split-out outputs/models/baseline_verification_split.json \
  --predictions-out outputs/evaluation/baseline_verification_predictions.csv \
  --metrics-out outputs/evaluation/baseline_verification_metrics.json
```

현재 구현된 baseline:

```text
nearest_centroid
majority
```

주의: 현재 검증용 데이터는 `2명` class만 있으므로 accuracy/F1은 실제 성능 의미가 없다. 코드 흐름 검증용이다.

현재 dry-run 결과:

```text
train_windows=59
test_windows=59
labels=['2']
accuracy=1.0000
macro_f1=1.0000
```

이 결과는 단일 class라 당연히 높게 나오는 것이므로 보고서 성능으로 사용하면 안 된다.

## 5. 독립 평가

저장된 모델을 다시 평가하려면:

```bash
python3 scripts/evaluate/evaluate_model.py
```

검증용 dry-run:

```bash
python3 scripts/evaluate/evaluate_model.py \
  --features-csv data/processed/features_verification.csv \
  --model outputs/models/baseline_verification_model.json \
  --split outputs/models/baseline_verification_split.json \
  --mode test \
  --predictions-out outputs/evaluation/model_verification_predictions.csv \
  --metrics-out outputs/evaluation/model_verification_metrics.json
```

생성 파일:

```text
outputs/evaluation/model_verification_predictions.csv
outputs/evaluation/model_verification_metrics.json
```

## 본격 데이터 수집 후 실행 순서

거치대 완성 후 class별 데이터가 수집되면 다음 순서로 실행한다.

```bash
python3 scripts/dataset/validate_sessions.py
python3 scripts/preprocess/make_windows.py
python3 scripts/preprocess/extract_features.py
python3 scripts/train/train_baseline.py
python3 scripts/evaluate/evaluate_model.py
```

## 현재 한계

아직 최종 학습 코드는 아니다.

현재 한계:

- 검증용 데이터는 `2명` class뿐이다.
- 3D 프린터 거치대 완성 전 데이터다.
- scikit-learn 기반 RandomForest/SVM은 아직 구현하지 않았다.
- phase feature는 아직 사용하지 않는다.
- window timestamp는 packet index를 세션 duration에 선형 매핑하는 방식이다.

본격 데이터가 모이면 다음을 추가한다.

- scikit-learn RandomForest/SVM/LogisticRegression
- session/group 기반 cross validation
- confusion matrix 이미지 생성
- class별 precision/recall/F1 표
- phase 보정 feature
