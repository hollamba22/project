# WiFi CSI 기반 실내 인원 수 추정 연구·실험·데이터 인수인계

작성·확인일: **2026-10-07, 한국 시간**  
프로젝트 위치: `/home/mh/바탕화면/project`  
대상: 연구 배경, 수집 환경, 진행한 실험, 보유 데이터, 분석 결과, 재현 절차, 후속 과제

이 문서는 프로젝트 안의 문서·코드·메타데이터·실험 산출물을 대조하여 작성했다. 데이터 수량은 현재 파일 기준이며, 과거 실험 결과는 해당 실험 당시의 입력과 평가 조건을 함께 기록했다. 이번 인수인계 작업에서는 새 현장 수집이나 추가 모델 학습을 수행하지 않았다.

## 1. 인수자가 먼저 알아야 할 현재 상태

**CSI 수집 환경과 오프라인 인원 분류 프로토타입은 구현되어 있다. 다음 단계는 보유 자료의 영상·품질 검수, 추가 인원 클래스 학습, 독립 세션 및 다른 강의실에서의 평가다.**

| 항목 | 현재 확인된 상태 |
|---|---|
| 연구 목적 | 최종 추론에서 카메라 없이 WiFi CSI만으로 실내 인원 수 분류 |
| 연구 범위 변화 | 초기 0~3명 → 수집·검증 범위 0~4명 → 5명 자료도 확보 |
| 수집 공간 | G308, G304 두 강의실 |
| 등록된 원본 세션 | 31개: 학습 후보 15, 실패 이력 13, 검증 전용 2, 자유 평가 후보 1 |
| 학습 후보 수집량 | 실제 CSI 관측 3시간 46분 18.67초, 1,102,726레코드, 저장 특징 13,522구간 |
| 보유 분류 모델 | 0~3명 정규화 SVM, RandomForest, 최근접 중심 모델 |
| 최고 탐색 결과 | 정규화 SVM 633/658 = 96.20%, macro F1 0.9622 |
| 위 결과의 평가 범위 | 9월 13일 같은 4개 세션 안에서 앞부분 학습·뒷부분 시험 |
| 새로운 강의실 성능 | 아직 측정·입증하지 않음 |
| 자유 테스트 | 40분 파일 1개 확보. 영상 정답 CSV는 미작성, CSI·영상 정렬은 미검증 |
| 실시간 인원 표시 | 연속 CSI 수신부터 인원 표시까지 연결한 앱은 아직 구현하지 않음 |

`valid_csi`, `training_candidate`, `use_for_final_training=true`는 최종 검수를 모두 통과했다는 뜻이 아니다. 현재 학습 후보 15개 중 구조화 manifest의 `final_training_allowed=true`는 2개뿐이다. 이 차이를 확인하지 않고 모든 특징 CSV를 학습에 합치면 안 된다.

인수 시 우선 읽을 자료는 이 문서, [9월 14일 분류 분석](docs/csi_people_analysis_20260914.md), [수집 실행기 사용법](docs/csi_desktop_capture_launchers.md), [자유 테스트 설명](docs/csi_free_test_capture.md)이다. 기존 README 및 6~7월 보고서는 당시 상태를 설명하는 자료이며, 현재 데이터 수량이나 구현 상태와 다를 수 있다.

## 2. 연구 배경과 목표

CSI(Channel State Information)는 WiFi 무선 채널을 부반송파 그룹과 안테나 조합별 복소수 값으로 기록한 정보다. 프로젝트는 사람의 존재·위치·자세·움직임에 따라 달라지는 채널 패턴을 특징으로 만들어 인원 수를 분류하는 접근을 사용한다. 현재 분류에는 CSI **진폭** 특징을 사용하며, 위상 보정 특징은 아직 적용하지 않았다.

초기 기획 PDF는 `Person-in-WiFi: Fine-grained Person Perception using WiFi`, `Can WiFi Estimate Person Pose?`, `DensePose From WiFi`, Linux 802.11n CSI Tool을 참고 대상으로 제시한다. 이 프로젝트가 실제로 수행한 문제는 인원 수 분류다. 참고 논문의 자세 추정·신체 분할 모델이나 논문 성능을 재현한 실험은 아니다. 원 기획 자료는 프로젝트 루트의 `WiFi CSI 기반 실내 인원 수 추정 프로젝트.pdf`라는 이름의 PDF다. 실제 파일명에는 분해된 한글 문자가 포함되어 있을 수 있다.

연구 질문은 다음 순서로 확장되었다.

1. Intel 5300에서 실제 CSI 로그를 안정적으로 얻을 수 있는가?
2. 같은 방·수집 조건에서 0·1·2·3명 CSI 특징이 구분되는가?
3. 날짜·사람 위치·가구 배치가 달라져도 분류가 유지되는가?
4. 4명·5명까지 클래스를 확장할 수 있는가?
5. 새로운 방에서는 **빈 방(0명) 기준 자료만** 확보하여 환경을 보정하고 인원수를 추정할 수 있는가?

1번과 2번에 대한 성공 자료를 확보했다. 3번은 제한적인 다른 날짜 비교만 수행했고, 4번은 데이터 확보 후 새 모델 학습·평가가 남아 있다. 5번은 강의실·배치·빈 방 참조 정보를 저장하는 기능까지 구현한 상태이며, 보정 모델과 방 간 평가 결과는 아직 없다.

카메라는 실제 인원수와 행동을 확인하는 **라벨 근거**다. 최종 추론 입력은 CSI 특징이며, 영상·정답 CSV·세션 이름·날짜·강의실 ID를 인원 예측 입력으로 사용하지 않는 것이 연구 목표다.

## 3. 장비, 무선 경로와 수집 환경

### 3.1 실제 데이터 경로

```text
TX PC: 일정한 UDP 트래픽 생성
              │ 동일 핫스팟/AP를 통해 RX로 전송
              ▼
휴대폰 핫스팟/AP ── WiFi 무선 수신 ──> RX PC: Intel 5300
                                          ├─ CSI 로그
웹캠 ──────────────────────────────────────┼─ 라벨 확인 영상
                                          └─ UDP·실행·제어 기록

CSI 원본 → 타임스탬프·순열·스케일 보정 → 구간 특징
        → 품질·라벨 검수 → 분할 → 학습/예측 → 평가
```

이 구성에서 RX가 수신하는 무선 프레임의 송신점은 **핫스팟/AP**다. TX PC는 트래픽 생성기 역할을 한다. 따라서 AP·수신 안테나의 위치와 방향을 반드시 고정·기록해야 한다. 직접적인 TX 안테나→RX 안테나 링크를 사용한 실험으로 설명하면 실제 구성과 달라진다.

### 3.2 성공 환경과 실행기 요구 조건

| 구성 | 기록된 성공 환경 / 현재 코드의 요구 |
|---|---|
| RX 운영체제 | 기존 성공 환경은 Ubuntu 18.04.6 LTS |
| RX 수집 커널 | `4.15.0-213-generic` |
| RX 카드 | Intel Ultimate N WiFi Link 5300, PCI ID `8086:4235` |
| RX 인터페이스 | `wlp4s0` |
| 수정 드라이버 | `/lib/modules/4.15.0-213-generic/updates/iwlwifi.ko` |
| CSI 펌웨어 | `iwlwifi-5000-2.ucode` → `iwlwifi-5000-2.ucode.sigcomm2010` |
| 로깅 옵션 | `/sys/module/iwlwifi/parameters/connector_log` = `1` |
| 검증된 AP 프로필 | S24+ 핫스팟, SSID `Minhyuck S24+`, 채널 6 / 2437 MHz |
| TX 트래픽 | UDP, 100패킷/초, 패킷당 512바이트 |
| 기본 포트 | UDP 데이터 5005, TCP 제어 5006 |
| 웹캠 기록 | 기본 640×480, 10 FPS, VP8/WebM, 음성 없음 |
| 주된 CSI 차원 | 30 부반송파 그룹 × 3 RX × 2 TX |

