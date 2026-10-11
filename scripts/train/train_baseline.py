#!/usr/bin/env python3
"""Train a small standard-library baseline classifier.

The default model is nearest-centroid. It is intentionally simple so the full
pipeline can run before installing scikit-learn.
"""

import argparse
import csv
import json
import math
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
KST = timezone(timedelta(hours=9))

NON_FEATURE_COLUMNS = {
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
    "csi_mode",
    "expected_nrx",
    "expected_ntx",
    "skipped_dimension_packets",
    "first_packet_sec",
    "last_packet_sec",
    "max_gap_ms",
    "gaps_gt_50ms",
    "gaps_gt_100ms",
}


def read_csv(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fields):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_json(path, data):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def numeric_feature_names(rows):
    if not rows:
        return []
    names = []
    for key in rows[0].keys():
        if key in NON_FEATURE_COLUMNS:
            continue
        ok = True
        for row in rows:
            try:
                float(row.get(key, ""))
            except (TypeError, ValueError):
                ok = False
                break
        if ok:
            names.append(key)
    return names


def vector(row, features):
    return [float(row[name]) for name in features]


def mean(values):
    return sum(values) / float(len(values)) if values else 0.0


def std(values):
    if not values:
        return 1.0
    m = mean(values)
    v = sum((x - m) ** 2 for x in values) / float(len(values))
    s = math.sqrt(v)
    return s if s > 1e-12 else 1.0


def fit_scaler(rows, features):
    cols = {name: [] for name in features}
    for row in rows:
        for name in features:
            cols[name].append(float(row[name]))
    return {
        "mean": {name: mean(cols[name]) for name in features},
        "std": {name: std(cols[name]) for name in features},
    }


def scale_vector(values, features, scaler):
    return [
        (value - scaler["mean"][name]) / scaler["std"][name]
        for value, name in zip(values, features)
    ]


def group_by_label_session(rows):
    grouped = defaultdict(lambda: defaultdict(list))
    for row in rows:
        grouped[str(row["num_people"])][row["session_id"]].append(row)
    return grouped


def split_by_session(rows, test_ratio):
    grouped = group_by_label_session(rows)
    train = []
    test = []
    for _label, sessions in sorted(grouped.items()):
        session_ids = sorted(sessions)
        if len(session_ids) == 1:
            train.extend(sessions[session_ids[0]])
            continue
        test_count = max(1, int(round(len(session_ids) * test_ratio)))
        test_ids = set(session_ids[-test_count:])
        for session_id in session_ids:
            if session_id in test_ids:
                test.extend(sessions[session_id])
            else:
                train.extend(sessions[session_id])
    return train, test


def fit_nearest_centroid(rows, features, scaler):
    vectors_by_label = defaultdict(list)
    for row in rows:
        values = scale_vector(vector(row, features), features, scaler)
        vectors_by_label[str(row["num_people"])].append(values)

    centroids = {}
    for label, vectors in vectors_by_label.items():
        centroid = []
        for idx in range(len(features)):
            centroid.append(mean([v[idx] for v in vectors]))
        centroids[label] = centroid
    return centroids


def predict_one(row, model):
    labels = model["labels"]
    if model["classifier"] == "majority" or len(labels) <= 1:
        return model["majority_label"]

    features = model["feature_names"]
    values = scale_vector(vector(row, features), features, model["scaler"])
    best_label = None
    best_dist = None
    for label, centroid in model["centroids"].items():
        dist = sum((a - b) ** 2 for a, b in zip(values, centroid))
        if best_dist is None or dist < best_dist:
            best_label = label
            best_dist = dist
    return best_label


def evaluate(rows, model):
    predictions = []
    for row in rows:
        pred = predict_one(row, model)
        predictions.append({
            "window_id": row["window_id"],
            "session_id": row["session_id"],
            "true_label": str(row["num_people"]),
            "pred_label": str(pred),
            "correct": str(str(row["num_people"]) == str(pred)),
        })
    return predictions


