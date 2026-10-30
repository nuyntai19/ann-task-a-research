#pragma once
// H25-R1 native PiPNN experimental hook. OFFLINE INTERVENTION only.
// No new distance computations; replacement distance is read from local dist_mat.
// Fail closed when sampled H18 leaf + Top2 pair does not match native build.
#include <atomic>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <mutex>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>

namespace h25_r1 {
struct RowKey {
  uint32_t leaf, src;
  bool operator==(const RowKey& o) const {return leaf==o.leaf && src==o.src;}
};
struct EdgeKey {
  uint32_t leaf,src,old_dst;
  bool operator==(const EdgeKey& o) const {return leaf==o.leaf && src==o.src && old_dst==o.old_dst;}
};
struct Hash {
  static uint64_t splitmix64(uint64_t x) {
    x+=0x9e3779b97f4a7c15ULL;
    x=(x^(x>>30))*0xbf58476d1ce4e5b9ULL;
    x=(x^(x>>27))*0x94d049bb133111ebULL;
    return x^(x>>31);
  }
  size_t operator()(RowKey k)const{return size_t(splitmix64((uint64_t(k.leaf)<<32)|k.src));}
  size_t operator()(EdgeKey k)const{return size_t(splitmix64((uint64_t(k.leaf)<<32)|k.src)^splitmix64(k.old_dst));}
};
struct Record {uint32_t a,b,c,d;};
struct Header {char magic[8]; uint64_t count,n,leaves;};
static_assert(sizeof(Header)==32,"Header must be 32 bytes");
static_assert(sizeof(Record)==16,"Record must be 16 bytes");
struct State {
  std::once_flag once;
  bool on=false;
  uint64_t n=0,nleaves=0;
  std::unordered_map<RowKey,std::pair<uint32_t,uint32_t>,Hash> rows;
  std::unordered_map<EdgeKey,uint32_t,Hash> patches;
  std::unordered_set<uint32_t> chosen_leaves;
  std::atomic<uint64_t> checked{0};
  std::atomic<uint64_t> applied{0};
};
inline State& state(){static State s;return s;}
inline void fail(const std::string& m){
  std::cerr << "H25_R1_FAIL_CLOSED: " << m << std::endl;
  throw std::runtime_error("H25-R1 gate failed: "+m);
}
template <class F>
inline void load_file(const char* path,const char expected[8],uint64_t& n,uint64_t& nleaves,
                      const F& callback) {
  std::ifstream f(path,std::ios::binary);
  if(!f)fail(std::string("cannot open ")+path);
  Header h{};
  if(!f.read(reinterpret_cast<char*>(&h),sizeof(h)))fail(std::string("bad header: ")+path);
  if(std::memcmp(h.magic,expected,8)!=0)fail(std::string("magic mismatch: ")+path);
  if(h.count>1'000'000ULL || h.n==0 || h.leaves==0)fail("invalid header fields");
  if(n && n!=h.n)fail("record n mismatch");
  if(nleaves && nleaves!=h.leaves)fail("record leaf-count mismatch");
  n=h.n;nleaves=h.leaves;
  for(uint64_t i=0;i<h.count;++i){
    Record r{};
    if(!f.read(reinterpret_cast<char*>(&r),sizeof(r)))fail("truncated record data");
    if(r.a>=nleaves || r.b>=n || r.c>=n || r.d>=n)fail("record ID out of range");
    callback(r);
  }
  char tail;
  if(f.get(tail))fail(std::string("extra trailing bytes: ")+path);
  if(!f.eof())fail(std::string("read failure: ")+path);
}
inline void init(){
  State& s=state();
  std::call_once(s.once,[&](){
    const char* rows=std::getenv("H25_R1_ROWS");
    const char* patch=std::getenv("H25_R1_PATCH");
    if(!rows && !patch)return;
    if(!rows || !patch)fail("must supply both H25_R1_ROWS and H25_R1_PATCH");
    load_file(rows,"H25R1C01",s.n,s.nleaves,[&](Record r){
      if(r.b==r.c || r.b==r.d || r.c==r.d)fail("invalid expected Top2 row");
      auto good=s.rows.emplace(RowKey{r.a,r.b},std::make_pair(r.c,r.d)).second;
      if(!good)fail("duplicate expected (leaf,source) control");
      s.chosen_leaves.insert(r.a);
    });
    load_file(patch,"H25R1P01",s.n,s.nleaves,[&](Record r){
      if(r.b==r.c || r.b==r.d || r.c==r.d)fail("invalid patch endpoint");
      if(!s.chosen_leaves.count(r.a))fail("patch leaf missing from expected controls");
      auto it=s.rows.find(RowKey{r.a,r.b});
      if(it==s.rows.end() || (it->second.first!=r.c && it->second.second!=r.c))
        fail("patch original destination not in expected Top2 row");
      auto good=s.patches.emplace(EdgeKey{r.a,r.b,r.c},r.d).second;
      if(!good)fail("duplicate patch (leaf,src,old) key");
    });
    s.on=true;
    std::cerr << "H25_R1_LOAD_OK: checks=" << s.rows.size()
              << " selected_leaves=" << s.chosen_leaves.size()
              << " patch_count=" << s.patches.size() << std::endl;
  });
}
inline bool enabled(){init();return state().on;}
inline bool target_leaf(uint32_t leaf){
  init();auto& s=state();return s.on && s.chosen_leaves.count(leaf)!=0;
}
inline void check_row(uint32_t leaf,uint32_t src,uint32_t d0,uint32_t d1){
  auto& s=state();
  auto it=s.rows.find(RowKey{leaf,src});
  if(it==s.rows.end())fail("selected leaf has unexpected source ID; leaf="+std::to_string(leaf)+",src="+std::to_string(src));
  auto expected=it->second;
  if(!((expected.first==d0 && expected.second==d1)||(expected.first==d1 && expected.second==d0)))
    fail("Top2 mismatch; leaf="+std::to_string(leaf)+",src="+std::to_string(src));
  s.checked.fetch_add(1,std::memory_order_relaxed);
}
inline uint32_t replacement(uint32_t leaf,uint32_t src,uint32_t old_dst){
  auto& s=state();
  auto it=s.patches.find(EdgeKey{leaf,src,old_dst});
  if(it==s.patches.end())return old_dst;
  s.applied.fetch_add(1,std::memory_order_relaxed);
  return it->second;
}
inline void verify(){
  init();auto& s=state();
  if(!s.on)return;
  auto checked=s.checked.load();auto applied=s.applied.load();
  std::cerr << "H25_R1_VERIFY: checked_rows=" << checked << "/" << s.rows.size()
            << " applied_patches=" << applied << "/" << s.patches.size() << std::endl;
  if(checked!=s.rows.size() || applied!=s.patches.size())
    fail("row count / applied count mismatch: wrong capture, leaf schedule or builder configuration");
  std::cerr << "H25_R1_VERIFY_PASS" << std::endl;
}
} // namespace h25_r1