최신 RX 실행기는 위 수집 커널·드라이버·펌웨어와 특정 RX 인터페이스/MAC, WiFi 절전 off 등을 검사한다. 장비 교체 시 기존 실행기가 그대로 통과한다고 가정하지 말고 [RX 코드](tools/csi_capture_rx_launcher.py)의 사전 검사 조건을 확인해야 한다.

최신 실행기는 실제 연결된 SSID를 자동 탐지한다. 검증된 SSID·채널과 다른 경우 미검증 환경 경고와 별도 승인을 거쳐 진행할 수 있다. 이는 다른 AP에서도 수집 성공이 검증되었다는 뜻은 아니다. 실행기는 WiFi 연결·채널·절전·방화벽 설정을 자동 변경하지 않는다.

과거 문서의 RX IP, TX IP, BSSID, 게이트웨이는 **해당 실험 당시 값**이다. 핫스팟을 다시 켜면 바뀔 수 있으므로 매번 현재 주소를 확인한다. 예를 들어 7월의 `10.27.219.22`를 다음 실험에 그대로 넣지 않는다.

CSI 파싱과 CPU 학습에는 4.15 커널 자체가 필수는 아니다. 다만 설치된 수집 드라이버가 4.15용이므로 다른 커널에서 새 CSI를 수집하려면 별도 호환성 검증이 필요하다. [9월 9일 화면·커널 진단](docs/kernel_display_diagnosis_20260909.md)의 GPU 오류·카드 미인식은 당시 관측이며, 10월 7일 현재 하드웨어 상태를 점검한 결과로 인용하지 않는다.

### 3.3 안테나 거치대

[거치대 설명](antenna_3D_Printer/README.md)과 [OpenSCAD 설계](antenna_3D_Printer/antenna_mount.scad)를 보유한다. 설계상 안테나 3개, 중심 간격 62.5 mm, SMA 고정판 높이 160 mm이며, TX/RX용 세트를 같은 치수로 제작하는 구성이다.

설계 파일이 있다는 사실과 각 세션에서 실제 거치대를 사용했다는 사실을 구분한다. 세션별 `layout.antenna_holder`, 방향 고정 여부와 현장 기록을 확인한다. 7월 10일 자료는 최종 거치대 사용 전 자료이므로 검증 전용으로 남겨 두었다. 안테나를 3개 연결했다고 모든 프레임이 3×3 CSI가 되는 것은 아니다. 현재 자료의 주된 3×2는 안테나/송신 스트림 차원이며 인원수가 아니다.

## 4. 연구·실험 진행 이력

| 시기 | 수행 내용 | 결과와 현재 해석 |
|---|---|---|
| 6월 15일 | Intel 5300, 수정 드라이버·펌웨어·netlink 도구 준비. IBSS/ad-hoc 직접 연결 시험 | ping 성공 시점은 있었으나 CSI는 0바이트. legacy 전송률·HT/MCS 안정성·펌웨어 오류가 원인 후보 |
| 7월 3일까지 | IBSS 및 AP 방식 재시도 | 초기 실패 세션 6개 보존. 현재 장비/드라이버에서 Intel 5300 AP 모드 시도는 지원 오류로 실패 |
| 7월 10일 | 두 PC를 같은 S24+ 핫스팟에 연결, TX→RX UDP 송신 | 첫 유효 CSI 2세션 확보. 4,690 및 4,916레코드. 파서·시각화·메타·초기 학습 파이프라인 검증 |
| 8월 14일 | 핫스팟 네트워크 기준 복구, 수집 코드·구조화 프로토타입 준비 | 네트워크 복구 기준을 문서화. 이 날짜의 세션은 실패 이력이며, 1시간 수집 방법 문서가 실제 1시간 성공 기록을 뜻하지 않음 |
| 9월 2일 | G308에서 3명 짧은 시험 및 4명 20분 수집 | 3명 12.48초/914레코드, 4명 1,202.76초/96,614레코드. 4명은 정상 종료했지만 일부 차원 변경으로 manifest는 검토 필요 |
| 9월 9일 | 커널·화면 문제 진단, RX/TX 동기화 실행기 및 배포 자료 준비 | 수집 환경과 분석 환경을 구분. 실행기 사용 시 최신 코드가 양쪽 PC에 있는지 확인 필요 |
| 9월 13일 | G308에서 0·1·2·3명 각 약 20분 수집 | 정상 4세션 확보. 별도 2명 중단 세션 2개는 실패로 보존 |
| 9월 14일 | 진폭 특징·정규화 특징과 여러 분류기 비교 | 같은 세션 내부 시간 분리 평가에서 정규화 SVM 96.20%. 다른 날짜 비교·혼합 학습·누수 대조 실험 수행 |
| 9월 14일 | 0~5명 반복·블라인드 수집 계획 작성 | 144파일/CSI 12시간 계획은 제안된 후속 프로토콜이며 완료 실험량이 아님 |
| 9월 17일 | 과거 세션의 방 정보를 G308로 보완. G304로 수집 확장 | 강의실·배치·0명 참조와 행동 안내 저장. G304 0명 약 5분, 4명 약 6분 확보 |
| 9월 29일 | G304 `0929G304` 배치에서 0~5명 수집 및 중간 데이터 감사 | 0명 10분, 1·2·4명 각 15분, 3명 30분, 5명 15분. 당시 감사는 완료 후보 14세션 대상 |
| 9월 29일 감사 이후 | 두 번째 5명 15분, 자유 테스트 40분 수집 | 현재 자료에는 추가분이 존재. 15학습 후보 + 1자유 평가 후보로 증가 |
| 10월 7일 | 인수인계용 최신 파일 대조 및 저장 SVM 재실행 | 기존 시험 입력 658개 예측이 저장 결과와 모두 일치. 새 데이터 성능 평가를 수행한 것은 아님 |

6~7월 실패 원인과 당시 조치의 상세 근거는 [중간 보고서](docs/midterm_progress_report.md), [7월 현황 보고서](docs/project_status_report_20260710.md), [최초 성공 조건](docs/csi_capture_success_conditions_20260710.md)에서 확인한다. 초기 실패 원인을 현재 모든 수집 실패의 원인으로 일반화하지 않는다.

## 5. 파일 구조와 메타데이터 읽는 방법

### 5.1 원본 및 파생 자료 위치

```text
project/
├─ data/
│  ├─ raw/<session_id>/            초기 원본·검증·실패 세션
│  │  ├─ csi.dat                   일부 실패 세션은 빈 파일 또는 파일 없음
│  │  └─ meta.json, 실행 기록 등
│  ├─ <N>_people/                  현재 고정 인원 자료: N=0~5
│  │  ├─ CSI_DATA/<session_id>.dat
│  │  ├─ Web_Cam/<session_id>.webm
│  │  └─ META_DATA/<session_id>/
│  │     ├─ meta.json
│  │     ├─ capture_runtime.json
│  │     ├─ session_control.json   동기화 실행기 세션
│  │     ├─ udp_packets.csv
│  │     └─ activity_segments.json 행동 안내를 사용한 세션
│  ├─ structured/<session_id>/
│  │  ├─ window_features.csv
│  │  └─ manifest.json
│  ├─ free_test/                   자유 평가 자료를 별도로 보존
│  │  ├─ CSI_DATA/, Web_Cam/
│  │  ├─ META_DATA/<session_id>/
│  │  │  ├─ meta.json, capture_runtime.json, session_control.json
│  │  │  ├─ udp_packets.csv, activity_segments.json, time_alignment.json
│  │  │  └─ annotations/ground_truth_intervals.csv, README.md
│  │  └─ STRUCTURED/<session_id>/manifest.json, window_features.csv
│  └─ processed/                  초기 병합 CSV와 파이프라인 검증 자료
├─ outputs/
│  ├─ people_count_analysis_20260914/  다중 클래스 분석·모델·예측·그림
│  ├─ dataset/                    과거 인덱스·감사·방 정보 보완 이력
│  ├─ launcher/                   실행기 제어·중단·완료 기록
│  ├─ models/, evaluation/        초기 단일 클래스 파이프라인 검증
│  ├─ csi_visualizations/         초기 2개 CSI 시각화
│  └─ csi_analysis_env/           분석용 Python 패키지
├─ scripts/                       수집·파싱·전처리·학습·평가 코드
├─ tools/                         실행기·드라이버 점검·네트워크 보조 도구
├─ docs/, templates/, tests/
├─ antenna_3D_Printer/            안테나 거치대 설계
└─ third_party/                   CSI Tool 소스·펌웨어·netlink 도구
```

