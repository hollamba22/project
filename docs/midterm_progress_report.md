# WiFi CSI 기반 실내 인원 수 추정 프로젝트 중간 진행 보고서

작성일: 2026-06-15

## 1. 프로젝트 개요

본 프로젝트의 목표는 WiFi Channel State Information(CSI)을 이용하여 실내 공간 내 인원 수를 추정하는 시스템을 구축하는 것이다. WiFi 신호는 사람의 이동, 위치, 자세, 인원 수 등에 따라 다중경로 특성이 변화한다. CSI는 이러한 무선 채널의 세부 변화를 서브캐리어 단위로 제공하므로, RSSI보다 더 정밀하게 실내 환경 변화를 관찰할 수 있다.

현재 단계에서는 최종 인원 수 추정 모델을 학습하기 전, Intel 5300 무선랜카드 기반 CSI 수집 환경을 구축하고 송수신 PC 간 테스트 트래픽을 발생시켜 실제 CSI 로그가 생성되는지 검증하는 것을 우선 목표로 진행하였다.

## 2. 전체 진행 요약

현재까지의 진행 상황은 다음과 같다.

1. 졸업프로젝트 PDF 자료를 확인하고 프로젝트 목표를 정리하였다.
2. 수신 PC(RXPC)의 운영체제, 커널, 무선랜카드 상태를 확인하였다.
3. Intel 5300 CSI Tool을 커널 4.15 환경에 맞게 준비하였다.
4. CSI 수집에 필요한 커널 모듈, 펌웨어, netlink 수집 도구를 빌드 및 설치하였다.
5. CSI 수집/검증/복구를 위한 보조 스크립트를 프로젝트 폴더에 작성하였다.
6. 송수신 PC 간 IBSS/ad-hoc 방식의 직접 WiFi 링크를 구성하여 ping 연결 시험을 수행하였다.
7. ping 연결은 한 차례 성공했으나, CSI 로그 파일의 크기가 증가하지 않는 문제가 확인되었다.
8. 현재 원인은 IBSS 링크가 802.11n HT/MCS 패킷이 아닌 legacy rate로 동작하거나, IBSS 재시도 과정에서 Intel 5300 펌웨어 오류가 발생했기 때문으로 판단된다.

따라서 현재 프로젝트는 “CSI Tool 설치 및 실행 환경 구축”은 완료되었고, “안정적인 CSI 데이터 수집”은 아직 해결 중인 단계이다.

## 3. 실험 장비 및 환경

### 3.1 수신 PC 환경

수신 PC의 현재 환경은 다음과 같다.

- PC 이름: RXPC
- 운영체제: Ubuntu 18.04.6 LTS
- 커널: Linux 4.15.0-213-generic
- 무선랜카드: Intel Corporation Ultimate N WiFi Link 5300
- PCI 장치 ID: 8086:4235
- WiFi 인터페이스명: wlp4s0
- 드라이버: iwlwifi
- CSI Tool 대상 펌웨어: iwlwifi-5000-2.ucode.sigcomm2010

수신 PC는 Intel 5300 CSI Tool에서 요구하는 4.15 계열 커널과 Intel 5300 무선랜카드 조건을 만족한다.

### 3.2 네트워크 구성 방향

초기에는 공유기 없이 송신 PC와 수신 PC를 직접 연결하기 위해 IBSS/ad-hoc 방식을 사용하였다. 실험 목표 구조는 다음과 같다.

```text
송신 PC Intel 5300: 192.168.70.1
        |
        | WiFi ad-hoc / IBSS / 2.4 GHz channel 1
        v
수신 PC Intel 5300: 192.168.70.2 + CSI logging
```

인터넷 연결은 USB 테더링으로 유지하고, Intel 5300 WiFi 인터페이스는 CSI 실험용 링크로 분리하여 사용하는 방향으로 테스트하였다.

## 4. CSI Tool 환경 구축 진행 내용

### 4.1 CSI Tool 소스 및 보조 도구 준비

