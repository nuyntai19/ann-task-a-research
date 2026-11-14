#!/usr/bin/env python3
"""R26b. Bounded SIFT1M .fbin/.ibin -> .npy and checked native-graph comparison.
Search results are same-native-searcher diagnostics unless graph arcs/bytes matched.
"""
from pathlib import Path
import argparse, hashlib, json, os, re, struct, sys, tempfile
import numpy as np
N,D,NQ,KGT=1_000_000,128,10_000,100

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(8*1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def header(path,rows,cols,bytes_per):
    path=Path(path)
    with path.open('rb') as f:
        shape=struct.unpack('<II',f.read(8))
    if shape!=(rows,cols) or path.stat().st_size!=8+rows*cols*bytes_per:
        raise ValueError(f'BAD_BIN_HEADER_OR_SIZE {path} actual_shape={shape} actual_bytes={path.stat().st_size}')

def convert(data,out):
    out.mkdir(exist_ok=True,parents=True)
    bp=data/'sift1m.fbin';qp=data/'sift1m_queries.fbin';gp=data/'sift1m_gt.ibin'
    header(bp,N,D,4);header(qp,NQ,D,4);header(gp,NQ,KGT,8)
    X=np.memmap(bp,dtype='<f4',mode='r',offset=8,shape=(N,D))
    q=np.memmap(qp,dtype='<f4',mode='r',offset=8,shape=(NQ,D))
    gt=np.memmap(gp,dtype='<u4',mode='r',offset=8,shape=(NQ,KGT))
    for src,name in [(X,'sift_X.npy'),(q,'sift_Q.npy')]:
        target=np.lib.format.open_memmap(out/name,mode='w+',dtype='<f4',shape=src.shape)
        for a in range(0,src.shape[0],20_000):
            target[a:a+20_000]=src[a:a+20_000]
        target.flush();del target
    if np.any(gt>=N):raise ValueError('GT_ID_OUT_OF_RANGE')
    np.save(out/'sift_GT100.npy',np.asarray(gt,dtype='<i4'))
    paths={name:{'sha256':sha(out/name),'bytes':(out/name).stat().st_size} for name in ['sift_X.npy','sift_Q.npy','sift_GT100.npy']}
    (out/'npy_manifest.json').write_text(json.dumps(paths,indent=2)+'\n')
    print('R26B_NPY_CONVERSION_PASS',[(x,paths[x]['bytes']) for x in paths])

def graph_check(path,expected_n=N,expected_max=None):
    path=Path(path);s=path.stat().st_size
    if s<8+expected_n*4 or s%4:raise ValueError(f'INVALID_GRAPH_LENGTH {path}')
    mm=np.memmap(path,mode='r',dtype='<u4')
    n,maxdeg=map(int,mm[:2]);deg=mm[2:2+n]
    if n!=expected_n or maxdeg<1 or maxdeg>1024 or (expected_max is not None and maxdeg!=expected_max):
        raise ValueError(f'INVALID_GRAPH_HEADER {path.name}: n={n},maxdeg={maxdeg}')
    if np.any(deg>maxdeg):raise ValueError(f'BAD_DEGREE {path.name}')
    offsets=np.empty(n+1,dtype=np.int64);offsets[0]=0
    np.cumsum(deg,dtype=np.int64,out=offsets[1:]);arcs=int(offsets[-1])
    if s!=8+4*(n+arcs):raise ValueError(f'GRAPH_SIZE_ARC_MISMATCH {path.name}')
    dst=mm[2+n:];isolated=int(np.count_nonzero(deg==0))
    for a in range(0,n,25_000):
        b=min(a+25_000,n);lo=int(offsets[a]);hi=int(offsets[b])
        chunk=dst[lo:hi]
        if np.any(chunk>=n):raise ValueError(f'GRAPH_DST_OOB {path.name} {a}')
        src=np.repeat(np.arange(a,b,dtype=np.uint32),deg[a:b].astype(np.int64))
        if np.any(src==chunk):raise ValueError(f'GRAPH_SELF_LOOP {path.name} {a}')
        key=(src.astype(np.uint64)<<32)|chunk.astype(np.uint64)
        if np.unique(key).size!=len(key):raise ValueError(f'GRAPH_DUPLICATE_EDGES {path.name} {a}')
    return {'sha256':sha(path),'vertices':n,'header_maxdeg':maxdeg,'arcs':arcs,
            'bytes':s,'mean_degree':round(arcs/n,7),'isolated_vertices':isolated}

def graph(pipnn,fg,out):
    a=graph_check(pipnn,N,32);b=graph_check(fg,N)
    if a['sha256']!='d497f6d19fff4b7db6436f960d036755e375be92483c03ec0b9ed61968d17bef':
        raise ValueError('PIPNN_GRAPH_SHA_CHANGED')
    difference=100*(b['arcs']/a['arcs']-1)
    approx=abs(difference)<=5
    rep={'status':'R26B_GRAPH_INTEGRITY_PASS','pipnn':a,'fg':b,'extra_arcs_percent':difference,
         'graph_budget_within_5pct':approx,
         'caveat':'Same pruning cap 32 does not equal same number of arcs. Qualitative search comparison only if graph budget unmatched.'}
    (out/'r26b_graph_report.json').write_text(json.dumps(rep,indent=2)+'\n')
    print('R26B_GRAPH_VALIDATION=PASS')
    print(f'R26B_PIPNN_ARCS={a["arcs"]} BYTES={a["bytes"]} SHA256={a["sha256"]}')
    print(f'R26B_FG_ARCS={b["arcs"]} BYTES={b["bytes"]} SHA256={b["sha256"]}')
    print(f'R26B_ARC_BUDGET_DELTA={difference:+.3f}%')
    print('R26B_BUDGET_STATUS='+('WITHIN_5PCT_EXPLORATORY' if approx else 'UNMATCHED_NO_SUPERIORITY_CLAIM'))

# Native source prints 5 repeats under fixed -Q, each line includes recall/QPS/comparisons.
PAT=re.compile(r'For\s+10@10\s+recall\s*=\s*([\deE.+-]+)\s*,\s*QPS\s*=\s*([\deE.+-]+).*?average\s+visited\s*=\s*(\d+)\s*,\s*average\s+cmps\s*=\s*(\d+)',re.I)

def search(out):
    gr=json.loads((out/'r26b_graph_report.json').read_text())
    result={'graph_budget':{'pipnn_arcs':gr['pipnn']['arcs'],'fg_arcs':gr['fg']['arcs'],
                            'delta_percent':gr['extra_arcs_percent']},'search':{}}
    for q in [80,100,120,160]:
        result['search'][str(q)]={}
        for arm in ['pipnn','fg']:
            p=out/f'search_{arm}_q{q}.log'
            text=p.read_text(errors='replace')
            matches=PAT.findall(text)
            if len(matches)!=5:
                raise ValueError(f'NOT_FIVE_FIXED_Q_RESULTS arm={arm} Q={q} found={len(matches)} log={p}')
            rows=[{'recall':float(r),'qps':float(qps),'visited':int(v),'dist_comparisons':int(cmps)} for r,qps,v,cmps in matches]
            result['search'][str(q)][arm]={'rows':rows, 'recall_median':float(np.median([x['recall'] for x in rows])),
                    'qps_median':float(np.median([x['qps'] for x in rows])),
                    'comparison_median':float(np.median([x['dist_comparisons'] for x in rows])),
                    'visited_median':float(np.median([x['visited'] for x in rows]))}
    budget_ok=abs(gr['extra_arcs_percent'])<=5
    result['status']='R26B_SIFT1M_NATIVE_PAIRED_DIAGNOSTIC_COMPLETED'
    result['inferential_limits']=[
       'One new FG graph from one fixed PiPNN pool, not independent graph build repetitions',
       'Five native repeats within each process are not independent process runs',
       'Same Q is not same Recall; same pruning cap32 is not necessarily same arc/byte budget',
       'FG end-to-end process wall includes local completeness and query diagnostics: do not compare as pure BUILD',
       'No PiPNN II author native baseline and no algorithm novelty claim']
    (out/'r26b_report.json').write_text(json.dumps(result,indent=2)+'\n')
    lines=['R26B_NATIVE_PAIRED_DIAGNOSTIC=PASS',
           f'R26B_ARC_BUDGET_DELTA={gr["extra_arcs_percent"]:+.3f}%',
           'R26B_BUDGET_MATCHED=APPROX_5PCT_ONLY' if budget_ok else 'R26B_BUDGET_MATCHED=NO']
    for q in [80,100,120,160]:
        for arm in ['pipnn','fg']:
            x=result['search'][str(q)][arm]
            lines.append(f'Q={q} ARM={arm} RECALL_MEDIAN={x["recall_median"]:.6f} QPS_MEDIAN={x["qps_median"]:.2f} AVG_CMPS_MEDIAN={x["comparison_median"]:.1f}')
    lines+=['R26B_SAME_SEARCHER=YES_NATIVE_PARLAYANN_SHA_PINNED',
            'R26B_NO_PIPNN_II_AND_NO_NOVELTY_CLAIM=YES',
            'R26B_SCIENTIFIC_STATUS=EXPLORATORY_NOT_MATCHED_RECALL_OR_BUILD_REPS']
    (out/'r26b_summary.txt').write_text('\n'.join(lines)+'\n')
    print('\n'.join(lines))

def selftest():
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp)/'p.graph'
        p.write_bytes(struct.pack('<IIIII',2,1,1,1,1)+struct.pack('<I',0))
        z=graph_check(p,2,1)
        assert z['arcs']==2 and z['bytes']==24
    line='For 10@10 recall = 0.99087, QPS = 2461.38, Q = 100, cut = 1.35, visited limit = 1000000, degree limit: 32, average visited = 110, average cmps = 2070'
    m=PAT.findall(line);assert len(m)==1 and m[0][0]=='0.99087' and m[0][3]=='2070'
    print('R26B_REPORT_SELFTEST_PASS')

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['selftest','convert','graph','search']);
    p.add_argument('--data',type=Path);p.add_argument('--out',type=Path);p.add_argument('--pipnn',type=Path);p.add_argument('--fg',type=Path)
    a=p.parse_args()
    if a.mode=='selftest':selftest()
    elif a.mode=='convert':convert(a.data,a.out)
    elif a.mode=='graph':graph(a.pipnn,a.fg,a.out)
    elif a.mode=='search':search(a.out)
if __name__=='__main__':main()
