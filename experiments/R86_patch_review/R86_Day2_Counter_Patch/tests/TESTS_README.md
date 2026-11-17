# Validation performed (sandbox, not Ubuntu native PiPNN)

- Source patch `patch --dry-run -p1`: PASS against uploaded H70 source-review snapshot.
- R86 logger import patch `patch --dry-run -p1`: PASS against the original R86 logging kit.
- `g++ -std=c++17` header tests with `-DR86_COUNTERS=1`, `=0`, and undefined: PASS.
- Synthetic 1-pass counter dump: measured zero `collision_same_id=0` was emitted; `W_P` depth0; leaf work at depth=null; final prune pass0: PASS.
- Original R86 logger Python unit tests after applying the one-line-depth update: 3/3 PASS.
- End-to-end synthetic import of counter JSONL + leaf_sizes JSONL with `depth:null`: PASS, zero mismatches.
- Native PiPNN CMake build, real 10K data gate, OFF/ON equivalence, and 100K matched beam/Recall: NOT RUN — require user's Ubuntu dependencies and Claude source review.
