#!/usr/bin/env python3
"""H32-R11 | READ-ONLY GT Top-10 structural triage + optional per-query-ID comparison.

No build, no ANN search, no mutations to graphs, datasets, binary or prior logs.
Never infer per-query search misses from aggregate recall numbers.
Python 3.9+ little-endian. Stdlib only.
"""
from __future__ import annotations

from array import array
from collections import Counter, deque
from datetime import datetime
import argparse
import csv
import hashlib
import json
import math
import mmap
from pathlib import Path
import struct
import sys
import tempfile

N=1_000_000
NQ=10_000
GT_WIDTH=100
TOPK=10
GRAPH_SPECS={
    'VAMANA':dict(path='results/vamana_sift1m.graph',sha='84b2935cb9f25e9ad53044099901c8c1e6cb4de059975882e8d91bca66aa5259',bytes=114_573_392,edges=27_643_346,reachable=999_795,recall_q100=0.983140),
    'STOCK':dict(path='experiments/H26/H26_profile_20261026_222107_gcgcqF/r1_stock.graph',sha='ce1cd7c5ae97b79972df2b30235a0844b88a6c8a983ce731ca3afca494d7095d',bytes=95_174_232,edges=22_793_556,reachable=999_999,recall_q100=0.990870),
    'TOP2':dict(path='experiments/H26/H26_profile_20261026_222107_gcgcqF/r1_top2.graph',sha='73646a2b5655e16939ca804c598818460152803c20f6932e6e9286acd334c5c6',bytes=95_176_264,edges=22_794_064,reachable=999_999,recall_q100=0.990870),
}
BIN_SHA='ee6b9c0bec2f32fe00607f3facc73691d2dca2d5158e84e69c226b3cd219c9a8'
H31_INVENTORY='experiments/H31/H31_R0_20261028_003956/h31_r0_inventory.json'
H31_INITIAL='experiments/H31/H31_R2_20261029_101943_596045'
R10_DIR='experiments/H32/H32_R10_20261029_145742_261037'

class AuditError(Exception): pass

def require(test, reason):
    if not test: raise AuditError(reason)

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''): h.update(b)
    return h.hexdigest()

def graph_depth_indegree(path, spec, expected_n, entry=0):
    require(path.is_file(),f'MISSING_GRAPH {path}')
    bs=path.stat().st_size
    require(bs==spec['bytes'],f'GRAPH_LENGTH_MISMATCH {path}: {bs}')
    sha=digest(path)
    require(sha==spec['sha'],f'GRAPH_SHA_MISMATCH {path}: {sha}')
    with path.open('rb') as fd:
        n,max_deg=struct.unpack('<II',fd.read(8))
        require(n==expected_n and 0<max_deg<=n,f'BAD_GRAPH_HEADER {path} n={n} maxdeg={max_deg}')
        require(0<=entry<n,'INVALID_ENTRY_ID')
        raw=fd.read(4*n)
        require(len(raw)==4*n,'TRUNCATED_DEGREE_ARRAY')
        deg=array('I'); deg.frombytes(raw)
        if sys.byteorder!='little': deg.byteswap()
        require(max(deg)<=max_deg,'DEGREE_ABOVE_MAX')
        count=sum(deg)
        require(count==spec['edges'],'EDGE_SUM_MISMATCH')
        require(bs==8+4*n+4*count,'GRAPH_CSR_LAYOUT_MISMATCH')
        offsets=array('Q',[0]); pos=0
        for val in deg:
            pos+=val; offsets.append(pos)
        depths=array('i',[-1])*n
        indeg=array('I',[0])*n
        depths[entry]=0
        frontier=deque([entry]); discovered=1
        with mmap.mmap(fd.fileno(),0,access=mmap.ACCESS_READ) as mapped:
            edges=memoryview(mapped)[8+4*n:].cast('I')
            try:
                require(len(edges)==count,'EDGE_VIEW_MISMATCH')
                for v in edges:
                    require(v<n,'INVALID_NEIGHBOR_ID')
                    indeg[v]+=1
                while frontier:
                    u=frontier.popleft(); step=depths[u]+1
                    for p in range(offsets[u],offsets[u+1]):
                        v=edges[p]
                        if depths[v]==-1:
                            depths[v]=step; discovered+=1; frontier.append(v)
            finally:
                edges.release()
    require(discovered==spec['reachable'],f'REACHABLE_COUNT_MISMATCH {discovered} expected {spec["reachable"]}')
    return depths,indeg,deg,dict(sha256=sha,nodes=n,edges=count,bytes=bs,entry=entry,reachable=discovered,unreachable=n-discovered)

