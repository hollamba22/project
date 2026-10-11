#!/usr/bin/env python3
"""Build a window index from CSI sessions.

This script does not copy CSI matrices. It creates a lightweight CSV that maps
each time window to packet index ranges inside a session's csi.dat file.
"""

import argparse
import csv
import json
import math
import os
import sys


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


WINDOW_FIELDS = [
    "window_id",
    "session_id",
    "csi_file",
    "meta_file",
    "quality_status",
    "dataset_role",
    "use_for_final_training",
    "num_people",
    "label_status",
    "activity",
    "duration_sec",
    "record_count",
    "window_size_sec",
    "stride_sec",
    "start_sec",
    "end_sec",
    "start_packet",
    "end_packet",
    "packet_count",
]


def parse_bool(value):
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def read_csv(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def write_csv(path, rows):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=WINDOW_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in WINDOW_FIELDS})


def write_json(path, rows):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"window_count": len(rows), "windows": rows}, f, ensure_ascii=False, indent=2)
        f.write("\n")


def meta_path_for_session(row):
    session_dir = row.get("session_dir", "")
    if not session_dir:
        return ""
    return os.path.join(session_dir, "meta.json")


def should_use_session(row, args):
    if row.get("quality_status") != "valid_csi":
        return False
    if int(row.get("record_count") or 0) <= 0:
        return False

    role = row.get("dataset_role", "")
    final_training = parse_bool(row.get("use_for_final_training", "false"))

    if args.include_all_valid:
        return True
    if args.include_verification and role in {"training_candidate", "test_candidate", "verification_only"}:
        return True
    if role in {"training_candidate", "test_candidate"} and final_training:
        return True
    return False


def get_label_from_meta_or_row(meta, row):
    if meta:
        label = meta.get("label", {})
        return {
            "num_people": label.get("num_people", row.get("num_people", "")),
            "label_status": label.get("label_status", row.get("label_status", "")),
            "activity": label.get("activity", row.get("activity", "")),
        }
    return {
        "num_people": row.get("num_people", ""),
        "label_status": row.get("label_status", ""),
        "activity": row.get("activity", ""),
    }


def get_duration(meta, row, default_duration):
    if meta:
        capture = meta.get("capture", {})
        duration = capture.get("duration_sec") or capture.get("planned_duration_sec")
        if duration:
            return float(duration)
    return float(default_duration)


def make_session_windows(row, args):
    session_id = row["session_id"]
    meta_rel = meta_path_for_session(row)
    meta = read_json(os.path.join(PROJECT_ROOT, meta_rel)) if meta_rel else None
    label = get_label_from_meta_or_row(meta, row)
    duration_sec = get_duration(meta, row, args.default_duration_sec)
    record_count = int(row.get("record_count") or 0)

    if duration_sec <= 0 or record_count <= 0:
        return []

    windows = []
    start_sec = 0.0
    idx = 0
    eps = 1e-9
    while start_sec + args.window_size_sec <= duration_sec + eps:
        end_sec = min(duration_sec, start_sec + args.window_size_sec)
        start_packet = int(math.floor((start_sec / duration_sec) * record_count))
        end_packet = int(math.ceil((end_sec / duration_sec) * record_count))
        start_packet = max(0, min(record_count, start_packet))
        end_packet = max(start_packet, min(record_count, end_packet))
        packet_count = end_packet - start_packet

        if packet_count >= args.min_packets:
            windows.append({
                "window_id": "{}_w{:04d}".format(session_id, idx),
                "session_id": session_id,
                "csi_file": row.get("csi_file", ""),
                "meta_file": meta_rel,
                "quality_status": row.get("quality_status", ""),
                "dataset_role": row.get("dataset_role", ""),
                "use_for_final_training": row.get("use_for_final_training", ""),
                "num_people": label["num_people"],
                "label_status": label["label_status"],
                "activity": label["activity"],
                "duration_sec": "{:.6f}".format(duration_sec),
                "record_count": record_count,
                "window_size_sec": "{:.6f}".format(args.window_size_sec),
                "stride_sec": "{:.6f}".format(args.stride_sec),
                "start_sec": "{:.6f}".format(start_sec),
                "end_sec": "{:.6f}".format(end_sec),
                "start_packet": start_packet,
                "end_packet": end_packet,
                "packet_count": packet_count,
            })
            idx += 1

        start_sec += args.stride_sec

    return windows


def main(argv=None):
    parser = argparse.ArgumentParser(description="Create CSI window index CSV")
    parser.add_argument("--session-index", default=os.path.join(PROJECT_ROOT, "outputs", "dataset", "session_index.csv"))
    parser.add_argument("--out-csv", default=os.path.join(PROJECT_ROOT, "data", "processed", "windows.csv"))
    parser.add_argument("--out-json", default=os.path.join(PROJECT_ROOT, "data", "processed", "windows.json"))
    parser.add_argument("--window-size-sec", type=float, default=2.0)
    parser.add_argument("--stride-sec", type=float, default=1.0)
    parser.add_argument("--default-duration-sec", type=float, default=60.0)
    parser.add_argument("--min-packets", type=int, default=1)
    parser.add_argument("--include-verification", action="store_true", help="include verification_only sessions for dry runs")
    parser.add_argument("--include-all-valid", action="store_true", help="include all valid_csi sessions")
    args = parser.parse_args(argv)

    rows = read_csv(args.session_index)
    windows = []
    for row in rows:
        if should_use_session(row, args):
            windows.extend(make_session_windows(row, args))

    write_csv(args.out_csv, windows)
    write_json(args.out_json, windows)
    print("Wrote {}".format(os.path.relpath(args.out_csv, PROJECT_ROOT)))
    print("Wrote {}".format(os.path.relpath(args.out_json, PROJECT_ROOT)))
    print("window_count={}".format(len(windows)))
    if not windows:
        print("No windows selected. Use --include-verification for dry runs before final training data exists.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
