// R78.3 experimental FastShift variant — source-derived from R78 S1.
// DO NOT replace PiPNN or original S1 header; test-only isolated variant.
// Standalone mode tests the SAME segmented implementation with mock dependencies.
// Production mode requires the original PiPNN 'utils/graph.h' (do not replace it).
#pragma once
#ifdef R78_STANDALONE
#include "r78_standalone_compat.h"
#else
#include "utils/graph.h"
#endif
#include <algorithm>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <limits>
#include <memory>
#include <mutex>
#include <new>
#include <stdexcept>
#include <type_traits>
#include <iterator>
#include <utility>

namespace parlayANN {

template <class Index_, class Distance_, class SketchHash>
class R78SegmentedFastShiftLSHGraph {
public:
  using indexType = Index_;
  using distanceType = Distance_;
  using T = LSHCandidate<indexType, distanceType>;
  static constexpr size_t kBase = 32;
  static constexpr size_t kMid = 32;
  static constexpr size_t kHigh = 96;
  static constexpr size_t kCapacity = kBase + kMid + kHigh;
  static constexpr size_t kChunkRows = 1024;

private:
  size_t n_;
  size_t cap_;
  SketchHash &hash_;
  std::unique_ptr<absl::Mutex[]> locks_;
  T *base_ = nullptr;                // n x (1 sentinel + 32)
  T **mid_ = nullptr;                // nullable n pointers to 32-slot segments
  T **high_ = nullptr;               // nullable n pointers to 96-slot segments
  std::unique_ptr<std::atomic<T*>[]> mid_chunks_, high_chunks_;
  size_t max_chunks_ = 0;
  std::atomic<size_t> mid_count_{0}, high_count_{0};
  std::mutex mid_alloc_lock_, high_alloc_lock_;

  static T* aligned_array(size_t count, size_t align=64) {
    if (count > (std::numeric_limits<size_t>::max)() / sizeof(T))
      throw std::bad_alloc();
    const size_t bytes = count * sizeof(T);
    if (bytes > (std::numeric_limits<size_t>::max)() - (align - 1))
      throw std::bad_alloc();
    size_t rounded = ((bytes + align - 1) / align) * align;
    if (rounded == 0) rounded = align;
    T* result = static_cast<T*>(std::aligned_alloc(align, rounded));
    if (!result) throw std::bad_alloc();
    return result;
  }

  T* allocate_segment(std::atomic<size_t>& count,
                      std::unique_ptr<std::atomic<T*>[]>& chunks,
                      std::mutex& global_lock,
                      size_t width) {
    const size_t ordinal = count.fetch_add(1, std::memory_order_relaxed);
    if (ordinal >= n_) throw std::overflow_error("R78: segment count exceeds n");
    const size_t chunk = ordinal / kChunkRows;
    const size_t sub = ordinal % kChunkRows;
    T* block = chunks[chunk].load(std::memory_order_acquire);
    if (!block) {
      std::lock_guard<std::mutex> g(global_lock);
      block = chunks[chunk].load(std::memory_order_relaxed);
      if (!block) {
        block = aligned_array(kChunkRows * width);
        chunks[chunk].store(block, std::memory_order_release);
      }
    }
    return block + sub * width;
  }

  T* sentinel(size_t i) { return base_ + i * (kBase + 1); }
  const T* sentinel(size_t i) const { return base_ + i * (kBase + 1); }

  T& slot(size_t i, size_t j) {
    if (j < kBase) return base_[i*(kBase+1)+j+1];
    if (j < kBase+kMid) return mid_[i][j-kBase];
    return high_[i][j-kBase-kMid];
  }
  const T& slot(size_t i, size_t j) const {
    if (j < kBase) return base_[i*(kBase+1)+j+1];
    if (j < kBase+kMid) return mid_[i][j-kBase];
    return high_[i][j-kBase-kMid];
  }