세션에 따라 일부 선택 파일은 없다. `meta.capture.csi_file`과 `video_file`은 메타 폴더에서 해석하는 상대 경로일 수 있으므로, 항상 `META_DATA` 안에 원본이 있다고 가정하지 않는다.

`session_id`가 원본·영상·메타·구조화 특징·예측을 연결하는 키다. 실행기 세션에는 `session_YYYYMMDD_HHMMSS_<임의식별자>` 형태도 있다. 이름의 시각만으로 실제 첫 CSI·UDP·영상 프레임 시각을 결정하지 않는다.

### 5.2 중요한 필드

| 파일 / 필드 | 의미 및 확인 사항 |
|---|---|
| `meta.quality_status` | `valid_csi`는 로그 유효 상태. 라벨·일반화 성능까지 보장하지 않음 |
| `meta.dataset_role` | `training_candidate`, `verification_only`, `failure_history`, `test_candidate` 등을 구분 |
| `meta.use_for_final_training` | 메타에 기록된 학습 사용 요청/정책. 구조화 검수 허용과 함께 확인 |
| `meta.label.num_people` | 고정 수집에서 입력한 인원 라벨. 실제 유지 여부는 영상 검수 필요. 자유 테스트는 `null` |
| `meta.label.label_status` | 고정 인원 완료 자료는 `stable_full_session`; 실패·자유 테스트는 `unknown` |
| `meta.environment.room` | G308 또는 G304. 방 정보 보완 이력의 근거도 함께 보존 |
| `meta.environment.setup_id` | 같은 방 안의 AP/RX·안테나·가구 배치 식별자 |
| `meta.environment.empty_reference_session_id` | 같은 방·배치의 0명 기준 참조. 연결만으로 기준 구간이 검수된 것은 아님 |
| `capture_runtime.json` | 실제 logger 시작·종료, 첫 UDP, 계획·실행 시간, 카메라, 완료/실패 상태 |
| `session_control.json` | 준비·승인·START·행동 지시·TX 종료·양쪽 완료/중단 기록 |
| `activity_segments.json` | 예정 행동 구간. 영상으로 확인한 실제 행동 정답과 구분 |
| `manifest.source` | 원본·메타 경로, 파일 크기, 특징 생성 당시 SHA-256 |
| `manifest.records` | 원본 레코드 수, 수용/차원 제외 수, NIC 기준 실제 관측 시간 |
| `manifest.configuration` | 구간 길이·간격·스케일·예상 차원·타임스탬프 기준 |
| `manifest.quality` | 검토 사유 및 구조화 단계의 `final_training_allowed` |

현재 `meta.json` 스키마 설명은 [메타데이터 기준](docs/meta_json_schema.md)에 있다. 기존 방 정보는 9월 17일 사용자 확인을 근거로 G308로 보완했으며, [보완 보고서](outputs/dataset/room_annotation_20260917/report.json)와 같은 폴더의 `before/`에 원래 메타 백업을 보유한다. 이 백업을 별도 수집 세션으로 집계하지 않는다.

## 6. 현재 보유 데이터: 2026-10-07 파일 기준

### 6.1 역할별 현황

여기서 등록 세션은 원본 위치에 `meta.json`이 존재하는 31개다. 수집 폴더 생성 전 중단된 실행기 로그까지 포함한 총 시도 횟수는 아니다. 시간은 성공 자료의 `manifest.records.observed_duration_sec`, 즉 첫~마지막 CSI의 NIC 상대 시각 기준이다. 중첩된 특징 구간이나 영상 시간을 더해 수집 시간을 늘리지 않았다. 용량은 십진 MB/GB다.

| 역할 | 세션 | CSI 레코드 | CSI 원본 용량 | 저장 특징 구간 | 사용 범위 |
|---|---:|---:|---:|---:|---|
| 학습 후보 | 15 | 1,102,726 | 433.849 MB | 13,522 | 품질·영상 라벨 검수 후 학습/평가 구성 |
| 검증 전용 | 2 | 9,606 | 3.785 MB | 126 | 7월 파서·수집·파이프라인 검증. 최종 학습 제외 |
| 실패 이력 | 13 | 114,461 | 45.211 MB | 0 | 중단·불완전 자료 포함. 정상 완료 통계·학습 제외 |
| 자유 평가 후보 | 1 | 190,409 | 75.095 MB | 2,398 | 영상 정답과 시간 정렬 후 별도 시험. 학습 제외 |
| 전체 원본 기록 | 31 | 1,417,202 | 557.941 MB | 16,046 | 실패 자료까지 포함한 보관량이며 학습 가능량과 다름 |

원본 CSI 파일은 실제 29개다. 실패 13개 중 7개는 빈 CSI 파일, 2개는 CSI 실물 없음, 4개는 부분 CSI가 남아 있다. 부분 CSI가 존재하는 실패 세션을 파일 용량만 보고 성공 세션으로 재분류하지 않는다.

실패 자료의 114,461레코드는 기존 9월 29일 감사 결과를 인용했다. 이번에는 해당 원본 파일 크기가 당시와 같음을 확인했으며, 실패 자료 전체를 다시 파싱한 집계는 아니다.

영상은 학습 후보 15개에 총 1.593 GB, 자유 테스트에 0.294 GB, 실패 이력 4개에 0.172 GB가 있다. 전체 20개 영상은 총 2.060 GB다. 현재 영상 전체의 재생 시간과 전 프레임 인원수 검수를 새로 수행한 집계는 아니다.

### 6.2 학습 후보의 인원·강의실별 현황

| 인원 | 세션 | G308 CSI 관측 시간 | G304 CSI 관측 시간 | CSI 레코드 | 저장 특징 구간 |
|---:|---:|---:|---:|---:|---:|
| 0명 | 3 | 20분 00.54초 | 15분 01.73초 | 172,794 | 2,079 |
| 1명 | 2 | 20분 00.05초 | 15분 00.01초 | 171,792 | 2,096 |
| 2명 | 2 | 20분 00.31초 | 15분 00.10초 | 173,834 | 2,097 |
| 3명 | 3 | 20분 12.58초 | 30분 00.13초 | 230,779 | 3,007 |
| 4명 | 3 | 20분 02.76초 | 21분 00.24초 | 198,165 | 2,445 |
| 5명 | 2 | 없음 | 30분 00.23초 | 155,362 | 1,798 |
| 합계 | 15 | 100분 16.23초 | 126분 02.44초 | 1,102,726 | 13,522 |

G308은 6세션, G304는 9세션이다. G308 3명 자료에는 12.48초 장비 시험 1개가 포함된다. 5명 2개는 모두 G304의 9월 29일 같은 배치 자료다. 두 파일이 있다고 다른 날짜·다른 방 반복 검증까지 확보한 것은 아니다.

**0~4명만** 대상으로 하면 13세션, 3시간 16분 18.44초, 947,364레코드, 저장 특징 11,724구간이다. G308에는 5명 자료가 없으므로 G308만 학습하여 G304의 0~5명 전체를 평가하는 구성은 현재 만들 수 없다.

### 6.3 세션별 학습 후보 목록

세션 ID 링크는 해당 메타데이터를 연다. 원본은 `data/<인원>_people/CSI_DATA/<세션ID>.dat`, 특징과 품질은 `data/structured/<세션ID>/`에서 확인한다. 관측 시간은 반올림했으며 합계는 반올림 전 값으로 계산했다.

