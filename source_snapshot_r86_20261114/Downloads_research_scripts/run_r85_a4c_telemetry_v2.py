#!/usr/bin/env python3
"""R85-A4c: guarded, BUILD-only telemetry wrapper around the proven R85-A4 runner.
Preflight is read-only. --run executes the proven A4 --run-build (six arms x three builds).
A4 dependency checks need six P-core IDs 0,2,4,6,8,10 to remain visible. Actual
native BUILD subprocesses are pinned by A4 itself to only 0,2,4,6.
Do NOT pin the parent A4 Python process to four cores: it would fail dependency
checks before BUILD. Never changes CPU governor or historical A4/A4b outputs.
"""
import argparse, datetime, hashlib, json, os, pathlib, re, shutil, signal, subprocess, sys, threading, time

HOME=pathlib.Path.home()
DEFAULT_RUNNER=HOME/'Downloads/run_r85_a4_paired_sift1m.py'
DEFAULT_OUTPUT=HOME/'ann-task-a/experiments/H85/r85_a4c_telemetry'
OLD_A4=HOME/'ann-task-a/experiments/H85/r85_a4_paired_sift1m/runs_20261111-162423'
OLD_A4B=HOME/'ann-task-a/experiments/H85/r85_a4b_searchonly/runs_20261111-193222'
EXPECTED_ARMS=['STOCK','D0','C64_K1024_N2','C64_K512_N2','C64_K1024_N1','C64_K512_N1']
EXPECTED_RUNNER_SHA256='b9db158b022d9df9633817031282d68e45f7c0ee9236d2b7059aa184d73e3106'
REQUIRED_PARENT_CPUS=(0,2,4,6,8,10)
EXPECTED_NATIVE_BUILD_CPUS=(0,2,4,6)

def command_for_a4(runner):
    # The proven A4 runner pins its native builders internally to 0,2,4,6.
    # Parent must see six P-cores to pass old.check_inputs(); no outer taskset.
    return [sys.executable,'-u',str(runner),'--run-build']


def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()

def read(path,limit=4096):
    try: return pathlib.Path(path).read_text(errors='replace')[:limit].strip()
    except (OSError,PermissionError): return None

def temperatures():
    out=[]
    for p in sorted(pathlib.Path('/sys/class/thermal').glob('thermal_zone*/temp')):
        t=read(p,40); typ=read(p.parent/'type',80)
        try: out.append({'zone':p.parent.name,'type':typ,'c':round(int(t)/1000,2)})
        except (TypeError,ValueError): pass
    for p in sorted(pathlib.Path('/sys/class/hwmon').glob('hwmon*/temp*_input')):
        t=read(p,40); lbl=read(p.with_name(p.name.replace('_input','_label')),80)
        try:out.append({'zone':p.parent.name+'/'+p.name,'type':lbl,'c':round(int(t)/1000,2)})
        except (TypeError,ValueError):pass
    return out

def frequencies(cpus):
    result={}
    for cpu in cpus:
        root=pathlib.Path(f'/sys/devices/system/cpu/cpu{cpu}/cpufreq')
        vals={}
        for f in ('scaling_cur_freq','cpuinfo_cur_freq','scaling_governor','scaling_driver'):
            v=read(root/f,120)
            if v is not None: vals[f]=(round(int(v)/1000,1) if 'freq' in f and v.isdecimal() else v)
        result[str(cpu)]=vals
    return result

def background():
    return {'loadavg':read('/proc/loadavg',200),'meminfo':{k:v for k,v in (line.split(':',1) for line in (read('/proc/meminfo',8000) or '').splitlines() if ':' in line) if k in ('MemAvailable','SwapFree','SwapTotal')},'cpu_pressure':read('/proc/pressure/cpu',400),'memory_pressure':read('/proc/pressure/memory',400)}

