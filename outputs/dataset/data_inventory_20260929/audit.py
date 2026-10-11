#!/usr/bin/env python3
"""Read-only source audit; writes only this dated inventory directory.

Uses the existing September audit's frame/header checks and sample decoder.
No capture metadata, quality flags, raw recordings or features are modified.
"""
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts/evaluate'))
from analyze_people_separability import raw_audit, quality_ok


def read(path):
    return json.loads(path.read_text()) if path.exists() else {}


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2,
                               sort_keys=True, allow_nan=False) + '\n')


def total(rows):
    return dict(sessions=len(rows),
                observed_csi_seconds=sum(r.get('raw', {}).get('duration_sec', 0) for r in rows),
                planned_seconds=sum(r['planned_seconds'] or 0 for r in rows),
                csi_records=sum(r.get('raw', {}).get('records', 0) for r in rows),
                csi_bytes=sum(r['csi_bytes'] for r in rows),
                video_bytes=sum(r['video_bytes'] for r in rows),
                accepted_records=sum(r['manifest'].get('records', {}).get('accepted', 0) for r in rows),
                skipped_dimension_records=sum(r['manifest'].get('records', {}).get('skipped_dimension', 0) for r in rows),
                stored_windows=sum(r.get('windows', {}).get('stored', 0) for r in rows),
                quality_screened_windows=sum(r.get('windows', {}).get('quality_screened', 0) for r in rows),
                nonoverlap_screened_windows=sum(r.get('windows', {}).get('nonoverlap_screened', 0) for r in rows),
                nonoverlap_screened_trimmed_windows=sum(r.get('windows', {}).get('nonoverlap_screened_trimmed', 0) for r in rows),
                dates=sorted(set(r['date'] for r in rows)),
                quality_status_counts=dict(Counter(r['manifest'].get('quality', {}).get('status', 'no_manifest') for r in rows)))