| 세션 ID | 방 | 인원 | CSI 관측초 | 레코드 | 특징 구간 | manifest 검수 |
|---|---|---:|---:|---:|---:|---|
| [session_20260902_182349](data/3_people/META_DATA/session_20260902_182349/meta.json) | G308 | 3 | 12.48 | 914 | 10 | 허용 |
| [session_20260902_183751](data/4_people/META_DATA/session_20260902_183751/meta.json) | G308 | 4 | 1,202.76 | 96,614 | 1,187 | 검토 필요 |
| [session_20260913_143135_999cdb09](data/3_people/META_DATA/session_20260913_143135_999cdb09/meta.json) | G308 | 3 | 1,200.10 | 103,326 | 1,199 | 검토 필요 |
| [session_20260913_154543_2e610644](data/1_people/META_DATA/session_20260913_154543_2e610644/meta.json) | G308 | 1 | 1,200.05 | 101,474 | 1,199 | 검토 필요 |
| [session_20260913_161128_29c3bb2f](data/2_people/META_DATA/session_20260913_161128_29c3bb2f/meta.json) | G308 | 2 | 1,200.31 | 103,856 | 1,199 | 검토 필요 |
| [session_20260913_170126_a81112c0](data/0_people/META_DATA/session_20260913_170126_a81112c0/meta.json) | G308 | 0 | 1,200.54 | 101,194 | 1,199 | 검토 필요 |
| [session_20260917_193753_575208a2](data/0_people/META_DATA/session_20260917_193753_575208a2/meta.json) | G304 | 0 | 300.88 | 25,714 | 299 | 허용 |
| [session_20260917_194936_cd512ca7](data/4_people/META_DATA/session_20260917_194936_cd512ca7/meta.json) | G304 | 4 | 360.11 | 29,815 | 359 | 검토 필요 |
| [session_20260929_130615_fca489d4](data/0_people/META_DATA/session_20260929_130615_fca489d4/meta.json) | G304 | 0 | 600.84 | 45,886 | 581 | 검토 필요 |
| [session_20260929_132739_efe51135](data/3_people/META_DATA/session_20260929_132739_efe51135/meta.json) | G304 | 3 | 1,800.13 | 126,539 | 1,798 | 검토 필요 |
| [session_20260929_141310_7e341f3a](data/2_people/META_DATA/session_20260929_141310_7e341f3a/meta.json) | G304 | 2 | 900.10 | 69,978 | 898 | 검토 필요 |
| [session_20260929_143235_e4fb900b](data/1_people/META_DATA/session_20260929_143235_e4fb900b/meta.json) | G304 | 1 | 900.01 | 70,318 | 897 | 검토 필요 |
| [session_20260929_145140_692f1cc4](data/4_people/META_DATA/session_20260929_145140_692f1cc4/meta.json) | G304 | 4 | 900.13 | 71,736 | 899 | 검토 필요 |
| [session_20260929_151447_cfbb436a](data/5_people/META_DATA/session_20260929_151447_cfbb436a/meta.json) | G304 | 5 | 900.10 | 77,604 | 899 | 검토 필요 |
| [session_20260929_154415_fd7afaa2](data/5_people/META_DATA/session_20260929_154415_fd7afaa2/meta.json) | G304 | 5 | 900.13 | 77,758 | 899 | 검토 필요 |

표의 ‘허용’은 구조화 코드의 품질 플래그를 의미하며, 영상 전수 검수나 독립 평가까지 완료했다는 뜻은 아니다.

### 6.4 실패 및 검증 자료

| 세션 | 위치 | 상태 / 보관 이유 |
|---|---|---|
| `session_20260615_203420` | `data/raw/` | 빈 CSI. 초기 IBSS 실패 이력 |
| `session_20260615_203722` | `data/raw/` | 빈 CSI. 초기 IBSS 실패 이력 |
| `session_20260615_205335` | `data/raw/` | 빈 CSI. 초기 IBSS 실패 이력 |
| `session_20260703_151554` | `data/raw/` | 빈 CSI. 초기 연결·수집 실패 이력 |
| `session_20260703_151951` | `data/raw/` | 빈 CSI. 초기 연결·수집 실패 이력 |
| `session_20260703_172027` | `data/raw/` | 빈 CSI. 초기 연결·수집 실패 이력 |
| `session_20260814_150923` | `data/raw/` | CSI 파일 없음. 실패 메타·실행 기록 보존 |
| `session_20260814_151345` | `data/raw/` | CSI 파일 없음. 실패 메타·실행 기록 보존 |
| `session_20260814_151757` | `data/raw/` | 빈 CSI |
| `session_20260902_174112` | `data/raw/` | 부분 CSI 85레코드. 완료 자료로 사용하지 않음 |
| `session_20260902_174312` | `data/raw/` | 부분 CSI 49레코드. 완료 자료로 사용하지 않음 |
| `session_20260913_145724_8ae77998` | `data/2_people/` | 중단 자료 19,402레코드. 인원 라벨 상태 unknown |
| `session_20260913_151206_6122a612` | `data/2_people/` | 중단 자료 94,925레코드. 인원 라벨 상태 unknown |
| `session_20260710_145820` | `data/raw/` | 검증 전용 4,690레코드, 거치대 사용 전 |
| `session_20260710_153743` | `data/raw/` | 검증 전용 4,916레코드, 거치대 사용 전 |

실패 파일은 연구 진행·장애 분석의 근거이므로 삭제하지 않는다. 일부 구간을 복구하려면 영상·완료/중단 기록을 별도로 검수하고 원본 상태를 보존한 새 파생 자료로 관리해야 한다.

### 6.5 자유 테스트 1세션

현재 파일은 [session_20260929_162631_f2a614d4 메타](data/free_test/META_DATA/session_20260929_162631_f2a614d4/meta.json)와 [manifest](data/free_test/STRUCTURED/session_20260929_162631_f2a614d4/manifest.json)에서 확인한다.

- G304, 배치 `0929G304`, 빈 방 참조 `session_20260929_130615_fca489d4`.
- 실제 CSI 관측 2,400.34초, 190,409레코드, 특징 2,398구간.
- 계획은 0~4명 자유 활동·입퇴실이다. 실제 인원수는 아직 영상 검수 전이므로 미상이다.
- `dataset_role=test_candidate`, `num_people=null`, `label_status=unknown`, `use_for_final_training=false`.
- [정답 CSV](data/free_test/META_DATA/session_20260929_162631_f2a614d4/annotations/ground_truth_intervals.csv)는 헤더만 있고 정답 행은 0개다.
- [시간 정렬 JSON](data/free_test/META_DATA/session_20260929_162631_f2a614d4/time_alignment.json)은 `verification_status=unverified`이며 실제 CSI 시작 오프셋과 정렬 오차가 미확정이다.

실행기 화면에 표시한 최대 인원 4명은 실제 정답 4명을 의미하지 않는다. 영상을 보고 구간별 실제 인원수를 작성하고 CSI 시간축으로 변환한 뒤 평가해야 한다. 확인되지 않는 구간에는 임의 정답을 넣지 않는다.

### 6.6 과거 집계와 현재 수량의 차이

[9월 29일 준비 상태 문서](docs/csi_dataset_readiness_20260929.md)와 [당시 감사 요약](outputs/dataset/data_inventory_20260929/summary.json)은 15:40경의 29등록 세션·14완료 후보를 대상으로 한다. 이후 두 번째 5명과 자유 테스트가 추가되어 현재는 31등록 세션·15학습 후보·1자유 평가 후보다.

당시 14세션의 수치 선별 결과인 비중첩 6,097구간, 시작·끝 30초 제외 후 5,721구간은 **그때 자료에 대한 결과**다. 이번 문서의 최신 15학습 후보 전체를 다시 선별한 수치로 인용하지 않는다. 0~4명 자료에는 이후 추가가 없어서 당시 0~4명 집계는 유지된다.