  // Shift logical entries [pos, end) RIGHT by one, writing positions [pos+1, end].
  // Process from high to low so segment-crossing source values are still intact.
  void shift_right(size_t i, size_t pos, size_t end) {
    static_assert(std::is_trivially_copyable<T>::value, "FastShift requires trivially copyable PiPNN candidate");
    if (pos >= end) return;
    T* base_row=sentinel(i);
    if (end >= 65) {
      const size_t start=std::max(size_t(65),pos+1);
      if (start<=end) {
        std::memmove(high_[i]+(start-64),high_[i]+(start-65),(end-start+1)*sizeof(T));
      }
    }
    if (pos <= 63 && end >= 64) high_[i][0]=mid_[i][31];
    if (end >= 33) {
      const size_t start=std::max(size_t(33),pos+1);
      const size_t last=std::min(end,size_t(63));
      if (start<=last) {
        std::memmove(mid_[i]+(start-32),mid_[i]+(start-33),(last-start+1)*sizeof(T));
      }
    }
    if (pos <= 31 && end >= 32) mid_[i][0]=base_row[32];
    const size_t last=std::min(end,size_t(31));
    if (pos<last) {
      std::memmove(base_row+(pos+2),base_row+(pos+1),(last-pos)*sizeof(T));
    }
  }
  // Delete logical element at low by moving [low+1, upper) LEFT by one.
  // The caller overwrites upper-1 after this move, if needed.
  void shift_left(size_t i, size_t low, size_t upper) {
    static_assert(std::is_trivially_copyable<T>::value, "FastShift requires trivially copyable PiPNN candidate");
    if (low+1>=upper) return;
    const size_t last=upper-2;
    T* base_row=sentinel(i);
    if (low<=30) {
      const size_t end=std::min(last,size_t(30));
      if (low<=end) std::memmove(base_row+low+1,base_row+low+2,(end-low+1)*sizeof(T));
    }
    if (low<=31 && last>=31) base_row[32]=mid_[i][0];
    const size_t mid_start=std::max(low,size_t(32));
    const size_t mid_end=std::min(last,size_t(62));
    if (mid_start<=mid_end) {
      std::memmove(mid_[i]+(mid_start-32),mid_[i]+(mid_start-31),(mid_end-mid_start+1)*sizeof(T));
    }
    if (low<=63 && last>=63) mid_[i][31]=high_[i][0];
    const size_t high_start=std::max(low,size_t(64));
    const size_t high_end=std::min(last,size_t(158));
    if (high_start<=high_end) {
      std::memmove(high_[i]+(high_start-64),high_[i]+(high_start-63),(high_end-high_start+1)*sizeof(T));
    }
  }

  void expand_if_needed(size_t i, size_t deg) {
    if (deg == kBase && !mid_[i]) {
      T* ptr = allocate_segment(mid_count_, mid_chunks_, mid_alloc_lock_, kMid);
      mid_[i] = ptr; // per-node writer lock already acquired
    }
    if (deg == kBase + kMid && !high_[i]) {
      T* ptr = allocate_segment(high_count_, high_chunks_, high_alloc_lock_, kHigh);
      high_[i] = ptr;
    }
  }

public:
  R78SegmentedFastShiftLSHGraph(size_t n, size_t logical_cap, SketchHash& h, bool allocate=true)
    : n_(n), cap_(logical_cap), hash_(h) {
    if (cap_ != kCapacity) throw std::invalid_argument("R78 only supports C160");
    if (allocate) allocate_graph(n);
  }
  R78SegmentedFastShiftLSHGraph(const R78SegmentedFastShiftLSHGraph&) = delete;
  R78SegmentedFastShiftLSHGraph& operator=(const R78SegmentedFastShiftLSHGraph&) = delete;

  void allocate_graph(size_t n) {
    if (n != n_ || n == 0 || base_ || mid_ || high_)
      throw std::invalid_argument("R78: invalid/repeated allocate_graph");
    max_chunks_ = (n + kChunkRows - 1)/kChunkRows;
    std::unique_ptr<absl::Mutex[]> new_locks(new absl::Mutex[n]);
    std::unique_ptr<T*[]> new_mid(new T*[n]());
    std::unique_ptr<T*[]> new_high(new T*[n]());
    std::unique_ptr<std::atomic<T*>[]> new_mid_chunks(new std::atomic<T*>[max_chunks_]);
    std::unique_ptr<std::atomic<T*>[]> new_high_chunks(new std::atomic<T*>[max_chunks_]);
    for (size_t k=0;k<max_chunks_;++k) {
      new_mid_chunks[k].store(nullptr, std::memory_order_relaxed);
      new_high_chunks[k].store(nullptr, std::memory_order_relaxed);
    }
    if (n > (std::numeric_limits<size_t>::max)()/(kBase+1))
      throw std::bad_alloc();
    T* new_base = aligned_array(n * (kBase+1));
    base_=new_base;
    locks_=std::move(new_locks);
    mid_=new_mid.release(); high_=new_high.release();
    mid_chunks_=std::move(new_mid_chunks);
    high_chunks_=std::move(new_high_chunks);
    parlay::parallel_for(0, n, [&](size_t i) {
      T* row=sentinel(i);
      row->point_id=0;
      row->norm=Eigen::bfloat16(0.f);
      row->hash=0;
    });
  }

  ~R78SegmentedFastShiftLSHGraph() {
    if (mid_chunks_) for(size_t k=0;k<max_chunks_;++k)
      std::free(mid_chunks_[k].load(std::memory_order_relaxed));
    if (high_chunks_) for(size_t k=0;k<max_chunks_;++k)
      std::free(high_chunks_[k].load(std::memory_order_relaxed));
    std::free(base_);
    delete[] mid_;
    delete[] high_;
  }

