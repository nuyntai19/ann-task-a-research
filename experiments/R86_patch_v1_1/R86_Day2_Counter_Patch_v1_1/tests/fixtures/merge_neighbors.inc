template<typename rangeType>
void merge_neighbors(const size_t i, const rangeType& r) {
#if defined(R86_COUNTERS) && R86_COUNTERS
  r86::HashWork work; // All inner-loop counting is local to this merge call.
#endif
  locks[i].Lock();

  const size_t base   = i * (kMaxDegree + 1);
  T* const sentinel   = &tables[base];
  T* const begin      = &tables[base + 1];

  size_t deg          = static_cast<size_t>(sentinel->point_id);
  T* end              = begin + deg;

  auto to_dt = [](Eigen::bfloat16 x) -> distanceType {
    return static_cast<distanceType>(static_cast<float>(x));
  };

  size_t       max_idx = static_cast<size_t>(sentinel->hash);
  distanceType max_val = to_dt(sentinel->norm);

  auto set_worst = [&](size_t idx, distanceType v) {
    max_idx = idx; max_val = v;
    sentinel->hash = static_cast<uint16_t>(idx);
    sentinel->norm = Eigen::bfloat16(v);
  };

  auto recompute_worst = [&]() {
#if defined(R86_COUNTERS) && R86_COUNTERS
    work.hash_worst_scan += static_cast<std::uint64_t>(deg);
    work.hash_worst_compares += (deg>0 ? static_cast<std::uint64_t>(deg-1) : 0);
#endif
    if (deg == 0) { set_worst(0, distanceType(0)); return; }
    size_t mi = 0;
    distanceType mv = to_dt(begin[0].norm);
    for (size_t j = 1; j < deg; ++j) {
      const distanceType v = to_dt(begin[j].norm);
      if (v > mv) { mv = v; mi = j; }
    }
    set_worst(mi, mv);
  };

#if defined(R86_COUNTERS) && R86_COUNTERS
  struct Cmp {
    std::uint64_t* comparisons;
    bool operator()(const T& a, uint16_t b) const {
      ++*comparisons;
      return a.hash < b;
    }
  } cmp{&work.hash_lb_compares};
#else
  struct Cmp {
    bool operator()(const T& a, uint16_t b) const { return a.hash < b; }
  } cmp;
#endif

  for (const auto& cand : r) {
    const indexType    pid  = cand.first;
    const distanceType dist = cand.second;
#if defined(R86_COUNTERS) && R86_COUNTERS
    ++work.merge_attempts;
    if (deg == kMaxDegree) {
      ++work.hash_full;
      ++work.hash_bound_compares;
    }
#endif
    // Early break; no hash is computed for this visited candidate.
    if (deg == kMaxDegree && dist >= max_val) {
#if defined(R86_COUNTERS) && R86_COUNTERS
      ++work.hash_early_break;
      ++work.hash_reject;
#endif
      break;
    }

#if defined(R86_COUNTERS) && R86_COUNTERS
    ++work.hash_compute;
#endif
    const uint16_t cand_hash = static_cast<uint16_t>(H.relative_hash(i, pid));
    T* pos_ptr = std::lower_bound(begin, end, cand_hash, cmp);
    size_t pos = static_cast<size_t>(pos_ptr - begin);

    // Same ID is a separate class even when its rounded bf16 distance is overwritten.
    if (pos < deg && pos_ptr->hash == cand_hash) {
#if defined(R86_COUNTERS) && R86_COUNTERS
      const bool is_same_id = pos_ptr->point_id == pid;
      if(is_same_id) ++work.collision_same_id;
      else ++work.collision_diff_id;
#endif
      const distanceType old = to_dt(pos_ptr->norm);
      if (old > dist) {
#if defined(R86_COUNTERS) && R86_COUNTERS
        ++work.hash_slot_writes;
        if (is_same_id) ++work.hash_same_id_rewrite;
        else {
          ++work.hash_accept;
          ++work.hash_replace;
          ++work.hash_diff_collision_rewrite;
        }
#endif
        pos_ptr->point_id = pid;
        pos_ptr->norm     = Eigen::bfloat16(dist);
        if (pos == max_idx) recompute_worst();
      } else {
#if defined(R86_COUNTERS) && R86_COUNTERS
        if (!is_same_id) {
          ++work.hash_reject;
          ++work.hash_diff_collision_reject;
        }
#endif
      }
      continue;
    }

    if (deg < kMaxDegree) {
#if defined(R86_COUNTERS) && R86_COUNTERS
      ++work.hash_accept;
      ++work.hash_insert_not_full;
      ++work.hash_slot_writes;
      work.hash_moves += static_cast<std::uint64_t>(end - pos_ptr);
#endif
      // make room
      std::move_backward(pos_ptr, end, end + 1);
      pos_ptr->point_id = pid;
      pos_ptr->norm     = Eigen::bfloat16(dist);
      pos_ptr->hash     = cand_hash;

      ++deg; ++end;
      if (deg == 1 || dist > max_val) {
        set_worst(pos, dist);
      } else if (pos <= max_idx) {
        set_worst(max_idx + 1, max_val);
      }
    } else {
#if defined(R86_COUNTERS) && R86_COUNTERS
      ++work.hash_accept;
      ++work.hash_replace;
      ++work.hash_replace_full;
      ++work.hash_slot_writes;
      if (max_idx < pos) {
        work.hash_moves += static_cast<std::uint64_t>(pos - max_idx - 1);
      } else if (pos < max_idx) {
        work.hash_moves += static_cast<std::uint64_t>(max_idx - pos);
      }
#endif
      // full: replace worst while keeping hash order
      if (max_idx < pos) {
        std::move(begin + max_idx + 1, begin + pos, begin + max_idx);
        --pos;
      } else if (pos < max_idx) {
        std::move_backward(begin + pos, begin + max_idx, begin + max_idx + 1);
      }
      T* write = begin + pos;
      write->point_id = pid;
      write->norm     = Eigen::bfloat16(dist);
      write->hash     = cand_hash;
      recompute_worst();
    }
  }

  sentinel->point_id = static_cast<indexType>(deg);
  locks[i].Unlock();
#if defined(R86_COUNTERS) && R86_COUNTERS
  r86::record_hash_work(work); // Flush once, outside lock.
#endif
}
