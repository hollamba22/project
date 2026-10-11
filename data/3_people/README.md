# 3명 데이터 수집 폴더

이 폴더는 방 안의 실제 인원 수가 수집 시작부터 종료까지 3명으로 유지된 세션만 저장한다.
웹캠 영상은 라벨 검증용이며 학습 모델 입력에는 사용하지 않는다.

## 저장 구조

```text
data/3_people/
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

CSI와 영상은 동일한 `session_YYYYMMDD_HHMMSS` 이름으로 연결한다. 파일명을 따로
변경하거나 한쪽 파일만 다른 세션으로 옮기지 않는다.

## 수신 PC 실행

먼저 10초 시험 수집을 실행한다.

```bash
sudo -v
python3 scripts/capture/capture_prototype.py \
  --duration 10 \
  --num-people 3 \
  --activity natural \
  --room project_room \
  --camera-device /dev/video0 \
  --collection-root data/3_people \
  --capture-purpose training \
  --antenna-holder 3d_printed_v1
```

`READY`가 표시된 다음에만 송신 PC에서 수신 화면에 출력된 명령을 실행한다.
시험 수집이 정상적으로 끝나면 `--duration 60`으로 바꾸어 본 수집을 반복한다.

## 라벨 조건

- 세션 전체에서 방 안의 인원 수를 3명으로 유지한다.
- 입장 또는 퇴장이 발생한 세션은 3명 학습 데이터로 사용하지 않는다.
- TX/RX PC, 안테나 거치대, 핫스팟 휴대폰, 웹캠 위치와 방향을 고정한다.
- 문 상태와 대형 물체 배치를 세션 사이에도 동일하게 유지한다.
- 사람은 정해진 활동 조건인 `natural` 범위에서 자연스럽게 움직인다.