[session_index.json](outputs/dataset/session_index.json)과 CSV는 초기 8개 `data/raw` 세션만 담고 있다. 방 정보는 나중에 보완했지만 전체 세션 목록은 갱신되지 않아 현재 23개를 누락한다. `validate_sessions.py`도 기본적으로 `data/raw` 한 단계만 스캔한다. 최신 인벤토리는 인원별 폴더와 `free_test`를 모두 포함해야 한다. 기존 9월 감사 스크립트도 자유 테스트 폴더는 탐색하지 않는다.

## 7. 전처리, 특징 및 데이터 품질

### 7.1 현재 구조화 처리

[csi_parser.py](scripts/csi/csi_parser.py)는 Intel CSI Tool의 `0xBB` 레코드를 읽고 복소 CSI, `Nrx/Ntx`, RSSI, noise, AGC, rate, 안테나 순열, NIC 시각을 추출한다. Python 행렬 순서는 `[30 부반송파][RX][TX]`다.

[build_structured_dataset.py](scripts/preprocess/build_structured_dataset.py)의 기본 처리는 다음과 같다.

1. NIC의 32비트 마이크로초 `timestamp_low` wrap을 보정하고 첫 CSI부터 상대 시각을 계산한다.
2. RX 안테나 순열을 물리 안테나 순서로 보정한다.
3. RSSI·noise·AGC 등을 사용하는 scaled CSI를 생성한다. noise 미측정 값의 처리 규칙은 코드에 있다.
4. 예상 3 RX × 2 TX와 다른 레코드를 특징 계산에서 제외한다.
5. 2초 구간, 1초 간격으로 진폭 통계와 품질 정보를 생성한다. 기본 최소 패킷 수는 40이다.
6. 원본 해시·구간 수·제외 사유·학습 허용 상태를 manifest에 기록한다.

구조화 CSV는 **107열 = 메타·구간 품질 19열 + 수치 특징 88열**이다. 구간 메타에는 인원 라벨, 시작·끝, 패킷 수, 차원 제외 수, 최대 간격 등이 있다. 모델에는 목적에 맞는 특징 열만 넣는다.

초기 `make_windows.py` 흐름은 패킷 인덱스를 메타의 수집 시간에 선형 매핑하는 방식이다. 현재 NIC 타임스탬프 기반 구조화 흐름과 같은 시간 정확도를 가진 것으로 취급하지 않는다. 9월 분류 분석은 구조화 특징을 사용했다.

### 7.2 분류에 사용한 특징

| 특징 집합 | 열 수 | 구성 |
|---|---:|---|
| `csi_amplitude_82` | 82 | 전체/패킷 진폭 통계 10 + 안테나쌍 6개 × 평균/표준편차 12 + 부반송파 30개 × 평균/표준편차 60 |
| `radio_only_6` | 6 | RSSI A/B/C, total RSS dBm, noise, AGC |
| `all_88` | 88 | 진폭 82 + 무선 상태 6 |
| `normalized_shape_76` | 76 | 안테나쌍·부반송파 통계 72 + 진폭 변동 통계 4를 각 구간 자신의 `amp_mean`으로 나눈 값 |

정규화 76특징의 추가 4개는 `amp_std`, `packet_amp_mean_std`, `packet_amp_diff_abs_mean`, `packet_amp_diff_abs_std`다. SVM의 StandardScaler는 **학습 집합으로만** 계산한다. 이 정규화는 각 구간의 상대 패턴을 강조하는 방식이며, 새 방의 빈 방 기준을 이용한 환경 보정은 아니다.

### 7.3 현재 품질 플래그와 검수 수준

학습 후보 15개 메타는 모두 `valid_csi`, `stable_full_session`, `use_for_final_training=true`다. 그러나 구조화 manifest는 13개가 `needs_review`이고 학습 허용은 false다. 일부 3×1 레코드를 건너뛴 사실만으로도 세션 전체를 검토 대상으로 표시하는 엄격한 정책 때문이다.

학습 후보 전체 1,102,726레코드 중 예상 3×2로 수용된 것은 1,093,128개이고 차원 제외는 9,598개(약 0.87%)다. G308 제외 44개, G304 제외 9,554개다. 방별 기록 상태 차이는 후속 품질 분석 대상이며, 원인 확인 없이 UDP 패킷 손실률이라고 해석하지 않는다.

현재 구조화 허용 true인 자료는 G304의 9월 17일 0명 299구간과 G308의 9월 2일 3명 짧은 시험 10구간, 총 309구간이다. 이 플래그만 엄격히 적용하면 0~4명 전체 분류 모델을 만들 수 없다. 원본을 일괄 승인하기보다 **검수된 구간을 따로 구성**하는 작업이 필요하다.

9월 14일 분석은 구간당 80레코드 이상, 관측 폭 1.5초 이상, 최대 간격 200 ms 이하, 타임스탬프 역전 구간 제외라는 추가 조건을 사용했다. 이것은 해당 분석의 선별 기준이며 보편적인 수집 합격 기준은 아니다.

9월 29일 당시 14세션은 원본 해시·레코드 수·프레임 구조, 복소 행렬 1,299개 표본, CSV의 NaN/무한대, 영상 컨테이너를 검사했다. 영상의 실제 인원·행동을 전 프레임 검수한 것은 아니다. 이번 인수인계에서는 최신 파일 크기와 manifest·CSV 행수를 대조했으며, 추가 5명·자유 테스트까지 포함한 원본 전체 해시·디코딩 및 영상 재검사는 수행하지 않았다.

## 8. 완료한 분석과 성능의 해석

### 8.1 9월 14일 0~3명 분류

입력은 9월 13일 G308의 정상 0·1·2·3명 세션 각 1개다. 품질 통과 후 2초 간격의 비중첩 구간을 선택하고 시작·끝 30초를 제외했다.

- 학습: 각 세션의 30~780초 범위, 총 1,488구간.
- 시험: 840~1170초 범위, 총 658구간.
- 사이에 60초 간격을 두고 원시 시간 구간이 겹치지 않는지 확인했다.
- 시험 인원별 구간 수: 0명 164, 1명 164, 2명 165, 3명 165.

| 특징 / 모델 | 정답 / 시험 구간 | 정확도 | macro F1 |
|---|---:|---:|---:|
| 진폭 82 / 최근접 중심 | 569 / 658 | 86.47% | 0.8646 |
| 진폭 82 / LogisticRegression | 594 / 658 | 90.27% | 0.9053 |
| 진폭 82 / RBF SVM | 597 / 658 | 90.73% | 0.9071 |
| 진폭 82 / RandomForest | 579 / 658 | 87.99% | 0.8824 |
| 전체 88 / LogisticRegression | 599 / 658 | 91.03% | 0.9126 |
| 무선 상태 6 / RBF SVM | 592 / 658 | 89.97% | 0.8957 |
| 정규화 76 / RBF SVM | **633 / 658** | **96.20%** | **0.9622** |
| 정규화 76 / RandomForest | 588 / 658 | 89.36% | 0.8953 |

모델 설정은 RBF SVM `C=1`, `gamma=scale`, `class_weight=balanced`; RF 트리 200개, `min_samples_leaf=3`, `max_features=sqrt`, `class_weight=balanced`이다. 로지스틱 회귀는 `C=1`, 최대 반복 3,000회다. 필요한 모델에는 학습 집합의 StandardScaler를 적용하고 RF에는 적용하지 않는다. 난수 시드는 `20260914`로 고정했다.

정규화 SVM의 혼동행렬은 행이 실제 인원, 열이 예측 인원이다.

| 실제 / 예측 | 0명 | 1명 | 2명 | 3명 |
|---|---:|---:|---:|---:|
| 0명 | 164 | 0 | 0 | 0 |
| 1명 | 0 | 145 | 19 | 0 |
| 2명 | 0 | 0 | 163 | 2 |
| 3명 | 0 | 0 | 4 | 161 |

