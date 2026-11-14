#!/usr/bin/env python3
"""Validate and SEARCH-evaluate 4 EXISTING SIFT1M graphs from the R72 4t pilot.
No BUILD. No changes to source, graph inputs, original binary or prior results.
"""
from __future__ import annotations
import argparse
from array import array
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import struct

ARMS = ('A_stock','B_h17','C_tier','D_h17_tier')
BEAMS = (10,20,40,80,160)
LABELS = {
    'A_stock': ('STOCK_FLAT_C160','STOCK_HIGHWAY'),
    'B_h17': ('STOCK_FLAT_C160','H17_PACKED_TOP2'),
    'C_tier': ('TIER_B64_C160','STOCK_HIGHWAY'),
    'D_h17_tier': ('TIER_B64_C160','H17_PACKED_TOP2'),
}
ROW = re.compile(r'R72_RECALL_ROW beam=(\d+) recall=([\d.eE+-]+) qps=([\d.eE+-]+) '
                 r'avg_cmps=([\d.eE+-]+) avg_visited=([\d.eE+-]+)')

def require(cond, message):
    if not cond:
        raise RuntimeError(message)

def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(4*1024*1024), b''):
            h.update(b)
    return h.hexdigest()

def check(path, purpose):
    require(path.is_file() and path.stat().st_size > 0, f'{purpose} missing or empty: {path}')

def shape(path, n, d, bytes_per_cell):
    check(path,'dataset')
    with path.open('rb') as f:
        a = f.read(8)
    require(len(a) == 8, f'incomplete header {path}')
    actual = struct.unpack('<II',a)
    expect_len = 8 + n*d*bytes_per_cell
    require(actual == (n,d) and path.stat().st_size == expect_len,
            f'invalid {path.name}: actual_shape={actual} bytes={path.stat().st_size} expected={(n,d,expect_len)}')

def check_manifest(root, base):
    manifest = root / 'inputs.sha256'
    check(manifest,'manifest')
    entries=[]
    for line in manifest.read_text().splitlines():
        m = re.fullmatch(r'([0-9a-f]{64})\s+\*?(.+)',line)
        require(m is not None, f'malformed manifest row {line}')
        expected,pathstr = m.groups()
        path = Path(pathstr).resolve()
        check(path,'manifest input')
        actual = sha256(path)
        require(actual == expected, f'input sha256 changed: {path}')
        entries.append({'path':str(path),'sha256':actual})
    expected_paths = {str(base.resolve())} | {
        str((root.parent / 'r71-bin' / arm).resolve()) for arm in ARMS
    }
    require(len(entries) == 5 and {x['path'] for x in entries} == expected_paths,
            'manifest contents do not match SIFT1M base and four R71 pinned arm binaries')
    print('R72_INPUT_MANIFEST_SHA256_PASS entries=5',flush=True)
    return entries

def inspect_graph(path, expected_n=1_000_000, expected_maxdeg=64):
    check(path,'graph')
    # Read-only input, and memory-bound: only one graph at a time.
    b=path.read_bytes()
    require(len(b) >= 8 and len(b)%4 == 0, f'invalid graph size: {path}')
    words=array('I')
    require(words.itemsize == 4, 'u32 word size unsupported')
    words.frombytes(b)
    if sys.byteorder != 'little':
        words.byteswap()
    n,maxdeg = words[:2]
    require(n == expected_n and maxdeg == expected_maxdeg,
            f'wrong graph n/maxdeg {n}/{maxdeg} for {path}')
    require(len(words)>=n+2, f'truncated graph degree table for {path}')
    degrees=words[2:2+n]
    require(all(d<=maxdeg for d in degrees), f'degree exceeds maxdeg in {path}')
    arcs=sum(degrees)
    require(len(words)==2+n+arcs, f'graph degree table and neighbor payload inconsistent: {path}')
    off=2+n
    for vertex,degree in enumerate(degrees):
        row=words[off:off+degree]
        off+=degree
        if any((neighbor>=n or neighbor==vertex) for neighbor in row) or len(set(row))!=degree:
            raise RuntimeError(f'invalid neighbor id, self-edge or duplicate at vertex {vertex} in {path}')
    require(off == len(words),f'graph payload has trailing entries: {path}')
    return {'n':n,'max_degree':maxdeg,'arcs':arcs,'avg_degree':arcs/n,
            'graph_bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),
            'invalid_neighbor_ids':0,'self_loops':0,'duplicate_neighbors':0}

def read_time(path):
    check(path,'time log')
    vals=dict(x.split('=',1) for x in path.read_text().split() if '=' in x)
    require(vals.get('EXIT')=='0','nonzero BUILD exit code in time log')
    w=float(vals['WALL_SEC']);rss=int(vals['MAX_RSS_KiB'])
    require(math.isfinite(w) and 0<w<1800 and rss>0,'invalid wall or RSS')
    return w,rss

