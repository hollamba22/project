# 송신 PC 독립 실행기: 0명 수집 호환 수정 프롬프트

아래 내용을 **송신 PC의 `csi-tx-standalone` 프로젝트에서 실행하는 코딩 도구**에 전달한다.
RX 수정은 이 프로젝트에 반영됐지만 송신 PC에는 아래 변경을 별도로 적용해야 한다.
실행 중인 TX 수집이 있다면 완료한 뒤 수정하고, 수정 후 기존 TX 창을 종료하고 다시 실행한다.

```text
현재 프로젝트는 CSI 송신 PC의 csi-tx-standalone이며 Python 3.6 이상에서 동작한다.
RX 실행기가 이제 num_people=0인 빈 방 수집 설정을 보낸다.
새 프로젝트를 만들거나 다른 구현으로 교체하지 말고 기존 TX를 최소 수정하고 테스트해줘.

1. 프로젝트 지침과 tools/csi_tx_common.py 및 실제 TX 실행기를 읽고,
   RX의 CONFIG와 TX_READY에서 num_people을 검사·전달하는 모든 경로를 확인해줘.
   파일/함수명이 다르면 실제 코드에서 해당 검사를 찾아줘.
2. num_people은 Python int 중 0 이상만 허용하도록 바꿔줘.
   핵심 조건은 type(num_people) is int and num_people >= 0 이다.
   bool(True/False), 음수, 실수(0.0 포함), 문자열("0" 포함), null은 계속 거부해줘.
   조건 실패 시 기존 TxError 등 오류 처리 구조를 유지하고 한국어 안내를 바꿔줘.
3. 숫자 0을 None, 빈 문자열, 1 등으로 바꾸지 마.
   CONFIG 원본 설정을 보존해 TX_READY에 그대로 반환해야 한다.
   num_people을 truthiness 검사나 `value or default`로 지우는 경로가 있으면 수정해줘.
4. 0명이어도 safe_sender.py를 평소처럼 실행해야 한다.
   UDP 5005, 초당 100개, 512바이트, RX 시간+10초 송신 조건을 그대로 유지해줘.
   RX 20분이면 TX는 1210초이며, RX READY/START 전에 송신하면 안 된다.
5. 세션 ID/nonce, 프로토콜 버전과 메시지 필드, PIN, SSID/BSSID/IP, 설정 일치,
   START_ACK, heartbeat, 종료·실패 검사는 변경하거나 생략하지 마.
   Wi-Fi 설정, 절전 설정, 방화벽, sudo 설정, 송신 timeout도 변경하지 마.
   RX의 csi_capture_common.py로 이 프로젝트의 csi_tx_common.py를 덮어쓰지 마.
6. 실제 Wi-Fi/수집을 시작하지 않는 자동 테스트로 다음을 검증해줘.
   - 나머지 필드가 유효한 CONFIG에서 num_people=0,1,2,3,4,5 모두 통과.
   - num_people=-1, true, false, 0.0, 1.5, "0", null 모두 거부.
   - CONFIG -> TX_READY 왕복에서 숫자 0과 다른 설정 필드가 그대로 보존됨.
   - 잘못된 duration/rate/size/session/nonce는 기존대로 거부됨.
   - 기존 송신·취소·연결 종료 테스트도 통과.
7. 수정 파일과 테스트 결과를 한국어로 알려주고 기존 TX 실행 명령을 안내해줘.
   자동으로 실제 수집을 시작하거나 기존 수집 기록을 수정하지 마.
```
