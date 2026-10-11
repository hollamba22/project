#!/usr/bin/env python3
"""Render the acquisition plan as a standalone, offline checklist."""
import html
import json
import re


def inline(value):
    value = html.escape(value)
    value = re.sub(r'`([^`]+)`', r'<code>\1</code>', value)
    value = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', value)
    return re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', value)


def markdown(source):
    """Render only the trusted, generated protocol's Markdown subset."""
    lines, content, i = source.splitlines(), [], 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith('#'):
            level = min(6, len(line) - len(line.lstrip('#')))
            content.append('<h{0}>{1}</h{0}>'.format(level, inline(line[level:].strip())))
        elif line.startswith('|'):
            table = []
            while i < len(lines) and lines[i].startswith('|'):
                cells = [s.strip() for s in lines[i].strip('|').split('|')]
                if not all(re.fullmatch(r':?-+:?', c) for c in cells):
                    tag = 'th' if not table else 'td'
                    table.append('<tr>' + ''.join('<{0}>{1}</{0}>'.format(tag, inline(c)) for c in cells) + '</tr>')
                i += 1
            content.append('<div class="table-wrap"><table>' + ''.join(table) + '</table></div>')
            continue
        elif line.startswith('- ') or re.match(r'^\d+\. ', line):
            ordered = not line.startswith('- ')
            tag = 'ol' if ordered else 'ul'
            items = []
            while i < len(lines) and (bool(re.match(r'^\d+\. ', lines[i])) if ordered else lines[i].startswith('- ')):
                text = re.sub(r'^\d+\. ', '', lines[i]) if ordered else lines[i][2:]
                items.append('<li>' + inline(text) + '</li>')
                i += 1
            content.append('<{0}>{1}</{0}>'.format(tag, ''.join(items)))
            continue
        else:
            content.append('<p>' + inline(line) + '</p>')
        i += 1
    return '\n'.join(content)