def parse_search(output):
    require('R72_RECALL_INPUT_PASS' in output and 'R72_RECALL_EVAL_PASS' in output,
            'native evaluator did not complete successfully')
    records={}
    for m in ROW.finditer(output):
        beam=int(m.group(1))
        require(beam in BEAMS and beam not in records, f'unexpected or duplicate beam {beam}')
        recall,qps,cmps,visited = map(float,m.groups()[1:])
        require(0<=recall<=1 and math.isfinite(recall) and math.isfinite(qps) and qps>0
                and math.isfinite(cmps) and cmps>=0 and math.isfinite(visited) and visited>=0,
                f'invalid native recall row for beam {beam}')
        records[str(beam)]={'recall':recall,'qps':qps,'avg_cmps':cmps,'avg_visited':visited}
    require(set(records) == {str(x) for x in BEAMS},
            f'missing search beams {sorted(records)}')
    return records

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('run','binary','base','queries','gt','out'):
        p.add_argument('--'+arg,required=True,type=Path)
    args=p.parse_args()
    for key in ('run','binary','base','queries','gt','out'):
        setattr(args,key,getattr(args,key).expanduser().resolve())
    require(args.run.is_dir() and args.run.name.startswith('r72-sift1m-pilot-4t-'),
            'unexpected R72 pilot directory')
    require(not args.out.exists(),'output exists, preserving it: '+str(args.out))
    check(args.binary,'SIFT1M native evaluator')
    require(os.access(args.binary,os.X_OK),'native evaluator not executable')
    shape(args.base,1_000_000,128,4)
    shape(args.queries,10_000,128,4)
    shape(args.gt,10_000,100,8)
    print('R72_DATA_SHAPES_PASS base=1000000x128 queries=10000x128 gt=10000x100',flush=True)
    manifest=check_manifest(args.run,args.base)
    entries=[]
    for arm in ARMS:
        graph=args.run/(arm+'.graph')
        logfile=args.run/(arm+'.log')
        times=args.run/(arm+'.time')
        check(logfile,'BUILD log')
        logtext=logfile.read_text(errors='replace')
        reservoir,select=LABELS[arm]
        require(f'R70_RESERVOIR_VARIANT={reservoir}' in logtext,
                f'wrong R70 reservoir label: {arm}')
        require(f'R71_SELECTION_VARIANT={select}' in logtext,
                f'wrong R71 H17 selection label: {arm}')
        wall,rss=read_time(times)
        s=inspect_graph(graph)
        entries.append({'variant':arm,'graph':str(graph),'build_wall_sec':wall,
                        'build_peak_rss_KiB':rss,'graph_stats':s})
        print(f'R72_GRAPH_VALID {arm} arcs={s["arcs"]} bytes={s["graph_bytes"]} '
              f'wall_sec={wall:.2f} rss_KiB={rss}',flush=True)
    print('R72_ALL_FOUR_GRAPHS_VALID_PASS',flush=True)
    args.out.mkdir(parents=True)
    # This evaluator only does SEARCH on existing graphs. Never constructs a graph.
    env=os.environ.copy()
    env['PARLAY_NUM_THREADS']='1'
    by_arm={entry['variant']:entry for entry in entries}
    for arm in ('A_stock','D_h17_tier','B_h17','C_tier'):
        entry=by_arm[arm]
        print('R72_RECALL_START',arm,flush=True)
        cmd=[str(args.binary),entry['graph'],str(args.base),str(args.queries),str(args.gt)]
        try:
            proc=subprocess.run(cmd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                text=True,timeout=1800)
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f'SEARCH timeout for {arm}') from e
        path=args.out/(arm+'.recall.log')
        path.write_text(proc.stdout)
        require(proc.returncode==0,f'SEARCH failed arm={arm} rc={proc.returncode} log={path}')
        entry['search']=parse_search(proc.stdout)
        print(f'R72_RECALL_RUN_PASS {arm} beams=5',flush=True)
    base=by_arm['A_stock']; d=by_arm['D_h17_tier']
    for arm in ARMS:
        entry=by_arm[arm]
        print(f'R72_PILOT_BUILD arm={arm} wall={entry["build_wall_sec"]:.2f}s '
              f'rss_KiB={entry["build_peak_rss_KiB"]} '
              f'wall_delta_pct={(entry["build_wall_sec"]/base["build_wall_sec"]-1)*100:+.2f} '
              f'rss_delta_pct={(entry["build_peak_rss_KiB"]/base["build_peak_rss_KiB"]-1)*100:+.2f}',
              flush=True)
    for beam in BEAMS:
        a=base['search'][str(beam)]
        x=d['search'][str(beam)]
        print(f'R72_RECALL_COMPARE beam={beam} A={a["recall"]:.6f} '
              f'B={by_arm["B_h17"]["search"][str(beam)]["recall"]:.6f} '
              f'C={by_arm["C_tier"]["search"][str(beam)]["recall"]:.6f} '
              f'D={x["recall"]:.6f} D_minus_A_pp={(x["recall"]-a["recall"])*100:+.4f} '
              f'A_QPS={a["qps"]:.2f} D_QPS={x["qps"]:.2f} '
              f'D_QPS_delta_pct={(x["qps"]/a["qps"]-1)*100:+.2f}',flush=True)
    report={'kind':'R72_SIFT1M_FOUR_ARM_PILOT_QUALITY','created_at':datetime.now().astimezone().isoformat(),
            'source_run':str(args.run),'build_threads':4,'search_threads':1,
            'query_count':10000,'k':10,'beams':list(BEAMS),'cut':1.35,
            'native_evaluator':str(args.binary),'native_evaluator_sha256':sha256(args.binary),
            'manifest':manifest,'base':str(args.base),'queries':str(args.queries),'gt':str(args.gt),
            'runs':entries,'limitations':[
                'ONE BUILD per arm: descriptive pilot, not a reproducible speed/RSS result.',
                'GT is separately exact-validated for only TWO query samples by r72_preflight.',
                'Search QPS is measured once per graph; repeat measurements and warmups for robust QPS.',
                'Graph topological difference at 4 threads is affected by concurrency nondeterminism.',
                'BUILD wall includes serialization and process time; no claim of algorithmic novelty.'
            ]}
    out=args.out/'r72_quality_summary.json'
    out.write_text(json.dumps(report,indent=2)+'\n')
    print(f'R72_SIFT1M_QUALITY_PILOT_PASS output={out}',flush=True)

if __name__=='__main__':
    try:
        main()
    except Exception as e:
        print(f'R72_QUALITY_FAIL {type(e).__name__}: {e}',file=sys.stderr,flush=True)
        sys.exit(1)
