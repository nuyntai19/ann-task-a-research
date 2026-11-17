#!/usr/bin/env python3
"""R65: bounded, read-only search for a SECOND dataset ANN build/search record.

Strictly an inventory: filename/context hints are NOT dataset/graph provenance.
Never runs BUILD/SEARCH, hashes giant files, changes source, or follows symlinks.
Only writes one new JSON report with exclusive-create, refusing overwrite.
"""
import argparse
import array
import datetime
import hashlib
import json
import os
import re
import struct
import sys
import tempfile
from collections import defaultdict, deque
from pathlib import Path

DATASETS = (
    ("bigann10m", r"bigann[_-]?(?:first)?10m"),
    ("bigann1m", r"bigann[_-]?1m"),
    ("gist", r"gist"), ("laion", r"laion"),
    ("glove", r"glo?ve"), ("deep", r"deep(?:1m|10m|100m)?"),
    ("yelp", r"yelp"), ("dbpedia", r"dbpedia"),
    ("sift10m", r"sift[_-]?10m"), ("sift1m", r"sift[_-]?1m"),
    ("sift100k", r"sift[_-]?100k"),
)
INDEPENDENT_FAMILIES = {'bigann10m', 'bigann1m', 'gist', 'laion', 'glove', 'deep', 'yelp', 'dbpedia'}
KNOWN_DATA = (
    ('BIGANN1M_U8', 'data/bigann1m_u8.u8bin', 'u8bin', 1_000_000, 128),
    ('BIGANN1M_FLOAT', 'data/bigann1m_prefix.fbin', 'fbin', 1_000_000, 128),
    ('BIGANN10M_U8', 'data/bigann10m_u8.u8bin', 'u8bin', 10_000_000, 128),
    ('SIFT10M_FLOAT', 'data/sift10m.fbin', 'fbin', 10_000_000, 128),
)
GRAPH_SUFFIX = ('.graph', '.index', '.idx', '.hnsw', '.hnswlib')
LOG_SUFFIX = ('.json', '.log', '.txt', '.csv', '.jsonl')
PIN_R26A = 'd497f6d19fff4b7db6436f960d036755e375be92483c03ec0b9ed61968d17bef'


def classify_name(s):
    q = str(s).lower()
    for name, pat in DATASETS:
        if re.search(pat, q):
            return name
    return None


def stat_file(path):
    if path.is_symlink() or not path.is_file():
        return None
    return path.stat().st_size


def header_matrix(path, kind):
    """Only check n,d and bytes. Never assume header validates semantic data."""
    size = stat_file(path)
    if size is None:
        return {'status':'MISSING_OR_SYMLINK'}
    if size < 8:
        return {'status':'INVALID_HEADER', 'bytes':size}
    with path.open('rb') as f:
        n,d = struct.unpack('<ii',f.read(8))
    bpe = 4 if kind=='fbin' else 1
    expected = 8 + n*d*bpe
    status = 'FORMAT_PASS' if (0<n<=20_000_000 and 0<d<=65536 and size==expected) else 'INVALID_FORMAT'
    return {'status':status,'n':n,'dimension':d,'bytes':size,'expected_bytes':expected}


