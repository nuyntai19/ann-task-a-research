#!/usr/bin/env python3
"""R64: read-only, provenance-conservative inventory for ANN Task A.

Run `selftest` or `audit`. Never alters any existing ANN data, graph, source,
logs or historical reports. Audit only creates one exclusive JSON report.
Only scans the bounded data/ directory; it does NOT claim full filesystem discovery.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import struct
import sys
import tempfile
from pathlib import Path

PIN_GRAPH_SHA = 'd497f6d19fff4b7db6436f960d036755e375be92483c03ec0b9ed61968d17bef'
PIN_POOL_SHA = '7e22a4ca2b71bd560560f7e4aa2a1f2dcad46b8f25ae48ca8ea014c17086f9e8'
PIN_LOG_NODUMP_SHA = '971ae489fff5aa5659f5833c377e709ec96775e8e01633eb3a2e50c01471ca2f'
PIN_LOG_DUMP_SHA = 'f0736533770f4fb569c81cbea608863a0c7baa407db804b5514bee3f855e5c72'
R26 = 'experiments/H32/H32_R26a_pool_20261029_172452_132314'
DATA_KEYWORDS = ('sift', 'bigann', 'gist', 'laion', 'deep', 'glove', 'yelp', 'dbpedia')
DATA_SUFFIXES = ('.fbin', '.u8bin', '.ibin', '.npy', '.h5', '.hdf5', '.bvecs', '.fvecs', '.ivecs', '.bin')


def sha256_file(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def inspect_binary_matrix(path, kind):
    """Header/size checks only, NOT data contents or GT semantic correctness."""
    bpe = {'fbin': 4, 'u8bin': 1, 'ibin': 4}[kind]
    size = path.stat().st_size
    if size < 8:
        return {'status':'INVALID', 'reason':'shorter than 8-byte header'}
    with path.open('rb') as f:
        n, d = struct.unpack('<ii', f.read(8))
    if not (1 <= n <= 1_000_000_000 and 1 <= d <= 100_000):
        return {'status':'INVALID', 'reason':'invalid positive n/d header', 'header_n':n, 'header_d':d}
    expect = 8 + n * d * bpe
    result = {'header_n':n, 'header_d':d, 'expected_payload_only_bytes':expect,
              'actual_bytes':size, 'kind':kind}
    if kind == 'ibin':
        # Some GT archives store only IDs; others concatenate float32 distances.
        expected_plus_dist = 8 + n * d * 8
        result['expected_ids_and_float_distances_bytes'] = expected_plus_dist
        if size == expect:
            result.update(status='PASS', layout='ids_only')
        elif size == expected_plus_dist:
            result.update(status='PASS', layout='ids_plus_float32_distances')
        else:
            result.update(status='INVALID', reason='GT header/size mismatch')
    else:
        result['status'] = 'PASS' if size == expect else 'INVALID'
        if size != expect:
            result['reason'] = 'matrix header/size mismatch'
    return result


def file_record(root, rel, *, kind=None, expected_bytes=None, expected_sha=None,
                sha_max=128*1024*1024, hash_when_expected=True, must_n=None, must_d=None):
    path = root / rel
    rec = {'relative_path':rel}
    try:
        if path.is_symlink():
            rec.update(status='UNTRUSTED_SYMLINK', reason='symlinks intentionally not followed')
            return rec
        if not path.is_file():
            rec['status'] = 'MISSING'
            return rec
        size = path.stat().st_size
        rec.update(status='PRESENT', bytes=size)
        if expected_bytes is not None and size != expected_bytes:
            rec.update(status='INVALID', reason=f'expected {expected_bytes} bytes')
        if kind:
            payload = inspect_binary_matrix(path,kind)
            rec['matrix'] = payload
            if payload['status'] != 'PASS':
                rec.update(status='INVALID', reason='matrix-format validation failed')
            if must_n is not None and payload.get('header_n') != must_n:
                rec.update(status='INVALID', reason='unexpected row count')
            if must_d is not None and payload.get('header_d') != must_d:
                rec.update(status='INVALID', reason='unexpected dimension')
        hash_this = size <= sha_max or (expected_sha is not None and hash_when_expected)
        if hash_this:
            actual_sha = sha256_file(path)
            rec['sha256'] = actual_sha
            if expected_sha is not None:
                rec['expected_sha256'] = expected_sha
                rec['sha_match'] = actual_sha == expected_sha
                if not rec['sha_match']:
                    rec.update(status='INVALID', reason='pinned sha256 mismatch')
        else:
            rec['sha256'] = 'NOT_COMPUTED_LARGE_FILE'
            if expected_sha:
                rec['expected_sha256'] = expected_sha
                rec['sha_match'] = 'UNVERIFIED'
        if rec['status'] == 'PRESENT':
            if expected_sha is not None and rec.get('sha_match') == 'UNVERIFIED':
                rec['status'] = 'SIZE_ONLY_SHA_UNVERIFIED'
            elif expected_sha is not None or kind is not None or expected_bytes is not None:
                rec['status'] = 'PASS'
            else:
                rec['status'] = 'PRESENT_UNVERIFIED'
        if rel.endswith('.graph') and rec['status'] == 'PASS':
            with path.open('rb') as f:
                h = f.read(8)
            if len(h) == 8:
                n, max_deg = struct.unpack('<II', h)
                rec['graph_header'] = {'n':n, 'max_degree':max_deg}
                if n != 1_000_000 or max_deg != 32:
                    rec.update(status='INVALID', reason='unexpected graph header')
    except (OSError, ValueError, OverflowError) as exc:
        rec.update(status='ERROR', reason=str(exc)[:400])
    return rec


def bounded_data_discovery(root, max_depth=3, max_entries=4000, max_results=300):
    data = root / 'data'
    out = []
    stats = {'scoped_root':'data/', 'max_depth':max_depth, 'entry_limit':max_entries,
             'result_limit':max_results, 'scanned_entries':0,
             'truncated':False,'note':'Only regular files, no symlink recursion; not a global filesystem inventory.'}
    if not data.is_dir():
        return out, stats
    queue = [(data, 0)]
    while queue and stats['scanned_entries'] < max_entries and len(out) < max_results:
        parent, dep = queue.pop(0)
        try:
            entries = sorted(os.scandir(parent), key=lambda e:e.name)
        except (OSError, PermissionError):
            continue
        for e in entries:
            stats['scanned_entries'] += 1
            if stats['scanned_entries'] > max_entries:
                stats['truncated'] = True
                break
            try:
                if e.is_symlink():
                    continue
                if e.is_dir(follow_symlinks=False):
                    if dep < max_depth:
                        queue.append((Path(e.path),dep+1))
                elif e.is_file(follow_symlinks=False):
                    if (e.name.lower().endswith(DATA_SUFFIXES) or
                        any(k in e.name.lower() for k in DATA_KEYWORDS)):
                        path = Path(e.path)
                        item = {'path':str(path.relative_to(root)), 'bytes':e.stat().st_size,
                                'classification':'DISCOVERED_ONLY_UNMATCHED_PROVENANCE'}
                        # Avoid reading gigabyte files; validate only known formats.
                        kind = path.suffix.lower().lstrip('.')
                        if kind in {'fbin','ibin','u8bin'}:
                            item['matrix'] = inspect_binary_matrix(path,kind)
                        out.append(item)
                    if len(out)>=max_results:
                        stats['truncated']=True
                        break
            except (OSError,ValueError,OverflowError):
                continue
    if queue or stats['scanned_entries']>=max_entries:
        stats['truncated']=True
    return out, stats


def audit(root, sha_max_mb):
    root = root.resolve()
    if not root.is_dir():
        raise ValueError('root must exist and be a directory')
    sha_max = sha_max_mb * 1024 * 1024
    spec = {
        'SIFT1M': [
            ('base','data/sift1m.fbin','fbin',512_000_008,1_000_000,128),
            ('queries','data/sift1m_queries.fbin','fbin',5_120_008,10_000,128),
            ('gt','data/sift1m_gt.ibin','ibin',8_000_008,10_000,100),
        ],
    }
    data = {}
    for ds, entries in spec.items():
        data[ds]={}
        for role, rel, kind, size, n, d in entries:
            data[ds][role]=file_record(root,rel,kind=kind,expected_bytes=size,
                                      must_n=n,must_d=d,sha_max=sha_max)
    r26_entries = {
        'nodump_graph':file_record(root, R26+'/nodump.graph',expected_bytes=95_190_528,
                                    expected_sha=PIN_GRAPH_SHA, sha_max=sha_max),
        'dump_graph':file_record(root,R26+'/dump.graph',expected_bytes=95_190_528,
                                    expected_sha=PIN_GRAPH_SHA,sha_max=sha_max),
        'pool_export':file_record(root,R26+'/dump.candidates.i32',expected_bytes=640_000_000,
                                  expected_sha=PIN_POOL_SHA,sha_max=sha_max,
                                  hash_when_expected=False),
        'nodump_build_log':file_record(root,R26+'/nodump.time.log',expected_sha=PIN_LOG_NODUMP_SHA,
                                       sha_max=sha_max),
        'dump_build_log':file_record(root,R26+'/dump.time.log',expected_sha=PIN_LOG_DUMP_SHA,
                                     sha_max=sha_max),
    }
    archival = {
        'R54_build_provenance_report':file_record(root,'experiments/H54/r54_archival_build_gate.json',sha_max=sha_max),
        'R47_search_q_sensitivity':file_record(root,'experiments/H47/r47_r5_q_sensitivity.json',sha_max=sha_max),
        'R59_occupancy':file_record(root,'experiments/H59/r59_reservoir_occupancy.json',sha_max=sha_max),
    }
    historical_leaf = {}
    for name in ('sift1m','bigann1m','bigann1m_u8','bigann10m_u8'):
        rel='experiments/H18/phase1_leaf_overlap/'+name+'.leaves.bin'
        record=file_record(root,rel,sha_max=sha_max)
        if record['status']=='PRESENT_UNVERIFIED':
            with (root/rel).open('rb') as f:
                b=f.read(24)
            if len(b)==24 and b[:8]==b'H18LEAF1':
                n,leaves=struct.unpack('<QQ',b[8:])
                record['leaf_header']={'magic':'H18LEAF1','base_n':n,'num_leaves':leaves}
                record['status']='HEADER_PASS_NOT_FULL_CONTENT_CHECK'
            else:
                record.update(status='INVALID',reason='H18 leaf header mismatch')
        historical_leaf[name]=record
    discovery, discovery_stats=bounded_data_discovery(root)
    sift_inputs_pass = all(v['status']=='PASS' for v in data['SIFT1M'].values())
    sift_graph_pin = r26_entries['nodump_graph']['status']=='PASS'
    sift_build_logs = r26_entries['nodump_build_log']['status']=='PASS'
    # Cross-dataset interpretation is intentionally conservative: discovered raw data and
    # leaf memberships are not equivalent to source-verified full ANN build/search evidence.
    report = {
        'audit':'R64_READONLY_DATASET_EVIDENCE_INVENTORY',
        'created_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
        'root':str(root),
        'scope':'ONLY_PREVIOUSLY_PINNED_R26A_AND_BOUNDED_DATA_DISCOVERY',
        'not_done':['NO_BUILD','NO_SEARCH','NO_GRAPH_MODIFICATION','NO_FULL_FILESYSTEM_WALK',
                    'NO_NEW_HUBNESS_OR_LID_MEASUREMENT','NO_AUTOMATIC_CROSS_RUN_ARTIFACT_JOINS'],
        'known_historical_facts_from_google_doc_not_live_recomputed':{
            'SIFT1M_R26a_arcs':22_797_630,'SIFT1M_R26a_bytes':95_190_528,
            'R26a_nodump_wall_seconds':47.58,'R26a_nodump_peak_rss_KiB':2_599_924,
            'R47_fixed_graph_Q100_recall_at_10':0.99096,
            'R47_fixed_graph_Q160_recall_at_10':0.99667,
            'H18_BIGANN1M_evidence':'LEAF_MEMBERSHIP_ONLY_NO_ANN_BUILD_OR_SEARCH',
            'H18_BIGANN10M_evidence':'LEAF_MEMBERSHIP_ONLY_NO_ANN_BUILD_OR_SEARCH',
        },
        'verified_inputs':data,
        'R26a_known_source_graph':r26_entries,
        'historical_report_presence_only':archival,
        'H18_leaf_membership_source_not_R26a_build':historical_leaf,
        'bounded_data_discovery':discovery,
        'bounded_discovery_stats':discovery_stats,
        'gates':{
            'SIFT1M_INPUTS': 'PASS' if sift_inputs_pass else 'BLOCKED',
            'R26A_GRAPH_SHA_PROVENANCE': 'PASS' if sift_graph_pin else 'BLOCKED',
            'R26A_BUILD_LOG_SHA': 'PASS' if sift_build_logs else 'BLOCKED',
            'MULTI_DATASET_GRAPH_SEARCH_BUILD_PARITY':'BLOCKED_NOT_PROVEN_BY_THIS_INVENTORY',
            'HUBNESS_LID_CONSTRUCTION_FAILURE':'UNMEASURED',
            'H33':'NOT_OPEN',
        },
        'caveat':'SIFT graph/BUILD and R47 query evidence originate from historical separated processes; this inventory does not parse all search logs and does not prove same-protocol multi-dataset Pareto. Alternate dataset graph/search/build provenance requires a separate verified manifest, not a filename match.'
    }
    return report


def save_exclusive(dest,obj):
    # No overwrite, no implicit directory creation; do not follow a preexisting symlink.
    with dest.open('x',encoding='utf-8') as f:
        json.dump(obj,f,indent=2,ensure_ascii=False,sort_keys=True)
        f.write('\n')


def selftest():
    with tempfile.TemporaryDirectory(prefix='r64_selftest_') as d:
        root=Path(d)
        root.joinpath('data').mkdir()
        base = root/'data'/'sift1m.fbin'
        base.write_bytes(struct.pack('<ii',3,2)+struct.pack('<6f',*(float(x) for x in range(6))))
        assert inspect_binary_matrix(base,'fbin')['status']=='PASS'
        gt=root/'data'/'sift1m_gt.ibin'
        gt.write_bytes(struct.pack('<ii',2,2)+struct.pack('<4i',0,1,2,3)+struct.pack('<4f',.1,.2,.3,.4))
        assert inspect_binary_matrix(gt,'ibin')['layout']=='ids_plus_float32_distances'
        assert inspect_binary_matrix(gt,'ibin')['status']=='PASS'
        with gt.open('ab') as f:f.write(b'X')
        assert inspect_binary_matrix(gt,'ibin')['status']=='INVALID'
        sha=sha256_file(base)
        assert file_record(root,'data/sift1m.fbin',expected_sha=sha)['status']=='PASS'
        assert file_record(root,'data/sift1m.fbin',expected_sha='a'*64)['status']=='INVALID'
        g=root/'data'/'bigann1m.u8bin'
        g.write_bytes(struct.pack('<ii',3,2)+bytes([0,1,2,3,4,5]))
        found,meta=bounded_data_discovery(root)
        assert any(x['path']=='data/bigann1m.u8bin' for x in found)
        dest=root/'r64.json'
        save_exclusive(dest,{'test':True})
        try:
            save_exclusive(dest,{'overwrite':True})
        except FileExistsError:
            pass
        else:
            raise AssertionError('exclusive-create must refuse overwrites')
        # Missing real R26 artifacts must fail closed rather than assert multi-dataset readiness.
        rep=audit(root,1)
        assert rep['gates']['R26A_GRAPH_SHA_PROVENANCE']=='BLOCKED'
        assert rep['gates']['MULTI_DATASET_GRAPH_SEARCH_BUILD_PARITY'].startswith('BLOCKED')
    print('R64_SYNTHETIC_SELFTEST_PASS')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='mode',required=True)
    sub.add_parser('selftest')
    a=sub.add_parser('audit')
    a.add_argument('--root',default='.')
    a.add_argument('--output',required=True)
    a.add_argument('--hash-max-mib',type=int,default=128,help='Limit hashing of unpinned large files; pinned graph 95MB always hashed')
    args=parser.parse_args()
    if args.mode=='selftest':
        selftest();return
    if not (1<=args.hash_max_mib<=1024):
        parser.error('hash-max-mib must be 1..1024')
    report=audit(Path(args.root),args.hash_max_mib)
    out=Path(args.output)
    if not out.parent.is_dir():
        parser.error('output directory not present (create it explicitly before run)')
    try:
        save_exclusive(out,report)
    except FileExistsError:
        print('R64_OUTPUT_EXISTS_NOT_OVERWRITTEN',out,file=sys.stderr)
        sys.exit(2)
    print('R64_READONLY_INVENTORY_COMPLETED')
    for key,value in report['gates'].items():print('R64_GATE',key,value)
    print('R64_DISCOVERED_DATA_CANDIDATES',len(report['bounded_data_discovery']))
    for item in report['bounded_data_discovery'][:60]:
        print('R64_DATA_FILE',item['path'],item['bytes'],item.get('matrix',{}).get('status','METADATA_ONLY'))
    if len(report['bounded_data_discovery'])>60:
        print('R64_MORE_CANDIDATES_IN_JSON',len(report['bounded_data_discovery'])-60)
    print('R64_REPORT',str(out))


if __name__=='__main__':
    main()