def parse_gt(path, n, nq, gw, k):
    require(path.is_file(),f'MISSING_GT {path}')
    require(path.stat().st_size==8+8*nq*gw,'GT_LENGTH_MISMATCH')
    with path.open('rb') as f:
        require(struct.unpack('<II',f.read(8))==(nq,gw),'GT_HEADER_MISMATCH')
        with mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as mm:
            ids=memoryview(mm)[8:8+4*nq*gw].cast('I')
            dist=memoryview(mm)[8+4*nq*gw:].cast('f')
            try:
                require(len(ids)==nq*gw and len(dist)==nq*gw,'GT_LAYOUT_MISMATCH')
                require(all(0<=v<n for v in ids),'GT_VERTEX_ID_OUT_OF_RANGE')
                require(all(math.isfinite(v) and v>=0 for v in dist),'GT_DISTANCE_NONFINITE_OR_NEGATIVE')
                out=[]
                for qi in range(nq):
                    row=tuple(int(x) for x in ids[qi*gw:qi*gw+k]); require(len(set(row))==k,f'DUPLICATE_GT_TOPK query={qi}')
                    out.append(row)
                return out
            finally:
                ids.release();dist.release()

def compare_predictions(predictions:Path, top10, depthmaps, strict=True):
    """Explicit additional per-query native results: JSONL, one row/query/role.
    Required: role,query_index,ids,graph_sha256,binary_sha256,Q,k,entry_id,source.
    This file is not generated by the standard H31 aggregate-only logs.
    """
    require(predictions.is_file(),f'MISSING_PREDICTIONS {predictions}')
    rows=[]; seen=set(); count=Counter(); sample=Counter(); summaries={}
    with predictions.open(encoding='utf-8') as f:
        for lineno,line in enumerate(f,1):
            if not line.strip(): continue
            try: obj=json.loads(line)
            except Exception as e: raise AuditError(f'PREDICTION_JSON_ERROR line={lineno}: {e}')
            role=obj.get('role'); qi=obj.get('query_index'); ids=obj.get('ids')
            require(role in GRAPH_SPECS,f'PREDICTION_BAD_ROLE line={lineno}')
            require(type(qi) is int and 0<=qi<len(top10),f'PREDICTION_BAD_QUERY_ID line={lineno}')
            require(obj.get('graph_sha256')==GRAPH_SPECS[role]['sha'],f'PREDICTION_GRAPH_SHA_MISMATCH line={lineno}')
            require(obj.get('binary_sha256')==BIN_SHA,f'PREDICTION_BINARY_SHA_MISMATCH line={lineno}')
            require(obj.get('Q')==100 and obj.get('k')==TOPK and obj.get('entry_id')==0,f'PREDICTION_SEARCH_CONFIG_MISMATCH line={lineno}')
            require(isinstance(obj.get('source'),str) and obj['source'].strip(),f'PREDICTION_NO_PROVENANCE line={lineno}')
            require(isinstance(ids,list) and len(ids)==TOPK and all(type(v) is int and 0<=v<N for v in ids) and len(set(ids))==TOPK, f'PREDICTION_BAD_IDS line={lineno}')
            require((role,qi) not in seen,f'DUPLICATE_PREDICTION_QUERY line={lineno}')
            seen.add((role,qi));count[role]+=1
            gt=set(top10[qi]); got=set(ids); missing=gt-got
            unreach={v for v in missing if depthmaps[role][v]==-1}
            reach=missing-unreach
            found=gt&got
            sample[(role,'all_gt_missed')]+=len(missing)
            sample[(role,'structural_gt_missed')]+=len(unreach)
            sample[(role,'reachable_gt_missed')]+=len(reach)
            sample[(role,'query_affected')]+=bool(missing)
            rows.append(dict(role=role,query_index=qi,found_gt=len(found),unreachable_gt_missed=len(unreach),reachable_gt_missed=len(reach),unreachable_ids=';'.join(map(str,sorted(unreach))),reachable_missed_ids=';'.join(map(str,sorted(reach)))))
    require(len(rows)>0,'EMPTY_PREDICTIONS')
    for role in GRAPH_SPECS:
        if count[role]:
            if strict: require(count[role]==len(top10),f'PARTIAL_PREDICTIONS role={role} count={count[role]} need={len(top10)}')
            summaries[role]=dict(queries_with_predictions=count[role], GT_found=sum(int(r['found_gt']) for r in rows if r['role']==role), missed_gt=sample[(role,'all_gt_missed')],missed_unreachable_gt=sample[(role,'structural_gt_missed')],missed_reachable_gt=sample[(role,'reachable_gt_missed')],query_affected=sample[(role,'query_affected')])
    return rows,summaries

