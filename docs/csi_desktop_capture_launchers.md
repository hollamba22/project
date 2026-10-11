# CSI RX/TX 바탕화면 실행기

기준: `csi_4people_20min_success_case_20260902.md`. Python 3.6 이상과 기존 CSI
파이프라인을 사용한다. 성공 기준 SSID는 `Minhyuck S24+`, 표시 이름은 `김민혁 핫스팟`이다.
RX/TX 모두 현재 연결된 Wi-Fi의 실제 SSID를 탐지해 수집 프로필에 자동 반영한다.
다른 SSID도 직접 입력할 필요 없이 미검증 환경 경고에 Y로 동의하면 진행할 수 있다.
실제 SSID와 `verified=false`를 제어 로그에 남기며, 두 PC의 SSID/BSSID 일치 검사는 유지한다.
이는 수집 설정의 자동 반영이며 OS의 Wi-Fi 연결이나 저장된 프로필을 변경하지 않는다.
IP/BSSID도 매번 현재 Wi-Fi 링크에서 읽는다. Wi-Fi 비밀번호는 입력받거나 저장하지 않는다.

2026-09-17부터 RX에서 **강의실·배치·행동과 같은 방의 0명 기준 세션**을 확인한다.
기존 데이터는 G308이며 오늘의 G304 수집은 [G304 0~4명 안내](csi_collection_G304_20260917.md)를 따른다.
강의실 정보는 RX에서 관리하며 TX 제어 설정 스키마는 유지하므로 기존 TX 실행기도 사용할 수 있다.

2026-09-29부터 수집 종류 `2`에 **0~4명 자유 테스트(CSI+영상, 기본 40분)**가 추가되었다.
무작위 활동·입퇴실을 기록하고 실제 인원은 추후 영상으로 작성한다.
별도 `data/free_test`에 저장하며 [자유 테스트 실행 안내](csi_free_test_capture.md)를 따른다.

## RX 설치 및 실행

RX의 현재 프로젝트에서 일반 사용자로 실행한다. 시스템 설치나 sudo 설치는 하지 않는다.

```bash
cd ~/바탕화면/project
bash tools/install_csi_capture_launchers.sh rx
python3 tools/csi_capture_rx_launcher.py
```

설치 후 바탕화면 `CSI RX 수집` 아이콘을 더블 클릭하면 터미널이 열린다.
아이콘 우클릭 → **실행 허용**이 필요한 GNOME 환경이 있다. 설치 파일은 실행 권한
0755이며 `Terminal=true`, 절대 `Exec`/`Path`를 사용한다. `gio`가 있으면 사용자 파일의
Trust 메타데이터도 설정하며 지원되지 않으면 실행 허용 안내를 출력한다. 설치기는 XDG 바탕화면,
존재하는 `바탕화면`/`Desktop` 순으로 찾고 없는 바탕화면은 만들지 않는다.
다시 설치해도 같은 파일만 갱신하며 다른 사용자 파일이나 심볼릭 링크는 덮어쓰지 않는다.
프로젝트를 이동한 경우 새 위치에서 재설치한다. `tools/*.desktop`은 설치용 템플릿이다.

## TX 복사 및 설치

TX는 CSI 파서/수신 드라이버가 필요 없다. 다음 파일을 상대 경로 그대로 복사한다.
기존 TX 작업과 충돌하지 않도록 새로운 `csi-launcher` 폴더에 풀 것을 권장한다.
RX 프로젝트에서 복사용 아카이브 생성:

```bash
tar -czf /tmp/csi-tx-launcher.tar.gz \
  tools/csi_capture_common.py tools/csi_capture_tx_launcher.py \
  tools/install_csi_capture_launchers.py tools/install_csi_capture_launchers.sh \
  tools/csi-capture-tx.desktop \
  scripts/sender/safe_sender.py scripts/capture/webcam_recorder.py \
  docs/csi_desktop_capture_launchers.md
```

USB 등으로 아카이브를 TX에 복사한다. TX에서 새 경로를 사용하여 실행:

```bash
mkdir -p ~/바탕화면/csi-launcher
tar -xzkf /미디어/실제경로/csi-tx-launcher.tar.gz -C ~/바탕화면/csi-launcher
cd ~/바탕화면/csi-launcher
bash tools/install_csi_capture_launchers.sh tx
python3 tools/csi_capture_tx_launcher.py
```

영문 환경이면 위 `바탕화면`을 `Desktop`으로 바꾼다. 기존 프로젝트가
`~/바탕화면/projects`이면 그 프로젝트에 같은 상대 경로로 변경 파일을 검토·복사한 후
그 위치에서 설치해도 된다. `tar -k`는 기존 파일 덮어쓰기를 거부한다.
TX 아이콘 이름은 `CSI TX 송신`이다. 다른 무선 인터페이스를 사용할 때는
`python3 tools/csi_capture_tx_launcher.py --interface <실제인터페이스>`로 실행한다.
RX/TX 모두 `--control-port 5006` 옵션을 지원하며 양쪽 값을 같게 설정한다.

## 운영 순서

1. 두 PC를 NetworkManager에서 같은 핫스팟에 연결하고 장비 위치를 고정한다.
2. RX 아이콘 실행 → 강의실 → 수집 종류를 선택한다. 기존 방식은 `1`을 선택하고 인원 → 배치 → 행동/0명 기준(1명 이상) → Wi-Fi → 시간/반복 → 카메라 → 참가자/자리 → 준비/안정화 시간을 입력한다. 자유 테스트는 `2`를 선택하며 고정 인원·행동·자리 질문 없이 진행한다.
3. 다른 핫스팟/채널 또는 영상 없는 수집은 경고를 읽고 별도로 Y로 승인한다.
4. RX의 현재 IP, TCP 포트, 일회용 PIN을 TX 운영자에게 전달한다.
5. TX 아이콘 실행 → 자동 탐지된 Wi-Fi 확인 → RX IP → PIN → RX 설정 요약을 승인한다.
6. TX ping 4회와 TX_READY/READY_ACK 교환이 성공한 후 RX 최종 질문이 나타난다.
7. RX에서 강의실·배치·인원·행동·기준 세션 요약을 확인하고 Y를 입력한 뒤 sudo 인증을 완료한다.
8. 카메라 준비 후 CMD에서 자리 준비/퇴실(기본 30초)·안정화(기본 60초)를 안내한다.
   카운트다운 후 CSI 로거를 시작하고 netlink/UDP READY 확인 뒤 START/ACK로 송신한다.
9. 첫 유효 UDP부터 RX 계획 시간을 재고 TX는 그보다 10초 길게 보낸다.
10. 양쪽 COMPLETE 및 원본·영상·메타데이터·정형화 manifest를 확인한다.

## 0명(빈 방) 수집

인원 입력과 RX/TX 공통 설정 검사는 **0 이상의 정수**를 허용한다.
0은 빈 방을 나타내는 실제 라벨이며, 미입력이나 취소가 아니다. 음수·소수·문자열 형태의
제어 설정 값·bool은 계속 거부하고, 수집 시간은 기존처럼 0보다 커야 한다.

실행 중인 RX 창을 종료하고 `CSI RX 수집` 아이콘을 새로 열어 다음과 같이 입력한다.
아이콘이 현재 프로젝트를 가리키고 있다면 재설치는 필요 없다.

```text
[0] 수집 강의실 ID: G304
[0-1] 수집 종류: 1 (기존 고정 인원 학습 수집)
[1] 수집 인원 수 (0: 빈 방): 0
[1-1] 배치 ID: A
[2] 현재 연결된 Wi-Fi 확인
[3] 수집 시간(분): 5 (기본값, 20분도 직접 입력 가능)
[4] 카메라: Y, 장치: Enter 또는 /dev/video0
```

이후 TX 연결·승인과 RX 최종 승인은 기존 절차와 같다. 5분이면 RX 300초, TX 310초,
100 pkt/s, 512바이트, UDP 5005를 유지하며, 0명이라고 송신을 생략하지 않는다.
저장 위치는 `data/0_people/{CSI_DATA,Web_Cam,META_DATA}`이고 정형화 결과는
`data/structured/<session>`에 생성된다. 메타데이터·CSV에는 `num_people=0`,
`activity=empty`를 기록한다. 1명 이상은 앉기·서기·교대 걷기·자세 변경·자연 활동 중 선택한다.
0명 세션도 실패 시 학습 금지 처리하며 라벨을 다른 인원으로 바꾸지 않는다.