프로젝트 폴더 안에 CSI Tool 관련 소스와 보조 도구를 다음 위치에 구성하였다.

- CSI Tool 커널 모듈 소스: `third_party/linux-80211n-csitool-csitool-4.15`
- CSI Tool supplementary 도구: `third_party/linux-80211n-csitool-supplementary-master`
- netlink 수집 도구: `third_party/linux-80211n-csitool-supplementary-master/netlink/log_to_file`

빌드 결과 다음 커널 모듈이 생성되었다.

- `iwlwifi.ko`
- `iwldvm.ko`
- `iwlmvm.ko`

또한 CSI 로그를 파일로 저장하는 `log_to_file` 실행 파일도 빌드되었다.

### 4.2 커널 모듈 설치 및 펌웨어 설정

빌드한 CSI 지원 `iwlwifi` 모듈을 다음 경로에 설치하였다.

```text
/lib/modules/4.15.0-213-generic/updates/iwlwifi.ko
```

펌웨어는 Intel 5300 CSI Tool에서 사용하는 SIGCOMM 2010 펌웨어로 연결하였다.

```text
/lib/firmware/iwlwifi-5000-2.ucode -> iwlwifi-5000-2.ucode.sigcomm2010
```

또한 CSI 로깅을 켜기 위해 `connector_log=0x1` 옵션을 적용하였다. 현재 런타임에서 다음 값이 확인되었다.

```text
/sys/module/iwlwifi/parameters/connector_log = 1
```

이는 CSI 로그를 netlink connector로 전달할 수 있는 드라이버 옵션이 활성화되었음을 의미한다.

### 4.3 검증 결과

`tools/verify_csitool.sh`를 통해 다음 항목을 검증하였다.

- 현재 커널이 4.15.0-213-generic인지 확인
- Intel 5300 PCI 장치 인식 확인
- 로드된 `iwlwifi` 모듈이 `/updates/iwlwifi.ko` 경로에서 로드되는지 확인
- 빌드된 CSI 모듈의 vermagic이 현재 커널과 일치하는지 확인
- `connector_log` 파라미터 존재 및 값 확인
- CSI 펌웨어 파일 및 심볼릭 링크 확인
- WiFi 인터페이스 `wlp4s0` 확인
- `log_to_file` 실행 파일 존재 확인
- 커널 로그에서 `iwlagn: connector callback registered` 메시지 확인

결과적으로 CSI Tool 드라이버 설치 자체는 정상적으로 완료된 것으로 판단된다.

## 5. 작성된 프로젝트 스크립트

현재 프로젝트 폴더에는 CSI 실험을 반복하기 위한 스크립트가 작성되어 있다.

### 5.1 설치 및 검증 스크립트

- `tools/install_csitool.sh`
  - CSI 지원 커널 모듈 빌드
  - `/lib/modules/.../updates` 경로로 모듈 설치
  - CSI 펌웨어 설치
  - `connector_log=0x1` 설정
  - `iwlwifi` 모듈 재로드

- `tools/verify_csitool.sh`
  - 커널, PCI 장치, 드라이버, 펌웨어, connector_log, 인터페이스, 로그 도구 상태를 한 번에 점검

- `tools/reload_csitool.sh`
  - `iwlwifi`, `iwldvm`, `iwlmvm`, `mac80211` 모듈을 내렸다가 `connector_log=0x1`로 다시 로드

### 5.2 수집 및 네트워크 설정 스크립트

- `tools/start_csi_logging.sh`
  - `log_to_file`을 실행하여 `data/raw/session_YYYYMMDD_HHMMSS/csi.dat` 형태로 CSI 로그 저장

- `tools/setup_ibss.sh`
  - 지정한 인터페이스를 IBSS/ad-hoc 모드로 전환
  - SSID, 주파수, IP 주소 설정

- `tools/reset_wifi_managed.sh`
  - 실험 후 WiFi 인터페이스를 일반 managed 모드로 복구