  size_t size() const { return n_; }
  size_t logical_capacity() const {return cap_;}
  // Nominal allocated bytes, not process RSS; excludes locks/allocator overhead.
  size_t nominal_candidate_bytes() const {
    if (!base_) return 0;
    const size_t m=(mid_count_.load()+kChunkRows-1)/kChunkRows;
    const size_t h=(high_count_.load()+kChunkRows-1)/kChunkRows;
    return n_*(kBase+1)*sizeof(T) + n_*2*sizeof(T*)
       + m*kChunkRows*kMid*sizeof(T) + h*kChunkRows*kHigh*sizeof(T);
  }
  size_t mid_promotions() const {return mid_count_.load();}
  size_t high_promotions() const {return high_count_.load();}
  bool has_mid(size_t i) const {return mid_[i]!=nullptr;}
  bool has_high(size_t i) const {return high_[i]!=nullptr;}
  size_t degree(size_t i) const {return static_cast<size_t>(sentinel(i)->point_id);}
  Eigen::bfloat16 get_furthest(size_t i) const {return sentinel(i)->norm;}
  size_t get_furthest_index(size_t i) const {return sentinel(i)->hash;}
  const T& get_candidate(size_t i, size_t j) const {return slot(i,j);}
  T& get_candidate(size_t i,size_t j) {return slot(i,j);}
  const T& get_sentinel(size_t i) const {return *sentinel(i);}
  void finalize() {}

  struct NeighborView {
    const R78SegmentedFastShiftLSHGraph *owner;
    size_t row;
    size_t count;
    struct Iterator {
      using iterator_category = std::forward_iterator_tag;
      using value_type = T;
      using difference_type = std::ptrdiff_t;
      using reference = const T&;
      using pointer = const T*;
      const R78SegmentedFastShiftLSHGraph* owner;
      size_t row, pos;
      reference operator*() const {return owner->slot(row,pos);}
      pointer operator->() const {return &owner->slot(row,pos);}
      Iterator& operator++() {++pos;return *this;}
      Iterator operator++(int) {auto old=*this;++(*this);return old;}
      bool operator==(const Iterator& rhs) const {
        return owner==rhs.owner && row==rhs.row && pos==rhs.pos;
      }
      bool operator!=(const Iterator& rhs) const {return !(*this==rhs);}
    };
    Iterator begin() const {return {owner,row,0};}
    Iterator end() const {return {owner,row,count};}
  };
  NeighborView Neighbors(size_t i) const { return {this,i,degree(i)}; }

  template <class Range>
  void merge_neighbors(size_t i, const Range& r) {
    absl::MutexLock g(&locks_[i]);
    T* state=sentinel(i);
    size_t deg=static_cast<size_t>(state->point_id);
    size_t max_idx=static_cast<size_t>(state->hash);
    const auto to_dt=[](Eigen::bfloat16 v) -> distanceType {
      return static_cast<distanceType>(static_cast<float>(v));
    };
    distanceType max_val=to_dt(state->norm);
    const auto set_worst=[&](size_t idx, distanceType value) {
      max_idx=idx; max_val=value;
      state->hash=static_cast<uint16_t>(idx);
      state->norm=Eigen::bfloat16(static_cast<float>(value));
    };
    const auto recompute_worst=[&]() {
      if (deg==0){set_worst(0,distanceType(0));return;}
      size_t idx=0;
      distanceType val=to_dt(slot(i,0).norm);
      for(size_t j=1;j<deg;++j) {
        const distanceType v=to_dt(slot(i,j).norm);
        if(v>val) {idx=j;val=v;}
      }
      set_worst(idx,val);
    };
    for(const auto& cand:r) {
      const indexType pid=cand.first;
      const distanceType dist=cand.second;
      if (deg==cap_ && dist>=max_val) break;
      const uint16_t new_hash=static_cast<uint16_t>(hash_.relative_hash(i,pid));
      size_t low=0,high=deg;
      while(low<high) {
        const size_t m=low+(high-low)/2;
        if(slot(i,m).hash<new_hash) low=m+1;
        else high=m;
      }
      size_t pos=low;
      if(pos<deg && slot(i,pos).hash==new_hash) {
        const distanceType old=to_dt(slot(i,pos).norm);
        if(old>dist) {
          slot(i,pos).point_id=pid;
          slot(i,pos).norm=Eigen::bfloat16(static_cast<float>(dist));
          if(pos==max_idx)recompute_worst();
        }
        continue;
      }
      if(deg<cap_) {
        expand_if_needed(i,deg); // alloc before any row mutation
        shift_right(i,pos,deg);
        T& out=slot(i,pos);
        out.point_id=pid;
        out.norm=Eigen::bfloat16(static_cast<float>(dist));
        out.hash=new_hash;
        ++deg;
        if(deg==1 || dist>max_val)set_worst(pos,dist);
        else if(pos<=max_idx)set_worst(max_idx+1,max_val);
      } else {
        if(max_idx<pos) {
          shift_left(i,max_idx,pos);
          --pos;
        } else if(pos<max_idx) {
          shift_right(i,pos,max_idx);
        }
        T& out=slot(i,pos);
        out.point_id=pid;
        out.norm=Eigen::bfloat16(static_cast<float>(dist));
        out.hash=new_hash;
        recompute_worst();
      }
    }
    state->point_id=static_cast<indexType>(deg);
  }
};
}
