# CSI 수집 성공 조건 - 2026-07-10

이 문서는 WiFi CSI 기반 실내 인원 수 추정 프로젝트에서 처음으로 재현 가능하게 CSI 수집에 성공한 조건을 기록한다.

## 결과

2026-07-10에 CSI 수집이 재현 가능하게 성공했다.

비어 있지 않은 CSI 파일 2개가 생성되었다.

| 세션 | 파일 크기 | CSI 레코드 수 | 상태 |
| --- | ---: | ---: | --- |
| `session_20260710_145820` | 1.8 MB | 4690 | 성공 |
| `session_20260710_153743` | 1.9 MB | 4916 | 성공 |

레코드는 다음 명령으로 검증했다.

```bash
third_party/linux-80211n-csitool-supplementary-master/netlink/parse_log data/raw/session_20260710_145820/csi.dat | head -10
third_party/linux-80211n-csitool-supplementary-master/netlink/parse_log data/raw/session_20260710_153743/csi.dat | head -10
```

정상 출력 예시는 다음과 같다.

```text
Entry size=393, code=0xBB
Entry size=393, code=0xBB
...
```

`code=0xBB`는 Intel 5300 CSI Tool에서 CSI/beamforming 레코드를 의미한다. 따라서 위 두 파일은 실제 CSI 로그로 판단할 수 있다.

## 수신 PC 조건

수신 PC는 CSI를 실제로 수집하는 장비다.

필수 상태는 다음과 같다.

```text
hostname: RXPC
kernel: 4.15.0-213-generic
interface: wlp4s0
driver: patched iwlwifi
connector_log: 1
CSI logging tool: third_party/linux-80211n-csitool-supplementary-master/netlink/log_to_file
```

확인된 드라이버 상태는 다음과 같다.

```text
loaded iwlwifi module:
/lib/modules/4.15.0-213-generic/updates/iwlwifi.ko

firmware:
iwlwifi-5000-2.ucode -> iwlwifi-5000-2.ucode.sigcomm2010

runtime connector_log:
1
```

성공 당시 수신 PC의 WiFi 상태는 다음과 같다.

```text
SSID: Minhyuck S24+
AP BSSID: 92:91:d6:68:b5:14
frequency: 2437 MHz
channel: 6
bandwidth: 20 MHz
RX IP: 10.27.219.22/24
signal: 약 -40 dBm ~ -42 dBm
관측된 rx bitrate: 최대 144.4 MBit/s MCS 15 short GI
```

중요 조건은 트래픽이 흐르는 동안 `rx bitrate`가 MCS rate로 표시되는 것이다. CSI는 수신 PC가 실제로 받은 패킷에서 생성된다.

## 송신 PC 조건

송신 PC는 수신 PC로 안정적인 트래픽을 보내는 역할만 수행한다.

필수 상태는 다음과 같다.

```text
same hotspot/AP: Minhyuck S24+
network: 10.27.219.0/24
target receiver IP: 10.27.219.22
TX -> RX ping: 0% packet loss
```

송신 PC는 CSI 드라이버가 반드시 필요하지 않다. 송신 PC의 핵심 역할은 트래픽 생성이다.

## 네트워크/AP 조건

성공한 구성에서는 휴대폰 핫스팟을 AP로 사용했다.

```text
AP/hotspot: Minhyuck S24+
channel: 6
frequency: 2437 MHz
band: 2.4 GHz
nmcli 표시 기준 보안: open/no security
```

수집 중 반드시 고정해야 하는 항목은 다음과 같다.

- 송신 PC 위치 고정
- 수신 PC 위치 고정
- 핫스팟 휴대폰 위치 고정
- 안테나 방향 고정
- 큰 물체, 문 상태, 방 배치 고정

현재 실험 공간은 WiFi 간섭이 많은 환경이다.

```text
room_has_wifi_rack: true
nearby_aps: many
same_channel_interference: channel 6에 여러 AP 존재
environment_note: high_wifi_interference
```

이 환경에서도 파일 수집 자체는 가능하지만, 실험 환경 조건으로 반드시 기록해야 하며 보고서에서는 한계점으로 다루어야 한다.

## 성공 명령 순서

### 1. 수신 PC 사전 확인

수신 PC에서 실행한다.

