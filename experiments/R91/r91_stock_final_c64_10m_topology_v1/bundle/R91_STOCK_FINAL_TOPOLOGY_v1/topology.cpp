#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <iomanip>
#include <limits>
#include <stdexcept>
#include <vector>
#include <array>
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
using U=uint32_t; using L=uint64_t;
void need(bool b,const char*s){if(!b)throw std::runtime_error(s);}
struct Map{int fd=-1;size_t size=0;const U* p=nullptr;Map(const char* path){fd=open(path,O_RDONLY|O_NOFOLLOW);need(fd>=0,"open");struct stat st{};need(!fstat(fd,&st)&&S_ISREG(st.st_mode)&&st.st_size>=8&&st.st_size%4==0,"file size");size=st.st_size;void*q=mmap(nullptr,size,PROT_READ,MAP_PRIVATE,fd,0);need(q!=MAP_FAILED,"mmap");p=(const U*)q;}~Map(){if(p)munmap((void*)p,size);if(fd>=0)close(fd);}};
struct Comp{L n=0,largest=0,singletons=0,sum=0;void add(L s){++n;largest=std::max(largest,s);singletons+=s==1;sum+=s;}void print(){std::cout<<"{\"count\":"<<n<<",\"largest\":"<<largest<<",\"singletons\":"<<singletons<<",\"vertices\":"<<sum<<"}";}};
void hist(const std::vector<L>&h,L n){L c=0,sum=0;size_t mn=0,mx=h.size()-1;while(mn<h.size()&&!h[mn])++mn;while(mx&&!h[mx])--mx;auto quant=[&](L pct){L rank=(n*pct+99)/100,acc=0;for(size_t i=0;i<h.size();i++){acc+=h[i];if(acc>=rank)return i;}throw std::runtime_error("quantile");};for(size_t i=0;i<h.size();i++){c+=h[i];sum+=i*h[i];}need(c==n,"hist count");std::cout<<"{\"min\":"<<mn<<",\"max\":"<<mx<<",\"mean\":"<<double(sum)/n<<",\"p50\":"<<quant(50)<<",\"p95\":"<<quant(95)<<",\"p99\":"<<quant(99)<<",\"zero\":"<<h[0]<<",\"histogram\":[";bool first=true;for(size_t i=0;i<h.size();i++)if(h[i]){if(!first)std::cout<<",";first=false;std::cout<<"["<<i<<","<<h[i]<<"]";}std::cout<<"]}";}
int main(int argc,char**argv){try{need(argc==4,"usage graph N arcs");uint16_t endian=1;need(*reinterpret_cast<char*>(&endian)==1,"little endian required");L wantN=std::stoull(argv[2]),wantM=std::stoull(argv[3]);need(wantN>0&&wantN<UINT32_MAX&&wantM<UINT32_MAX,"bounds");Map f(argv[1]);U n=f.p[0],cap=f.p[1];need(n==wantN&&cap==64,"header");need(f.size==8+4*wantN+4*wantM,"exact file bytes");const U*d=f.p+2,*e=d+n;std::vector<U> off(n+1,0),in(n,0);std::vector<L> oh(65,0);L m=0;for(U u=0;u<n;u++){need(d[u]<=64,"degree cap");m+=d[u];need(m<=wantM,"arc overflow");off[u+1]=m;++oh[d[u]];}need(m==wantM,"arcs");
// validate every arc and every row, then count incoming degrees.
for(U u=0;u<n;u++){std::array<U,64> tmp{};U k=0;for(U j=off[u];j<off[u+1];j++){U w=e[j];need(w<n&&w!=u,"invalid ID/self loop");++in[w];tmp[k++]=w;}std::sort(tmp.begin(),tmp.begin()+k);need(std::adjacent_find(tmp.begin(),tmp.begin()+k)==tmp.begin()+k,"duplicate edge");}
U maxin=*std::max_element(in.begin(),in.end());std::vector<L> ih(L(maxin)+1,0);std::vector<U> ro(n+1,0);for(U u=0;u<n;u++){++ih[in[u]];ro[u+1]=ro[u]+in[u];}need(ro[n]==m,"reverse count");std::vector<U> rev(m);for(U u=0;u<n;u++)in[u]=ro[u];for(U u=0;u<n;u++)for(U j=off[u];j<off[u+1];j++)rev[in[e[j]]++]=u;for(U u=0;u<n;u++)need(in[u]==ro[u+1],"reverse fill");std::vector<U>().swap(in);
// Kosaraju: finish order with iterative DFS, then reverse DFS.
std::vector<uint8_t> seen(n,0);std::vector<U> order;order.reserve(n);struct Frame{U u,j;};std::vector<Frame> stack;for(U u=0;u<n;u++){if(seen[u])continue;seen[u]=1;stack.push_back({u,off[u]});while(!stack.empty()){auto &t=stack.back();if(t.j==off[t.u+1]){order.push_back(t.u);stack.pop_back();continue;}U w=e[t.j++];if(!seen[w]){seen[w]=1;stack.push_back({w,off[w]});}}}need(order.size()==n,"finish order");std::vector<Frame>().swap(stack);std::fill(seen.begin(),seen.end(),0);Comp scc,wcc;std::vector<U> q;q.reserve(n);for(auto it=order.rbegin();it!=order.rend();++it){U u=*it;if(seen[u])continue;q.clear();q.push_back(u);seen[u]=1;for(size_t i=0;i<q.size();i++){U v=q[i];for(U j=ro[v];j<ro[v+1];j++){U w=rev[j];if(!seen[w]){seen[w]=1;q.push_back(w);}}}scc.add(q.size());}need(scc.sum==n,"SCC vertices");std::vector<U>().swap(order);
// WCC via undirected traversal of both adjacency lists.
std::fill(seen.begin(),seen.end(),0);for(U u=0;u<n;u++){if(seen[u])continue;q.clear();q.push_back(u);seen[u]=1;for(size_t i=0;i<q.size();i++){U v=q[i];for(U j=off[v];j<off[v+1];j++){U w=e[j];if(!seen[w]){seen[w]=1;q.push_back(w);}}for(U j=ro[v];j<ro[v+1];j++){U w=rev[j];if(!seen[w]){seen[w]=1;q.push_back(w);}}}wcc.add(q.size());}need(wcc.sum==n&&wcc.n<=scc.n&&wcc.largest>=scc.largest,"component consistency");std::cout<<std::setprecision(17)<<"{\"nodes\":"<<n<<",\"arcs\":"<<m<<",\"bytes\":"<<f.size<<",\"degree_cap\":"<<cap<<",\"out_degree\":";hist(oh,n);std::cout<<",\"in_degree\":";hist(ih,n);std::cout<<",\"scc\":";scc.print();std::cout<<",\"wcc\":";wcc.print();std::cout<<",\"status\":\"TOPOLOGY_PASS\"}\n";return 0;}catch(const std::exception&e){std::cerr<<"TOPOLOGY_HOLD "<<e.what()<<"\n";return 2;}}
