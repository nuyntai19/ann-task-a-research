#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <numeric>
#include <queue>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>
#include <omp.h>
using u32=uint32_t;
using clk=std::chrono::steady_clock;
using P=std::pair<float,u32>;
static void bad(const std::string& m){throw std::runtime_error(m);}
static uint64_t fsize(const std::string& path){std::ifstream f(path,std::ios::binary|std::ios::ate);if(!f)bad("Missing file: "+path);return static_cast<uint64_t>(f.tellg());}
static u32 read32(std::ifstream& f){u32 v;f.read((char*)&v,4);if(!f)bad("Truncated input");return v;}
static void read_exact(std::ifstream& f,void* p,size_t bytes){f.read((char*)p,static_cast<std::streamsize>(bytes));if(!f)bad("Truncated data payload");}
struct Matrix{u32 n=0,d=0;std::vector<float> v;
 void load(const std::string& p){std::ifstream f(p,std::ios::binary);if(!f)bad("Cannot open "+p);n=read32(f);d=read32(f);
  if(n==0||d==0||d>4096||fsize(p)!=8ULL+4ULL*n*d)bad("Bad fbin format/dimensions: "+p);
  v.resize(static_cast<size_t>(n)*d);read_exact(f,v.data(),v.size()*4);
 } const float* row(u32 i) const {return v.data()+static_cast<size_t>(i)*d;}
};
struct Graph{u32 n=0,mx=0;std::vector<u32> off,edges;
 void load(const std::string& p){std::ifstream f(p,std::ios::binary);if(!f)bad("Cannot open graph");n=read32(f);mx=read32(f);
  if(n==0||n>50000000||mx==0||mx>4096)bad("Bad graph header");
  std::vector<u32> deg(n);read_exact(f,deg.data(),4ULL*n);off.resize(static_cast<size_t>(n)+1);off[0]=0;
  uint64_t cum=0;for(u32 i=0;i<n;i++){if(deg[i]>mx)bad("Degree > max-degree");cum+=deg[i];if(cum>UINT32_MAX)bad("Graph has >UINT32_MAX edges; unsupported");off[i+1]=(u32)cum;}
  if(fsize(p)!=8ULL+4ULL*n+4ULL*cum)bad("Graph bytes mismatch");edges.resize(cum);read_exact(f,edges.data(),4ULL*cum);
  for(auto v:edges)if(v>=n)bad("Invalid graph edge target");
 }
};
struct GT{u32 n=0,k=0;std::vector<u32> v;bool available=false;
 void load(const std::string& p,u32 query_n,u32 base_n){if(p=="-")return;std::ifstream f(p,std::ios::binary);if(!f)bad("Cannot open groundtruth");n=read32(f);k=read32(f);
  if(n!=query_n||k<10||k>100000||fsize(p)!=8ULL+4ULL*n*k)bad("GT .ibin dimensions/size wrong");
  v.resize(static_cast<size_t>(n)*k);read_exact(f,v.data(),v.size()*4);
  for(u32 x:v)if(x>=base_n)bad("GT id out of bounds");available=true;
 }
};
static float squared(const float* a,const float* b,u32 d){float s=0;for(u32 j=0;j<d;j++){float z=a[j]-b[j];s+=z*z;}return s;}
struct Min{bool operator()(const P& a,const P& b)const{return a.first!=b.first?a.first>b.first:a.second>b.second;}};
struct Tot{
 double wall_us=0,gather_us=0,dedup_us=0,distance_us=0,update_us=0;
 uint64_t adjacency=0,prior_seen=0,new_occurrences=0,new_unique=0,same_wave_dups=0,
 cross_worker_dup_events=0,cross_worker_new_ids=0,dist_eval=0,waves=0,expanded=0;
 int threads_active=0;double recall=-1;
};
static double micro(clk::time_point a,clk::time_point b){return std::chrono::duration<double,std::micro>(b-a).count();}
struct Holder{u32 id=0,owners=0,occ=0,firstowner=100;u32 owner_counts[4]={0,0,0,0};bool prev=false;};
static Tot run(const Graph& g,const Matrix& b,const Matrix& queries,const GT& gt,u32 qid,
               int thread_count,int beam,int limit,u32 entry){
 const float* q=queries.row(qid);Tot r;auto allstart=clk::now();
 std::priority_queue<P,std::vector<P>,Min> heap;
 std::unordered_set<u32> seen;seen.reserve(static_cast<size_t>(limit)*g.mx+32);
 std::vector<P> evaluated;evaluated.reserve(static_cast<size_t>(limit)*g.mx+32);
 float d0=squared(b.row(entry),q,b.d);heap.emplace(d0,entry);seen.insert(entry);evaluated.emplace_back(d0,entry);r.dist_eval=1;
 std::vector<uint64_t> active(static_cast<size_t>(thread_count),0);
 while(!heap.empty()&&r.expanded<(uint64_t)limit){
  std::vector<u32> selected;selected.reserve(beam);
  for(int k=0;k<beam&&r.expanded+selected.size()<(uint64_t)limit&&!heap.empty();k++){
   auto item=heap.top();heap.pop();selected.push_back(item.second);
  }
  if(selected.empty())break;
  std::vector<std::vector<u32>> lists(selected.size());
  auto t0=clk::now();
  #pragma omp parallel for num_threads(thread_count) schedule(static,1) if(thread_count>1)
  for(int jj=0;jj<(int)selected.size();jj++){
   int tid=omp_get_thread_num();active[tid]++;
   const u32 u=selected[jj];
   lists[jj].assign(g.edges.begin()+g.off[u],g.edges.begin()+g.off[u+1]);
  }
  auto t1=clk::now();r.gather_us+=micro(t0,t1);
  std::unordered_map<u32,size_t> pos;pos.reserve(static_cast<size_t>(selected.size())*g.mx+1);
  std::vector<Holder> h;h.reserve(static_cast<size_t>(selected.size())*g.mx+1);
  // A diagnostic scan. Seen is unchanged until every proposal in this wave is classified.
  for(size_t j=0;j<lists.size();j++){
   int owner=static_cast<int>(j)%thread_count;
   for(u32 id:lists[j]){
    r.adjacency++;bool was=seen.find(id)!=seen.end();
    if(was)r.prior_seen++;else r.new_occurrences++;
    auto [it,ins]=pos.emplace(id,h.size());
    if(ins){Holder z;z.id=id;z.prev=was;h.push_back(z);}
    Holder& z=h[it->second];z.occ++;z.owners|=(1U<<owner);
    z.owner_counts[owner]++;
    z.firstowner=std::min(z.firstowner,(u32)owner);
   }
  }
  std::vector<u32> news;news.reserve(h.size());
  for(const Holder& z:h){
   r.same_wave_dups+=z.occ-1;
   for(int owner=0;owner<thread_count;owner++)if((u32)owner!=z.firstowner)r.cross_worker_dup_events+=z.owner_counts[owner];
   if(!z.prev){news.push_back(z.id);if(__builtin_popcount(z.owners)>1)r.cross_worker_new_ids++;}
  }
  for(u32 id:news)seen.insert(id);
  auto t2=clk::now();r.dedup_us+=micro(t1,t2);
  std::vector<float> ds(news.size());
  #pragma omp parallel for num_threads(thread_count) schedule(static) if(thread_count>1)
  for(int jj=0;jj<(int)news.size();jj++){
   int tid=omp_get_thread_num();active[tid]++;
   ds[jj]=squared(b.row(news[jj]),q,b.d);
  }
  auto t3=clk::now();r.distance_us+=micro(t2,t3);
  for(size_t j=0;j<news.size();j++){heap.emplace(ds[j],news[j]);evaluated.emplace_back(ds[j],news[j]);}
  auto t4=clk::now();r.update_us+=micro(t3,t4);
  r.new_unique+=news.size();r.dist_eval+=news.size();r.expanded+=selected.size();r.waves++;
 }
 std::sort(evaluated.begin(),evaluated.end(),[](const P&a,const P&b){return a.first!=b.first?a.first<b.first:a.second<b.second;});
 if(gt.available){int hits=0;const u32* gold=gt.v.data()+static_cast<size_t>(qid)*gt.k;
  for(size_t j=0;j<std::min<size_t>(10,evaluated.size());j++){
   if(std::find(gold,gold+10,evaluated[j].second)!=gold+10)hits++;
  }r.recall=hits/10.0;
 }
 r.threads_active=std::count_if(active.begin(),active.end(),[](uint64_t v){return v>0;});
 r.wall_us=micro(allstart,clk::now());return r;
}
int main(int argc,char** argv){try{
 if(argc!=11)bad("Usage: binary graph base query gt-or-dash query-id-txt workers wave expansions entry warmup");
 const std::string graph=argv[1],base=argv[2],query=argv[3],gtpath=argv[4],qids=argv[5];
 int workers=std::stoi(argv[6]),wave=std::stoi(argv[7]),limit=std::stoi(argv[8]);u32 entry=std::stoul(argv[9]);int warm=std::stoi(argv[10]);
 if(workers!=1&&workers!=2&&workers!=4)bad("workers must 1,2,4");
 if(wave<1||wave>128||limit<wave||limit>4096||warm<0||warm>1000)bad("bad wave/expansion/warmup values");
 Graph g;g.load(graph);Matrix b;b.load(base);Matrix queries;queries.load(query);GT gt;gt.load(gtpath,queries.n,g.n);
 if(g.n!=b.n||b.d!=queries.d||entry>=g.n)bad("graph/base/query dimension mismatch");
 std::ifstream f(qids);if(!f)bad("Missing query ids file");std::vector<u32> ids;u32 x;
 while(f>>x){if(x>=queries.n)bad("Query id out of range");ids.push_back(x);}if(ids.empty())bad("Empty query IDs");
 omp_set_dynamic(0);omp_set_num_threads(workers);
 for(int i=0;i<warm;i++)run(g,b,queries,gt,ids[i%ids.size()],workers,wave,limit,entry);
 std::cout<<std::setprecision(12);
 std::cout<<"query_id,latency_us,gather_us,dedup_us,distance_us,update_us,adjacency,prior_seen,new_occurrences,new_unique,same_wave_dups,cross_worker_dup_events,cross_worker_new_ids,dist_eval,waves,expanded,threads_active,recall10\n";
 for(u32 id:ids){Tot r=run(g,b,queries,gt,id,workers,wave,limit,entry);
  std::cout<<id<<","<<r.wall_us<<","<<r.gather_us<<","<<r.dedup_us<<","<<r.distance_us<<","<<r.update_us<<","<<r.adjacency<<","<<r.prior_seen<<","<<r.new_occurrences<<","<<r.new_unique<<","<<r.same_wave_dups<<","<<r.cross_worker_dup_events<<","<<r.cross_worker_new_ids<<","<<r.dist_eval<<","<<r.waves<<","<<r.expanded<<","<<r.threads_active<<","<<r.recall<<"\n";
 }
 }catch(const std::exception& e){std::cerr<<"H20R2 C++ ERROR: "<<e.what()<<"\n";return 2;}
 return 0;
}
