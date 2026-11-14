#!/usr/bin/env python3
"""R86 MS-Turing1M fast-track, source/binary/dataset pinned, safe resumable workflow.

User Ubuntu only; NOT runnable against the 1M files in this ChatGPT container.

Modes:
  --preflight: read-only, validate pins, pilot graphs, capacity and CPU affinity.
  --refine: last fine-beam pass on immutable 1M pilot graphs, v3/v4 scripts.
  --build-all: 3 fresh independent OFF graph builds per 6 arms (18 builds), one
      native process per build, 4 threads, independent isolated run dirs.
  --calibrate-all: 100K-query native Search for both target-recall floors on
      each fresh graph; cautiously increase beam if a new graph falls short.
  --measure-all: 5 independent native Search process repetitions per graph
      per recall floor. Every run has separate log, command, SHA receipt.
  --summarize: read-only summary printed to stdout; no winner asserted.
  --scale-plan: read-only resource + dataset capacity planning for 10M/50M/100M,
      *NOT* permission to run large data or extrapolated proof of feasibility.

No graph/log/receipt overwrite, no deletion, no source edits. One native process
at a time. A0/A1/A2/A3/A4/D0 one-factor controlled arm definitions from the
pinned previous R86 pilot script. Data and evaluator SHA rechecked at invocation.
Every latency quantity 1e6/QPS is throughput-equivalent, NOT per-query p50/p95.
Quality-floor search at first verified passing beam is NOT exact interpolated
matched Recall, and must not be labeled an exact matched-Recall median.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys
sys.dont_write_bytecode = True

HOME = Path.home()
ROOT = HOME / "ann-task-a"
PILOT_SCRIPT = HOME / "Downloads/r86_msturing1m_sixarm_pilot_v1.py"
PILOT_SCRIPT_SHA = "92a4abb8e66d1b0692a3ff8cee7a4e2ea9bff315036dd05cdb0ab7acda695bff"
HIGH_SCRIPT = HOME / "Downloads/r86_msturing1m_highbeam_eval_search_gate_v4.py"
HIGH_SCRIPT_SHA = "0b9eb6a9c3a6a79ae00989d8dd4a7e031132fceda29d2efc66bfa5b8cd61edc8"
V4_BINARY = ROOT / "experiments/R86/msturing_1m_eval/r86_msturing1m_graph_recall_v4_highbeam"
V4_SHA = "bb6576ad3e1e0cc770535aa06355c664993ca70bd1170d6dd4d202ab5767e144"
PILOT_PATH = ROOT / "experiments/R86/msturing_1m_sixarm/pilot_mst1m_v1"
FORMAL = ROOT / "experiments/R86/msturing_1m_sixarm/formal_mst1m_v1"
ARMS = ("A0", "A1", "A2", "A3", "A4", "D0")
TARGETS = (("t0990", .990), ("t0998", .998))
REPS = (1, 2, 3)
SEARCH_REPS = (1, 2, 3, 4, 5)

# First *measured* passing beams from user's 74-point pilot; conservative
# fallbacks if the new independent graph requires additional beam.
START_BEAMS = {
    "A0": (384, 896), "A1": (384, 896), "A2": (768, 2048),
    "A3": (896, 2176), "A4": (896, 2048), "D0": (384, 896)
}
# One last bracketing refinement. CSV groups kept under <=6 beams/v4 call.
REFINE_V4 = (
    ("A0", "832"), ("A1", "832"), ("D0", "832"),
    ("A2", "704,1920"), ("A3", "832,2112"), ("A4", "832,1920")
)
REFINE_V3 = (("A0", "320"), ("A1", "320"), ("D0", "320"))
ROWS_RE = re.compile(r"R72_RECALL_ROW\s+beam=(\d+)\s+recall=([^\s]+)\s+qps=([^\s]+)")
RESOURCE_RE = re.compile(r"R86_MST1M_PILOT_TIME\s+wall_s=([\d.eE+-]+)\s+peak_rss_kib=(\d+)")

def log(s): print(s, flush=True)
def hold(s): raise RuntimeError("R86_MST1M_FASTTRACK_HOLD " + s)

def sha(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(4<<20),b""): h.update(chunk)
    return h.hexdigest()

def checksha(path, expected):
    if not path.is_file(): hold("PIN_FILE_MISSING " + str(path))
    actual=sha(path)
    if actual!=expected: hold(f"PIN_SHA_MISMATCH {path} actual={actual} expected={expected}")
    return actual

def read_json(path):
    if not path.is_file(): hold("JSON_FILE_MISSING " + str(path))
    try: item=json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as e: hold("JSON_INVALID " + str(path) + " " + str(e))
    if not isinstance(item,dict): hold("JSON_NOT_OBJECT "+str(path))
    return item

def write_json_exclusive(path, obj):
    with path.open('x',encoding='utf-8') as f:
        json.dump(obj,f,indent=2,sort_keys=True,ensure_ascii=False)
        f.write('\n')

def ensure_json_same_or_create(path, obj):
    if path.is_file():
        if read_json(path)!=obj: hold("EXISTING_MANIFEST_DIFFERENT " + str(path))
    elif path.exists(): hold("MANIFEST_BAD_FILE_TYPE " + str(path))
    else: write_json_exclusive(path,obj)

def import_pilot():
    checksha(PILOT_SCRIPT,PILOT_SCRIPT_SHA)
    spec=importlib.util.spec_from_file_location("r86_mst1m_original_pilot",PILOT_SCRIPT)
    if spec is None or spec.loader is None: hold("CANNOT_IMPORT_PINNED_PILOT")
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def pilot_receipts(pilot):
    out={}
    for a in ARMS:
        folder=PILOT_PATH/a
        data=read_json(folder/'build_result.json')
        gp=folder/'index.graph'
        if data.get('arm')!=a or data.get('input_sha256')!=pilot.PINS['base'][1] or data.get('native_binary_sha256')!=pilot.PINS[pilot.ARMS[a][0]][1]: hold("PILOT_GRAPH_RECEIPT_INCOMPATIBLE "+a)
        if not gp.is_file() or gp.stat().st_size!=data.get('graph_bytes') or sha(gp)!=data.get('graph_sha256'): hold("PILOT_GRAPH_SHA_FAILED "+a)
        out[a]=data
    return out

def mem_available_gib():
    p=Path('/proc/meminfo')
    if not p.is_file(): return None
    for line in p.read_text().splitlines():
        if line.startswith('MemAvailable:'):
            return float(line.split()[1])/1048576
    return None

def preflight(need_pilot=True):
    if not ROOT.is_dir(): hold("ROOT_MISSING")
    pilot=import_pilot()
    checksha(HIGH_SCRIPT,HIGH_SCRIPT_SHA)
    checksha(V4_BINARY,V4_SHA)
    pilot.preflight(need_resource=False)
    if hasattr(os,'sched_getaffinity') and not {0,2,4,6}.issubset(os.sched_getaffinity(0)):
        hold("CPU_AFFINITY_0_2_4_6_NOT_ALLOWED")
    if need_pilot: pilot_receipts(pilot)
    free=shutil.disk_usage(ROOT).free/1024**3
    mem=mem_available_gib()
    if free<8: hold(f"FREE_DISK_LT_8_GIB free={free:.2f}")
    if mem is not None and mem<7: hold(f"AVAILABLE_RAM_LT_7_GIB available={mem:.2f}")
    log(f"R86_FASTTRACK_PREFLIGHT_PASS_NO_WRITES free_gib={free:.2f} mem_available_gib={mem}")
    return pilot

def command_run(cmd,logfile,env):
    # Do NOT claim output before native process finished and validated.
    with logfile.open('x',encoding='utf-8') as f:
        result=subprocess.run(cmd,env=env,stdout=f,stderr=subprocess.STDOUT,check=False)
    if result.returncode!=0:
        lines=logfile.read_text(errors='replace').splitlines()
        log("\n".join(lines[-30:]))
        hold(f"PROCESS_EXIT_{result.returncode} log={logfile}")
    return logfile.read_text(errors='replace')

def parse_native(text,beam):
    if 'R72_RECALL_INPUT_PASS' not in text or 'R72_RECALL_EVAL_PASS' not in text:
        hold("EVALUATOR_PASS_MARKERS_MISSING")
    rows=ROWS_RE.findall(text)
    if len(rows)!=1 or int(rows[0][0])!=beam: hold("SEARCH_ROW_BEAM_OR_COUNT_MISMATCH")
    recall,qps=map(float,rows[0][1:])
    if not (0<=recall<=1 and math.isfinite(qps) and qps>0): hold("SEARCH_VALUE_INVALID")
    return recall,qps

def refine(pilot):
    pilot_receipts(pilot)
    # Use ORIGINAL, SHA-pinned R86 runner; logs are stored under pilot arm folders.
    todo=[(HIGH_SCRIPT,a,bs,True) for a,bs in REFINE_V4]+[(PILOT_SCRIPT,a,bs,False) for a,bs in REFINE_V3]
    for script,a,bs,high in todo:
        suffix=bs.replace(',','_')
        stem=('search_v4_beams_' if high else 'search_beams_')+suffix
        folder=PILOT_PATH/a
        logfile=folder/(stem+'.log')
        cmdfile=folder/(stem+'_command.json')
        beams=[int(s) for s in bs.split(',')]
        if logfile.exists() or cmdfile.exists():
            if not logfile.is_file() or not cmdfile.is_file(): hold("INCOMPLETE_EXISTING_REFINE_LOG "+str(logfile))
            text=logfile.read_text(errors='replace')
            matches=ROWS_RE.findall(text)
            if 'R72_RECALL_EVAL_PASS' not in text or len(matches)!=len(beams) or [int(m[0]) for m in matches]!=beams: hold("UNVERIFIED_EXISTING_REFINE_LOG "+str(logfile))
            j=read_json(cmdfile)
            if j.get('arm')!=a or j.get('beams')!=beams: hold("REFINE_EXISTING_COMMAND_DIFFERS")
            log(f"R86_FASTTRACK_REFINE_ALREADY_VERIFIED arm={a} beams={bs}")
            continue
        log(f"R86_FASTTRACK_REFINE_START arm={a} beams={bs} evaluator={'v4' if high else 'v3'}")
        subprocess.run([sys.executable,str(script),'--search','--arm',a,'--beams',bs],check=True)
    log("R86_FASTTRACK_LAST_BEAM_REFINE_PASS_EXPERIMENTS_COMPLETE_NOT_FORMAL")

def select_first_measured_pilot_beams(pilot):
    """Quality-floor beams from actual, SHA-locked existing pilot Search logs.

    No interpolation, no 100K-query subsets and no invented values.
    """
    receipts=pilot_receipts(pilot)
    selected={}
    for a in ARMS:
        observed={}
        folder=PILOT_PATH/a
        for logfile in sorted(folder.glob('search*beams_*.log')):
            commandfile=logfile.with_name(logfile.stem+'_command.json')
            if not commandfile.is_file(): hold('UNPAIRED_PILOT_SEARCH_LOG '+str(logfile))
            command=read_json(commandfile)
            if command.get('arm')!=a or command.get('graph_sha256')!=receipts[a]['graph_sha256']:
                hold('PILOT_SEARCH_COMMAND_GRAPH_MISMATCH '+str(commandfile))
            if logfile.name.startswith('search_v4_'):
                if command.get('evaluator_v4_sha256')!=V4_SHA: hold('PILOT_SEARCH_V4_SHA_MISMATCH')
            elif logfile.name.startswith('search_beams_'):
                if command.get('evaluator_sha256')!=pilot.PINS['eval'][1]: hold('PILOT_SEARCH_V3_SHA_MISMATCH')
            else: continue
            text=logfile.read_text(errors='replace')
            if 'R72_RECALL_INPUT_PASS' not in text or 'R72_RECALL_EVAL_PASS' not in text:
                hold('PILOT_SEARCH_LOG_PASS_MISSING '+str(logfile))
            rows=ROWS_RE.findall(text)
            beams=command.get('beams')
            if len(rows)!=len(beams) or [int(x[0]) for x in rows]!=beams:
                hold('PILOT_SEARCH_LOG_ROWS_MISMATCH '+str(logfile))
            for beamstr,recstr,qpsstr in rows:
                beam=int(beamstr);rec=float(recstr);qps=float(qpsstr)
                if not (0<=rec<=1 and qps>0 and math.isfinite(qps)):
                    hold('INVALID_PILOT_SEARCH_VALUE '+str(logfile))
                if beam in observed and abs(observed[beam]-rec)>1e-7:
                    hold('INCONSISTENT_PILOT_RECALL_AT_SAME_BEAM '+a+' '+str(beam))
                observed[beam]=rec
        values=[]
        for tkey,target in TARGETS:
            passes=[beam for beam,rec in observed.items() if rec>=target]
            if not passes: hold('PILOT_TARGET_NOT_MEASURED '+a+' '+tkey)
            values.append(min(passes))
        selected[a]=values
    log('R86_FASTTRACK_PILOT_BEAM_FLOORS '+json.dumps(selected,sort_keys=True))
    return selected


def formal_manifest(pilot,selected_beams=None):
    self_sha=sha(Path(__file__))
    if selected_beams is None: selected_beams=select_first_measured_pilot_beams(pilot)
    return dict(campaign='R86_MSTURING1M_FORMAL_OFF_3X5_V1',version=1,
        script_sha256=self_sha,pilot_script_sha256=PILOT_SCRIPT_SHA,highbeam_script_sha256=HIGH_SCRIPT_SHA,
        dataset_sha256={k:pilot.PINS[k][1] for k in ('base','query','gt')},
        binary_sha256={k:pilot.PINS[k][1] for k in ('stock','h17','d0','eval')},
        evaluator_v4_sha256=V4_SHA,arms=list(ARMS),reps=list(REPS),search_reps=list(SEARCH_REPS),
        cpu_build=[0,2,4,6],cpu_search=0,build_threads=4,search_threads=1,query_count=100000,
        targets={k:t for k,t in TARGETS},start_beams=selected_beams,
        note='3 independent native OFF graph builds/arm, 5 searches/graph/target; quality-floor selected per independent graph. Not exact interpolated matched-Recall; no p95/p99 or NDC. Graphs and logs preserved exclusively.')

def ensure_formal_root(pilot):
    # Once any formal graph exists, beam seeds are frozen in the existing manifest.
    mf=FORMAL/'campaign_manifest.json'
    if mf.exists():
        old=read_json(mf)
        if not isinstance(old.get('start_beams'),dict) or set(old['start_beams'])!=set(ARMS):
            hold('FORMAL_MANIFEST_START_BEAMS_INVALID')
        expected=formal_manifest(pilot,selected_beams=old['start_beams'])
        if old!=expected: hold('FORMAL_MANIFEST_CHANGED_STOP')
        return old
    selected=select_first_measured_pilot_beams(pilot)
    form=formal_manifest(pilot,selected_beams=selected)
    FORMAL.mkdir(parents=True,exist_ok=True)
    ensure_json_same_or_create(mf,form)
    return form

def balanced_builds():
    return [(a,r) for r,order in ((1,ARMS),(2,tuple(reversed(ARMS))),(3,('A2','A3','A4','D0','A0','A1'))) for a in order]

def rep_folder(a,rep): return FORMAL/a/f'r{rep}'

def verify_graph(pilot,a,rep):
    folder=rep_folder(a,rep)
    receipt=read_json(folder/'build_result.json')
    gp=folder/'index.graph'
    if receipt.get('arm')!=a or receipt.get('rep')!=rep or receipt.get('input_sha256')!=pilot.PINS['base'][1] or receipt.get('native_binary_sha256')!=pilot.PINS[pilot.ARMS[a][0]][1]: hold("FORMAL_BUILD_RECEIPT_MISMATCH "+str(folder))
    if not gp.is_file() or gp.stat().st_size!=receipt.get('graph_bytes') or sha(gp)!=receipt.get('graph_sha256'): hold("FORMAL_GRAPH_SHA_OR_SIZE_MISMATCH "+str(gp))
    if not (folder/'native.build.log').is_file(): hold("FORMAL_BUILD_LOG_MISSING "+str(folder))
    return receipt

def build_all(pilot,arms,max_new):
    ensure_formal_root(pilot)
    made=0
    for a,r in balanced_builds():
        if a not in arms: continue
        folder=rep_folder(a,r)
        if folder.exists():
            verify_graph(pilot,a,r)
            log(f'R86_FORMAL_BUILD_SKIP_VERIFIED arm={a} rep={r}')
            continue
        if max_new and made>=max_new: break
        # Safety: bounds checked per build. No parallel process, no deletion.
        free=shutil.disk_usage(ROOT).free/1024**3
        mem=mem_available_gib()
        if free<7 or (mem is not None and mem<7): hold(f'RESOURCE_GATE_DURING_BUILD free_gib={free:.2f} mem_gib={mem}')
        folder.parent.mkdir(parents=True,exist_ok=True)
        folder.mkdir()  # no existing build directory accepted
        gp=folder/'index.graph'
        cmd=pilot.native_build_command(a,gp)
        write_json_exclusive(folder/'build_command.json',dict(arm=a,rep=r,command=cmd,env={'PARLAY_NUM_THREADS':'4'},script_sha256=sha(Path(__file__)),pin_sha256={k:v[1] for k,v in pilot.PINS.items()},status='STARTED_NOT_YET_COMPLETED'))
        log(f'R86_FORMAL_BUILD_START arm={a} rep={r} free_gib={free:.2f}')
        txt=command_run(cmd,folder/'native.build.log',dict(os.environ,PARLAY_NUM_THREADS='4'))
        res=RESOURCE_RE.findall(txt)
        if len(res)!=1: hold('NATIVE_BUILD_TIME_ROW_MISSING '+str(folder))
        wall=float(res[0][0]); peak=int(res[0][1])
        if not gp.is_file() or gp.stat().st_size<1024 or wall<=0 or peak<=0: hold('NATIVE_GRAPH_OR_RESOURCES_INVALID '+str(folder))
        receipt=dict(arm=a,rep=r,graph_path=str(gp),graph_sha256=sha(gp),graph_bytes=gp.stat().st_size,build_wall_s=wall,peak_rss_kib=peak,
                     input_sha256=pilot.PINS['base'][1],native_binary_sha256=pilot.PINS[pilot.ARMS[a][0]][1],
                     build_log_sha256=sha(folder/'native.build.log'),status='FORMAL_INDEPENDENT_NATIVE_OFF_BUILD_EXIT0_SEARCH_PENDING')
        write_json_exclusive(folder/'build_result.json',receipt)
        made+=1
        log(f"R86_FORMAL_BUILD_PASS arm={a} rep={r} wall_s={wall:.4f} rss_kib={peak} graph_sha256={receipt['graph_sha256']} bytes={receipt['graph_bytes']}")
    log(f'R86_FORMAL_BUILD_STAGE_DONE new_builds={made} requested_arms={",".join(arms)} (possibly partial)')

def exec_search_one(pilot,a,rep,beam,logfile):
    receipt=verify_graph(pilot,a,rep)
    evaluator=pilot.PINS['eval'][0] if beam<=512 else V4_BINARY
    evaluator_sha=pilot.PINS['eval'][1] if beam<=512 else V4_SHA
    if beam<10 or beam>4096: hold('BEAM_OUTSIDE_NATIVE_EVALUATOR_CAP')
    cmd=['taskset','-c','0','/usr/bin/time','-f','R86_MST1M_FORMAL_SEARCH_TIME wall_s=%e peak_rss_kib=%M',str(evaluator),str(rep_folder(a,rep)/'index.graph'),
        str(pilot.PINS['base'][0]),str(pilot.PINS['query'][0]),str(pilot.PINS['gt'][0]),str(beam)]
    log(f'R86_FORMAL_SEARCH_START arm={a} rep={rep} beam={beam} log={logfile.name}')
    txt=command_run(cmd,logfile,dict(os.environ,PARLAY_NUM_THREADS='1'))
    recall,qps=parse_native(txt,beam)
    return dict(arm=a,rep=rep,beam=beam,recall_at10=recall,qps=qps,graph_sha256=receipt['graph_sha256'],
                evaluator_sha256=evaluator_sha,command=cmd,source_log=str(logfile),log_sha256=sha(logfile),query_count=100000,
                cpu_search=0,search_threads=1,status='NATIVE_100K_SEARCH_EXIT0_SINGLE_RUN_NOT_P95')

def round32(x): return int(math.ceil(x/32)*32)

def calibrated_beam(pilot,a,r,tkey,target,starting):
    folder=rep_folder(a,r)
    select=folder/f'calibrated_{tkey}.json'
    if select.exists():
        v=read_json(select)
        if v.get('arm')!=a or v.get('rep')!=r or v.get('target')!=target or v.get('beam',0)>4096 or v.get('recall_at10',0)<target: hold('CALIBRATION_SELECTION_INVALID '+str(select))
        return v
    beam=starting
    for attempt in range(10):
        name=f'calib_{tkey}_beam_{beam}'
        logfile=folder/(name+'.log')
        resultfile=folder/(name+'.json')
        if resultfile.exists():
            v=read_json(resultfile)
            if v.get('arm')!=a or v.get('rep')!=r or v.get('beam')!=beam or v.get('target')!=target or not logfile.is_file() or v.get('log_sha256')!=sha(logfile): hold('CALIB_EXISTING_RECEIPT_INVALID')
        else:
            if logfile.exists(): hold('ORPHAN_CALIB_LOG_HOLD '+str(logfile))
            v=exec_search_one(pilot,a,r,beam,logfile)
            v['target']=target
            write_json_exclusive(resultfile,v)
        if v['recall_at10']>=target:
            selected={k:v[k] for k in ('arm','rep','beam','recall_at10','qps','graph_sha256','evaluator_sha256','log_sha256')}
            selected.update(target=target,target_key=tkey,status='QUALITY_FLOOR_PASS_ONE_CALIBRATION_SEARCH_NOT_EXACT_MATCHED')
            write_json_exclusive(select,selected)
            log(f'R86_FORMAL_CALIBRATION_PASS arm={a} rep={r} target={target} beam={beam} recall={v["recall_at10"]:.8f}')
            return selected
        nxt=round32(max(beam+32,beam*1.08))
        if nxt>4096: hold(f'RECALL_TARGET_NOT_REACHED_BY_MAX_BEAM arm={a} rep={r} target={target}')
        log(f'R86_FORMAL_CALIBRATION_BELOW_TARGET arm={a} rep={r} target={target} beam={beam} recall={v["recall_at10"]:.8f} next={nxt}')
        beam=nxt
    hold(f'CALIBRATION_RETRY_LIMIT_REACHED arm={a} rep={r} target={target}')

def calibrate_all(pilot,arms,max_graphs):
    frozen_manifest=ensure_formal_root(pilot)
    made=0
    for a,r in balanced_builds():
        if a not in arms: continue
        folder=rep_folder(a,r)
        if not (folder/'build_result.json').is_file(): hold('FORMAL_BUILD_REQUIRED_BEFORE_CALIBRATION '+str(folder))
        if all((folder/f'calibrated_{tkey}.json').is_file() for tkey,_ in TARGETS):
            verify_graph(pilot,a,r)
            for tkey,target in TARGETS:
                v=read_json(folder/f'calibrated_{tkey}.json')
                if v.get('target')!=target or v.get('recall_at10',0)<target: hold('EXISTING_SELECTED_BEAM_INVALID')
            log(f'R86_FORMAL_CALIBRATION_SKIP_VERIFIED arm={a} rep={r}')
            continue
        if max_graphs and made>=max_graphs: break
        for (tkey,target),start in zip(TARGETS,frozen_manifest['start_beams'][a]): calibrated_beam(pilot,a,r,tkey,target,int(start))
        made+=1
    log(f'R86_FORMAL_CALIBRATION_STAGE_DONE newly_calibrated_graphs={made}')

def measure_all(pilot,arms,max_search):
    ensure_formal_root(pilot)
    completed=0
    # Interleave arms and target processing, alternate target order by Search rep.
    for sr in SEARCH_REPS:
        order=balanced_builds()
        if sr%2==0: order=list(reversed(order))
        for a,r in order:
            if a not in arms: continue
            folder=rep_folder(a,r)
            if not (folder/'build_result.json').is_file(): hold('BUILD_REQUIRED_FOR_MEASURE '+str(folder))
            for tkey,target in (TARGETS if sr%2 else tuple(reversed(TARGETS))):
                select=read_json(folder/f'calibrated_{tkey}.json')
                if select.get('target')!=target or select.get('recall_at10',0)<target: hold('BAD_CALIBRATED_SELECTION '+str(folder))
                beam=int(select['beam'])
                stem=f'measure_{tkey}_s{sr}_beam_{beam}'
                outfile=folder/(stem+'.log')
                resultfile=folder/(stem+'.json')
                if resultfile.exists():
                    v=read_json(resultfile)
                    if v.get('arm')!=a or v.get('rep')!=r or v.get('search_rep')!=sr or v.get('target')!=target or v.get('beam')!=beam or v.get('recall_at10',0)<target or not outfile.is_file() or v.get('log_sha256')!=sha(outfile): hold('MEASURE_EXISTING_RECEIPT_INVALID '+str(resultfile))
                    continue
                if outfile.exists(): hold('ORPHAN_SEARCH_LOG_HOLD '+str(outfile))
                if max_search and completed>=max_search:
                    log(f'R86_FORMAL_SEARCH_PAUSED_AFTER {completed} new native Search processes; invoke --measure-all again to resume')
                    return
                v=exec_search_one(pilot,a,r,beam,outfile)
                v.update(search_rep=sr,target=target,target_key=tkey,status='FORMAL_SEARCH_SINGLE_REP_AT_VERIFIED_RECALL_FLOOR_PASS_NO_PER_QUERY_LATENCY')
                if v['recall_at10']<target: hold('RECALL_FAILED_ON_REPEATED_SEARCH '+str(outfile))
                write_json_exclusive(resultfile,v)
                completed+=1
                log(f'R86_FORMAL_SEARCH_PASS arm={a} rep={r} target={target} search_rep={sr} beam={beam} recall={v["recall_at10"]:.8f} qps={v["qps"]:.3f}')
    log(f'R86_FORMAL_3BUILDS_X_5SEARCH_PER_GRAPH_PER_TARGET_ALL_PASS new_searches={completed}')

def summarize(pilot,arms):
    # All output is printed, no writes and no false formal-PASS on partial work.
    for a in arms:
        builds=[]
        for r in REPS:
            folder=rep_folder(a,r)
            if not (folder/'build_result.json').is_file():
                log(f'R86_FORMAL_SUMMARY_HOLD arm={a} build_rep={r} missing graph');continue
            builds.append(verify_graph(pilot,a,r))
        if len(builds)!=3: continue
        log(f'R86_FORMAL_BUILD_SUMMARY arm={a} n_graphs=3 median_wall_s={statistics.median(x["build_wall_s"] for x in builds):.6f} median_peakRSS_KiB={statistics.median(x["peak_rss_kib"] for x in builds):.0f} graph_bytes_median={statistics.median(x["graph_bytes"] for x in builds):.0f}')
        for tkey,target in TARGETS:
            pergraph=[]
            for r in REPS:
                folder=rep_folder(a,r)
                sfile=folder/f'calibrated_{tkey}.json'
                if not sfile.is_file(): break
                selected=read_json(sfile)
                beam=selected.get('beam'); reps=[]
                for sr in SEARCH_REPS:
                    fp=folder/f'measure_{tkey}_s{sr}_beam_{beam}.json'
                    if not fp.is_file(): break
                    rr=read_json(fp)
                    if rr.get('target')!=target or rr.get('recall_at10',0)<target: hold('SUMMARY_TARGET_OR_RECALL_INCONSISTENCY '+str(fp))
                    reps.append(rr)
                if len(reps)!=5: break
                pergraph.append((r,beam,statistics.median(rr['qps'] for rr in reps),selected['recall_at10']))
            if len(pergraph)!=3:
                log(f'R86_FORMAL_SEARCH_SUMMARY_HOLD arm={a} target={target} complete_graphs={len(pergraph)}/3');continue
            log(f'R86_FORMAL_SEARCH_QUALITY_FLOOR_SUMMARY arm={a} target={target} complete_graphs=3 search_reps_per_graph=5 median_of_three_graph_medQPS={statistics.median(g[2] for g in pergraph):.6f} median_selected_beam={statistics.median(g[1] for g in pergraph):.1f} *NOT_EXACT_INTERPOLATED_MATCHED_RECALL*')
    log('R86_FORMAL_SUMMARY_READ_ONLY_END')

def scale_plan(pilot):
    # Never run larger datasets based on this report. Hardware observations vary.
    sample_bytes={a:read_json(PILOT_PATH/a/'build_result.json')['graph_bytes'] for a in ARMS}
    free=shutil.disk_usage(ROOT).free/1024**3
    mem=mem_available_gib()
    log(f'R86_SCALE_PLAN_RESOURCES_FREE_DISK_GIB={free:.2f} MEM_AVAILABLE_GIB={mem}')
    # Required base is float32 100D, not necessarily the same data distribution.
    for millions in (10,50,100):
        n=millions*1000000
        base_bytes=n*100*4+8
        graph_min=min(sample_bytes.values())*millions
        graph_max=max(sample_bytes.values())*millions
        needed_min=(base_bytes+graph_min)/1024**3
        needed_max=(base_bytes+graph_max)/1024**3
        log(f'R86_SCALE_PLAN_ESTIMATE n={n} base_gib={base_bytes/1024**3:.2f} one_graph_gib_range={graph_min/1024**3:.2f}-{graph_max/1024**3:.2f} minimum_base_plus_one_graph_gib_range={needed_min:.2f}-{needed_max:.2f} FREE_DISK_GIB={free:.2f} MEM_AVAILABLE_GIB={mem} NOT_MEASURED_NOT_AUTHORIZED_FOR_BUILD')
        # RSS extrapolation not safe. Resource feasibility requires actual dataset,
        # source/config pins, disk budget for logs+reps, and 3M/5M scale pilot.
    log('R86_SCALE_PLAN_GATE_HOLD_10M_50M_100M_NATIVE_BUILD_NOT_AUTHORIZED_FROM_1M_EXTRAPOLATION')

def main():
    ap=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawTextHelpFormatter)
    g=ap.add_mutually_exclusive_group(required=True)
    for name in ('preflight','refine','build-all','calibrate-all','measure-all','summarize','scale-plan'):
        g.add_argument('--'+name,action='store_true')
    ap.add_argument('--arms',default=','.join(ARMS),help='Comma-separated subset, order fixed by design')
    ap.add_argument('--max-new-builds',type=int,default=0,help='0 means all remaining builds')
    ap.add_argument('--max-new-graphs',type=int,default=0,help='0 means calibrate all ready graphs')
    ap.add_argument('--max-new-searches',type=int,default=0,help='0 means all remaining Search')
    a=ap.parse_args()
    arms=tuple(a.arms.split(','))
    if not arms or len(set(arms))!=len(arms) or any(x not in ARMS for x in arms): hold('INVALID_ARMS_SUBSET')
    if any(getattr(a,x)<0 for x in ('max_new_builds','max_new_graphs','max_new_searches')): hold('NEGATIVE_MAX')
    pilot=preflight(need_pilot=True)
    if a.preflight: pass
    elif a.refine: refine(pilot)
    elif a.scale_plan: scale_plan(pilot)
    elif a.build_all: build_all(pilot,arms,a.max_new_builds)
    elif a.calibrate_all: calibrate_all(pilot,arms,a.max_new_graphs)
    elif a.measure_all: measure_all(pilot,arms,a.max_new_searches)
    elif a.summarize: summarize(pilot,arms)
    return 0

if __name__=='__main__':
    try: raise SystemExit(main())
    except (OSError,ValueError,KeyError,RuntimeError,subprocess.CalledProcessError) as e:
        print(str(e),file=sys.stderr,flush=True)
        raise SystemExit(2)
