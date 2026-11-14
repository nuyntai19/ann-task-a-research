#!/usr/bin/env python3
"""H32-R12: read-only audit of strict GT@10 vs source-style tie-aware recall.

Only reads R10/R11 provenance, pinned SIFT1M data, graphs and local ParlayANN code.
NO build, NO ANN search, NO graph mutation. The Python distance calculation is a
float32 sequential *proxy*, not proof of binary-level equivalence to native C++.
"""
from __future__ import annotations
import argparse, csv, hashlib, importlib.util, json, math, mmap, re, struct, subprocess, sys, tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT_REQUIRED=1_000_000; NQ=10_000; D=128; GTW=100; K=10
HEAD='a48c6a34e5f959190992aa531cc18454cfcc3dd3'
ROLES=('VAMANA','STOCK','TOP2')

class AuditError(Exception): pass

def require(cond, message):
    if not cond: raise AuditError(message)

def f32(v): return struct.unpack('<f',struct.pack('<f',v))[0]

def float_l2_sequential(q, b):
    # Similar arithmetic expression to Euclidian_Point<float>::distance;
    # binary-level equality still depends on compiler/ISA options.
    accum=f32(0.0)
    for x,y in zip(q,b):
        d=f32(x-y)
        accum=f32(accum+f32(d*d))
    return accum

def load_json(path):
    require(path.is_file(),f'MISSING_FILE: {path}')
    return json.loads(path.read_text(encoding='utf-8'))

def newest(root,prefix,suffix):
    paths=sorted((root/'experiments/H32').glob(prefix),key=lambda p:p.name,reverse=True)
    for p in paths:
        if (p/suffix).is_file(): return p
    raise AuditError(f'MISSING_PREVIOUS_AUDIT: {prefix}/{suffix}')

def source_check(root):
    repo=root/'src/ParlayANN'
    required_files={
      'algorithms/vamana/neighbors.h':('start_point = 0','search_and_parse'),
      'algorithms/utils/check_nn_recall.h':('results_with_ties','== last_dist','qsearchAll'),
      'algorithms/utils/beamSearch.h':('if (random)','starting_points = {starting_point}', 'parlay::parallel_for'),
      'algorithms/utils/euclidian_point.h':('float euclidian_distance(const float *p, const float *q, unsigned d)',)
    }
    checks={}
    for name,patterns in required_files.items():
        path=repo/name
        require(path.is_file(),f'SOURCE_MISSING: {path}')
        contents=path.read_text(encoding='utf-8')
        for pattern in patterns:
            require(pattern in contents,f'SOURCE_PATTERN_MISSING {name}: {pattern}')
        checks[name]='KEY_SOURCE_PATTERNS_PRESENT'
    neighbor=(repo/'algorithms/vamana/neighbors.h').read_text()
    # Verify ordering of arguments and fixed policy in a narrow pattern.
    require(re.search(r'search_and_parse\s*\(G_,\s*G,.*?res_file,\s*k,\s*false,\s*start_point',neighbor,re.S) is not None,
            'VAMANA_CALL_POLICY_NOT_CONFIRMED')
    src=(repo/'algorithms/utils/check_nn_recall.h').read_text()
    require('for (indexType l = k; l < GT.dimension(); l++)' in src and
            'qp.distance(Base_Points[GT.coordinates(i, l)]) == last_dist' in src,
            'NATIVE_TIE_POLICY_NOT_CONFIRMED')
    out={'repository':str(repo), 'files':checks,
         'vamana_search_entry_from_source':'ZERO_NONRANDOM',
         'native_recall_source':'TOP_K_PLUS_EXACT_DISTANCE_TIES_IN_GT_100',
         'native_binary_parity':'NOT_REVERIFIED_BY_THIS_SOURCE_AUDIT'}
    if (repo/'.git').exists():
        cmd=subprocess.run(['git','-C',str(repo),'rev-parse','HEAD'],capture_output=True,text=True)
        out['git_head']=cmd.stdout.strip() if cmd.returncode==0 else 'UNKNOWN'
        require(out['git_head']==HEAD, f'GIT_HEAD_NOT_PINNED: {out["git_head"]}')
        modified=subprocess.run(['git','-C',str(repo),'diff','--name-only','HEAD','--',*required_files],capture_output=True,text=True)
        require(modified.returncode==0, 'GIT_DIFF_CHECK_FAILED')
        require(not modified.stdout.strip(),f'PINNED_SOURCE_MODIFIED: {modified.stdout.strip()}')
        out['modified_relevant_files']='NONE'
    else:
        out['git_head']='UNVERIFIED_NO_GIT';out['modified_relevant_files']='UNVERIFIED'
    return out

