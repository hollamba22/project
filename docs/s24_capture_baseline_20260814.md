# S24+ CSI 수집 링크 기준 상태 - 2026-08-14

이 문서는 다음 실험을 시작하기 전에 현재 환경이 기존 CSI 성공 환경과 달라졌는지 확인하기 위한 기준 문서다.

## 상태 구분

2026-08-14에 확인된 것은 `Minhyuck S24+` 핫스팟을 사용한 네트워크 링크 복구다. 오늘 새 CSI 파일을 성공적으로 수집한 것은 아직 아니다.

현재 판정은 다음과 같다.

```text
S24+ 핫스팟 연결: 성공
RX DHCP: 성공
RX -> 핫스팟 게이트웨이 ping: 성공
TX -> RX ICMP: RX tcpdump에서 관측
RX -> TX ping: 실패
오늘 UDP 수신 검증: 아직 수행하지 않음
오늘 non-zero csi.dat 생성: 아직 수행하지 않음
```

따라서 이 문서는 `CSI 수집 성공 기록`이 아니라 `S24+ 네트워크 복구 기준 상태`다. 실제 CSI 성공의 기준 기록은 `docs/csi_capture_success_conditions_20260710.md`와 2026-07-10 성공 세션 2개다.

## 기존 CSI 성공 기준

| 항목 | 2026-07-10 성공 값 |
| --- | --- |
| 핫스팟 | `Minhyuck S24+` |
| 주파수/채널 | 2437 MHz / 채널 6 |
| 대역폭 | 20 MHz |
| RX 커널 | `4.15.0-213-generic` |
| RX 인터페이스 | `wlp4s0` |
| RX MAC | `00:16:ea:ed:a9:80` |
| RX 드라이버 | patched `iwlwifi` |
| CSI 펌웨어 | `iwlwifi-5000-2.ucode.sigcomm2010` |
| `connector_log` | `1` |
| 트래픽 중 RX rate | 최대 144.4 MBit/s, MCS 15, short GI |
| TX -> RX ping | 0% packet loss |
| 트래픽 | UDP, 100 packets/s, 512 bytes |

검증된 파일은 다음과 같다.

```text
data/raw/session_20260710_145820/csi.dat: 1,843,190 bytes, 4,690 records
data/raw/session_20260710_153743/csi.dat: 1,941,820 bytes, 4,916 records
```

## 2026-08-14 S24+ 복구 스냅샷

기록 시각: `2026-08-14T16:06:06+09:00`

| 항목 | 관측값 | 판정 |
| --- | --- | --- |
| SSID | `Minhyuck S24+` | 일치 |
| BSSID | `be:93:07:3c:38:15` | 동적 값 |
| 주파수/채널 | 2437 MHz / 채널 6 | 일치 |
| RX IPv4 | `172.17.35.22/24` | DHCP 성공, 동적 값 |
| 핫스팟 게이트웨이 | `172.17.35.132` | 동적 값 |
| TX IPv4 | `172.17.35.104` | 이웃 테이블에서 확인 |
| TX MAC | `00:21:6a:6d:30:40` | 이웃 테이블에서 확인 |
| 신호 | 약 -32 dBm | 양호 |
| 절전 | off | 일치 |
| RX -> 게이트웨이 ping | 4/4, 0% loss | 성공 |
| 무선 누적 tx failed | 3 | S25+ 사용 때보다 정상화 |
| TX -> RX ICMP | 16 packets captured, 0 dropped | 수신 인터페이스 도착 확인 |
| RX -> TX ping | 4 transmitted, 0 received | 추가 확인 필요 |

S25+ 사용 중에는 RX 무선 송신 177개 중 173개가 실패하고 DHCP 및 게이트웨이 ping도 실패했다. S24+로 전환한 뒤 게이트웨이 ping이 즉시 성공하고 무선 전송 실패가 크게 줄었다. 따라서 S25+ 핫스팟 설정 또는 SoftAP 호환성은 현재 장비에서 별도 검증 전까지 사용하지 않는다.

## 반드시 같아야 하는 항목

다음 항목이 다르면 CSI 수집을 시작하지 않는다.

```text
kernel = 4.15.0-213-generic
receiver interface = wlp4s0
receiver MAC = 00:16:ea:ed:a9:80
iwlwifi module = /lib/modules/4.15.0-213-generic/updates/iwlwifi.ko
firmware target = /lib/firmware/iwlwifi-5000-2.ucode.sigcomm2010
connector_log = 1
SSID = Minhyuck S24+
frequency = 2437 MHz
channel = 6
power_save = off
```

## 바뀌어도 정상인 항목

핫스팟을 다시 켜면 다음 값은 달라질 수 있다. 과거 값을 강제로 입력하지 말고 DHCP와 현재 링크 값을 사용한다.

```text
AP BSSID
RX IPv4
TX IPv4
게이트웨이 IPv4
네트워크 CIDR
DHCP 임대 시간
idle 상태의 tx/rx bitrate
```

특히 과거 성공 주소 `10.27.219.22`를 강제로 설정하면 안 된다. 현재 핫스팟이 다른 네트워크 대역을 할당하면 통신이 끊긴다.

## 다음 실험 전 자동 점검

수신 PC에서 실행한다.

```bash
cd ~/바탕화면/project
python3 scripts/capture/check_baseline.py
```

송신 PC 주소까지 확인할 때는 다음처럼 실행한다.

```bash
python3 scripts/capture/check_baseline.py --sender-ip <현재_TX_IP>
```

모든 필수 항목이 `PASS`이고 게이트웨이 ping이 성공해야 한다. `--sender-ip`를 사용했다면 TX ping도 성공해야 완전한 양방향 통신으로 기록한다.

## 실제 수집 전 수동 확인

송신 PC에서 현재 RX 주소로 ping을 실행한다.

```bash
iw dev wlp4s0 link
ip -4 addr show wlp4s0
ip route get <현재_RX_IP>
ping -c 4 <현재_RX_IP>
```

수신 PC에서는 동시에 확인한다.

```bash
sudo tcpdump -ni wlp4s0 'icmp or udp port 5005'
```

다음 조건을 모두 만족한 뒤에만 CSI 수집을 시작한다.

1. TX -> RX ping 0% packet loss
2. RX `tcpdump`에서 ICMP request/reply 확인
3. 송신 UDP가 RX `tcpdump`의 port 5005에 표시됨
4. 트래픽 중 `iw dev wlp4s0 station dump`의 `rx bitrate`에 MCS 표시
5. 수집 후 `csi.dat`가 0 byte가 아님
6. parser에서 `code=0xBB` 및 record count 확인

## NetworkManager 프로필 기준

2026-08-14에 다음처럼 정리했다.

```text
Minhyuck S24+ 1: autoconnect yes, priority 100, IPv4 DHCP, power save disabled
Minhyuck S24+: autoconnect no
Galaxy S25+ D8BB: autoconnect no
Galaxy S25+ D8BB 1: autoconnect no
csi-hotspot-rx: autoconnect no
```

S24+ 연결이 끊겼을 때 S25+ 또는 과거 고정 IP 프로필로 자동 전환되지 않도록 유지한다.
