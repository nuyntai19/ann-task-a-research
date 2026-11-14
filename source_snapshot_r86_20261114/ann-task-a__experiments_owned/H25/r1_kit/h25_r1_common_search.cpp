// H25-R1 independent, single-thread, graph-invariant common search evaluator.
// All compared graphs MUST use this same binary and equal base/queries/exact GT.
// This is not bit-identical to H24-R0f search; do not compare QPS across evaluators.
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <limits>
#include <numeric>
#include <queue>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <vector>
using U=uint32_t;
using Item=std::pair<float,U>;
struct Graph {U n=0,maxdeg=0; std::vector<U> deg,ids;std::vector<uint64_t> off;uint64_t bytes=0;};
[[noreturn]] void die(const std::string& s){throw std::runtime_error(s);}
uint64_t sizefile(const std::string& p){std::ifstream f(p,std::ios::binary|std::ios::ate);if(!f)die("Cannot open "+p);return static_cast<uint64_t>(f.tellg());}
std::vector<U> parse_ef(const std::string& s){std::vector<U> out;size_t p=0;while(p<s.size()){size_t q=s.find(',',p);auto tok=s.substr(p,q==std::string::npos?std::string::npos:q-p);auto v=std::stoul(tok);if(v<10 || v>2000)die("ef must be 10..2000");out.push_back(U(v));if(q==std::string::npos)break;p=q+1;}if(out.empty())die("Empty ef list");return out;}
Graph load_graph(const std::string& path){
  Graph g;g.bytes=sizefile(path);std::ifstream f(path,std::ios::binary);
  if(!f.read((char*)&g.n,4) || !f.read((char*)&g.maxdeg,4))die("Invalid graph preamble");
  if(g.n==0 || g.n>1000000000 || g.maxdeg<1 || g.maxdeg>10000)die("Graph n/maxdeg out of range");
  g.deg.resize(g.n);if(!f.read((char*)g.deg.data(),4ULL*g.n))die("Truncated degree table");
  g.off.resize(g.n+1);g.off[0]=0;
  for(size_t i=0;i<g.n;++i){if(g.deg[i]>g.maxdeg)die("Degree exceeds maxdeg");g.off[i+1]=g.off[i]+g.deg[i];}
  if(g.bytes!=8+4ULL*g.n+4ULL*g.off.back())die("Graph size mismatch");
  g.ids.resize(g.off.back());if(!f.read((char*)g.ids.data(),4ULL*g.ids.size()))die("Truncated IDs");
  for(size_t u=0;u<g.n;++u)for(uint64_t j=g.off[u];j<g.off[u+1];++j)
    if(g.ids[j]>=g.n||g.ids[j]==u)die("Invalid neighbor or self link");
  return g;
}
struct Matrix{U n=0,d=0;std::vector<float> v;};
Matrix load_fbin(const std::string& s){
  Matrix a;uint64_t bytes=sizefile(s);std::ifstream f(s,std::ios::binary);
  if(!f.read((char*)&a.n,4)||!f.read((char*)&a.d,4))die("fbin header invalid");
  if(a.n==0||a.d==0||a.d>100000)die("fbin dimensions invalid");
  if(bytes!=8+4ULL*a.n*a.d)die("fbin size mismatch");
  a.v.resize(uint64_t(a.n)*a.d);
  if(!f.read((char*)a.v.data(),a.v.size()*sizeof(float)))die("fbin data truncated");
  return a;
}
struct Gold{U n=0,k=0;std::vector<U> ids;};
// Accept TWO explicitly validated ibin layouts, both starting with uint32 (n,k):
//  (1) 8-byte header + n*k uint32 IDs (common minimal ibin), or
//  (2) header + n*k uint32 IDs + n*k float32 L2 distances (PiPNN/ParlayANN SIFT GT).
// The distance array in (2) is stored AFTER the complete IDs array, not interleaved.
// Keep the unmodified IDs for Recall@10, verify trailing distances are finite.
Gold load_gt(const std::string&s){
  Gold g;const uint64_t z=sizefile(s);std::ifstream f(s,std::ios::binary);
  if(!f.read((char*)&g.n,4)||!f.read((char*)&g.k,4))die("GT header invalid");
  if(g.n==0||g.k<10||g.k>1000)die("GT dimension invalid: n="+std::to_string(g.n)+" k="+std::to_string(g.k));
  const uint64_t count=uint64_t(g.n)*g.k;
  const uint64_t ids_only=8ULL+4ULL*count;
  const uint64_t ids_plus_dist=8ULL+8ULL*count;
  const bool has_dist=(z==ids_plus_dist);
  if(z!=ids_only&&!has_dist)die("GT shape invalid: header n="+std::to_string(g.n)+
       " k="+std::to_string(g.k)+" bytes="+std::to_string(z)+
       " expected IDs-only="+std::to_string(ids_only)+
       " or IDs+float32-dist="+std::to_string(ids_plus_dist));
  g.ids.resize(count);
  if(!f.read(reinterpret_cast<char*>(g.ids.data()),count*sizeof(U)))die("GT IDs truncated");
  if(has_dist){
    std::vector<float> buffer(16384);
    uint64_t remaining=count;
    while(remaining){
      const size_t m=static_cast<size_t>(std::min<uint64_t>(remaining,buffer.size()));
      if(!f.read(reinterpret_cast<char*>(buffer.data()),m*sizeof(float)))die("GT distances truncated");
      for(size_t i=0;i<m;i++)if(!std::isfinite(buffer[i])||buffer[i]<0.0f)
        die("GT distance is NaN, inf or negative: invalid IDs+dist layout");
      remaining-=m;
    }
  }
  std::cout<<"H25_R1_GT_VALID n="<<g.n<<" k="<<g.k
     <<" layout="<<(has_dist?"ids_then_float32_distances":"ids_only")
     <<" bytes="<<z<<std::endl;
  return g;
}
size_t reachable(const Graph& g,std::vector<U>& indeg){
  indeg.assign(g.n,0);for(U v:g.ids)indeg[v]++;
  std::vector<uint8_t> seen(g.n,0);std::vector<U> q;q.reserve(g.n);q.push_back(0);seen[0]=1;
  for(size_t z=0;z<q.size();++z){U u=q[z];for(uint64_t e=g.off[u];e<g.off[u+1];++e){U v=g.ids[e];if(!seen[v]){seen[v]=1;q.push_back(v);}}}
  return q.size();
}
struct Searcher{
 const Graph& g;const Matrix& b;std::vector<U> seen;U stamp=0;
 explicit Searcher(const Graph& G,const Matrix& B):g(G),b(B),seen(G.n,0){}
 float dist(const float* q, U x)const {const float* p=b.v.data()+uint64_t(x)*b.d;float v=0.f;for(U i=0;i<b.d;++i){float delta=q[i]-p[i];v+=delta*delta;}return v;}
 std::vector<U> search(const float* q,U ef){
   if(++stamp==0){std::fill(seen.begin(),seen.end(),0);stamp=1;}
   std::priority_queue<Item,std::vector<Item>,std::greater<Item>> candidates;
   std::priority_queue<Item> retained;
   float d=dist(q,0);seen[0]=stamp;candidates.push({d,0});retained.push({d,0});
   while(!candidates.empty()){
     auto cur=candidates.top();candidates.pop();
     if(retained.size()>=ef && cur.first>retained.top().first)break;
     U u=cur.second;
     for(uint64_t e=g.off[u];e<g.off[u+1];++e){U v=g.ids[e];if(seen[v]==stamp)continue;seen[v]=stamp;
       float nd=dist(q,v);
       if(retained.size()<ef||std::make_pair(nd,v)<retained.top()){
         candidates.push({nd,v});retained.push({nd,v});if(retained.size()>ef)retained.pop();
       }
     }
   }
   std::vector<Item> rs;while(!retained.empty()){rs.push_back(retained.top());retained.pop();}
   std::sort(rs.begin(),rs.end());std::vector<U> out;for(size_t i=0;i<std::min<size_t>(10,rs.size());++i)out.push_back(rs[i].second);return out;
 }
};
struct Row{U ef,nq,repeats;double recall,median_qps,min_qps,max_qps;};
Row measure(Searcher& s,const Matrix& Q,const Gold& gt,U ef,U nq,U repeats){
  // Warm-up outside timings.
  for(U i=0;i<std::min<U>(10,nq);++i) (void)s.search(Q.v.data()+uint64_t(i)*Q.d,ef);
  std::vector<double> qps;double recall=-1;
  for(U rep=0;rep<repeats;++rep){
    size_t hits=0;auto begin=std::chrono::steady_clock::now();
    for(U qi=0;qi<nq;++qi){auto ids=s.search(Q.v.data()+uint64_t(qi)*Q.d,ef);
      const U* gold=gt.ids.data()+uint64_t(qi)*gt.k;
      for(U v:ids)for(U j=0;j<10;++j)if(v==gold[j]){hits++;break;}
    }
    auto end=std::chrono::steady_clock::now();
    double sec=std::chrono::duration<double>(end-begin).count();qps.push_back(nq/sec);
    double this_recall=double(hits)/(10*nq);
    if(recall>=0 && std::fabs(this_recall-recall)>1e-12)die("Recall non-deterministic across repeated reads");recall=this_recall;
  }
  std::sort(qps.begin(),qps.end());return {ef,nq,repeats,recall,qps[qps.size()/2],qps.front(),qps.back()};
}
int main(int argc,char**argv){try{
  std::string graph,base,queries,gt,out,efs="100,140,200,300";U nq=1000,repeats=3;
  for(int i=1;i<argc;i++){
    std::string k=argv[i];if(i+1>=argc)die("Missing value after "+k);std::string v=argv[++i];
    if(k=="--graph")graph=v;else if(k=="--base")base=v;else if(k=="--queries")queries=v;
    else if(k=="--gt")gt=v;else if(k=="--csv")out=v;else if(k=="--efs")efs=v;
    else if(k=="--nq")nq=std::stoul(v);else if(k=="--repeats")repeats=std::stoul(v);else die("Unknown arg "+k);
  }
  if(graph.empty()||base.empty()||queries.empty()||gt.empty()||out.empty()||nq==0||repeats<1||repeats>20)die("Required --graph --base --queries --gt --csv [--efs, --nq, --repeats]");
  std::ifstream check(out);if(check.good())die("Refuse to overwrite CSV "+out);
  auto G=load_graph(graph);auto B=load_fbin(base);auto Q=load_fbin(queries);auto GT=load_gt(gt);
  if(G.n!=B.n||B.d!=Q.d||Q.n!=GT.n||nq>Q.n||nq>GT.n)die("Graph/base/queries/GT shapes incompatible");
  for(U z:GT.ids)if(z>=G.n)die("GT id out of range");
  std::vector<U> indeg;size_t nreachable=reachable(G,indeg);size_t zero=std::count(indeg.begin(),indeg.end(),0U);
  std::cout << "H25_R1_GRAPH_VALID n="<<G.n<<" edges="<<G.off.back()<<" bytes="<<G.bytes
            <<" maxdeg="<<G.maxdeg<<" reachable0="<<nreachable<<" zero_indegree="<<zero<<std::endl;
  std::ofstream f(out);f<<"graph,ef,nq,repeats,recall10,median_qps,min_qps,max_qps,n,edges,graph_bytes,reachable0,zero_indegree\n";
  Searcher s(G,B);
  for(U ef:parse_ef(efs)){
    auto r=measure(s,Q,GT,ef,nq,repeats);
    f<<graph<<","<<r.ef<<","<<r.nq<<","<<r.repeats<<","<<r.recall<<","<<r.median_qps<<","<<r.min_qps<<","<<r.max_qps
     <<","<<G.n<<","<<G.off.back()<<","<<G.bytes<<","<<nreachable<<","<<zero<<"\n";f.flush();
    std::cout<<"H25_R1_SEARCH ef="<<ef<<" recall10="<<r.recall<<" medianQPS="<<r.median_qps<<std::endl;
  }
  std::cout<<"H25_R1_SEARCH_DONE "<<out<<std::endl;
  return 0;
 }catch(const std::exception& e){std::cerr<<"H25_R1_FAIL_CLOSED: "<<e.what()<<std::endl;return 2;}}
