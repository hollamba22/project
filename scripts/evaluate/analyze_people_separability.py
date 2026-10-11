#!/usr/bin/env python3
"""Reproducible, offline CSI separability audit for 2026-09-02 and 2026-09-13.

Uses the existing, SHA-256-verified 2 s feature tables. No acquisition metadata,
filenames, times, or labels are model inputs. Temporal tests measure separation
within the four recorded sessions, NOT generalization to new sessions/rooms.
Dependencies may be installed in outputs/csi_analysis_env (Python 3.6 compatible).
"""
import argparse
import csv
import hashlib
import json
import os
import struct
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'outputs/csi_analysis_env'))
sys.path.insert(0, str(ROOT / 'scripts/train'))
sys.path.insert(0, str(ROOT / 'scripts/csi'))
os.environ.setdefault('MPLCONFIGDIR', '/tmp/csi-matplotlib-config')
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '1')
import numpy as np
import scipy
import sklearn
import joblib
from sklearn.base import clone
from sklearn.decomposition import PCA
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split
from sklearn.neighbors import NearestCentroid
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
import train_baseline
from csi_parser import parse_bfee_payload

SEED = 20260914
KST = timezone(timedelta(hours=9))
LABELS = [0, 1, 2, 3]
RADIO = ['rssi_a_mean', 'rssi_b_mean', 'rssi_c_mean',
         'total_rss_dbm_mean', 'noise_mean', 'agc_mean']


def read_json(p):
    return json.loads(Path(p).read_text())


def write_json(p, data):
    Path(p).write_text(json.dumps(data, ensure_ascii=False, indent=2,
                                sort_keys=True, allow_nan=False) + '\n')


def write_csv(p, rows):
    if not rows:
        return
    with Path(p).open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def raw_audit(path):
    """Check every frame boundary/header; sample-decode complex CSI matrices."""
    raw = path.read_bytes()
    offset = 0
    timestamp, dims, rates, noise, agc, permutations = [], Counter(), Counter(), [], [], Counter()
    issues, decoded = [], 0
    while offset < len(raw):
        begin = offset
        if offset + 2 > len(raw):
            issues.append('truncated length at {}'.format(offset)); break
        size = struct.unpack_from('>H', raw, offset)[0]
        offset += 2
        if size == 0 or size > 4096 or offset + size > len(raw):
            issues.append('invalid frame at {}'.format(begin)); break
        payload = raw[offset:offset + size]
        offset += size
        if payload[0] != 0xBB:
            continue
        b = payload[1:]
        if len(b) < 20:
            issues.append('short header at {}'.format(begin)); continue
        nrx, ntx = b[8], b[9]
        expected = (30 * (nrx * ntx * 16 + 3) + 7) // 8
        declared = struct.unpack_from('<H', b, 16)[0]
        if not 1 <= nrx <= 3 or not 1 <= ntx <= 3 or declared != expected or len(b) != 20 + expected:
            issues.append('matrix length/dimensions at {}'.format(begin)); continue
        perm = [((b[15] >> k) & 3) + 1 for k in (0, 2, 4)][:nrx]
        if sorted(perm) != list(range(1, nrx + 1)):
            issues.append('invalid permutation at {}'.format(begin))
        if len(timestamp) < 20 or len(timestamp) % 997 == 0:
            parse_bfee_payload(b)
            decoded += 1
        timestamp.append(struct.unpack_from('<I', b, 0)[0])
        dims['{}x{}'.format(nrx, ntx)] += 1
        rates['0x{:04x}'.format(struct.unpack_from('<H', b, 18)[0])] += 1
        noise.append(b[13] - 256 if b[13] >= 128 else b[13])
        agc.append(b[14])
        permutations['-'.join(map(str, perm))] += 1
    delta = np.diff(np.asarray(timestamp, dtype=np.int64))
    delta[delta < -(2 ** 31)] += 2 ** 32
    relative = np.concatenate(([0], np.cumsum(delta))) / 1e6
    reverse_events = [dict(previous_sec=float(relative[i]), current_sec=float(relative[i + 1]),
                           jump_ms=float(delta[i] / 1000)) for i in np.where(delta < 0)[0]]
    duration = float(delta.sum() / 1e6) if len(delta) else 0.0
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                records=len(timestamp), duration_sec=duration,
                csi_records_per_sec=len(timestamp) / max(duration, 1e-9),
                dimensions=dict(dims), rates=dict(rates), permutations=dict(permutations),
                decode_samples=decoded, structural_errors=issues,
                backward_timestamps=int(np.sum(delta < 0)),
                backward_events_sec=reverse_events,
                duplicate_timestamps=int(np.sum(delta == 0)),
                gap_p50_ms=float(np.percentile(delta, 50) / 1000) if len(delta) else None,
                gap_p95_ms=float(np.percentile(delta, 95) / 1000) if len(delta) else None,
                gap_p99_ms=float(np.percentile(delta, 99) / 1000) if len(delta) else None,
                max_gap_ms=float(delta.max() / 1000) if len(delta) else None,
                gaps_gt_50ms=int(np.sum(delta > 50000)),
                gaps_gt_100ms=int(np.sum(delta > 100000)),
                gaps_gt_200ms=int(np.sum(delta > 200000)),
                noise_mean_db=float(np.mean(noise)) if noise else None,
                noise_unknown_records=int(np.sum(np.array(noise) == -127)),
                agc_mean_db=float(np.mean(agc)) if agc else None)