def rapl():
    d={}
    for p in pathlib.Path('/sys/class/powercap').glob('intel-rapl*/energy_uj'):
        x=read(p,100)
        if x and x.isdecimal():d[str(p)]={'uj':int(x),'max':read(p.parent/'max_energy_range_uj',100),'name':read(p.parent/'name',100)}
    return d

def cpu_stat_counters(cpus):
    # Raw tick counters (user,nice,system,idle,iowait,irq,softirq,steal,guest,guest_nice).
    # Reconstruct utilization from between-sample deltas; do not treat loadavg as CPU utilization.
    want={f'cpu{c}' for c in cpus}
    result={}
    try:
        with open('/proc/stat','r') as f:
            for line in f:
                parts=line.split()
                if parts and parts[0] in want:
                    result[parts[0]]=[int(x) for x in parts[1:11]]
    except (OSError,ValueError):
        pass
    return result

def throttle_counts(cpus):
    out={}
    for cpu in cpus:
        base=pathlib.Path(f'/sys/devices/system/cpu/cpu{cpu}/thermal_throttle')
        values={}
        for name in ('core_throttle_count','package_throttle_count'):
            value=read(base/name,64)
            if value is not None and value.isdecimal():values[name]=int(value)
        out[str(cpu)]=values
    return out

def cpu_topology(cpus):
    res={}
    for cpu in cpus:
        p=pathlib.Path(f'/sys/devices/system/cpu/cpu{cpu}/topology')
        res[str(cpu)]={'core_id':read(p/'core_id'),'package_id':read(p/'physical_package_id'),'siblings':read(p/'thread_siblings_list')}
    return res

def snapshot(cpus):
    return {'ts_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'monotonic':time.monotonic(),'freq_mhz':frequencies(cpus),'temp':temperatures(),'rapl':rapl(),'cpu_stat':cpu_stat_counters(cpus),'throttle_counts':throttle_counts(cpus),'system':background()}

def check_preflight(runner,cpus,output):
    failures=[]; notes=[]
    if not runner.is_file(): failures.append('Missing proven A4 runner: '+str(runner))
    elif not os.access(runner,os.R_OK):failures.append('Runner unreadable')
    else:
        txt=runner.read_text(errors='replace')
        if '--run-build' not in txt: failures.append('Runner source does not contain --run-build; inspect invocation')
        actual_sha=sha256(runner)
        if actual_sha!=EXPECTED_RUNNER_SHA256:
            failures.append('A4 runner SHA256 drift: expected '+EXPECTED_RUNNER_SHA256+' observed '+actual_sha)
        # Source checks in addition to SHA pin. Avoid invoking A4 code during preflight.
        if not re.search(r'BUILD_CPUS\s*=\s*\(0\s*,\s*2\s*,\s*4\s*,\s*6\s*\)', txt):
            failures.append('A4 runner does not declare native BUILD_CPUS=(0,2,4,6)')
        if not re.search(r"cmd\s*=\s*\['taskset'",txt):
            failures.append('A4 runner internal taskset not found; refuse BUILD')
        if 'A4' not in txt.upper():notes.append('Runner name/source lacks A4 marker; verify provenance')
    for cpu in cpus:
        if not pathlib.Path(f'/sys/devices/system/cpu/cpu{cpu}').exists(): failures.append(f'CPU {cpu} absent')
    allowed=None
    try:allowed=sorted(os.sched_getaffinity(0))
    except Exception:notes.append('CPU affinity visibility unavailable')
    if allowed is not None and not set(cpus).issubset(allowed):failures.append(f'Chosen CPUs {cpus} not in allowed affinity {allowed}')
    if allowed is not None and not set(REQUIRED_PARENT_CPUS).issubset(allowed):
        failures.append(f'Parent must see six P-cores {REQUIRED_PARENT_CPUS} for A4 dep(): missing {sorted(set(REQUIRED_PARENT_CPUS)-set(allowed))}')
    if tuple(cpus)!=EXPECTED_NATIVE_BUILD_CPUS:
        failures.append('Use exactly native BUILD_CPUS 0,2,4,6 to match historical A4 protocol')
    if not shutil.which('taskset'): failures.append('Missing taskset required by A4 native builder')
    topo=cpu_topology(cpus)
    identities=[(x['package_id'],x['core_id']) for x in topo.values()]
    if None in [v for pair in identities for v in pair]: notes.append('CPU core topology partially unknown')
    elif len(set(identities))!=len(identities):failures.append('Chosen logical CPUs share a physical core')
    if runner.resolve() in (OLD_A4,OLD_A4B):failures.append('Invalid runner path')
    if output.resolve() in (OLD_A4.resolve(),OLD_A4B.resolve()):failures.append('Output overlaps historical experiment')
    if not OLD_A4.is_dir():notes.append('Historical A4 run directory not found (not required for new builds)')
    if not OLD_A4B.is_dir():notes.append('Historical A4b run directory not found (not required for new builds)')
    return {'status':'PASS' if not failures else 'BLOCKED','runner':str(runner),'runner_sha256':sha256(runner) if runner.is_file() else None,'cpus':cpus,'parent_required_cpus':list(REQUIRED_PARENT_CPUS),'native_build_cpus':list(EXPECTED_NATIVE_BUILD_CPUS),'topology':topo,'allowed_affinity':allowed,'output':str(output),'existing_a4':OLD_A4.is_dir(),'existing_a4b':OLD_A4B.is_dir(),'failures':failures,'notes':notes,'pre_snapshot':snapshot(cpus)}

def atomic_json(path,data):
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2,default=str)+'\n')
    os.replace(tmp,path)

