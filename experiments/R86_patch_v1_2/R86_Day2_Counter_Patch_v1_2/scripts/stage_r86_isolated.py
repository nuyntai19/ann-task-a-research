#!/usr/bin/env python3
"""Stage R86 on a new directory only; never modify H70/R85. --apply is required."""
from pathlib import Path
import argparse,subprocess,hashlib,shutil,json,os,sys
HERE=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser()
p.add_argument('--source',required=True,type=Path,help='Original H70 source directory')
p.add_argument('--dest',required=True,type=Path,help='Non-existing R86 source directory')
p.add_argument('--apply',action='store_true',help='Actually create isolated source and apply patch')
a=p.parse_args()
src=a.source.resolve(strict=True);dest=a.dest.expanduser().absolute()
if dest.exists():p.error(f'Destination exists: {dest}')
if str(dest).startswith(str(src)+os.sep):p.error('Destination must not reside under source tree')
expected={}
for line in (HERE/'EXPECTED_SOURCE_SHA256.txt').read_text().splitlines():
 if not line or line.startswith('#'):continue
 sha,path=line.split(maxsplit=1);expected[path]=sha
for rel,sha in expected.items():
 data=(src/rel).read_bytes();h=hashlib.sha256(data).hexdigest()
 if h!=sha:p.error(f'SHA mismatch {rel}: {h} vs {sha}')
print('R86_SOURCE_PIN_PASS',len(expected),'files')
print('SOURCE',src);print('DESTINATION',dest)
if not a.apply:
 print('R86_STAGING_DRY_RUN_ONLY: re-run with --apply to copy/patch a NEW isolated directory')
 sys.exit(0)
missing=[]
def ign(d,names):
 out=[]
 for name in names:
  x=Path(d)/name
  if name in {'.git','r70_integration_backups','r71_h17_integration_backups','__pycache__'}:
   out.append(name)
  elif x.is_symlink() and not x.exists():
   out.append(name);missing.append(str(x))
 return out
shutil.copytree(src,dest,symlinks=True,ignore=ign)
patch=HERE/'R86_counter_source_v1_2.patch'
try:
 for args in [ ['patch','-p1','--batch','--dry-run','-i',str(patch)],
               ['patch','-p1','--batch','-i',str(patch)]]:
  subprocess.run(args,cwd=dest,check=True)
 subprocess.run(['python3',str(HERE/'scripts/verify_g0.py'),'--baseline',str(src),'--patched',str(dest)],check=True)
except Exception as e:
 print('STAGING_FAILED: isolated destination is left for inspection:',dest,file=sys.stderr)
 raise
report={'source':str(src),'staged':str(dest),'patch_sha256':hashlib.sha256(patch.read_bytes()).hexdigest(),
        'baseline_sha256':expected,'omitted_dangling_symlinks':missing,
        'note':'No edits made to original H70/R85; G0 source OFF parity checked.'}
(dest/'R86_STAGING_PROVENANCE.json').write_text(json.dumps(report,indent=2)+'\n')
print('R86_ISOLATED_STAGING_AND_G0_PASS',dest)
