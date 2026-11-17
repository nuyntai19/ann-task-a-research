// H24-R1a: controlled offline source-row transplants, NOT real STH construction.
// Original diagnostic code; CSR layout: u32 n, u32 max_degree, u32 deg[n], u32 target[sum(deg)].
// C++17, Linux; no external dependencies. No existing graph is overwritten.
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>
using u32=uint32_t; using u64=uint64_t;
struct G{u32 n=0, maxdeg=0;std::vector<u32> deg,adj; std::vector<u64> off;};
static G load(const std::string&p){
 std::ifstream f(p,std::ios::binary);if(!f)throw std::runtime_error("Cannot open "+p);
 G g;f.read((char*)&g.n,4);f.read((char*)&g.maxdeg,4);if(!f||g.n<2||g.n>100000000)throw std::runtime_error("Invalid graph header");
 f.seekg(0,std::ios::end);const auto bytes=(u64)f.tellg();if(bytes<8ULL+4ULL*g.n||((bytes-8ULL-4ULL*g.n)%4))throw std::runtime_error("Invalid graph length");
 const u64 ne=(bytes-8ULL-4ULL*g.n)/4; if(ne>2000000000ULL)throw std::runtime_error("Too many edges for this study");
 g.deg.resize(g.n); f.seekg(8); f.read((char*)g.deg.data(),4ULL*g.n);
 g.off.assign((size_t)g.n+1,0);u32 maxd=0;
 for(u32 u=0;u<g.n;u++){g.off[u+1]=g.off[u]+g.deg[u];maxd=std::max(maxd,g.deg[u]);}
 if(g.off.back()!=ne || maxd>g.maxdeg)throw std::runtime_error("Degree header invalid");
 g.adj.resize((size_t)ne);f.read((char*)g.adj.data(),4ULL*ne);if(!f)throw std::runtime_error("Truncated graph");
 for(u32 u=0;u<g.n;u++)for(u64 j=g.off[u];j<g.off[u+1];j++)if(g.adj[j]>=g.n||g.adj[j]==u)throw std::runtime_error("Bad target ID/self-link in input graph");
 return g;
}
static void safe_file(const std::string&p){std::ifstream f(p,std::ios::binary);if(f.good())throw std::runtime_error("Refuse to overwrite existing: "+p);}
static int bucket(u32 d){return d<8?0:d<16?1:d<32?2:3;}
static u64 mix(u64 x){x+=0x9e3779b97f4a7c15ULL;x=(x^(x>>30))*0xbf58476d1ce4e5b9ULL;x=(x^(x>>27))*0x94d049bb133111ebULL;return x^(x>>31);}
int main(int argc,char**argv){try{
 std::string lp,hp,policy,prefix;double percent=-1;u64 seed=20261026;
 for(int i=1;i<argc;i++){
  std::string a=argv[i];auto v=[&](){if(i+1>=argc)throw std::runtime_error("Missing "+a);return std::string(argv[++i]);};
  if(a=="--low")lp=v();else if(a=="--high")hp=v();else if(a=="--policy")policy=v();else if(a=="--percent")percent=std::stod(v());else if(a=="--prefix")prefix=v();else if(a=="--seed")seed=std::stoull(v());else throw std::runtime_error("Unknown flag "+a);
 }
 if(lp.empty()||hp.empty()||prefix.empty()||percent<=0||percent>20||!(policy=="hindsight"||policy=="random"||policy=="degree_matched_random"))throw std::runtime_error("Usage: --low ... --high ... --policy hindsight|random|degree_matched_random --percent 1|2|5|10 --prefix ... [--seed 20261026]");
 G low=load(lp),high=load(hp);if(low.n!=high.n)throw std::runtime_error("Different n");const u32 n=low.n,k=(u32)((percent*n)/100.0+0.5);
 if(!k||k>=n)throw std::runtime_error("Bad selected fraction");
 std::vector<u32> novelty(n,0),order(n);std::iota(order.begin(),order.end(),0);
 std::vector<u32> tmp;
 for(u32 u=0;u<n;u++){
  tmp.assign(low.adj.begin()+low.off[u],low.adj.begin()+low.off[u+1]);std::sort(tmp.begin(),tmp.end());
  for(u64 j=high.off[u];j<high.off[u+1];j++)if(!std::binary_search(tmp.begin(),tmp.end(),high.adj[j]))novelty[u]++;
 }
 // Hindsight is from HIGH rows, is NOT an online low-only predictor or optimal oracle.
 std::sort(order.begin(),order.end(),[&](u32 a,u32 b){
  return novelty[a]!=novelty[b]?novelty[a]>novelty[b]:mix(seed^a)<mix(seed^b);
 });
 std::vector<u32> selected;
 if(policy=="hindsight")selected.assign(order.begin(),order.begin()+k);
 else if(policy=="random"){
  std::mt19937_64 rng(seed);std::shuffle(order.begin(),order.end(),rng);selected.assign(order.begin(),order.begin()+k);
 }else{
  u32 target[4]={};for(u32 j=0;j<k;j++)target[bucket(low.deg[order[j]])]++;
  std::vector<u32> bins[4];for(u32 u=0;u<n;u++)bins[bucket(low.deg[u])].push_back(u);
  for(int b=0;b<4;b++){
   std::mt19937_64 rng(seed+1103*b);std::shuffle(bins[b].begin(),bins[b].end(),rng);
   if(bins[b].size()<target[b])throw std::runtime_error("Impossible degree quota");
   selected.insert(selected.end(),bins[b].begin(),bins[b].begin()+target[b]);
  }
 }
 if(selected.size()!=k)throw std::runtime_error("Selected count inconsistent");
 std::vector<uint8_t> flags(n,0);for(u32 u:selected)if(flags[u]++)throw std::runtime_error("Duplicate selected vertex");
 std::sort(selected.begin(),selected.end());
 u64 ne=0;u32 maxdeg=0;u64 bonus=0;
 std::vector<u32> degrees(n),indeg(n,0);std::vector<u32> offsets(n+1,0);
 for(u32 u=0;u<n;u++){
  const G &g=flags[u]?high:low;
  degrees[u]=g.deg[u];ne+=g.deg[u];maxdeg=std::max(maxdeg,g.deg[u]);
  if(flags[u])bonus+=novelty[u];
 }
 if(ne>0xFFFFFFFFULL)throw std::runtime_error("Output edge count exceeds conservative limit");
 const std::string path=prefix+".graph",selpath=prefix+".selected.u32";safe_file(path);safe_file(selpath);
 // Before output, check whole graph reachability + indegree (entry 0, common R0f entry1).
 std::vector<u32> ptr(n+1,0);for(u32 u=0;u<n;u++)ptr[u+1]=ptr[u]+degrees[u];
 for(u32 u=0;u<n;u++){
  const G &g=flags[u]?high:low;for(u64 j=g.off[u];j<g.off[u+1];j++)indeg[g.adj[j]]++;
 }
 u64 zeros=0;for(u32 v:indeg)if(!v)zeros++;
 std::vector<uint8_t> seen(n,0);std::vector<u32> queue;queue.reserve(n);queue.push_back(0);seen[0]=1;
 for(size_t q=0;q<queue.size();q++){
  const u32 u=queue[q];const G &g=flags[u]?high:low;
  for(u64 j=g.off[u];j<g.off[u+1];j++){const u32 v=g.adj[j];if(!seen[v]){seen[v]=1;queue.push_back(v);}}
 }
 FILE *f=fopen(path.c_str(),"wb");if(!f)throw std::runtime_error("Cannot create graph file");
 bool ok=fwrite(&n,4,1,f)==1&&fwrite(&maxdeg,4,1,f)==1&&fwrite(degrees.data(),4,n,f)==n;
 for(u32 u=0;u<n&&ok;u++){
  const G &g=flags[u]?high:low;const u32 degree=g.deg[u];
  if(degree&&fwrite(g.adj.data()+g.off[u],4,degree,f)!=degree)ok=false;
 }
 if(fclose(f)!=0||!ok)throw std::runtime_error("Graph write failed; delete incomplete output and rerun");
 FILE *fs=fopen(selpath.c_str(),"wb");if(!fs)throw std::runtime_error("Cannot create selection file");
 bool sok=fwrite(selected.data(),4,selected.size(),fs)==selected.size();
 if(fclose(fs)!=0||!sok)throw std::runtime_error("Selection write failed");
 std::cout<<"RESULT policy="<<policy<<" percent="<<percent<<" selected="<<k<<" n="<<n<<" edges="<<ne<<" maxdeg="<<maxdeg<<" reach_entry0="<<queue.size()<<" zero_indeg="<<zeros<<" high_only_edges_in_selected="<<bonus<<" graph="<<path<<" selected_ids="<<selpath<<"\n";
 return 0;
 }catch(const std::exception&e){std::cerr<<"ERROR: "<<e.what()<<"\n";return 2;}}