def quality_ok(row):
    return (row.get('timestamp_quality', 'ok') == 'ok' and
            float(row['packet_count']) >= 80 and
            float(row['last_packet_sec']) - float(row['first_packet_sec']) >= 1.5 and
            float(row['max_gap_ms']) <= 200)


def summarize(y, pred, labels=LABELS):
    cm = confusion_matrix(y, pred, labels=labels)
    recall = cm.diagonal() / np.maximum(cm.sum(axis=1), 1)
    return dict(n=len(y), accuracy=float(accuracy_score(y, pred)),
                macro_f1=float(f1_score(y, pred, labels=labels, average='macro', zero_division=0)),
                labels=labels, confusion_matrix=cm.tolist(),
                recall={str(k): float(v) for k, v in zip(labels, recall)})


def make_models():
    return {
        'centroid': make_pipeline(StandardScaler(), NearestCentroid()),
        'logistic': make_pipeline(StandardScaler(), LogisticRegression(
            C=1.0, max_iter=3000, class_weight='balanced', random_state=SEED)),
        'svm_rbf': make_pipeline(StandardScaler(), SVC(
            C=1.0, kernel='rbf', gamma='scale', class_weight='balanced')),
        'random_forest': RandomForestClassifier(
            n_estimators=200, min_samples_leaf=3, max_features='sqrt',
            class_weight='balanced', random_state=SEED, n_jobs=1),
    }


def feature_sets(rows, names):
    all_x = np.array([[float(r[k]) for k in names] for r in rows])
    assert np.isfinite(all_x).all()
    csi_names = [k for k in names if k not in RADIO]
    shape_names = [k for k in csi_names if k.startswith(('sub', 'pair_'))]
    shape_names += ['amp_std', 'packet_amp_mean_std',
                    'packet_amp_diff_abs_mean', 'packet_amp_diff_abs_std']
    scale = all_x[:, names.index('amp_mean')][:, None]
    return {
        'all_88': (all_x, names),
        'csi_amplitude_82': (all_x[:, [names.index(k) for k in csi_names]], csi_names),
        'radio_only_6': (all_x[:, [names.index(k) for k in RADIO]], RADIO),
        'normalized_shape_76': (
            all_x[:, [names.index(k) for k in shape_names]] / np.maximum(scale, 1e-9),
            [k + '/amp_mean' for k in shape_names]),
    }