def layout_svg():
    panels = []
    for x, layout in [(0, 'A'), (520, 'B')]:
        shift = -36 if layout == 'B' else 0
        chairs = ''.join('<rect x="{0}" y="310" width="44" height="32" rx="7" fill="#cbd5e1"/>'
                         '<text x="{1}" y="333" text-anchor="middle" font-size="17">Z{2}</text>'
                         '<circle cx="{1}" cy="365" r="8" fill="#e2e8f0" stroke="#64748b"/>'
                         .format(62 + i * 77, 84 + i * 77, i + 1) for i in range(5))
        ghost = '<rect x="58" y="195" width="154" height="95" fill="none" stroke="#64748b" stroke-dasharray="5 5"/>' if layout == 'B' else ''
        arrow = ('<path d="M135 269 V228" stroke="#0f766e" stroke-width="3" marker-end="url(#arrow)"/>'
                 '<text x="230" y="185" font-size="16" fill="#0f766e">T1만 창문 쪽 30cm</text>') if layout == 'B' else ''
        panels.append('''<g transform="translate({x},0)">
          <rect x="12" y="12" width="496" height="470" rx="15" fill="white" stroke="#cbd5e1"/>
          <text x="34" y="47" font-size="23" font-weight="700">배치 {layout} · {subtitle}</text>
          <text x="260" y="88" text-anchor="middle" font-size="17" fill="#475569">창문 / 대형 화면 반대쪽</text>
          <path d="M65 105 H455" stroke="#38bdf8" stroke-width="5"/>
          <path d="M60 143 H440" stroke="#b45309" stroke-width="2" stroke-dasharray="5 4"/>
          <circle cx="60" cy="143" r="6" fill="#b45309"/><circle cx="440" cy="143" r="6" fill="#b45309"/>
          <text x="60" y="130" text-anchor="middle" font-size="15">W0</text>
          <text x="440" y="130" text-anchor="middle" font-size="15">W1</text>
          <text x="250" y="132" text-anchor="middle" font-size="14" fill="#92400e">실제 통로에 2m 구간 표시</text>
          {ghost}<rect x="58" y="{table_y}" width="154" height="95" rx="3" fill="#99f6e4" stroke="#0f766e"/>
          <text x="135" y="{text_y}" text-anchor="middle" font-size="20" font-weight="700">T1</text>
          <rect x="218" y="195" width="222" height="95" rx="3" fill="#f1f5f9" stroke="#94a3b8"/>
          <text x="329" y="246" text-anchor="middle" font-size="17" fill="#475569">다른 중앙 책상</text>
          {arrow}{chairs}
          <text x="250" y="397" text-anchor="middle" font-size="15" fill="#475569">Z1 → Z5: 카메라 쪽부터 / 회색 점은 서는 자리</text>
          <rect x="170" y="415" width="180" height="25" rx="4" fill="#334155"/>
          <text x="260" y="434" text-anchor="middle" font-size="14" fill="white">대형 화면 쪽</text>
          <text x="260" y="465" text-anchor="middle" font-size="14" fill="#475569">의자 5개 · 바닥 Z · AP · RX는 계속 고정</text>
        </g>'''.format(x=x, layout=layout, subtitle='기준 위치' if layout == 'A' else 'T1 평행 이동',
                     ghost=ghost, table_y=195 + shift, text_y=234 + shift, arrow=arrow, chairs=chairs))
    # A diagram of the rules, not a reconstruction of measured room geometry.
    return '''<svg xmlns="http://www.w3.org/2000/svg" width="1040" height="552" viewBox="0 0 1040 552" role="img" aria-labelledby="layout-title layout-desc">
      <title id="layout-title">두 책상 배치와 사람 위치를 표시하는 방법</title>
      <desc id="layout-desc">실측 도면이 아니다. A의 중앙 책상 한 개만 창문 방향으로 30cm 옮겨 B를 만든다. 의자와 장비는 고정한다.</desc>
      <defs><marker id="arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0 0 L7 3.5 L0 7" fill="#0f766e"/></marker></defs>
      <rect width="1040" height="552" fill="#f8fafc"/>
      <g font-family="Noto Sans CJK KR, Malgun Gothic, sans-serif" fill="#172235">''' + ''.join(panels) + '''
      <text x="520" y="512" text-anchor="middle" font-size="17" font-weight="700">배치 규칙 설명용 · 실측 도면 아님 · 가구 수와 거리는 축척에 맞지 않음</text>
      <text x="520" y="539" text-anchor="middle" font-size="15">AP/RX 실제 좌표는 첫 준비 때 표시. 장비가 놓인 책상은 이동 대상에서 제외.</text>
      </g></svg>'''


