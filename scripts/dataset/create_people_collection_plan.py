#!/usr/bin/env python3
"""Build a calendar-free, 12-hour acquisition plan for 0-5 people.

Writes planning artifacts only. Does not capture data or change the logger.
Participants are anonymous P1-P5. Hidden evaluation answers are kept separately
from the inference manifest; the folder separation is organizational, not ACLs.
"""
import csv
import json
from collections import Counter
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'outputs/csi_collection_0to5_plan'
DOC = ROOT / 'docs/csi_collection_0to5_plan'
PEOPLE = ['P1', 'P2', 'P3', 'P4', 'P5']
BASE_ORDERS = [[0, 1, 2, 3, 4], [0, 2, 4, 1, 3],
               [0, 4, 3, 2, 1], [0, 3, 1, 4, 2]]
COUNT_SEED = [0, 1, 5, 2, 4, 3]
SET_START = [15, 70, 138, 193]  # Relative minutes, not clock/calendar times.
DYNAMIC = [[0, 1, 2, 3, 4, 5], [5, 4, 3, 2, 1, 0],
           [0, 3, 1, 5, 2, 4], [4, 2, 5, 1, 3, 0],
           [1, 4, 0, 5, 3, 2], [2, 5, 3, 0, 4, 1]]
PHASE_NAME = {
    'train': '학습', 'validation': '모델 선택', 'blind_static': '정답 비공개 고정 인원 평가',
    'blind_dynamic': '정답 비공개 인원 변화 평가', 'unlabeled': '실제 무라벨 시연'}