RX/TX PC와 핫스팟은 켜 둔 채 **수집 시작부터 종료까지 실제 방에 사람이 없어야 한다.**
운영자 퇴장 구간이 수집에 섞이지 않도록 시작 위치/방법을 준비하고 카메라로 확인한다.
퇴실·안정화 타이머는 준비가 끝난 뒤 동작한다. 실제 퇴실 여부와 인원은 영상으로 확인한다.

## CMD 실시간 행동 안내와 연속 수집

1명 이상은 행동 `0`(자동 진행)이 기본이다. **한 동작 5분 × 앉기/서기/교대 걷기 × 2회 =
인원별 30분**을 한 파일로 연속 수집한다. 동작당 시간과 반복 횟수는 변경할 수 있다.
수집 중에는 인원·강의실·배치를 고정한다. 0명은 선택한 시간 동안 빈 방을 유지한다.
이전 단일 행동 선택도 지원한다.

CMD가 전체/동작별 남은 시간, 지금 할 행동, 걷기 방향·정지·60초 교대를 표시한다.
타이머는 첫 유효 UDP에 맞추고 준비 90초는 계획 수집 시간에서 제외한다.
카운트다운 중에도 heartbeat·UDP 수신기·카메라 상태를 점검하고 중단 시 START를 보내지 않는다.
안내 전환 시 터미널 bell을 사용하며 소리 여부는 터미널 설정에 따른다. 중단은 Ctrl+C다.
종료 후 결과를 읽고 Enter로 창을 닫는다. TX의 제어 스키마와 송신 시간 규칙은 바뀌지 않는다.

참가자/자리 입력은 `P1:Z1 P2:Z2` 형식이다. 입력 순서대로 걷기를 교대하며, 두 번째 회차는
두 번째 참가자부터 시작한다. `activity_segments.json`에 계획 구간을, `session_control.json`에
실제 안내 시각을 기록한다. 자동 진행의 파일 단위 활동은 `mixed`이며, 실제 수행과 동작
전환 구간은 영상으로 검수한다. [오늘 수집 안내와 미리보기](csi_collection_G304_20260917.md)를 참고한다.

### TX도 0명을 허용해야 함

이 프로젝트의 TX 실행기는 수정된 `tools/csi_capture_common.py`를 공유하므로 0명을 허용한다.
TX에 이전 버전을 복사했다면 변경된 공통 파일을 검토·반영하고 TX 창도 새로 열어야 한다.
**송신 PC의 파일은 RX에서 수정하는 것만으로 자동 갱신되지 않는다.**

별도 구현한 `csi-tx-standalone`의 `tools/csi_tx_common.py`는 이 프로젝트 공통 파일과
API가 다르므로 서로 덮어쓰면 안 된다. 해당 TX의 `num_people` 검사를 0 이상 정수로
수정해야 하며, 다운로드 없이 적용할 수 있는
[송신 PC용 수정 프롬프트](tx_zero_people_update_prompt.md)를 제공한다.
RX가 전송한 0명을 TX가 1명으로 바꾸는 우회는 설정 일치/라벨을 훼손하므로 금지한다.

## 제어와 실패 정책

- TCP 제어 기본 5006, UDP 데이터 5005. RX의 현재 Wi-Fi 주소에만 bind한다.
  자동 discovery는 없으며 Wi-Fi 서브넷 밖의 TX, SSID/BSSID/채널/peer IP 불일치는 차단한다.
  TCP는 SO_REUSEADDR로 이전 세션의 TIME_WAIT 중에도 다음 세션을 시작할 수 있다.
  SO_REUSEPORT는 사용하지 않으므로 실행 중인 RX의 중복 점유는 계속 차단한다.
  이전 버전 종료 직후에는 약 1분 기다려야 할 수 있다. 실행 중인 프로그램은
  파일 수정만으로 갱신되지 않으므로 대기/오류 창을 종료한 뒤 다시 실행한다.