CSS = '''
:root{color-scheme:light;--ink:#172235;--muted:#58697e;--line:#d9e2ec;--brand:#0f766e}
*{box-sizing:border-box}body{margin:0;background:#f4f7fb;color:var(--ink);font:15px/1.7 "Noto Sans CJK KR","Malgun Gothic",sans-serif}
main{max-width:1160px;margin:auto;padding:28px 24px 80px}h1{font-size:32px;line-height:1.4;letter-spacing:-1px;margin:8px 0 16px}h2{font-size:23px;margin:30px 0 14px}h3{font-size:19px;margin:0}
p{margin:12px 0}a{color:var(--brand);text-underline-offset:3px}strong{font-weight:700}small,.muted{color:var(--muted)}.eyebrow{color:var(--brand);font-size:13px;letter-spacing:1px;font-weight:700}
.card,details.protocol{background:white;border:1px solid var(--line);border-radius:14px;padding:22px;margin:18px 0}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.metric{background:#fff;padding:16px;border:1px solid var(--line);border-radius:12px}.metric b{display:block;font-size:27px;line-height:1.4}.metric span{color:var(--muted);font-size:13px}
.notice{padding:13px 17px;border-left:4px solid #0d9488;background:#ecfdf5;border-radius:6px}.ready{background:#fff7ed;border-color:#c2410c}.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px}th,td{border-bottom:1px solid var(--line);padding:10px 12px;text-align:left;vertical-align:top}th{background:#f1f5f9;white-space:nowrap}tr:last-child td{border-bottom:0}.layout svg{display:block;width:100%;height:auto}.links{display:flex;flex-wrap:wrap;gap:12px 20px}
.filters{display:flex;flex-wrap:wrap;align-items:end;gap:12px}.filters label{font-weight:600;font-size:13px}.filters select,.filters input{display:block;margin-top:3px;padding:9px;border:1px solid #afbfce;border-radius:6px;background:white;color:var(--ink);font-size:14px}button{cursor:pointer;background:var(--brand);color:white;border:0;border-radius:6px;padding:10px 14px;font-size:14px}button.secondary{background:#e2e8f0;color:var(--ink)}button:focus-visible,summary:focus-visible,a:focus-visible{outline:3px solid #f59e0b;outline-offset:3px}
progress{width:240px;height:16px;accent-color:var(--brand);vertical-align:middle}.set{margin:16px 0;border:1px solid var(--line);background:white;border-radius:12px;overflow:hidden}.set>summary{padding:17px 20px;cursor:pointer;background:#edf6f5;font-weight:700}.set-info{padding:12px 20px;color:var(--muted);border-bottom:1px solid var(--line);font-size:13px}.trial{padding:14px 20px;border-bottom:1px solid var(--line)}.trial:last-child{border-bottom:0}.trial.done{background:#f0fdf4}.trial-top{display:flex;align-items:center;flex-wrap:wrap;gap:10px}.trial-top label{display:flex;align-items:center;gap:8px;font-size:14px;font-weight:700;cursor:pointer}.trial-top input[type=checkbox]{height:19px;width:19px;accent-color:var(--brand)}.pill{border-radius:20px;padding:2px 10px;background:#e2e8f0;font-size:13px;font-weight:700}.pill.unlabeled{background:#ede9fe;color:#6d28d9}.pill.blind{background:#dbeafe;color:#1e40af}.target{font-size:19px;font-weight:700}.trial details{margin-top:7px}.trial details>summary{color:var(--brand);cursor:pointer;font-size:14px}.trial dl{margin:12px 0;display:grid;grid-template-columns:100px 1fr;gap:6px 12px}.trial dt{color:var(--muted);font-size:13px}.trial dd{margin:0}.trial .fields{display:grid;grid-template-columns:1fr 2fr;gap:12px;margin-top:12px}.fields label{font-size:12px;color:var(--muted)}.fields input{display:block;width:100%;padding:8px 10px;border:1px solid #b9c6d4;border-radius:5px;font-size:14px;margin-top:3px}.protocol>summary{font-size:19px;font-weight:700;cursor:pointer}.protocol h1{font-size:25px}.protocol li{margin:8px 0}code{background:#edf1f7;padding:2px 4px;border-radius:4px;font-family:monospace;font-size:.93em}.footer{color:var(--muted);font-size:13px}.status{min-height:1.7em;color:var(--brand);font-size:13px}[hidden]{display:none!important}
@media(max-width:700px){main{padding:16px 12px 50px}h1{font-size:26px}.metrics{grid-template-columns:repeat(2,1fr)}.card,details.protocol{padding:15px}.trial,.set-info,.set>summary{padding-left:13px;padding-right:13px}.trial .fields{grid-template-columns:1fr}.trial dl{grid-template-columns:75px 1fr}.layout{overflow:auto}.layout svg{min-width:730px}progress{width:150px}}
@media print{body{background:white;font-size:11px}main{padding:0;max-width:none}.filters,.fields,.export,.progress-area,.no-print{display:none}.card,.set,details.protocol{border:0;padding:0}.trial{break-inside:avoid}.set>summary{background:#eee}.trial details>summary{display:none}a{color:inherit}.layout svg{max-height:320px}.metrics{grid-template-columns:repeat(4,1fr)}}
'''


