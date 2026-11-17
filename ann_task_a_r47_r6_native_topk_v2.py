#!/usr/bin/env python3
"""R47-R6 v2: independent native SEARCH IDs at Q80/120/160.

Fixes the two confirmed R6-v1 problems:
* R45 writes SEARCH/EVAL to per-query q_<ID>.trace FILES, enabled by
  ANN_R45_TRACE_DIR and ANN_R45_TRACE_QIDS, not stdout/stderr.
* R45's two C++ trace hooks are deliberately gated to QP.beamSize==100.
  Patch ONLY those two gating expressions in a SEPARATE COPY of H45 source.

Commands (from ~/ann-task-a):
  python3 ann_task_a_r47_r6_native_topk_v2.py selftest
  python3 ann_task_a_r47_r6_native_topk_v2.py prepare --build
  python3 -u ann_task_a_r47_r6_native_topk_v2.py run
  python3 -u ann_task_a_r47_r6_native_topk_v2.py audit

No graph construction, source overwrite, or modification of H45/R47-R5.
The native baseline is independent of the R47 beam-decision instrumentation.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

from ann_task_a_r47_r6_native_topk_independent import required_inputs, parse_metrics

PINNED_SOURCE_COMMIT = 'a48c6a34e5f959190992aa531cc18454cfcc3dd3'
ROOT = Path('experiments/H47')
R6 = ROOT / 'R6_v2'
SRC_R45 = Path('experiments/H45/ParlayANN-native-trace')
SRC_COPY = R6 / 'ParlayANN-native-trace-r6'
BUILD_LOG = R6 / 'r6_v2_build.log'
BIN = SRC_COPY / 'algorithms/vamana/neighbors'
PATCH_REPORT = R6 / 'source_patch_manifest.json'
QS = (80, 120, 160)
R5_REPORT = ROOT / 'r47_r5_q_sensitivity.json'

SEARCH_ANCHOR = 'if (r45_selected && QP.beamSize == 100) {'
SEARCH_REPLACEMENT = 'if (r45_selected && (QP.beamSize == 80 || QP.beamSize == 120 || QP.beamSize == 160)) {'
EVAL_ANCHOR = 'if (r45_ids && QP.beamSize == 100 && GT.size() > 0 && k > 0) {'
EVAL_REPLACEMENT = ('if (r45_ids && (QP.beamSize == 80 || QP.beamSize == 120 || '
                    'QP.beamSize == 160) && GT.size() > 0 && k > 0) {')


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as fp:
        for block in iter(lambda: fp.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def patch(text, anchor, replacement, filename):
    if text.count(anchor) != 1:
        raise ValueError(f'{filename}: expected EXACTLY ONE guarded trace anchor; got {text.count(anchor)}')
    if replacement in text:
        raise ValueError(f'{filename}: v2 patch already applied')
    out = text.replace(anchor, replacement, 1)
    if out.replace(replacement, anchor, 1) != text:
        raise ValueError(f'{filename}: patch was not limited to one trace-gate expression')
    return out


def verify_original_source():
    for rel in ('algorithms/utils/beamSearch.h', 'algorithms/utils/check_nn_recall.h'):
        if not (SRC_R45 / rel).is_file():
            raise ValueError(f'R45 source file missing: {SRC_R45 / rel}')
    b = (SRC_R45/'algorithms/utils/beamSearch.h').read_text()
    e = (SRC_R45/'algorithms/utils/check_nn_recall.h').read_text()
    if 'R45 diagnostic' not in b or 'R45 evaluation trace' not in e:
        raise ValueError('Expected R45 SEARCH and EVAL diagnostic hooks not found in original source')
    return b, e


def prepare(build=False):
    qids, _ = required_inputs()
    if R6.exists():
        raise ValueError(f'Isolated R6 directory already exists; refuse overwrite: {R6}')
    b, e = verify_original_source()
    changed_b = patch(b, SEARCH_ANCHOR, SEARCH_REPLACEMENT, 'beamSearch.h')
    changed_e = patch(e, EVAL_ANCHOR, EVAL_REPLACEMENT, 'check_nn_recall.h')
    # Verify pinned base repository HEAD, never modify this repository.
    head = subprocess.check_output(['git', '-C', 'src/ParlayANN', 'rev-parse', 'HEAD'], text=True).strip()
    if head != PINNED_SOURCE_COMMIT:
        raise ValueError(f'ParlayANN checkout changed: {head} != {PINNED_SOURCE_COMMIT}')
    R6.mkdir(parents=True, exist_ok=False)
    # Copy source, never source .git or old build outputs. Preserve vendored libraries.
    def ignore(directory, names):
        exclude = {n for n in names if n in ('.git','build','CMakeFiles','__pycache__')
                   or n.endswith(('.o', '.a', '.gch', '.pyc'))}
        if Path(directory).resolve() == (SRC_R45/'algorithms/vamana').resolve():
            exclude.add('neighbors')
        return exclude
    shutil.copytree(SRC_R45, SRC_COPY, symlinks=True, ignore=ignore)
    target_b = SRC_COPY/'algorithms/utils/beamSearch.h'
    target_e = SRC_COPY/'algorithms/utils/check_nn_recall.h'
    if target_b.is_symlink() or target_e.is_symlink():
        raise ValueError('Refusing to write through symlink in source copy')
    target_b.write_text(changed_b)
    target_e.write_text(changed_e)
    details = {
        'audit': 'R47_R6_V2_ISOLATED_TRACE_GATE_PATCH',
        'pinned_commit': head,
        'source_r45': str(SRC_R45),
        'destination': str(SRC_COPY),
        'only_edited_files': ['algorithms/utils/beamSearch.h', 'algorithms/utils/check_nn_recall.h'],
        'search_gate_old': SEARCH_ANCHOR, 'search_gate_new': SEARCH_REPLACEMENT,
        'eval_gate_old': EVAL_ANCHOR, 'eval_gate_new': EVAL_REPLACEMENT,
        'original_hashes': {'beamSearch.h':sha256(SRC_R45/'algorithms/utils/beamSearch.h'),
                            'check_nn_recall.h':sha256(SRC_R45/'algorithms/utils/check_nn_recall.h')},
        'patched_hashes': {'beamSearch.h':sha256(target_b), 'check_nn_recall.h':sha256(target_e)},
        'targets':qids,
    }
    PATCH_REPORT.write_text(json.dumps(details, indent=2, ensure_ascii=False) + '\n')
    print('R47_R6_V2_SOURCE_COPY_PATCH_PASS', flush=True)
    print('SOURCE', SRC_COPY, flush=True)
    print('PATCH_MANIFEST', PATCH_REPORT, flush=True)
    if build:
        print('BUILDING ISOLATED NATIVE R6 BINARY', flush=True)
        with BUILD_LOG.open('w') as log:
            subprocess.run(['make', '-j2', 'OPENMP=1', 'neighbors'], cwd=SRC_COPY/'algorithms/vamana',
                           stdout=log, stderr=subprocess.STDOUT, check=True)
        if not BIN.is_file() or not os.access(BIN, os.X_OK):
            raise ValueError(f'Isolated neighbors executable missing after build: {BIN}')
        print('R47_R6_V2_BUILD_PASS', flush=True)
        print('BINARY', BIN, flush=True)
        print('BUILD_LOG', BUILD_LOG, flush=True)
    else:
        print('RUN make -j2 OPENMP=1 neighbors IN COPY BEFORE run', flush=True)


def check_source_copy():
    if not PATCH_REPORT.is_file():
        raise ValueError('Run `prepare --build` first; R6 v2 patch manifest missing')
    meta = json.loads(PATCH_REPORT.read_text())
    if meta['pinned_commit'] != PINNED_SOURCE_COMMIT:
        raise ValueError('R6 v2 source commit pin mismatch')
    for label,rel in [('beamSearch.h','algorithms/utils/beamSearch.h'),
                      ('check_nn_recall.h','algorithms/utils/check_nn_recall.h')]:
        if sha256(SRC_R45/rel) != meta['original_hashes'][label]:
            raise ValueError(f'Original H45 source CHANGED since prepare: {rel}')
        if sha256(SRC_COPY/rel) != meta['patched_hashes'][label]:
            raise ValueError(f'R6 v2 source CHANGED since prepare: {rel}')
    if not BIN.is_file() or not os.access(BIN, os.X_OK):
        raise ValueError('R6 v2 executable missing; `prepare --build` may not have finished')


def qdir(q):
    return R6/f'Q{q}'


def read_trace_file(path, qid, q, repeats=5):
    if not path.is_file():
        raise ValueError(f'Missing independent native trace: {path}')
    records = []
    eval_count = 0
    for line_no, raw in enumerate(path.read_text().splitlines(), 1):
        fields = raw.split('|')
        if len(fields) < 2:
            raise ValueError(f'Malformed R45 trace line {path}:{line_no}')
        if fields[0] == 'SEARCH':
            if len(fields) != 8:
                raise ValueError(f'Malformed SEARCH fields {path}:{line_no} ({len(fields)} vs 8)')
            rqid, gotq, k, opaque, cmps = map(int, fields[1:6])
            if (rqid, gotq, k) != (qid, q, 10):
                raise ValueError(f'SEARCH header mismatch at {path}:{line_no}')
            def ids(s): return tuple(int(v) for v in s.split(',') if v.strip())
            beam, visited = ids(fields[6]), ids(fields[7])
            if len(beam) != q or len(set(beam)) != q:
                raise ValueError(f'Unexpected beam length or duplicate IDs at {path}:{line_no}')
            if not visited or len(visited) != len(set(visited)):
                raise ValueError(f'Unexpected visited IDs at {path}:{line_no}')
            records.append({'top10':beam[:10], 'full_beam':beam,
                            'visited':visited, 'comparisons':cmps})
        elif fields[0] == 'EVAL':
            if len(fields) < 6:
                raise ValueError(f'Malformed EVAL {path}:{line_no}')
            if tuple(map(int,fields[1:4])) != (qid, q, 10):
                raise ValueError(f'EVAL header mismatch {path}:{line_no}')
            eval_count += 1
        else:
            raise ValueError(f'Unexpected R45 trace record at {path}:{line_no}: {raw[:50]}')
    if len(records) != repeats or eval_count != repeats:
        raise ValueError(f'q={qid}, Q{q}: expected {repeats} SEARCH and EVAL records, found {len(records)}/{eval_count}')
    for j in range(1,repeats):
        if records[j] != records[0]:
            raise ValueError(f'Native R6 trace differs across repeats q={qid}, Q{q}, repeat={j}')
    return records[0]


def run(q_values):
    qids, _ = required_inputs()
    check_source_copy()
    dirs = [qdir(q) for q in q_values]
    if any(p.exists() for p in dirs):
        raise ValueError('Refusing to overwrite R6 v2 Q output: ' + ', '.join(str(p) for p in dirs if p.exists()))
    flags=['-data_type','float','-dist_func','Euclidian',
           '-base_path', str(Path('data/sift1m.fbin').resolve()),
           '-query_path', str(Path('data/sift1m_queries.fbin').resolve()),
           '-gt_path', str(Path('data/sift1m_gt.ibin').resolve()),
           '-graph_path', str(Path('experiments/H32/H32_R26a_pool_20261029_172452_132314/dump.graph').resolve()),
           '-k','10','-verbose']
    for q in q_values:
        dest=qdir(q)
        traces=dest/'traces'
        traces.mkdir(parents=True, exist_ok=False)
        env=dict(os.environ)
        env.update(PARLAY_NUM_THREADS='1', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
                   ANN_R45_TRACE_DIR=str(traces.resolve()),
                   ANN_R45_TRACE_QIDS=','.join(map(str,qids)))
        print(f'R47_R6_V2_Q{q}_START',flush=True)
        with (dest/'native.stdout').open('w') as o, (dest/'native.stderr').open('w') as e:
            subprocess.run([str(BIN.resolve()),*flags,'-Q',str(q)],
                           stdout=o,stderr=e,env=env,check=True)
        actual = parse_metrics(dest/'native.stdout', q)
        expected = parse_metrics(ROOT/f'r47_r5_q{q:03d}_baseline.stdout', q)
        if actual != expected:
            raise ValueError(f'Q{q}: aggregate metrics differ from pinned R5 original native baseline')
        for qid in qids:
            read_trace_file(traces/f'q_{qid}.trace', qid, q)
        all_files = sorted(traces.glob('q_*.trace'))
        if len(all_files) != len(qids):
            raise ValueError(f'Q{q}: expected only 17 selected trace files, found {len(all_files)}')
        print(f'R47_R6_V2_Q{q}_AGGREGATE_AND_17X5_NATIVE_TRACE_PASS',flush=True)
    print('R47_R6_V2_NATIVE_RUN_COMPLETED',flush=True)


def audit():
    # Load the already installed R47-R3/R4 helpers only when auditing.
    from ann_task_a_r47_r3_witness_audit import read_events
    from ann_task_a_r47_r4_topk_parity_v2 import Fbin, exact_integer_l2, reconstruct_r47
    qids, by_id = required_inputs()
    check_source_copy()
    for q in QS:
        dest=qdir(q)
        if not (dest/'native.stdout').is_file():
            raise ValueError(f'Missing R6 v2 run at Q{q}')
    if (R6/'r47_r6_v2_independent_native_parity.json').exists():
        raise ValueError('R6 v2 audit report already exists; refusing overwrite')
    summary=[]
    base=Fbin(Path('data/sift1m.fbin'))
    queries=Fbin(Path('data/sift1m_queries.fbin'))
    try:
        for q in QS:
            dest=qdir(q)
            native_metrics = parse_metrics(dest/'native.stdout',q)
            r5_baseline_metrics = parse_metrics(ROOT/f'r47_r5_q{q:03d}_baseline.stdout',q)
            if native_metrics != r5_baseline_metrics:
                raise ValueError(f'Q{q}: R6 native aggregate vs R5 native baseline mismatch')
            events=read_events(ROOT/f'r47_r5_q{q:03d}_events.stderr',set(qids),expected_repeats=5)
            qrows=[]
            for qid in qids:
                native=read_trace_file(dest/'traces'/f'q_{qid}.trace',qid,q)
                trace=reconstruct_r47(events[qid],qid,beam_size=q)
                query_vec=queries.vector(qid)
                r47_scored=[]
                for id_,log_distance in trace['beam_distances_printed'].items():
                    true_distance=exact_integer_l2(query_vec,base.vector(id_))
                    if abs(float(true_distance)-log_distance) > max(0.51,abs(true_distance)*1.0e-5):
                        raise ValueError(f'Q{q} query={qid} distance mismatch node={id_}')
                    r47_scored.append((true_distance,id_))
                r47_beam=tuple(id_ for d,id_ in sorted(r47_scored))
                if native['full_beam'] != r47_beam:
                    raise ValueError(f'Q{q} query={qid}: native full-beam IDs/order differ from R47 trace reconstruction')
                if native['top10'] != tuple(by_id[qid]['by_q'][str(q)]['top10']):
                    raise ValueError(f'Q{q} query={qid}: independent native Top-10 differs from R47-R5')
                if set(native['visited']) != trace['visited_ids']:
                    raise ValueError(f'Q{q} query={qid}: independent native visited ID SET differs from R47')
                if native['comparisons'] != trace['comparisons']:
                    raise ValueError(f'Q{q} query={qid}: independent native comparisons differ from R47')
                if len(native['visited']) != by_id[qid]['by_q'][str(q)]['visited_count']:
                    raise ValueError(f'Q{q} query={qid}: visited count differs from R5 report')
                qrows.append({'query_id':qid, 'top10_ids':list(native['top10']),
                              'visited_count':len(native['visited']),
                              'comparisons':native['comparisons']})
            print(f'R47_R6_V2_Q{q}_TOP10_FULL_BEAM_VISITED_COMPARISONS_PARITY_PASS 17/17 x 5 repeats',flush=True)
            summary.append({'Q':q,'aggregate_native_metrics':native_metrics,
                            'queries_passed':len(qrows),'query_results':qrows})
    finally:
        base.close()
        queries.close()
    report={'audit':'R47_R6_V2_INDEPENDENT_NATIVE_TOP10_PARITY_PASS',
            'Q':list(QS),'selected_queries':qids,'repeats':5,
            'method':'isolate R45 trace instrumentation, change ONLY Q gate in source COPY, set original R45 trace env vars, compare native file SEARCH IDs to R47-R5',
            'per_q':summary,
            'caveat':'Observational search-level parity only; does not demonstrate graph construction improvement or novelty.'}
    out=R6/'r47_r6_v2_independent_native_parity.json'
    out.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print('R47_R6_V2_INDEPENDENT_NATIVE_TOP10_PARITY_PASS',flush=True)
    print('OUTPUT',out,flush=True)


def selftest():
    b='preamble\n  // R45 diagnostic.\n  '+SEARCH_ANCHOR+'\ntrailing\n'
    e='preamble\n  // R45 evaluation trace\n  '+EVAL_ANCHOR+'\ntrailing\n'
    assert SEARCH_REPLACEMENT in patch(b,SEARCH_ANCHOR,SEARCH_REPLACEMENT,'beam')
    assert EVAL_REPLACEMENT in patch(e,EVAL_ANCHOR,EVAL_REPLACEMENT,'eval')
    try:
        patch(b.replace(SEARCH_ANCHOR,SEARCH_REPLACEMENT),SEARCH_ANCHOR,SEARCH_REPLACEMENT,'beam')
        raise AssertionError('Duplicate patch accepted')
    except ValueError:
        pass
    with TemporaryDirectory() as td:
        path=Path(td)/'q_42.trace'
        beam=','.join(map(str,range(80)))+','
        visited='1,2,3,'
        line=f'SEARCH|42|80|10|0|313|{beam}|{visited}\nEVAL|42|80|10|1,2,|1,2,|1,2,3,\n'
        path.write_text(line*5)
        rec=read_trace_file(path,42,80)
        assert rec['top10']==tuple(range(10)) and rec['comparisons']==313
        path.write_text(line*4)
        try:
            read_trace_file(path,42,80)
            raise AssertionError('Missing search/eval repeat accepted')
        except ValueError:
            pass
        path.write_text((line*5).replace('SEARCH|42|80|10|0|313','SEARCH|42|80|10|0|314',1))
        try:
            read_trace_file(path,42,80)
            raise AssertionError('Mismatched repeat accepted')
        except ValueError:
            pass
    print('R47_R6_V2_SELFTEST_PASS: isolated trace gates, per-query SEARCH/EVAL, 5 repeats, mismatches')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    actions=parser.add_subparsers(dest='action',required=True)
    actions.add_parser('selftest')
    prep=actions.add_parser('prepare');prep.add_argument('--build',action='store_true')
    runp=actions.add_parser('run');runp.add_argument('--q',nargs='+',type=int,choices=QS,default=list(QS))
    actions.add_parser('audit')
    args=parser.parse_args()
    try:
        if args.action=='selftest':selftest()
        elif args.action=='prepare':prepare(args.build)
        elif args.action=='run':run(args.q)
        else:audit()
    except (OSError,ValueError,KeyError,AssertionError,subprocess.CalledProcessError) as exc:
        print('R47_R6_V2_FAIL:',exc,file=sys.stderr)
        sys.exit(2)


if __name__=='__main__':main()
