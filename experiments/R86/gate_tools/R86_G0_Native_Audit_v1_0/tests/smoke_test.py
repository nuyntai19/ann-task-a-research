#!/usr/bin/env python3
"""Synthetic fixture: exercises G0 stdout/readback, not native PiPNN."""
import hashlib, json, pathlib, shutil, subprocess, sys, tarfile, tempfile
SOURCE=pathlib.Path('/mnt/data/R86_day2_source_review.tar.gz')
PKG=pathlib.Path('/mnt/data/_audit_r86_kit/R86_Day2_Counter_Patch_v1_2')
SCRIPT=pathlib.Path(__file__).parents[1]/'r86_g0_native_audit.py'
VARIANTS={'stock_off':('OFF','OFF'),'stock_on':('OFF','ON'),'h17_off':('ON','OFF'),'h17_on':('ON','ON')}
with tempfile.TemporaryDirectory() as td:
 root=pathlib.Path(td);src=root/'H70/pipnn-clean-443a328';src.mkdir(parents=True)
 with tarfile.open(SOURCE,'r:gz') as tar:
  for m in tar.getmembers():
   if m.name.startswith('./H70_source/') and m.isfile():
    rel=m.name.removeprefix('./H70_source/')
    out=src/rel;out.parent.mkdir(parents=True,exist_ok=True)
    out.write_bytes(tar.extractfile(m).read())
 staged=root/'R86/r86_v1_2_source';shutil.copytree(src,staged)
 patch=root/'R86_patch_v1_2/R86_Day2_Counter_Patch_v1_2';shutil.copytree(PKG,patch)
 r=subprocess.run(['patch','-p1','--batch','-i',str(patch/'R86_counter_source_v1_2.patch')],cwd=staged,capture_output=True,text=True)
 assert r.returncode==0, r.stdout+'\n'+r.stderr
 (staged/'R86_STAGING_PROVENANCE.json').write_text(json.dumps({'source':str(src),'staged':str(staged),'patch_sha256':'test','omitted_dangling_symlinks':[]}))
 builds=root/'R86/r86_v1_2_builds'
 for name,(h17,on) in VARIANTS.items():
  build=builds/name;build.mkdir(parents=True)
  exe=build/'algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN';exe.parent.mkdir(parents=True)
  exe.write_text('#!/bin/sh\necho '+name+'\n');exe.chmod(0o755)
  digest=hashlib.sha256(exe.read_bytes()).hexdigest()
  (build/'R86_EXECUTABLE_SHA256.txt').write_text(f'{digest}  {exe}\n')
  cache=f'''R70_USE_TIER:BOOL=OFF\nR71_USE_H17:BOOL={h17}\nR86_USE_COUNTERS:BOOL={on}\nCMAKE_BUILD_TYPE:STRING=Release\nCMAKE_CXX_COMPILER:FILEPATH=/usr/bin/c++\nCMAKE_CXX_FLAGS:STRING=\nCMAKE_CXX_FLAGS_RELEASE:STRING=-O3 -DNDEBUG\nCMAKE_HOME_DIRECTORY:INTERNAL={staged}\n'''
  (build/'CMakeCache.txt').write_text(cache)
 audit=subprocess.run([sys.executable,str(SCRIPT),'--root',str(root),'--out',str(root/'R86/gates/g0_test')],capture_output=True,text=True)
 assert audit.returncode==0, audit.stdout+'\n'+audit.stderr
 assert 'R86_G0_NATIVE_BINARY_AUDIT_PASS' in audit.stdout
 e=json.loads((root/'R86/gates/g0_test/g0_manifest.json').read_text())
 assert len(e['variants'])==4 and e['result'].endswith('PASS')
 cache=builds/'h17_on/CMakeCache.txt'
 cache.write_text(cache.read_text().replace('R71_USE_H17:BOOL=ON','R71_USE_H17:BOOL=OFF'))
 bad=subprocess.run([sys.executable,str(SCRIPT),'--root',str(root),'--out',str(root/'R86/gates/g0_bad')],capture_output=True,text=True)
 assert bad.returncode==1 and 'R86_G0_NATIVE_BINARY_AUDIT_FAIL' in bad.stdout
 print('R86_G0_AUDIT_SYNTHETIC_PASS')
