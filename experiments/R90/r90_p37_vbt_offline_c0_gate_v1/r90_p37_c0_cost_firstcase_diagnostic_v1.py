#!/usr/bin/env python3
"""R90-P3.7 fail-closed first-case COST diagnostic, read-only.

Use this after r90_p37_independent_c0_replay_v1.py HOLD_COST_cross_rectangular_matrix_cells.
Validates the ORIGINAL source on seed 555/random/kb 8 against the immutable archive,
then separately reconstructs the same set of joins and recalculates all work counts.
NO graph build, NO modification to source/archive/dataset, NO overwrite of any results.

Usage:
 python3 THIS.py selftest
 python3 THIS.py diagnose --archive ~/R90_P37_EVIDENCE_v1.tar.gz \
    --source ~/Downloads/r90_p37_vbt_offline_c0_gate_v1.py \
    --base ~/ann-task-a/data/sift100k.fbin
"""
from __future__ import annotations
import argparse,csv,hashlib,importlib.util,io,json,pathlib,sys,tarfile
import numpy as np

ARCHIVE_SHA='43cc4bcf7bf7b6ad43f5967c160d98a38acd2183aa4dc57d768b37777cc5fec9'
SOURCE_SHA='7090021f62af082abe38fa3cca54492cc0afebf589caea57dc914532baabb4cf'
BASE_SHA='e50ff1bc34bcc6d1c97dd001023c09a666971cde64605cc06671ed8a8ff1ed12'
GT_SHA='2f838dab19b8e48006b97f5bc263f4d3b2a9ec2847b320e065300c1bae12a2b4'
QIDS_SHA='8440c63e92d31fcf4edc31ce691de76364b5e04f8950cd7db5fafe534d5ecb0a'
HOME=pathlib.Path.home()
DEFAULT_ARCHIVE=HOME/'R90_P37_EVIDENCE_v1.tar.gz'
DEFAULT_SOURCE=HOME/'Downloads/r90_p37_vbt_offline_c0_gate_v1.py'
DEFAULT_BASE=HOME/'ann-task-a/data/sift100k.fbin'
FIELDS=['within_full_matrix_cells','within_unique_pairs','cross_rectangular_matrix_cells','total_distance_matrix_cells','unique_tile_joins','TOTAL_PARTITION_POINT_CENTROID_EVALS','TOTAL_PARTITION_AND_TILE_DISTANCE_CELLS']
METHODS=('seam','center_topk','center_workmatched')

def gate(ok,code):
    if not ok:raise RuntimeError('R90_P37_DIAG_HOLD_'+code)

def sha_file(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(4<<20),b''):h.update(chunk)
    return h.hexdigest()

def sha_arr(a):return hashlib.sha256(np.asarray(a).tobytes(order='C')).hexdigest()

def module_load(source):
    gate(source.is_file() and sha_file(source)==SOURCE_SHA,'SOURCE_SHA')
    spec=importlib.util.spec_from_file_location('r90_p37_original_source_for_diagnostic',str(source))
    gate(spec is not None and spec.loader is not None,'SOURCE_IMPORT_SPEC')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m

def load_archive(path):
    gate(path.is_file() and sha_file(path)==ARCHIVE_SHA,'ARCHIVE_SHA')
    with tarfile.open(path,'r:gz') as tar:
        members=tar.getmembers()
        gate(len(members)==3 and {m.name for m in members}=={'offline_arms.csv','result_manifest.json','eval_qids_and_gt10.npz'},'ARCHIVE_3_MEMBERS')
        gate(all(m.isfile() and m.size<10000000 for m in members),'ARCHIVE_TYPE_SIZE')
        files={m.name:tar.extractfile(m).read() for m in members}
    manifest=json.loads(files['result_manifest.json'])
    for item,key in [('offline_arms.csv','csv_sha'),('eval_qids_and_gt10.npz','eval_npz_sha')]:
        gate(hashlib.sha256(files[item]).hexdigest()==manifest[key],key+'_CHECK')
    gate(manifest['base_sha']==BASE_SHA and manifest['eval_gt10_sha']==GT_SHA and manifest['eval_qids_sha']==QIDS_SHA,'MANIFEST_INPUT_GT_SHA')
    rows=list(csv.DictReader(io.StringIO(files['offline_arms.csv'].decode())))
    gate(len(rows)==72,'ARM_COUNT')
    case=next(x for x in manifest['cases'] if int(x['seed'])==555 and x['mode']=='random')
    selected={(r['control']):r for r in rows if int(r['seed'])==555 and r['center_mode']=='random' and int(r['kb'])==8}
    gate(set(selected)==set(METHODS),'FIRST_CASE_ARMS')
    with np.load(io.BytesIO(files['eval_qids_and_gt10.npz']),allow_pickle=False) as z:
        qids=np.array(z['qids'],dtype=np.int32,copy=True)
        gt10=np.array(z['gt10'],dtype=np.int32,copy=True)
    gate(qids.shape==(2000,) and gt10.shape==(2000,10) and sha_arr(qids)==QIDS_SHA and sha_arr(gt10)==GT_SHA,'GT_QIDS_ARRAYS')
    return selected,case,qids,gt10