```bash
cd ~/바탕화면/project
uname -r
cat /sys/module/iwlwifi/parameters/connector_log
iw dev wlp4s0 link
ip -4 addr show wlp4s0
iw dev wlp4s0 station dump
```

정상 기준은 다음과 같다.

```text
uname -r -> 4.15.0-213-generic
connector_log -> 1
wlp4s0 connected to Minhyuck S24+
RX IP -> 10.27.219.22/24
station dump -> 트래픽 중 rx bitrate에 MCS가 포함됨
```

### 2. 송신 PC ping 확인

송신 PC에서 실행한다.

```bash
iw dev wlp4s0 link
ip -4 addr show wlp4s0
ping -c 4 10.27.219.22
```

정상 기준은 다음과 같다.

```text
4 packets transmitted, 4 received, 0% packet loss
```

이 ping 테스트가 성공하기 전에는 CSI 로깅을 시작하지 않는다.

### 3. 수신 PC에서 CSI 로깅 시작

수신 PC의 첫 번째 터미널에서 실행한다.

```bash
cd ~/바탕화면/project
bash tools/start_csi_logging.sh
```

정상 출력 예시는 다음과 같다.

```text
Writing CSI to /home/mh/바탕화면/project/data/raw/session_YYYYMMDD_HHMMSS/csi.dat
Stop with Ctrl-C.
```

이 터미널은 계속 켜둔다.

### 4. 송신 PC에서 트래픽 생성

송신 PC에서 실행한다.

```bash
cd ~/바탕화면/projects
python3 scripts/sender/safe_sender.py --target 10.27.219.22 --mode udp --duration 60 --rate 100 --size 512
```

60초 송신 명령이 끝날 때까지 기다린다.

### 5. 수신 PC에서 로깅 종료

송신이 끝난 뒤 수신 PC의 로깅 터미널로 돌아가 다음을 누른다.

```text
Ctrl-C
```

### 6. 수신 PC에서 파일 확인

수신 PC에서 실행한다.

```bash
cd ~/바탕화면/project
ls -lh data/raw/session_*/csi.dat
```

정상 기준은 다음과 같다.

```text
최신 csi.dat가 0 bytes가 아니라 MB 단위여야 함
```

그 다음 CSI 레코드를 검증한다.

```bash
third_party/linux-80211n-csitool-supplementary-master/netlink/parse_log data/raw/<latest_session>/csi.dat | head -10
```

정상 출력은 다음과 같다.

```text
Entry size=393, code=0xBB
```

## 현재 raw 데이터 상태

초기 실패 파일은 아직 남겨두며 학습에는 사용하지 않는다.

```text
data/raw/session_20260615_203420/csi.dat 0 bytes
data/raw/session_20260615_203722/csi.dat 0 bytes
data/raw/session_20260615_205335/csi.dat 0 bytes
data/raw/session_20260703_151554/csi.dat 0 bytes
data/raw/session_20260703_151951/csi.dat 0 bytes
data/raw/session_20260703_172027/csi.dat 0 bytes
```

성공한 수집 파일은 다음과 같다.

```text
data/raw/session_20260710_145820/csi.dat 1843190 bytes
data/raw/session_20260710_153743/csi.dat 1941820 bytes
```

나중에 유효한 CSI 파일만 고를 때는 다음 명령을 사용한다.

```bash
find data/raw -name csi.dat ! -size 0 -print
```

## 라벨 관련 주의사항

CSI 파일 자체에는 사람 수 라벨이 들어 있지 않다. 사람 수는 실험 당시 조건을 보고 별도로 기록해야 한다.

첫 번째 성공 파일은 60초 수집 구간 전체 동안 방 안에 사람이 2명 있었다면 `num_people=2`로 라벨링할 수 있다.

```text
session_20260710_145820: 전체 세션 동안 사람이 2명 있었다면 num_people=2
```

현재 성공 파일들은 안테나 거치대 완성 전에 수집된 데이터이므로 최종 학습 데이터가 아니라 다음 용도로 사용한다.

```text
purpose: 수집 검증, 파서 개발, 시각화 개발
not purpose: 최종 모델 학습/평가
```

최종 데이터셋 수집은 3D 프린터로 만든 안테나 거치대가 완성되고 TX/RX/핫스팟/안테나 위치가 고정된 뒤 시작한다.
