#!/usr/bin/env python3
"""G0: remove only the R86_COUNTERS conditional blocks and compare byte-for-byte to H70.
This is a text-level OFF projection audit, in addition to native tests. Does not modify source.
"""
from pathlib import Path
import argparse,sys,difflib,hashlib
p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--patched',type=Path,required=True)
a=p.parse_args()
FILES=['algorithms/PipNN/pipnn.h','algorithms/PipNN/pipnn_utils.h','algorithms/utils/graph.h']
MARK='#if defined(R86_COUNTERS) && R86_COUNTERS'
def strip_only_r86(text):
 result=[];stack=[]
 for num,line in enumerate(text.splitlines(keepends=True),1):
  x=line.strip()
  if x.startswith('#if ') or x.startswith('#ifdef ') or x.startswith('#ifndef '):
   if x==MARK: stack.append({'r86':True,'keep':False})
   else:
    if all(f['keep'] for f in stack):result.append(line)
    stack.append({'r86':False,'keep':True})
   continue
  if (x=='#else' or x.startswith('#else ')) and stack:
   if stack[-1]['r86']:stack[-1]['keep']=not stack[-1]['keep']
   elif all(f['keep'] for f in stack):result.append(line)
   continue
  if (x=='#endif' or x.startswith('#endif ')) and stack:
   f=stack.pop()
   if not f['r86'] and all(q['keep'] for q in stack):result.append(line)
   continue
  if all(f['keep'] for f in stack):result.append(line)
 if stack:raise ValueError('Unbalanced C-preprocessor conditionals')
 return ''.join(result)
failed=False
for f in FILES:
 src=(a.baseline/f).read_text();patch=(a.patched/f).read_text();off=strip_only_r86(patch)
 if off==src:print('G0_EXACT_SOURCE_OFF_PASS',f,hashlib.sha256(off.encode()).hexdigest())
 else:
  failed=True;print('G0_EXACT_SOURCE_OFF_FAIL',f)
  print(''.join(list(difflib.unified_diff(src.splitlines(True),off.splitlines(True),fromfile='baseline',tofile='OFF'))[:120]))
if failed:sys.exit(1)
print('R86_G0_SOURCE_OFF_BYTE_IDENTITY_PASS')