def direct_budget(edges,sizes,T,M,n,training):
    s=np.asarray(sizes,dtype=np.int64)
    own=int(np.dot(s,s))
    tri=int(np.sum(s*(s-1)//2,dtype=np.int64))
    decoded=[divmod(int(e),T) for e in edges]
    gate(all(0<=a<b<T for a,b in decoded),'EDGE_ID_ORDER')
    cross=int(sum(int(s[a])*int(s[b]) for a,b in decoded))
    return {'within_full_matrix_cells':own,'within_unique_pairs':tri,
            'cross_rectangular_matrix_cells':cross,'total_distance_matrix_cells':own+cross,
            'unique_tile_joins':len(decoded),'TOTAL_PARTITION_POINT_CENTROID_EVALS':n*(M+T)+training,
            'TOTAL_PARTITION_AND_TILE_DISTANCE_CELLS':n*(M+T)+training+own+cross}

def row_comparison(arm,csv_row,reference,recomputed):
    print('ARM',arm,flush=True)
    bad=[]
    for field in FIELDS:
        past=int(csv_row[field]);orig=int(reference[field]);own=int(recomputed[field]);delta=own-past
        print('  FIELD',field,'archive',past,'source_scenario',orig,'direct_reconstruction',own,'direct_minus_archive',delta,flush=True)
        if orig!=past or own!=past:bad.append(field)
    return bad

def run(z):
    orig=module_load(z.source)
    csv_rows,manifest_case,qids,gt10=load_archive(z.archive)
    gate(z.base.is_file() and sha_file(z.base)==BASE_SHA,'BASE_SHA')
    x,n,d=orig.read_fbin(z.base,verify_sha=True)
    gate((n,d)==(100000,128),'BASE_SHAPE')
    M=(n+255)//256
    print('R90_P37_DIAG_INPUTS_SOURCE_ARCHIVE_BASE_GT_SHA_PASS',flush=True)
    print('R90_P37_DIAG_ENV_NUMPY',np.__version__, 'source',SOURCE_SHA[:12], 'archive',ARCHIVE_SHA[:12],flush=True)
    # Reproduce EXACT original scenario through its original entrypoint.
    printed,sc=orig.scenario(x,qids,gt10,555,'random',256,(8,))
    gate(len(printed)==3 and sc['tile_map_sha']==manifest_case['tile_map_sha'] and sc['coarse_map_sha']==manifest_case['coarse_map_sha'],'ORIGINAL_SCENARIO_MAP_SHA')
    original_by_arm={r['control']:r for r in printed}
    gate(set(original_by_arm)==set(METHODS),'ORIGINAL_SCENARIO_3ARMS')
    print('R90_P37_DIAG_SOURCE_SCENARIO_555_RANDOM_K8_MAP_SHA_PASS',sc['tile_map_sha'][:16],flush=True)
    # Execute same source path independently, with direct budget calculation.
    cent,training,meta=orig.choose_centers(x,M,555,'random')
    coarse=orig.assign_coarse(x,cent)
    cells,tile,final_cent,sizes,splits=orig.split_overfull(x,coarse,256)
    gate(sha_arr(coarse)==manifest_case['coarse_map_sha'] and sha_arr(tile)==manifest_case['tile_map_sha'],'DIRECT_REBUILD_MAP_SHA')
    T=len(cells)
    alt=orig.final_alternates(x,final_cent,tile)
    dc=orig.center_distance(final_cent)
    seam,deficit,unique=orig.seam_adjacency(tile,alt,dc,8)
    ctop=orig.center_knn_adjacency(dc,8)
    target=direct_budget(seam,sizes,T,M,n,training)['cross_rectangular_matrix_cells']
    cwork=orig.center_workmatched(dc,sizes,target)
    edge_sets={'seam':seam,'center_topk':ctop,'center_workmatched':cwork}
    fullmatch=True
    for arm in METHODS:
        e=edge_sets[arm]
        b=direct_budget(e,sizes,T,M,n,training)
        alt_src=orig.work(e,sizes,T)
        gate(all(b[key]==alt_src[key] for key in alt_src),'BUDGET_IMPLEMENTATIONS_DISAGREE_'+arm)
        csvr=csv_rows[arm];ref=original_by_arm[arm]
        bad=row_comparison(arm,csvr,ref,b)
        fullmatch=fullmatch and not bad
        print('  EDGE_COUNT',len(e),'EDGE_SHA256',sha_arr(np.array(sorted(e),dtype=np.int64)),'BAD_FIELDS',bad,flush=True)
    if fullmatch:
        print('R90_P37_DIAG_FIRSTCASE_3ARMS_CROSS_AND_WORK_REPRO_PASS',flush=True)
        print('R90_P37_DIAG_REPLAY_V1_REVIEW_NEEDED_IF_IT_STILL_FAILS',flush=True)
    else:
        print('R90_P37_DIAG_SOURCE_FIRSTCASE_COST_NOT_REPRODUCIBLE_HOLD',flush=True)
        raise SystemExit(2)

def selftest():
    s=np.array([2,2,3],dtype=np.int32);T=3;E={1,2}
    z=direct_budget(E,s,T,3,7,0)
    gate(z['cross_rectangular_matrix_cells']==10,'SELF_CROSS')
    gate(z['within_full_matrix_cells']==17,'SELF_OWN')
    gate(z['within_unique_pairs']==5,'SELF_PAIRS')
    gate(z['total_distance_matrix_cells']==27,'SELF_TOTAL')
    gate(z['TOTAL_PARTITION_POINT_CENTROID_EVALS']==42,'SELF_TRAIN')
    print('R90_P37_DIAG_SELFTEST_PASS_DIRECT_BUDGET_AND_ID_DECODE',flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase',choices=['selftest','diagnose'])
    p.add_argument('--archive',type=pathlib.Path,default=DEFAULT_ARCHIVE)
    p.add_argument('--source',type=pathlib.Path,default=DEFAULT_SOURCE)
    p.add_argument('--base',type=pathlib.Path,default=DEFAULT_BASE)
    z=p.parse_args()
    try:
        if z.phase=='selftest':selftest()
        else:run(z)
    except Exception as ex:
        print('R90_P37_DIAG_EXCEPTION_HOLD',repr(ex),file=sys.stderr,flush=True)
        raise SystemExit(2)
if __name__=='__main__':main()
