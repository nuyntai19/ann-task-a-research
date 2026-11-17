#!/usr/bin/env bash
# R86 HW85 SIFT100K A0-A4: read-only examination of existing 20 graph builds.
# Writes ONLY a new detached export directory under R86/analysis_exports.
# No graph build, source edit, binary execution, search, or GT claim.
set -Eeuo pipefail
umask 077
RUN_DIR="${1:-$HOME/ann-task-a/experiments/R86/benchmarks/sift100k_a0a4_hw85_7ueCvd}"
[[ -s "$RUN_DIR/runs.csv" && -s "$RUN_DIR/build_only_summary.json" ]] || {
  echo "MISSING_RUNS_CSV_OR_BUILD_ONLY_SUMMARY: $RUN_DIR" >&2; exit 2;
}
command -v python3 >/dev/null || exit 2
EXBASE="$HOME/ann-task-a/experiments/R86/analysis_exports"
mkdir -p "$EXBASE"
EXPORT_DIR="$(mktemp -d "$EXBASE/a0a4_sift100k_postbuild_XXXXXXXX")"
python3 - "$RUN_DIR" "$EXPORT_DIR" <<'PY'
import csv, json, hashlib, math, statistics, sys
from collections import Counter, defaultdict
from pathlib import Path

root = Path(sys.argv[1]).resolve(strict=True)
export = Path(sys.argv[2]).resolve(strict=True)
rows = list(csv.DictReader((root/'runs.csv').open(newline='')))
assert len(rows)==20, f"EXPECTED_20_ROWS_FOUND_{len(rows)}"
assert len({r['run_id'] for r in rows})==20, 'DUPLICATE_RUN_ID'
arms=[('A0','stock',160,1024,2),('A1','h17',160,1024,2),('A2','h17',64,1024,2),('A3','h17',64,512,2),('A4','h17',64,512,1)]
known={name:(binary,c,k,n) for name,binary,c,k,n in arms}
arm_rows=defaultdict(list)
checks=[]
all_counter_records=[]
issues=[]

for row in rows:
    run_id=row['run_id']; label=None
    for arm,(b,c,k,n) in known.items():
        if (row['arm'],int(row['C']),int(row['K']),int(row['N']))==(b,c,k,n):label=arm;break
    assert label, f'UNKNOWN_ARM_CONFIG: {run_id}'
    mode=row['mode']; assert mode in ('off','on')
    arm_rows[label].append(row)
    gp=root/run_id/f'{run_id}.graph'
    log=root/run_id/f'{run_id}.build.log'
    assert gp.is_file() and gp.stat().st_size>0, f'MISSING_GRAPH {gp}'
    assert log.is_file() and log.stat().st_size>0, f'MISSING_LOG {log}'
    h=hashlib.sha256()
    with gp.open('rb') as fd:
        for chunk in iter(lambda:fd.read(1024*1024),b''):h.update(chunk)
    got=h.hexdigest()
    assert got==row['graph_sha256'],f'GRAPH_SHA_MISMATCH {run_id}'
    checks.append(dict(arm=label,run_id=run_id,mode=mode,rep=int(row['rep']),graph_bytes=gp.stat().st_size,
                       graph_sha256=got,wall_s=float(row['wall_s']),peak_rss_KiB=int(row['peak_rss_KiB'])))

for label in known:
    subset=arm_rows[label]
    off=[x for x in subset if x['mode']=='off'];on=[x for x in subset if x['mode']=='on']
    assert len(subset)==4 and len(off)==3 and len(on)==1, f'ARM_COUNTS {label}'
    print(f"ARM {label}: median_OFF_wall={statistics.median(float(r['wall_s']) for r in off):.3f}s "
          f"median_OFF_RSS={statistics.median(int(r['peak_rss_KiB']) for r in off):.0f}KiB "
          f"distinct_graph_SHAs={len(set(r['graph_sha256'] for r in subset))} "
          f"OFF_size_bytes={sorted(set(int(r['graph_bytes']) for r in off))}")

