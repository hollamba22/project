#!/usr/bin/env python3
"""Evaluate a saved baseline model on a feature CSV."""

import argparse
import csv
import json
import os
import sys


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


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


def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def mean(values):
    return sum(values) / float(len(values)) if values else 0.0


def vector(row, feature_names):
    return [float(row[name]) for name in feature_names]


def scale_vector(values, features, scaler):
    return [
        (value - scaler["mean"][name]) / scaler["std"][name]
        for value, name in zip(values, features)
    ]


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


def build_predictions(rows, model):
    predictions = []
    for row in rows:
        pred = predict_one(row, model)
        true = str(row["num_people"])
        predictions.append({
            "window_id": row["window_id"],
            "session_id": row["session_id"],
            "true_label": true,
            "pred_label": str(pred),
            "correct": str(true == str(pred)),
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


def filter_rows(rows, split, mode):
    if mode == "all":
        return rows
    if mode == "train":
        allowed = set(split.get("train_sessions", []))
    elif mode == "test":
        allowed = set(split.get("test_sessions", []))
    else:
        raise ValueError("unknown eval mode: {}".format(mode))
    return [row for row in rows if row["session_id"] in allowed]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Evaluate saved CSI baseline model")
    parser.add_argument("--features-csv", default=os.path.join(PROJECT_ROOT, "data", "processed", "features.csv"))
    parser.add_argument("--model", default=os.path.join(PROJECT_ROOT, "outputs", "models", "baseline_model.json"))
    parser.add_argument("--split", default=os.path.join(PROJECT_ROOT, "outputs", "models", "baseline_split.json"))
    parser.add_argument("--mode", choices=["test", "train", "all"], default="test")
    parser.add_argument("--predictions-out", default=os.path.join(PROJECT_ROOT, "outputs", "evaluation", "model_predictions.csv"))
    parser.add_argument("--metrics-out", default=os.path.join(PROJECT_ROOT, "outputs", "evaluation", "model_metrics.json"))
    args = parser.parse_args(argv)

    rows = read_csv(args.features_csv)
    model = read_json(args.model)
    split = read_json(args.split) if os.path.exists(args.split) else {}
    rows = filter_rows(rows, split, args.mode)
    if not rows:
        raise SystemExit("No rows selected for evaluation mode={!r}".format(args.mode))

    labels = sorted(set(model.get("labels", [])) | {str(row["num_people"]) for row in rows})
    predictions = build_predictions(rows, model)
    metrics = metrics_from_predictions(predictions, labels)
    write_csv(args.predictions_out, predictions, ["window_id", "session_id", "true_label", "pred_label", "correct"])
    write_json(args.metrics_out, metrics)

    print("Wrote {}".format(os.path.relpath(args.predictions_out, PROJECT_ROOT)))
    print("Wrote {}".format(os.path.relpath(args.metrics_out, PROJECT_ROOT)))
    print("mode={}, rows={}, accuracy={:.4f}, macro_f1={:.4f}".format(
        args.mode, len(rows), metrics["accuracy"], metrics["macro_f1"]
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
