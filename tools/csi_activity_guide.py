#!/usr/bin/env python3
"""RX terminal instructions, timed from the first valid UDP packet (Python 3.6+)."""
import math
import os
import re
import shutil
import sys
import time
import unicodedata


ACTIVITY_NAMES = {"empty": "빈 방", "sitting": "앉기", "standing": "서기",
                  "walking": "교대 걷기", "sit_stand": "앉기 → 서기", "natural": "자연 활동",
                  "mixed": "앉기·서기·걷기 자동 진행", "free_test": "자유 테스트"}


def repetitions_input(value):
    if not re.fullmatch(r"[0-9]+", value) or not 1 <= int(value) <= 20:
        raise ValueError("반복 횟수는 1~20 사이의 정수로 입력하세요.")
    return int(value)


def build_segments(activity, duration_per_activity, repetitions=1):
    if activity not in ACTIVITY_NAMES or not math.isfinite(duration_per_activity) or duration_per_activity <= 0:
        raise ValueError("행동과 유한한 양수 수집 시간을 확인하세요.")
    if type(repetitions) is not int or not 1 <= repetitions <= 20:
        raise ValueError("반복 횟수는 1~20이어야 합니다.")
    sequence = ("sitting", "standing", "walking") if activity == "mixed" else (activity,)
    segments = []
    for repeat in range(repetitions):
        for current in sequence:
            index = len(segments)
            segments.append({"index": index + 1, "repeat": repeat + 1, "activity": current,
                             "start_sec": index * duration_per_activity,
                             "end_sec": (index + 1) * duration_per_activity})
    return segments


def assign_walking_order(segments, participants):
    for segment in segments:
        if segment["activity"] == "walking":
            if not participants:
                raise ValueError("걷기 안내에는 참가자가 필요합니다.")
            offset = (segment["repeat"] - 1) % len(participants)
            segment["walking_order"] = [p["person"] for p in participants[offset:] + participants[:offset]]


def seconds_input(value):
    if not re.fullmatch(r"[0-9]+", value) or not 0 <= int(value) <= 120:
        raise ValueError("0~120 사이의 정수(초)를 입력하세요.")
    return int(value)


def participant_input(value, count):
    tokens = value.upper().replace(",", " ").split()
    if len(tokens) != count or any(not re.fullmatch(r"P[1-9][0-9]*:Z[1-9][0-9]*", token) for token in tokens):
        raise ValueError("{}명의 참가자:자리를 입력하세요. 예: P1:Z1 P2:Z2".format(count))
    pairs = [token.split(":") for token in tokens]
    if len({p for p, _ in pairs}) != count or len({z for _, z in pairs}) != count:
        raise ValueError("참가자 번호와 자리는 각각 중복될 수 없습니다.")
    return [{"person": p, "position": z} for p, z in pairs]


