#!/usr/bin/env python3
"""R90-P3.7 independent C0 replay from pinned ORIGINAL SCRIPT + real SIFT100K.

Recreates six partitions with a SHA-locked original source implementation, then
INDEPENDENTLY counts 72 arm raw/Top2 C0 and exact logical operation budgets.
The archive's tile maps/joins are absent; matching regenerated tile_map SHA
is a precondition of evidence-equivalent replay, not proof of formal VBT quality.

This is not a new ANN graph BUILD, not a speedup, not native HashPrune, and does
not replace RBC N1/N2 SAME-ANCHOR controls. Fails closed; never touches R90-P3.7.

Usage:
 python3 THIS.py selftest
 python3 THIS.py preflight --archive ... --source ... --base ...
 python3 THIS.py audit     --archive ... --source ... --base ... [--out DIR]
"""
from __future__ import annotations
import argparse, csv, hashlib, importlib.util, io, json, os, pathlib, sys, tarfile
from collections import Counter
import numpy as np

EXPECTED_ARCHIVE = '43cc4bcf7bf7b6ad43f5967c160d98a38acd2183aa4dc57d768b37777cc5fec9'
EXPECTED_SOURCE = '7090021f62af082abe38fa3cca54492cc0afebf589caea57dc914532baabb4cf'
EXPECTED_BASE = 'e50ff1bc34bcc6d1c97dd001023c09a666971cde64605cc06671ed8a8ff1ed12'
EXPECTED_GT = '2f838dab19b8e48006b97f5bc263f4d3b2a9ec2847b320e065300c1bae12a2b4'
EXPECTED_QIDS = '8440c63e92d31fcf4edc31ce691de76364b5e04f8950cd7db5fafe534d5ecb0a'
KBS=(8,12,16,20); SEEDS=(555,556,557); MODES=('random','sample1pct_kmeans')
CONTROLS=('seam','center_topk','center_workmatched')
ARCHIVE = pathlib.Path.home() / 'R90_P37_EVIDENCE_v1.tar.gz'
SOURCE = pathlib.Path.home() / 'Downloads/r90_p37_vbt_offline_c0_gate_v1.py'
BASE = pathlib.Path.home() / 'ann-task-a/data/sift100k.fbin'
OUT = pathlib.Path.home() / 'ann-task-a/experiments/R90/r90_p37_independent_c0_replay_v1'

def fail(code): raise RuntimeError('R90_P37_C0_HOLD_'+str(code))
def need(x,code):
    if not x: fail(code)
def sha_bytes(x): return hashlib.sha256(x).hexdigest()
def sha_file(p):
    hh=hashlib.sha256()
    with pathlib.Path(p).open('rb') as f:
        for chunk in iter(lambda:f.read(4<<20),b''):hh.update(chunk)
    return hh.hexdigest()
def sha_array(x): return sha_bytes(np.asarray(x).tobytes(order='C'))

def load_archive(path):
    need(path.is_file(),'ARCHIVE_MISSING')
    need(sha_file(path)==EXPECTED_ARCHIVE,'ARCHIVE_SHA')
    with tarfile.open(path,'r:gz') as f:
        mm=f.getmembers()
        need(len(mm)==3 and {m.name for m in mm}=={'result_manifest.json','offline_arms.csv','eval_qids_and_gt10.npz'},'ARCHIVE_MEMBERS')
        need(all(m.isfile() and m.size<10000000 for m in mm),'ARCHIVE_MEMBER_SIZE_OR_TYPE')
        files={m.name:f.extractfile(m).read() for m in mm}
    manifest=json.loads(files['result_manifest.json'])
    need(sha_bytes(files['offline_arms.csv'])==manifest['csv_sha'],'CSV_SHA')
    need(sha_bytes(files['eval_qids_and_gt10.npz'])==manifest['eval_npz_sha'],'NPZ_SHA')
    need(manifest['base_sha']==EXPECTED_BASE and manifest['eval_gt10_sha']==EXPECTED_GT and manifest['eval_qids_sha']==EXPECTED_QIDS,'MANIFEST_PIN')
    with np.load(io.BytesIO(files['eval_qids_and_gt10.npz']),allow_pickle=False) as z:
        qids=np.asarray(z['qids'],dtype=np.int32).copy()
        gt=np.asarray(z['gt10'],dtype=np.int32).copy()
    need(qids.shape==(2000,) and gt.shape==(2000,10),'GT_SHAPE')
    need(sha_array(qids)==EXPECTED_QIDS and sha_array(gt)==EXPECTED_GT,'GT_ARRAY_SHA')
    need(np.all(np.diff(qids)>0) and np.all(gt!=qids[:,None]),'GT_ROWS_VALID')
    records=list(csv.DictReader(io.StringIO(files['offline_arms.csv'].decode('utf-8'))))
    need(len(records)==72,'CSV_ROWS_72')
    by_key={}
    for r in records:
        key=(int(r['seed']),r['center_mode'],int(r['kb']),r['control'])
        need(key not in by_key,'DUPLICATE_ARM')
        need(key[0] in SEEDS and key[1] in MODES and key[2] in KBS and key[3] in CONTROLS,'UNKNOWN_ARM')
        by_key[key]=r
    need(len(by_key)==72,'ARM_KEYSET')
    cases={(int(x['seed']),x['mode']):x for x in manifest['cases']}
    need(len(cases)==6,'CASE_COUNT')
    return qids,gt,by_key,cases

