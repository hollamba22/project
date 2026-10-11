#!/usr/bin/env python3
"""Validate CSI sessions and write a session index CSV."""

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timedelta, timezone


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CSI_SCRIPT_DIR = os.path.join(PROJECT_ROOT, "scripts", "csi")
if CSI_SCRIPT_DIR not in sys.path:
    sys.path.insert(0, CSI_SCRIPT_DIR)

from csi_parser import summarize_file  # noqa: E402


KST = timezone(timedelta(hours=9))


CSV_FIELDS = [
    "session_id",
    "session_dir",
    "csi_file",
    "has_csi",
    "has_meta",
    "file_bytes",
    "record_count",
    "quality_status",
    "dataset_role",
    "use_for_final_training",
    "num_people",
    "label_status",
    "activity",
    "rx_kernel",
    "rx_ip",
    "ap_ssid",
    "ap_channel",
    "ap_frequency_mhz",
    "antenna_holder",
    "room",
    "environment_note",
    "antenna_dimensions",
    "rates",
    "validation_message",
]


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def write_json(path, data):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def write_csv(path, rows):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in CSV_FIELDS})


def as_csv_json(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def infer_without_meta(file_bytes, record_count, has_csi):
    if not has_csi:
        return "failed", "failure_history", False, "missing csi.dat"
    if file_bytes <= 0:
        return "failed", "failure_history", False, "0 byte csi.dat"
    if record_count > 0:
        return "valid_csi", "verification_only", False, "valid CSI but missing meta.json"
    return "needs_review", "excluded", False, "non-empty csi.dat but no CSI records parsed"


def validate_meta_consistency(meta, file_bytes, record_count):
    messages = []
    if not meta:
        return messages

    capture = meta.get("capture", {})
    validation = meta.get("validation", {})
    meta_bytes = capture.get("csi_file_bytes")
    meta_records = capture.get("csi_record_count")
    if meta_bytes is not None and meta_bytes != file_bytes:
        messages.append("meta csi_file_bytes differs")
    if meta_records is not None and meta_records != record_count:
        messages.append("meta csi_record_count differs")
    if record_count <= 0 and validation.get("valid_csi") is True:
        messages.append("meta valid_csi=true but parser found no records")
    if record_count > 0 and validation.get("valid_csi") is False:
        messages.append("meta valid_csi=false but parser found records")
    return messages


def scan_session(session_dir):
    session_id = os.path.basename(session_dir.rstrip(os.sep))
    csi_path = os.path.join(session_dir, "csi.dat")
    meta_path = os.path.join(session_dir, "meta.json")
    has_csi = os.path.exists(csi_path)
    has_meta = os.path.exists(meta_path)
    file_bytes = os.path.getsize(csi_path) if has_csi else 0
    summary = None
    record_count = 0
    parser_message = ""

    if has_csi and file_bytes > 0:
        try:
            summary = summarize_file(csi_path)
            record_count = int(summary.get("record_count") or 0)
        except Exception as exc:
            parser_message = "parser error: {}".format(exc)

    meta = read_json(meta_path) if has_meta else None

    if meta:
        quality_status = meta.get("quality_status", "")
        dataset_role = meta.get("dataset_role", "")
        use_for_final_training = meta.get("use_for_final_training", "")
        label = meta.get("label", {})
        receiver = meta.get("receiver", {})
        network = meta.get("network", {})
        layout = meta.get("layout", {})
        environment = meta.get("environment", {})
        messages = validate_meta_consistency(meta, file_bytes, record_count)
        if parser_message:
            messages.append(parser_message)
        if not messages:
            messages.append("ok")
    else:
        quality_status, dataset_role, use_for_final_training, msg = infer_without_meta(
            file_bytes, record_count, has_csi
        )
        label = {}
        receiver = {}
        network = {}
        layout = {}
        environment = {}
        messages = [msg]
        if parser_message:
            messages.append(parser_message)

    if not quality_status:
        quality_status, dataset_role, use_for_final_training, msg = infer_without_meta(
            file_bytes, record_count, has_csi
        )
        messages.append("missing quality_status; inferred {}".format(quality_status))
    if not dataset_role:
        dataset_role = "excluded"
        messages.append("missing dataset_role")

    return {
        "session_id": session_id,
        "session_dir": os.path.relpath(session_dir, PROJECT_ROOT),
        "csi_file": os.path.relpath(csi_path, PROJECT_ROOT) if has_csi else "",
        "has_csi": has_csi,
        "has_meta": has_meta,
        "file_bytes": file_bytes,
        "record_count": record_count,
        "quality_status": quality_status,
        "dataset_role": dataset_role,
        "use_for_final_training": use_for_final_training,
        "num_people": label.get("num_people", ""),
        "label_status": label.get("label_status", ""),
        "activity": label.get("activity", ""),
        "rx_kernel": receiver.get("kernel", ""),
        "rx_ip": receiver.get("ip", ""),
        "ap_ssid": network.get("ap_ssid", ""),
        "ap_channel": network.get("ap_channel", ""),
        "ap_frequency_mhz": network.get("ap_frequency_mhz", ""),
        "antenna_holder": layout.get("antenna_holder", ""),
        "room": environment.get("room", ""),
        "environment_note": environment.get("environment_note", ""),
        "antenna_dimensions": as_csv_json(summary.get("antenna_dimensions") if summary else {}),
        "rates": as_csv_json(summary.get("rates") if summary else {}),
        "validation_message": "; ".join(messages),
    }


def find_sessions(raw_dir):
    if not os.path.isdir(raw_dir):
        return []
    sessions = []
    for name in sorted(os.listdir(raw_dir)):
        path = os.path.join(raw_dir, name)
        if os.path.isdir(path) and name.startswith("session_"):
            sessions.append(path)
    return sessions


def print_summary(rows):
    status_counts = {}
    role_counts = {}
    training_count = 0
    for row in rows:
        status_counts[row["quality_status"]] = status_counts.get(row["quality_status"], 0) + 1
        role_counts[row["dataset_role"]] = role_counts.get(row["dataset_role"], 0) + 1
        if str(row["use_for_final_training"]).lower() == "true":
            training_count += 1

    print("Validated {} sessions".format(len(rows)))
    print("quality_status:", status_counts)
    print("dataset_role:", role_counts)
    print("use_for_final_training=true:", training_count)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate CSI raw sessions")
    parser.add_argument("--raw-dir", default=os.path.join(PROJECT_ROOT, "data", "raw"))
    parser.add_argument("--out-csv", default=os.path.join(PROJECT_ROOT, "outputs", "dataset", "session_index.csv"))
    parser.add_argument("--out-json", default=os.path.join(PROJECT_ROOT, "outputs", "dataset", "session_index.json"))
    args = parser.parse_args(argv)

    raw_dir = os.path.abspath(args.raw_dir)
    rows = [scan_session(session_dir) for session_dir in find_sessions(raw_dir)]
    write_csv(args.out_csv, rows)
    output = {
        "created_at": datetime.now(KST).isoformat(timespec="seconds"),
        "raw_dir": os.path.relpath(raw_dir, PROJECT_ROOT),
        "session_count": len(rows),
        "sessions": rows,
    }
    write_json(args.out_json, output)
    print("Wrote {}".format(os.path.relpath(args.out_csv, PROJECT_ROOT)))
    print("Wrote {}".format(os.path.relpath(args.out_json, PROJECT_ROOT)))
    print_summary(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