def get_gt_rows(path, selected):
    require(path.stat().st_size==8+8*NQ*GTW,'GT_SIZE_MISMATCH')
    rows={}
    with path.open('rb') as fd:
        require(struct.unpack('<II',fd.read(8))==(NQ,GTW),'GT_HEADER_MISMATCH')
        with mmap.mmap(fd.fileno(),0,access=mmap.ACCESS_READ) as mm:
            for qi in sorted(selected):
                off=8+qi*GTW*4
                idx=struct.unpack_from('<100I',mm,off)
                offdist=8+NQ*GTW*4+qi*GTW*4
                distances=struct.unpack_from('<100f',mm,offdist)
                require(max(idx)<ROOT_REQUIRED and len(set(idx[:10]))==K,f'GT_IDS_INVALID query {qi}')
                require(all(math.isfinite(x) and x>=0 for x in distances),f'GT_DIST_INVALID query {qi}')
                rows[qi]=(idx,distances)
    return rows

def vectors_for_queries(base_path, query_path, gt_rows):
    expected_data=8+4*ROOT_REQUIRED*D; expected_queries=8+4*NQ*D
    require(base_path.stat().st_size==expected_data,'BASE_SIZE_MISMATCH')
    require(query_path.stat().st_size==expected_queries,'QUERY_SIZE_MISMATCH')
    with base_path.open('rb') as bf,query_path.open('rb') as qf:
        require(struct.unpack('<II',bf.read(8))==(ROOT_REQUIRED,D),'BASE_HEADER_MISMATCH')
        require(struct.unpack('<II',qf.read(8))==(NQ,D),'QUERY_HEADER_MISMATCH')
        with mmap.mmap(bf.fileno(),0,access=mmap.ACCESS_READ) as bmm, mmap.mmap(qf.fileno(),0,access=mmap.ACCESS_READ) as qmm:
            # avoid retaining a million points; only affected query IDs
            out={}
            for qi,(ids,_) in gt_rows.items():
                qvec=struct.unpack_from('<128f',qmm,8+qi*D*4)
                dists=[]
                for vid in ids:
                    bvec=struct.unpack_from('<128f',bmm,8+vid*D*4)
                    dists.append(float_l2_sequential(qvec,bvec))
                out[qi]=dists
            return out

