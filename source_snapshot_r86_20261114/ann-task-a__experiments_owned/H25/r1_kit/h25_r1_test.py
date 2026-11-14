#!/usr/bin/env python3
"""Self-test native searcher against exhaustive gold and full synthetic graph."""
from pathlib import Path
import numpy as np, subprocess,struct,tempfile,os,csv
ROOT=Path(__file__).resolve().parent

def main():
    binary=ROOT/'h25_r1_common_search'
    subprocess.run(['g++','-std=c++17','-O3','-pthread',str(ROOT/'h25_r1_common_search.cpp'),'-o',str(binary)],check=True)
    with tempfile.TemporaryDirectory(prefix='h25r1_test_') as td:
        d=Path(td);n=20;k=10
        pts=np.array([[float(i),0.] for i in range(n)],dtype=np.float32)
        qq=np.array([[i+.13,0.] for i in range(4)],dtype=np.float32)
        gt=np.empty((4,k),dtype=np.uint32)
        for i,q in enumerate(qq):
            ranks=sorted(range(n),key=lambda j:(float(np.sum((pts[j]-q)**2)),j))
            gt[i]=ranks[:k]
        def fbin(p,x):
            with p.open('wb') as f:f.write(struct.pack('<II',*x.shape));f.write(x.astype('<f4').tobytes())
        fbin(d/'b.fbin',pts);fbin(d/'q.fbin',qq)
        with (d/'g.ibin').open('wb') as f:f.write(struct.pack('<II',*gt.shape));f.write(gt.astype('<u4').tobytes())
        with (d/'g.graph').open('wb') as f:
            f.write(struct.pack('<II',n,n-1));f.write(np.full(n,n-1,dtype='<u4').tobytes())
            for i in range(n): f.write(np.array([j for j in range(n) if j!=i],dtype='<u4').tobytes())
        r=subprocess.run([str(binary),'--graph',str(d/'g.graph'),'--base',str(d/'b.fbin'),'--queries',str(d/'q.fbin'),
          '--gt',str(d/'g.ibin'),'--csv',str(d/'out.csv'),'--efs','20','--nq','4','--repeats','2'],capture_output=True,text=True)
        print(r.stdout);print(r.stderr)
        if r.returncode!=0:raise RuntimeError('Searcher synthetic run failed')
        with (d/'out.csv').open() as f:row=next(csv.DictReader(f))
        assert abs(float(row['recall10'])-1.0)<1e-9, row
        assert int(row['reachable0'])==n
        print('SELFTEST PASS: native C++ common search reaches all vertices and achieves Recall@10=1.0 on exact synthetic gold')
if __name__=='__main__':main()
