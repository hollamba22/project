# CSI 파싱/시각화 코드 사용법

이 문서는 수집된 Intel 5300 CSI Tool `.dat` 파일을 Python으로 파싱하고 시각화하는 방법을 정리한다.

## 생성된 스크립트

```text
scripts/csi/csi_parser.py
scripts/csi/visualize_csi.py
```

두 스크립트는 `numpy`, `matplotlib` 없이 Python 표준 라이브러리만 사용한다.

## 파서 기능

`scripts/csi/csi_parser.py`는 `csi.dat`에서 `code=0xBB` CSI 레코드를 읽는다.

추출하는 주요 정보:

- CSI record count
- `Nrx`, `Ntx`
- RSSI A/B/C
- noise
- AGC
- antenna permutation
- rate flag
- complex CSI matrix
- amplitude 통계

Python 내부 CSI shape:

```text
[subcarrier][rx][tx]
```

즉, 30개 subcarrier마다 RX antenna와 TX antenna pair의 complex CSI 값이 들어 있다.

## 기본 요약 생성

예시:

```bash
python3 scripts/csi/csi_parser.py \
  data/raw/session_20260710_153743/csi.dat \
  --pretty \
  --summary-json outputs/csi_visualizations/session_20260710_153743/summary.json
```

생성 파일:

```text
outputs/csi_visualizations/session_20260710_153743/summary.json
```

정상 예시:

```json
{
  "record_count": 4916,
  "antenna_dimensions": {
    "3x2": 4916
  },
  "rates": {
    "0x210f": 4752
  }
}
```

## 패킷별 amplitude CSV 생성

예시:

```bash
python3 scripts/csi/csi_parser.py \
  data/raw/session_20260710_153743/csi.dat \
  --packet-csv outputs/csi_visualizations/session_20260710_153743/packet_amplitude_summary.csv
```

CSV column:

```text
packet_index,timestamp_low,bfee_count,Nrx,Ntx,rate_hex,
rssi_a,rssi_b,rssi_c,noise,agc,amp_mean,amp_std,amp_min,amp_max
```

이 CSV는 이후 baseline feature 생성에 사용할 수 있다.

## 전체 시각화 생성

예시:

```bash
python3 scripts/csi/visualize_csi.py \
  data/raw/session_20260710_153743/csi.dat \
  --outdir outputs/csi_visualizations/session_20260710_153743
```

생성 파일:

```text
outputs/csi_visualizations/session_20260710_153743/
  summary.json
  packet_amplitude_summary.csv
  amplitude_over_time.svg
  subcarrier_heatmap.svg
  antenna_pair_mean.svg
  index.html
```

## 시각화 파일 의미

### `amplitude_over_time.svg`

패킷 순서에 따른 평균 CSI amplitude 변화 그래프다.

용도:

- 수집 중 CSI가 시간에 따라 변하는지 확인
- 갑작스러운 끊김/이상값 확인
- 사람 움직임이 있는 구간의 변화 확인

### `subcarrier_heatmap.svg`

시간축 packet index와 30개 subcarrier별 평균 amplitude heatmap이다.

용도:

- subcarrier별 변화 패턴 확인
- 전체 세션이 비어 있지 않고 정상적으로 변하는지 확인
- 특정 subcarrier만 이상한지 확인

### `antenna_pair_mean.svg`

RX/TX antenna pair별 평균 amplitude 막대그래프다.

용도:

- 어떤 antenna pair가 강하게 잡히는지 확인
- 안테나 연결/방향 문제 확인
- 거치대 완성 후 antenna pair 안정성 확인

## 현재 검증된 결과

현재 두 성공 파일 모두 파싱/시각화에 성공했다.

### `session_20260710_145820`

```text
file_bytes: 1843190
record_count: 4690
antenna_dimensions:
  3x2: 4638
  3x1: 52
main rate: 0x210f
mean amplitude: about 30.40
```

### `session_20260710_153743`

```text
file_bytes: 1941820
record_count: 4916
antenna_dimensions:
  3x2: 4916
main rate: 0x210f
mean amplitude: about 36.05
```

## 주의사항

현재 스크립트는 초기 검증/시각화용이다.

최종 모델 학습 전에는 다음 단계가 추가로 필요하다.

- session 단위 metadata 연결
- 사람 수 label 연결
- windowing
- train/test split
- normalization
- feature extraction

즉, 이 코드는 “CSI가 제대로 읽히는지와 어떤 형태로 변화하는지 확인하는 단계”를 담당한다.

## 다음 단계

다음 구현 단계는 전처리 코드다.

필요한 기능:

- 여러 `session_*/csi.dat` 일괄 스캔
- `meta.json` 읽기
- 실패/검증용/학습용 데이터 구분
- 1초 또는 2초 window 생성
- window별 feature CSV 생성
- `num_people` 라벨 연결
