#!/usr/bin/env python3
"""R83.10 SEARCH-only quality on six saved R83.9 new-PC SIFT100K graphs.

Reuses verified historical R83.8 v3 parser/evaluator. No ANN BUILD, source
patch, existing result overwrite, or git operation. 300 heldout queries,
fixed R70 beam protocol 10/20/40/80/160. Research screening only.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from datetime import datetime, timezone

OLD_HELPER_SHA = '84c213fa1d89015ee5b0b524c1cc64808b7b7e844c4861bbd2cf4325992f67bf'
BASE_SHA = 'e50ff1bc34bcc6d1c97dd001023c09a666971cde64605cc06671ed8a8ff1ed12'
QUERY_SHA = '9e9328e3f0488840d3f12efcc3b0f6af940dd398fb7b6d178d72bd1e1c0f9d74'
GT_SHA = 'e038aff5970977d0ee925b4357295bd81817b99b35e11bbab783fd64e0715e7f'
EVAL_SHA = 'f3999051c6cc96434ea26d2faedd3ac632ed8d20be342e15c92fd4b905a33fe9'
BINARY_SHA = {'D0': '254fe67c42a5568fc78062b51ee65ebcf13d03b6689c2470bc465423f9aad7e6',
              'E': 'd6ba7dcf7ed4fce1f40b646bc90bcd4cafa9fd668630d9b5a8922ad02e32615f'}
GRAPH_PINS = {
 'r1_D0': ('2739ccaccca64ed26c2840ff41cb8bb005ffdb9b62423f96dba3fa8dd65778a0', 2267625),
 'r1_E': ('96e6c8ff5f5b6b298dba065fb47f9af535c4b1e46fd55482419e2e6677e3d40b', 2267610),
 'r2_E': ('b60b1174395758eced707ec4c8e426f6095766b30d81fd3e863691a548eff1e5', 2267605),
 'r2_D0': ('117b3c809294bdbf50950f52f26f13acc1903f8d510962b4b671088f4a26e5f3', 2267612),
 'r3_D0': ('b1c45aec97b5cc0f3caa8110e08df5b8b58dee8b450f35f1e44a791a910ec0cf', 2267618),
 'r3_E': ('116e2a3e74893ebc3e312150576fb6e94178b67cecb5a2e19377a33c24c25089', 2267623),
}
PLAN = tuple(GRAPH_PINS)
RUN_STATUS = 'R83_9_TWO_METRIC_SCREEN_NO_GO_OR_HOLD'
QUALITY_STATUS = 'R83_8_TECHNICAL_RECALL_SCREEN_PASS_NOT_STATISTICAL_PROOF'


def gate(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as fp:
        for chunk in iter(lambda: fp.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def module_import(path):
    gate(path.is_file() and sha(path) == OLD_HELPER_SHA,
         'R83_10_PINNED_R83_8_V3_HELPER_NOT_FOUND_OR_SHA_MISMATCH ' + str(path))
    spec=importlib.util.spec_from_file_location('r83_8_verified_helper', path)
    gate(spec is not None and spec.loader is not None, 'R83_10_MODULE_IMPORT_BLOCKED')
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def preflight(root, helper):
    run=root/'experiments/H83/r83_9_newpc_pcore4_sift100k'
    summary=run/'r83_9_summary.json'
    gate(summary.is_file(), 'R83_10_R83_9_REPORT_MISSING')
    data=json.loads(summary.read_text())
    gate(data.get('status') == RUN_STATUS and data.get('threads') == 4,
         'R83_10_R83_9_VERDICT_OR_THREADS_MISMATCH')
    gate(data.get('base_sha256') == BASE_SHA and data.get('binary_sha256') == BINARY_SHA,
         'R83_10_BASE_OR_BINARY_PROVENANCE_MISMATCH')
    gate(data.get('cpu_allowed') == [0,2,4,6], 'R83_10_BUILD_AFFINITY_MISMATCH')
    gate(data.get('schedule') == list(PLAN), 'R83_10_BUILD_ORDER_MISMATCH')
    oldq=root/'experiments/H83/r83_7_sift100k_paired/quality/r83_8_quality_summary.json'
    gate(oldq.is_file(), 'R83_10_PRIOR_R83_8_QUALITY_REPORT_MISSING')
    old=json.loads(oldq.read_text())
    gate(old.get('status') == QUALITY_STATUS and old.get('evaluator_sha256') == EVAL_SHA,
         'R83_10_PRIOR_R83_8_QUALITY_OR_EVALUATOR_MISMATCH')
    base=root/'data/sift100k.fbin'
    query=root/'data/sift100k_queries_300.fbin'
    gt=root/'data/sift100k_gt300.ibin'
    helper.validate_matrix(base,(100000,128))
    helper.validate_matrix(query,(300,128))
    helper.validate_matrix(gt,(300,100),payload_bytes_per_slot=8)
    for name,path,pin in (('base',base,BASE_SHA),('query',query,QUERY_SHA),('gt',gt,GT_SHA)):
        gate(sha(path)==pin,f'R83_10_{name.upper()}_SHA_MISMATCH')
    ev=helper.find_evaluator(root)
    gate(sha(ev)==EVAL_SHA,'R83_10_EVALUATOR_SHA_MISMATCH')
    for tag,(digest,arcs) in GRAPH_PINS.items():
        entry=data.get('runs',{}).get(tag, {})
        gate(entry.get('tag')==tag and entry.get('exit_code')==0 and
             entry.get('variant')==tag.split('_')[1] and entry.get('threads')==4,
             f'R83_10_MISSING_OR_FAILED_BUILD {tag}')
        graph=entry.get('graph',{})
        gate(graph.get('sha256')==digest and graph.get('arcs')==arcs,
             f'R83_10_MANIFEST_GRAPH_MISMATCH {tag}')
        helper.check_graph(run/tag/'graph.bin',graph)
    out=run/'quality_r83_10'
    gate(not out.exists(),'R83_10_OUTPUT_EXISTS_FAIL_CLOSED ' + str(out))
    print('R83_10_PINNED_SIX_NEWPC_GRAPHS_AND_EVALUATOR_PASS',flush=True)
    print('R83_10_EVALUATOR_SHA256', EVAL_SHA,flush=True)
    print('R83_10_R83_9_BUILD_STATUS',RUN_STATUS,flush=True)
    return run,out,base,query,gt,ev,summary


def run(root, helper, dry_run):
    run_dir,out,base,query,gt,ev,summary=preflight(root,helper)
    if dry_run:
        print('R83_10_DRY_RUN_PASS_NO_SEARCH',flush=True)
        return
    out.mkdir(exist_ok=False)
    report=out/'r83_10_quality_summary.json'
    obj={'status':'STARTED', 'source_report':str(summary),
         'source_report_sha256':sha(summary),'evaluator_sha256':EVAL_SHA,
         'query_sha256':QUERY_SHA,'gt_sha256':GT_SHA,
         'search_host':{'node':platform.node(),'kernel':platform.release(),
                        'allowed_cpus':sorted(os.sched_getaffinity(0))},
         'created_at_utc':datetime.now(timezone.utc).isoformat(),'rows':{}}
    report.write_text(json.dumps(obj,indent=2)+'\n')
    try:
        for tag in PLAN:
            log=out/(tag+'.recall.log')
            print('R83_10_SEARCH_START graph='+tag,flush=True)
            with log.open('x') as fp:
                try:
                    p=subprocess.run([str(ev),str(run_dir/tag/'graph.bin'),str(base),str(query),str(gt)],
                        cwd=out,stdout=fp,stderr=subprocess.STDOUT,timeout=300,check=False)
                    code=p.returncode
                except subprocess.TimeoutExpired:
                    code=124
            gate(code==0,f'R83_10_EVALUATOR_EXIT_{code} graph={tag} log={log}')
            rows=helper.extract_rows(log.read_text(errors='replace'))
            obj['rows'][tag]={'arm':tag.split('_')[1],'rep':int(tag[1]),'beams':rows,'log':str(log)}
            report.write_text(json.dumps(obj,indent=2)+'\n')
            print('R83_10_SEARCH_PASS graph='+tag+' rows=5',flush=True)
        m=helper.metrics(obj['rows'])
        obj['assessment']=m
        obj['status']='R83_10_'+m['verdict'].removeprefix('R83_8_')
        obj['research_decision']='R83.9 wall gain 1.44% < 3% prespecified gate: HOLD/NO-GO to SIFT1M even if search passes'
        report.write_text(json.dumps(obj,indent=2)+'\n')
        print('R83_10_MEDIANS '+json.dumps([{k:v for k,v in b.items() if k.startswith('beam_') or k.startswith('median_')} for b in m['beams']],sort_keys=True),flush=True)
        print(obj['status'],flush=True)
        print('R83_10_BUILD_TWO_METRIC_SCREEN_REMAINS_NO_GO_OR_HOLD',flush=True)
        print('R83_10_NO_NEW_BUILD_NO_SIFT1M_NO_PUSH',flush=True)
        print('R83_10_REPORT',report,flush=True)
    except Exception as e:
        obj['status']='STOP_INCOMPLETE'
        obj['error']=str(e)
        report.write_text(json.dumps(obj,indent=2)+'\n')
        raise


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,default=Path.home()/'ann-task-a')
    p.add_argument('--helper',type=Path,default=Path.home()/'Downloads/run_r83_8_v3_evaluator_locator.py')
    p.add_argument('--dry-run',action='store_true')
    p.add_argument('--selftest',action='store_true')
    a=p.parse_args()
    helper=module_import(a.helper.expanduser())
    if a.selftest:
        helper.selftest()
        gate(len(GRAPH_PINS)==6 and len(set(GRAPH_PINS))==6,'R83_10_PLAN_SELFTEST_FAIL')
        print('R83_10_SELFTEST_PASS',flush=True)
        return
    run(a.root.expanduser().resolve(),helper,a.dry_run)

if __name__=='__main__':
    try:
        main()
    except Exception as e:
        print('R83_10_STOP',e,file=sys.stderr,flush=True)
        sys.exit(1)
