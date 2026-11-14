#!/usr/bin/env python3
"""H31-R0: READ-ONLY audit of existing SIFT1M Vamana / PiPNN graph assets.
No BUILD, no SEARCH, no edge modification, no claim of matched Recall/QPS or novelty.
Graph schema: ParlayANN/PiPNN Graph<uint32_t>: n, maxDegree, n degrees, packed neighbors.
Reads with Python stdlib, no numpy, no perf, no sudo.
"""
from __future__ import annotations
import argparse
from array import array
from collections import Counter
import datetime as dt
import hashlib
import json
import mmap
import contextlib
import io
from pathlib import Path
import struct
import sys
import tempfile

N_EXPECTED=1_000_000
ROLE_NAMES=('VAMANA','STOCK','TOP2')
SCHEMA='little-endian u32: [n,max_degree,degree[n],neighbor_ids[sum(degree)]]'


def sha256(path:Path):
    h=hashlib.sha256()
    with path.open('rb') as fd:
        while True:
            s=fd.read(4*1024*1024)
            if not s:break
            h.update(s)
    return h.hexdigest()


def graph_check(path:Path, n_expected:int=N_EXPECTED, full_neighbors:bool=True):
    path=path.expanduser().resolve(strict=True)
    if not path.is_file() or path.stat().st_size<12 or path.stat().st_size%4:
        raise ValueError(f'Invalid graph size/alignment: {path}')
    with path.open('rb') as f, mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as mm:
        n, maxdeg=struct.unpack_from('<II',mm,0)
        if not (2<=n<=20_000_000):raise ValueError(f'Invalid n={n} for {path}')
        if n!=n_expected:raise ValueError(f'Expected n={n_expected}, found {n} in {path}')
        if not (1<=maxdeg<=4096):raise ValueError(f'Invalid max_degree={maxdeg} in {path}')
        if len(mm)<8+4*n:raise ValueError(f'Truncated degrees in {path}')
        degrees=array('I')
        degrees.frombytes(mm[8:8+4*n])
        # Python array/memoryview native little endian required; environment is checked in main.
        total=0; zero=0; count_hist=Counter()
        for deg in degrees:
            if deg>maxdeg:raise ValueError(f'Degree {deg}>{maxdeg} in {path}')
            total+=deg;zero+=(deg==0);count_hist[deg]+=1
        expected_bytes=8+4*n+4*total
        if len(mm)!=expected_bytes:raise ValueError(f'Size/degree mismatch expected {expected_bytes}, got {len(mm)}: {path}')
        # mmap slice read-only: no writes to source. For verified neighbor ID bounds/indegree.
        indeg=None;zeros_in=None;mx_id=None;self_edges=None
        if full_neighbors:
            indeg=array('I',[0])*n
            mx_id=0
            first=8+4*n
            for off in range(first,len(mm),4*1_000_000):
                ch=array('I')
                ch.frombytes(mm[off:min(off+4*1_000_000,len(mm))])
                for v in ch:
                    if v>=n:raise ValueError(f'Out-of-range destination {v} in {path}')
                    indeg[v]+=1
                    if v>mx_id:mx_id=v
            zeros_in=sum(x==0 for x in indeg)
        del degrees
    return {
        'path':str(path),'bytes':path.stat().st_size,'sha256':sha256(path),
        'schema':SCHEMA,'n':n,'max_degree':maxdeg,'directed_edge_occurrences':total,
        'mean_outdegree':round(total/n,6),'zero_outdegree_vertices':zero,
        'zero_indegree_vertices':zeros_in,'neighbor_id_bounds_validated':full_neighbors,
        'max_neighbor_id':mx_id,'degree_histogram':{str(k):v for k,v in sorted(count_hist.items())},
        'graph_only_bytes_per_vector':round(path.stat().st_size/n,4),
        'notes':['No duplicate-edge scan or BFS in H31-R0; use H27 for exact edge-set/BFS on known H26 graphs.',
                 'Graph-only bytes exclude base-vector storage/searcher metadata.']
    }


