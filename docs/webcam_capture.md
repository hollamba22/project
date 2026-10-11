# 웹캠 연결 및 녹화

웹캠 영상은 사람 수 라벨과 실험 상태를 사후 확인하는 용도다. 최종 모델 입력에는 영상을 사용하지 않는다.

현재 코드는 별도 Python 패키지 없이 Ubuntu에 설치된 GStreamer를 사용한다. 녹화 중에는 실시간 미리보기 창이 열리고, 같은 영상은 VP8 형식의 `video.webm`으로 저장된다. 오디오는 녹음하지 않는다.

## 웹캠 장치 확인

웹캠을 연결한 뒤 실행한다.

```bash
python3 scripts/capture/webcam_recorder.py --list-devices
```

정상이라면 `/dev/video0`과 장치 이름이 표시된다. 장치가 여러 개면 실제 영상을 제공하는 번호를 아래 단독 녹화 시험으로 확인한다.

## 10초 단독 녹화 시험

```bash
python3 scripts/capture/webcam_recorder.py \
  --device /dev/video0 \
  --duration 10 \
  --output /tmp/webcam_test.webm \
  --log /tmp/webcam_test.log \
  --overwrite
```

명령이 성공하면 `/tmp/webcam_test.webm`이 0 byte보다 커야 한다. 실패 원인은 `/tmp/webcam_test.log`에서 확인한다.

녹화 중 미리보기 창을 닫지 않는다. 화면 표시가 필요 없는 경우에만 `--no-preview`를 추가한다.

## CSI와 함께 녹화

수신 PC에서 다음처럼 `--camera-device`를 추가한다.

```bash
python3 scripts/capture/capture_prototype.py \
  --duration 60 \
  --num-people 2 \
  --activity natural \
  --room project_room \
  --camera-device /dev/video0
```

웹캠은 CSI 로거보다 기본 5초 먼저 시작하고 CSI 종료 후 5초 더 녹화한다. 생성되는 파일은 다음과 같다.

```text
data/raw/session_YYYYMMDD_HHMMSS/
  csi.dat
  video.webm
  webcam_gstreamer.log
  udp_packets.csv
  capture_runtime.json
  meta.json
```

`capture_runtime.json`에는 카메라 장치, 해상도, FPS, 녹화 시간, 파일 크기와 종료 코드가 기록된다. `meta.json`의 `capture.video_file`에는 `video.webm`이 기록된다.

기본 녹화 설정은 `640x480`, `10 FPS`다. 라벨 확인에는 충분하며 수신 PC의 CPU 및 저장 공간 사용량을 줄인다.

CSI 동시 수집에서 미리보기를 끄려면 `--camera-no-preview`를 추가한다.

## 실패 처리

다음 경우 CSI 본 수집을 정상 완료로 처리하지 않는다.

- 웹캠 장치가 존재하지 않음
- 현재 사용자에게 장치 읽기/쓰기 권한이 없음
- GStreamer 녹화 프로세스가 중간에 종료됨
- 결과 영상이 0 byte임

웹캠을 사용하지 않는 기존 CSI 검증은 `--camera-device`를 생략하면 된다.
