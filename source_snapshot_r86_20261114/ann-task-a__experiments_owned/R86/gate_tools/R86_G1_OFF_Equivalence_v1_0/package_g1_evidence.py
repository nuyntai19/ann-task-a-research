#!/usr/bin/env python3
"""Package SMALL G1 logs/manifests only; never include .graph or data files."""
import argparse
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import tarfile

HOME=Path.home()
ROOT=HOME/'ann-task-a/experiments/R86/gates/g1_off_bigann1m'
R85=HOME/'ann-task-a/experiments/H85/r85_scale1_bigann1m/bigann1m_20261112-022002_494222'

ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--session',required=True,type=Path)
a=ap.parse_args()
run=a.session.resolve()
root=ROOT.resolve()
if not run.is_dir() or not run.is_relative_to(root) or run==root:
    raise SystemExit('FAIL: session must be existing new R86 G1 folder')

names=['manifest.json','build_results.json']
for tag in ['stock_c160_k1024_n2','h17_c64_k512_n2']:
    names += [tag+s for s in ('.record.json','.build.log','.time','.quality_record.json','.quality.log')]
files=[]
for n in names:
    p=run/n
    if p.is_file() and not p.is_symlink():files.append((p,'r86_session/'+n))
for tag in ['STOCK','C64_K512_N2']:
    for suffix in ('.build.log',):
        p=R85/('t4_r1_'+tag+suffix)
        if p.is_file() and not p.is_symlink():files.append((p,'r85_reference/'+p.name))
    p=R85/'quality'/('t4_r1_'+tag+'.log')
    if p.is_file() and not p.is_symlink():files.append((p,'r85_reference/quality_'+p.name))
if not any(arc=='r86_session/manifest.json' for p,arc in files):
    raise SystemExit('FAIL: R86 G1 manifest missing')

out=HOME/('R86_G1_Evidence_'+run.name+'.tar.gz')
if out.exists() or out.is_symlink():
    raise SystemExit('FAIL: output archive exists, refusing overwrite: '+str(out))
index=[]
with tarfile.open(out,mode='x:gz') as tf:
    for p,arc in files:
        dig=hashlib.sha256(p.read_bytes()).hexdigest()
        index.append({'archive_path':arc,'sha256':dig,'size':p.stat().st_size})
        tf.add(p,arcname=arc,recursive=False)
    payload=json.dumps({'schema':'R86_G1_EVIDENCE_INDEX_V1','session':str(run),
                        'archived_at':dt.datetime.now().astimezone().isoformat(),
                        'files':index,'excluded':['*.graph','*.graph.tmp','data/*'],
                        'note':'No interpretation of G1 PASS is inferred from packaging.'},
                       ensure_ascii=False,indent=2).encode()+b'\n'
    ti=tarfile.TarInfo('EVIDENCE_INDEX.json');ti.size=len(payload);ti.mode=0o644
    tf.addfile(ti,io.BytesIO(payload))
print('R86_G1_EVIDENCE_PACKAGE_PASS',out,'files='+str(len(index)+1),flush=True)