- JSON Lines protocol v1, 한 줄 최대 16 KiB, 필수 envelope:
  `protocol_version`, `session_id`, `nonce`, `type`, `body`.
  첫 HELLO는 세션을 알기 전이라 ID/nonce가 빈 문자열이며 PIN/역할/현재 링크를 보낸다.
  RX CONFIG부터 256비트 난수 nonce와 RX 세션 ID가 모든 메시지에 필요하다.
  PIN은 임의의 6자리 일회용 값이며 잘못된 접속은 세션을 종료한다.
  이는 로컬 실험 연결 확인용이며 TLS/적대적 네트워크용 인증 프로토콜은 아니다.
- HELLO → CONFIG → TX_READY(동일 설정·ping) → READY_ACK → RX 승인 →
  capture READY → START → START_ACK → DONE → COMPLETE → COMPLETE_ACK.
  TX는 START_ACK 송신 뒤에만 `safe_sender.py`를 생성한다.
  START_ACK가 3초 안에 없으면 START를 최대 3회 전송한다.
  중복 START에는 ACK만 다시 보내고 sender를 다시 만들지 않는다.
  다른 순서 오류는 차단한다. 연결 실패는 자동 과거 IP fallback 없이 R로 새 세션을 시작한다.
- heartbeat 2초, 상대 메시지 없음 15초 후 실패. 운영자 입력 중에도 heartbeat가 동작한다.
  초기 접속/설정 승인 대기는 RX 10분, TX START 대기는 15분이다.
  START 후 첫 유효 UDP 20초, 수집 중 UDP 정지 5초, RX 수집 종료 후 TX DONE 대기 30초,
  sender 종료/후처리 여유는 TX에서 계획 송신 시간 + 300초다.
  sudo 사전 인증은 최대 120초이며 제어 연결 단절 시 인증 자식도 종료한다.
  모든 소켓에 timeout이 있고 제어 스레드/대기 큐 크기를 제한한다.
- UDP 페이로드는 전체 512바이트를 유지하며 앞부분에 `CSI1:<nonce>:`를 넣는다.
  협상한 TX source IP, nonce prefix, 512바이트가 모두 맞아야 타이머/CSV에 포함한다.
  이전 sender나 우연히 도착한 UDP는 reject 횟수에만 포함한다.
- RX 로거는 기존 guard를 통해 `sudo -n`으로 실행한다. 새 API 경로에서 guard는
  자식 PID의 NETLINK_CONNECTOR 소켓 및 multicast membership과 출력 파일을 확인하고
  별도 stdout JSON `{"ready": true}`를 출력한다. 일반 로거 출력은 로그 파일로 간다.
  기존 CLI 경로는 그대로 지원한다.
- 카메라 선택 시 V4L2 장치·포맷, GStreamer 플러그인, DISPLAY/Wayland를 사전 확인한다.
  실제 640×480/10fps 변환·미리보기·WebM 동작은 WebcamRecorder 시작 검사로 확인하며
  실패하면 START하지 않는다. `--camera-no-preview`는 사용하지 않는다.
- 수집 중 logger/camera 조기 종료, 제어 단절, sender 실패, Ctrl+C는 실패로 기록하고
  보유한 자식만 종료한다. guard는 STOP/EOF로 자신의 로거를 회수한다.
  후처리 중 취소도 실행 중인 후처리 자식을 회수한다. SIGTERM/SIGHUP도 취소 경로를 따른다.
  SIGKILL/전원 차단처럼 정리 코드를 실행할 수 없는 중단은 운영체제 수준 한계다.

## 결과와 메타데이터

RX 세션은 `data/<N>_people/{CSI_DATA,Web_Cam,META_DATA}`에 저장된다.
계획 분은 Decimal로 초 변환 후 수집 API의 float 초로 전달되며 소수 초를 반올림하지 않는다.
`outputs/launcher/<session>_<role>.json`에 준비 단계부터 최종 실패/완료 기록을 남긴다.
수집 폴더 생성 후에는 `META_DATA/<session>/session_control.json`에도 RX 제어 기록을 남긴다.
nonce/PIN/비밀번호는 제어 로그에 저장하지 않는다.