def audit(root, predictions, allow_partial):
    root=root.expanduser().resolve()
    require(sys.byteorder=='little','LITTLE_ENDIAN_REQUIRED')
    require(root.is_dir(),f'ROOT_MISSING {root}')
    inv=root/H31_INVENTORY; require(inv.is_file(),f'H31_INVENTORY_NOT_FOUND {inv}')
    try: json.loads(inv.read_text(encoding='utf-8'))
    except Exception as e: raise AuditError(f'H31_INVENTORY_JSON_INVALID {e}')
    rd=root/R10_DIR/'h32_r10_report.json'
    require(rd.is_file(),f'R10_REPORT_REQUIRED {rd}')
    try: r10=json.loads(rd.read_text(encoding='utf-8'))
    except Exception as e: raise AuditError(f'R10_REPORT_INVALID {e}')
    require(r10.get('status')=='PASS_REAL_READONLY_GT_REACHABILITY','R10_REPORT_NOT_PASS')
    gt_path=root/'data/sift1m_gt.ibin'
    base=root/'data/sift1m.fbin'
    queries=root/'data/sift1m_queries.fbin'
    for path,expected_n in [(base,N),(queries,NQ)]:
        require(path.is_file(),f'MISSING_DATA_FILE {path}')
        require(path.stat().st_size==8+4*expected_n*128,f'BAD_FBIN_LENGTH {path}')
        with path.open('rb') as f: require(struct.unpack('<II',f.read(8))==(expected_n,128),f'BAD_FBIN_HEADER {path}')
    top10=parse_gt(gt_path,N,NQ,GT_WIDTH,TOPK)
    rows=[]; summaries={}; depthmaps={}; samples=[]; metas={}
    for role,spec in GRAPH_SPECS.items():
        depth,indeg,deg,meta=graph_depth_indegree(root/spec['path'],spec,N,0)
        meta_r10=r10.get('graphs',{}).get(role,{})
        require(meta_r10.get('graph',{}).get('sha256')==meta['sha256'],f'R10_GRAPH_PROVENANCE_MISMATCH {role}')
        require(meta_r10.get('graph',{}).get('unreachable')==meta['unreachable'],f'R10_GRAPH_UNREACH_MISMATCH {role}')
        total_unreach=0; touched=0; distinct=set(); hop_hist=Counter(); indeg_hist=Counter()
        zero_indeg_gt_positions=0; zero_indeg_unreach_vertices=0
        role_rows=[]
        for qi,gt_ids in enumerate(top10):
            absent=[v for v in gt_ids if depth[v]==-1]
            total_unreach+=len(absent); touched+=bool(absent);distinct.update(absent)
            hops=[depth[v] for v in gt_ids if depth[v]>=0]
            hop_hist.update(hops)
            indeg_hist.update((indeg[v] for v in gt_ids))
            zero_indeg_gt_positions+=sum(indeg[v]==0 for v in gt_ids)
            if absent:
                samples.append(dict(role=role,query_index=qi,gt_unreachable_ids=absent,gt_unreachable_indeg=[indeg[v] for v in absent],other_gt_hops=[depth[v] for v in gt_ids if depth[v]>=0]))
            role_rows.append(dict(role=role,query_index=qi,unreachable_gt_positions=len(absent),unreachable_gt_ids=';'.join(map(str,absent)),reachable_gt_positions=TOPK-len(absent),reachable_gt_min_hops=min(hops) if hops else '',reachable_gt_max_hops=max(hops) if hops else '',reachable_gt_mean_hops=round(sum(hops)/len(hops),3) if hops else ''))
        rows.extend(role_rows)
        require(total_unreach==meta_r10.get('GT',{}).get('unreachable_gt_positions_M'),f'R10_GT_M_MISMATCH {role}')
        hist_list=sorted(hop_hist.items())
        sumhop=sum(h*c for h,c in hop_hist.items()); denom=sum(hop_hist.values())
        missed=round((1-spec['recall_q100'])*NQ*TOPK)
        summaries[role]=dict(graph=meta,gt_unreachable_positions_M=total_unreach,queries_affected=touched,distinct_unreachable_GT=len(distinct),GT_reachable_positions=NQ*TOPK-total_unreach,hop_histogram_gt_positions=dict(hist_list),mean_hops_among_reachable_GT=(sumhop/denom if denom else None),max_hops_among_reachable_GT=max(hop_hist) if hop_hist else None,zero_indeg_gt_positions=zero_indeg_gt_positions,h31_q100_recall_historical=spec['recall_q100'],h31_q100_missed_slots_from_reported_recall=missed,reachable_missed_slots_lower_bound_conditional=max(0,missed-total_unreach),limitations=['R10 M from entry-0 BFS; H31 actual start point not proven by this script','No historical per-query search result IDs provided; aggregate misses do not identify queries','GT exactness not recomputed; graph degree/index size not matched','Hop distances are graph-topology descriptors, not actual visited/search paths'])
        depthmaps[role]=depth
        metas[role]=meta
        print(f'GRAPH_{role}=PASS_PINNED_SHA_R10_GT; M={total_unreach}; AFFECTED_QUERIES={touched}; GT_HOPS_MAX={summaries[role]["max_hops_among_reachable_GT"]}',flush=True)
    pred_rows=None;pred_summaries=None
    if predictions:
        pred_rows,pred_summaries=compare_predictions(predictions.expanduser(),top10,depthmaps,not allow_partial)
        status='PASS_GT_TOPOLOGY_PLUS_USER_PROVIDED_QUERY_IDS'
    else:
        status='PASS_STRUCTURAL_TRIAGE_SEARCH_MISSES_NOT_CLASSIFIABLE'
    outdir=root/'experiments/H32';require(outdir.is_dir(),f'OUTPUT_PARENT_MISSING {outdir}')
    folder=outdir/f'H32_R11_{datetime.now().strftime("%Y%m%d_%H%M%S_%f")}'
    folder.mkdir(mode=0o755)
    with (folder/'h32_r11_gt_query_matrix.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    with (folder/'h32_r11_affected_queries.csv').open('w',newline='',encoding='utf-8') as f:
        fieldnames=['role','query_index','gt_unreachable_ids','gt_unreachable_indeg','other_gt_hops']
        writer=csv.DictWriter(f,fieldnames=fieldnames);writer.writeheader()
        for a in samples:
            writer.writerow({k:json.dumps(a[k],ensure_ascii=False) if isinstance(a[k],list) else a[k] for k in fieldnames})
    if pred_rows is not None:
        with (folder/'h32_r11_verified_per_query_misses.csv').open('w',newline='',encoding='utf-8') as f:
            writer=csv.DictWriter(f,fieldnames=list(pred_rows[0]));writer.writeheader();writer.writerows(pred_rows)
    report=dict(status=status,read_only=True,graph_source='H31 pinned SHA and H32-R10 actual local report',r10_report=str(rd),gt_file=str(gt_path),query_count=NQ,topk=TOPK,graph_index_search_entry_policy='NOT_INDEPENDENTLY_VERIFIED_FROM_NATIVE_SEARCHER',exact_gt_recomputed=False,h31_query_results_verified=bool(predictions),predictions_file=str(predictions) if predictions else None,predictions_role_summaries=pred_summaries,graphs=summaries)
    (folder/'h32_r11_report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    lines=['H32-R11 | STRUCTURAL GT TRIAGE AND OPTIONAL HISTORICAL QUERY-ID COMPARISON',f'OVERALL={status}',f'ROOT={root}',f'R10_PROVENANCE={rd}', 'ENTRY_POLICY=NOT_INDEPENDENTLY_VERIFIED_FROM_NATIVE_SEARCHER','GT_EXACTNESS=NOT_RECOMPUTED','NO BUILD / NO ANN SEARCH / NO GRAPH MODIFICATION','']
    for role,s in summaries.items():
        lines += [f'[{role}] UNREACHABLE_GT_M={s["gt_unreachable_positions_M"]} QUERIES_AFFECTED={s["queries_affected"]}',f'  REACHABLE_GT_POSITIONS={s["GT_reachable_positions"]}',f'  MEAN_ENTRY0_BFS_HOPS_REACHABLE_GT={s["mean_hops_among_reachable_GT"]:.4f}',f'  MAX_ENTRY0_BFS_HOPS_REACHABLE_GT={s["max_hops_among_reachable_GT"]}',f'  ZERO_INDEG_GT_POSITIONS={s["zero_indeg_gt_positions"]}',f'  H31_Q100_MISSED_SLOTS_AGGREGATE={s["h31_q100_missed_slots_from_reported_recall"]}',f'  NONSTRUCTURAL_MISSED_SLOTS_IF_H31_ENTRY0_ONLY={s["reachable_missed_slots_lower_bound_conditional"]}', '']
    lines += [f'PREDICTION_IDS={"VERIFIED_USER_PROVIDED" if predictions else "NOT_AVAILABLE_IN_CURRENT_INPUT"}', 'RESEARCH_DECISION=Do not attribute misses to beam-pruning, wrong turn or topology without actual per-query native results and expansion traces.','R11_OUTPUTS=gt_query_matrix.csv + affected_queries.csv + report.json',f'H32R11_DONE={folder}']
    (folder/'h32_r11_summary.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('\n'.join(lines),flush=True)

def selftest():
    with tempfile.TemporaryDirectory(prefix='h32r11_selftest_') as tmp:
        t=Path(tmp)
        path=t/'toy.graph'
        # 0 -> 1 -> 2; 3 is disconnected but has indegree 1 from 4.
        adj=[[1],[2],[],[],[3]]
        with path.open('wb') as f:
            f.write(struct.pack('<II',5,1));f.write(struct.pack('<5I',*(len(v) for v in adj)))
            for lst in adj:
                for v in lst: f.write(struct.pack('<I',v))
        spec=dict(sha=digest(path),bytes=path.stat().st_size,edges=3,reachable=3)
        depth,indeg,_,meta=graph_depth_indegree(path,spec,5)
        require(depth.tolist()==[0,1,2,-1,-1],'SELFTEST_DEPTH_BAD')
        require(indeg.tolist()==[0,1,1,1,0],'SELFTEST_INDEG_BAD')
        require(meta['unreachable']==2,'SELFTEST_UNREACH_BAD')
        gt=t/'toy.ibin'
        with gt.open('wb') as f:
            f.write(struct.pack('<II',2,3));f.write(struct.pack('<6I',3,2,0,1,4,0));f.write(struct.pack('<6f',.1,.2,.3,.1,.2,.3))
        x=parse_gt(gt,5,2,3,3)
        require(x==[(3,2,0),(1,4,0)],'SELFTEST_GT_BAD')
        # Optional native per-query import: test separate reachable-vs-unreachable missed GT.
        predictions=t/'toy_predictions.jsonl'
        synthetic_ids=[dict(role='VAMANA',query_index=0,ids=list(range(9))+[10],graph_sha256=GRAPH_SPECS['VAMANA']['sha'],binary_sha256=BIN_SHA,Q=100,k=10,entry_id=0,source='synthetic_test'),dict(role='VAMANA',query_index=1,ids=list(range(8))+[9,10],graph_sha256=GRAPH_SPECS['VAMANA']['sha'],binary_sha256=BIN_SHA,Q=100,k=10,entry_id=0,source='synthetic_test')]
        predictions.write_text(''.join(json.dumps(v)+'\n' for v in synthetic_ids),encoding='utf-8')
        depth_test=array('i',[0]*11);depth_test[9]=-1
        rs,summary=compare_predictions(predictions,[tuple(range(10)),tuple(range(10))],{'VAMANA':depth_test},strict=True)
        require(summary['VAMANA']['missed_unreachable_gt']==1 and summary['VAMANA']['missed_reachable_gt']==1,'SELFTEST_PREDICTION_CLASSIFICATION_BAD')
        synthetic_ids[1]['binary_sha256']='NOT_REAL'
        predictions.write_text(''.join(json.dumps(v)+'\n' for v in synthetic_ids),encoding='utf-8')
        try: compare_predictions(predictions,[tuple(range(10)),tuple(range(10))],{'VAMANA':depth_test},strict=True)
        except AuditError: pass
        else: raise AuditError('SELFTEST_PREDICTION_WRONG_BIN_SHA_NOT_REJECTED')
        broken=t/'corrupt.graph';broken.write_bytes(path.read_bytes()[:-4])
        try: graph_depth_indegree(broken,spec,5)
        except AuditError: pass
        else: raise AuditError('SELFTEST_FAIL_CLOSED_SHA_DID_NOT_FAIL')
    print('H32R11_SYNTHETIC_SELFTEST_PASS (NO SIFT1M REAL DATA CHECKED)')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',required=True,choices=['selftest','audit'])
    p.add_argument('--root',default='~/ann-task-a')
    p.add_argument('--predictions',type=Path,help='OPTIONAL: JSONL query-level native IDs with explicit graph/binary SHA and Q100/entry0 metadata')
    p.add_argument('--allow-partial',action='store_true',help='Explicitly permit fewer than 10k per-query predictions per provided role')
    a=p.parse_args()
    try: selftest() if a.mode=='selftest' else audit(Path(a.root),a.predictions,a.allow_partial)
    except (AuditError,OSError,ValueError,struct.error,KeyError) as e:
        print(f'H32R11_FAIL_CLOSED: {e}',file=sys.stderr)
        sys.exit(2)
if __name__=='__main__': main()
