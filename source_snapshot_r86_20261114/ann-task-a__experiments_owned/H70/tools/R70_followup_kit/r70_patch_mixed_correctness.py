#!/usr/bin/env python3
"""Patch only R70's generated correctness harness to keep mixed-sized rows.

Does not edit original PiPNN source or TwoTierLSHGraph. Exits closed if the
fixture differs from the exact known R70 starter harness.
"""
import argparse
import hashlib
import pathlib
import shutil
import subprocess

COMMIT = '443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd'
GRAPH_BLOB = '7c5b8c1196a3ad741dfd22fe8f35b72acae2b19f'
START_SHA256 = '9f5ece923da9ffc7bdc34e14db90f308cb47354fbd69e2b737531c382b721c7c'

def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--worktree', type=pathlib.Path, required=True)
    args = ap.parse_args()
    w = args.worktree.expanduser().resolve()
    src = w / 'algorithms/PipNN/r70_native_tests.cc'
    hdr = w / 'algorithms/utils/graph.h'
    if git(w, 'rev-parse', 'HEAD') != COMMIT or git(w, 'hash-object', str(hdr)) != GRAPH_BLOB:
        raise SystemExit('R70_BLOCKED_WRONG_SOURCE_COMMIT_OR_GRAPH_BLOB')
    if not src.exists():
        raise SystemExit('R70_BLOCKED_TEST_SOURCE_MISSING')
    raw = src.read_bytes()
    if 'R70_MIXED_FINAL_ROW_PARITY_PASS' in raw.decode('utf-8'):
        print('R70_MIXED_PATCH_ALREADY_APPLIED')
        return
    if hashlib.sha256(raw).hexdigest() != START_SHA256:
        raise SystemExit('R70_BLOCKED_TEST_SOURCE_HASH_CHANGED_MANUAL_REVIEW_NEEDED')
    text = raw.decode('utf-8')
    old = '''  for(size_t row=1;row<16;row++) {
    for(uint32_t j=1;j<=170;j++) send(s,t,row,j+uint32_t(row*1000),float(j%21)+float(row)*0.01f);
    check_sorted(t,row);
  }
'''
    new = '''  for(size_t row=1;row<16;row++) {
    const uint32_t count=(row%3==0)?24u:((row%3==1)?64u:170u);
    for(uint32_t j=1;j<=count;j++) send(s,t,row,j+uint32_t(row*1000),float(j%21)+float(row)*0.01f);
    check(t.is_promoted(row)==(count>64),"mixed sequential row promotion mismatch");
    check_sorted(t,row);
  }
'''
    old2 = '''        for(size_t row=16+thread;row<N;row+=4) {
          for(uint32_t j=1;j<=170;j++) {
'''
    new2 = '''        for(size_t row=16+thread;row<N;row+=4) {
          const uint32_t count=(row%5==0)?0u:((row%5==1)?32u:((row%5==2)?64u:170u));
          for(uint32_t j=1;j<=count;j++) {
'''
    old3 = '''          same_row(s,t,row,"parallel distinct sources");
          check_sorted(t,row);
'''
    new3 = '''          same_row(s,t,row,"parallel distinct sources");
          check(t.is_promoted(row)==(count>64),"mixed parallel row promotion mismatch");
          check_sorted(t,row);
'''
    old4 = '''  for(size_t i=0;i<N;i++) same_row(s,t,i,"final all rows");
  check(t.promoted_rows()>0,"promotion path not exercised");
'''
    new4 = '''  for(size_t i=0;i<N;i++) same_row(s,t,i,"final all rows");
  check(t.promoted_rows()>0 && t.promoted_rows()<N,"must exercise promoted AND unpromoted final rows");
  std::cout<<"R70_MIXED_FINAL_ROW_PARITY_PASS promoted="<<t.promoted_rows()
           <<" unpromoted="<<(N-t.promoted_rows())<<"\\n";
'''
    for idx, (needle, replacement) in enumerate([(old,new),(old2,new2),(old3,new3),(old4,new4)], 1):
        if text.count(needle)!=1:
            raise SystemExit('R70_BLOCKED_PATCH_MATCH_'+str(idx))
        text = text.replace(needle,replacement,1)
    # The project H70 folder is parent of the worktree.
    backup = w.parent / 'r70_native_tests.before_mixed.cc'
    if backup.exists():
        raise SystemExit('R70_BLOCKED_BACKUP_EXISTS')
    shutil.copy2(src, backup)
    src.write_text(text)
    print('R70_MIXED_PATCH_PASS')
    print('R70_PATCH_ONLY_GENERATED_TEST', src)
    print('R70_BACKUP', backup)
    print('R70_STOCK_GRAPH_H_UNMODIFIED', git(w, 'hash-object', str(hdr)))

if __name__=='__main__':
    main()