def verify_intervals(rows, train, test):
    for sid in sorted(set(r['session_id'] for r in rows)):
        tr = [(float(rows[i]['start_sec']), float(rows[i]['end_sec']))
              for i in train if rows[i]['session_id'] == sid]
        te = [(float(rows[i]['start_sec']), float(rows[i]['end_sec']))
              for i in test if rows[i]['session_id'] == sid]
        assert not any(a < d and c < b for a, b in tr for c, d in te), sid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default=str(ROOT / 'outputs/people_count_analysis_20260914'))
    args = parser.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    audit, rows, loaded = [], [], {}
    for mp in sorted((ROOT / 'data').glob('*_people/META_DATA/session_202609*/meta.json')):
        meta, runtime = read_json(mp), read_json(mp.parent / 'capture_runtime.json')
        sid = meta['session_id']
        raw = mp.parents[2] / 'CSI_DATA' / (sid + '.dat')
        a = raw_audit(raw)
        a.update(session_id=sid, label=meta['label']['num_people'], date=sid[8:16],
                 meta_file=str(mp.relative_to(ROOT)), csi_file=str(raw.relative_to(ROOT)),
                 completed=runtime.get('completed', False),
                 label_status=meta['label'].get('label_status'),
                 metadata_quality_status=meta['quality_status'],
                 udp_count=runtime.get('udp', {}).get('packet_count'),
                 network=meta.get('network'), layout=meta.get('layout'))
        a['csi_to_udp_ratio'] = a['records'] / float(a['udp_count']) if a['udp_count'] else None
        epoch = runtime.get('logger_started_wall_epoch')
        a['logger_start_local'] = datetime.fromtimestamp(epoch, KST).isoformat() if epoch else None
        a['meta_start_local'] = meta.get('capture', {}).get('start_time_local')
        if a['meta_start_local'] and epoch:
            parsed = datetime.strptime(a['meta_start_local'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=KST)
            a['meta_start_error_vs_logger_sec'] = parsed.timestamp() - epoch
        manifest_path = ROOT / 'data/structured' / sid / 'manifest.json'
        if manifest_path.exists():
            manifest = read_json(manifest_path)
            assert a['sha256'] == manifest['source']['sha256'], 'Source changed: ' + sid
            assert a['records'] == manifest['records']['total'], 'Record count changed: ' + sid
            assert not a['structural_errors']
            a['cached_feature_source_hash_verified'] = True
            a['manifest_quality'] = manifest['quality']
            assert manifest['configuration']['rx_permutation_applied']
            assert manifest['configuration']['csi_mode'] == 'scaled'
            fp = manifest_path.parent / 'window_features.csv'
            rr = list(csv.DictReader(fp.open()))
            for row in rr:
                lo, hi = float(row['start_sec']), float(row['end_sec'])
                affected = any(lo <= e['previous_sec'] and e['current_sec'] < hi
                               for e in a['backward_events_sec'])
                row['timestamp_quality'] = 'reverse_jump' if affected else 'ok'
            assert len(rr) == manifest['windows']['kept']
            a['feature_windows'] = len(rr)
            a['quality_rejected_windows'] = sum(not quality_ok(r) for r in rr)
            a['feature_file_sha256'] = hashlib.sha256(fp.read_bytes()).hexdigest()
            if a['completed'] and a['label_status'] == 'stable_full_session':
                loaded[sid] = rr
                rows.extend(rr)
        audit.append(a)
        print('AUDIT', sid, a['records'], 'records,', round(a['csi_records_per_sec'], 2), 'Hz', flush=True)
    write_json(out / 'session_audit.json', audit)
    assert len(set(a['sha256'] for a in audit)) == len(audit), 'Duplicate raw sessions'
    names = train_baseline.numeric_feature_names(rows)
    assert len(names) == 88, names
    sets = feature_sets(rows, names)
    y = np.array([int(r['num_people']) for r in rows])
    start = np.array([float(r['start_sec']) for r in rows])
    end = np.array([float(r['end_sec']) for r in rows])
    new = np.array(['20260913' in r['session_id'] for r in rows])
    quality = np.array([quality_ok(r) for r in rows])
    even = start.astype(int) % 2 == 0
    eligible = new & quality & even & (start >= 30) & (end <= 1170)
    train = np.where(eligible & (end <= 780))[0]
    test = np.where(eligible & (start >= 840))[0]
    reverse_train = np.where(eligible & (start >= 420))[0]
    reverse_test = np.where(eligible & (end <= 360))[0]
    all_new = np.where(eligible)[0]
    old3 = np.where(~new & quality & even & (y == 3))[0]
    old4 = np.where(~new & quality & even & (y == 4) & (start >= 30) & (end <= 1170))[0]
    verify_intervals(rows, train, test)
    verify_intervals(rows, reverse_train, reverse_test)
    assert set(y[train]) == set(y[test]) == set(LABELS)
    write_csv(out / 'analysis_features.csv', rows)
    split_rows = []
    train_set, test_set, used_set = set(train), set(test), set(all_new)
    for i, r in enumerate(rows):
        split_rows.append(dict(session_id=r['session_id'], window_id=r['window_id'],
                               label=int(y[i]), start_sec=float(start[i]), end_sec=float(end[i]),
                               quality_pass=bool(quality[i]),
                               split=('train' if i in train_set else 'test' if i in test_set
                                      else 'temporal_gap' if i in used_set else 'excluded_or_external')))
    write_csv(out / 'split_manifest.csv', split_rows)
    metrics, predictions, fitted = [], [], {}
    models = make_models()

    def experiment(kind, fs, name, tr, te, shuffle=False, labels=LABELS):
        x, _ = sets[fs]
        model = clone(models[name])
        yy = y[tr].copy()
        if shuffle:
            np.random.RandomState(SEED).shuffle(yy)
        begin = time.time(); model.fit(x[tr], yy)
        pred = model.predict(x[te])
        m = summarize(y[te], pred, labels)
        m.update(experiment=kind, feature_set=fs, model=name,
                 n_train=len(tr), fit_seconds=time.time() - begin)
        metrics.append(m)
        for i, p in zip(te, pred):
            predictions.append(dict(experiment=kind, feature_set=fs, model=name,
                                    session_id=rows[i]['session_id'], window_id=rows[i]['window_id'],
                                    start_sec=float(start[i]), true_label=int(y[i]), prediction=int(p)))
        print(kind, fs, name, '{:.4f}'.format(m['accuracy']), 'n=', len(te), flush=True)
        return model, m

    for fs in sets:
        for name in models:
            model, _ = experiment('forward_time_holdout', fs, name, train, test)
            fitted[(fs, name)] = model
    for fs in ('csi_amplitude_82', 'normalized_shape_76', 'all_88'):
        experiment('reverse_time_holdout', fs, 'random_forest', reverse_train, reverse_test)
    experiment('reverse_time_holdout', 'normalized_shape_76', 'svm_rbf', reverse_train, reverse_test)
    # Deliberately retain overlapping windows only for the leakage demonstration.
    random_idx = np.where(new & quality & (start >= 30) & (end <= 1170))[0]
    random_train, random_test = train_test_split(random_idx, test_size=.3,
                                               random_state=SEED, stratify=y[random_idx])
    experiment('random_overlapping_windows_not_generalization', 'csi_amplitude_82',
               'random_forest', random_train, random_test)
    overlapping = 0
    for i in random_test:
        overlapping += any(rows[j]['session_id'] == rows[i]['session_id'] and
                           start[j] < end[i] and start[i] < end[j] for j in random_train)
    experiment('shuffled_training_labels_negative_control', 'csi_amplitude_82',
               'random_forest', train, test, shuffle=True)
    block = ((start - 30) // 228).astype(int)
    for fold in range(5):
        lo, hi = 30 + fold * 228, 30 + (fold + 1) * 228
        te = np.where(eligible & (start >= lo) & (end <= hi))[0]
        tr = np.where(eligible & ((end <= lo - 30) | (start >= hi + 30)))[0]
        verify_intervals(rows, tr, te)
        experiment('blocked_fold_{}'.format(fold), 'csi_amplitude_82', 'random_forest', tr, te)
        experiment('blocked_fold_{}'.format(fold), 'normalized_shape_76', 'svm_rbf', tr, te)
    pairwise = []
    for a, b in combinations(LABELS, 2):
        tr, te = train[np.isin(y[train], [a, b])], test[np.isin(y[test], [a, b])]
        _, m = experiment('pair_{}_{}'.format(a, b), 'csi_amplitude_82', 'random_forest',
                          tr, te, labels=[a, b])
        pairwise.append(dict(pair='{} vs {}'.format(a, b), accuracy=m['accuracy'], n=m['n']))
    # A cross-date probe has only one short 3-person session. Report its recall;
    # its score is NOT a four-class cross-date accuracy estimate.
    external = []
    for fs in ('all_88', 'csi_amplitude_82', 'normalized_shape_76'):
        for name in ('centroid', 'random_forest', 'svm_rbf'):
            x, _ = sets[fs]
            model = clone(models[name]).fit(x[all_new], y[all_new])
            pred3, pred4 = model.predict(x[old3]), model.predict(x[old4])
            external.append(dict(feature_set=fs, model=name, old3_windows=len(old3),
                                 old3_recall=float(np.mean(pred3 == 3)),
                                 old3_predictions={str(k): int(v) for k, v in Counter(pred3).items()},
                                 old4_windows=len(old4),
                                 old4_forced_predictions={str(k): int(v) for k, v in Counter(pred4).items()}))
        experiment('mixed_training_add_old3', fs, 'random_forest',
                   np.concatenate([train, old3]), test)
    experiment('mixed_training_add_old3', 'normalized_shape_76', 'svm_rbf',
               np.concatenate([train, old3]), test)
    # Primary artifact fixed in advance: amplitude-only random forest, forward split.
    primary = fitted[('csi_amplitude_82', 'random_forest')]
    bundle = dict(model=primary, feature_names=sets['csi_amplitude_82'][1], labels=LABELS,
                  preprocessing='existing physical-RX-permuted scaled CSI, 2-second windows',
                  training_scope='2026-09-13 four sessions, 30-780 seconds; research prototype',
                  independent_session_validation=False, sklearn_version=sklearn.__version__)
    joblib.dump(bundle, str(out / 'people_count_rf_prototype.joblib'))
    restored = joblib.load(str(out / 'people_count_rf_prototype.joblib'))
    x_csi = sets['csi_amplitude_82'][0]
    assert np.array_equal(primary.predict(x_csi[test]), restored['model'].predict(x_csi[test]))
    shape_names = [n.split('/')[0] for n in sets['normalized_shape_76'][1]]
    shape_bundle = dict(model=fitted[('normalized_shape_76', 'svm_rbf')],
                        feature_names=shape_names, divide_by='amp_mean', labels=LABELS,
                        preprocessing='per-window amplitude ratio, then training-only StandardScaler',
                        training_scope=bundle['training_scope'],
                        independent_session_validation=False,
                        selection='exploratory candidate among the reported fixed models',
                        sklearn_version=sklearn.__version__)
    joblib.dump(shape_bundle, str(out / 'people_count_normalized_svm_prototype.joblib'))
    restored_shape = joblib.load(str(out / 'people_count_normalized_svm_prototype.joblib'))
    assert np.array_equal(shape_bundle['model'].predict(sets['normalized_shape_76'][0][test]),
                          restored_shape['model'].predict(sets['normalized_shape_76'][0][test]))
    plain_train = [rows[i] for i in train]
    scaler = train_baseline.fit_scaler(plain_train, sets['csi_amplitude_82'][1])
    plain = dict(classifier='nearest_centroid', labels=list(map(str, LABELS)),
                 feature_names=sets['csi_amplitude_82'][1], scaler=scaler,
                 centroids=train_baseline.fit_nearest_centroid(plain_train, sets['csi_amplitude_82'][1], scaler),
                 independent_session_validation=False)
    write_json(out / 'people_count_centroid_prototype.json', plain)
    descriptive = []
    for sid, rr in loaded.items():
        rr = [r for r in rr if quality_ok(r) and int(float(r['start_sec'])) % 2 == 0]
        z = dict(session_id=sid, label=int(rr[0]['num_people']), windows=len(rr))
        for k in ['amp_mean', 'amp_std', 'packet_amp_diff_abs_mean'] + RADIO:
            vals = [float(r[k]) for r in rr]
            z[k] = dict(mean=float(np.mean(vals)), std=float(np.std(vals)), median=float(np.median(vals)))
        descriptive.append(z)
    # Standardized centroid distances using only Sept 13 training statistics.
    x = sets['csi_amplitude_82'][0]
    std = StandardScaler().fit(x[train])
    z = std.transform(x)
    centroids = {str(k): z[all_new[y[all_new] == k]].mean(axis=0) for k in LABELS}
    old_center = z[old3].mean(axis=0)
    distances = {k: float(np.sqrt(np.mean((old_center - c) ** 2))) for k, c in centroids.items()}
    # Session-level inference is unavailable for 0,1,2: each has one session.
    result = dict(seed=SEED, versions=dict(python=sys.version, numpy=np.__version__,
                  scipy=scipy.__version__, sklearn=sklearn.__version__),
                  evaluation_scope='within-session separability, not causal count isolation or new-session accuracy',
                  feature_dimensions={k: v[0].shape[1] for k, v in sets.items()},
                  train_windows=len(train), test_windows=len(test), eligible_windows=len(all_new),
                  overlap_fraction_in_random_test=overlapping / float(len(random_test)),
                  quality_rule='>=80 packets, >=1.5 s observed coverage, <=200 ms max gap; windows spanning reversed timestamps excluded; 3x1 packets already skipped',
                  trimming='Sept13: first/last 30 seconds removed; stride 2 s; train [30,780], gap 60 s, test [840,1170]',
                  metrics=metrics, external_date_probe=external, pairwise=pairwise,
                  same3_old_to_new_centroid_rms_z=distances,
                  session_descriptive=descriptive,
                  independent_session_evaluation=dict(available=False, reason='Only one completed Sept13 session per label; Sept2 lacks labels 0,1,2'),
                  artifacts_reloaded_successfully=True)
    write_json(out / 'metrics.json', result)
    write_csv(out / 'predictions.csv', predictions)
    write_csv(out / 'pairwise.csv', pairwise)
    flat = [{k: m[k] for k in ['experiment', 'feature_set', 'model', 'n_train', 'n', 'accuracy', 'macro_f1']}
            for m in metrics]
    write_csv(out / 'metrics_summary.csv', flat)
    importance = sorted(zip(sets['csi_amplitude_82'][1], primary.feature_importances_), key=lambda kv: -kv[1])
    write_csv(out / 'feature_importance.csv', [dict(feature=k, importance=float(v)) for k, v in importance])
    plot_results(out, rows, y, start, sets, train, test, all_new, old3, old4, result, primary)
    print('OUTPUT', out, flush=True)


def plot_results(out, rows, y, start, sets, train, test, all_new, old3, old4, result, primary):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size': 11, 'figure.dpi': 150, 'axes.spines.top': False,
                         'axes.spines.right': False})
    colors = ['#3b82f6', '#f59e0b', '#10b981', '#8b5cf6']
    x = sets['csi_amplitude_82'][0]
    pred = primary.predict(x[test])
    cm = confusion_matrix(y[test], pred, labels=LABELS)
    fig, ax = plt.subplots(figsize=(6, 5))
    im = ax.imshow(cm / cm.sum(axis=1, keepdims=True), vmin=0, vmax=1, cmap='Blues')
    for i in LABELS:
        for j in LABELS:
            v = cm[i, j] / cm[i].sum()
            ax.text(j, i, '{}\n{:.1%}'.format(cm[i, j], v), ha='center', va='center',
                    color='white' if v > .5 else '#18212f')
    ax.set(xticks=LABELS, yticks=LABELS, xlabel='Predicted people', ylabel='Recorded people',
           title='CSI amplitude only: temporal holdout\nSame four sessions; 60 s gap')
    fig.colorbar(im, ax=ax, label='Recall per class'); fig.tight_layout()
    fig.savefig(str(out / 'confusion_matrix.png')); fig.savefig(str(out / 'confusion_matrix.pdf')); plt.close(fig)
    scaler = StandardScaler().fit(x[train])
    pca = PCA(n_components=2, random_state=SEED).fit(scaler.transform(x[train]))
    pc = pca.transform(scaler.transform(x))
    fig, ax = plt.subplots(figsize=(8, 6))
    for k, color in zip(LABELS, colors):
        idx = all_new[y[all_new] == k]
        ax.scatter(pc[idx, 0], pc[idx, 1], s=9, alpha=.3, c=color, label='Sep 13: {} people'.format(k))
    ax.scatter(pc[old3, 0], pc[old3, 1], s=140, marker='X', c='red', edgecolors='black', label='Sep 2: 3 people')
    ax.scatter(pc[old4[::8], 0], pc[old4[::8], 1], s=24, marker='+', c='gray', label='Sep 2: 4 people (out of scope)')
    ax.set(xlabel='PC1 ({:.1%} variance)'.format(pca.explained_variance_ratio_[0]),
           ylabel='PC2 ({:.1%} variance)'.format(pca.explained_variance_ratio_[1]),
           title='Feature distribution by session\nProjection fitted on training data only')
    ax.legend(fontsize=9); fig.tight_layout(); fig.savefig(str(out / 'feature_distribution.png')); plt.close(fig)
    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
    for ax, key, title in zip(axes, ['amp_mean', 'packet_amp_diff_abs_mean', 'total_rss_dbm_mean'],
                             ['Scaled CSI amplitude', 'Mean absolute packet amplitude change', 'Total RSS (dBm)']):
        for k, color in zip(LABELS, colors):
            ix = all_new[y[all_new] == k]
            ax.plot(start[ix] / 60, [float(rows[i][key]) for i in ix], color=color,
                    alpha=.7, linewidth=.8, label='{} people'.format(k))
        ax.axvspan(13, 14, color='gray', alpha=.15)
        ax.set_ylabel(title)
    axes[0].legend(ncol=4); axes[-1].set_xlabel('Minutes from first CSI record')
    axes[0].set_title('Sep 13 sessions: signal levels do not increase monotonically with people count')
    fig.tight_layout(); fig.savefig(str(out / 'signals_over_time.png')); plt.close(fig)


if __name__ == '__main__':
    main()