### 5.3 송신 트래픽 발생 스크립트

- `scripts/sender/safe_sender.py`
  - UDP 또는 TCP 트래픽을 일정 시간, 일정 rate로 송신
  - CSI 수집 테스트용 트래픽 발생에 사용
  - 기본 권장 방식은 UDP 송신

예상 사용 예시는 다음과 같다.

```bash
python3 scripts/sender/safe_sender.py --target 192.168.70.2 --mode udp --duration 60 --rate 20 --size 512
```

## 6. 송수신 링크 테스트 진행 내용

### 6.1 IBSS/ad-hoc 설정

공유기 없이 송수신 PC를 직접 연결하기 위해 IBSS/ad-hoc 네트워크를 구성하였다.

수신 PC 설정값은 다음과 같다.

- 인터페이스: wlp4s0
- IP 주소: 192.168.70.2/24
- SSID: csi_ibss
- 주파수: 2412 MHz
- 채널: 1
- 대역폭: HT20
- 고정 BSSID: 02:11:22:33:44:55

수신 PC에서 최종적으로 다음 상태가 확인되었다.

```text
Interface wlp4s0
type IBSS
ssid csi_ibss
channel 1 (2412 MHz), width: 20 MHz
inet 192.168.70.2/24
```

### 6.2 연결 확인

송신 PC와 수신 PC 사이에서 한 차례 ping 테스트가 성공하였다.

```text
4 packets transmitted, 4 received, 0% packet loss
```

이 결과는 송수신 PC가 동일한 IBSS 네트워크에 들어와 IP 레벨 통신이 가능했던 시점이 있었음을 의미한다.

### 6.3 CSI 로그 수집 시도

수신 PC에서 `log_to_file`을 실행하여 CSI 로그를 저장하도록 구성하였고, 송신 PC에서 UDP 트래픽을 전송하였다. 그러나 생성된 CSI 파일은 다음과 같이 0 byte로 남아 있었다.

```text
data/raw/session_20260615_203420/csi.dat 0 bytes
data/raw/session_20260615_203722/csi.dat 0 bytes
```

따라서 현재까지는 실제 CSI 패킷이 파일로 저장되는 데 성공하지 못했다.

## 7. 현재 발견된 문제와 원인 분석

### 7.1 CSI 파일이 증가하지 않는 문제

CSI Tool은 일반 legacy WiFi 패킷이 아니라 802.11n HT/MCS 기반 패킷에 대해 CSI 정보를 생성한다. 하지만 테스트 중 `iw station dump`에서 확인된 전송률은 다음과 같이 legacy rate였다.

```text
tx bitrate: 54.0 MBit/s
rx bitrate: 54.0 MBit/s
```

또는 이전 시점에는 2.0 MBit/s로 확인되었다. 이는 802.11n HT MCS rate가 아니라 legacy 802.11a/g 계열 rate에 해당한다. 따라서 ping이나 UDP 패킷이 송수신되더라도 CSI 로그가 생성되지 않을 수 있다.

### 7.2 IBSS 링크 안정성 문제

IBSS 모드에서 HT20 및 MCS 설정을 강제로 시도했으나, 이후 연결이 불안정해졌다. 현재 수신 PC에서 송신 PC 주소인 `192.168.70.1`로 ping을 수행하면 다음 상태가 확인된다.

```text
4 packets transmitted, 0 received, 100% packet loss
Destination Host Unreachable
```

또한 최근 커널 로그에는 Intel 5300 펌웨어의 microcode 오류가 기록되었다.

```text
Microcode SW error detected
SYSASSERT
BUG_ON, Stop restarting
```

이는 반복적인 IBSS 재설정 또는 HT-IBSS 조건에서 Intel 5300 드라이버/펌웨어가 불안정해졌을 가능성을 보여준다.

## 8. 현재 달성한 성과

현재까지 달성한 주요 성과는 다음과 같다.