def main():
    snapshot = datetime.now(timezone(timedelta(hours=9))).isoformat()
    paths = sorted((ROOT / 'data').glob('*_people/META_DATA/*/meta.json'))
    paths += sorted((ROOT / 'data/raw').glob('*/meta.json'))
    rows = []
    for mp in paths:
        meta = read(mp)
        runtime = read(mp.parent / 'capture_runtime.json')
        control = read(mp.parent / 'session_control.json')
        segments = read(mp.parent / 'activity_segments.json')
        sid = meta['session_id']
        people_layout = mp.parent.parent.name == 'META_DATA'
        csi = (mp.parents[2] / 'CSI_DATA' / (sid + '.dat')) if people_layout else (mp.parent / 'csi.dat')
        if people_layout:
            video = mp.parents[2] / 'Web_Cam' / (sid + '.webm')
        else:
            video_name = meta.get('capture', {}).get('video_file') or 'video.webm'
            video = mp.parent / video_name
        manifest_path = ROOT / 'data/structured' / sid / 'manifest.json'
        manifest = read(manifest_path)
        if not manifest and not people_layout:
            manifest_path = ROOT / 'data/structured' / (sid + '_prototype_v1') / 'manifest.json'
            manifest = read(manifest_path)
        label, environment = meta.get('label', {}), meta.get('environment', {})
        row = dict(session_id=sid, date=sid[8:16],
                   metadata_file=str(mp.relative_to(ROOT)),
                   layout='people' if people_layout else 'raw',
                   room=environment.get('room'), setup_id=environment.get('setup_id'),
                   empty_reference_session_id=environment.get('empty_reference_session_id'),
                   num_people=label.get('num_people'), activity=label.get('activity'),
                   label_status=label.get('label_status'),
                   dataset_role=meta.get('dataset_role'),
                   metadata_quality=meta.get('quality_status'),
                   metadata_training_allowed=meta.get('use_for_final_training'),
                   runtime_completed=runtime.get('completed'),
                   control_completed=control.get('completed', runtime.get('session_control', {}).get('completed')),
                   planned_seconds=runtime.get('planned_duration_sec', meta.get('capture', {}).get('planned_duration_sec')),
                   csi_file=str(csi.relative_to(ROOT)), csi_exists=csi.exists(),
                   csi_bytes=csi.stat().st_size if csi.exists() else 0,
                   video_file=str(video.relative_to(ROOT)), video_exists=video.exists(),
                   video_bytes=video.stat().st_size if video.exists() else 0,
                   video_runtime_duration_sec=runtime.get('camera', {}).get('observed_duration_sec'),
                   manifest_file=str(manifest_path.relative_to(ROOT)) if manifest else None,
                   manifest=manifest, planned_activity_seconds={},
                   annotation_kind=segments.get('label_status'), audit_problems=[])
        durations = defaultdict(float)
        for segment in segments.get('segments', []):
            durations[segment['activity']] += segment['end_sec'] - segment['start_sec']
        row['planned_activity_seconds'] = dict(durations)
        if row['csi_bytes']:
            before = csi.stat()
            row['raw'] = raw_audit(csi)
            after = csi.stat()
            row['source_stable_during_scan'] = (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
            if not row['source_stable_during_scan']:
                row['audit_problems'].append('source_changed_during_scan')
            if row['raw']['structural_errors']:
                row['audit_problems'].append('raw_structure_errors')
            if manifest:
                row['source_hash_verified'] = row['raw']['sha256'] == manifest.get('source', {}).get('sha256')
                row['source_records_verified'] = row['raw']['records'] == manifest.get('records', {}).get('total')
                if not row['source_hash_verified'] or not row['source_records_verified']:
                    row['audit_problems'].append('manifest_source_mismatch')
                fp = manifest_path.parent / 'window_features.csv'
                if fp.exists():
                    with fp.open() as stream:
                        windows = list(csv.DictReader(stream))
                    reversals = row['raw']['backward_events_sec']
                    for w in windows:
                        lo, hi = float(w['start_sec']), float(w['end_sec'])
                        w['timestamp_quality'] = 'reverse_jump' if any(lo <= e['previous_sec'] and e['current_sec'] < hi for e in reversals) else 'ok'
                    good = [w for w in windows if quality_ok(w)]
                    # Cached windows have 1 s stride; even start times retain disjoint 2 s intervals.
                    nonoverlap = [w for w in good if abs(float(w['start_sec']) % 2) < 1e-8]
                    trimmed = [w for w in nonoverlap if float(w['start_sec']) >= 30 and float(w['end_sec']) <= row['raw']['duration_sec'] - 30]
                    numeric = [k for k in windows[0] if k.startswith(('amp_', 'packet_amp_', 'sub', 'pair_', 'rssi_', 'total_rss_', 'noise_', 'agc_'))] if windows else []
                    nonfinite = 0
                    import math
                    for w in windows:
                        if not all(math.isfinite(float(w[k])) for k in numeric):
                            nonfinite += 1
                    row['windows'] = dict(stored=len(windows), quality_screened=len(good),
                                          quality_rejected=len(windows)-len(good),
                                          nonoverlap_screened=len(nonoverlap),
                                          nonoverlap_screened_trimmed=len(trimmed),
                                          feature_columns_checked=len(numeric), nonfinite_rows=nonfinite,
                                          feature_sha256=hashlib.sha256(fp.read_bytes()).hexdigest())
                    if len(windows) != manifest.get('windows', {}).get('kept'):
                        row['audit_problems'].append('feature_row_count_mismatch')
                    if nonfinite:
                        row['audit_problems'].append('nonfinite_features')
        row['complete_candidate'] = bool(row['runtime_completed'] and row['control_completed'] is not False
                                         and row['dataset_role'] == 'training_candidate'
                                         and row['metadata_quality'] == 'valid_csi'
                                         and row['label_status'] == 'stable_full_session'
                                         and row.get('raw', {}).get('records', 0) > 0
                                         and not row['audit_problems'])
        rows.append(row)
        print(sid, row['room'], row['num_people'], 'records', row.get('raw', {}).get('records', 0),
              'seconds', round(row.get('raw', {}).get('duration_sec', 0), 3),
              'candidate', row['complete_candidate'], 'problems', row['audit_problems'], flush=True)

    candidates = [r for r in rows if r['complete_candidate']]
    hashes = defaultdict(list)
    for row in rows:
        if row.get('raw'):
            hashes[row['raw']['sha256']].append(row['session_id'])
    summary = dict(snapshot_local=snapshot, all_sources=total(rows),
                   complete_candidates=total(candidates),
                   zero_to_four_candidates=total([r for r in candidates if r['num_people'] <= 4]),
                   final_training_flag_true=total([r for r in candidates if r['manifest'].get('quality', {}).get('final_training_allowed')]),
                   excluded=total([r for r in rows if not r['complete_candidate']]),
                   candidate_by_room={room: total([r for r in candidates if r['room'] == room]) for room in sorted(set(r['room'] for r in candidates))},
                   candidate_by_count={str(n): total([r for r in candidates if r['num_people'] == n]) for n in range(6)},
                   candidate_by_room_and_count={room: {str(n): total([r for r in candidates if r['room'] == room and r['num_people'] == n]) for n in range(6)} for room in sorted(set(r['room'] for r in candidates))},
                   duplicate_nonempty_sources={k:v for k,v in hashes.items() if len(v)>1},
                   candidate_raw_decode_samples=sum(r['raw']['decode_samples'] for r in candidates),
                   screening_policy=dict(packet_count_min=80, coverage_sec_min=1.5, max_gap_ms=200,
                                         timestamp_reversals='exclude_intersecting_windows',
                                         nonoverlap='even integer start seconds', trim_seconds_each_end=30,
                                         meaning='provisional numerical screening; does not change quality flags or verify actual headcounts/actions'))
    write(OUT / 'session_audit.json', rows)
    write(OUT / 'summary.json', summary)
    flat = []
    for r in rows:
        flat.append(dict(session_id=r['session_id'], room=r['room'], setup_id=r['setup_id'],
                         num_people=r['num_people'], complete_candidate=r['complete_candidate'],
                         observed_seconds=r.get('raw', {}).get('duration_sec', 0),
                         csi_records=r.get('raw', {}).get('records', 0), csi_bytes=r['csi_bytes'], video_bytes=r['video_bytes'],
                         quality_status=r['manifest'].get('quality', {}).get('status'),
                         final_training_allowed=r['manifest'].get('quality', {}).get('final_training_allowed'),
                         stored_windows=r.get('windows', {}).get('stored', 0),
                         screened_nonoverlap_trimmed_windows=r.get('windows', {}).get('nonoverlap_screened_trimmed', 0),
                         source_hash_verified=r.get('source_hash_verified'),
                         audit_problems=';'.join(r['audit_problems'])))
    with (OUT / 'sessions.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(flat[0]))
        writer.writeheader()
        writer.writerows(flat)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