def perform(root):
    require(sys.byteorder=='little','LITTLE_ENDIAN_REQUIRED')
    root=root.expanduser().resolve();require(root.is_dir(),'ROOT_MISSING')
    r10_dir=newest(root,'H32_R10_2*','h32_r10_report.json'); r11_dir=newest(root,'H32_R11_2*','h32_r11_report.json')
    r10=load_json(r10_dir/'h32_r10_report.json');r11=load_json(r11_dir/'h32_r11_report.json')
    require(r10.get('status')=='PASS_REAL_READONLY_GT_REACHABILITY','R10_STATUS_NOT_PASS')
    require(r11.get('status')=='PASS_STRUCTURAL_TRIAGE_SEARCH_MISSES_NOT_CLASSIFIABLE','R11_STATUS_NOT_PASS')
    require(r11.get('r10_report')==str(r10_dir/'h32_r10_report.json'),'R11_R10_PROVENANCE_MISMATCH')
    source=source_check(root)
    affected_file=r11_dir/'h32_r11_affected_queries.csv'
    require(affected_file.is_file(),'R11_AFFECTED_QUERIES_MISSING')
    affected=defaultdict(dict)
    with affected_file.open(newline='',encoding='utf-8') as f:
        for row in csv.DictReader(f):
            role=row['role']; require(role in ROLES,'UNKNOWN_ROLE_IN_R11_CSV')
            qi=int(row['query_index'])
            unreachable=json.loads(row['gt_unreachable_ids'])
            require(0<=qi<NQ and unreachable,f'INVALID_AFFECTED_QUERY {role} {qi}')
            require(qi not in affected[role],'DUPLICATE_AFFECTED_QUERY')
            affected[role][qi]=set(map(int,unreachable))
    for role in ROLES:
        expect=r10['graphs'][role]['GT']['unreachable_gt_positions_M']
        require(sum(len(s) for s in affected[role].values())==expect, f'AFFECTED_MISMATCH_R10 {role}')
    queries={qi for byquery in affected.values() for qi in byquery}
    gtrows=get_gt_rows(root/'data/sift1m_gt.ibin',queries)
    proxy=vectors_for_queries(root/'data/sift1m.fbin',root/'data/sift1m_queries.fbin',gtrows) if queries else {}
    # Need reachability only for affected roles to classify GT[10:100] tie replacements
    kit=root/'experiments/H32/R11_kit/h32_r11_audit.py'
    require(kit.is_file(),f'R11_SCRIPT_MISSING: {kit}')
    spec=importlib.util.spec_from_file_location('h32_r11_original',kit)
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    masks={}
    for role in ROLES:
        if affected[role]:
            gspec=mod.GRAPH_SPECS[role]
            depth,_,_,meta=mod.graph_depth_indegree(root/gspec['path'],gspec,ROOT_REQUIRED,0)
            require(meta['sha256']==r10['graphs'][role]['graph']['sha256'],'GRAPH_PROVENANCE_MISMATCH')
            masks[role]=depth
    rows=[];details={}
    for role in ROLES:
        strict_deficit=r10['graphs'][role]['GT']['unreachable_gt_positions_M']
        recorded_deficit=0; proxy_deficit=0; tie_mismatch=0; exact_extra=0; recorded_extra=0
        for qi,unreachable in sorted(affected[role].items()):
            ids,distances=gtrows[qi]
            valid_gt10=sum(vid not in unreachable for vid in ids[:K])
            require(valid_gt10==K-len(unreachable),'GT_R11_UNREACH_IDS_MISMATCH')
            # IDs beyond k: require directed reachable (measured from pinned graph)
            d10=distances[K-1];p10=proxy[qi][K-1]
            extra_recorded=[j for j in range(K,GTW) if distances[j]==d10 and masks[role][ids[j]]>=0]
            extra_proxy=[j for j in range(K,GTW) if proxy[qi][j]==p10 and masks[role][ids[j]]>=0]
            recorded_floor=max(0,K-valid_gt10-len(extra_recorded))
            proxy_floor=max(0,K-valid_gt10-len(extra_proxy))
            recorded_deficit+=recorded_floor;proxy_deficit+=proxy_floor
            exact_extra+=len(extra_proxy);recorded_extra+=len(extra_recorded)
            mismatch=(set(extra_proxy)!=set(extra_recorded))
            tie_mismatch+=int(mismatch)
            rows.append({'role':role,'query_index':qi,'strict_gt10_unreachable':len(unreachable),
                        'stored_GT_distance_reachable_tie_replacements':len(extra_recorded),
                        'recomputed_float32_reachable_tie_replacements':len(extra_proxy),
                        'stored_GT_tie_floor':recorded_floor,'recomputed_float32_tie_floor':proxy_floor,
                        'stored_vs_recomputed_tie_set_mismatch':mismatch,
                        'GT_tenth_distance_stored':d10,'GT_tenth_distance_recomputed':p10})
        details[role]={'strict_gt10_unreachable_M':strict_deficit,
                        'stored_gt_tie_proxy_miss_floor':recorded_deficit,
                        'float32_sequential_proxy_miss_floor':proxy_deficit,
                        'affected_queries':len(affected[role]),
                        'stored_tie_replacements':recorded_extra,
                        'float32_tie_replacements':exact_extra,
                        'queries_where_tie_sets_disagree':tie_mismatch,
                        'strict_ceiling':1-strict_deficit/(NQ*K),
                        'stored_gt_tie_proxy_ceiling':1-recorded_deficit/(NQ*K),
                        'float32_sequential_proxy_ceiling':1-proxy_deficit/(NQ*K),
                        'native_exact_ceiling_not_certified':True}
    output_parent=root/'experiments/H32'; require(output_parent.is_dir(),'H32_OUTPUT_PARENT_MISSING')
    out=output_parent/('H32_R12_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    out.mkdir()
    report={'status':'PASS_SOURCE_AND_TIE_PROXY_AUDIT_NATIVE_EQUIVALENCE_UNVERIFIED',
            'R10':str(r10_dir),'R11':str(r11_dir),'source_audit':source,'graphs':details,
            'limits':['No ANN build/search, no mutation.','Stored GT distance equality may differ from native query-to-base float32 equality.',
                      'Sequential float32 recomputation may differ from compiler SIMD/fast-math numeric evaluation.',
                      'Native binary was not recompiled or verified by this audit.',
                      'Upper bounds apply to entry0 graph traversal; no equal-degree/index-byte matching.',
                      'GT exactness was not independently recomputed.']}
    (out/'h32_r12_report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    with (out/'h32_r12_affected_ties.csv').open('w',newline='',encoding='utf-8') as f:
        if rows:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    lines=['H32-R12 | SOURCE ENTRY + TIE-AWARE REACHABILITY PROXY','OVERALL='+report['status'],
            'NATIVE_BINARY_EXACT_PARITY=NOT_VERIFIED','NO BUILD / NO ANN SEARCH / NO GRAPH MODIFICATION',
            'SOURCE_POLICY='+source['vamana_search_entry_from_source'],
            'SOURCE_TIE_POLICY='+source['native_recall_source'],
            'SOURCE_GIT_HEAD='+source['git_head'],'']
    for role in ROLES:
        o=details[role]
        lines += [f'[{role}] STRICT_UNREACHABLE_GT10_M={o["strict_gt10_unreachable_M"]} AFFECTED_QUERIES={o["affected_queries"]}',
                  f'  STORED_GT_TIE_PROXY_MISS_FLOOR={o["stored_gt_tie_proxy_miss_floor"]}',
                  f'  FLOAT32_SEQUENTIAL_TIE_PROXY_MISS_FLOOR={o["float32_sequential_proxy_miss_floor"]}',
                  f'  TIE_SET_DISAGREEING_QUERIES={o["queries_where_tie_sets_disagree"]}',
                  f'  STRICT_CEILING={o["strict_ceiling"]:.8f}',
                  f'  STORED_GT_TIE_PROXY_CEILING={o["stored_gt_tie_proxy_ceiling"]:.8f}',
                  f'  FLOAT32_TIE_PROXY_CEILING={o["float32_sequential_proxy_ceiling"]:.8f}','']
    lines += ['RESEARCH_DECISION=Do not compare strict GT@10 structural ceiling directly to native tie-aware H31 recall without validated parity.',
              'NEXT=If native query-by-query prediction IDs are needed, create an isolated diagnostic build; do not modify graph.',
              'H32R12_DONE='+str(out)]
    (out/'h32_r12_summary.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('\n'.join(lines))

def selftest():
    # One unreachable GT10 position can be replaced by a reachable exact-distance tie.
    gt10=[0,1,2,3,4,5,6,7,8,9]
    unreachable={9}
    extra=[10]
    require(K-sum(i not in unreachable for i in gt10)-len(extra)==0,'SELFTEST_TIE_REPLACEMENT_FAILED')
    require(float_l2_sequential([1.0,2.0],[1.0,4.0])==4.0,'SELFTEST_L2_FAILED')
    require(f32(1.0)==1.0,'SELFTEST_F32_FAILED')
    print('H32R12_SYNTHETIC_SELFTEST_PASS (no real SIFT1M data checked)')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--mode',required=True,choices=['selftest','audit']);ap.add_argument('--root',default='~/ann-task-a')
    args=ap.parse_args()
    try:
        if args.mode=='selftest':selftest()
        else:perform(Path(args.root))
    except (AuditError,OSError,ValueError,KeyError,struct.error) as e:
        print(f'H32R12_FAIL_CLOSED={e}',file=sys.stderr)
        sys.exit(2)
if __name__=='__main__':main()
