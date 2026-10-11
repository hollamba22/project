#!/usr/bin/env python3
"""Extract baseline statistical features from CSI windows."""

import argparse
import csv
import math
import os
import sys
from collections import defaultdict


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CSI_SCRIPT_DIR = os.path.join(PROJECT_ROOT, "scripts", "csi")
if CSI_SCRIPT_DIR not in sys.path:
    sys.path.insert(0, CSI_SCRIPT_DIR)

from csi_parser import iter_csi_records  # noqa: E402


BASE_FIELDS = [
    "window_id",
    "session_id",
    "num_people",
    "label_status",
    "activity",
    "dataset_role",
    "use_for_final_training",
    "start_sec",
    "end_sec",
    "start_packet",
    "end_packet",
    "packet_count",
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
    "rssi_total_mean",
    "noise_mean",
    "agc_mean",
]

PAIR_FEATURES = []
for rx in range(1, 4):
    for tx in range(1, 4):
        PAIR_FEATURES.extend([
            "pair_r{}t{}_mean".format(rx, tx),
            "pair_r{}t{}_std".format(rx, tx),
        ])

SUBCARRIER_FEATURES = []
for sub in range(1, 31):
    SUBCARRIER_FEATURES.extend([
        "sub{:02d}_mean".format(sub),
        "sub{:02d}_std".format(sub),
    ])

FEATURE_FIELDS = BASE_FIELDS + GLOBAL_FEATURES + PAIR_FEATURES + SUBCARRIER_FEATURES


def read_csv(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FEATURE_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in FEATURE_FIELDS})


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
    n = len(values)
    mean = sum(values) / float(n)
    var = sum((x - mean) ** 2 for x in values) / float(n)
    if n % 2:
        median = ordered[n // 2]
    else:
        median = (ordered[n // 2 - 1] + ordered[n // 2]) / 2.0
    energy = sum(x * x for x in values) / float(n)
    return {
        "mean": mean,
        "std": math.sqrt(var),
        "min": min(values),
        "max": max(values),
        "median": median,
        "energy": energy,
    }


def mean(values):
    return sum(values) / float(len(values)) if values else 0.0


def float_text(value):
    return "{:.8f}".format(float(value))


def load_records(csi_file):
    path = csi_file if os.path.isabs(csi_file) else os.path.join(PROJECT_ROOT, csi_file)
    return list(iter_csi_records(path))


def record_amplitudes(record):
    amps = []
    pair_values = defaultdict(list)
    sub_values = defaultdict(list)
    for sub_idx, sub in enumerate(record["csi"], start=1):
        for rx_idx, rx_values in enumerate(sub, start=1):
            for tx_idx, value in enumerate(rx_values, start=1):
                amp = abs(value)
                amps.append(amp)
                pair_values[(rx_idx, tx_idx)].append(amp)
                sub_values[sub_idx].append(amp)
    return amps, pair_values, sub_values


def extract_window_features(window, records):
    start_packet = int(window["start_packet"])
    end_packet = int(window["end_packet"])
    selected = records[start_packet:end_packet]

    all_amps = []
    packet_means = []
    pair_values = defaultdict(list)
    sub_values = defaultdict(list)
    rssi_a = []
    rssi_b = []
    rssi_c = []
    noise = []
    agc = []

    for record in selected:
        amps, record_pairs, record_subs = record_amplitudes(record)
        all_amps.extend(amps)
        packet_means.append(mean(amps))
        for key, values in record_pairs.items():
            pair_values[key].extend(values)
        for key, values in record_subs.items():
            sub_values[key].extend(values)
        rssi_a.append(float(record["rssi_a"]))
        rssi_b.append(float(record["rssi_b"]))
        rssi_c.append(float(record["rssi_c"]))
        noise.append(float(record["noise"]))
        agc.append(float(record["agc"]))

    amp_stats = stats(all_amps)
    packet_stats = stats(packet_means)
    diffs = [abs(packet_means[i] - packet_means[i - 1]) for i in range(1, len(packet_means))]
    diff_stats = stats(diffs)

    row = {field: window.get(field, "") for field in BASE_FIELDS}
    row.update({
        "amp_mean": float_text(amp_stats["mean"]),
        "amp_std": float_text(amp_stats["std"]),
        "amp_min": float_text(amp_stats["min"]),
        "amp_max": float_text(amp_stats["max"]),
        "amp_median": float_text(amp_stats["median"]),
        "amp_energy": float_text(amp_stats["energy"]),
        "packet_amp_mean_mean": float_text(packet_stats["mean"]),
        "packet_amp_mean_std": float_text(packet_stats["std"]),
        "packet_amp_diff_abs_mean": float_text(diff_stats["mean"]),
        "packet_amp_diff_abs_std": float_text(diff_stats["std"]),
        "rssi_a_mean": float_text(mean(rssi_a)),
        "rssi_b_mean": float_text(mean(rssi_b)),
        "rssi_c_mean": float_text(mean(rssi_c)),
        "rssi_total_mean": float_text(mean([a + b + c for a, b, c in zip(rssi_a, rssi_b, rssi_c)])),
        "noise_mean": float_text(mean(noise)),
        "agc_mean": float_text(mean(agc)),
    })

    for rx in range(1, 4):
        for tx in range(1, 4):
            pair_stats = stats(pair_values.get((rx, tx), []))
            row["pair_r{}t{}_mean".format(rx, tx)] = float_text(pair_stats["mean"])
            row["pair_r{}t{}_std".format(rx, tx)] = float_text(pair_stats["std"])

    for sub in range(1, 31):
        sub_stats = stats(sub_values.get(sub, []))
        row["sub{:02d}_mean".format(sub)] = float_text(sub_stats["mean"])
        row["sub{:02d}_std".format(sub)] = float_text(sub_stats["std"])

    return row


def main(argv=None):
    parser = argparse.ArgumentParser(description="Extract statistical features from CSI windows")
    parser.add_argument("--windows-csv", default=os.path.join(PROJECT_ROOT, "data", "processed", "windows.csv"))
    parser.add_argument("--out-csv", default=os.path.join(PROJECT_ROOT, "data", "processed", "features.csv"))
    parser.add_argument("--max-windows", type=int, default=None)
    args = parser.parse_args(argv)

    windows = read_csv(args.windows_csv)
    if args.max_windows is not None:
        windows = windows[:args.max_windows]

    by_file = defaultdict(list)
    for window in windows:
        by_file[window["csi_file"]].append(window)

    rows = []
    for csi_file, file_windows in sorted(by_file.items()):
        records = load_records(csi_file)
        for window in file_windows:
            rows.append(extract_window_features(window, records))

    write_csv(args.out_csv, rows)
    print("Wrote {}".format(os.path.relpath(args.out_csv, PROJECT_ROOT)))
    print("feature_rows={}".format(len(rows)))
    if not rows:
        print("No feature rows. Generate windows first, or use make_windows.py --include-verification for dry runs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
