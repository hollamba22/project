#!/usr/bin/env python3
"""Stream an Intel 5300 CSI session into a trainable window feature table.

The script keeps only the active overlapping windows in memory, so an hour-long
capture can be processed without loading every CSI matrix at once.
"""

import argparse
import csv
import hashlib
import json
import math
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CSI_SCRIPT_DIR = os.path.join(PROJECT_ROOT, "scripts", "csi")
if CSI_SCRIPT_DIR not in sys.path:
    sys.path.insert(0, CSI_SCRIPT_DIR)

from csi_parser import (  # noqa: E402
    CSIParseError,
    TimestampUnwrapper,
    get_scaled_csi,
    get_total_rss_dbm,
    iter_csi_records,
)


KST = timezone(timedelta(hours=9))
NUM_SUBCARRIERS = 30


BASE_FIELDS = [
    "window_id",
    "session_id",
    "num_people",
    "label_status",
    "activity",
    "dataset_role",
    "use_for_final_training",
    "csi_mode",
    "expected_nrx",
    "expected_ntx",
    "start_sec",
    "end_sec",
    "packet_count",
    "skipped_dimension_packets",
    "first_packet_sec",
    "last_packet_sec",
    "max_gap_ms",
    "gaps_gt_50ms",
    "gaps_gt_100ms",
]


GLOBAL_FEATURES = [
    "amp_mean",
    "amp_std",
    "amp_min",
    "amp_max",
    "amp_median",
    "amp_energy",
    "packet_amp_mean_mean",
    "packet_amp_mean_std",
    "packet_amp_diff_abs_mean",
    "packet_amp_diff_abs_std",
    "rssi_a_mean",
    "rssi_b_mean",
    "rssi_c_mean",
    "total_rss_dbm_mean",
    "noise_mean",
    "agc_mean",
]


def parse_bool(value):
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def read_json(path):
    if not path or not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path, data):
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


def mean(values):
    return sum(values) / float(len(values)) if values else 0.0