0명은 모두 구분됐고 주요 오류는 1명을 2명으로 예측한 19구간이다. 같은 세션의 시간 구간은 상관관계가 있으며 인원수와 해당 세션의 자리·자세·가구·무선 상태가 함께 바뀔 수 있다. 이 결과는 분류 가능한 신호가 있다는 근거지만, 새로운 세션·날짜·방의 확정 정확도는 아니다. 여러 후보 중 최고를 선택한 탐색 결과라는 점도 함께 보고해야 한다.

### 8.2 시간 분할과 누수 대조

| 실험 | 분할 조건 | 결과와 해석 |
|---|---|---|
| 뒷부분 학습 → 앞부분 시험 | 420~1170초 학습 1,491개, 30~360초 시험 655개, 사이 60초 | 정규화 SVM 611/655 = 93.28%. 시간 방향에 따른 변동 확인 |
| 5개 시간 블록 교대 시험 | 30~1170초를 228초씩 5블록. 시험 경계 양쪽 30초는 학습에서 제외 | 정규화 SVM 약 90.3~100%, 평균 약 96.0%. 같은 세션 내부 평가 |
| 2초/1초 중첩 구간 무작위 분할 | 학습 3,168개, 시험 1,358개 | 진폭 RF 99.56%. 시험의 92.12%가 학습과 원시 패킷 공유. 일반화 근거 제외 |
| 학습 정답만 섞은 대조군 | 기본 시간 분할 유지, 학습 정답만 무작위 변경 | 진폭 RF 약 17.17%. 올바른 라벨과 특징의 관계를 확인 |

같은 파일에서 생성한 구간 수를 독립 실험 횟수로 세지 않는다. 후속 성능 검증은 목적에 맞게 원본 세션·날짜·강의실을 먼저 나눈 뒤 구간을 만들어야 한다.

### 8.3 다른 날짜 및 혼합 학습

9월 13일 전체 적격 2,266구간으로 학습하여 9월 2일 G308의 실제 3명 자료를 시험한 별도 실험이 있다. 시험 구간은 짧은 세션에서 나온 5개뿐이다. 기본 진폭 RF는 5개 모두 2명, 진폭 SVM은 모두 1명, 정규화 SVM은 모두 3명으로 예측했다. 전처리와 모델에 따라 날짜 변화에 대한 반응이 달랐다는 결과이며, 다른 날짜에서 4개 인원 클래스의 정확도가 100%라는 의미는 아니다.

혼합 실험은 기본 학습 1,488구간에 위 3명 5구간을 추가하고 9월 13일 시험 658구간을 유지했다. 정규화 SVM은 634/658 = 96.35%로 한 구간 더 맞혔고 RF는 변화가 없었다. 이 차이만으로 배치 변화 대응이나 일반적인 혼합 학습 이득을 주장할 수 없다. **저장된 SVM 파일은 기본 633/658 모델이며 혼합 634/658 모델이 아니다.**

0~3명 모델에 실제 4명 자료를 입력하면 0~3 중 하나로 강제 분류한다. 범위 밖 인원이나 “모름”을 감지하는 기능은 구현하지 않았다. 4명·5명 자료가 생겼다는 이유로 기존 모델의 출력 클래스가 자동 확장되지는 않는다.

### 8.4 초기 100% 평가 자료

`outputs/evaluation/baseline_verification_metrics.json`, `model_verification_metrics.json`, `structured_prototype_metrics.json`에 100% 결과가 있다. 모두 7월 10일의 **2명 단일 클래스** 두 세션으로 코드 연결을 확인한 결과다. 59/59 또는 60/60을 맞혔지만 0~3명 분류 정확도로 인용하지 않는다.

일반 [train_baseline.py](scripts/train/train_baseline.py)는 최근접 중심/다수 클래스 모델을 지원한다. 별도 9월 분석 코드에는 SVM·RF·로지스틱 회귀가 구현되어 있다. 초기 문서의 “SVM/RF 미구현”은 현재 별도 분석 코드의 상태와 다르다. 또한 일반 학습 코드는 독립 시험 자료가 없으면 학습 자료 자체를 평가할 수 있으므로 분할 JSON과 실제 시험 세션을 함께 확인해야 한다.

## 9. 실험 재개 및 새 수집 절차

### 9.1 사전 확인

프로젝트 루트에서 실행한다. 수집 직전 현재 커널·카드·드라이버·주소·AP·카메라를 확인하고 AP/RX/안테나/가구 위치를 기록한다.

```bash
cd '/home/mh/바탕화면/project'
uname -r
bash tools/verify_csitool.sh
iw dev wlp4s0 link
ip -4 addr show wlp4s0
cat /sys/module/iwlwifi/parameters/connector_log
python3 scripts/capture/webcam_recorder.py --list-devices
```

[check_baseline.py](scripts/capture/check_baseline.py)는 S24+ 복구 기준과 비교하는 보조 도구다. [8월 기준 문서](docs/s24_capture_baseline_20260814.md)의 주소나 BSSID를 강제로 복원하는 도구로 사용하지 않는다.

### 9.2 RX/TX 동기화 실행

RX PC에서:

```bash
python3 tools/csi_capture_rx_launcher.py
```

TX PC의 최신 프로젝트 사본에서:

```bash
python3 tools/csi_capture_tx_launcher.py
```

1. 두 PC를 같은 핫스팟/AP에 연결한다. RX에서 수집 종류, 실제 강의실, 배치 ID를 입력한다. 기존 G308 자료와 G304 자료를 자동으로 같은 조건으로 취급하지 않는다.
2. RX 화면의 현재 IP와 PIN을 TX에 입력한다. 제어 포트는 기본 5006이다. 변경할 때는 양쪽 실행 명령에 같은 `--control-port <번호>`를 지정한다. 설정 승인, TX→RX ping, READY 교환을 통과한다.
3. RX에서 최종 시작 승인 및 필요한 관리자 인증을 마친다. 카메라·준비·안정화·CSI logger 준비 후 TX 송신을 시작한다.
4. 시간 측정은 첫 **유효 세션 UDP 패킷**부터 시작한다. TX는 RX 수집보다 10초 더 송신한다.
5. RX/TX 양쪽 완료와 후처리가 끝날 때까지 기다린다. 원본 크기·레코드·runtime 완료·제어 완료·영상·manifest를 함께 확인한다.

아이콘 재설치는 [설치 스크립트](tools/install_csi_capture_launchers.sh)에 `rx` 또는 `tx`를 전달하는 방식이다. 프로젝트 이동이나 실행기 변경 후에는 경로와 양쪽 코드 버전을 확인한다. RX 수정이 TX에 이미 복사된 파일까지 자동 반영되지는 않는다.

### 9.3 고정 인원 수집: 종류 1

| 조건 | 최신 실행기 기본 동작 |
|---|---|
| 0명 | 기본 5분, `activity=empty`, 전원 퇴실, 자신의 세션을 빈 방 참조로 기록 |
| 1명 이상 | 기본 앉기 5분 → 서기 5분 → 교대 걷기 5분을 2회, 총 30분 |
| 안내 변경 | 반복 횟수·시간 및 단일 행동 등을 입력으로 변경 가능 |
| 준비/안정화 | 기본 30초/60초. 계획 CSI 수집 시간과 별도 |
| 영상 | 카메라 장치가 있으면 기본 Y, 없으면 기본 N. 영상 없이 진행할 때 별도 경고 승인 필요 |
| 빈 방 연결 | 같은 강의실·배치의 완료된 0명 후보를 선택하거나 미연결로 기록 |

실제 9월 29일 1·2·4·5명 자료는 15분 구성으로 수집했다. 최신 기본값 30분을 과거 모든 세션의 실제 시간으로 적지 않는다.