def sha256(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()


def graph_header(path):
    """ParlayANN/PiPNN .graph format check; other formats remain UNKNOWN."""
    size = stat_file(path)
    result={'path':str(path), 'bytes':size, 'format':'UNVERIFIED'}
    if size is None or size<8:
        result['status']='SKIP_MISSING_OR_SHORT'; return result
    with path.open('rb') as f:
        n, max_degree=struct.unpack('<II',f.read(8))
        result['header_n']=n;result['header_max_degree']=max_degree
        if not (1<=n<=20_000_000 and 1<=max_degree<=4096 and size>=8+4*n):
            result['status']='UNKNOWN_GRAPH_FORMAT';return result
        # This reads ONLY the n degree words, not all edges. Bounded by n<=20m.
        remaining=n
        edges=0
        while remaining:
            batch=min(remaining,262144)
            raw=f.read(batch*4)
            if len(raw)!=batch*4:
                result['status']='TRUNCATED_DEGREES';return result
            a=array.array('I'); a.frombytes(raw)
            if sys.byteorder!='little':a.byteswap()
            if any(v>max_degree for v in a):
                result['status']='BAD_DEGREE';return result
            edges+=sum(a)
            remaining-=batch
    if size != 8+4*(n+edges):
        result.update(status='SIZE_MISMATCH_PARLAYANN',expected_bytes=8+4*(n+edges));return result
    result.update(status='HEADER_AND_LENGTH_PASS',format='PARLAYANN_GRAPH_POSSIBLE',directed_edges=edges)
    return result


def bounded_walk(root, relroots, max_entries=18000, max_depth=7):
    """Deterministic breadth-first path inventory; never follows symlinks."""
    seen=0; stopped=False; errors=[]
    graph=[]; logs=[]; q=deque()
    for relative in relroots:
        d=root/relative
        if d.is_dir() and not d.is_symlink():q.append((d,0))
    while q:
        current,dep=q.popleft()
        try: entries=sorted(os.scandir(current), key=lambda x:x.name)
        except OSError as exc:
            errors.append({'path':str(current.relative_to(root)),'error':str(exc)[:160]});continue
        for ent in entries:
            seen+=1
            if seen>max_entries:
                stopped=True;break
            try:
                if ent.is_symlink():continue
                if ent.is_dir(follow_symlinks=False):
                    if dep<max_depth and ent.name not in {'node_modules','.git','__pycache__','_deps','.cache','venv','.venv','build','cmake-build-debug'}:
                        q.append((Path(ent.path),dep+1))
                elif ent.is_file(follow_symlinks=False):
                    relative=str(Path(ent.path).relative_to(root))
                    lower=ent.name.lower()
                    if lower.endswith(GRAPH_SUFFIX):graph.append(relative)
                    elif lower.endswith(LOG_SUFFIX) and (classify_name(relative) or lower in {'manifest.json','metadata.json','run_manifest.json'}):
                        logs.append(relative)
            except OSError as exc:
                errors.append({'path':ent.path,'error':str(exc)[:160]})
        if stopped:break
    return graph, logs, {'scanned_entries':min(seen,max_entries),'entry_cap':max_entries,
                          'truncated':stopped or bool(q),'max_depth':max_depth,'scan_roots':list(relroots),
                          'errors':errors[:20]}


def log_preview(path):
    size=stat_file(path)
    if size is None: return {'status':'MISSING'}
    # Only bounded text from the start and end of source logs. No JSON semantic assumption.
    with path.open('rb') as f:
        b=f.read(32768)
        if size>65536:
            f.seek(max(0,size-32768));b+=b'\n'+f.read(32768)
    text=b.decode('utf-8','replace')
    p={'status':'TEXT_SAMPLE_ONLY','bytes':size,'sampled_bytes':len(b)}
    checks={
      'graph_path':r'\b\S+\.graph\b',
      'data_path':r'\b\S+\.(?:fbin|u8bin|hdf5|h5)\b',
      'heldout_gt_path':r'\b\S*(?:_gt|ground.?truth)\S*\.(?:ibin|ivecs|hdf5|h5)\b',
      'build_wall':r'(?i)(?:Elapsed \(wall clock\)|build(?:[_\- ](?:wall|time))|BUILD[=: ])',
      'peak_rss':r'(?i)(?:maximum resident set size|peak.?rss|maxrss)',
      'query_recall':r'(?i)(?:recall@|recall[_\- ]at|Recall\s*[=:])',
      'query_comparisons':r'(?i)(?:comparisons|dist(?:ance)?.?eval(?:uations)?)',
      'source_commit':r'(?i)(?:commit[_\- ]?(?:id|sha|hash)?|source[_\- ]sha)',
      'graph_sha':r'(?i)(?:graph[_\- ]sha(?:256)?|SHA256.*graph)',
    }
    p['hints']={key:bool(re.search(reg,text)) for key,reg in checks.items()}
    p['dataset_in_text'] = [name for name,pattern in DATASETS if re.search(pattern,text.lower())][:8]
    p['note']='These are only keyword matches in bounded text, NOT per-run or graph provenance joins.'
    return p


def audit(root, max_entries=18000, max_graphs=90, max_logs=90):
    root=root.resolve()
    if not root.is_dir():raise ValueError('root directory does not exist')
    data={}
    for label,rel,kind,n,d in KNOWN_DATA:
        v=header_matrix(root/rel,kind)
        v['path']=rel
        v['expected_n']=n;v['expected_dimension']=d
        v['role']='DATA_ONLY_NOT_SEARCH_PROVENANCE'
        if v['status']=='FORMAT_PASS' and (v['n']!=n or v['dimension']!=d):v['status']='UNEXPECTED_SHAPE'
        data[label]=v
    graphs,logs,scan=bounded_walk(root,('results','logs','experiments'),max_entries=max_entries)
    # Prioritize alternate datasets before numerous SIFT graphs, and keep explicit cap.
    priority=lambda rel:(0 if classify_name(rel) in INDEPENDENT_FAMILIES else 1,rel)
    graphs=sorted(graphs,key=priority)
    logs=sorted(logs,key=priority)
    select_graphs=graphs[:max_graphs]
    select_logs=logs[:max_logs]
    gc=[]
    for rel in select_graphs:
        v=graph_header(root/rel)
        v['path']=rel
        v['dataset_name_hint']=classify_name(rel)
        v['dataset_name_hint_is_provenance']=False
        v['eligible_as_verified_second_experiment']=False
        gc.append(v)
    lc=[]
    for rel in select_logs:
        v=log_preview(root/rel)
        v['path']=rel
        v['dataset_name_hint']=classify_name(rel)
        v['eligible_as_verified_second_experiment']=False
        lc.append(v)
    graph_hints=defaultdict(int)
    for g in gc:
        if g['dataset_name_hint'] in INDEPENDENT_FAMILIES and g['status']=='HEADER_AND_LENGTH_PASS':
            graph_hints[g['dataset_name_hint']]+=1
    control = root/'experiments/H32/H32_R26a_pool_20261029_172452_132314/nodump.graph'
    pinned_control={'status':'MISSING','path':str(control.relative_to(root))}
    if stat_file(control)==95_190_528:
        digest=sha256(control)
        pinned_control.update(status='PASS' if digest==PIN_R26A else 'HASH_MISMATCH',sha256=digest)
    output={
        'audit':'R65_EXISTING_SECOND_DATASET_PROVENANCE_INVENTORY',
        'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'root':str(root), 'read_only':True,
        'data_candidates':data, 'pinned_R26A_control':pinned_control,
        'scan':scan,
        'graph_file_count_discovered':len(graphs),
        'graph_file_count_inspected':len(gc),
        'graph_file_count_omitted_by_cap':max(0,len(graphs)-len(gc)),
        'graph_candidates':gc,
        'log_file_count_discovered':len(logs),
        'log_file_count_inspected':len(lc),
        'log_file_count_omitted_by_cap':max(0,len(logs)-len(lc)),
        'log_candidates':lc,
        'dataset_name_graph_hints':dict(graph_hints),
        'scientific_gates':{
            'R65_BOUNDED_FILE_INVENTORY':'COMPLETED',
            'SECOND_INDEPENDENT_DATASET_GRAPH_SEARCH_BUILD_PARITY':'BLOCKED_NOT_PROVEN_BY_FILENAME_OR_HEADER',
            'PIPNN_HUBNESS_LID_QUALITY_FAILURE':'UNMEASURED',
            'H33':'NOT_OPEN'
        },
        'limits':[
            'Searched only results/, logs/, experiments/ with bounded depth/entry caps.',
            'Name hints and graph n,degree,bytes DO NOT prove which base dataset produced a graph.',
            'Does not search all files or reconstruct BUILD source/seed/config, GT, graph hash and search logs in one run.',
            'Graph degree/payload ID integrity beyond header/length and SHA are not checked here.',
            'Does not read all alternate datasets or calculate LID/hubness, Recall, latency or graph reachability.',
            'No second-dataset native ANN record is promoted to PASS without a manually verified same-build and same-graph provenance chain.'
        ]
    }
    return output


def selftest():
    with tempfile.TemporaryDirectory() as t:
        root=Path(t)
        (root/'data').mkdir(); (root/'results/bigann1m').mkdir(parents=True)
        f=root/'data/bigann1m_u8.u8bin'
        f.write_bytes(struct.pack('<ii',3,2)+bytes([1,2,3,4,5,6]))
        assert header_matrix(f,'u8bin')['status']=='FORMAT_PASS'
        with (root/'results/bigann1m/pipnn_bigann1m.graph').open('wb') as g:
            g.write(struct.pack('<II',3,2));g.write(struct.pack('<III',1,1,0));g.write(struct.pack('<II',1,0))
        g=graph_header(root/'results/bigann1m/pipnn_bigann1m.graph')
        assert g['status']=='HEADER_AND_LENGTH_PASS' and g['directed_edges']==2
        (root/'results/bigann1m/run.log').write_text('PiPNN BUILD 9.7s; peak RSS 512MiB; Recall@10=0.8; dummy_bigann1m.graph')
        report=audit(root)
        assert report['graph_file_count_discovered']==1
        assert report['scientific_gates']['SECOND_INDEPENDENT_DATASET_GRAPH_SEARCH_BUILD_PARITY'].startswith('BLOCKED')
        assert report['dataset_name_graph_hints']=={'bigann1m':1}
        # A file named like a graph can still have malformed content; do not promote it.
        (root/'results/bigann1m/bad.graph').write_bytes(b'bad')
        assert graph_header(root/'results/bigann1m/bad.graph')['status']=='SKIP_MISSING_OR_SHORT'
        assert classify_name('sift10m.fbin')=='sift10m'
        # Exclude symlink traversal, if the environment supports symlinks.
        try:
            (root/'results/bigann1m/linked.graph').symlink_to(root/'results/bigann1m/pipnn_bigann1m.graph')
            a,b,_=bounded_walk(root,('results',))
            assert not any('linked.graph' in x for x in a)
        except (OSError, NotImplementedError):pass
        out=root/'new.json'
        with out.open('x',encoding='utf-8') as f:json.dump(report,f)
        try:
            out.open('x')
            raise AssertionError('must refuse overwrite')
        except FileExistsError:pass
    print('R65_SYNTHETIC_SELFTEST_PASS')


def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest='mode',required=True)
    sub.add_parser('selftest')
    a=sub.add_parser('audit')
    a.add_argument('--root',default='.')
    a.add_argument('--output',default='experiments/H65/r65_existing_second_dataset.json')
    a.add_argument('--max-entries',type=int,default=18000)
    args=p.parse_args()
    if args.mode=='selftest': selftest();return
    if not 100<=args.max_entries<=50000:raise SystemExit('--max-entries must be within [100,50000]')
    root=Path(args.root).resolve();out=Path(args.output)
    if not out.is_absolute():out=root/out
    if not out.parent.is_dir():raise SystemExit('Output parent directory does not exist; mkdir -p experiments/H65')
    if out.exists():raise SystemExit('Refusing to overwrite existing R65 report; inspect it instead.')
    report=audit(root,max_entries=args.max_entries)
    with out.open('x',encoding='utf-8') as f:
        json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
    print('R65_READONLY_PROVENANCE_INVENTORY_COMPLETED')
    print('R65_SCAN',report['scan']['scanned_entries'],'TRUNCATED',int(report['scan']['truncated']))
    print('R65_GRAPH_CANDIDATES',report['graph_file_count_discovered'],'INSPECTED',report['graph_file_count_inspected'])
    print('R65_LOG_CANDIDATES',report['log_file_count_discovered'],'INSPECTED',report['log_file_count_inspected'])
    print('R65_SIFT1M_PINNED_CONTROL',report['pinned_R26A_control']['status'])
    for name,info in report['data_candidates'].items():
        print('R65_ALTERNATE_DATA',name,info['status'])
    graph_alternates=[g for g in report['graph_candidates'] if g['dataset_name_hint'] in INDEPENDENT_FAMILIES]
    for g in graph_alternates[:12]:
        print('R65_ALTERNATE_GRAPH_HINT',g['dataset_name_hint'],g['status'],g['path'])
    for l in [x for x in report['log_candidates'] if x['dataset_name_hint'] in INDEPENDENT_FAMILIES][:10]:
        print('R65_ALTERNATE_LOG_HINT',l['dataset_name_hint'],l['path'])
    for name,count in report['dataset_name_graph_hints'].items():
        print('R65_ALTERNATE_GRAPH_NAME_HINT',name,count,'UNVERIFIED')
    print('R65_GATE SECOND_INDEPENDENT_DATASET_GRAPH_SEARCH_BUILD_PARITY',report['scientific_gates']['SECOND_INDEPENDENT_DATASET_GRAPH_SEARCH_BUILD_PARITY'])
    print('R65_GATE HUBNESS_LID_QUALITY_FAILURE',report['scientific_gates']['PIPNN_HUBNESS_LID_QUALITY_FAILURE'])
    print('R65_GATE H33',report['scientific_gates']['H33'])
    print('R65_REPORT',out)

if __name__=='__main__':main()
