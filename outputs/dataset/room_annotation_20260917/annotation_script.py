"""One-time, audited room annotation of the sessions present before G304 capture."""
import copy
import csv
import hashlib
import io
import json
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path('/home/mh/바탕화면/project')
AUDIT = ROOT / 'outputs/dataset/room_annotation_20260917'
SESSION_PATHS = [
    'data/raw/session_20260615_203420',
    'data/raw/session_20260615_203722',
    'data/raw/session_20260615_205335',
    'data/raw/session_20260703_151554',
    'data/raw/session_20260703_151951',
    'data/raw/session_20260703_172027',
    'data/raw/session_20260710_145820',
    'data/raw/session_20260710_153743',
    'data/raw/session_20260814_150923',
    'data/raw/session_20260814_151345',
    'data/raw/session_20260814_151757',
    'data/raw/session_20260902_174112',
    'data/raw/session_20260902_174312',
    'data/0_people/META_DATA/session_20260913_170126_a81112c0',
    'data/1_people/META_DATA/session_20260913_154543_2e610644',
    'data/2_people/META_DATA/session_20260913_145724_8ae77998',
    'data/2_people/META_DATA/session_20260913_151206_6122a612',
    'data/2_people/META_DATA/session_20260913_161128_29c3bb2f',
    'data/3_people/META_DATA/session_20260902_182349',
    'data/3_people/META_DATA/session_20260913_143135_999cdb09',
    'data/4_people/META_DATA/session_20260902_183751',
]
SOURCE = 'User confirmed on 2026-09-17: all previously collected CSI sessions were in classroom G308.'
ALLOWED = {None, '', 'unknown', 'project_room', 'prototype_room', 'school_lounge_or_lab_room', 'G308'}


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def encoded(data):
    return (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def annotate(data, runtime=False):
    result = copy.deepcopy(data)
    location = result if runtime else result.setdefault('environment', {})
    previous = location.get('room')
    if previous not in ALLOWED:
        raise ValueError('Unexpected existing room: ' + str(previous))
    location['room'] = 'G308'
    if 'room_annotation' not in result:
        result['room_annotation'] = {'source': SOURCE, 'previous_room': previous}
    return result


def main():
    known = {Path(p).name for p in SESSION_PATHS}
    planned = {}
    rows = []
    binary_stats = {str(p): (p.stat().st_size, p.stat().st_mtime_ns)
                    for p in (ROOT / 'data').rglob('*') if p.suffix in ('.dat', '.webm')}
    for relative in SESSION_PATHS:
        session = ROOT / relative
        if not session.is_dir():
            raise ValueError('Missing frozen session path: ' + relative)
        meta_path = session / 'meta.json'
        runtime_path = session / 'capture_runtime.json'
        runtime = read(runtime_path) if runtime_path.exists() else {}
        if meta_path.exists():
            meta = read(meta_path)
        else:
            csi = session / 'csi.dat'
            failed = runtime.get('completed') is False or not csi.is_file() or csi.stat().st_size == 0
            meta = {'schema_version': '1.0', 'session_id': session.name,
                    'quality_status': 'failed' if failed else 'needs_review',
                    'dataset_role': 'failure_history' if failed else 'excluded',
                    'use_for_final_training': False,
                    'label': {'num_people': runtime.get('num_people'), 'label_status': 'unknown',
                              'activity': runtime.get('activity', 'unknown')},
                    'capture': {'csi_file': 'csi.dat'},
                    'comments': 'Minimal metadata added for room annotation; no new CSI or label validation.'}
        planned[meta_path] = encoded(annotate(meta))
        if runtime_path.exists():
            planned[runtime_path] = encoded(annotate(runtime, runtime=True))
        control = session / 'session_control.json'
        if control.exists():
            planned[control] = encoded(annotate(read(control)))
        rows.append({'session_id': session.name, 'session_dir': relative, 'room': 'G308',
                     'num_people': meta.get('label', {}).get('num_people'),
                     'activity': meta.get('label', {}).get('activity'),
                     'quality_status': meta.get('quality_status'),
                     'dataset_role': meta.get('dataset_role'),
                     'use_for_final_training': meta.get('use_for_final_training')})
    for path in (ROOT / 'data/structured').glob('*/manifest.json'):
        data = read(path)
        source_meta = data.get('source', {}).get('meta_file')
        if source_meta and Path(source_meta).parent.name in known:
            planned[path] = encoded(annotate(data))
    for path in (ROOT / 'outputs/launcher').glob('*.json'):
        data = read(path)
        if data.get('session_id') in known or data.get('negotiated_session_id') in known:
            planned[path] = encoded(annotate(data))
    index = ROOT / 'outputs/dataset/session_index.json'
    if index.exists():
        data = read(index)
        for row in data.get('sessions', []):
            if row.get('session_id') in known:
                row['room'] = 'G308'
        planned[index] = encoded(data)
    index = ROOT / 'outputs/dataset/session_index.csv'
    if index.exists():
        with index.open(newline='') as handle:
            reader = csv.DictReader(handle)
            fields, entries = reader.fieldnames, list(reader)
        for row in entries:
            if row.get('session_id') in known:
                row['room'] = 'G308'
        output = io.StringIO(newline='')
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(entries)
        planned[index] = output.getvalue().encode('utf-8')
    index = ROOT / 'data/processed/structured_dataset_prototype_manifest.json'
    if index.exists():
        data = read(index)
        for row in data.get('selected_sessions', []):
            if row.get('session_id', '').split('_prototype')[0] in known:
                row.setdefault('environment', {})['room'] = 'G308'
        planned[index] = encoded(data)
    print('Frozen sessions: {}; metadata/index files: {}; CSI/video files: {}'.format(
        len(rows), len(planned), len(binary_stats)))
    if '--apply' not in sys.argv:
        for row in rows:
            print('{}: G308, {} people, {}'.format(row['session_id'], row['num_people'], row['quality_status']))
        return
    if AUDIT.exists():
        raise ValueError('Audit directory already exists; refusing to overwrite backups')
    AUDIT.mkdir(parents=True)
    report = {'source': SOURCE, 'created_at': datetime.now(timezone(timedelta(hours=9))).isoformat(),
              'sessions': rows, 'files': []}
    # Back up and validate the complete plan before the first original file is modified.
    for path, content in sorted(planned.items()):
        old = path.read_bytes() if path.exists() else None
        backup = AUDIT / 'before' / path.relative_to(ROOT)
        if old is not None:
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(old)
        report['files'].append({'path': str(path.relative_to(ROOT)), 'created': old is None,
                                'before_sha256': hashlib.sha256(old).hexdigest() if old is not None else None,
                                'after_sha256': hashlib.sha256(content).hexdigest()})
    (AUDIT / 'report.json').write_bytes(encoded(report))
    for path, content in sorted(planned.items()):
        temp = path.with_name(path.name + '.room.tmp')
        temp.write_bytes(content)
        temp.replace(path)
    for relative in SESSION_PATHS:
        assert read(ROOT / relative / 'meta.json')['environment']['room'] == 'G308'
    for path, before in binary_stats.items():
        actual = Path(path).stat()
        assert before == (actual.st_size, actual.st_mtime_ns), path
    report['verification'] = {'all_21_sessions_labeled_G308': True,
                              'csi_and_video_sizes_and_mtimes_unchanged': True}
    (AUDIT / 'report.json').write_bytes(encoded(report))
    with (AUDIT / 'session_rooms.csv').open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    shutil.copyfile(__file__, str(AUDIT / 'annotation_script.py'))
    print('Applied and verified. Audit and original metadata:', AUDIT)


if __name__ == '__main__':
    main()
