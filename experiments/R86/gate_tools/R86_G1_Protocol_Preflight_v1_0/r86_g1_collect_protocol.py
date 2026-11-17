#!/usr/bin/env python3
"""Collect read-only R85 runner/manifest evidence for building an isolated R86 G1 runner.

Never runs the R85 script, never builds an ANN graph, never modifies R85/H70.
Copies only small source/config/log files to a NEW R86 evidence directory.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil
import sys

PICKED_LOGS = ('t4_r1_STOCK.build.log', 't4_r1_C64_K512_N2.build.log')
MAX_FILE = 3 * 1024 * 1024
MAX_FILES = 35
RUNNER_NAME = 'run_r85_scale1_bigann1m_v1.py'


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as fp:
        for chunk in iter(lambda: fp.read(2 ** 20), b''):
            h.update(chunk)
    return h.hexdigest()


def report_file(path, reason, out, records, *, copy=False, root=None):
    path = Path(path).expanduser()
    item = {'path': str(path), 'purpose': reason, 'exists': path.is_file()}
    if not item['exists']:
        records.append(item)
        return
    item['size'] = path.stat().st_size
    if item['size'] > MAX_FILE:
        item['status'] = 'SKIP_TOO_LARGE'
        records.append(item)
        return
    item['sha256'] = sha256(path)
    item['status'] = 'READ_ONLY_AUDITED'
    if copy:
        if root is None:
            dest = out / 'files' / path.name
        else:
            dest = out / 'files' / path.relative_to(root)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
        item['evidence_copy'] = str(dest.relative_to(out))
    records.append(item)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--home', type=Path, default=Path.home())
    ap.add_argument('--out', type=Path, help='New empty output directory; refuses overwrite')
    args = ap.parse_args()
    home = args.home.expanduser().resolve()
    exp = home / 'ann-task-a' / 'experiments'
    r85 = exp / 'H85' / 'r85_scale1_bigann1m'
    session = r85 / 'bigann1m_20261112-022002_494222'
    out = args.out or exp / 'R86' / 'gates' / ('g1_r85_protocol_' + dt.datetime.now().strftime('%Y%m%d_%H%M%S'))
    out = out.expanduser().absolute()
    if out.exists():
        raise SystemExit(f'FAIL: output directory already exists; refusing overwrite: {out}')
    if not exp.exists():
        raise SystemExit(f'FAIL: missing experiments root: {exp}')
    out.mkdir(parents=True)
    files = []
    runner = home / 'Downloads' / RUNNER_NAME
    report_file(runner, 'R85 SCALE1 runner source (never execute)', out, files, copy=True)
    print('RUNNER', runner, 'FOUND' if runner.is_file() else 'MISSING')

    # Collect the stored R85 build commands/manifest from the ONE pinned session.
    print('R85_SESSION', session, 'FOUND' if session.is_dir() else 'MISSING')
    if session.is_dir():
        for basename in PICKED_LOGS:
            report_file(session / basename, 'Historical R85 build stdout', out, files, copy=True, root=session)
        candidates = []
        for path in session.rglob('*'):
            if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_FILE:
                continue
            if path.name in PICKED_LOGS:
                continue
            lower = path.name.lower()
            if path.suffix.lower() in ('.json', '.jsonl', '.txt') and any(
                key in lower for key in ('manifest', 'command', 'build_summary', 'config', 'protocol', 'run_index')
            ):
                candidates.append(path)
        candidates.sort(key=lambda p: (len(p.relative_to(session).parts), str(p)))
        for path in candidates[:MAX_FILES]:
            report_file(path, 'R85 pinned protocol/config/manifest', out, files, copy=True, root=session)
    else:
        print('WARN: no R85 session found; source runner may still be sufficient')

    # Just a file listing of runners and existing output structure, not a search of large data.
    for path in [
        exp / 'R86' / 'r86_v1_2_source' / 'R86_STAGING_PROVENANCE.json',
        exp / 'R86' / 'gates' / 'g0_20261113_011256' / 'g0_manifest.json'
    ]:
        report_file(path, 'R86 G0 provenance (read-only)', out, files, copy=True)

    summary = {
        'schema': 'R86_G1_R85_protocol_preflight_v1',
        'created_local': dt.datetime.now().astimezone().isoformat(timespec='seconds'),
        'R85_runner': str(runner),
        'R85_session': str(session),
        'R86_target': str(exp / 'R86' / 'r86_v1_2_builds'),
        'file_evidence': files,
        'status': 'PREFLIGHT_EVIDENCE_ONLY_NO_ANN_RUN',
        'WARNING': 'Never execute the R85 historical runner with --resume-build or --run-quality on R85 session for R86 measurements.'
    }
    (out / 'preflight_manifest.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    readme = [
        'R86 G1 PROTOCOL PREFLIGHT — READ ONLY',
        f'R85 runner: {runner}',
        f'R85 session: {session}',
        'G0 has passed; G1 has not run.',
        'The file copies are source/config/logs only — no .graph, fbin/u8bin or executable.',
        'DO NOT run R85 --resume-build/--run-quality on old session.',
    ]
    (out / 'README_EVIDENCE.txt').write_text('\n'.join(readme) + '\n')
    print('R86_G1_R85_PROTOCOL_PREFLIGHT_COLLECTED')
    print('EVIDENCE_DIR', out)
    print('RUNNER_COPY', 'YES' if runner.is_file() and runner.stat().st_size <= MAX_FILE else 'NO')
    print('MANIFEST_FILES', sum(x['purpose'] == 'R85 pinned protocol/config/manifest' for x in files))
    print('NEXT: package this NEW directory and upload for exact G1 R86 runner construction')
    return 0 if runner.is_file() and session.is_dir() else 2

if __name__ == '__main__':
    sys.exit(main())
