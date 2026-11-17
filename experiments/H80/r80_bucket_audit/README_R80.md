# R80 — Bucket ownership / read-only evidence kit

Research target: PiPNN `algorithms/PipNN/pipnn.h` (pinned research snapshot
`d1b5b1a44122a6ce667ece548ea95a3b12df2d19`), especially the
`MergeBuckets` priority-queue extraction at lines 113–160.

## What has been shown (assistant isolated C++ fixture, NOT a PiPNN build)

`r80_heap_drain_probe.cc` models **only the leftover bucket extraction**:

- PiPNN-like baseline: `remaining.emplace_back(pq.top()); pq.pop();`
- Alternative: a vector heap with `std::pop_heap`, then move the popped tail
  into `remaining` (no bucket-element deep copy).

For four seeds and 12,000 synthetic buckets, final bucket sequences are
byte-for-byte equal (including size ties); source-like path copies about
9.2 MB of bucket IDs per seed at this drain step, alternative copies 0 bytes
at this step. A separate ASan+UBSan run for 4,000 buckets passed. Timing in
this fixture is neither a production benchmark nor an estimate of PiPNN
wall time or RSS. The full `MergeBuckets` routine additionally merges
small buckets and uses Parlay `remove_duplicates`, which this fixture
**does not** implement.

## Safe Ubuntu commands

Download the archive into `~/Downloads`, then:

```bash
mkdir -p ~/ann-task-a/experiments/H80
cd ~/ann-task-a/experiments/H80
tar -xzf ~/Downloads/r80_bucket_audit.tar.gz
cd r80_bucket_audit
python3 r80_readonly_bucket_logs.py --selftest
python3 r80_readonly_bucket_logs.py --root ~/ann-task-a/experiments/H70 --max-files 2000 --limit 40
c++ -std=c++17 -O2 -Wall -Wextra -Werror r80_heap_drain_probe.cc -o r80_heap_drain_probe
./r80_heap_drain_probe 12000
```

Only the last two commands create an executable, **inside H80**. No source,
benchmark binary, graph or dataset in H70 is edited. The parser is read-only:
no files are written, and it skips `build-r70`, `pipnn-clean-*`, R78,
symlinks and files over 12 MB. Its output reports existing *final bucket*
statistics per log file; these do NOT measure intermediate `priority_queue`
copy bytes or live memory. The search is bounded by `--max-files`.

## GO / NO-GO protocol for future production adaptation

- First compare exact output bucket *order* plus bucket membership through a
  full `MergeBuckets` clone using real Parlay `remove_duplicates`, with seed
  and threshold settings pinned. Merely comparing multisets is insufficient
  because recursion and tie ordering affect subsequent steps.
- Preserve `std::priority_queue` size comparator and push/pop order. A bare
  `std::move(pq.top())` is invalid because `top()` returns `const&`.
- Only if a complete native test and copy/allocation instrumentation identify
  meaningful traffic should a new isolated build be justified. Do not
  touch H70 A/B/C/D or immediately run SIFT1M.
- A copy-free heap is a generic C++ storage optimization, not a new ANN
  algorithm. It is a systems candidate to supplement H17+Two-Tier if
  measurable on realistic input.