def source_module(path):
    need(path.is_file(),'SOURCE_MISSING')
    need(sha_file(path)==EXPECTED_SOURCE,'ORIGINAL_SOURCE_SHA')
    spec=importlib.util.spec_from_file_location('p37_pinned_original',str(path))
    need(spec is not None and spec.loader is not None,'IMPORT_SPEC')
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def independent_raw_hits(qids,gt,tile,edges,T):
    """Direct adjacency matrix lookup, not P3.7's encoded-edge np.isin."""
    adjacency=np.zeros((T,T),dtype=np.bool_)
    np.fill_diagonal(adjacency,True)
    for e in edges:
        a,b=divmod(int(e),T)
        need(0<=a<T and 0<=b<T and a!=b,'ENCODED_EDGE_RANGE')
        adjacency[a,b]=True;adjacency[b,a]=True
    mask=adjacency[tile[qids,None],tile[gt]]
    return mask, int(mask.sum())

def independent_top2_pass(x,qids,gt,cells,tile):
    """Direct float32 squared L2 with sum(), separate from original einsum.

    Bitwise identity with the ORIGINAL post_top2 semantics is asserted by counts
    below. On roundoff-sensitive inputs a mismatch is a HOLD, never patched.
    """
    cache={}
    def near2(p,t):
        key=(int(p),int(t))
        if key not in cache:
            idx=cells[t]
            dif=np.asarray(x[idx],dtype=np.float32)-np.asarray(x[p],dtype=np.float32)
            dd=np.sum(dif*dif,axis=1,dtype=np.float32)
            dd=np.asarray(dd).copy();dd[idx==p]=np.inf
            order=np.lexsort((idx,dd))[:2]
            cache[key]=frozenset(int(idx[i]) for i in order if np.isfinite(dd[i]))
        return cache[key]
    out=np.zeros(gt.shape,dtype=np.bool_)
    for i,q in enumerate(qids):
        q=int(q)
        for j,tgt in enumerate(gt[i]):
            v=int(tgt)
            out[i,j]=(v in near2(q,int(tile[v])) or q in near2(v,int(tile[q])))
    return out,len(cache)

