#!/usr/bin/env python3
"""H32-R14: retrospective per-query strict/tie-aware and cross-graph comparison.

Only reads original R11/R13 outputs and GT. No graph build, ANN search, modifications
or causal claims. Standard library only. Python >=3.9, little-endian SIFT1M.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import mmap
import struct
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

NQ=10000
K=10
GW=100
N=1_000_000
ROLES=('VAMANA','STOCK','TOP2')
GRAPH_SHA={
  'VAMANA':'84b2935cb9f25e9ad53044099901c8c1e6cb4de059975882e8d91bca66aa5259',
  'STOCK':'ce1cd7c5ae97b79972df2b30235a0844b88a6c8a983ce731ca3afca494d7095d',
  'TOP2':'73646a2b5655e16939ca804c598818460152803c20f6932e6e9286acd334c5c6',
}
H31_RECALL={'VAMANA':.983140,'STOCK':.990870,'TOP2':.990870}
STRICT_MISSED={'VAMANA':1759,'STOCK':979,'TOP2':979}
UNREACH_MISSED={'VAMANA':12,'STOCK':0,'TOP2':0}
class Failed(Exception): pass

def check(cond,why):
    if not cond:raise Failed(why)

def newest(folder,pat,required):
    dirs=sorted([d for d in folder.glob(pat) if d.is_dir() and (d/required).is_file()],reverse=True)
    check(bool(dirs),f'MISSING_RESULT dir={folder} pattern={pat} required={required}')
    return dirs[0]

def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()

def read_gt(path,nq=NQ):
    check(path.is_file() and path.stat().st_size==8+8*nq*GW,'GT_SHAPE_NOT_EXPECTED')
    with path.open('rb') as f:
        with mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as mm:
            check(struct.unpack_from('<II',mm,0)==(nq,GW),'GT_HEADER_INVALID')
            out=[]
            for i in range(nq):
                arr=struct.unpack_from('<10I',mm,8+i*GW*4)
                check(len(set(arr))==K and all(0<=x<N for x in arr),f'GT_IDS_INVALID query={i}')
                out.append(arr)
    return out

def load_r11(csvpath,nq=NQ):
    seen=set(); unreach={x:{} for x in ROLES}
    with csvpath.open(newline='',encoding='utf-8') as f:
        for row in csv.DictReader(f):
            role=row['role']; qi=int(row['query_index'])
            check(role in ROLES and 0<=qi<nq and (role,qi) not in seen,'BAD_R11_QUERY_MATRIX')
            seen.add((role,qi)); ui=row['unreachable_gt_ids']
            unreach[role][qi]=set(int(x) for x in ui.split(';') if x)
            check(len(unreach[role][qi])==int(row['unreachable_gt_positions']),'INCONSISTENT_R11_UNREACHABLE_COUNT')
    check(len(seen)==nq*len(ROLES),'INCOMPLETE_R11_MATRIX')
    return unreach

def load_preds(path,role,gt,unreach,nq=NQ):
    records=[]; missed_rank=Counter(); gt_miss=reach_miss=unreach_miss=0; strict_sum=tie_sum=0
    with path.open(newline='',encoding='utf-8') as f:
        reader=csv.DictReader(f)
        required={'query_index','strict_hits','tie_aware_hits',*(f'id{i}' for i in range(K))}
        check(required.issubset(set(reader.fieldnames or [])),'PREDICTIONS_CSV_MISSING_COLUMNS')
        for row in reader:
            qi=int(row['query_index']);check(qi==len(records) and qi<nq,'QUERY_ORDER_MISMATCH')
            ids=tuple(int(row[f'id{j}']) for j in range(K))
            check(len(set(ids))==K and all(0<=v<N for v in ids),'PREDICTION_ID_INVALID')
            got=set(ids);gold=gt[qi]; missing=[v for v in gold if v not in got]
            strict_hits=K-len(missing); tie_hits=int(row['tie_aware_hits'])
            check(strict_hits==int(row['strict_hits']),'STRICT_HITS_DISAGREE_WITH_GT')
            check(strict_hits<=tie_hits<=K,'TIE_HITS_OUT_OF_RANGE')
            absent=unreach[role][qi]
            check(absent.issubset(set(gold)),'R11_UNREACH_IDS_NOT_GT10')
            check(absent.issubset(set(missing)),'UNREACHABLE_GT_WAS_RETURNED_WITH_ENTRY0')
            missed_rank.update(i for i,v in enumerate(gold) if v in missing)
            gt_miss+=len(missing);unreach_miss+=len(absent);reach_miss+=len(missing)-len(absent)
            strict_sum+=strict_hits;tie_sum+=tie_hits
            records.append({'ids':ids,'id_set':got,'strict_hits':strict_hits,'tie_hits':tie_hits,
                            'strict_missing':tuple(missing),'unreach_missing':tuple(sorted(absent)),
                            'reachable_missing':tuple(v for v in missing if v not in absent)})
    check(len(records)==nq,'WRONG_PREDICTION_QUERY_COUNT')
    return records, {'strict_missed':gt_miss,'reachable_missed':reach_miss,'unreachable_missed':unreach_miss,
                    'strict_recall':strict_sum/(nq*K),'tie_aware_recall':tie_sum/(nq*K),
                    'tie_credit_hits':tie_sum-strict_sum,
                    'queries_with_any_strict_miss':sum(bool(r['strict_missing']) for r in records),
                    'queries_with_tie_credit':sum(r['tie_hits']>r['strict_hits'] for r in records),
                    'missed_gt_rank_histogram':dict(sorted(missed_rank.items())),
                    'predictions_csv_sha256':digest(path)}

def pair_stats(a,b):
    out={'queries_same_prediction_order':0,'queries_same_prediction_set':0,
         'total_prediction_overlap_ids':0,'A_strict_better_queries':0,'B_strict_better_queries':0,'strict_ties_queries':0,
         'A_tie_aware_better_queries':0,'B_tie_aware_better_queries':0,'tie_aware_ties_queries':0,
         'queries_with_different_strict_gt_hits':0,
         'queries_equal_strict_gt_hits_but_different_pred_set':0}
    for x,y in zip(a,b):
        same_order=x['ids']==y['ids'];same_set=x['id_set']==y['id_set']
        out['queries_same_prediction_order']+=same_order
        out['queries_same_prediction_set']+=same_set
        out['total_prediction_overlap_ids']+=len(x['id_set']&y['id_set'])
        ds=x['strict_hits']-y['strict_hits']; dt=x['tie_hits']-y['tie_hits']
        out['A_strict_better_queries']+=ds>0;out['B_strict_better_queries']+=ds<0;out['strict_ties_queries']+=ds==0
        out['A_tie_aware_better_queries']+=dt>0;out['B_tie_aware_better_queries']+=dt<0;out['tie_aware_ties_queries']+=dt==0
        out['queries_with_different_strict_gt_hits']+=ds!=0
        out['queries_equal_strict_gt_hits_but_different_pred_set']+=(ds==0 and not same_set)
    out['mean_prediction_overlap_at_10']=out['total_prediction_overlap_ids']/len(a)
    return out

def selftest():
    # Equal global hit counts do NOT imply identical predictions or errors by query.
    gt=[tuple(range(10)),tuple(range(10))]
    aa=[{'ids':tuple(range(10)),'id_set':set(range(10)),'strict_hits':10,'tie_hits':10},
        {'ids':tuple(range(10,20)),'id_set':set(range(10,20)),'strict_hits':0,'tie_hits':0}]
    bb=[{'ids':tuple(range(10,20)),'id_set':set(range(10,20)),'strict_hits':0,'tie_hits':0},
        {'ids':tuple(range(10)),'id_set':set(range(10)),'strict_hits':10,'tie_hits':10}]
    p=pair_stats(aa,bb)
    check(p['queries_same_prediction_set']==0 and p['A_strict_better_queries']==1 and p['B_strict_better_queries']==1,'PAIRED_DISCORDANCE_SELFTEST_FAILED')
    cc=[{'ids':tuple(range(10)),'id_set':set(range(10)),'strict_hits':10,'tie_hits':10}]
    check(pair_stats(cc,cc)['queries_same_prediction_order']==1,'IDENTITY_SELFTEST_FAILED')
    print('H32R14_PYTHON_SYNTHETIC_SELFTEST_PASS (NO REAL DATA CHECKED)')

def audit(root):
    root=root.expanduser().resolve(); exp=root/'experiments/H32'
    check(exp.is_dir(),'NO_EXPERIMENTS_H32_DIR')
    r11dir=newest(exp,'H32_R11_2*','h32_r11_report.json')
    r13dir=newest(exp,'H32_R13_2*','h32_r13_report.json')
    r11=json.loads((r11dir/'h32_r11_report.json').read_text(encoding='utf-8'))
    r13=json.loads((r13dir/'h32_r13_report.json').read_text(encoding='utf-8'))
    check(r11['status']=='PASS_STRUCTURAL_TRIAGE_SEARCH_MISSES_NOT_CLASSIFIABLE','R11_NOT_PASS')
    check(r13['status']=='PASS_SOURCE_BASED_PREDICTION_CAPTURE_WITH_AGGREGATE_GATE','R13_NOT_PASS')
    summary=(r13dir/'h32_r13_summary.txt').read_text(encoding='utf-8')
    check('SOURCE_GIT_HEAD=a48c6a34e5f959190992aa531cc18454cfcc3dd3' in summary,'R13_SOURCE_PIN_NOT_CONFIRMED')
    gt=read_gt(root/'data/sift1m_gt.ibin')
    unreachable=load_r11(r11dir/'h32_r11_gt_query_matrix.csv')
    records={};role_stats={}
    for role in ROLES:
        check(r13['roles'][role]['graph_sha256']==GRAPH_SHA[role],'R13_SHA_MISMATCH_'+role)
        check(r13['roles'][role]['aggregate_recall_parity_pass'] is True,'R13_AGGREGATE_GATE_FAILED_'+role)
        check(abs(r13['roles'][role]['observed_tie_aware_recall']-H31_RECALL[role])<2e-5,'H31_RECALL_GATE_FAILED_'+role)
        pred=r13dir/(role.lower()+'_q100_predictions.csv');check(pred.is_file(),'PREDICTION_MISSING_'+role)
        records[role],role_stats[role]=load_preds(pred,role,gt,unreachable)
        s=role_stats[role]; old=r13['roles'][role]
        check(s['strict_missed']==STRICT_MISSED[role]==old['strict_gt10_missed'],'STRICT_MISS_GATE_'+role)
        check(s['unreachable_missed']==UNREACH_MISSED[role]==old['strict_missed_unreachable_from_entry0'],'UNREACH_GATE_'+role)
        check(s['reachable_missed']==old['strict_missed_reachable_from_entry0'],'REACH_GATE_'+role)
        check(abs(s['tie_aware_recall']-H31_RECALL[role])<1e-10,'TIE_RECALL_GATE_'+role)
    paired={a+'__'+b:pair_stats(records[a],records[b]) for a,b in [('STOCK','TOP2'),('VAMANA','STOCK'),('VAMANA','TOP2')]}
    out=exp/('H32_R14_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'));out.mkdir()
    header=['query_index','VAMANA_strict_hits','STOCK_strict_hits','TOP2_strict_hits',
            'VAMANA_tie_hits','STOCK_tie_hits','TOP2_tie_hits',
            'VAMANA_reachable_missed','VAMANA_unreachable_missed',
            'STOCK_reachable_missed','TOP2_reachable_missed',
            'STOCK_TOP2_prediction_same_set','STOCK_TOP2_prediction_same_order',
            'STOCK_TOP2_strict_hits_delta','VAMANA_STOCK_strict_hits_delta']
    with (out/'h32_r14_paired_query_matrix.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=header);writer.writeheader()
        for qi in range(NQ):
            rv,rs,rt=(records[z][qi] for z in ROLES)
            writer.writerow({'query_index':qi,'VAMANA_strict_hits':rv['strict_hits'],'STOCK_strict_hits':rs['strict_hits'],
                 'TOP2_strict_hits':rt['strict_hits'],'VAMANA_tie_hits':rv['tie_hits'],'STOCK_tie_hits':rs['tie_hits'],
                 'TOP2_tie_hits':rt['tie_hits'],'VAMANA_reachable_missed':len(rv['reachable_missing']),
                 'VAMANA_unreachable_missed':len(rv['unreach_missing']),
                 'STOCK_reachable_missed':len(rs['reachable_missing']),'TOP2_reachable_missed':len(rt['reachable_missing']),
                 'STOCK_TOP2_prediction_same_set':int(rs['id_set']==rt['id_set']),
                 'STOCK_TOP2_prediction_same_order':int(rs['ids']==rt['ids']),
                 'STOCK_TOP2_strict_hits_delta':rs['strict_hits']-rt['strict_hits'],
                 'VAMANA_STOCK_strict_hits_delta':rv['strict_hits']-rs['strict_hits']})
    with (out/'h32_r14_unreachable_cases.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.writer(f);writer.writerow(['query_index','gt10_ids','unreachable_gt_ids','v_strict_missed_ids','v_reachable_missed_ids','s_strict_missed_ids','t_strict_missed_ids'])
        for qi in range(NQ):
            v=records['VAMANA'][qi]
            if not v['unreach_missing']:continue
            writer.writerow([qi,';'.join(map(str,gt[qi])),';'.join(map(str,v['unreach_missing'])),
                             ';'.join(map(str,v['strict_missing'])),';'.join(map(str,v['reachable_missing'])),
                             ';'.join(map(str,records['STOCK'][qi]['strict_missing'])),
                             ';'.join(map(str,records['TOP2'][qi]['strict_missing']))])
    with (out/'h32_r14_stock_top2_discordant_queries.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.writer(f);writer.writerow(['query_index','stock_strict_hits','top2_strict_hits','stock_tie_hits','top2_tie_hits','same_prediction_set','common_prediction_count','stock_predictions','top2_predictions','stock_missing_gt10','top2_missing_gt10'])
        for qi in range(NQ):
            s=records['STOCK'][qi];t=records['TOP2'][qi]
            if s['id_set']==t['id_set'] and s['strict_hits']==t['strict_hits'] and s['tie_hits']==t['tie_hits']:continue
            writer.writerow([qi,s['strict_hits'],t['strict_hits'],s['tie_hits'],t['tie_hits'],
                             int(s['id_set']==t['id_set']),len(s['id_set']&t['id_set']),
                             ';'.join(map(str,s['ids'])),';'.join(map(str,t['ids'])),
                             ';'.join(map(str,s['strict_missing'])),';'.join(map(str,t['strict_missing']))])
    status='PASS_R13_QUERY_PAIRED_AUDIT_READONLY'
    rep={'status':status,'source_dirs':{'R11':str(r11dir),'R13':str(r13dir)},
         'N_QUERY':NQ,'TOP_K':K,'roles':role_stats,'pairs':paired,
         'limits':['Pairwise comparison is descriptive, not matched graph-budget or novel-algorithm evidence.',
                   'R13 diagnostic compiled from same source; not per-query identical to original H31 binary.',
                   'Tie-aware recall uses R13 source-based IDs and native tie rule.',
                   'GT exactness not independently validated.',
                   'No per-expansion search trace; misses cannot be assigned to beam pruning or topology mechanism.',
                   'No BUILD, graph modifications, or new ANN Search in R14.']}
    (out/'h32_r14_report.json').write_text(json.dumps(rep,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    lines=['H32-R14 | PAIRWISE PER-QUERY MISS AUDIT (REUSE R11/R13)',
           'OVERALL='+status,'NO BUILD / NO NEW ANN SEARCH / NO GRAPH MODIFICATION',
           'R11_PROVENANCE='+str(r11dir),'R13_PROVENANCE='+str(r13dir),
           'H31_NATIVE_BINARY_PER_QUERY_PARITY=NOT_PROVEN',
           'GT_EXACTNESS=NOT_INDEPENDENTLY_RECOMPUTED','']
    for role in ROLES:
        s=role_stats[role]
        lines.extend([f'[{role}] STRICT_RECALL={s["strict_recall"]:.6f} TIE_AWARE_RECALL={s["tie_aware_recall"]:.6f}',
                      f'  STRICT_MISSED={s["strict_missed"]} REACHABLE_MISSED={s["reachable_missed"]} UNREACHABLE_MISSED={s["unreachable_missed"]}',
                      f'  TIE_CREDIT_HITS={s["tie_credit_hits"]} QUERIES_ANY_STRICT_MISS={s["queries_with_any_strict_miss"]}',
                      f'  MISSED_GT_RANK_HISTOGRAM={s["missed_gt_rank_histogram"]}',''])
    for pair,st in paired.items():
        lines.extend([f'[PAIR {pair}] SAME_SET_QUERIES={st["queries_same_prediction_set"]} SAME_ORDER_QUERIES={st["queries_same_prediction_order"]}',
                      f'  PREDICTION_OVERLAP_MEAN_AT10={st["mean_prediction_overlap_at_10"]:.4f}',
                      f'  STRICT_A_BETTER={st["A_strict_better_queries"]} STRICT_B_BETTER={st["B_strict_better_queries"]} STRICT_EQUAL={st["strict_ties_queries"]}',
                      f'  TIE_A_BETTER={st["A_tie_aware_better_queries"]} TIE_B_BETTER={st["B_tie_aware_better_queries"]} TIE_EQUAL={st["tie_aware_ties_queries"]}',
                      f'  EQUAL_STRICT_HITS_DIFFERENT_PRED_SET={st["queries_equal_strict_gt_hits_but_different_pred_set"]}',''])
    lines.extend(['RESEARCH_DECISION=Use paired-query evidence to decide whether error sets differ; no mechanism attribution without expansion traces.',
                  'NO H33 / NO NOVELTY CLAIM','H32R14_DONE='+str(out)])
    (out/'h32_r14_summary.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('\n'.join(lines))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--mode',choices=('selftest','audit'),required=True)
    ap.add_argument('--root',default='~/ann-task-a')
    a=ap.parse_args()
    try: selftest() if a.mode=='selftest' else audit(Path(a.root))
    except (Failed,KeyError,ValueError,OSError,TypeError,IndexError,struct.error) as ex:
        print('H32R14_FAIL_CLOSED='+str(ex),file=sys.stderr);sys.exit(2)
if __name__=='__main__': main()