def clock_text(seconds):
    seconds = max(0, int(seconds))
    return "{:02d}:{:02d}".format(seconds // 60, seconds % 60)


def action_at(activity, participants, duration, elapsed):
    """Return the cue due now; do not invent cues skipped by a delayed display."""
    elapsed = max(0.0, elapsed)
    if elapsed >= duration:
        return {"key": "ended", "scheduled_sec": duration, "action": "기록 시간 종료. 정리가 끝날 때까지 유지하세요.",
                "others": "", "next": "저장·검사 후 완료 안내", "next_sec": duration}
    if activity == "empty":
        action, others = "빈 방 유지 — 들어오지 마세요.", "조작자를 포함해 방 안 0명 유지"
    elif activity == "walking":
        if not participants:
            raise ValueError("걷기 안내에는 참가자가 필요합니다.")
        minute = int(elapsed // 60)
        walker = participants[minute % len(participants)]
        phase = int(elapsed // 5) % 4
        instructions = ("W0 → W1로 5초 동안 이동", "W1에서 5초 정지",
                        "W1 → W0로 5초 동안 이동", "W0에서 5초 정지")
        boundary = (int(elapsed // 5) + 1) * 5
        next_walker = participants[int(boundary // 60) % len(participants)]
        others = " / ".join("{}: {}에서 앉기".format(p["person"], p["position"])
                            for p in participants if p != walker) or "참가자 1명: 같은 사람이 계속 걷기"
        if minute and elapsed % 60 < 5 and len(participants) > 1:
            previous = participants[(minute - 1) % len(participants)]
            others += " | 교대: {}는 {}로 복귀".format(previous["person"], previous["position"])
        following = "{}: {}".format(next_walker["person"], instructions[(phase + 1) % 4])
        if boundary >= duration:
            following = "기록 시간 종료 — 정리 중 현재 상태 유지"
        next_minute = (minute + 1) * 60
        return {"key": "walking_{}_{}".format(walker["person"], int(elapsed // 5)),
                "scheduled_sec": int(elapsed // 5) * 5, "person": walker["person"],
                "action": "{}: {}".format(walker["person"], instructions[phase]),
                "others": others, "next": following, "next_sec": min(boundary, duration),
                "rotation": ("다음 교대 {}: {}".format(clock_text(next_minute),
                    participants[(minute + 1) % len(participants)]["person"])
                    if next_minute < duration else "이번이 마지막 걷기 담당입니다.")}
    elif activity == "standing" or (activity == "sit_stand" and elapsed >= duration / 2):
        action, others = "지정 위치에서 서서 유지하세요.", "자연스러운 자세 조절 허용 / 자리 이동 없음"
    elif activity in ("sitting", "sit_stand"):
        action, others = "지정 자리에 앉아 유지하세요.", "작은 손동작·자세 조절 허용 / 자리 이동 없음"
    elif activity == "natural":
        action, others = "정한 범위에서 자연스럽게 활동하세요.", "수집 중 인원수와 기기·가구 배치 유지"
    else:
        raise ValueError("알 수 없는 행동: " + activity)
    first_half = activity == "sit_stand" and elapsed < duration / 2
    return {"key": "sitting" if first_half else activity,
            "scheduled_sec": duration / 2 if activity == "sit_stand" and not first_half else 0,
            "action": action, "others": others,
            "next": "전원 지정 위치에서 서기" if first_half else "기록 시간 종료 — 정리 중 현재 상태 유지",
            "next_sec": duration / 2 if first_half else duration}


def wrap_cells(text, width):
    """Wrap Korean text by terminal cells; filter control characters from messages."""
    lines, line, used = [], "", 0
    for char in str(text):
        if unicodedata.category(char).startswith("C"):
            char = " "
        cells = 0 if unicodedata.combining(char) else (2 if unicodedata.east_asian_width(char) in "WF" else 1)
        if used + cells > width and line:
            lines.append(line)
            line, used = "", 0
        line += char
        used += cells
    return lines + [line]


class TerminalPanel:
    def __init__(self, stream=None):
        self.stream = stream or sys.stdout
        self.tty = bool(self.stream.isatty() and os.environ.get("TERM") != "dumb")
        self.active = False

    def show(self, lines, changed=False):
        if not self.tty and not changed:
            return
        if self.tty:
            if not self.active:
                self.stream.write("\033[?1049h\033[?25l")
                self.active = True
            self.stream.write("\033[H\033[2J")
        width = max(20, shutil.get_terminal_size((100, 24)).columns - 1)
        for index, line in enumerate(lines):
            text = "\n".join(wrap_cells(line, width))
            if self.tty and index == 4:
                text = "\033[1m" + text + "\033[0m"
            self.stream.write(text + "\n")
        self.stream.flush()

    def bell(self):
        if self.tty:
            self.stream.write("\a")
            self.stream.flush()

    def close(self):
        if self.active:
            self.stream.write("\033[0m\033[?25h\033[?1049l")
            self.stream.flush()
            self.active = False


class ActivityGuide:
    def __init__(self, config, collection, settings, record, panel=None,
                 monotonic=None, sleep=None):
        self.config, self.collection, self.settings = config, collection, settings
        self.record = record
        self.panel = panel or TerminalPanel()
        self.now, self.sleep = monotonic or time.monotonic, sleep or time.sleep
        self.last_key = self.last_second = None
        self.anchor = None
        self.duration = config["duration_sec"]
        self.segments = settings["segments"]
        if not self.segments or abs(self.segments[-1]["end_sec"] - self.duration) > 1e-6:
            raise ValueError("행동 구간 총 시간과 RX 수집 시간이 다릅니다.")

    def header(self):
        return "{} | 배치 {} | {}명 | {}".format(self.collection["room"], self.collection["setup_id"],
            self.config["num_people"], ACTIVITY_NAMES[self.collection["activity"]])

    def show(self, key, stage, timing, action, details, second, **event):
        changed = key != self.last_key
        if changed:
            self.record("GUIDE_CUE", stage=stage, cue_key=key, instruction=action, **event)
            self.panel.bell()
        if changed or second != self.last_second:
            self.panel.show(["CSI 수집 행동 안내", self.header(), stage + " | " + timing, "",
                             "지금: " + action, ""] + details + ["", "중단: Ctrl+C"], changed)
        self.last_key, self.last_second = key, second

    def prepare(self, health):
        people = self.settings["participants"]
        places = " / ".join("{} → {}".format(p["person"], p["position"]) for p in people)
        if self.config["num_people"] == 0:
            instruction = "조작자를 포함해 모두 퇴실하고 문 상태를 고정하세요."
        elif self.segments[0]["activity"] == "walking":
            instruction = "{}은 W0로, 나머지는 지정 자리로 가세요.".format(people[0]["person"])
        elif self.segments[0]["activity"] == "standing":
            instruction = "각자 지정된 Z 위치에 서서 준비하세요."
        else:
            instruction = "지정 자리에 앉아 준비하세요. 수집 중 방 안 인원은 {}명입니다.".format(self.config["num_people"])
        for stage, seconds, action in (("자리 준비·퇴실", self.settings["prepare_sec"], instruction),
                                       ("안정화", self.settings["settle_sec"],
                                        "빈 방 유지 — 들어오지 마세요." if not people else "이동을 멈추고 시작 신호를 기다리세요.")):
            deadline = self.now() + seconds
            # Even a zero-duration phase performs one health check before START.
            while True:
                health()
                remaining = max(0, math.ceil(deadline - self.now()))
                self.show(stage, stage, "남은 시간 " + clock_text(remaining), action,
                          [places, "이 준비 시간은 CSI 수집 시간에 포함되지 않습니다."], remaining,
                          planned_duration_sec=seconds)
                if self.now() >= deadline:
                    break
                self.sleep(min(0.1, max(0, deadline - self.now())))
        self.progress("waiting")

    def progress(self, stage, **details):
        if stage == "recording":
            if self.anchor is None:
                self.anchor = details["first_packet_wall_epoch"]
                self.record("GUIDE_TIME_ANCHOR", first_packet_wall_epoch=self.anchor,
                            clock="elapsed seconds since first valid session UDP; cues are instructions, not observed actions")
            elapsed = min(self.duration, max(0, details["elapsed_sec"]))
            segment = next((s for s in self.segments if elapsed < s["end_sec"]), self.segments[-1])
            participants = self.settings["participants"]
            if segment.get("walking_order"):
                by_person = {p["person"]: p for p in participants}
                participants = [by_person[p] for p in segment["walking_order"]]
            cue = action_at(segment["activity"], participants,
                            segment["end_sec"] - segment["start_sec"], elapsed - segment["start_sec"])
            cue["scheduled_sec"] += segment["start_sec"]
            cue["next_sec"] += segment["start_sec"]
            if cue["next_sec"] >= segment["end_sec"] and segment["index"] < len(self.segments):
                following = self.segments[segment["index"]]
                cue["next"] = "다음 동작 {} ({}분), 인원 유지".format(
                    ACTIVITY_NAMES[following["activity"]], (following["end_sec"] - following["start_sec"]) / 60)
            next_in = math.ceil(max(0, cue["next_sec"] - elapsed))
            lines = ["이번 동작: {} | 남은 {} | {}회차".format(ACTIVITY_NAMES[segment["activity"]],
                     clock_text(math.ceil(max(0, segment["end_sec"] - elapsed))), segment["repeat"]),
                     cue["others"], "{}초 후: {}".format(next_in, cue["next"])]
            if cue.get("rotation"):
                lines.append(cue["rotation"] + " (이번 걷기 구간 기준)")
            lines += ["수신 패킷: {} | 방 안 인원 유지".format(details["packets"])]
            self.show("segment_{}_{}".format(segment["index"], cue["key"]),
                      "수집 중 {}/{}구간".format(segment["index"], len(self.segments)),
                      "경과 {} / {} | 남은 {}".format(clock_text(elapsed),
                      clock_text(self.duration), clock_text(math.ceil(max(0, self.duration - elapsed)))),
                      cue["action"], lines, int(elapsed), scheduled_elapsed_sec=cue["scheduled_sec"],
                      observed_elapsed_sec=elapsed, first_packet_wall_epoch=self.anchor,
                      next_instruction=cue["next"], person=cue.get("person"),
                      activity=segment["activity"], segment_index=segment["index"], repeat=segment["repeat"])
        elif stage == "waiting":
            self.show("waiting", "시작 대기", "첫 유효 패킷 대기 중", "현재 상태를 유지하고 시작 안내를 기다리세요.",
                      ["0명 수집이면 계속 퇴실 상태를 유지하세요." if not self.config["num_people"]
                       else "지정한 시작 자세를 유지하세요."], 0)
        elif stage == "finishing":
            self.show("finishing", "기록 마무리", "수집 시간 종료", "영상·기록 정리가 끝날 때까지 현재 상태를 유지하세요.",
                      ["아직 최종 완료 상태가 아닙니다."], 0, elapsed_sec=self.duration)
        elif stage in ("processing", "confirming"):
            self.panel.close()
            self.record("GUIDE_STATUS", stage=stage)
            print("[행동 안내] 기록 종료. 이제 자리 이동이 가능합니다. " +
                  ("파일 저장·품질 검사 중입니다." if stage == "processing" else "TX 완료 확인 중입니다."), flush=True)
        elif stage == "failed":
            # Restore normal scrollback before capture prints the actual error.
            self.panel.close()
            self.record("GUIDE_STATUS", stage=stage, reason=details.get("reason", ""))

    def result(self, success, reason=""):
        self.panel.close()
        self.panel.bell()
        if success:
            print("\n[수집 완료] " + self.header())
            count = self.config["num_people"]
            if count == 0:
                print("[다음] 빈 방 영상·품질을 확인한 뒤 같은 강의실·배치에서 1명을 수집하세요.")
            elif count < 4:
                print("[다음] 오늘 순서: {}명, 같은 강의실·배치·행동으로 준비하세요.".format(count + 1))
            else:
                print("[다음] 이번 행동 세트가 끝났습니다. 계획표의 다음 행동/배치를 확인하세요.")
            print("다음 파일은 RX/TX 실행기를 새로 실행해 설정을 확인한 뒤 시작합니다.")
        else:
            print("\n[수집 실패/중단] {}\n이번 파일은 성공 처리하지 않습니다.".format(reason))

    def close(self):
        self.panel.close()


class FreeTestGuide(ActivityGuide):
    """Show capture health/time without scheduling actions or assigning counts."""

    def header(self):
        return "{} | 배치 {} | 0~4명 자유 테스트 | 실제 인원 미확정".format(
            self.collection["room"], self.collection["setup_id"])

    def prepare(self, health):
        for stage, seconds in (("촬영 준비", self.settings["prepare_sec"]),
                               ("시작 대기", self.settings["settle_sec"])):
            deadline = self.now() + seconds
            while True:
                health()
                remaining = max(0, math.ceil(deadline - self.now()))
                self.show(stage, stage, "남은 시간 " + clock_text(remaining),
                          "출입문과 방 안 인원이 영상에 보이는지 확인하고 자유 테스트를 준비하세요.",
                          ["시작 인원은 지정하지 않습니다. 자리 번호·행동 순서는 자유입니다.",
                           "이 준비 시간은 본 수집 시간에 포함되지 않습니다."], remaining,
                          planned_duration_sec=seconds)
                if self.now() >= deadline:
                    break
                self.sleep(min(0.1, max(0, deadline - self.now())))
        self.progress("waiting")

    def progress(self, stage, **details):
        if stage == "recording":
            if self.anchor is None:
                self.anchor = details["first_packet_wall_epoch"]
                self.record("GUIDE_TIME_ANCHOR", first_packet_wall_epoch=self.anchor,
                            clock="elapsed seconds since first valid session UDP; occupancy is unknown")
            elapsed = min(self.duration, max(0, details["elapsed_sec"]))
            self.show("free_test", "CSI·영상 수집 중",
                      "경과 {} / {} | 남은 {}".format(clock_text(elapsed), clock_text(self.duration),
                          clock_text(math.ceil(max(0, self.duration - elapsed)))),
                      "0~4명 범위에서 자유롭게 활동하고 들어오거나 나가세요.",
                      ["정해진 입퇴실 순서·동작·자리 번호는 없습니다.",
                       "실제 인원수: 영상 검수 후 기록 예정 (현재 자동 판별하지 않음)",
                       "수신 패킷: {} | 영상 녹화 중".format(details["packets"]),
                       "카메라·AP·RX 배치를 유지하세요. 방 안 조작자도 인원에 포함됩니다."],
                      int(elapsed), observed_elapsed_sec=elapsed, first_packet_wall_epoch=self.anchor,
                      activity="free_test", label_status="unknown")
        elif stage == "waiting":
            self.show("waiting", "시작 대기", "첫 유효 패킷 대기 중",
                      "수집 시작 안내를 기다리세요. 시작 인원과 자세는 자유입니다.",
                      ["화면의 경과 시간이 시작되면 자유 테스트를 진행하세요."], 0)
        else:
            super().progress(stage, **details)

    def result(self, success, reason=""):
        self.panel.close()
        self.panel.bell()
        if success:
            print("\n[자유 테스트 수집 완료] " + self.header())
            print("[저장] data/free_test / 세션 " + self.config["session_id"])
            print("[정답 작성] META_DATA/<세션>/annotations/ground_truth_intervals.csv에 영상 검수 후 입력하세요.")
            print("[시각 확인] time_alignment.json과 영상에 표시된 RX 시각을 확인하세요.")
        else:
            print("\n[자유 테스트 실패/중단] {}\n부분 기록은 보존되며 성공 처리하지 않습니다.".format(reason))

def demo():
    import argparse
    parser = argparse.ArgumentParser(description="하드웨어·실험 파일 없이 RX 행동 안내 미리보기")
    parser.add_argument("--activity", choices=sorted(ACTIVITY_NAMES), default="walking")
    parser.add_argument("--people", type=int, default=3)
    parser.add_argument("--speed", type=float, default=10)
    args = parser.parse_args()
    if not 1 <= args.people <= 20 or not math.isfinite(args.speed) or not 0 < args.speed <= 100:
        parser.error("people: 1~20, speed: 0 초과 100 이하")
    count = 0 if args.activity == "empty" else args.people
    participants = [] if args.activity == "free_test" else participant_input(
        " ".join("P{0}:Z{0}".format(i + 1) for i in range(count)), count)
    segments = build_segments(args.activity, 300, 2 if args.activity == "mixed" else 1)
    assign_walking_order(segments, participants)
    duration = segments[-1]["end_sec"]
    start = time.monotonic()
    guide = (FreeTestGuide if args.activity == "free_test" else ActivityGuide)({"num_people": count, "duration_sec": duration},
        {"room": "DEMO", "setup_id": "A", "activity": args.activity},
        {"participants": participants, "prepare_sec": 3, "settle_sec": 3, "segments": segments}, lambda *a, **k: None,
        monotonic=lambda: (time.monotonic() - start) * args.speed)
    try:
        guide.prepare(lambda: None)
        anchor = guide.now()
        wall = time.time()
        while guide.now() - anchor < duration:
            elapsed = guide.now() - anchor
            guide.progress("recording", elapsed_sec=elapsed, first_packet_wall_epoch=wall, packets=int(elapsed * 100))
            time.sleep(0.05)
        guide.progress("finishing")
        time.sleep(0.3)
        guide.progress("processing")
        guide.progress("confirming")
        print("[미리보기 종료] 실제 수집·송신·파일 저장은 수행하지 않았습니다.")
    finally:
        guide.close()


if __name__ == "__main__":
    demo()