JS = r'''
"use strict";
const plan = JSON.parse(document.getElementById("plan-data").textContent);
const storageKey = "csi-0to5-12h-plan-v1";
const phases = {train:"학습",validation:"모델 선택",blind_static:"정답 비공개 고정 평가",blind_dynamic:"정답 비공개 변화 평가",unlabeled:"실제 무라벨 시연"};
let ledger = {};
let storageAvailable = true;
try { ledger = JSON.parse(localStorage.getItem(storageKey) || "{}"); if (!ledger || Array.isArray(ledger) || typeof ledger !== "object") ledger = {}; }
catch(e) { ledger = {}; storageAvailable = false; }
const node = (tag, text, cls) => { const el = document.createElement(tag); if(text !== undefined) el.textContent=text; if(cls) el.className=cls; return el; };
function entry(id) {
  const stored = ledger[id] && typeof ledger[id] === "object" ? ledger[id] : {};
  return {done:stored.done === true, session:typeof stored.session === "string" ? stored.session : "", notes:typeof stored.notes === "string" ? stored.notes : ""};
}
function persist() {
  try { localStorage.setItem(storageKey, JSON.stringify(ledger)); }
  catch(e) { storageAvailable = false; }
  updateProgress();
}
function updateProgress() {
  const done=plan.filter(r=>entry(r.trial_id).done).length;
  document.getElementById("progress").value=done;
  document.getElementById("progress-text").textContent=`수동 완료 표시 ${done}/144개 · ${(done*5/60).toFixed(2)}시간`;
  document.getElementById("storage-status").textContent=storageAvailable ? "체크와 메모는 이 브라우저에 저장됩니다. 실제 파일 검수 후 표시하고, 종료 전에 진행 기록을 내려받으세요." : "이 브라우저는 로컬 저장을 허용하지 않습니다. 페이지를 닫기 전에 진행 기록을 내려받으세요.";
}
function addDetail(list, name, value) { list.append(node("dt",name),node("dd",value)); }
function target(r) { return r.stages.length ? r.stages.map(s=>s.target_count).join(" → ")+"명" : r.target_count === null ? "자유 출입 · 정답 미기록" : r.target_count+"명"; }
function render() {
  const round=document.getElementById("round").value;
  const phase=document.getElementById("phase").value;
  const onlyPending=document.getElementById("pending").checked;
  const selected=plan.filter(r=>(!round||String(r.round)===round)&&(!phase||r.phase===phase)&&(!onlyPending||!entry(r.trial_id).done));
  const container=document.getElementById("schedule"); container.textContent="";
  document.getElementById("filter-count").textContent=`현재 ${selected.length}개 촬영 표시`;
  const groups = new Map();
  for(const r of selected) { const key=`${r.round}-${r.set}`; if(!groups.has(key)) groups.set(key,[]); groups.get(key).push(r); }
  for(const rows of groups.values()) {
    const first=rows[0]; const group=node("details",undefined,"set"); group.open=Boolean(round);
    group.append(node("summary",`${first.round}회차 · 세트 ${first.set} · 배치 ${first.layout} · ${first.activity}`));
    const set=JSON.parse(document.getElementById("sets-data").textContent).find(s=>s.round===first.round&&s.set===first.set);
    group.append(node("div",`${set.relative} · P 순서 ${set.person_order.join(" → ")} · ${Object.entries(set.positions).map(([p,z])=>p+"→"+z).join(" / ")}`,"set-info"));
    for(const r of rows) {
      const saved=entry(r.trial_id); const article=node("article",undefined,"trial"+(saved.done?" done":""));
      const top=node("div",undefined,"trial-top"); const label=node("label"); const check=node("input"); check.type="checkbox"; check.checked=saved.done;
      check.setAttribute("aria-label",r.trial_id+" 검수 후 완료 표시");
      check.addEventListener("change",()=>{ ledger[r.trial_id]={...entry(r.trial_id),done:check.checked}; article.classList.toggle("done",check.checked); persist(); if(document.getElementById("pending").checked) render(); });
      label.append(check,node("span",r.trial_id)); top.append(label,node("span",target(r),"target"));
      top.append(node("span",phases[r.phase],"pill "+(r.phase==="unlabeled"?"unlabeled":r.round>=5?"blind":"")));
      article.append(top,node("div",`CSI ${r.record_relative} · 5분 · 수집 라벨 ${r.source_label} · 영상 ${r.video?"ON":"OFF"}`,"muted"));
      const detail=node("details"); const summary=node("summary","입퇴장 · 자리 · 행동 지시 보기"); detail.append(summary);
      const dl=node("dl"); addDetail(dl,"참가자",r.participants.join(" · ")||"전원 퇴실"); addDetail(dl,"위치",r.positions); addDetail(dl,"촬영 전",r.entry_exit); addDetail(dl,"행동",r.instructions); detail.append(dl);
      if(r.stages.length) {
        const wrap=node("div",undefined,"table-wrap");const table=node("table");const header=node("tr");["신호 시각","목표","실행할 출입","유지 행동"].forEach(t=>header.append(node("th",t)));table.append(header);
        for(const stage of r.stages) { const tr=node("tr"); const sec=stage.offset_sec; [Math.floor(sec/60)+":"+String(sec%60).padStart(2,"0"),stage.target_count+"명",stage.action,stage.hold].forEach(t=>tr.append(node("td",t)));table.append(tr); }
        wrap.append(table); detail.append(wrap,node("p","신호 시각은 정답이 아닙니다. 실제 출입·안정 완료 시각은 별도 평가자 로그에 기록합니다.","muted"));
      }
      article.append(detail); const inputs=node("div",undefined,"fields");
      for(const [key,title,placeholder] of [["session","실제 session_id","수집 후 파일의 session_id"],["notes","진행 메모","재촬영·검수·장비 상태 등"]]) {
        const field=node("label",title); const input=node("input"); input.type="text"; input.value=saved[key]; input.placeholder=placeholder;
        input.addEventListener("input",()=>{ledger[r.trial_id]={...entry(r.trial_id),[key]:input.value}; persist();});field.append(input); inputs.append(field);
      }
      article.append(inputs);group.append(article);
    }
    container.append(group);
  }
  if(!selected.length) container.append(node("p","선택한 조건에 해당하는 촬영이 없습니다."));
}
function download(name, data, type) {
  const url=URL.createObjectURL(new Blob([data],{type})); const a=node("a"); a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function csvCell(value) { let s=String(value); if(/^[=+\-@]/.test(s)) s="'"+s; return '"'+s.replace(/"/g,'""')+'"'; }
document.getElementById("export-csv").addEventListener("click",()=>{
  const rows=[["계획_ID","회차","세트","촬영순번","완료상태","실제_session_id","메모"],...plan.map(r=>{const e=entry(r.trial_id); return [r.trial_id,r.round,r.set,r.capture,e.done?"검수 후 완료 표시":"미수집",e.session,e.notes];})];
  download("csi_0to5_collection_progress.csv","\ufeff"+rows.map(r=>r.map(csvCell).join(",")).join("\r\n"),"text/csv;charset=utf-8");
});
document.getElementById("export-json").addEventListener("click",()=>download("csi_0to5_collection_progress.json",JSON.stringify({plan_version:1,ledger},null,2),"application/json"));
document.getElementById("import-json").addEventListener("change",async event=>{
  const file=event.target.files[0]; if(!file) return;
  try { const loaded=JSON.parse(await file.text()); if(loaded.plan_version!==1||!loaded.ledger||typeof loaded.ledger!=="object"||Array.isArray(loaded.ledger)) throw new Error("다른 형식");
    const merged={...ledger};for(const r of plan){const value=loaded.ledger[r.trial_id];if(value&&typeof value==="object"){merged[r.trial_id]={done:value.done===true,session:typeof value.session==="string"?value.session:"",notes:typeof value.notes==="string"?value.notes:""};}}
    ledger=merged;persist();render();document.getElementById("import-status").textContent="선택한 진행 기록을 불러왔습니다.";
  } catch(e) { document.getElementById("import-status").textContent="이 일정표에서 내보낸 진행 기록 JSON을 선택하세요. 기존 기록은 유지했습니다."; }
  event.target.value="";
});
for(const id of ["round","phase","pending"]) document.getElementById(id).addEventListener("change",render);
document.getElementById("expand").addEventListener("click",()=>document.querySelectorAll("#schedule details").forEach(d=>d.open=true));
document.getElementById("collapse").addEventListener("click",()=>document.querySelectorAll("#schedule details").forEach(d=>d.open=false));
updateProgress();render();
'''