for label,(_,_,_,n_passes) in known.items():
    row=next(r for r in arm_rows[label] if r['mode']=='on')
    run_id=row['run_id']; work=root/run_id
    cf=work/f'{run_id}.counters.jsonl'
    leaf=work/f'{run_id}.leaf_sizes.out'
    occupancy=work/f'{run_id}.occupancy.jsonl'
    assert all(p.is_file() and p.stat().st_size>0 for p in (cf,leaf,occupancy)),f'MISSING_ON_OUTPUTS {label}'
    recs=[json.loads(x) for x in cf.read_text().splitlines() if x.strip()]
    kv={}
    for x in recs:
        key=(int(x['pass_id']),x['depth'],x['metric_code'])
        assert key not in kv,f'DUPLICATE_METRIC_KEY {label}: {key}'
        kv[key]=int(x['observed'])
        all_counter_records.append(dict(run_id=run_id,arm_id=label,pass_id=x['pass_id'],depth=x['depth'],metric_code=x['metric_code'],observed=x['observed'],n=100000))
    leaves=defaultdict(list)
    for line in leaf.read_text().splitlines():
        if not line.strip():continue
        x=json.loads(line); leaves[int(x['pass_id'])].append(int(x['size']))
    occ=[json.loads(x) for x in occupancy.read_text().splitlines() if x.strip()]
    occ_out=[]
    for o in occ:
        n=int(o['n']);cap=int(o['capacity']);hist=o.get('histogram',{})
        if hist:
            freq=sum(int(v) for v in hist.values())
            total=sum(int(k)*int(v) for k,v in hist.items())
            assert freq==n and total==int(o['occupied_slots']),f'OCCUPANCY_HISTOGRAM_INCONSISTENT {label} {o.get("pass_id")}'
        occ_out.append((o.get('pass_id'),o.get('stage'),o.get('mean_occupancy_exact'),o.get('full_nodes')))
    prev=0
    vals=[]
    for p in range(1,n_passes+1):
        ss=leaves[p]
        def metric(code,depth=None):
            key=(p,depth,code)
            assert key in kv,f'MISSING_METRIC {label} {key}'
            return kv[key]
        wp=sum(v for (pid,depth,code),v in kv.items() if pid==p and code=='W_P' and depth is not None)
        wp_cum=int(row['P1_WP_cumulative'] if p==1 else row['P2_WP_cumulative'])
        assert wp==wp_cum-prev,f'W_P_INCONSISTENT {label} pass{p}: {wp}!={wp_cum-prev}'
        prev=wp_cum
        leaf_size_sum=sum(ss)
        total_points=int(row['P1_points'] if p==1 else row['P2_points'])
        buckets=int(row['P1_buckets'] if p==1 else row['P2_buckets'])
        assert len(ss)==buckets and leaf_size_sum==total_points,f'LEAF_COUNTS_INCONSISTENT {label} pass{p}'
        wl=sum(s*s for s in ss)
        assert metric('W_L')==wl,f'W_L_INCONSISTENT {label} pass{p}'
        prop=metric('proposals')
        assert prop==2*leaf_size_sum,f'PROPOSALS_INCONSISTENT {label} pass{p}'
        assert metric('merge_attempts')==2*prop,f'MERGE_ATTEMPTS_INCONSISTENT {label} pass{p}'
        q,ps=metric('top2_q_writes'),metric('partial_sort_calls')
        if label=='A0':
            assert q==sum(s*(s-1) for s in ss) and ps==leaf_size_sum, f'STOCK_TOP2_INVARIANT {label} pass{p}'
        else:
            assert q==0 and ps==0,f'H17_STOCK_PATH_NOT_ZERO {label} pass{p}'
        vals.append(dict(pass_id=p,WP=wp,WL=wl,leaf_total=leaf_size_sum,buckets=buckets,Qwrites=q,partialSortCalls=ps,
                         proposals=prop,merge_attempts=metric('merge_attempts')))
    print('COUNTER_IDENTITIES_PASS',label,json.dumps(vals,separators=(',',':')))
    print('OCCUPANCY',label,json.dumps(occ_out,separators=(',',':')))

with (export/'graph_sha_and_off_times.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(checks[0]));w.writeheader();w.writerows(checks)
with (export/'C_WORK_100K_counter_records.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(all_counter_records[0]));w.writeheader();w.writerows(all_counter_records)
(export/'audit_summary.json').write_text(json.dumps({'source_dir':str(root),'graph_shas_verified':len(checks),
    'counters_raw_rows':len(all_counter_records),'counter_identities':'PASS','search_and_graph_adjacency_audit':'NOT_RUN',
    'warning':'GRAPH_SHA_VARIANCE remains; no independent native graph adjacency audit or matched Recall yet.'},indent=2)+'\n')
print('GRAPH_FILE_SHA_VERIFICATION_PASS',len(checks))
print('COUNTER_IDENTITIES_PASS_ALL_FIVE_100K')
print('GRAPH_ADJACENCY_AND_SEARCH_NOT_RUN')
print('EXPORT_DIR='+str(export))
print('SEND_FILES='+str(export/'audit_summary.json')+' '+str(export/'C_WORK_100K_counter_records.csv'))
PY
