#!/usr/bin/env python3
"""R90-P3.1 — strictly read-only audit of P2.2/P2.3 Recall-QPS interpolation and P3 work.

Reads pinned native result_manifest.json and original native sweep stdout logs;
checks SHA and rows, then reports interpolated QPS at Recall 0.990/.998.
NO code modification, ANN BUILD, graph writes, Search runs or filesystem output.

The interpolation is exploratory: QPS at each bracket beam comes from ONE sweep
run per graph, even though repeated quality-floor runs exist separately.
"""
from __future__ import annotations
import argparse, hashlib, json, math, re, statistics
from pathlib import Path

ROOT = Path.home() / 'ann-task-a/experiments/R90'
D21 = ROOT / 'r90_p2_sift100k_pass2_value_gate1_v1'
D22 = ROOT / 'r90_p22_sift100k_10kq_floor_v1'
D23 = ROOT / 'r90_p23_sift100k_a5_qgrid_v1'
D3  = ROOT / 'r90_p3_rect_work_probe_v1'
BEAMS = [40,48,56,64,72,80,88,96,104,112,128,144,160,176,192,224,256,320]
TARGETS = (0.990,0.998)
ARMS = ('stock_N1','stock_N2','a5_gate_q0p5_N2',
        'a5_gate_q001_N2','a5_gate_q2_N2','a5_gate_q5_N2')
NEW_ARMS = frozenset(('a5_gate_q0p5_N2','a5_gate_q2_N2','a5_gate_q5_N2'))
RX = re.compile(r'^R72_RECALL_ROW beam=(\d+) recall=([0-9.]+) qps=([0-9.]+) avg_cmps=([0-9.]+) avg_visited=([0-9.]+)\s*$',re.M)

def ck(cond,msg):
    if not cond: raise RuntimeError('R90_P31_HOLD_'+msg)

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024), b''): h.update(b)
    return h.hexdigest()

def manifest(folder,status):
    file=folder/'result_manifest.json'
    ck(file.is_file(),'MISSING_MANIFEST_'+folder.name)
    v=json.loads(file.read_text())
    ck(v.get('status')==status,'BAD_STATUS_'+folder.name)
    return v

def verify_log(r,dir_):
    p=Path(r['log_path'])
    ck(p.is_file() and p.parent.resolve()==(dir_/'logs').resolve(),'MISSING_OR_WRONG_LOG_'+dir_.name)
    ck(sha(p)==r['log_sha256'],'LOG_SHA_'+p.name)
    data=p.read_text(errors='replace')
    ck(data.count('R72_RECALL_EVAL_PASS')==1,'MISSING_EVAL_PASS_'+p.name)
    entries=RX.findall(data)
    rows=[dict(beam=int(a),recall=float(b),qps=float(c),avg_cmps=float(d),avg_visited=float(e)) for a,b,c,d,e in entries]
    ck([z['beam'] for z in rows]==BEAMS,'BAD_BEAMS_'+p.name)
    ck(len(rows)==len(r['rows']),'BAD_ROWS_'+p.name)
    for a,b in zip(rows,r['rows']):
        ck(a['beam']==b['beam'] and all(math.isclose(a[key],b[key],abs_tol=1e-8,rel_tol=1e-8)
                for key in ('recall','qps','avg_cmps','avg_visited')),'PARSED_CONTENT_'+p.name)
    ck(all(0 <= a['recall'] <= 1 and a['qps'] > 0 for a in rows),'ROW_VALUES_'+p.name)
    return rows

