# CSI 4명 20분 수집 성공 사례 - 2026-09-02

작성일: 2026-09-09  
성공 세션: `session_20260902_183751`

## 1. 문서 목적

이 문서는 2026-09-02에 성공한 4명, 20분 CSI 수집의 환경과 실행 순서, 결과를 다음 실험의 재현 기준으로 남긴다.

다음 수집을 시작하기 전에 이 문서와 현재 상태를 비교한다. IP 주소와 BSSID처럼 핫스팟을 다시 켤 때 달라지는 값은 과거 값을 강제로 사용하지 않고 현재 할당값을 사용한다.

## 2. 최종 판정

| 검증 항목 | 결과 | 판정 |
| --- | ---: | --- |
| 계획된 CSI 수집 시간 | 1,200초 | 성공 |
| 관측된 CSI 시간 | 1,202.757초 | 성공 |
| 수신 UDP 패킷 | 119,973개 | 성공 |
| CSI 파일 크기 | 38,161,090 bytes | 성공 |
| 파싱된 CSI 레코드 | 96,614개 | 성공 |
| 정상 `3 Rx x 2 Tx` 레코드 | 96,606개 | 성공 |
| 다른 형상 `3 Rx x 1 Tx` 레코드 | 8개, 약 0.008% | 정형화 시 제외 |
| 스케일링 오류 | 0개 | 성공 |
| 안테나 순열 오류 | 0개 | 성공 |
| 생성된 2초 윈도우 | 1,187개 | 성공 |
| 결측값 `NaN`/`Inf` | 0개 | 성공 |
| 영상 길이 | 20분 35.9초 | 성공 |
| CSI 로거 종료 | `stopped=true`, `exit_code=0` | 성공 |

**수집 자체는 성공했다.** 원본 CSI, 영상, UDP 기록 및 메타데이터가 모두 존재하고 CSI 파싱과 정형화까지 완료되었다.

현재 정형화 manifest는 형상이 다른 레코드 8개 때문에 보수적으로 `needs_review`, `final_training_allowed=false`를 기록한다. 이는 원본 수집 실패가 아니다. 8개 레코드는 윈도우 특징 계산에서 이미 제외되었다. 최종 학습 전에 허용 비율 기준을 팀에서 확정하고 수동 검토한다.

## 3. 성공한 시스템 구성

```text
송신 PC(Intel 5300)
        |
        | 동일한 2.4 GHz Wi-Fi 핫스팟
        v
Minhyuck S24+ 핫스팟/AP
        |
        | AP -> 수신 PC 무선 프레임에서 CSI 생성
        v
수신 PC(Intel 5300 + 수정 iwlwifi + CSI Tool)
        |
        +-- CSI 로그 저장
        +-- UDP 수신 기록
        +-- 웹캠 영상 저장
```

- 실제 RF 송신기는 휴대폰 핫스팟/AP다.
- 송신 PC는 UDP 트래픽을 발생시켜 AP가 수신 PC로 지속적으로 무선 프레임을 보내게 한다.
- 송신 PC와 수신 PC 모두 같은 `Minhyuck S24+` 핫스팟에 Wi-Fi로 연결했다.
- USB 테더링 경로 또는 서로 다른 핫스팟으로 UDP를 보내지 않았다.

## 4. 성공 당시 고정 조건

| 항목 | 성공 당시 값 |
| --- | --- |
| 수신 PC | `RXPC` |
| 수신 인터페이스 | `wlp4s0` |
| 수신 무선 MAC | `00:16:ea:ed:a9:80` |
| 수신 커널 | `4.15.0-213-generic` |
| 수신 드라이버 | CSI Tool용 수정 `iwlwifi` |
| `connector_log` | `1` |
| 핫스팟 | `Minhyuck S24+` |
| Wi-Fi 대역 | 2.4 GHz |
| 주파수/채널 | 2437 MHz / 채널 6 |
| 수집 중 관측 MCS | MCS 6 및 MCS 15 계열 |
| 트래픽 종류 | UDP |
| UDP 포트 | `5005` |
| 송신률 | 초당 100패킷 |
| 페이로드 | 512 bytes |
| 수신 계획 시간 | 1,200초 |
| 송신 계획 시간 | 1,210초 |
| 인원 라벨 | 4명 |
| 활동 | `natural` |
| 안테나 거치대 | `3d_printed_v1` |
| 웹캠 | `/dev/video0`, 640x480, 10 FPS |

TX/RX PC, 안테나 거치대, 핫스팟 휴대폰 및 웹캠의 위치와 방향은 수집 중 고정해야 한다. 이 세션의 메타데이터에는 정확한 좌표와 거리가 기록되지 않았으므로 이후 실험부터는 별도로 측정해 기록한다.