def hm(minutes):
    return '{:02d}:{:02d}'.format(minutes // 60, minutes % 60)


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def write_csv(path, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def order_for(set_index):
    base = BASE_ORDERS[(set_index // 5) % 4]
    return [PEOPLE[(p + set_index % 5) % 5] for p in base]


def positions_for(set_index):
    offset = (2 * set_index + set_index // 5) % 5
    return {p: 'Z{}'.format((i + offset) % 5 + 1) for i, p in enumerate(PEOPLE)}


def change_text(previous, current):
    if previous is None:
        return '이전 시연 종료 후 전원 퇴실 확인. ' + ('전원 밖에서 대기' if not current else ', '.join(current) + ' 입장')
    enter = [p for p in current if p not in previous]
    leave = [p for p in previous if p not in current]
    return ('퇴실: ' + (', '.join(leave) or '없음') + ' / 입장: ' + (', '.join(enter) or '없음') +
            ' / 유지: ' + (', '.join(p for p in current if p in previous) or '없음'))


def walking_text(group, seconds=300):
    if not group:
        return '전원 퇴실. 의자·물건은 그대로 유지.'
    if seconds == 300:
        roles = ['{}~{}초 {}'.format(i * 60, (i + 1) * 60, group[i % len(group)]) for i in range(5)]
        return '걷는 사람: ' + '; '.join(roles) + '. 나머지는 본인 Z 의자에 앉음. 인원수는 유지.'
    return '{}만 W0↔W1을 천천히 왕복하고 나머지는 본인 Z 의자에 앉음.'.format(group[0])


def make_plan():
    rows, sets, static_keys, event_plans = [], [], [], []
    for round_no in range(1, 7):
        layouts = ['A', 'B'] if round_no % 2 else ['B', 'A']
        previous = []
        for set_no in range(1, 5):
            index = (round_no - 1) * 4 + set_no - 1
            layout = layouts[(set_no - 1) // 2]
            people_order = order_for(index)
            zones = positions_for(index)
            counts = [(x + index % 6) % 6 for x in COUNT_SEED]
            moving = set_no % 2 == 0
            quiet = '앉아서 유지' if round_no in (1, 3) else '서서 유지' if round_no in (2, 4) else '전반 150초 앉기 / 후반 150초 서기'
            activity = '1명씩 교대 걷기' if moving else quiet
            if round_no == 6:
                activity = '변화 평가 2회 + 무라벨 4회' if moving else '인원 변화 평가 6회'
            set_trials = []
            if set_no in (1, 3):
                previous = []  # All leave while changing or checking the layout.
            for capture_no in range(1, 7):
                trial_id = 'R{:02d}_S{:02d}_C{:02d}'.format(round_no, set_no, capture_no)
                slot = SET_START[set_no - 1] + (capture_no - 1) * 8
                phase = 'train' if round_no <= 3 else 'validation' if round_no == 4 else 'blind_static'
                row = dict(trial_id=trial_id, round=round_no, set=set_no, capture=capture_no,
                           layout=layout, phase=phase, activity=activity,
                           slot_relative='T+{}~{}'.format(hm(slot), hm(slot + 8)),
                           record_relative='T+{}~{}'.format(hm(slot + 2), hm(slot + 7)),
                           recording_seconds=300, target_count=None, participants=[],
                           positions='', entry_exit='', instructions='', stages=[],
                           source_label='unknown' if round_no >= 5 else '',
                           video=True, status='미수집', actual_session_id='')
                if round_no <= 5:
                    n = counts[capture_no - 1]
                    group = people_order[:n]
                    row.update(target_count=n, participants=group,
                               positions=', '.join('{}→{}'.format(p, zones[p]) for p in group) or '전원 퇴실',
                               entry_exit=change_text(previous, group),
                               source_label=n if round_no <= 4 else 'unknown')
                    row['instructions'] = ('전원 퇴실. 가구와 물건은 그대로.' if n == 0 else
                                           walking_text(group) if moving else quiet + '. 사람별 지정 Z 유지.')
                    previous = group
                    if round_no == 5:
                        static_keys.append(dict(trial_id=trial_id, planned_people=n,
                                                actual_people_after_video_review='', video_verified='', notes=''))
                elif not moving or capture_no <= 2:
                    row['phase'] = 'blind_dynamic'
                    profile = DYNAMIC[capture_no - 1]
                    group = people_order[:profile[0]]
                    row.update(participants=PEOPLE[:], positions='인원별 Z: ' + ', '.join('{}→{}'.format(p, zones[p]) for p in people_order),
                               entry_exit=change_text(previous, group),
                               instructions=('각 50초마다 목표 인원 변경. 홀드 구간: ' + ('한 명만 걷기' if moving else '앉아서 유지') +
                                             '. 예정 시각이 아닌 실제 출입 시각을 영상으로 나중에 기록.'))
                    stage_previous = group
                    for step, n in enumerate(profile):
                        stage_group = people_order[:n]
                        stage = dict(offset_sec=step * 50, target_count=n,
                                     participants=stage_group,
                                     action='시작 인원 배치 완료' if step == 0 else change_text(stage_previous, stage_group),
                                     hold=('전원 퇴실. 의자·물건 그대로.' if not stage_group else
                                           walking_text(stage_group, 50) if moving else '각자 본인 Z 의자에 앉아서 유지'))
                        row['stages'].append(stage)
                        event_plans.append(dict(trial_id=trial_id, planned_cue_sec=step * 50,
                                                planned_target_people=n, planned_participants='+'.join(stage_group),
                                                planned_action=stage['action']))
                        stage_previous = stage_group
                    previous = people_order[:profile[-1]]
                else:
                    row.update(phase='unlabeled', video=False, source_label='unknown')
                    options = [(['P1', 'P2'], '0~2명 범위. 두 사람이 각자 최소 한 번 출입하고 앉기/걷기를 자유롭게 수행.'),
                               (['P3', 'P4', 'P5'], '0~3명 범위. 세 사람이 출입 순서와 시점을 자유롭게 정함.'),
                               (PEOPLE[:], '3~5명 범위. P1·P2·P3은 방에 남고 P4·P5가 자유롭게 출입. 4명과 5명 상태를 모두 경험.'),
                               (PEOPLE[:], '0~5명 범위. 전원 퇴실과 5명 동시 재실을 각각 한 번 포함하고 나머지는 자유롭게 출입.')]
                    group, instruction = options[capture_no - 3]
                    row.update(participants=group, positions='자유. 가구·AP·RX 고정.',
                               entry_exit=('P1·P2·P3이 방 안에 있는 상태로 시작하고 P4·P5의 시작 위치는 자유.' if capture_no == 5 else
                                           '+'.join(group) + ' 외의 사람은 전원 퇴실. 참가자의 시작 인원과 출입 시점은 자유.') +
                                          ' 실제 출입 시각/정답은 기록하지 않음.',
                               instructions=instruction + ' CSI와 예측/처리시간/오류만 저장. 영상과 정답 기록 없음.')
                    previous = None
                rows.append(row); set_trials.append(row)
            sets.append(dict(round=round_no, set=set_no, layout=layout, activity=activity,
                             relative='T+{}~{}'.format(hm(SET_START[set_no - 1]), hm(SET_START[set_no - 1] + 48)),
                             person_order=people_order, positions=zones, trials=set_trials))
    return rows, sets, static_keys, event_plans


def validate(rows, sets):
    assert len(rows) == 144 and len({r['trial_id'] for r in rows}) == 144
    assert sum(r['recording_seconds'] for r in rows) == 12 * 3600
    phases = Counter(r['phase'] for r in rows)
    assert phases == {'train': 72, 'validation': 24, 'blind_static': 24, 'blind_dynamic': 16, 'unlabeled': 8}
    for round_no in range(1, 7):
        part = [r for r in rows if r['round'] == round_no]
        assert len(part) == 24 and sum(r['recording_seconds'] for r in part) == 7200
        assert Counter(r['layout'] for r in part) == {'A': 12, 'B': 12}
        if round_no <= 5:
            assert Counter(r['target_count'] for r in part) == dict((n, 4) for n in range(6))
    for s in sets:
        if s['round'] <= 5:
            assert sorted(r['target_count'] for r in s['trials']) == list(range(6))
            group_by_n = {r['target_count']:set(r['participants']) for r in s['trials']}
            assert all(group_by_n[n] < group_by_n[n + 1] for n in range(5))
    for n in range(1, 6):
        groups = Counter(tuple(sorted(r['participants'])) for r in rows if r['round'] <= 5 and r['target_count'] == n)
        assert set(groups) == set(combinations(PEOPLE, n))
        assert len(set(groups.values())) == 1  # All 2- and 3-person combinations appear twice.
    for r in rows:
        if r['phase'] == 'blind_dynamic':
            assert sorted(x['target_count'] for x in r['stages']) == list(range(6))
            assert [x['offset_sec'] for x in r['stages']] == [0, 50, 100, 150, 200, 250]
        if r['round'] >= 5:
            assert r['source_label'] == 'unknown'
        if r['phase'] == 'unlabeled':
            assert r['target_count'] is None and not r['video'] and not r['stages']
    return dict(total_recordings=144, total_hours=12, phases=dict(phases),
                static_train_validation_count_per_class=16,
                blind_static_count_per_class=4,
                public_inference_manifest_has_answers=False,
                all_static_participant_combinations_balanced=True,
                all_static_sets_have_nested_groups=True,
                hardware_or_data_modified=False)


def md_table(headers, rows):
    return '\n'.join(['| ' + ' | '.join(map(str, headers)) + ' |',
                      '| ' + ' | '.join('---' for _ in headers) + ' |'] +
                     ['| ' + ' | '.join(str(v).replace('|', '/') for v in row) + ' |' for row in rows])


def target_text(r):
    if r['stages']:
        return '→'.join(str(s['target_count']) for s in r['stages'])
    return str(r['target_count']) + '명' if r['target_count'] is not None else '무라벨 자유 출입'


def make_markdown(rows, sets):
    parts = [PROTOCOL]
    parts.append('## 각 회차·세트의 정확한 수집 순서\n\n각 세트의 수집 1~6을 순서대로 진행한다. 고정 인원 촬영은 파일 사이에서만 인원을 바꾼다. 괄호의 P 순서에서 앞 n명이 n명 촬영에 참여하므로 4→5명에서는 기존 4명이 같은 자리에 있고 한 명만 추가된다.\n')
    for round_no in range(1, 7):
        rr = [s for s in sets if s['round'] == round_no]
        parts.append('### {}회차\n'.format(round_no))
        parts.append(md_table(['세트', '배치', '행동', 'P 순서', '수집 1', '수집 2', '수집 3', '수집 4', '수집 5', '수집 6'],
                              [[s['set'], s['layout'], s['activity'], '→'.join(s['person_order'])] +
                               [target_text(r) for r in s['trials']] for s in rr]))
    parts.append('## 현장에서 사용할 파일\n\n- [클릭하며 확인하는 전체 144회 일정표](csi_collection_0to5_plan.html)\n- [엑셀용 전체 일정 CSV](../outputs/csi_collection_0to5_plan/operator_schedule.csv)\n- [실제 세션 ID·완료 상태 기록용 CSV](../outputs/csi_collection_0to5_plan/collection_log_template.csv)\n- [회차별 환경·배치 기록용 CSV](../outputs/csi_collection_0to5_plan/round_setup_template.csv)\n- [모델 실행용 무라벨 목록](../outputs/csi_collection_0to5_plan/inference_manifest.csv)\n- [평가 담당자용 정답·이벤트 서식](../outputs/csi_collection_0to5_plan/evaluator_only/README.md)\n- [수집량·인원 조합 검산](../outputs/csi_collection_0to5_plan/validation.json)\n\n일정표와 평가자 파일에는 계획상 인원수가 들어 있다. 모델에는 CSI와 모델 실행용 목록만 전달한다. `evaluator_only`라는 폴더명은 정리 규칙이며 접근 권한을 자동으로 막는 기능은 아니다. 실제 완료 항목은 처음에 모두 미수집 상태다.\n')
    return '\n\n'.join(parts)


PROTOCOL = '''# 0~5명 CSI 수집·검증 계획 — 추가 12시간

**달력 날짜를 지정하지 않고 1~6회차로 진행한다. 회차는 가능한 한 서로 다른 날에 배치한다.** 같은 날에 6회차를 몰아 하면 날짜 변화에 대한 검증이 되지 않는다.

총량은 **6회차 × 4세트 × 6번 × 5분 = 144개 파일, CSI 기록 12시간**이다. 한 회차에는 CSI 2시간과 준비·입퇴장·배치 변경·검수를 포함해 약 4시간 30분을 확보한다. 기존 데이터는 이 12시간에 포함하지 않는다. 첫/끝 30초를 제거하는 기존 정적 분석 기준을 적용하면 파일당 최대 4분이 남는다. 12시간 전체가 그대로 학습 시간이 되는 것은 아니다.

현재 검증된 모델은 0~3명용이다. **4·5명 데이터가 새로 모여야 0~5명 모델을 학습·검증할 수 있다.** 이 일정은 그 목표를 위한 1차 수집 계획이며, 5명까지의 정확도를 미리 보장하지 않는다.

| 회차 | 용도 | 세트 구성 | CSI 기록량 |
|---|---|---|---|
| 1회차 | 학습 | A 앉기 / A 걷기 / B 앉기 / B 걷기 | 2시간·24파일 |
| 2회차 | 학습 | B 서기 / B 걷기 / A 서기 / A 걷기 | 2시간·24파일 |
| 3회차 | 학습 | A 앉기 / A 걷기 / B 앉기 / B 걷기 | 2시간·24파일 |
| 4회차 | 모델 선택 | B 서기 / B 걷기 / A 서기 / A 걷기 | 2시간·24파일 |
| 5회차 | 정답 비공개 고정 인원 평가 | A 자세 변경 / A 걷기 / B 자세 변경 / B 걷기 | 2시간·24파일 |
| 6회차 | 인원 변화 평가·무라벨 실시간 시연 | B 변화 평가 / B 변화+시연 / A 변화 평가 / A 변화+시연 | 2시간·24파일 |

1~4회차를 합치면 0·1·2·3·4·5명 각각 **16개 파일·80분**, 총 8시간이다. 5회차는 인원수마다 4개 파일·20분씩이다. 6회차는 영상으로 사후 정답을 만드는 변화 평가 **80분·16파일**, 정답과 영상을 기록하지 않는 실제 무라벨 시연 **40분·8파일**로 나눈다. 무라벨 40분은 인원별 학습량이나 정확도 평가 표본 수에 넣지 않는다.

## 인원·위치·물건을 고정하는 방법

- 참가자 5명에게 P1~P5를 붙이고 캠페인 내내 같은 번호를 쓴다. 조작자도 방 안에 있으면 사람 수에 포함한다. 카메라 담당자가 여섯 번째 사람으로 들어오지 않는다.
- 중앙 긴 책상의 **대형 화면 쪽 긴 변을 여섯 등분**한다. 카메라 쪽부터 1/6·2/6·3/6·4/6·5/6 지점에 의자 다리 위치를 표시해 Z1~Z5로 정한다. 서는 자리는 각 의자 바로 옆에 동일 번호로 표시한다. 0명일 때도 의자 5개를 그대로 둔다.
- 의자나 사람이 겹치면 첫 준비 때 같은 쪽의 자리 간격을 넓혀 Z를 확정하고 사진·실측 간격을 남긴다. 사람이 늘 때마다 자리를 좁히거나 옮기지 않는다.
- 매 세트의 사람별 Z 위치는 전체 일정표에 지정돼 있다. **같은 세트의 0~5명 비교에서는 각 사람이 같은 Z를 쓴다.** 다음 세트에서는 지시된 Z로 바꾼다.
- 빈백·가방·개인 휴대폰·노트북은 준비 단계에서 정한 보관 위치에 두고 0~5명 사이에 바꾸지 않는다. 빈백에 눕는 실험은 이번 기본 프로토콜에서 제외한다. 의자를 사람 수만큼 가져오거나 빼지 않는다.
- P 조합은 모든 2인 조합 10가지, 3인 조합 10가지를 1~5회차 전체에서 각각 두 번씩 포함하도록 만들었다. 1인 참가자와 4인 조합도 고르게 돌아간다. 5인 실험은 매번 P1~P5 전원이다.

이 계획의 인원 검증 범위는 우선 이 참가자 5명이다. 다른 체격·새로운 참가자에 대한 성능은 이번 결과만으로 주장하지 않는다. 이후 실제 이용자를 대상으로 별도 회차를 확보해야 한다.

## 배치 A와 B

**A는 이번 수집의 기준 배치**다. 첫 준비 때 중앙 책상과 의자의 다리 위치, AP·RX·송신 PC 위치를 테이프로 표시하고 사진을 찍는다. 과거 배치를 정확히 복원했다고 가정하지 않는다.

**B는 카메라에서 가장 가까운 중앙 책상 한 개(T1)를 창문 쪽으로 30cm 평행 이동한 배치**다. AP·RX·송신 PC가 놓인 책상은 T1로 선택하지 않는다. 회전하지 않고, 의자 Z1~Z5·빈백·다른 책상·기기 위치는 바꾸지 않는다. 한쪽이 창문이 아니라면 A 사진에 표시한 '대형 화면 반대쪽' 방향을 기준으로 삼는다. T1의 A/B 발 위치를 각각 표시한다.

실측 도면이 없으므로 30cm는 제안 이동량이다. 준비 단계에서 책상끼리 겹치거나 통로를 사용할 수 없게 되면 가능한 이동량을 한 번 정해 기록하고, 이후 6회차 내내 같은 A/B 위치를 재현한다. 현장 상황에 따라 매번 다른 거리로 옮기지 않는다.

실제 무선 송신점은 휴대폰 핫스팟/AP이므로 **AP 위치·높이·방향과 RX 안테나를 고정**한다. 채널 6·2437MHz, UDP 100패킷/초·512바이트 조건을 유지하고 RX/TX 절전 상태를 통일한다. 문·창문·팬/에어컨 상태도 회차 기록에 남긴다. 이 계획은 같은 방의 두 배치에서 새 회차에 대한 동작을 검증하며, 새로운 방 전체에 대한 일반화를 입증하지는 않는다.

회차마다 환경 기록 CSV에 실제 실행일, 배치 사진, T1 실제 이동량, AP/RX 위치·높이·방향, 문·창문·냉난방 상태, 참가자 변경 여부를 남긴다. 실행일은 수집 후 이력을 남기는 항목이며 일정 날짜를 지정한 것이 아니다. 영상을 끄는 시연에서도 카메라 본체 위치는 그대로 둔다.

## 촬영 1번의 실행 방법

한 촬영 슬롯은 **약 8분 = 준비 2분 + CSI 5분 + 저장 확인 1분**이다. 처리 시간이 길어지면 뒤 슬롯을 밀고 기록 시간을 줄이지 않는다.

1. 이전 파일을 끝내고, 일정표의 퇴실자·입장자만 바꾼다. 각 사람은 자신의 Z로 간다. 변경 후 가능하면 60초 안정 시간을 둔다.
2. 인원수·실험 ID·배치·참가자·위치를 확인하고 수집을 시작한다. 0명은 전원이 퇴실한 구간만 빈 방으로 인정한다. 조작 때문에 시작 시 사람이 있었다면 실제 퇴실 시각을 기록하고 그 이전 구간을 제외한다.
3. 1~5회차는 **촬영 중 인원수를 바꾸지 않는다.** 종료 신호 후에 다음 촬영 인원으로 바꾼다. 실수로 출입했다면 파일을 억지로 고정 인원 라벨로 사용하지 않고 이벤트를 기록해 재촬영/구간 제외한다.
4. 5분 후 CSI 크기 증가·원시 파일·메타데이터·영상(해당 촬영만)·실제 session_id를 확인한다. 실패 파일은 남기고 재촬영을 같은 계획 ID의 별도 attempt로 연결한다. 12시간 목표에는 성공·검수된 계획 촬영만 계산한다.

| 회차 시작으로부터 | 작업 |
|---|---|
| T+00:00~00:15 | 배치·기기·영상·참가자·빈 방 시작 절차 점검 |
| T+00:15~01:03 | 세트 1: 6번 촬영 |
| T+01:03~01:10 | 휴식·저장 확인 |
| T+01:10~01:58 | 세트 2: 6번 촬영 |
| T+01:58~02:18 | A↔B 배치 변경·사진·휴식 |
| T+02:18~03:06 | 세트 3: 6번 촬영 |
| T+03:06~03:13 | 휴식·저장 확인 |
| T+03:13~04:01 | 세트 4: 6번 촬영 |
| T+04:01~04:30 | 파일 검수·복사·실패 촬영 보충 여유 |

## 행동 규칙

- **앉기:** 지정된 Z 의자에서 자연스럽게 앉는다. 숨쉬기·작은 손동작은 허용하고, 자리 이동과 큰 반복 운동은 하지 않는다.
- **서기:** 같은 번호의 발 위치에서 선다. 자연스러운 자세 조절은 허용하고 자리 사이 이동은 하지 않는다. 앉기용 의자는 그대로 둔다.
- **걷기:** 통로에 W0와 W1을 2m 간격으로 표시한다. 한 사람만 W0→W1 5초, 정지 5초, W1→W0 5초, 정지 5초의 20초 주기를 반복한다. 나머지는 자신의 Z에 앉는다. 걸을 사람은 60초마다 P 순서대로 바꾸고 인원이 적으면 순환한다. 5명일 때 각자가 1분씩 걷는다. 전체 일정표에 각 분의 담당자를 적었다.
- **5회차 자세 변경 세트:** 첫 150초는 앉기, 다음 150초는 서기로 바꾼다. 방 안 인원수는 계속 같다.

## 라벨을 숨긴 평가와 실제 무라벨 시연

**추론 입력에는 원래부터 사람 수 정답이 필요 없다. 정확도를 계산할 때만 별도 정답이 필요하다.** 모델 입력에 라벨이 없는 평가와, 정답 자체를 수집하지 않는 시연을 구분한다.

**5회차:** 촬영당 0~5명 중 하나를 유지하되 모델 측 기록은 `unknown`이다. 계획표의 정답은 평가 담당자만 보관하고 영상으로 실제 인원을 확인한다. 예측을 저장한 뒤 정답을 대조한다. 모델이 일정 순서·폴더의 인원수·영상·정답 CSV를 읽지 않도록 한다.

**6회차 변화 평가 16번:** 촬영 5분 동안 0:00·0:50·1:40·2:30·3:20·4:10에 여섯 인원 상태를 순서대로 만든다. 실제 출입은 파일을 끊지 않고 수행한다. 추가 인원은 P 순서대로 들어오고 감소할 때는 P 순서의 뒤쪽부터 나간다. 기존 사람은 본인 Z를 유지한다. 4:10 이후 마지막 인원수로 5:00까지 유지한다.

계획 시각은 행동 신호일 뿐 정답 시각이 아니다. 영상에서 실제 문턱 통과와 인원수를 기록하고, 여러 명이 출입하면 한 명씩 실제 변화 시각을 남긴다. 문이 닫히고 목표 인원 배치가 끝난 시각도 기록한다. 모델에는 CSI만 제공하며 정답은 예측 저장 후 붙인다. 시야가 가려져 정답을 확인하지 못한 구간은 미확인으로 남긴다.

영상 시각과 CSI 시각의 대응은 검증된 시작 로그 또는 두 기록에서 확인 가능한 동기 신호로 맞춘다. 동기 오차를 기록하고, 알려진 시각 기록 오류를 그대로 사용해 지연을 계산하지 않는다.

**6회차 실제 무라벨 8번:** 세트 2·4의 촬영 3~6이다. 영상·인원 라벨·출입 시각 정답을 기록하지 않는다. CSI·모델 출력·판별 시각·처리 시간·데이터 부족/오류만 저장한다. 정확도와 실제 출입에 대한 지연은 계산할 수 없으며, 연속 출력·끊김·처리 속도를 확인하는 용도다. 이 파일은 지도학습에 자동 합치지 않는다.

## 모델 개발·평가와 시행 전 준비

1~3회차로 학습하고 4회차로 전처리·모델을 선택한다. 선택이 끝나면 1~4회차로 재학습해 **0~5명 모델과 정규화 규칙을 고정**한다. 5·6회차는 학습·모델 선택에 쓰지 않는다. 기존 0~3명·이전 4명 자료는 환경 정보가 제한된 보조 자료로만 검토한다.

현재 수집기는 5명을 입력할 수 있다. 그러나 현재 `--num-people`은 필수이고, 저장된 추론 스크립트는 CSV를 읽는 오프라인 프로토타입이다. **라벨 미지정 수집 모드와 연속 CSI 추론은 아직 구현 완료된 기능이 아니다.** 1회차 전에는 시각 기록 오류·퇴실 구간 처리·계획 ID 기록을 확인하고, 5회차 전에 unknown 수집과 0~5명 연속 추론을 구현·시험해야 한다. unknown을 임의로 0명으로 저장하지 않는다. 일정표 작성 자체가 이 기능의 구현을 의미하지 않는다.

실시간 기준은 2초 CSI 구간에서 1초마다 출력하는 것으로 정한다. 원시 예측과 최근 3회 다수결 결과를 모두 저장한다. 패킷이 부족하거나 품질이 나쁘면 0명 대신 '판별 대기'로 표시한다. 예측 파일에는 모델 버전·구간 시작/끝·예측·출력 시각·처리 시간·품질 상태만 기록하고 정답을 섞지 않는다.

초기 목표는 5회차의 전체 정확도 90% 이상, **0~5명 각각 재현율 85% 이상**으로 제안한다. 특히 1↔2명과 4↔5명을 별도로 본다. 6회차는 인원 변경 후 안정 구간의 정확도와 변경 반응 시간을 따로 평가한다. 안정 완료 10초 뒤부터 다음 출입 전까지의 구간을 안정 구간으로 두고, 전환 중 결과는 지연 평가에 포함한다. 목표 인원·문 상태가 안정된 시각부터 올바른 출력이 3회 연속 나올 때까지의 지연을 측정한다. 5초 이내는 초기 목표이며 달성 보장이 아니다.

5·6회차 결과를 보고 모델을 수정하면 이 자료는 개발 자료가 된다. 그 뒤의 최종 성능은 새 회차로 검증한다. 시간 구간을 잘게 나눠도 같은 세션을 학습과 시험에 동시에 넣지 않는 원칙은 유지한다. [scikit-learn 그룹 검증 설명](https://scikit-learn.org/stable/modules/cross_validation.html#cross-validation-iterators-for-grouped-data)

## 목표를 달성하지 못했을 때의 추가 회차

12시간 수집만으로 성능이 부족하면 같은 파일 길이만 늘리지 않는다. 특히 4↔5명 혼동, 특정 배치에서의 오류, 정지 상태에서의 오류 중 어디에 문제가 있는지 먼저 확인한다. 새 배치 검증에서만 무너지면 회차·배치 다양성을 늘리고, 두 배치 모두에서 4↔5명이 구분되지 않으면 AP/RX 배치나 추가 수신 링크를 별도 실험으로 검토한다. 설정을 바꾼 자료는 새 설정 ID로 분리한다.

필요할 때만 **7회차: 부족 조건 보강 2시간, 8회차: 새 고정 인원 평가 2시간, 9회차: 새 변화 평가·무라벨 시연 2시간**을 추가한다. 각 회차는 계속 4세트 × 6번 × 5분으로 진행하며 7회차도 모든 0~5명을 고르게 포함한다. 같은 설정을 유지하는 경우 7회차는 1회차, 8회차는 5회차, 9회차는 6회차의 상세 지시를 각각 복제하고 계획 ID의 회차만 새 번호로 바꾼다. 설정 변경이 필요하면 먼저 새 배치 지시를 확정한다. 이 예비 6시간은 기본 12시간·144파일에 포함되지 않으며 자동으로 진행하는 필수 일정이 아니다.
'''


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    private = OUT / 'evaluator_only'; private.mkdir(exist_ok=True)
    rows, sets, keys, events = make_plan()
    check = validate(rows, sets)
    write_json(OUT / 'plan.json', dict(rounds=6, classes=list(range(6)), recordings=rows))
    write_json(OUT / 'validation.json', check)
    flat = []
    for r in rows:
        flat.append(dict(계획_ID=r['trial_id'], 회차=r['round'], 세트=r['set'], 촬영순번=r['capture'],
                         배치=r['layout'], 용도=PHASE_NAME[r['phase']], 행동=r['activity'],
                         상대슬롯=r['slot_relative'], 상대기록시간=r['record_relative'], 기록초=r['recording_seconds'],
                         계획인원=target_text(r), 참가자='+'.join(r['participants']), 위치=r['positions'],
                         촬영전출입=r['entry_exit'], 행동지시=r['instructions'],
                         초별변화지시='; '.join('{}초: {}명 / {} / {}'.format(s['offset_sec'], s['target_count'],
                                                                      s['action'], s['hold']) for s in r['stages']),
                         수집측라벨=r['source_label'], 영상='ON' if r['video'] else 'OFF'))
    write_csv(OUT / 'operator_schedule.csv', flat)
    ledger = [dict(계획_ID=r['trial_id'], 회차=r['round'], 세트=r['set'], 촬영순번=r['capture'],
                   실제_session_id='', 실제_실험일='', 실제_기록시작='', 실제_기록끝='',
                   재시도번호='', 완료상태='미수집', 검수통과='', 실제_CSI파일='', 실제_영상파일='',
                   메모='') for r in rows]
    write_csv(OUT / 'collection_log_template.csv', ledger)
    setup = [dict(회차=n, 실제_실험일='', 배치_A_사진='', 배치_B_사진='', T1_실제이동_cm='',
                  Z1_Z5_간격기록='', AP_위치높이방향='', RX_위치높이방향='', 송신PC_위치='',
                  실제_채널주파수='', 실제_UDP_pps_bytes='', 절전상태='', 문창문상태='', 냉난방팬상태='',
                  참가자_ID_변경여부='', 시각동기_방법오차='', 메모='') for n in range(1, 7)]
    write_csv(OUT / 'round_setup_template.csv', setup)
    public = [dict(trial_id=r['trial_id'], csi_path='', prediction_path='', model_version='',
                   capture_label='unknown') for r in rows if r['round'] >= 5]
    assert len(public) == 48 and not {'num_people', 'target_count', 'participants'} & set(public[0])
    write_csv(OUT / 'inference_manifest.csv', public)
    write_csv(private / 'static_answer_key.csv', keys)
    write_csv(private / 'dynamic_cue_plan.csv', events)
    actual = [dict(trial_id=r['trial_id'], video_pts_sec='', csi_relative_sec='',
                   event_type='', participant='', people_after_event='',
                   stable_complete_sec='', annotator_verified='', notes='')
              for r in rows if r['phase'] == 'blind_dynamic']
    write_csv(private / 'actual_event_log_template.csv', actual)
    (private / 'README.md').write_text('''# 평가자 전용 계획·정답 서식

static_answer_key.csv의 planned_people은 목표 인원이며 실제 정답 확인란은 비어 있다. 영상 검수 후 actual_people_after_video_review를 채운다.

dynamic_cue_plan.csv는 예정 행동 신호이며 실제 정답이 아니다. actual_event_log_template.csv에 실제 입장/퇴장 하나마다 행을 추가한다. 시작 인원, 문턱 통과, 출입 후 인원수, 문 닫힘/배치 안정 시각을 기록한다. video_pts_sec와 CSI 상대 시각의 대응을 확인한다. 모르면 빈칸/미확인으로 남긴다.

이 폴더는 모델 학습·추론 입력에 넣지 않는다. 5·6회차의 예측 파일을 먼저 확정한 뒤 정답을 대조한다. 실제 무라벨 시연 8개에는 정답 표가 없다. 이 폴더는 OS 권한으로 잠긴 폴더가 아니라 분리 보관용이다.
''')
    DOC.with_suffix('.md').write_text(make_markdown(rows, sets))
    from render_people_collection_plan import render
    render(rows, sets, PROTOCOL, OUT, DOC)
    print(json.dumps(check, ensure_ascii=False, indent=2))
    print(DOC.with_suffix('.html'))


if __name__ == '__main__':
    main()
