
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