## 5. 성공 당시 동적 값

다음 값은 핫스팟 재시작 또는 DHCP 갱신 시 달라져도 정상이다.

| 항목 | 이 세션의 값 |
| --- | --- |
| AP BSSID | `be:93:07:3c:38:15` |
| 수신 PC IPv4 | `10.175.218.22/24` |
| 송신 PC IPv4 | `10.175.218.104` |

다음 실험에서는 `10.175.218.22`를 고정 입력하지 않는다. 수신 PC의 현재 IP를 확인하고, 수신 프로그램이 `READY`와 함께 출력하는 송신 명령의 주소를 사용한다.

## 6. 실제 성공 실행 순서

### 6.1 두 PC를 같은 핫스팟에 연결

송신 PC와 수신 PC의 Intel 5300 인터페이스를 모두 `Minhyuck S24+`의 2.4 GHz Wi-Fi에 연결했다.

수신 PC에서 링크와 주소를 확인한다.

```bash
uname -r
cat /sys/module/iwlwifi/parameters/connector_log
iw dev wlp4s0 link
ip -4 addr show wlp4s0
python3 scripts/capture/webcam_recorder.py --list-devices
```

필수 확인값은 다음과 같다.

```text
kernel: 4.15.0-213-generic
connector_log: 1
SSID: Minhyuck S24+
frequency: 2437 MHz
webcam: /dev/video0
```

### 6.2 송신 PC에서 수신 연결 확인

`<현재_RX_IP>`에는 수신 PC에서 확인한 현재 주소를 넣는다.

```bash
iw dev wlp4s0 link
ip -4 addr show wlp4s0
ip route get <현재_RX_IP>
ping -c 4 <현재_RX_IP>
```

`4 packets received`, `0% packet loss`를 확인한 뒤 진행한다.

### 6.3 수신 PC에서 수집 프로그램 실행

프로젝트 루트에서 다음 스크립트를 실행했다.

```bash
cd ~/바탕화면/project
bash tools/start_4_people_20min_capture.sh
```

이 스크립트는 다음 작업을 수행한다.

1. CSI 드라이버, Wi-Fi 링크, 웹캠, 기존 로거 및 디스크 공간을 사전 점검한다.
2. `sudo -v`로 CSI 로거 실행 권한을 미리 인증한다.
3. CSI 로거와 웹캠 녹화를 시작한다.
4. 송신을 시작할 수 있는 `READY` 메시지와 현재 RX IP 기반 명령을 출력한다.
5. 1,200초 수집 후 로거를 종료한다.
6. CSI 파싱, 메타데이터 작성 및 2초 윈도우 특징 생성을 수행한다.

### 6.4 `READY` 이후 송신 PC에서 UDP 시작

성공 세션에서는 다음 명령을 사용했다.

```bash
cd ~/바탕화면/projects
python3 scripts/sender/safe_sender.py \
  --target 10.175.218.22 \
  --mode udp \
  --duration 1210 \
  --rate 100 \
  --size 512
```

다음 실험에서는 위의 과거 IP 대신 수신 PC가 `READY` 아래에 출력한 명령을 그대로 사용한다.

수신 프로그램보다 송신을 10초 길게 실행하는 이유는 수신 시작 대기와 종료 시점의 여유를 확보하기 위해서다. 양쪽 프로그램이 끝날 때까지 터미널을 닫거나 `Ctrl+C`를 누르지 않는다.

## 7. 성공한 핵심 이유

1. 수신 PC를 CSI Tool과 호환되는 `4.15.0-213-generic` 커널로 부팅했다.
2. 수정된 `iwlwifi` 드라이버와 CSI 펌웨어를 사용하고 `connector_log=1`을 확인했다.
3. 호환성이 검증된 `Minhyuck S24+` 2.4 GHz 핫스팟을 사용했다.
4. 송신 PC와 수신 PC를 서로 다른 네트워크가 아니라 동일한 핫스팟에 연결했다.
5. 과거 고정 IP를 재사용하지 않고 현재 DHCP 주소로 통신했다.
6. 송신 전 ping으로 TX에서 RX까지의 경로를 확인했다.
7. 수신 프로그램의 `READY` 이후에 UDP 트래픽을 시작했다.
8. 초당 100개의 512-byte UDP 패킷을 보내 HT/MCS 무선 프레임이 지속적으로 발생하게 했다.
9. 수집 전에 `sudo -v`를 수행해 CSI 로거가 비밀번호 문제로 즉시 종료되는 상황을 방지했다.
10. CSI 로거 guard가 수집 종료 시 로거를 정상 종료하고 파일을 완결했다.
11. 3D 프린터 거치대로 안테나 방향을 고정했다.
12. 웹캠을 동시에 녹화해 4명 라벨과 수집 구간을 사후 검증했다.