def calculate_budget(sizes,T,edges,M,n,training):
    own=sum(int(z)**2 for z in sizes)
    own_unordered=sum(int(z)*(int(z)-1)//2 for z in sizes)
    cross=sum(int(sizes[divmod(int(e),T)[0]])*int(sizes[divmod(int(e),T)[1]]) for e in edges)
    return dict(within_full_matrix_cells=own,within_unique_pairs=own_unordered,
                cross_rectangular_matrix_cells=cross,total_distance_matrix_cells=own+cross,
                unique_tile_joins=len(edges),TOTAL_PARTITION_POINT_CENTROID_EVALS=n*(M+T)+training,
                TOTAL_PARTITION_AND_TILE_DISTANCE_CELLS=n*(M+T)+training+own+cross)

def validate_row(row,budget,raw,post):
    need(0<=post<=raw<=20000,'COVERAGE_ORDER')
    for k,v in budget.items():
        need(int(row[k])==v,'COST_'+k)
    need(int(row['raw_hits'])==raw,'RAW_HITS')
    need(int(row['post_top2_hits'])==post,'TOP2_HITS')
    need(int(row['exact_top10_total'])==20000,'GT_TOTAL')
    need(abs(float(row['raw_C0'])-raw/20000)<1e-8,'RAW_RATIO')
    need(abs(float(row['post_top2_C0'])-post/20000)<1e-8,'POST_RATIO')

def do_audit(archive,source,base,out):
    need(not out.exists() and not out.is_symlink(),'AUDIT_OUT_EXISTS')
    print('R90_P37_C0_REPLAY_START',flush=True)
    qids,gt,records,cases=load_archive(archive)
    orig=source_module(source)
    x,n,d=orig.read_fbin(base,verify_sha=True)
    need((n,d)==(100000,128),'BASE_DIM')
    verified=0;case_result=[]
    evidence_arrays={'qids':qids,'gt10':gt}
    for seed in SEEDS:
        for mode in MODES:
            prev=cases[(seed,mode)]
            M=(n+255)//256
            cent,training,trainmeta=orig.choose_centers(x,M,seed,mode)
            coarse=orig.assign_coarse(x,cent)
            cells,tile,final_cent,sizes,splits=orig.split_overfull(x,coarse,256)
            need(sha_array(coarse)==prev['coarse_map_sha'],'COARSE_SHA_'+str(seed)+'_'+mode)
            need(sha_array(tile)==prev['tile_map_sha'],'TILE_MAP_SHA_'+str(seed)+'_'+mode)
            T=len(cells)
            key_suffix=f'{seed}_{mode}'
            evidence_arrays[f'tile_{key_suffix}']=np.asarray(tile,dtype=np.int32)
            evidence_arrays[f'sizes_{key_suffix}']=np.asarray(sizes,dtype=np.int32)
            need(T==prev['final_T'] and splits==prev['splits'],'PARTITION_META')
            need(int(sizes.sum())==n and int(sizes.max())<=256,'PARTITION_TOTAL')
            need(training==int(prev['training']['train_size'])*int(prev['training']['iterations'])*M,'TRAIN_COST')
            print('R90_P37_C0_TILE_REPLAY_PASS',seed,mode,'tiles',T,'coarse_sha',prev['coarse_map_sha'][:12],'tile_sha',prev['tile_map_sha'][:12],flush=True)
            alternates=orig.final_alternates(x,final_cent,tile)
            centerd=orig.center_distance(final_cent)
            postmask,ncache=independent_top2_pass(x,qids,gt,cells,tile)
            need(ncache>0,'NO_POST2_CACHE')
            evidence_arrays[f'post2_{key_suffix}']=np.asarray(postmask,dtype=np.uint8)
            for kb in KBS:
                seam,deficit,ignored=orig.seam_adjacency(tile,alternates,centerd,kb)
                ctopk=orig.center_knn_adjacency(centerd,kb)
                seam_cost=calculate_budget(sizes,T,seam,M,n,training)
                matched=orig.center_workmatched(centerd,sizes,seam_cost['cross_rectangular_matrix_cells'])
                edgesets={'seam':seam,'center_topk':ctopk,'center_workmatched':matched}
                for control,edges in edgesets.items():
                    row=records[(seed,mode,kb,control)]
                    rawmask,raw=independent_raw_hits(qids,gt,tile,edges,T)
                    post=int((rawmask&postmask).sum())
                    budget=calculate_budget(sizes,T,edges,M,n,training)
                    evidence_arrays[f'joins_{key_suffix}_{kb}_{control}']=np.asarray(sorted(edges),dtype=np.int64)
                    validate_row(row,budget,raw,post)
                    need(int(row['final_tile_count'])==T,'TILE_COUNT_ROW')
                    need(int(row['missing_seam_directed_slots'])==(deficit if control=='seam' else -1),'SEAM_DEGREE_DEFICIT')
                    verified+=1
            case_result.append({'seed':seed,'center':mode,'final_tiles':T,'top2_cache_size':ncache,'verified_arms':12,
                                'tile_sha':prev['tile_map_sha'],'coarse_sha':prev['coarse_map_sha']})
            print('R90_P37_C0_CASE_REPLAY_PASS',seed,mode,'arms',12,'sampled_top2_contexts',ncache,flush=True)
    need(verified==72,'TOTAL_72_ARMS')
    report={'status':'PASS_REPLAYED_PARTITION_TILE_AND_72_ARM_RAW_POSTTOP2_C0_COST',
            'scope':'P3.7 offline only; source-pinned same algorithm partition/joins, independent C0+work count implementation; NOT fully independently derived partition algorithm',
            'original_archive_sha':EXPECTED_ARCHIVE,'original_source_sha':EXPECTED_SOURCE,
            'base_sha':EXPECTED_BASE,'qids_sha':EXPECTED_QIDS,'gt10_sha':EXPECTED_GT,
            'matched_arm_count':verified,'cases':case_result,
            'limitations':['RBC N1/N2 same-sample raw and native Top2 proposals missing',
             'Post Top2 remains offline float32 simulation, not native PiPNN packed selection/HashPrune',
             'Real ANN BUILD/Recall/QPS not tested',
             'Same original source regenerates partitions and join lists, but independent matrix counting validates archive numerators and work',
             'Independent FP64 GT is separately checked on sampled anchors, not entire 2000']}
    out.mkdir(parents=True,exist_ok=False)
    np.savez_compressed(out/'independent_c0_replay_trace.npz',**evidence_arrays)
    report['replay_trace_sha256']=sha_file(out/'independent_c0_replay_trace.npz')
    report['trace_arrays_count']=len(evidence_arrays)
    (out/'independent_c0_replay_audit.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print('R90_P37_C0_INDEPENDENT_72ARM_REPLAY_PASS',verified,'report',out/'independent_c0_replay_audit.json',flush=True)
    print('R90_P37_C0_REPLAY_TRACE_SHA',report['replay_trace_sha256'],'trace',out/'independent_c0_replay_trace.npz',flush=True)
    print('R90_P37_C0_ALGORITHMIC_RBC_MATCHED_HOLD__NOT_AN_ANN_BUILD_PASS',flush=True)

def selftest():
    x=np.array([[0.],[1.],[2.],[5.]],dtype=np.float32)
    cells=[np.array([0,1],dtype=np.int32),np.array([2,3],dtype=np.int32)]
    tile=np.array([0,0,1,1],dtype=np.int32)
    qids=np.array([0,2],dtype=np.int32)
    gt=np.array([[1,2],[1,3]],dtype=np.int32)
    edges={1}
    mask,raw=independent_raw_hits(qids,gt,tile,edges,2)
    need(raw==4 and mask.shape==(2,2),'TEST_RAW')
    pm,c=independent_top2_pass(x,qids,gt,cells,tile)
    need(pm.shape==(2,2) and c>0 and pm.dtype==np.bool_,'TEST_TOP2')
    w=calculate_budget(np.array([2,2]),2,edges,2,4,0)
    need(w['total_distance_matrix_cells']==12 and w['TOTAL_PARTITION_AND_TILE_DISTANCE_CELLS']==28,'TEST_WORK')
    print('R90_P37_C0_INDEPENDENT_REPLAY_SELFTEST_PASS',flush=True)

def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('phase',choices=['selftest','preflight','audit'])
    a.add_argument('--archive',type=pathlib.Path,default=ARCHIVE)
    a.add_argument('--source',type=pathlib.Path,default=SOURCE)
    a.add_argument('--base',type=pathlib.Path,default=BASE)
    a.add_argument('--out',type=pathlib.Path,default=OUT)
    z=a.parse_args()
    try:
        if z.phase=='selftest':selftest();return
        load_archive(z.archive)
        source_module(z.source)
        orig=source_module(z.source)
        orig.read_fbin(z.base,verify_sha=True)
        need(not z.out.exists() and not z.out.is_symlink(),'OUT_EXISTS')
        print('R90_P37_C0_REPLAY_PREFLIGHT_PASS_ARCHIVE_SOURCE_GT_BASE_AND_OUT',flush=True)
        if z.phase=='audit':do_audit(z.archive,z.source,z.base,z.out)
    except Exception as e:
        print('R90_P37_C0_REPLAY_HOLD',repr(e),file=sys.stderr,flush=True)
        raise SystemExit(2)
if __name__=='__main__':main()