def metrics_from_predictions(predictions, labels):
    total = len(predictions)
    correct = sum(1 for row in predictions if row["correct"] == "True")
    accuracy = correct / float(total) if total else 0.0

    matrix = {true: {pred: 0 for pred in labels} for true in labels}
    for row in predictions:
        true = row["true_label"]
        pred = row["pred_label"]
        matrix.setdefault(true, {label: 0 for label in labels})
        matrix[true].setdefault(pred, 0)
        matrix[true][pred] += 1

    per_class = {}
    f1_values = []
    for label in labels:
        tp = matrix.get(label, {}).get(label, 0)
        fp = sum(matrix.get(other, {}).get(label, 0) for other in matrix if other != label)
        fn = sum(value for pred, value in matrix.get(label, {}).items() if pred != label)
        precision = tp / float(tp + fp) if tp + fp else 0.0
        recall = tp / float(tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / float(precision + recall) if precision + recall else 0.0
        per_class[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": sum(matrix.get(label, {}).values()),
        }
        f1_values.append(f1)

    return {
        "accuracy": accuracy,
        "macro_f1": mean(f1_values),
        "total": total,
        "correct": correct,
        "labels": labels,
        "per_class": per_class,
        "confusion_matrix": matrix,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Train nearest-centroid baseline on CSI features")
    parser.add_argument("--features-csv", default=os.path.join(PROJECT_ROOT, "data", "processed", "features.csv"))
    parser.add_argument("--model-out", default=os.path.join(PROJECT_ROOT, "outputs", "models", "baseline_model.json"))
    parser.add_argument("--split-out", default=os.path.join(PROJECT_ROOT, "outputs", "models", "baseline_split.json"))
    parser.add_argument("--predictions-out", default=os.path.join(PROJECT_ROOT, "outputs", "evaluation", "baseline_predictions.csv"))
    parser.add_argument("--metrics-out", default=os.path.join(PROJECT_ROOT, "outputs", "evaluation", "baseline_metrics.json"))
    parser.add_argument("--classifier", choices=["nearest_centroid", "majority"], default="nearest_centroid")
    parser.add_argument("--test-ratio", type=float, default=0.25)
    args = parser.parse_args(argv)

    rows = read_csv(args.features_csv)
    rows = [row for row in rows if row.get("num_people", "") != ""]
    if not rows:
        raise SystemExit("No feature rows with labels found: {}".format(args.features_csv))

    features = numeric_feature_names(rows)
    if not features:
        raise SystemExit("No numeric feature columns found")

    train_rows, test_rows = split_by_session(rows, args.test_ratio)
    if not train_rows:
        raise SystemExit("No training rows after session split")

    labels = sorted({str(row["num_people"]) for row in rows})
    majority_label = Counter(str(row["num_people"]) for row in train_rows).most_common(1)[0][0]
    scaler = fit_scaler(train_rows, features)
    centroids = fit_nearest_centroid(train_rows, features, scaler)

    classifier = args.classifier
    if len(labels) <= 1 and classifier != "majority":
        print("Only one class is present; using majority behavior for predictions.")

    model = {
        "created_at": datetime.now(KST).isoformat(timespec="seconds"),
        "classifier": classifier,
        "feature_names": features,
        "labels": labels,
        "majority_label": majority_label,
        "scaler": scaler,
        "centroids": centroids,
        "train_window_count": len(train_rows),
        "test_window_count": len(test_rows),
        "train_sessions": sorted({row["session_id"] for row in train_rows}),
        "test_sessions": sorted({row["session_id"] for row in test_rows}),
    }

    write_json(args.model_out, model)
    write_json(args.split_out, {
        "train_window_count": len(train_rows),
        "test_window_count": len(test_rows),
        "train_sessions": model["train_sessions"],
        "test_sessions": model["test_sessions"],
        "labels": labels,
    })

    eval_rows = test_rows if test_rows else train_rows
    predictions = evaluate(eval_rows, model)
    metrics = metrics_from_predictions(predictions, labels)
    write_csv(args.predictions_out, predictions, ["window_id", "session_id", "true_label", "pred_label", "correct"])
    write_json(args.metrics_out, metrics)

    print("Wrote {}".format(os.path.relpath(args.model_out, PROJECT_ROOT)))
    print("Wrote {}".format(os.path.relpath(args.split_out, PROJECT_ROOT)))
    print("Wrote {}".format(os.path.relpath(args.predictions_out, PROJECT_ROOT)))
    print("Wrote {}".format(os.path.relpath(args.metrics_out, PROJECT_ROOT)))
    print("train_windows={}, test_windows={}, labels={}".format(len(train_rows), len(test_rows), labels))
    print("accuracy={:.4f}, macro_f1={:.4f}".format(metrics["accuracy"], metrics["macro_f1"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
