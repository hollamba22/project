#!/usr/bin/env python3
"""Run the saved research prototype on an existing CSI window_features.csv."""
import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--features-csv', required=True)
    p.add_argument('--model', default=str(ROOT / 'outputs/people_count_analysis_20260914/people_count_rf_prototype.joblib'))
    p.add_argument('--out-csv', required=True)
    args = p.parse_args()
    rows = list(csv.DictReader(open(args.features_csv)))
    if not rows:
        p.error('Feature CSV is empty')
    if args.model.endswith('.json'):
        sys.path.insert(0, str(ROOT / 'scripts/train'))
        import train_baseline
        model = json.loads(Path(args.model).read_text())
        predictions = [int(train_baseline.predict_one(row, model)) for row in rows]
    else:
        sys.path.insert(0, str(ROOT / 'outputs/csi_analysis_env'))
        import joblib
        import numpy as np
        # Only load this locally generated, trusted model artifact.
        model = joblib.load(args.model)
        x = np.asarray([[float(row[k]) for k in model['feature_names']] for row in rows])
        if model.get('divide_by'):
            denominator = np.array([float(row[model['divide_by']]) for row in rows])[:, None]
            x = x / np.maximum(denominator, 1e-9)
        if not np.isfinite(x).all():
            p.error('Nonfinite CSI features')
        predictions = model['model'].predict(x).astype(int).tolist()
    with open(args.out_csv, 'w', newline='') as f:
        fields = ['window_id', 'start_sec', 'predicted_people']
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader()
        for i, (row, prediction) in enumerate(zip(rows, predictions)):
            writer.writerow(dict(window_id=row.get('window_id', str(i)),
                                 start_sec=row.get('start_sec', ''), predicted_people=prediction))
    print(json.dumps(dict(windows=len(rows), predicted_counts=dict(Counter(predictions)),
                          output=args.out_csv, scope='research prototype; labels 0-3 only; new-session accuracy unvalidated'),
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
