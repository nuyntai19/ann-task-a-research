# R83.2 Compact Fanout standalone microbenchmark

This is a diagnostic-only controlled pilot, not a PiPNN BUILD or ANN algorithm. It uses the pinned Parlay library to compare (A) materialized `(leader,point_id)` pairs vs (B) `uint16_t leader` plus delayed pair reconstruction, with synthetic deterministic leader choices. Parity is checked using an order-sensitive checksum over every resulting bucket.

The R83.2 Python runner requires H70 PiPNN HEAD 443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd and `~/ann-task-a/src/PiPNN/parlaylib` HEAD 7cdb4cae8f020525f5eb4ad82e2565d1e38cfbc3. No source in H70 or H80 is edited. Each invocation writes an executable, text logs and a JSON summary to its own kit directory and fails closed if that executable already exists.

To run selftest and pilot, extract the kit into TWO FRESH directories to preserve each result. For each, run `python3 run_r83_2.py --root "$HOME/ann-task-a" --phase selftest` or `--phase pilot` respectively.

Selftest uses 4096 synthetic source points; pilot uses 1,000,000 source points with fanout10 to 100 leaders, 3 paired repetitions per pattern. Parlay4 threads, OpenBLAS1. There is no fidelity claim for real PiPNN leader memberships, no whole-build wall or peak RSS result, and no proof of novel algorithmic contribution. The source-time excludes checksum calculation; GNU time process wall includes it.
