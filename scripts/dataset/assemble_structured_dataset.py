#!/usr/bin/env python3
"""Combine per-session structured CSI feature CSVs into one ML table."""

import argparse
import csv
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
KST = timezone(timedelta(hours=9))


def read_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path, data):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def find_session_outputs(structured_dir):
    outputs = []
    if not os.path.isdir(structured_dir):
        return outputs
    for name in sorted(os.listdir(structured_dir)):
        session_dir = os.path.join(structured_dir, name)
        feature_path = os.path.join(session_dir, "window_features.csv")
        manifest_path = os.path.join(session_dir, "manifest.json")
        if os.path.isfile(feature_path) and os.path.isfile(manifest_path):
            outputs.append((feature_path, manifest_path))
    return outputs


def should_include(manifest, args):
    quality = manifest.get("quality", {})
    label = manifest.get("label", {})
    if not label.get("has_trainable_label", False):
        return False, "missing label"
    status = quality.get("status", "")
    if status == "failed":
        return False, "failed quality"
    if status == "needs_review" and not args.include_needs_review:
        return False, "needs_review excluded"
    if quality.get("final_training_allowed", False):
        return True, "final training"
    if args.include_prototype:
        return True, "prototype included"
    return False, "prototype excluded"


def assemble(args):
    structured_dir = os.path.abspath(args.structured_dir)
    discovered = find_session_outputs(structured_dir)
    selected = []
    excluded = []
    expected_fields = None
    all_rows = []
    label_counts = Counter()
    session_counts = Counter()

    for feature_path, manifest_path in discovered:
        manifest = read_json(manifest_path)
        include, reason = should_include(manifest, args)
        session_id = manifest.get("session_id", os.path.basename(os.path.dirname(feature_path)))
        if not include:
            excluded.append({"session_id": session_id, "reason": reason})
            continue

        with open(feature_path, "r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = list(reader.fieldnames or [])
            if expected_fields is None:
                expected_fields = fields
            elif fields != expected_fields:
                excluded.append({"session_id": session_id, "reason": "feature schema mismatch"})
                continue
            rows = list(reader)

        for row in rows:
            label = str(row.get("num_people", ""))
            label_counts[label] += 1
            session_counts[session_id] += 1
            all_rows.append(row)
        selected.append({
            "session_id": session_id,
            "reason": reason,
            "quality_status": manifest.get("quality", {}).get("status"),
            "environment": manifest.get("environment", {}),
            "rows": len(rows),
            "feature_file": os.path.relpath(feature_path, PROJECT_ROOT),
            "feature_sha256": sha256_file(feature_path),
        })

    if expected_fields is None:
        expected_fields = []
    parent = os.path.dirname(os.path.abspath(args.out_csv))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(args.out_csv, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=expected_fields)
        if expected_fields:
            writer.writeheader()
            for row in all_rows:
                writer.writerow({field: row.get(field, "") for field in expected_fields})

    output_manifest = {
        "schema_version": "1.0-prototype",
        "created_at": datetime.now(KST).isoformat(timespec="seconds"),
        "structured_dir": os.path.relpath(structured_dir, PROJECT_ROOT),
        "output_csv": os.path.relpath(os.path.abspath(args.out_csv), PROJECT_ROOT),
        "selection": {
            "include_prototype": args.include_prototype,
            "include_needs_review": args.include_needs_review,
        },
        "session_count": len(selected),
        "row_count": len(all_rows),
        "label_window_counts": dict(label_counts),
        "session_window_counts": dict(session_counts),
        "selected_sessions": selected,
        "excluded_sessions": excluded,
        "feature_columns": expected_fields,
    }
    write_json(args.out_manifest, output_manifest)

    print("Wrote {}".format(os.path.relpath(args.out_csv, PROJECT_ROOT)))
    print("Wrote {}".format(os.path.relpath(args.out_manifest, PROJECT_ROOT)))
    print("sessions={}, rows={}, labels={}".format(
        len(selected), len(all_rows), dict(label_counts)
    ))
    if not all_rows:
        print("No sessions selected. Use --include-prototype for pre-holder dry runs.")
        return 2
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description="Assemble structured CSI sessions")
    parser.add_argument(
        "--structured-dir",
        default=os.path.join(PROJECT_ROOT, "data", "structured"),
    )
    parser.add_argument(
        "--out-csv",
        default=os.path.join(PROJECT_ROOT, "data", "processed", "structured_dataset.csv"),
    )
    parser.add_argument(
        "--out-manifest",
        default=os.path.join(PROJECT_ROOT, "data", "processed", "structured_dataset_manifest.json"),
    )
    parser.add_argument("--include-prototype", action="store_true")
    parser.add_argument("--include-needs-review", action="store_true")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return assemble(args)


if __name__ == "__main__":
    sys.exit(main())
