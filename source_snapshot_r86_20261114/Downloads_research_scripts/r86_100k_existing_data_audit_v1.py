#!/usr/bin/env python3
"""R86 SIFT100K existing-evidence collector (READ ONLY for experiment directories).

Reads 15 pinned OFF native graphs/build logs plus five ON occupancy artifacts.
Writes reviewable CSV/JSON and a tar.gz only to an isolated NEW results directory.
It does NOT build an index, modify source, or claim native phase timers are verified.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, re, shutil, struct, tarfile
from datetime import datetime, timezone
from pathlib import Path

ARMS = (
    ("A0", "stock_C160_K1024_N2", 160, 2),
    ("A1", "h17_C160_K1024_N2", 160, 2),
    ("A2", "h17_C64_K1024_N2", 64, 2),
    ("A3", "h17_C64_K512_N2", 64, 2),
    ("A4", "h17_C64_K512_N1", 64, 1),
)
GRAPH_SHA = {
"stock_C160_K1024_N2_off_r1":"f1727131d7427c4132ed48468c026f97f09e0b5fe7d94a56d26f4a46c0885978",
"stock_C160_K1024_N2_off_r2":"02c1ff2104309a59e7bb51016966a2e847aa1913e39c99f8010b8acca787d909",
"stock_C160_K1024_N2_off_r3":"57252481ace67e1fb9e6c55c223e3e01b707cb5898744519c4b136cd4e5d7877",
"h17_C160_K1024_N2_off_r1":"18809c747d38ee1dfa26053bb6b3650dd0adf26f798ef47a0f6250e81530d841",
"h17_C160_K1024_N2_off_r2":"5bae9f4eff8b05eb5f0ed521d2044ce80601cfd620741a01da13fcdfbbc67f92",
"h17_C160_K1024_N2_off_r3":"a40f45b31954ac483133b807ce7e1591e5d76fd34fa6638ebc28ce29c53948f6",
"h17_C64_K1024_N2_off_r1":"3ae4f18205c2841f0045e94d006dc6dda15357554f789610bafcb8b6e58cb4d1",
"h17_C64_K1024_N2_off_r2":"2606931d8c07234a157b5d151381e9b46b067c6e91ed016847869d2d2b85ce2b",
"h17_C64_K1024_N2_off_r3":"5f4853c48efeeacfe2dd447169975c2bef6a8b804d4bebddabc49062a7402d45",
"h17_C64_K512_N2_off_r1":"2311777f6c807410bac87669c297a8ff247960d4f8583bb63c29eaea0458c1c4",
"h17_C64_K512_N2_off_r2":"13c117fcecdb02b9b55f53280da3621ee68cc6f9dea5095e71e54bb247e0f731",
"h17_C64_K512_N2_off_r3":"096ad8491d70c8357d8540b76b086ae16f89c59cde7048d00b5c2f1a50678691",
"h17_C64_K512_N1_off_r1":"aa7234e667ddfb3f681fccaa78ec8eeb7304f76e0d25cfd45ee640c9ddbe4b5b",
"h17_C64_K512_N1_off_r2":"5872d07e3b4d737f20227cc0496ba2608ed1ca4ea35d7640184c4bab6a86b0f9",
"h17_C64_K512_N1_off_r3":"d4f312f54f1cb0e1a0bc28f3899b358986ee5d4053e67cc57b48486abf300202",
}
# Capture native printed timing lines verbatim, never assume its units or boundaries.
PHASE_LABELS=(('T_partition_candidate','buckets time'),('T_leaf_candidate','build leaf time'),('T_prune_candidate','final prune time'))
NUMBER=re.compile(r'(?<![A-Za-z0-9_.])(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)(?:[eE][-+]?[0-9]+)?')

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def csv_out(path,headers,rows):
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=headers,extrasaction='ignore');w.writeheader();w.writerows(rows)

def find_one(folder,pattern,explicit=None):
    exact=folder/explicit if explicit else None
    if exact is not None and exact.is_file():return exact
    hits=[p for p in folder.glob(pattern) if p.is_file()]
    return hits[0] if len(hits)==1 else None

def phase_lines(text,run_id):
    result=[]
    for lineno,line in enumerate(text.splitlines(),1):
        for key,label in PHASE_LABELS:
            pos=line.lower().find(label)
            if pos<0:continue
            tail=line[pos+len(label):]
            match=NUMBER.search(tail)
            value=float(match.group()) if match else None
            result.append(dict(run_id=run_id,line_no=lineno,metric_candidate=key,printed_number=value,raw_line=line.strip()[:2000]))
    return result

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root',type=Path,default=Path.home()/'ann-task-a')
    ap.add_argument('--out',type=Path)
    ap.add_argument('--max-copy-bytes',type=int,default=12_000_000)
    args=ap.parse_args()
    root=args.root.expanduser().resolve()
    bench=root/'experiments/R86/benchmarks/sift100k_a0a4_hw85_7ueCvd'
    home=root/'00_PROJECT_HOME/05_RESULTS_AND_COUNTERS'
    out=(args.out or home/'R86_SIFT100K_EXISTING_EVIDENCE_AUDIT_v1_0').expanduser().resolve()
    if not bench.is_dir():raise RuntimeError('BENCH_DIRECTORY_MISSING: '+str(bench))
    if out.exists():raise RuntimeError('OUTPUT_ALREADY_EXISTS_NO_OVERWRITE: '+str(out))
    # Fail closed if output is inside benchmark runs or source directories.
    if out==bench or bench in out.parents or out==root or out==root/'experiments':
        raise RuntimeError('UNSAFE_OUTPUT_PATH')
    out.mkdir(parents=True,exist_ok=False)
    (out/'source_logs').mkdir();(out/'occupancy_files').mkdir()
    graphs=[];phase=[];occs=[];issues=[];count_pass=0
    for arm,tag,C,N in ARMS:
        for rep in (1,2,3):
            name=f'{tag}_off_r{rep}';folder=bench/name
            graph=folder/(name+'.graph')
            logfile=find_one(folder,'*.build.log',name+'.build.log')
            if not graph.is_file():issues.append(f'GRAPH_MISSING {name}');continue
            with graph.open('rb') as f:header=f.read(8)
            actual=sha(graph)
            good=(len(header)==8 and struct.unpack('<II',header)==(100000,64) and actual==GRAPH_SHA[name])
            if not good:issues.append(f'GRAPH_SHA_OR_HEADER_HOLD {name}: {actual}');continue
            count_pass+=1
            row=dict(arm=arm,run_id=name,rep=rep,n=100000,C=C,N=N,graph_bytes=graph.stat().st_size,
                    graph_sha256=actual,model_slot_bytes=8,M_reservoir_model_B=8*100000*(C+1),
                    build_log_present=int(logfile is not None),phase_status='LOG_MISSING',
                    T_partition_candidate_s='',T_leaf_candidate_s='',T_prune_candidate_s='',
                    graph_file=str(graph),build_log=str(logfile) if logfile else '')
            if logfile:
                content=logfile.read_text(errors='replace')
                lines=phase_lines(content,name);phase.extend(lines)
                groups={key:[z['printed_number'] for z in lines if z['metric_candidate']==key] for key,_ in PHASE_LABELS}
                for metric,values in groups.items():
                    row[metric+'_line_count']=len(values)
                ok=all(len(groups[k])==(N if k!='T_prune_candidate' else 1) and all(v is not None and v>=0 for v in groups[k]) for k,_ in PHASE_LABELS)
                if ok:
                    row['T_partition_candidate_s']=sum(groups['T_partition_candidate'])
                    row['T_leaf_candidate_s']=sum(groups['T_leaf_candidate'])
                    row['T_prune_candidate_s']=groups['T_prune_candidate'][0]
                    row['phase_status']='PHASE_LINES_COUNT_PASS_SEMANTICS_UNVERIFIED'
                else:
                    row['phase_status']='PHASE_LINES_HOLD_INSPECT_RAW'
                    issues.append(f'PHASE_HOLD {name} counts={ {k:len(v) for k,v in groups.items()} }')
                if logfile.stat().st_size<=args.max_copy_bytes:
                    shutil.copy2(logfile,out/'source_logs'/(name+'.build.log'))
                else:issues.append(f'LOG_TOO_LARGE_FOR_ARCHIVE {name}')
            else:issues.append(f'BUILD_LOG_MISSING {name}')
            graphs.append(row)
        on_name=f'{tag}_on_r1'; on_dir=bench/on_name
        if not on_dir.is_dir():issues.append(f'ON_RUN_MISSING {on_name}');continue
        candidates=[p for p in on_dir.iterdir() if p.is_file() and ('occupancy' in p.name.lower())]
        if not candidates:issues.append(f'OCCUPANCY_FILE_MISSING {on_name}')
        for p in candidates:
            oc=dict(arm=arm,run_id=on_name,file_path=str(p),filename=p.name,file_bytes=p.stat().st_size,
                    sha256=sha(p),copied_to_evidence=False,source='ON build; NOT OFF phase time')
            if p.stat().st_size<=args.max_copy_bytes:
                dest=out/'occupancy_files'/f'{on_name}__{p.name}'
                shutil.copy2(p,dest);oc['copied_to_evidence']=True
            else:issues.append(f'OCCUPANCY_TOO_LARGE_FOR_ARCHIVE {p}')
            occs.append(oc)
    graph_fields=['arm','run_id','rep','n','C','N','graph_bytes','graph_sha256','model_slot_bytes','M_reservoir_model_B','build_log_present','phase_status','T_partition_candidate_s','T_leaf_candidate_s','T_prune_candidate_s','T_partition_candidate_line_count','T_leaf_candidate_line_count','T_prune_candidate_line_count','graph_file','build_log']
    csv_out(out/'A_SYSTEM_candidate_rows.csv',graph_fields,graphs)
    csv_out(out/'native_phase_stdout_lines.csv',['run_id','line_no','metric_candidate','printed_number','raw_line'],phase)
    csv_out(out/'occupancy_artifacts.csv',['arm','run_id','file_path','filename','file_bytes','sha256','copied_to_evidence','source'],occs)
    (out/'audit_issues.txt').write_text(('\n'.join(issues) if issues else 'NONE')+'\n')
    summary=dict(created_utc=datetime.now(timezone.utc).isoformat(),graph_sha_pinned_pass=count_pass,graphs_total=len(graphs),
      phase_pass=sum(x['phase_status']=='PHASE_LINES_COUNT_PASS_SEMANTICS_UNVERIFIED' for x in graphs),
      copied_occupancy=len([x for x in occs if x['copied_to_evidence']]),issues=issues,
      model_note='M_model = 8*n*(C+1) is a theoretical flat-slot capacity, not allocations/RSS',
      timing_note='Candidate values from native printed lines; verify time units, phase scope, and whether pass timings are wall-clock before importing.',
      graph_note='graph_bytes is serialized native saved graph file size, not in-memory index allocations')
    (out/'audit_summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n')
    archive=out.parent/(out.name+'_EVIDENCE.tar.gz')
    if archive.exists():raise RuntimeError('ARCHIVE_ALREADY_EXISTS_NO_OVERWRITE: '+str(archive))
    with tarfile.open(archive,'w:gz') as f:f.add(out,arcname=out.name)
    print('R86_100K_READ_ONLY_COLLECT_DONE')
    print('GRAPH_SHA_PASS',count_pass,'/15')
    print('OFF_PHASE_CANDIDATE_COUNT_PASS',summary['phase_pass'],'/15','SEMANTICS_NEED_AUDIT')
    print('ON_OCCUPANCY_FILES_FOUND',len(occs))
    print('ISSUES',len(issues))
    for s in issues[:15]:print('ISSUE',s)
    print('OUTPUT',out)
    print('ARCHIVE',archive)
    print('ARCHIVE_SHA256',sha(archive))
    print('NO_BUILD_NO_SOURCE_EDITS')

if __name__=='__main__':
    try:main()
    except Exception as e:
        print('R86_100K_EVIDENCE_COLLECT_HOLD',str(e));raise SystemExit(1)