걷기 안내는 한 사람만 지정 경로를 걷고 나머지는 자리에서 앉아 있는 교대 방식이다. 지시된 행동은 `activity_segments.json`의 **계획**이고 실제 안내 표시 시각은 `session_control.json`의 `GUIDE_CUE`로 확인한다. 동작 수행 여부는 영상으로 검수한다. 0명에서는 운영자도 퇴실해야 하며, 카운트다운만으로 실제 빈 방 상태가 입증되지는 않는다.

### 9.4 자유 테스트: 종류 2

기본 40분, 계획 범위 0~4명, 자유 활동·입퇴실이며 인원·자리·행동 순서를 지정하지 않는다. 카메라와 시각 표시가 필수이고 자료는 `data/free_test`에 별도 저장된다. 실제 인원 라벨은 영상 검수 전까지 미상이며 자동 학습에서 제외된다.

[정답 작성 안내](data/free_test/META_DATA/session_20260929_162631_f2a614d4/annotations/README.md)에 따라 영상 시간의 구간 `[시작, 끝)`별 인원수를 작성한다. 출입과 가림이 있는 구간은 확인 여부를 기록하고, 계획 범위를 넘어 실제 5명이 확인되면 4명으로 잘라 쓰지 않는다. 시험 정답은 예측을 확정한 뒤 평가에만 사용한다.

## 10. 보유 결과 확인과 재현 명령

### 10.1 분석 환경

저장 모델 제작 환경은 Python 3.6.9, NumPy 1.19.5, SciPy 1.5.4, scikit-learn 0.24.2, Matplotlib 3.3.4, joblib 1.1.1, threadpoolctl 3.1.0이다. [버전 목록](scripts/evaluate/requirements-csi-analysis.txt)을 보유하며 패키지는 `outputs/csi_analysis_env/`에 따로 설치되어 있다. 분석/예측 코드가 이 경로를 추가한다. 다른 Python 환경으로 옮길 때는 보유 모델의 로딩 및 동일 예측을 확인한다.

### 10.2 저장 SVM으로 기존 시험 입력 재판별

```bash
cd '/home/mh/바탕화면/project'
PYTHONDONTWRITEBYTECODE=1 python3 scripts/evaluate/predict_people_prototype.py \
  --features-csv outputs/people_count_analysis_20260914/heldout_csi_only.csv \
  --model outputs/people_count_analysis_20260914/people_count_normalized_svm_prototype.joblib \
  --out-csv /tmp/csi_handover_svm_predictions_20261007.csv
```

위 명령은 10월 7일에 실제 실행해 658개 예측이 기존 결과와 모두 같고 정답 633개를 다시 확인했다. 동일한 기존 시험 입력의 재현성 점검이다. 기본 모델은 RF이므로 SVM 경로를 명시했다. 입력 CSV는 정답·날짜·세션 이름·시각을 제거한 진폭 82열이며, SVM bundle이 필요한 76열과 평균 진폭 나눗셈·스케일러를 적용한다.

새 세션 특징도 같은 예측기에 입력할 수 있지만, 예측기 자체가 구간 품질·라벨·동기화·새 방 정확도를 검수해 주지는 않는다. 기존 모델은 0~3명 출력만 지원한다.

### 10.3 원본 파싱과 특징 생성 예시

이미 확보된 G304 1명 세션을 기준으로 원본 요약을 확인한다.

```bash
python3 scripts/csi/csi_parser.py \
  data/1_people/CSI_DATA/session_20260929_143235_e4fb900b.dat --pretty
```

특징을 다시 생성할 때는 기존 결과와 다른 출력 경로를 사용한다.

```bash
python3 scripts/preprocess/build_structured_dataset.py \
  data/1_people/META_DATA/session_20260929_143235_e4fb900b \
  --csi-file ../../CSI_DATA/session_20260929_143235_e4fb900b.dat \
  --output-dir outputs/handover_rebuild_20261007/session_20260929_143235_e4fb900b \
  --csi-mode scaled --expected-nrx 3 --expected-ntx 2 \
  --window-size-sec 2 --stride-sec 1 --min-packets 40
```

위 특징 생성 명령은 재생성 절차의 예시이며 이번 인수인계 작업에서는 실행하지 않았다. 생성 후 원본 해시·행 수·품질 사유를 대조하고, 9월 분석용 추가 선별과 분할은 별도로 적용한다.

### 10.4 전체 분석을 다시 돌릴 때의 주의

[analyze_people_separability.py](scripts/evaluate/analyze_people_separability.py)는 현재 `data/*_people/META_DATA/session_202609*`를 탐색한다. 9월 13일 외의 9월 자료를 이전 날짜 비교로 선택하는 부분이 있어, 현재 그대로 실행하면 9월 17·29일 자료가 당시의 9월 2일 비교에 섞일 수 있다. 기본 출력 경로도 기존 9월 분석 폴더다.

따라서 당시 분석 재현에는 입력 세션을 당시 9월 2일·13일 자료로 고정하고 별도 출력 폴더를 지정하는 작업이 먼저 필요하다. 저장된 split·예측·모델은 그대로 보존한다. 이 문서의 저장 모델 재판별 명령과 전체 재학습을 구분한다.

### 10.5 기존 파생 CSV의 범위

| 파일 | 실제 범위 |
|---|---|
| `data/processed/windows.csv` | 초기 기본 실행 결과, 구간 0개 |
| `windows_verification.csv`, `features_verification.csv` | 7월 검증용 118구간. 최신 다중 인원 데이터셋이 아님 |
| `structured_dataset_prototype.csv` | 7월 검증 전용 2세션을 합친 126구간 |
| `data/structured/` | 학습 후보 15개 + 7월 prototype 2개, 총 17폴더 |
| `data/free_test/STRUCTURED/` | 자유 평가 후보 1개, 학습 자료와 별도 |

[assemble_structured_dataset.py](scripts/dataset/assemble_structured_dataset.py)는 기본적으로 manifest의 라벨·품질·학습 허용 상태를 확인한다. 검토 필요 자료를 강제로 포함하는 옵션이 영상 검수나 최종 품질 승인까지 대신하지 않는다. 현재 전체 0~5명 검수 완료 병합본은 없다.

## 11. 알려진 문제와 후속 작업 시 주의점

| 문제 | 영향 | 인수 후 처리 |
|---|---|---|
| 메타의 시작·종료 시각 오류 | 일부 실행기 세션은 수집 후 메타 생성 시각을 시작으로 기록 | runtime의 logger/첫 UDP 시각과 실제 영상·CSI를 기준으로 정렬 |
| CSI·UDP·영상의 0초가 다름 | 행동·입퇴실 라벨을 잘못된 특징 구간에 붙일 수 있음 | 오프셋과 정렬 오차를 확인하고 기록 |
| 안내 계획과 실제 행동이 다름 | 앉기/서기/걷기 계획을 정답으로 오인할 수 있음 | 영상 검수, 행동 전환·출입 주변 구간 별도 처리 |
| 차원 변경 시 세션 전체 검토 표시 | 대부분의 후보가 자동 학습 허용 false | 검수된 구간 목록과 제외 근거를 별도 산출물로 구성 |
| 독립 반복이 적음 | 같은 세션의 수천 구간으로 일반화가 과대평가될 수 있음 | 날짜·사람·자리·배치를 바꾼 독립 세션 추가 |
| 옛 인덱스·분석 스캔 범위 | 새 자료 누락 또는 역사적 실험 입력 변경 | 원본 3종 경로와 정확한 세션 목록을 포함하는 인벤토리·분할 관리 |
| G308 배치/빈 방 참조 미확인 | G304처럼 같은 배치의 0명 기준이 확보됐다고 가정할 수 없음 | 현장 근거·사진·영상으로 확인하고 미확인은 그대로 기록 |
| 기존 모델은 0~3명 | 4·5명도 0~3 중 하나로 출력 | 확장 모델 재학습 및 범위 밖 입력 처리 평가 |
| 방 간 빈 방 보정 미구현 | 새 방 0명만으로 추정한다는 주장을 할 수 없음 | 보정 규칙 구현과 미사용 시험 방 평가 |

