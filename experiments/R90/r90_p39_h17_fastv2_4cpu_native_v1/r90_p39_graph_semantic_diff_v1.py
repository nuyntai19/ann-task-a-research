#!/usr/bin/env python3
"""R90-P3.9: independent read-only comparison of the FIRST 4CPU 100K CTRL/FAST graphs.

Distinguishes byte-order mismatch from different adjacency multisets / edge sets.
Does not build graphs, change evidence, or conclude ANN Search quality.
"""
from __future__ import annotations
import argparse, hashlib, json, mmap, os, struct, sys, tempfile
from collections import Counter
from pathlib import Path

ROOT=Path.home()/"ann-task-a/experiments/R90/r90_p39_h17_fastv2_4cpu_native_v1"
ORIG=Path.home()/"Downloads/r90_p39_h17_fastv2_4cpu_native_v1.py"
ORIG_SHA="f42ea9732560e646481f51f9f3458da1f7d2bd1dd3c7e5b2965cee363903e7d6"
EXPECTED={"ctrl":"292e757f22f3307b9746693c20081d82367f99d18db93324d0d865666ca32c59",
          "fast":"f383b05bcc4bc097ef18315f468b104b1e45395736fe3140d79708d1af445c1c"}
N=100000; CAP=64

def ck(condition, tag):
    if not condition: raise RuntimeError("R90_P39_DIFF_HOLD_"+tag)

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(4<<20),b''):h.update(block)
    return h.hexdigest()

class Graph:
    def __init__(self,path,n=None,cap=None):
        self.path=Path(path)
        self.file=self.path.open('rb')
        self.mm=mmap.mmap(self.file.fileno(),0,access=mmap.ACCESS_READ)
        ck(len(self.mm)>=8,"GRAPH_TOO_SHORT")
        self.n,self.cap=struct.unpack_from('<II',self.mm,0)
        if n is not None: ck(self.n==n,"GRAPH_N")
        if cap is not None: ck(self.cap==cap,"GRAPH_CAP")
        ck(len(self.mm)>=8+4*self.n,"DEGREES_TRUNCATED")
        self.deg=struct.unpack_from('<'+'I'*self.n,self.mm,8)
        ck(max(self.deg,default=0)<=self.cap,"DEGREE_EXCEEDS_CAP")
        self.offset=[0]*(self.n+1)
        for i,d in enumerate(self.deg):self.offset[i+1]=self.offset[i]+d
        ck(len(self.mm)==8+4*self.n+4*self.offset[-1],"GRAPH_FILE_LENGTH")
        self.efirst=8+4*self.n
    def row(self,i):
        n=self.deg[i]
        return struct.unpack_from('<'+'I'*n,self.mm,self.efirst+4*self.offset[i]) if n else ()
    def close(self):
        self.mm.close();self.file.close()

def compare(a,b,detail_limit=8):
    ck(a.n==b.n and a.cap==b.cap,"GRAPHS_SHAPE_MISMATCH")
    A=hashlib.sha256();B=hashlib.sha256()
    stat=dict(n=a.n,max_degree=a.cap,arcs_ctrl=a.offset[-1],arcs_fast=b.offset[-1],
              same_sequence_vertices=0,order_only_vertices=0,same_multiset_vertices=0,
              different_neighbor_multiset_vertices=0,degree_changed_vertices=0,
              duplicate_neighbor_rows_ctrl=0,duplicate_neighbor_rows_fast=0,
              arc_instances_removed_ctrl_to_fast=0,arc_instances_added_ctrl_to_fast=0,
              unique_edge_set_removed=0,unique_edge_set_added=0,
              sample_different_vertices=[])
    for i in range(a.n):
        x=a.row(i);y=b.row(i)
        if x==y:stat['same_sequence_vertices']+=1
        if len(x)!=len(y):stat['degree_changed_vertices']+=1
        sx=sorted(x);sy=sorted(y)
        A.update(struct.pack('<I',len(sx)));B.update(struct.pack('<I',len(sy)))
        if sx:A.update(struct.pack('<'+'I'*len(sx),*sx))
        if sy:B.update(struct.pack('<'+'I'*len(sy),*sy))
        if len(set(x))!=len(x):stat['duplicate_neighbor_rows_ctrl']+=1
        if len(set(y))!=len(y):stat['duplicate_neighbor_rows_fast']+=1
        if sx==sy:
            stat['same_multiset_vertices']+=1
            if x!=y:stat['order_only_vertices']+=1
        else:
            stat['different_neighbor_multiset_vertices']+=1
            cx,cy=Counter(x),Counter(y)
            lost=cx-cy;gained=cy-cx
            stat['arc_instances_removed_ctrl_to_fast']+=sum(lost.values())
            stat['arc_instances_added_ctrl_to_fast']+=sum(gained.values())
            stat['unique_edge_set_removed']+=len(set(x)-set(y))
            stat['unique_edge_set_added']+=len(set(y)-set(x))
            if len(stat['sample_different_vertices'])<detail_limit:
                stat['sample_different_vertices'].append({
                    'vertex':i,'ctrl_degree':len(x),'fast_degree':len(y),
                    'ctrl_lost_neighbor_ids':sorted(lost)[:10],
                    'fast_gained_neighbor_ids':sorted(gained)[:10]
                })
    stat['normalized_sorted_rows_sha_ctrl']=A.hexdigest()
    stat['normalized_sorted_rows_sha_fast']=B.hexdigest()
    stat['normalized_sorted_rows_equal']=A.digest()==B.digest()
    ck(stat['same_sequence_vertices']+stat['order_only_vertices']+stat['different_neighbor_multiset_vertices']==a.n,'ACCOUNTING')
    if stat['normalized_sorted_rows_equal']:
        ck(stat['different_neighbor_multiset_vertices']==0,'NORMALIZED_HASH_INCONSISTENT')
        stat['classification']='ORDER_ONLY_DIFFERENCE'
    else:
        ck(stat['different_neighbor_multiset_vertices']>0,'UNEXPECTED_HASH_DIFFERENCE')
        stat['classification']='EDGE_MULTISET_DIFFERENCE'
    return stat

