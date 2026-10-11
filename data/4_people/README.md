# 4명 20분 데이터 수집

이 폴더에는 수집 전 구간에 실제 인원이 4명으로 유지된 세션만 저장한다.
웹캠은 사후 라벨 검증용이며 CSI 기반 모델의 입력으로 사용하지 않는다.

## 저장 구조

```text
data/4_people/
  CSI_DATA/
    session_YYYYMMDD_HHMMSS.dat
  Web_Cam/
    session_YYYYMMDD_HHMMSS.webm
  META_DATA/
    session_YYYYMMDD_HHMMSS/
      meta.json
      capture_runtime.json
      udp_packets.csv
      csi_logger.log
      webcam_gstreamer.log
```

CSI와 영상은 같은 세션 ID로 연결한다. 파일명을 개별적으로 변경하지 않는다.

## 수집 전 고정 조건

- 수집 시작 전부터 종료 후 웹캠 post-roll까지 방 안에 정확히 4명이 있어야 한다.
- 수집 중 입장 또는 퇴장이 발생하면 해당 세션을 학습에 사용하지 않는다.
- TX/RX PC, 3D 안테나 거치대, 핫스팟 휴대폰, 웹캠 위치와 방향을 고정한다.
- 문 상태와 대형 물체 배치를 유지한다.
- 웹캠 화면에서 가능한 한 네 명이 모두 확인되게 한다.
- 송신 PC와 수신 PC를 동일한 `Minhyuck S24+` 2.4 GHz 핫스팟에 연결한다.

## 실행 순서

1. 수신 PC에서 웹캠이 `/dev/video0`으로 보이는지 확인한다.

```bash
python3 scripts/capture/webcam_recorder.py --list-devices
```

2. 송신 PC에서 수신 IP로 ping을 보낸다. 현재 수신 IP는 `10.175.218.22`다.

```bash
ping -c 4 10.175.218.22
```

3. `4 received, 0% packet loss`를 확인한 뒤 수신 PC에서 실행한다.

```bash
bash tools/start_4_people_20min_capture.sh
```

4. 수신 터미널에 `READY`가 나온 다음 송신 PC에서 실행한다.

```bash
python3 scripts/sender/safe_sender.py \
  --target 10.175.218.22 \
  --mode udp \
  --duration 1210 \
  --rate 100 \
  --size 512
```

수신 IP가 바뀌었다면 `READY` 아래에 자동 출력된 송신 명령을 그대로 사용한다.
수집과 후처리가 모두 끝날 때까지 양쪽 터미널을 닫거나 `Ctrl+C`를 누르지 않는다.

## 정상 완료 조건

- UDP 약 120,000패킷이 수신된다.
- CSI 파일이 0 byte보다 크고 파싱 가능한 레코드가 존재한다.
- CSI 로거가 `stopped: true`, `exit_code: 0`으로 종료된다.
- 영상 파일이 재생 가능하고 약 20분 이상의 길이를 가진다.
- `meta.json`의 `num_people`이 4이고 `use_for_final_training`이 true다.
- 정형화된 `window_features.csv`가 생성된다.