def dataset_check(path:Path, expected_n:int, expected_d:int, suffix:str):
    if not path.is_file():return {'path':str(path),'status':'MISSING'}
    fsize=path.stat().st_size
    if fsize<8:return {'path':str(path),'status':'INVALID_TOO_SHORT'}
    with path.open('rb') as f:hdr=f.read(8)
    n,d=struct.unpack('<II',hdr)
    element_size={'fbin':4,'ibin':4}[suffix]
    want=8+n*d*element_size
    good=(n==expected_n and d==expected_d and fsize==want)
    return {'path':str(path),'status':'STRUCTURE_PASS' if good else 'STRUCTURE_FAIL',
            'n':n,'d_or_k':d,'bytes':fsize,'expected_bytes':want,
            'sha256':'NOT_COMPUTED_BY_DEFAULT: >500MB possible',
            'caution':'Header/size validation is not value-level ground truth verification.'}


def candidate_paths(root:Path):
    search_roots=[root/'results',root/'experiments'/'H17',root/'experiments'/'H26']
    out=[]
    # Target known graph families; never recurse entire repo or dataset directory.
    for base in search_roots:
        if not base.is_dir():continue
        out.extend(p for p in base.rglob('*.graph') if p.is_file())
    return sorted(set(x.resolve() for x in out))


def discover(root:Path):
    roots=candidate_paths(root)
    named={role:[] for role in ROLE_NAMES}
    for p in roots:
        name=p.name.lower();par=p.parent.name.lower()
        if 'vamana' in name and 'sift1m' in name and ('4t' in name or '4thread' in name):named['VAMANA'].append(p)
        if name=='r1_stock.graph' and par.startswith('h26_profile_'):named['STOCK'].append(p)
        if name=='r1_top2.graph' and par.startswith('h26_profile_'):named['TOP2'].append(p)
    return named,roots


def select_graphs(root:Path,explicit:list[str],auto:bool):
    if explicit:
        out={}
        for item in explicit:
            if '=' not in item:raise ValueError('Expected --graph ROLE=/absolute/path.graph')
            role,s=item.split('=',1);role=role.upper()
            if role not in ROLE_NAMES or role in out:raise ValueError('Only once each: VAMANA STOCK TOP2')
            p=Path(s).expanduser().resolve(strict=True)
            if not p.is_file():raise ValueError('Graph is not a file: '+s)
            out[role]=p
        if set(out)!=set(ROLE_NAMES):raise ValueError('Specify VAMANA, STOCK, TOP2 together')
        return out,'USER_ASSIGNED_LABELS_NOT_VERIFIED_BUILD_PROVENANCE'
    if not auto:raise ValueError('Need all three --graph args, or --mode auto')
    named,_=discover(root)
    if any(len(named[k])!=1 for k in ROLE_NAMES):
        print('H31R0_NEEDS_EXPLICIT_SELECTION: 4-thread Vamana and H26 r1 Stock/Top2 not uniquely discovered')
        for k in ROLE_NAMES:
            print(f'  {k}: {len(named[k])} strict candidate(s)')
            for p in named[k]:print('    '+str(p))
        raise ValueError('Ambiguous or missing strict paths. Run --mode discover, then --mode run with 3 --graph flags')
    paths={k:named[k][0] for k in ROLE_NAMES}
    if paths['STOCK'].parent!=paths['TOP2'].parent:
        raise ValueError('Stock and Top2 candidates do not share H26 profile parent')
    return paths,'STRICT_FILENAME_HEURISTIC_ONLY_BUILD_PROVENANCE_NOT_VERIFIED'


def inventory_report(root:Path):
    named,allp=discover(root)
    print('H31-R0 GRAPH DISCOVERY — files only, no benchmark')
    for k,files in named.items():
        print(f'{k}: {len(files)} strict candidate(s)')
        for p in files:print(f'  {p} ({p.stat().st_size:,} B)')
    print(f'ALL_GRAPH_FILES_SCANNED={len(allp)}')
    for p in allp:
        print('FILE '+str(p)+'\t'+str(p.stat().st_size)+' B')
    print('H31R0_DISCOVER_DONE')


