// H24-R0f: independent, read-only, single-thread ANN graph evaluator.
// This evaluator is original standalone code, not copied from GRAFT/PiPNN.
// Shared protocol: classical HNSW layer-0 best-first beam, identical initial
// node IDs, dataset, ground truth, ef values, distance kernel across graphs.
// Metric: squared L2 float32; query IDs are external queries, not base points.
// Build: g++ -O3 -std=c++17 -march=native -ffp-contract=off h24_r0f_common_search.cpp -o h24_r0f_common_search
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <limits>
#include <queue>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <utility>
#include <vector>

using u32=uint32_t;
using u64=uint64_t;
struct Fbin {u32 n=0,d=0; std::vector<float> a;};
static Fbin load_fbin(const std::string& p, u32 take=0) {
    std::ifstream f(p,std::ios::binary); if(!f)throw std::runtime_error("missing fbin: "+p);
    Fbin z;f.read((char*)&z.n,4);f.read((char*)&z.d,4);
    if(!f || !z.n || !z.d || z.d>10000)throw std::runtime_error("bad fbin header: "+p);
    f.seekg(0,std::ios::end);auto len=f.tellg();
    if(len!=(std::streamoff)8+(std::streamoff)z.n*z.d*4)throw std::runtime_error("bad fbin size: "+p);
    if(take && take>z.n)throw std::runtime_error("too few vectors: "+p);
    if(take)z.n=take;
    z.a.resize((size_t)z.n*z.d);f.seekg(8);f.read((char*)z.a.data(),(std::streamsize)z.a.size()*4);
    if(!f)throw std::runtime_error("short fbin read: "+p);
    return z;
}
struct G {u32 n=0,maxdeg=0;u64 E=0;std::vector<u64> offsets;std::vector<u32> arcs;};
static G load_graph(const std::string& p,u32 expected){
    std::ifstream f(p,std::ios::binary);if(!f)throw std::runtime_error("missing graph: "+p);
    G g;f.read((char*)&g.n,4);f.read((char*)&g.maxdeg,4);
    if(!f || g.n!=expected)throw std::runtime_error("graph n mismatch or truncated header: "+p);
    f.seekg(0,std::ios::end);const std::streamoff len=(std::streamoff)f.tellg();
    if(len<8+(std::streamoff)g.n*4 || (len-8-(std::streamoff)g.n*4)%4)throw std::runtime_error("bad CSR graph size: "+p);
    g.E=(u64)((len-8-(std::streamoff)g.n*4)/4);
    f.seekg(8);std::vector<u32> deg(g.n);f.read((char*)deg.data(),(std::streamsize)deg.size()*4);
    g.offsets.resize((size_t)g.n+1);u32 maxfound=0;
    for(u32 i=0;i<g.n;i++){g.offsets[i+1]=g.offsets[i]+deg[i];maxfound=std::max(maxfound,deg[i]);}
    if(g.offsets[g.n]!=g.E || maxfound>g.maxdeg)throw std::runtime_error("CSR header/degree mismatch: "+p);
    g.arcs.resize((size_t)g.E);f.read((char*)g.arcs.data(),(std::streamsize)g.E*4);
    if(!f)throw std::runtime_error("truncated graph arcs: "+p);
    for(u64 i=0;i<g.E;i++)if(g.arcs[(size_t)i]>=g.n)throw std::runtime_error("out-of-range graph target: "+p);
    return g;
}
static std::vector<int32_t> read_gt(const std::string&p,size_t nq,int k){
    std::ifstream f(p,std::ios::binary);if(!f)throw std::runtime_error("missing gold file: "+p);
    f.seekg(0,std::ios::end);if(f.tellg()!=(std::streamoff)(nq*(size_t)k*4))throw std::runtime_error("gold.raw file size mismatch");
    f.seekg(0);std::vector<int32_t> z(nq*(size_t)k);f.read((char*)z.data(),z.size()*4);
    if(!f)throw std::runtime_error("short gold file");
    return z;
}
static float l2(const float *a,const float*b,int d){
    float s=0.f;for(int j=0;j<d;j++){const float v=a[j]-b[j];s+=v*v;}return s;
}
struct Hit{float dist;u32 id;};
// Best/top tie ordering: distance ascending, ID ascending.
struct Better {bool operator()(const Hit&x,const Hit&y)const{return x.dist<y.dist || (x.dist==y.dist && x.id<y.id);}};
struct Worse {bool operator()(const Hit&x,const Hit&y)const{return x.dist>y.dist || (x.dist==y.dist && x.id>y.id);}};
struct Searcher {
    std::vector<u32> visited;u32 stamp=1;const G&g;const Fbin&X;u64 distances=0;
    explicit Searcher(const G& gg,const Fbin&xx):visited(gg.n,0),g(gg),X(xx){}
    std::vector<u32> run(const float*q,int ef,const std::vector<u32>&entries,int k){
        if(ef<k)throw std::runtime_error("ef must be >= k");
        if(++stamp==0){std::fill(visited.begin(),visited.end(),0);stamp=1;}
        std::priority_queue<Hit,std::vector<Hit>,Worse> frontier; // min distance at top
        std::priority_queue<Hit,std::vector<Hit>,Better> best; // max distance at top
        auto offer=[&](u32 v){
            if(visited[v]==stamp)return;
            visited[v]=stamp;
            float dd=l2(q,X.a.data()+(size_t)v*X.d,X.d);distances++;
            Hit h{dd,v};
            if((int)best.size()<ef || Better{}(h,best.top())){
                frontier.push(h);best.push(h);if((int)best.size()>ef)best.pop();
            }
        };
        for(u32 v:entries)offer(v);
        while(!frontier.empty()){
            Hit top=frontier.top();frontier.pop();
            if((int)best.size()>=ef && Worse{}(top,best.top()))break;
            for(u64 i=g.offsets[top.id];i<g.offsets[top.id+1];i++)offer(g.arcs[(size_t)i]);
        }
        std::vector<Hit> out;out.reserve(best.size());
        while(!best.empty()){out.push_back(best.top());best.pop();}
        std::sort(out.begin(),out.end(),Better{});
        std::vector<u32> ans;for(int i=0;i<k && i<(int)out.size();i++)ans.push_back(out[i].id);
        return ans;
    }
};
static std::vector<u32> load_entries(const std::string &p,u32 n){
    std::ifstream f(p,std::ios::binary);if(!f)throw std::runtime_error("missing entries file: "+p);
    f.seekg(0,std::ios::end);auto len=f.tellg();
    if(len<=0 || len%4 || len>400)throw std::runtime_error("entries must contain 1..100 int32 IDs");
    f.seekg(0);std::vector<u32> entries((size_t)len/4);
    f.read((char*)entries.data(),len);if(!f)throw std::runtime_error("short entries file");
    for(u32 v:entries)if(v>=n)throw std::runtime_error("entry vertex out of range");
    return entries;
}
int main(int argc,char**argv){
 try{
    std::string graph,base,queries,gold,entries,tag="untagged";int nq=1000,k=10,repeats=2;
    std::vector<int> efs{60,100,140,200,300,400};
    for(int i=1;i<argc;i++){
        std::string a=argv[i];auto v=[&](){if(i+1>=argc)throw std::runtime_error("missing value for "+a);return std::string(argv[++i]);};
        if(a=="--graph")graph=v();else if(a=="--base")base=v();else if(a=="--queries")queries=v();
        else if(a=="--gold")gold=v();else if(a=="--entries")entries=v();else if(a=="--tag")tag=v();
        else if(a=="--nq")nq=std::stoi(v());else if(a=="--k")k=std::stoi(v());
        else if(a=="--repeats")repeats=std::stoi(v());
        else if(a=="--efs"){
            efs.clear();while(i+1<argc && argv[i+1][0]!='-')efs.push_back(std::stoi(argv[++i]));
        }else throw std::runtime_error("unknown option: "+a);
    }
    if(graph.empty()||base.empty()||queries.empty()||gold.empty()||entries.empty()||nq<1||k!=10||repeats<1||repeats>12||efs.empty())throw std::runtime_error("usage: --graph G --base X.fbin --queries Q.fbin --gold gold.rawi32 --entries entries.rawu32 --tag NAME --nq 1000 --efs 60 100 140 200 300 400 [--repeats 2]");
    Fbin X=load_fbin(base),Q=load_fbin(queries,nq);
    if(X.d!=Q.d)throw std::runtime_error("base/query dimension mismatch");
    G g=load_graph(graph,X.n);
    auto gt=read_gt(gold,nq,k); auto ent=load_entries(entries,X.n);
    for(auto v:gt)if(v<0||(u32)v>=X.n)throw std::runtime_error("GT out of range");
    std::fprintf(stderr,"[H24] graph=%s n=%u edges=%llu maxdeg=%u bytes=%llu entries=%zu nq=%d\n",graph.c_str(),g.n,(unsigned long long)g.E,g.maxdeg,(unsigned long long)(8+4ULL*g.n+4*g.E),ent.size(),nq);
    Searcher search(g,X);
    for(int ef:efs){
        if(ef<k)throw std::runtime_error("ef smaller than k");
        auto measure=[&](int first,int count,u64 &hits,u64 &evals){
            hits=0;const u64 old=search.distances;
            for(int qi=first;qi<first+count;qi++){
                auto ans=search.run(Q.a.data()+(size_t)qi*Q.d,ef,ent,k);
                const int32_t*truth=gt.data()+(size_t)qi*k;
                for(u32 v:ans)for(int j=0;j<k;j++)if(v==(u32)truth[j]){hits++;break;}
            }
            evals=search.distances-old;
        };
        u64 w1,w2;measure(0,std::min(nq,32),w1,w2); // unreported cache warmup
        for(int r=1;r<=repeats;r++){
            u64 hits=0,ev=0;
            auto t0=std::chrono::steady_clock::now();measure(0,nq,hits,ev);
            double secs=std::chrono::duration<double>(std::chrono::steady_clock::now()-t0).count();
            std::printf("RESULT tag=%s ef=%d rep=%d nq=%d recall10=%.6f dist_per_query=%.2f qps=%.3f seconds=%.6f distances=%llu hits=%llu graph_edges=%llu graph_max_degree=%u\n",tag.c_str(),ef,r,nq,(double)hits/(nq*k),(double)ev/nq,nq/secs,secs,(unsigned long long)ev,(unsigned long long)hits,(unsigned long long)g.E,g.maxdeg);
            std::fflush(stdout);
        }
    }
    return 0;
 }catch(const std::exception&e){std::fprintf(stderr,"[H24 ERROR] %s\n",e.what());return 2;}
}