def crossing(rows,target):
    """Interpolate against recall within the *first* adjacent sampled crossing.
    QPS-linear and latency-linear are both reported for sensitivity.
    """
    for i,r in enumerate(rows):
        if r['recall'] == target:
            return dict(b0=r['beam'],b1=r['beam'],r0=r['recall'],r1=r['recall'],
                        qps_linear=r['qps'],qps_latency=r['qps'],q0=r['qps'],q1=r['qps'])
        if r['recall'] > target and i > 0 and rows[i-1]['recall'] < target:
            a=rows[i-1];b=r
            t=(target-a['recall'])/(b['recall']-a['recall'])
            qps_linear=a['qps']+t*(b['qps']-a['qps'])
            latency_us=(1-t)*1e6/a['qps']+t*1e6/b['qps']
            return dict(b0=a['beam'],b1=b['beam'],r0=a['recall'],r1=b['recall'],
                        qps_linear=qps_linear,qps_latency=1e6/latency_us,q0=a['qps'],q1=b['qps'])
    return None

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['selftest','audit'])
    args=p.parse_args()
    if args.mode=='selftest':
        x=[dict(beam=40,recall=.98,qps=20000),dict(beam=48,recall=.994,qps=10000)]
        t=crossing(x,.990)
        ck(t['b0']==40 and t['b1']==48 and 10000<t['qps_latency']<20000,'SELFTEST_INTERPOLATION')
        ck(crossing(x,.998) is None,'SELFTEST_UNREACHED')
        print('R90_P31_SELFTEST_PASS_READONLY_BRACKET_AND_INTERPOLATION')
        return
    a=manifest(D21,'NATIVE_SCREEN_COMPLETED')
    b=manifest(D22,'COMPLETE')
    c=manifest(D23,'COMPLETE')
    d=manifest(D3,'NATIVE_DIAGNOSTIC_COMPLETE')
    builds={t['arm']:t for t in a['builds']}
    builds.update({t['arm']:t for t in c['builds']})
    ck(len(a['builds'])==4 and len(c['builds'])==3,'BUILD_REPS')
    ck(set(ARMS) <= set(builds),'MISSING_BUILDS')
    ck(b['graphs_sha256']['stock_N2']==b['graphs_sha256']['a5_dryrun_q001_N2'],'DRYRUN_GRAPH_SHA')
    for arm in ARMS:
        entry=builds[arm]
        graph=Path(entry['graph_path'])
        ck(graph.is_file() and sha(graph)==entry['graph_sha256'],'GRAPH_SHA_'+arm)
        if arm not in NEW_ARMS:
            ck(entry['graph_sha256']==b['graphs_sha256'][arm],'GRAPH_AGAINST_P22_'+arm)
    src=D3/'source/algorithms/PipNN/pipnn.h'
    exe=D3/'build/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'
    ck(src.is_file() and sha(src)==d['patched_source_sha256'],'P3_PATCHED_SOURCE_SHA')
    ck(exe.is_file() and sha(exe)==d['diagnostic_elf_sha256'],'P3_DIAGNOSTIC_ELF_SHA')
    runmap={}
    for arm in ARMS:
        parent,folder=(c,D23) if arm in NEW_ARMS else (b,D22)
        hits=[r for r in parent['runs'] if r.get('arm')==arm and r.get('phase')=='sweep']
        ck(len(hits)==1,'MISSING_OR_DUP_SWEEP_'+arm)
        runmap[arm]=verify_log(hits[0],folder)
    print('R90_P31_NATIVE_SWEEP_SOURCE_AND_LOG_SHA_PARITY_PASS')
    all_r={}
    for target in TARGETS:
        print('\n=== INTERPOLATED RECALL',f'{target:.3f}','===')
        for arm in ARMS:
            z=crossing(runmap[arm],target)
            ck(z is not None,'NO_RECALL_CROSSING_'+arm+'_'+str(target))
            bld=builds[arm].get('build_wall_s',builds[arm].get('wall_s_external_including_output'))
            ck(bld is not None,'BUILD_WALL_MISSING_'+arm)
            z['build_s']=bld
            all_r[(arm,target)]=z
            monotonic=all(v['recall']<=w['recall']+1e-8 for v,w in zip(runmap[arm],runmap[arm][1:]))
            print(f'{arm:22s} BUILD={bld:7.3f}s bracket={z["b0"]:3d}-{z["b1"]:3d} '
                  f'R=({z["r0"]:.8f},{z["r1"]:.8f}) '
                  f'QPS_interp_direct={z["qps_linear"]:10.2f} '
                  f'QPS_interp_latency={z["qps_latency"]:10.2f} '
                  f'sweep_recall_monotone={monotonic}')
        n1=all_r[('stock_N1',target)]
        n2=all_r[('stock_N2',target)]
        print('--- Relative to Stock N2 and N1-to-N2 build/QPS chord ---')
        for arm in ARMS:
            if not arm.startswith('a5_gate'): continue
            z=all_r[(arm,target)]
            w=(z['build_s']-n1['build_s'])/(n2['build_s']-n1['build_s'])
            line=n1['qps_latency']+w*(n2['qps_latency']-n1['qps_latency'])
            pct_vs_n2=100*(z['qps_latency']/n2['qps_latency']-1)
            pct_vs_line=100*(z['qps_latency']/line-1)
            print(f'{arm:22s} vs_N2={pct_vs_n2:+8.3f}% vs_build_QPS_chord={pct_vs_line:+8.3f}% '
                  f'NOT_A_FORMAL_MATCHED_RECALL_CLAIM')
    ck(len(d['rows'])==4,'P3_ROWS')
    print('\n=== P3 RECTANGULAR PAIR PROXY ===')
    for row in d['rows']:
        tri=row['triangle_pairs'];rect=row['rectangular_pairs']
        ck(tri>0 and rect>=0,'P3_PAIR_COUNTER')
        calc=100*rect/tri
        ck(math.isclose(calc,row['rectangular_to_triangle_pct'],abs_tol=1e-10),'P3_RECT_RATIO')
        ck(Path(row['stdout_path']).is_file() and sha(row['stdout_path'])==row['stdout_sha256'],'P3_STDOUT_SHA_'+row['tag'])
        print(f'q={row["fraction"]:.4f} rect/tri={calc:.4f}% '
              f'Q_occ={row["selected_member_occurrences"]} total_occ={row["leaf_member_occurrences"]} '
              'PROXY_ONLY_NOT_BUILD_SPEEDUP')
    print('\nR90_P31_READONLY_AUDIT_PASS_NO_GRAPH_BUILD_OR_SEARCH_NO_WRITES')
    print('LIMITATION: bracket QPS derived from ONE 18-beam sweep per graph; '\
          'interpolation model, time noise and single build/seed must be validated before claims.')

if __name__=='__main__':
    try:main()
    except Exception as e:
        print('R90_P31_HOLD',type(e).__name__,str(e))
        raise SystemExit(2)