def evidence_files(root:Path):
    specs={
        'LEGACY_PARLAY_SEARCH_LOGS': list((root/'logs').glob('vamana*Q*.log'))+list((root/'logs').glob('pipnn_commonsearch_Q*.log')),
        'H27_EXACT_TOPOLOGY_SUMMARIES': list((root/'experiments'/'H27').glob('H27_R0_topology_*/h27_r0_summary.json')),
        'H26_P0_PROFILE_OUTPUT': list((root/'experiments'/'H26').glob('H26_profile_*/h26_*summary*.txt')),
    }
    ans={}
    for label,paths in specs.items():
        paths=[p for p in sorted(set(paths)) if p.is_file()]
        ans[label]=[{'path':str(p),'bytes':p.stat().st_size,'sha256':sha256(p)} for p in paths[:100]]
    return ans


def fmt_graph(k,v):
    return f"{k:<8s} {v['n']:>10,d} {v['directed_edge_occurrences']:>13,d} {v['mean_outdegree']:>8.4f} {v['zero_indegree_vertices']:>10,d} {v['bytes']:>13,d}"


def run(root:Path, graphs:list[str],auto:bool, expected_n:int, outdir:str|None):
    paths,provenance=select_graphs(root,graphs,auto)
    if len(set(paths.values()))!=3:raise ValueError('Duplicate input graph paths')
    stats={role:graph_check(paths[role],expected_n,full_neighbors=True) for role in ROLE_NAMES}
    dataset={
        'base':dataset_check(root/'data'/'sift1m.fbin',expected_n,128,'fbin'),
        'queries':dataset_check(root/'data'/'sift1m_queries.fbin',10_000,128,'fbin'),
        'gt':dataset_check(root/'data'/'sift1m_gt.ibin',10_000,100,'ibin'),
    }
    status='INPUT_DATA_PASS' if all(x['status']=='STRUCTURE_PASS' for x in dataset.values()) else 'INPUT_DATA_PARTIAL_OR_FAIL'
    meta={'study':'H31_R0_EXISTING_GRAPH_AUDIT','mode':'READ_ONLY_NO_BUILD_NO_SEARCH',
          'time_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'host_home_root':str(root),
          'graph_selection_basis':provenance,'graph_roles':stats,'dataset':dataset,
          'input_dataset_status':status,'evidence_files':evidence_files(root),
          'baseline_provenance_historical_only':{
              'Vamana_4t_single_build_s':208.10,'PiPNN_stock_G0_4t_median3_build_s':50.58,
              'PiPNN_H17_top2_4t_median3_build_s':44.95,
              'PiPNN_H26_P0_stock_median2_build_s':50.025,
              'PiPNN_H26_P0_top2_median2_build_s':42.035,
              'warning':'Reference data from prior research reports; not measured or automatically matched to these selected graph files.'},
          'gates':{
              'graph_file_schema':'PASS','graph_sha256':'PASS','dataset_header_and_size':status,
              'same_BUILD_seed_and_flags':'UNVERIFIED',
              'same_searcher_same_query_set':'UNVERIFIED',
              'matched_graph_bytes_or_degree':'UNVERIFIED',
              'matched_Recall_QPS_curves':'NOT_EVALUATED_IN_R0',
              'intra_query_parallelism':'NOT_EVALUATED_IN_R0'},
          'caveats':[
              'File names and hashes do not establish same BUILD seed, source code, or parameter lineage.',
              'Original graph-only bytes are not full index footprint.',
              'Indegree zero != reachability from entry. No BFS run here; H27 audits known H26 graphs.',
              'H27 Stock/Top2 edge similarity does not identify scheduler causality.',
              'No new BUILD/Search measurements; independent historical timings are not strict matched comparison.'
          ]}
    # Do not silently report matched dataset if failed.
    folder=Path(outdir).expanduser().resolve() if outdir else root/'experiments'/'H31'/('H31_R0_'+dt.datetime.now().strftime('%Y%m%d_%H%M%S'))
    folder.mkdir(parents=True,exist_ok=False)
    (folder/'h31_r0_inventory.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=[
        'H31-R0 EXISTING GRAPH & EVIDENCE PROVENANCE AUDIT (read-only; no new BUILD/SEARCH)',
        f'GRAPH_SELECTION_BASIS={provenance}',f'DATASET_STATUS={status}',
        'ROLE             N    EDGES(dir)      AVG-D     ZERO-IN   BYTES(graph-only)',
    ]
    for k in ROLE_NAMES:lines.append(fmt_graph(k,stats[k]))
    ratio=stats['TOP2']['bytes']/stats['VAMANA']['bytes']
    lines.extend(['',f'TOP2/VAMANA graph-only bytes ratio = {ratio:.5f} (DESCRIPTIVE, NOT EQUAL BUDGET)',
                  'GRAPH_FILE_SCHEMA_AND_SHA_PASS; SCORE GATES BELOW ARE NOT PASSED:',
                  '  BUILD seed/source/flags lineage: UNVERIFIED',
                  '  Same native searcher 10k query per selected graph: UNVERIFIED',
                  '  Degree/index bytes matched: UNVERIFIED',
                  '  Matched Recall-QPS and intra-query scalability: NOT TESTED',
                  '  Original Vamana 4t 208.10s (one run), Stock 50.58s (three median), H17 Top2 44.95s (three median), H26 P0 Top2 42.035s (two median) are HISTORICAL reported results, NOT NEW/MATCHED timings.',
                  'NEXT DECISION: inventory file validates graph format/structure only. Cross-method Pareto comparison requires controlled search and bytes/degree budgets.',
                  f'H31R0_DONE={folder}'])
    (folder/'h31_r0_summary.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('\n'.join(lines))


def selftest():
    with tempfile.TemporaryDirectory() as t:
        root=Path(t)
        def save(name,rows,maxd=2):
            a=[len(rows),maxd]+[len(z) for z in rows]+[v for row in rows for v in row]
            f=root/name;f.write_bytes(struct.pack('<'+'I'*len(a),*a));return f
        g=save('valid.graph',[[1,2],[2],[0],[]]);a=graph_check(g,4)
        assert a['directed_edge_occurrences']==4 and a['zero_outdegree_vertices']==1 and a['zero_indegree_vertices']==1,a
        assert a['bytes']==(2+4+4)*4
        b=save('bad.graph',[[1,5],[2],[0],[]])
        try:graph_check(b,4)
        except ValueError:pass
        else:raise AssertionError('Accepted invalid neighbor ID')
        c=save('bad_len.graph',[[1],[2],[3],[]]);c.write_bytes(c.read_bytes()[:-4]);
        try:graph_check(c,4)
        except ValueError:pass
        else:raise AssertionError('Accepted truncated graph')
        testbase=root/'data';testbase.mkdir()
        p=testbase/'test.fbin';p.write_bytes(struct.pack('<II',2,3)+bytes(2*3*4));
        assert dataset_check(p,2,3,'fbin')['status']=='STRUCTURE_PASS'
        assert dataset_check(p,2,128,'fbin')['status']=='STRUCTURE_FAIL'
        try:
            with contextlib.redirect_stdout(io.StringIO()):select_graphs(root,[],auto=True)
        except ValueError:pass
        else:raise AssertionError('Autoselected nonexistent graphs')
    print('H31R0_SCHEMA_PROVENANCE_FAIL_CLOSED_SELFTEST_PASS')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--mode',choices=['selftest','discover','auto','run'],default='discover')
    ap.add_argument('--root',default='~/ann-task-a',help='ANN project root')
    ap.add_argument('--graph',action='append',default=[],help='ROLE=/absolute/path.graph, three roles VAMANA STOCK TOP2')
    ap.add_argument('--expected-n',type=int,default=N_EXPECTED)
    ap.add_argument('--out',default=None)
    args=ap.parse_args()
    if sys.byteorder!='little' or array('I').itemsize!=4:raise SystemExit('H31R0_BLOCKED: Requires little-endian 32-bit unsigned C int memoryview')
    try:
        if args.mode=='selftest':selftest();return
        root=Path(args.root).expanduser().resolve(strict=True)
        if args.expected_n<2:raise ValueError('Invalid expected n')
        if args.mode=='discover':inventory_report(root);return
        if args.mode=='auto':
            if args.graph:raise ValueError('--mode auto does not accept --graph')
            run(root,[],True,args.expected_n,args.out)
        else:run(root,args.graph,False,args.expected_n,args.out)
    except (ValueError,OSError,AssertionError,MemoryError) as e:
        print('H31R0_FAIL_CLOSED: '+str(e),file=sys.stderr);sys.exit(2)

if __name__=='__main__':main()
