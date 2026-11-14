#!/usr/bin/env python3
"""R70 read-only native PiPNN source/data preflight. DOES NOT modify source, run BUILD, or measure RSS.
Usage: python3 r70_preflight.py --root ~/ann-task-a --out experiments/H70/r70_preflight.json
"""
import argparse, hashlib, json, re, subprocess
from pathlib import Path

KEYS = ["LSHGraph", "LSHCandidate", "merge_neighbors", "allocate_graph", "kMaxDegree", "aligned_alloc", "HashPrune"]

def sha256(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(1<<20),b''):h.update(chunk)
    return h.hexdigest()

def git(cmd,cwd):
    try:
        p=subprocess.run(['git','-C',str(cwd)]+cmd,capture_output=True,text=True,timeout=8)
        return p.stdout.strip() if p.returncode==0 else None
    except Exception:return None

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--max-files',type=int,default=15000)
    a=ap.parse_args();root=a.root.expanduser().resolve();out=a.out.expanduser();out=out if out.is_absolute() else root/out
    if not root.is_dir():raise SystemExit(f'ROOT_NOT_FOUND {root}')
    files=[]
    for p in root.rglob('*'):
        if p.is_file() and p.suffix in ('.h','.hpp','.cpp','.cc','.cxx') and not any(z in p.parts for z in ('build','.git','.cache','third_party','_deps')):
            files.append(p)
            if len(files)>=a.max_files:break
    hits=[]
    for p in files:
        try:
            if p.stat().st_size>2_000_000:continue
            s=p.read_text(errors='replace')
        except OSError:continue
        matched=[k for k in KEYS if k in s]
        if len(matched)>=2 or ('merge_neighbors' in s):
            snippets=[]
            lines=s.splitlines()
            for i,line in enumerate(lines):
                if any(re.search(r'\b'+re.escape(k)+r'\b',line) for k in KEYS):
                    snippets.append({'line':i+1,'text':line[:250]})
            hits.append({'path':str(p.relative_to(root)),'sha256':sha256(p),'matched':matched,'matching_lines':snippets[:50]})
    candidates=[x for x in hits if 'merge_neighbors' in x['matched'] and 'LSHGraph' in x['matched']]
    result={'protocol':'R70 SOURCE PREFLIGHT ONLY','root':str(root),'pinned_expected_commit_prefix':'443a328',
       'files_examined':len(files),'truncated_at_max_files':len(files)>=a.max_files,
       'git_root_commit':git(['rev-parse','HEAD'],root),'git_status_short':git(['status','--short'],root),
       'potential_source_files':hits,'likely_graph_source_files':len(candidates),
       'checklist':{'pinned_source_verified':False,'native_semantic_parity_tested':False,'native_rss_measured':False,'native_build_executed':False},
       'warnings':['A file matching tokens is not proof it is PiPNN pinned 443a328.',
         'Do not edit stock sources. Verify commit and source file before building R70 worktree.',
         'R57 BF16/hash ordering caveat: parity requires exactly same ordered per-source candidate stream.']}
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('R70_PREFLIGHT_CREATED',out)
    print('CXX_FILES_SCANNED',len(files),'CANDIDATE_SOURCES',len(candidates),'GIT_HEAD',result['git_root_commit'] or 'NOT_AT_GIT_ROOT')
    for z in hits[:8]:print('SOURCE_HIT',z['path'],','.join(z['matched']))
    if not candidates:print('R70_BLOCKED_NATIVE_SOURCE_NOT_IDENTIFIED')
    elif not any('443a328' in str(git(['rev-parse','HEAD'],root) or '') for _ in [0]):print('R70_REQUIRES_PINNED_COMMIT_VERIFICATION')
    print('R70_BUILD_NOT_RUN RSS_NOT_MEASURED')
if __name__=='__main__':main()