## 8. 생성된 데이터

### 원본 CSI

```text
data/4_people/CSI_DATA/session_20260902_183751.dat
SHA-256: 60098a2a56fcd4fe2fa7bb3e20b6df0c7df48284d0a2c93660772c39ccba9c05
```

### 라벨 검증 영상

```text
data/4_people/Web_Cam/session_20260902_183751.webm
```

카메라는 CSI 입력으로 사용하지 않고 인원 라벨 검증용으로만 사용한다. 영상은 CSI 트래픽보다 약 9.44초 먼저 시작했고, CSI 시작 시점부터 중간 및 종료 직전 표본에서 4명이 확인되었다.

### 실행 기록 및 메타데이터

```text
data/4_people/META_DATA/session_20260902_183751/meta.json
data/4_people/META_DATA/session_20260902_183751/capture_runtime.json
data/4_people/META_DATA/session_20260902_183751/udp_packets.csv
data/4_people/META_DATA/session_20260902_183751/csi_logger.log
data/4_people/META_DATA/session_20260902_183751/webcam_gstreamer.log
```

### 정형화된 학습 입력 후보

```text
data/structured/session_20260902_183751/window_features.csv
data/structured/session_20260902_183751/manifest.json
```

`window_features.csv`에는 1,187개의 2초 윈도우와 윈도우당 88개 특징이 저장되어 있다. 모든 행은 `num_people=4`, `label_status=stable_full_session`, `dataset_role=training_candidate`다.

## 9. 다음 수집 전 재현 체크리스트

다음 항목이 모두 충족된 경우에만 본 수집을 시작한다.

- [ ] RX 커널이 `4.15.0-213-generic`이다.
- [ ] `connector_log`가 `1`이다.
- [ ] TX와 RX가 모두 `Minhyuck S24+`에 Wi-Fi로 연결되어 있다.
- [ ] 두 링크가 2437 MHz, 채널 6을 사용한다.
- [ ] RX의 현재 IPv4 주소를 새로 확인했다.
- [ ] TX에서 현재 RX IP로 ping이 0% 손실이다.
- [ ] 웹캠 `/dev/video0`이 인식된다.
- [ ] 3D 프린터 안테나 거치대와 안테나 방향이 고정되어 있다.
- [ ] 핫스팟, TX, RX 및 웹캠 위치가 고정되어 있다.
- [ ] 세션 전체에 필요한 인원이 방 안에 있고 영상으로 확인 가능하다.
- [ ] 수신 스크립트의 사전 점검이 통과했다.
- [ ] 수신 터미널에 `READY`가 나온 뒤 송신을 시작했다.
- [ ] 수집 종료 후 CSI 파일이 0 byte보다 크다.
- [ ] CSI record count, 영상 길이 및 정형화 manifest를 확인했다.

## 10. 실패로 이어질 가능성이 큰 변경

- `5.4` 계열 일반 커널로 부팅해 수정 CSI 드라이버가 활성화되지 않은 상태
- `connector_log`가 없거나 `0`인 상태
- S25+ 등 현재 장비에서 검증되지 않은 핫스팟 사용
- TX와 RX가 서로 다른 핫스팟 또는 서로 다른 네트워크에 연결된 상태
- 과거 성공 IP를 현재 네트워크에 수동으로 강제 설정
- 수신 프로그램의 `READY` 전에 송신 시작
- `sudo` 인증 없이 자동 수집을 시작해 CSI 로거가 즉시 종료
- 안테나, 거치대 또는 핫스팟 위치를 수집 중 변경
- 인원 입장 또는 퇴장이 있었는데 전체 세션에 단일 인원 라벨 부여

## 11. 데이터 해석 시 주의

- 이 20분 데이터는 연속된 한 세션이다. 1,187개 윈도우를 1,187개의 독립 실험으로 간주하지 않는다.
- 학습/검증/테스트를 나눌 때 같은 세션의 윈도우를 여러 분할에 섞지 않는다.
- 향후에는 인원별로 위치와 참여자 조합을 바꾼 독립 세션을 반복 수집한다.
- 다음 세션부터 방 크기, TX/RX/핫스팟 좌표, 높이, 거리, 문 상태를 `meta.json`에 정확히 기록한다.
- 이 세션의 자동 `needs_review` 판정은 8개의 `3x1` 레코드 때문이며, 데이터 전체 실패를 의미하지 않는다.