시각 오류의 코드상 원인은 [create_meta.py](scripts/dataset/create_meta.py)의 세션 이름 파싱이 `session_날짜_시각`만 받아 뒤 식별자가 있으면 현재 시각을 사용하는 부분이다. 이름 파싱만 수정해도 GUI를 연 시각과 실제 수집 시작은 다를 수 있다. 9월 13일 약 20분 49초 차이가 분석 문서에 기록되어 있고, 현재 5명 두 세션의 메타 시작 시각도 runtime보다 늦다. 자유 테스트에는 첫 유효 UDP 타이머 기준을 별도로 기록한다.

자유 테스트의 `estimated_timer_zero_video_sec`는 영상 프로세스 시작 기반 추정치다. 실제 첫 영상 프레임과 첫 CSI의 검증된 정렬 값으로 취급하지 않는다. 0명 영상의 준비·퇴실 구간도 자동으로 빈 방 기준에 포함하지 않는다.

## 12. 인수 후 권장 진행 순서와 완료 기준

1. **전체 인벤토리 고정:** 현재 31세션의 원본·영상·메타·manifest를 연결하고 역할별로 구분한다. 실패/검증/자유 평가 자료가 학습에 섞이지 않는 목록을 만든다. 완료 기준은 파일 위치·해시·라벨·방·배치·품질·실행 완료 상태를 추적할 수 있는 목록이다.
2. **영상·시간·구간 품질 검수:** 고정 인원 자료의 실제 인원 유지, 0명 퇴실, 행동 전환, CSI·영상 오프셋을 확인한다. 자유 테스트 정답 CSV와 동기화 검증값을 채운다. 원본과 기존 플래그는 보존하고 채택/제외 구간과 이유를 별도로 기록한다.
3. **0~4명 초기 학습·평가:** 정규화 SVM/RF를 출발점으로 삼되, 원본 세션·날짜·방 단위 분할과 클래스별 시험 존재 여부를 확인한다. accuracy, macro F1, 클래스별 재현율, 혼동행렬, 실제 사용 세션과 구간 수를 함께 저장한다.
4. **빈 방 보정 가설 시험:** G308에서 학습·모델 선택을 마친 뒤, G304의 0명만 보정에 쓰고 G304 1~4명은 시험에 둔다. G304 유인 자료를 특징 선택·튜닝에 사용하지 않는다. G308 배치와 빈 방 참조의 미확인 조건도 결과에 기록한다.
5. **독립 반복과 5명 보강:** G308 5명과 G304 다른 날짜 5명, 방별·인원별 독립 반복을 수집한다. 기존 계획의 방별·인원별 긴 세션 3회는 보강 목표이며 성능을 보장하는 통계적 최소치가 아니다. 일반적인 새 방 성능을 주장하려면 제3 강의실 등 미사용 환경을 추가한다.
6. **실시간 연결:** 검증한 전처리와 저장 모델을 연속 CSI 입력에 연결한다. 예측 간격, 품질 불량·수신 정지·범위 밖 인원 처리 및 실제 변화 반응 시간을 평가한다.

[0~5명 수집 계획](docs/csi_collection_0to5_plan.md)의 6회차·144파일·CSI 12시간, 블라인드 고정 인원/변화 평가와 정확도 목표는 후속 실험 설계다. 현재 완료된 15학습 후보나 자유 테스트 1세션으로 이 계획 전체를 수행했다고 기록하지 않는다. 현재 자유 테스트 40분도 그 계획의 블라인드 변화 평가 전체와 동일한 실험이 아니다.

## 13. 핵심 자료·코드·결과 위치

| 목적 | 확인할 자료 |
|---|---|
| 초기 환경 구축·실패 이력 | [중간 보고서](docs/midterm_progress_report.md), [7월 현황](docs/project_status_report_20260710.md) |
| 첫 CSI 성공 조건 | [성공 조건](docs/csi_capture_success_conditions_20260710.md), [성공/실패 기준](docs/data_success_failure_criteria.md) |
| 네트워크 복구 기준 | [S24+ 기준](docs/s24_capture_baseline_20260814.md), [기준 JSON](docs/s24_capture_baseline_20260814.json) |
| 4명 장시간 수집 근거 | [9월 2일 성공 사례](docs/csi_4people_20min_success_case_20260902.md) |
| 현재 실행기 운영 | [RX/TX 사용법](docs/csi_desktop_capture_launchers.md), [G304 수집 절차](docs/csi_collection_G304_20260917.md), [자유 테스트](docs/csi_free_test_capture.md) |
| 수집 코드 | [RX](tools/csi_capture_rx_launcher.py), [TX](tools/csi_capture_tx_launcher.py), [공통 제어](tools/csi_capture_common.py), [수집 본체](scripts/capture/capture_prototype.py), [행동 안내](tools/csi_activity_guide.py) |
| 영상·라벨 | [영상 설명](docs/webcam_capture.md), [녹화 코드](scripts/capture/webcam_recorder.py), [자유 테스트 기록](scripts/capture/free_test_recording.py) |
| 메타·구조화 처리 | [메타 기준](docs/meta_json_schema.md), [파서](scripts/csi/csi_parser.py), [구조화](scripts/preprocess/build_structured_dataset.py), [병합](scripts/dataset/assemble_structured_dataset.py) |
| 과거 데이터 감사 | [9월 29일 설명](docs/csi_dataset_readiness_20260929.md), [세션 CSV](outputs/dataset/data_inventory_20260929/sessions.csv), [상세 감사](outputs/dataset/data_inventory_20260929/session_audit.json) |
| 분류 분석 설명 | [9월 14일 Markdown](docs/csi_people_analysis_20260914.md), [HTML](docs/csi_people_analysis_20260914.html) |
| 정확한 결과와 분할 | [metrics.json](outputs/people_count_analysis_20260914/metrics.json), [요약 CSV](outputs/people_count_analysis_20260914/metrics_summary.csv), [split](outputs/people_count_analysis_20260914/split_manifest.csv), [예측](outputs/people_count_analysis_20260914/predictions.csv) |
| 저장 모델 | [정규화 SVM](outputs/people_count_analysis_20260914/people_count_normalized_svm_prototype.joblib), [RF](outputs/people_count_analysis_20260914/people_count_rf_prototype.joblib), [최근접 중심](outputs/people_count_analysis_20260914/people_count_centroid_prototype.json) |
| 학습·추론 코드 | [분석](scripts/evaluate/analyze_people_separability.py), [저장 모델 예측](scripts/evaluate/predict_people_prototype.py), [보고서 생성](scripts/evaluate/render_people_analysis_report.py) |
| 재로딩 검증 | [verification.json](outputs/people_count_analysis_20260914/verification.json), [SVM 재판별](outputs/people_count_analysis_20260914/reloaded_svm_predictions.csv) |
| 후속 수집 계획 | [0~5명 계획](docs/csi_collection_0to5_plan.md), [계획 산출물](outputs/csi_collection_0to5_plan/) |
| 안테나 설계 | [거치대 설명](antenna_3D_Printer/README.md), [설계 파일](antenna_3D_Printer/antenna_mount.scad) |

기존 `confusion_matrix.png`와 PDF 그림은 **기본 RF의 87.99% 결과**다. 정규화 SVM 96.20%의 혼동행렬 그림으로 사용하지 않는다. SVM 행렬은 이 문서 8.1 및 결과 JSON/예측 CSV에서 확인한다.

## 14. 문서 갱신 원칙

새 자료나 결과가 생기면 확인 날짜, 포함 세션, 실제 관측 시간, 학습/시험 구간, 모델·전처리 버전, 품질·영상 검수 범위를 함께 갱신한다. 과거 분석 폴더와 원본을 덮어쓰지 않고 새 실험 폴더에 입력 목록·모델·예측·평가를 남긴다. 측정한 결과, 수집 계획, 아직 확인하지 않은 가설을 구분하여 인수자가 같은 조건으로 재현할 수 있게 유지한다.