def stats(values):
    if not values:
        return {
            "mean": 0.0,
            "std": 0.0,
            "min": 0.0,
            "max": 0.0,
            "median": 0.0,
            "energy": 0.0,
        }
    ordered = sorted(values)
    count = len(values)
    avg = mean(values)
    variance = sum((value - avg) ** 2 for value in values) / float(count)
    if count % 2:
        median = ordered[count // 2]
    else:
        median = (ordered[count // 2 - 1] + ordered[count // 2]) / 2.0
    return {
        "mean": avg,
        "std": math.sqrt(variance),
        "min": min(values),
        "max": max(values),
        "median": median,
        "energy": sum(value * value for value in values) / float(count),
    }


def float_text(value):
    return "{:.8f}".format(float(value))


def feature_fields(expected_nrx, expected_ntx):
    fields = list(BASE_FIELDS) + list(GLOBAL_FEATURES)
    for rx in range(1, expected_nrx + 1):
        for tx in range(1, expected_ntx + 1):
            fields.extend([
                "pair_r{}t{}_mean".format(rx, tx),
                "pair_r{}t{}_std".format(rx, tx),
            ])
    for subcarrier in range(1, NUM_SUBCARRIERS + 1):
        fields.extend([
            "sub{:02d}_mean".format(subcarrier),
            "sub{:02d}_std".format(subcarrier),
        ])
    return fields


def matrix_amplitudes(matrix):
    amplitudes = []
    pairs = defaultdict(list)
    subcarriers = defaultdict(list)
    for sub_index, subcarrier in enumerate(matrix, start=1):
        for rx_index, tx_values in enumerate(subcarrier, start=1):
            for tx_index, value in enumerate(tx_values, start=1):
                amplitude = abs(value)
                amplitudes.append(amplitude)
                pairs[(rx_index, tx_index)].append(amplitude)
                subcarriers[sub_index].append(amplitude)
    return amplitudes, pairs, subcarriers


class WindowAccumulator(object):

    def __init__(self, start_sec, end_sec):
        self.start_sec = float(start_sec)
        self.end_sec = float(end_sec)
        self.packet_count = 0
        self.skipped_dimension_packets = 0
        self.first_packet_sec = None
        self.last_packet_sec = None
        self.previous_packet_sec = None
        self.max_gap_sec = 0.0
        self.gaps_gt_50ms = 0
        self.gaps_gt_100ms = 0
        self.all_amplitudes = []
        self.packet_means = []
        self.pair_values = defaultdict(list)
        self.subcarrier_values = defaultdict(list)
        self.rssi_a = []
        self.rssi_b = []
        self.rssi_c = []
        self.total_rss_dbm = []
        self.noise = []
        self.agc = []

    def note_dimension_skip(self):
        self.skipped_dimension_packets += 1

    def add(self, record, matrix, relative_sec):
        amplitudes, pairs, subcarriers = matrix_amplitudes(matrix)
        self.packet_count += 1
        self.all_amplitudes.extend(amplitudes)
        self.packet_means.append(mean(amplitudes))
        for key, values in pairs.items():
            self.pair_values[key].extend(values)
        for key, values in subcarriers.items():
            self.subcarrier_values[key].extend(values)

        self.rssi_a.append(float(record["rssi_a"]))
        self.rssi_b.append(float(record["rssi_b"]))
        self.rssi_c.append(float(record["rssi_c"]))
        total_rss = get_total_rss_dbm(record)
        if total_rss is not None:
            self.total_rss_dbm.append(total_rss)
        self.noise.append(float(record["noise"]))
        self.agc.append(float(record["agc"]))

        if self.first_packet_sec is None:
            self.first_packet_sec = relative_sec
        if self.previous_packet_sec is not None:
            gap_sec = max(0.0, relative_sec - self.previous_packet_sec)
            self.max_gap_sec = max(self.max_gap_sec, gap_sec)
            if gap_sec > 0.050:
                self.gaps_gt_50ms += 1
            if gap_sec > 0.100:
                self.gaps_gt_100ms += 1
        self.previous_packet_sec = relative_sec
        self.last_packet_sec = relative_sec

    def to_row(self, index, context, expected_nrx, expected_ntx, csi_mode):
        amp_stats = stats(self.all_amplitudes)
        packet_stats = stats(self.packet_means)
        differences = [
            abs(self.packet_means[idx] - self.packet_means[idx - 1])
            for idx in range(1, len(self.packet_means))
        ]
        difference_stats = stats(differences)

        row = {
            "window_id": "{}_w{:05d}".format(context["session_id"], index),
            "session_id": context["session_id"],
            "num_people": context["num_people"],
            "label_status": context["label_status"],
            "activity": context["activity"],
            "dataset_role": context["dataset_role"],
            "use_for_final_training": context["use_for_final_training"],
            "csi_mode": csi_mode,
            "expected_nrx": expected_nrx,
            "expected_ntx": expected_ntx,
            "start_sec": float_text(self.start_sec),
            "end_sec": float_text(self.end_sec),
            "packet_count": self.packet_count,
            "skipped_dimension_packets": self.skipped_dimension_packets,
            "first_packet_sec": float_text(self.first_packet_sec or 0.0),
            "last_packet_sec": float_text(self.last_packet_sec or 0.0),
            "max_gap_ms": float_text(self.max_gap_sec * 1000.0),
            "gaps_gt_50ms": self.gaps_gt_50ms,
            "gaps_gt_100ms": self.gaps_gt_100ms,
            "amp_mean": float_text(amp_stats["mean"]),
            "amp_std": float_text(amp_stats["std"]),
            "amp_min": float_text(amp_stats["min"]),
            "amp_max": float_text(amp_stats["max"]),
            "amp_median": float_text(amp_stats["median"]),
            "amp_energy": float_text(amp_stats["energy"]),
            "packet_amp_mean_mean": float_text(packet_stats["mean"]),
            "packet_amp_mean_std": float_text(packet_stats["std"]),
            "packet_amp_diff_abs_mean": float_text(difference_stats["mean"]),
            "packet_amp_diff_abs_std": float_text(difference_stats["std"]),
            "rssi_a_mean": float_text(mean(self.rssi_a)),
            "rssi_b_mean": float_text(mean(self.rssi_b)),
            "rssi_c_mean": float_text(mean(self.rssi_c)),
            "total_rss_dbm_mean": float_text(mean(self.total_rss_dbm)),
            "noise_mean": float_text(mean(self.noise)),
            "agc_mean": float_text(mean(self.agc)),
        }

        for rx in range(1, expected_nrx + 1):
            for tx in range(1, expected_ntx + 1):
                pair_stats = stats(self.pair_values.get((rx, tx), []))
                row["pair_r{}t{}_mean".format(rx, tx)] = float_text(pair_stats["mean"])
                row["pair_r{}t{}_std".format(rx, tx)] = float_text(pair_stats["std"])

        for subcarrier in range(1, NUM_SUBCARRIERS + 1):
            subcarrier_stats = stats(self.subcarrier_values.get(subcarrier, []))
            row["sub{:02d}_mean".format(subcarrier)] = float_text(subcarrier_stats["mean"])
            row["sub{:02d}_std".format(subcarrier)] = float_text(subcarrier_stats["std"])
        return row


def session_context(session_dir, meta, label_override):
    session_id = os.path.basename(os.path.abspath(session_dir).rstrip(os.sep))
    label = meta.get("label", {})
    num_people = label_override if label_override is not None else label.get("num_people")
    return {
        "session_id": session_id,
        "num_people": "" if num_people is None else num_people,
        "label_status": label.get("label_status", "unknown"),
        "activity": label.get("activity", "unknown"),
        "dataset_role": meta.get("dataset_role", "verification_only"),
        "use_for_final_training": meta.get("use_for_final_training", False),
    }


def write_feature_csv(path, fields, rows):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def build_dataset(args):
    session_dir = os.path.abspath(args.session_dir)
    csi_path = os.path.join(session_dir, args.csi_file)
    meta_path = os.path.join(session_dir, "meta.json")
    if not os.path.isfile(csi_path):
        raise SystemExit("Missing CSI file: {}".format(csi_path))
    if os.path.getsize(csi_path) <= 0:
        raise SystemExit("CSI file is empty: {}".format(csi_path))

    meta = read_json(meta_path)
    context = session_context(session_dir, meta, args.num_people)
    output_dir = os.path.abspath(
        args.output_dir or os.path.join(PROJECT_ROOT, "data", "structured", context["session_id"])
    )
    os.makedirs(output_dir, exist_ok=True)
    feature_path = os.path.join(output_dir, "window_features.csv")
    manifest_path = os.path.join(output_dir, "manifest.json")
    if not args.overwrite and (os.path.exists(feature_path) or os.path.exists(manifest_path)):
        raise SystemExit("Output already exists; use --overwrite: {}".format(output_dir))

    fields = feature_fields(args.expected_nrx, args.expected_ntx)
    rows = []
    active = []
    next_window_start = 0.0
    unwrapper = TimestampUnwrapper()
    first_timestamp = None
    last_relative_sec = 0.0
    total_records = 0
    accepted_records = 0
    skipped_dimension_records = 0
    invalid_permutation_records = 0
    scaling_error_records = 0
    dropped_short_windows = 0
    dimension_counts = Counter()
    rate_counts = Counter()
    permutation_counts = Counter()

    def finish_window(window):
        nonlocal dropped_short_windows
        if window.packet_count < args.min_packets:
            dropped_short_windows += 1
            return
        rows.append(window.to_row(
            len(rows), context, args.expected_nrx, args.expected_ntx, args.csi_mode
        ))

    for record in iter_csi_records(csi_path, strict=args.strict):
        total_records += 1
        dimension_key = "{}x{}".format(record["Nrx"], record["Ntx"])
        dimension_counts[dimension_key] += 1
        rate_counts[record["rate_hex"]] += 1
        permutation_key = "-".join(str(value) for value in record["perm"][:record["Nrx"]])
        permutation_counts[permutation_key] += 1
        if not record["permutation_valid"]:
            invalid_permutation_records += 1

        timestamp = unwrapper.update(record["timestamp_low"])
        if first_timestamp is None:
            first_timestamp = timestamp
        relative_sec = (timestamp - first_timestamp) / 1000000.0
        last_relative_sec = max(last_relative_sec, relative_sec)

        while next_window_start <= relative_sec + 1e-12:
            active.append(WindowAccumulator(
                next_window_start, next_window_start + args.window_size_sec
            ))
            next_window_start += args.stride_sec

        remaining = []
        for window in active:
            if window.end_sec <= relative_sec + 1e-12:
                finish_window(window)
            else:
                remaining.append(window)
        active = remaining

        matching_dimension = (
            int(record["Nrx"]) == args.expected_nrx
            and int(record["Ntx"]) == args.expected_ntx
        )
        relevant_windows = [
            window for window in active
            if window.start_sec <= relative_sec < window.end_sec
        ]
        if not matching_dimension:
            skipped_dimension_records += 1
            for window in relevant_windows:
                window.note_dimension_skip()
            continue

        try:
            matrix = get_scaled_csi(record) if args.csi_mode == "scaled" else record["csi"]
        except CSIParseError:
            scaling_error_records += 1
            continue

        accepted_records += 1
        for window in relevant_windows:
            window.add(record, matrix, relative_sec)

    for window in active:
        if window.end_sec <= last_relative_sec + 1e-12:
            finish_window(window)

    write_feature_csv(feature_path, fields, rows)
    has_label = context["num_people"] != ""
    final_training_requested = parse_bool(context["use_for_final_training"])
    quality_status = (
        "valid_training_candidate" if final_training_requested else "valid_prototype"
    )
    review_reasons = []
    if not rows:
        quality_status = "failed"
        review_reasons.append("no windows met the minimum packet requirement")
    if skipped_dimension_records:
        review_reasons.append("{} records had unexpected antenna dimensions".format(
            skipped_dimension_records
        ))
    if invalid_permutation_records:
        review_reasons.append("{} records had invalid antenna permutations".format(
            invalid_permutation_records
        ))
    if scaling_error_records:
        review_reasons.append("{} records could not be scaled".format(scaling_error_records))
    if quality_status != "failed" and review_reasons:
        quality_status = "needs_review"

    final_training_allowed = (
        final_training_requested
        and has_label
        and quality_status != "failed"
        and not review_reasons
    )
    if final_training_requested:
        quality_note = (
            "Training-candidate data captured with the antenna fixture recorded in meta.json."
        )
    elif meta.get("dataset_role") == "test_candidate":
        quality_note = "Held-out test recording; occupancy is unknown until annotation; excluded from training."
    else:
        quality_note = "Prototype data; excluded from final training by meta.json."

    manifest = {
        "schema_version": "1.1",
        "created_at": datetime.now(KST).isoformat(timespec="seconds"),
        "session_id": context["session_id"],
        "source": {
            "csi_file": os.path.relpath(csi_path, PROJECT_ROOT),
            "meta_file": os.path.relpath(meta_path, PROJECT_ROOT) if os.path.exists(meta_path) else None,
            "file_bytes": os.path.getsize(csi_path),
            "sha256": sha256_file(csi_path),
        },
        "label": {
            "num_people": context["num_people"],
            "label_status": context["label_status"],
            "activity": context["activity"],
            "has_trainable_label": has_label,
        },
        "environment": {
            "room": meta.get("environment", {}).get("room", "unknown"),
            "setup_id": meta.get("environment", {}).get("setup_id", "unknown"),
            "empty_reference_session_id": meta.get("environment", {}).get("empty_reference_session_id"),
        },
        "configuration": {
            "csi_mode": args.csi_mode,
            "window_size_sec": args.window_size_sec,
            "stride_sec": args.stride_sec,
            "min_packets": args.min_packets,
            "expected_nrx": args.expected_nrx,
            "expected_ntx": args.expected_ntx,
            "timestamp_source": "Intel 5300 timestamp_low (microseconds, unwrapped)",
            "rx_permutation_applied": True,
        },
        "records": {
            "total": total_records,
            "accepted": accepted_records,
            "skipped_dimension": skipped_dimension_records,
            "invalid_permutation": invalid_permutation_records,
            "scaling_errors": scaling_error_records,
            "observed_duration_sec": last_relative_sec,
            "antenna_dimensions": dict(dimension_counts),
            "rates": dict(rate_counts),
            "permutations": dict(permutation_counts),
        },
        "windows": {
            "kept": len(rows),
            "dropped_short": dropped_short_windows,
            "feature_count": max(0, len(fields) - len(BASE_FIELDS)),
        },
        "quality": {
            "status": quality_status,
            "review_reasons": review_reasons,
            "final_training_allowed": final_training_allowed,
            "note": quality_note,
        },
        "outputs": {
            "window_features_csv": os.path.relpath(feature_path, PROJECT_ROOT),
        },
    }
    write_json(manifest_path, manifest)

    print("Wrote {}".format(os.path.relpath(feature_path, PROJECT_ROOT)))
    print("Wrote {}".format(os.path.relpath(manifest_path, PROJECT_ROOT)))
    print("records total={}, accepted={}, skipped_dimension={}".format(
        total_records, accepted_records, skipped_dimension_records
    ))
    print("duration_sec={:.3f}, windows kept={}, dropped_short={}".format(
        last_relative_sec, len(rows), dropped_short_windows
    ))
    print("quality_status={}, trainable_label={}".format(quality_status, has_label))
    return 0 if rows else 2


def build_parser():
    parser = argparse.ArgumentParser(
        description="Build a timestamp-based trainable CSI window feature dataset"
    )
    parser.add_argument("session_dir", help="data/raw/session_YYYYMMDD_HHMMSS")
    parser.add_argument("--csi-file", default="csi.dat")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--num-people", type=int, default=None, help="override label from meta.json")
    parser.add_argument("--csi-mode", choices=["raw", "scaled"], default="scaled")
    parser.add_argument("--expected-nrx", type=int, default=3)
    parser.add_argument("--expected-ntx", type=int, default=2)
    parser.add_argument("--window-size-sec", type=float, default=2.0)
    parser.add_argument("--stride-sec", type=float, default=1.0)
    parser.add_argument("--min-packets", type=int, default=40)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.window_size_sec <= 0 or args.stride_sec <= 0:
        parser.error("window and stride must be positive")
    if args.min_packets <= 0:
        parser.error("--min-packets must be positive")
    return build_dataset(args)


if __name__ == "__main__":
    sys.exit(main())
