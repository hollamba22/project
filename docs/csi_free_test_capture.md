# 0~4명 자유 테스트 수집

2026-09-29 추가. 기본 40분 동안 CSI와 웹캠 영상을 연속 기록한다. 참가자는 0~4명 범위에서
자유롭게 활동하고 입퇴실한다. 시작 인원, 행동 순서, 입퇴실 시각, P/Z 자리는 지정하지 않는다.
실제 인원수는 촬영 후 영상으로 작성하며 현재 실행기는 인원을 자동 판별하지 않는다.

## 실행 순서

`CSI RX 수집` 아이콘을 새로 연다. 현재 아이콘은 이 프로젝트의 실행기를 직접 실행하므로
재설치가 필요 없다. TX PC는 기존 실행기를 사용한다.

```text
[0] 수집 강의실 ID: G304
[0-1] 수집 종류: 2
      1: 기존 고정 인원 학습 수집
      2: 자유 테스트 — 0~4명 자유 활동·입퇴실, CSI+영상, 기본 40분
[1-1] 배치 ID: 0929G304   ← 오늘 수집과 동일한 장비 배치를 유지하는 경우
[1-3] 연결할 0명 기준: 같은 방·배치의 기준 세션 선택 (0은 연결 보류)
[2] 현재 Wi-Fi 확인
[3] 자유 테스트 수집 시간(분): Enter → 40분
[4] 카메라 장치: Enter → /dev/video0
[4-2] 촬영 준비 시간: Enter → 30초
[4-3] 추가 시작 대기: Enter → 0초
```

장비 배치가 달라졌으면 새 배치 ID를 사용한다. 자유 테스트 자체를 빈방 기준으로 자동 등록하지 않는다.
카메라가 없으면 이 모드는 시작하지 않는다. 영상으로 실제 인원을 검수하므로 촬영 전 미리보기에서
출입문과 방 안 사람들이 보이는지 확인한다. 방 안에 있는 조작자·관찰자도 인원에 포함한다.

이후 TX에 RX의 현재 IP/PIN을 입력하고 기존과 같은 연결 확인을 거친 뒤 RX에서 최종 Y를 입력한다.
카메라 준비와 준비 타이머가 끝나면 CSI 기록과 TX 송신이 시작된다. 첫 유효 UDP 패킷부터 40분을 재며
TX는 40분 10초 동안 송신한다. 수집 중 CMD에는 경과/남은 시간, 수신 패킷 수와 자유 활동 안내가 표시된다.
예정된 인원 변화나 행동을 강제하는 안내는 하지 않는다. 종료 후 파일 검사 및 양쪽 완료 확인까지 기다린다.

TX의 기존 설정 화면에 표시되는 **4명은 자유 테스트의 최대 인원 설정**이다.
실제 수집 데이터의 인원 라벨은 미확정 상태로 저장된다. RX↔TX의 기존 제어 스키마와 트래픽 설정은 그대로 사용한다.

## 저장 결과

```text
data/free_test/
  CSI_DATA/<session>.dat
  Web_Cam/<session>.webm
  META_DATA/<session>/
    meta.json
    capture_runtime.json
    session_control.json
    activity_segments.json
    udp_packets.csv
    time_alignment.json
    annotations/
      ground_truth_intervals.csv
      README.md
  STRUCTURED/<session>/
    manifest.json
    window_features.csv
```

정상 완료 시 위 구조로 저장한다. 실패·중단 시 이미 기록된 CSI·영상과 상태를 보존하며,
아직 시작되지 않은 파일 또는 완료되지 않은 후처리 결과는 없을 수 있다.

`meta.json`의 `label.num_people`는 `null`, `label_status`는 `unknown`, `activity`는 `free_test`이다.
`dataset_role=test_candidate`, `use_for_final_training=false`로 기록한다.
특징 CSV의 `num_people`도 빈 값이며 manifest의 `has_trainable_label`과 `final_training_allowed`는 false이다.
기존 `data/0_people`~`data/4_people`와 `data/structured`에 합치지 않는다.
`planned_people_range=[0,4]`는 계획 범위이며 실제 인원 라벨이 아니다. `activity_segments.json`의 한 구간도
자유 테스트 수집 구간만 표시하며 실제 출입이나 동작 정답을 뜻하지 않는다.

## 나중에 실제 인원 그래프 작성

`annotations/ground_truth_intervals.csv`는 열 이름만 있는 빈 서식이다. 영상 검수 후
실제 인원이 일정한 구간을 `[video_start_sec, video_end_sec)`로 한 행씩 작성한다.
두 시각은 **영상 재생 시작을 0초**로 한 초 단위 시각이며, 실제 문턱 통과 때마다 구간을 나눈다.
여러 명이 연속 출입하면 그 사이의 인원수도 기록한다. 검수한 행은 `verified=true`로 표시하고,
가림 등으로 확인 불가능한 구간은 인원을 비워 두고 `notes`에 사유를 남긴다.
계획 범위를 벗어난 상황이 발생해도 실제 확인한 인원을 기록하며 4명으로 잘라 기록하지 않는다.

영상 왼쪽 위에 RX PC의 날짜·시각을 표시한다. `time_alignment.json`에는 카메라 프로세스 시작,
첫 유효 UDP, CSI 로거 시작·종료 및 CSI timestamp 요약을 저장한다. 영상은 준비 시간부터 시작하므로
**영상 0초, 타이머 0초, 첫 CSI 레코드 0초는 서로 다르다.**

`estimated_timer_zero_video_sec`는 프로세스 시작 시각을 이용한 추정값이다. 프레임 수준으로
검증된 동기 오프셋이 아니며 `verified_csi_zero_video_sec`와 오차는 비워 둔다.
실제 인원 그래프는 우선 영상 시각으로 작성하고, 이후 CSI 예측과 비교할 때 오프셋과 오차를 확인한다.
화면에 찍히는 시각은 RX 로컬 시계의 초 단위 표시이며, 정밀한 출입 시각은 영상 프레임으로 구분한다.

## 확인한 범위

기존 고정 인원·자유 테스트를 포함한 자동 테스트 62개를 통과했다. 새 테스트에는
미확정 라벨의 실제 메타데이터/특징 CSV 생성, 학습 제외, 기본 40분, 준비 중 취소,
localhost UDP 수신과 자식 프로세스 정리 검증이 포함된다.
실제 GStreamer 인코더로 합성 영상을 생성해 날짜·시각 표시, WebM 재생 길이와 프레임을 확인했다.
실제 카메라/CSI 장비를 사용한 40분 현장 수집은 이번 변경 검증에서 시작하지 않았다.

하드웨어 없이 화면 안내를 미리 볼 수 있다. 데모는 5분짜리 안내 시간을 100배속으로 재생한다.

```bash
python3 tools/csi_activity_guide.py --activity free_test --speed 100
```
