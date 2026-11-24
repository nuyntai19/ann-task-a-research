import json,struct,subprocess,tempfile,random,sys
from pathlib import Path

def expected(rows):
 n=len(rows); reach=[]
 for u in range(n):
  vis={u};q=[u]
  for v in q:
   for w in rows[v]:
    if w not in vis:vis.add(w);q.append(w)
  reach.append(vis)
 def parts(strong):
  left=set(range(n));sizes=[]
  while left:
   a=min(left);seen={a};q=[a]
   for v in q:
    for w in range(n):
     ok=(w in reach[v] and v in reach[w]) if strong else (w in rows[v] or v in rows[w])
     if ok and w not in seen:seen.add(w);q.append(w)
   sizes.append(len(seen));left-=seen
  return dict(count=len(sizes),largest=max(sizes),singletons=sizes.count(1),vertices=n)
 return parts(True),parts(False)

def test(exe):
 exe=str(Path(exe).resolve());rng=random.Random(555)
 with tempfile.TemporaryDirectory() as td:
  p=Path(td)/'fixture.graph'
  for rows in [[[1],[0,2],[],[4],[3],[]],[[],[]],[[1],[2],[0]]]+[[[v for v in range(n) if v!=u and rng.random()<.15] for u in range(n)] for n in range(2,35)]:
   n=len(rows);m=sum(map(len,rows));p.write_bytes(struct.pack('<'+'I'*(2+n+m),n,64,*map(len,rows),*(v for row in rows for v in row)));x=json.loads(subprocess.check_output([exe,str(p),str(n),str(m)]));s,w=expected(rows);assert x['scc']==s and x['wcc']==w
   for k,d in [('out_degree',list(map(len,rows))),('in_degree',[sum(u in r for r in rows) for u in range(n)])]:
    h=x[k];assert h['histogram']==[[v,d.count(v)] for v in sorted(set(d))];assert h['mean']==sum(d)/n;assert all(h['p'+str(t)]==sorted(d)[(n*t+99)//100-1] for t in (50,95,99))
  for raw,n,m in [(struct.pack('<6I',2,64,1,1,0,0),2,2),(struct.pack('<6I',2,64,2,0,1,1),2,2),(struct.pack('<5I',2,64,1,0,9),2,1),(struct.pack('<4I',2,64,1,0),2,1)]:
   p.write_bytes(raw);assert subprocess.run([exe,str(p),str(n),str(m)],capture_output=True).returncode!=0
 print('TOPOLOGY_FIXTURES_PASS_36_VALID_4_INVALID')
if __name__=='__main__':test(sys.argv[1])
