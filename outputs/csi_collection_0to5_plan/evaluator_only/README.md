# 평가자 전용 계획·정답 서식

static_answer_key.csv의 planned_people은 목표 인원이며 실제 정답 확인란은 비어 있다. 영상 검수 후 actual_people_after_video_review를 채운다.

dynamic_cue_plan.csv는 예정 행동 신호이며 실제 정답이 아니다. actual_event_log_template.csv에 실제 입장/퇴장 하나마다 행을 추가한다. 시작 인원, 문턱 통과, 출입 후 인원수, 문 닫힘/배치 안정 시각을 기록한다. video_pts_sec와 CSI 상대 시각의 대응을 확인한다. 모르면 빈칸/미확인으로 남긴다.

이 폴더는 모델 학습·추론 입력에 넣지 않는다. 5·6회차의 예측 파일을 먼저 확정한 뒤 정답을 대조한다. 실제 무라벨 시연 8개에는 정답 표가 없다. 이 폴더는 OS 권한으로 잠긴 폴더가 아니라 분리 보관용이다.