def load_progress(root):
    p=root/'progress_100k.json';ck(p.is_file() and not p.is_symlink(),'PROGRESS_MISSING')
    m=json.loads(p.read_text())
    ck(m.get('phase')=='RUNNING_100K','PROGRESS_PHASE')
    ck(m.get('script_sha')==ORIG_SHA,'PROGRESS_SCRIPT_SHA')
    ck(m.get('source',{}).get('affinity')=='0,2,4,6','AFFINITY')
    ck(m.get('source',{}).get('PARLAY_NUM_THREADS')==4,'THREADS')
    r=m.get('runs',[])
    ck(len(r)==2 and {x.get('arm') for x in r}=={'ctrl','fast'},'PROGRESS_TWO_RUNS_ONLY')
    for row in r:
        arm=row['arm'];ck(row.get('n')==N and row.get('rep')==1,'RUN_ID')
        for field,hashname,subdir in [('graph','graph_sha','graphs'),('stdout','stdout_sha','logs'),('timefile','timefile_sha','logs')]:
            p=Path(row[field]);ck(p.is_file() and not p.is_symlink(),'FILE_MISSING_'+field)
            ck(p.resolve().parent==((root/subdir).resolve()),'PATH_OUTSIDE_'+field)
            ck(sha(p)==row[hashname],'EVIDENCE_SHA_'+arm+'_'+field)
        ck(row['graph_sha']==EXPECTED[arm],'GRAPH_SHA_'+arm)
    return {q['arm']:q for q in r}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase',choices=['selftest','audit'])
    p.add_argument('--root',type=Path,default=ROOT)
    p.add_argument('--report',type=Path)
    arg=p.parse_args()
    if arg.phase=='selftest':
        with tempfile.TemporaryDirectory() as t:
            def wr(fname,adj):
                path=Path(t)/fname;data=b''.join(struct.pack('<'+'I'*len(x),*x) for x in adj if x)
                path.write_bytes(struct.pack('<II',len(adj),4)+struct.pack('<'+'I'*len(adj),*[len(a) for a in adj])+data)
                return path
            pa=wr('a',[[1,2],[2,0],[0]])
            pb=wr('b',[[2,1],[0,2],[0]])
            pc=wr('c',[[2,1],[0,2],[1]])
            a=Graph(pa);b=Graph(pb);c=Graph(pc)
            x=compare(a,b);y=compare(a,c)
            assert x['classification']=='ORDER_ONLY_DIFFERENCE' and x['order_only_vertices']==2
            assert y['classification']=='EDGE_MULTISET_DIFFERENCE' and y['unique_edge_set_added']==1
            for obj in (a,b,c):obj.close()
        print('R90_P39_GRAPH_DIFF_SELFTEST_PASS_ORDER_VS_REAL_EDGE_CHANGE',flush=True)
        return
    ck(arg.report is not None,'OUTPUT_PATH_REQUIRED')
    root=arg.root.expanduser().resolve();report=arg.report.expanduser().absolute()
    ck(not (report.exists() or report.is_symlink()),'OUTPUT_EXISTS')
    ck(report.parent.is_dir() and os.access(report.parent,os.W_OK),'OUTPUT_PARENT')
    ck(ORIG.is_file() and sha(ORIG)==ORIG_SHA,'P39_ORIGINAL_SCRIPT_SHA')
    run=load_progress(root)
    c=Graph(run['ctrl']['graph'],N,CAP);f=Graph(run['fast']['graph'],N,CAP)
    try:
        d=compare(c,f)
    finally:c.close();f.close()
    d['source_root']=str(root)
    d['evidence_sha']={a:{k:run[a][k] for k in ['graph_sha','stdout_sha','timefile_sha']} for a in ['ctrl','fast']}
    d['interpretation']='Only adjacency comparison; does not measure Recall, QPS or explain concurrency causality.'
    with report.open('x') as out:json.dump(d,out,indent=2,sort_keys=True);out.write('\n')
    print('R90_P39_GRAPH_DIFF_AUDIT_PASS',d['classification'],'changed_multiset_vertices',d['different_neighbor_multiset_vertices'],
          'order_only_vertices',d['order_only_vertices'],'arcs_ctrl',d['arcs_ctrl'],'arcs_fast',d['arcs_fast'],flush=True)
    print('R90_P39_GRAPH_DIFF_REPORT',report,flush=True)

if __name__=='__main__':
    try: main()
    except Exception as e:
        print('R90_P39_GRAPH_DIFF_HOLD',repr(e),file=sys.stderr,flush=True)
        sys.exit(2)