1. Intel 5300 CSI Tool 구동에 필요한 커널 버전과 하드웨어 조건을 확인하였다.
2. CSI 지원 `iwlwifi` 커널 모듈을 빌드하고 설치하였다.
3. SIGCOMM 2010 CSI 펌웨어를 설치하고 펌웨어 링크를 구성하였다.
4. `connector_log=1` 상태를 확인하여 CSI 로깅 옵션이 활성화되었음을 검증하였다.
5. `log_to_file` 수집 도구를 빌드하였다.
6. CSI 수집, 검증, 재로드, IBSS 설정, 복구를 위한 반복 실험용 스크립트를 작성하였다.
7. 송수신 PC 간 IBSS 네트워크 연결을 구성하고 ping 성공 사례를 확보하였다.
8. CSI 파일이 생성되지 않는 원인이 단순 파일 경로 문제가 아니라 HT/MCS 패킷 생성 또는 IBSS 안정성 문제에 가깝다는 점을 확인하였다.

## 9. 미완료 항목

아직 완료되지 않은 항목은 다음과 같다.

1. 실제 CSI가 들어 있는 non-zero `csi.dat` 파일 확보
2. 송수신 링크를 안정적으로 802.11n HT/MCS rate로 유지
3. 실험 조건별 데이터셋 수집
4. CSI 파싱 및 전처리 코드 작성
5. 인원 수 라벨링 체계 수립
6. 인원 수 추정 모델 학습 및 평가

현재 가장 중요한 다음 목표는 “수신 PC에서 `csi.dat` 파일 크기가 증가하는 첫 성공 사례 확보”이다.

## 10. 향후 진행 계획

다음 단계는 CSI 수집 경로를 안정화하는 것이다.

1. 수신 PC 재부팅 또는 CSI 모듈 재로드를 통해 Intel 5300 펌웨어 오류 상태를 초기화한다.
2. IBSS/ad-hoc 방식을 다시 시도하되, 송신 PC와 수신 PC가 같은 SSID, 같은 채널, 같은 BSSID, 같은 MCS 설정을 사용하는지 확인한다.
3. `iw dev wlp4s0 station dump`에서 `rx bitrate` 또는 `tx bitrate`가 `MCS` 형태로 표시되는지 확인한다.
4. MCS rate가 유지될 때만 `log_to_file`을 실행하고 UDP 트래픽을 발생시킨다.
5. 그래도 IBSS에서 CSI가 생성되지 않으면, 공유기 또는 AP 기반 managed 모드로 전환하여 802.11n 링크를 먼저 안정화한다.
6. non-zero CSI 로그가 확보되면, 사람 수 0명, 1명, 2명, 3명 등 조건별 반복 수집을 시작한다.
7. 수집된 CSI를 파싱하고 amplitude/phase 기반 특징을 추출한다.
8. SVM, Random Forest, CNN/LSTM 등 후보 모델을 비교하여 실내 인원 수 추정 성능을 평가한다.

## 11. 중간 결론

본 프로젝트는 현재 CSI 기반 인원 수 추정 모델 개발 전 단계인 CSI 수집 환경 구축을 진행 중이다. 수신 PC의 커널, Intel 5300 무선랜카드, CSI Tool 드라이버, 펌웨어, connector_log 설정, log_to_file 도구는 정상적으로 준비되었다. 또한 실험 반복을 위한 설치/검증/수집/복구 스크립트도 작성되었다.

다만 실제 CSI 로그 파일은 아직 0 byte 상태이며, 이는 송수신 링크가 802.11n HT/MCS 패킷을 안정적으로 사용하지 못했기 때문으로 판단된다. IBSS/ad-hoc 연결은 ping 성공 사례가 있었지만, CSI 수집에는 충분히 안정적이지 않았다. 따라서 다음 단계에서는 WiFi 링크를 HT/MCS 상태로 안정화하고, non-zero CSI 로그를 확보하는 것을 최우선 과제로 진행할 예정이다.