def render(rows, sets, protocol, out, doc):
    svg = layout_svg()
    (out / 'layouts.svg').write_text(svg, encoding='utf-8')
    (out / 'checklist.js').write_text(JS, encoding='utf-8')
    small_sets = [{k: v for k, v in s.items() if k != 'trials'} for s in sets]
    rows_json = json.dumps(rows, ensure_ascii=False).replace('<', '\\u003c')
    sets_json = json.dumps(small_sets, ensure_ascii=False).replace('<', '\\u003c')
    body = '''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>0~5명 CSI · 6회차 수집 일정표</title><style>''' + CSS + '''</style></head><body><main>
    <div class="eyebrow">CSI PEOPLE COUNT · COLLECTION PLAN</div>
    <h1>0~5명 판별을 위한<br>6회차 수집 일정표</h1>
    <p>날짜 없이 회차별로 진행합니다. 회차는 가능한 한 서로 다른 날에 나누고, 같은 방에서 두 책상 배치를 반복합니다.</p>
    <div class="metrics"><div class="metric"><b>0~5명</b><span>학습할 인원수 6개</span></div><div class="metric"><b>6회차</b><span>매 회차 4세트 × 6번</span></div><div class="metric"><b>144파일</b><span>파일당 CSI 5분</span></div><div class="metric"><b>12시간</b><span>새 CSI 기록량 · 준비 시간 별도</span></div></div>
    <p class="notice">현재 모델은 0~3명용입니다. 4·5명 데이터를 새로 수집하고 0~5명 모델을 학습·평가해야 합니다. 12시간은 첫 수집 예산이며 정확도를 미리 보장하지 않습니다.</p>
    <div class="card"><h2 style="margin-top:0">회차별 목표</h2><div class="table-wrap"><table><thead><tr><th>회차</th><th>용도</th><th>세트 1 → 2 → 3 → 4</th><th>CSI</th></tr></thead><tbody>
    <tr><td>1회차</td><td>학습</td><td>A 앉기 → A 걷기 → B 앉기 → B 걷기</td><td>2시간</td></tr>
    <tr><td>2회차</td><td>학습</td><td>B 서기 → B 걷기 → A 서기 → A 걷기</td><td>2시간</td></tr>
    <tr><td>3회차</td><td>학습</td><td>A 앉기 → A 걷기 → B 앉기 → B 걷기</td><td>2시간</td></tr>
    <tr><td>4회차</td><td>모델 선택</td><td>B 서기 → B 걷기 → A 서기 → A 걷기</td><td>2시간</td></tr>
    <tr><td>5회차</td><td>정답 비공개 고정 인원 평가</td><td>A 자세 변경 → A 걷기 → B 자세 변경 → B 걷기</td><td>2시간</td></tr>
    <tr><td>6회차</td><td>인원 변화 평가 + 실제 무라벨</td><td>B 변화 6번 → B 변화 2번+시연 4번 → A 변화 6번 → A 변화 2번+시연 4번</td><td>80분 + 40분</td></tr>
    </tbody></table></div><p class="muted">1~4회차: 인원수마다 16개 파일·80분. 5회차: 인원수마다 4개 파일·20분. 각 회차는 준비와 검수를 포함해 약 4시간 30분을 확보합니다.</p>
    <p><strong>진행 순서:</strong> 1~3회차 학습 → 4회차로 모델 선택 → 1~4회차로 재학습·고정 → 5~6회차 최종 평가. 5~6회차를 보고 모델을 바꾸면 최종 검증용 새 회차가 필요합니다.</p></div>
    <div class="card layout"><h2 style="margin-top:0">배치와 사람 위치</h2>''' + svg + '''
    <p>첫 준비 때 의자 5개와 서는 자리를 Z1~Z5로 표시합니다. 매 세트의 지정 위치는 아래에 있습니다. 같은 세트에서는 기존 사람의 자리를 유지하고, 다음 세트에서 참가자 조합과 Z 배정을 바꿉니다. T1 이동량이 현장에 맞지 않으면 한 번 조정해 기록한 뒤 계속 같은 A/B를 사용합니다.</p></div>
    <details class="protocol"><summary>먼저 읽기: 배치·입퇴장·행동·라벨·모델 평가 규칙</summary>''' + markdown(protocol) + '''</details>
    <div class="card"><h2 style="margin-top:0">현장 파일</h2><div class="links">
    <a href="csi_collection_0to5_plan.md">설명과 전체 순서 Markdown</a>
    <a href="../outputs/csi_collection_0to5_plan/operator_schedule.csv" download>전체 144회 일정 CSV</a>
    <a href="../outputs/csi_collection_0to5_plan/collection_log_template.csv" download>실제 수집 기록 CSV</a>
    <a href="../outputs/csi_collection_0to5_plan/round_setup_template.csv" download>회차별 환경 기록 CSV</a>
    <a href="../outputs/csi_collection_0to5_plan/inference_manifest.csv" download>모델 실행용 무라벨 목록</a>
    <a href="../outputs/csi_collection_0to5_plan/evaluator_only/README.md">평가자 정답 서식</a></div>
    <p class="notice ready">5~6회차 전 준비: 현재 수집기는 5명 입력을 지원하지만, 라벨 미지정 수집과 연속 추론은 아직 구현되지 않았습니다. unknown 수집 모드·0~5명 모델·연속 추론을 준비한 뒤 평가를 진행합니다.</p>
    <p class="muted">이 일정표는 수집 담당자용으로 계획 인원을 포함합니다. 모델에는 CSI만 입력하고, 사람 수가 들어 있는 일정표·파일명·영상·정답을 입력으로 사용하지 않습니다. 실제 무라벨 40분은 정확도 평가에 사용하지 않습니다.</p></div>
    <div class="card"><h2 style="margin-top:0">144번 촬영 체크리스트</h2>
    <div class="filters"><label>회차<select id="round"><option value="1">1회차</option><option value="2">2회차</option><option value="3">3회차</option><option value="4">4회차</option><option value="5">5회차</option><option value="6">6회차</option><option value="">전체 회차</option></select></label>
    <label>용도<select id="phase"><option value="">전체 용도</option><option value="train">학습</option><option value="validation">모델 선택</option><option value="blind_static">정답 비공개 고정 평가</option><option value="blind_dynamic">정답 비공개 변화 평가</option><option value="unlabeled">실제 무라벨 시연</option></select></label>
    <label style="padding:9px 0"><input type="checkbox" id="pending" style="display:inline"> 미완료만</label>
    <button type="button" id="expand" class="secondary">지시 모두 펼치기</button><button type="button" id="collapse" class="secondary">접기</button></div>
    <p id="filter-count" class="muted"></p><div class="progress-area"><progress id="progress" max="144" value="0"></progress> <span id="progress-text"></span><p id="storage-status" class="muted"></p></div>
    <div class="filters export"><button type="button" id="export-csv">진행 기록 CSV 저장</button><button type="button" id="export-json" class="secondary">백업 JSON 저장</button><label>백업 불러오기<input type="file" id="import-json" accept=".json,application/json"></label></div><div class="status" id="import-status" role="status"></div></div>
    <noscript><p class="notice">체크리스트를 표시하려면 JavaScript를 켜거나 위의 전체 일정 CSV·Markdown 파일을 사용하세요.</p></noscript><div id="schedule"></div>
    <p class="footer">각 촬영: 준비 2분 + CSI 5분 + 저장 확인 1분. 모든 시각은 회차 시작 기준 T+입니다. 체크는 수동 기록이며 원시 파일 존재·품질을 자동으로 확인하지 않습니다.</p>
    </main><script type="application/json" id="plan-data">''' + rows_json + '''</script><script type="application/json" id="sets-data">''' + sets_json + '''</script><script>''' + JS + '''</script></body></html>'''
    doc.with_suffix('.html').write_text(body, encoding='utf-8')