def run(args,pre):
    base=args.output.expanduser().resolve()
    if base.exists() and not base.is_dir():raise RuntimeError('Output exists and is not a directory')
    base.mkdir(parents=True,exist_ok=True)
    # Unique run directory: never reuse or overwrite.
    stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    session=base/('session_'+stamp+'_'+str(os.getpid()))
    session.mkdir(exist_ok=False)
    atomic_json(session/'preflight.json',pre)
    command=command_for_a4(args.runner)
    if not shutil.which('taskset'):raise RuntimeError('taskset not installed')
    atomic_json(session/'command.json',{'argv':command,'cwd':str(HOME),'PARLAY_NUM_THREADS':'4','start_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'run_scope':'A4 six arms x 3 BUILD, no SEARCH; A4 runner owns build artifacts', 'native_cpu_pinning':'internal A4 taskset 0,2,4,6', 'parent_required_cpus':list(REQUIRED_PARENT_CPUS)})
    print('R85_A4C_SESSION',session,flush=True)
    print('R85_A4C_COMMAND',' '.join(command),flush=True)
    print('R85_A4C_NOTE A4 parent sees all 6 P-core IDs; native BUILD is pinned by original A4 to 0,2,4,6.',flush=True)
    env=os.environ.copy();env['PARLAY_NUM_THREADS']='4'
    stop=threading.Event();counts={'samples':0}
    def monitor():
        with (session/'telemetry.jsonl').open('w') as f:
            while not stop.is_set():
                f.write(json.dumps(snapshot(args.cpus),ensure_ascii=False)+'\n');f.flush();counts['samples']+=1
                stop.wait(args.interval)
    th=threading.Thread(target=monitor,daemon=True);th.start()
    started=time.monotonic();code=None
    try:
        with (session/'build.log').open('w') as f, (session/'events.jsonl').open('w') as events:
            process=subprocess.Popen(command,cwd=HOME,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1,start_new_session=True)
            try:
                for line in process.stdout:
                    print(line,end='',flush=True);f.write(line);f.flush()
                    if any(marker in line for marker in ('R85_A4_BUILD_START','R85_A4_BUILD_PASS','R85_A4_FAIL_CLOSED','R85_A4_ALL_18_BUILDS_PASS','R85_A4_RESULTS_DIR')):
                        events.write(json.dumps({'monotonic':time.monotonic(),
                                                 'ts_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                                 'line':line.strip()},ensure_ascii=False)+'\n')
                        events.flush()
                code=process.wait()
            except KeyboardInterrupt:
                os.killpg(process.pid,signal.SIGINT)
                code=process.wait(timeout=15)
                raise
    finally:
        stop.set();th.join(timeout=args.interval+2)
        text=(session/'build.log').read_text(errors='replace') if (session/'build.log').exists() else ''
        hits=re.findall(r'R85_A4_BUILD_PASS\s+(\S+).*?wall_s=([0-9.]+)\s+rss_kib=(\d+)\s+arcs=(\d+)',text)
        summary={'exit_code':code,'elapsed_s':round(time.monotonic()-started,3),'telemetry_samples':counts['samples'],'observed_builds':len(hits),'observed_arms':sorted(set(re.sub(r'^t\d+_r\d+_','',x[0]) for x in hits)),'build_records':[{'tag':a,'wall_s':float(b),'rss_kib':int(c),'arcs':int(d)} for a,b,c,d in hits],'all_builds_pass':('R85_A4_ALL_18_BUILDS_PASS' in text),'end_snapshot':snapshot(args.cpus),'note':'BUILD only, no per-graph latency measurement. Historical A4 scripts and artifacts preserved.'}
        atomic_json(session/'result.json',summary)
        print('R85_A4C_RESULT',session/'result.json',flush=True)
        print('R85_A4C_BUILD_SUCCESS' if code==0 and summary['all_builds_pass'] and len(hits)==18 else 'R85_A4C_NEEDS_REVIEW',flush=True)
    return 0 if code==0 and summary['all_builds_pass'] and len(hits)==18 else 2

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    modes=ap.add_mutually_exclusive_group(required=True)
    modes.add_argument('--preflight',action='store_true',help='read-only preflight, NO BUILD')
    modes.add_argument('--selftest',action='store_true',help='static regression check; NO BUILD')
    modes.add_argument('--run',action='store_true',help='execute proven A4 --run-build and capture Linux telemetry')
    ap.add_argument('--runner',type=pathlib.Path,default=DEFAULT_RUNNER)
    ap.add_argument('--output',type=pathlib.Path,default=DEFAULT_OUTPUT)
    ap.add_argument('--cpus',default='0,2,4,6',help='four distinct physical cores')
    ap.add_argument('--interval',type=float,default=1.0)
    ap.add_argument('--confirm-build',action='store_true',help='required for --run')
    args=ap.parse_args()
    if args.selftest:
        z=command_for_a4(pathlib.Path('/tmp/fake_a4.py'))
        assert z==[sys.executable,'-u','/tmp/fake_a4.py','--run-build']
        assert z[0]!='taskset' and EXPECTED_NATIVE_BUILD_CPUS==(0,2,4,6)
        assert REQUIRED_PARENT_CPUS==(0,2,4,6,8,10)
        print('R85_A4C_V2_SELFTEST_PASS_NO_BUILD');return 0
    try:args.cpus=[int(x) for x in args.cpus.split(',')]
    except ValueError:ap.error('invalid CPU list')
    if len(args.cpus)!=4 or len(set(args.cpus))!=4:ap.error('expected four distinct logical CPUs')
    if args.interval<0.2:ap.error('interval >=0.2s')
    pre=check_preflight(args.runner,args.cpus,args.output)
    print('R85_A4C_PREFLIGHT_REPORT',json.dumps(pre,ensure_ascii=False,indent=2),flush=True)
    if pre['status']!='PASS':return 2
    if args.preflight:
        print('R85_A4C_PREFLIGHT_PASS_READ_ONLY_NO_BUILD',flush=True);return 0
    if not args.confirm_build:ap.error('--run requires --confirm-build')
    return run(args,pre)

if __name__=='__main__':sys.exit(main())