기존 `capture_runtime.json`/`meta.json`에 추가되는 `session_control`은 파일 참조와 최종
완료 여부/중단 원인이다. 제어 로그에는 프로필 검증 여부, 실제 링크/IP/MAC,
카메라 정책, 인원·계획 시간, ping/사전 검사, 승인·START 시각, sender 전송 수가 있다.
수집이 끝났어도 TX 완료 확인에 실패하면 runtime을 실패로 바꾸고 meta는
`failure_history`, `use_for_final_training=false`, structured manifest의
`quality.final_training_allowed=false`로 기록한다. 부분 세션도 실패 meta를 남긴다.
카메라 없는 수집은 `camera.label_video_missing=true`를 남긴다.
영상 없는 라벨과 성공 사례처럼 드문 CSI 형상 차이는 학습 전 별도 검토한다.

`meta.json` 및 정형화 manifest의 `environment`에는 `room`, `setup_id`,
`empty_reference_session_id`를 저장한다. runtime에는 같은 이름의 최상위 필드,
RX 제어 로그에는 `collection_context`를 남긴다. 실패한 수집도 장소 정보는 보존한다.
기존 특징 CSV는 `session_id`로 manifest의 환경 정보와 연결한다.

## 자동 검증과 수동 검증

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile tools/csi_capture_common.py tools/csi_capture_rx_launcher.py \
  tools/csi_activity_guide.py tests/test_csi_activity_guide.py \
  tools/csi_capture_tx_launcher.py tools/install_csi_capture_launchers.py \
  scripts/capture/capture_prototype.py scripts/capture/csi_logger_guard.py \
  scripts/sender/safe_sender.py scripts/dataset/create_meta.py tests/test_capture_launchers.py
bash -n tools/install_csi_capture_launchers.sh tools/start_4_people_20min_capture.sh
```

자동 테스트는 localhost TCP/UDP와 임시 파일/가짜 CSI·카메라를 사용한다.
실제 sender를 사용하는 RX 3초/TX 13초 실험을 4명/0명에 각각 수행하며 약 40초 소요된다.
0명 입력·설정 협상·카메라 유무·실패 라벨 보존과, 합성 CSI를 실제 파서로 읽어
`meta.json`·학습 CSV까지 숫자 0이 보존되는지도 검사한다.
모든 테스트 출력 데이터는 임시 폴더에 두므로 기존 실험 데이터와 섞이지 않는다.

**실제 두 PC·CSI·카메라 end-to-end 검증은 별도 필요하다.** 양쪽 바탕화면 아이콘 실행과
Trust 승인을 확인한 뒤 RX 1명/0.05분/카메라 Y, TX 설정 승인으로 시작한다.
RX의 마지막 Y 전에는 CSI/UDP가 시작하지 않는지, READY 전에 sender가 없는지,
미리보기와 `.webm`이 함께 동작하는지 확인한다. COMPLETE 후 다음을 확인한다.

```bash
python3 scripts/dataset/validate_sessions.py --help
cat data/1_people/META_DATA/<새세션>/session_control.json
cat data/1_people/META_DATA/<새세션>/capture_runtime.json
cat data/1_people/META_DATA/<새세션>/meta.json
cat data/structured/<새세션>/manifest.json
```

이어서 0.1분/카메라 N 경로, 잘못된 PIN, 다른 핫스팟, RX 최종 N,
수집 중 TX Ctrl+C 및 RX Ctrl+C를 각각 새 세션으로 확인한다.
실패 로그와 `pgrep -af 'log_to_file|safe_sender.py|gst-launch-1.0'`를 대조하여 고아가 없는지 확인한다.
짧은 실험을 통과하면 4명/20분에서 기존 성공 사례와 CSI 레코드/영상/윈도우를 비교한다.

장애 시 `iw dev <인터페이스> link`, `ip -4 addr`, `ip route get <현재_RX_IP>`,
`ping -c 4 <현재_RX_IP>`, `ss -ltnp`, `ss -lunp`를 확인한다.
AP client isolation이나 방화벽의 TCP 5006/UDP 5005 차단 여부를 점검한다.
실행기는 방화벽, Wi-Fi 프로필, 채널, power save를 자동 변경하지 않는다.
