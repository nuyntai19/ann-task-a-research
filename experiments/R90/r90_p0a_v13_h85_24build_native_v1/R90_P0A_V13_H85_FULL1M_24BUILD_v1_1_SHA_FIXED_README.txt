R90 P0A v1.3 H85 HIGHWAY — v1.1 STRICT SHA PIN TYPO FIX

Original uploaded build runner has V13_PY_SHA with 63 hex chars (52805e517a8534732f0cbb6aeac374afc71dcbb88af53aae0d7a4d624d9e5dc), always mismatching even an original correct file. Original H85 Stage A/B script SHA256 is 52805e517a8534732f0cbb6aeac374afc71dcbb88afc53aae0d7a4d624d9e5dc (64 digits) verified from historical ZIP. The ONLY change inside the 24-BUILD Python runner is correcting the SHA literal to that value. No change to import path, native_one, build protocol, graph audits, source trees, six compiled ELF or existing outputs.

Patched runner SHA256: 68bab029e4bd65a7179372ee67389c1272a5ce3bb6030b3f9be83318945fb140
Runner filename: r90_p0a_v13_h85_24build_native_v1_1_SHA_FIXED.py
New first-run shell SHA256: 2132bc2917a0b7886515f7e18cf74c6eb827ad29b751dc6001fe93944b26cdb4
New resume shell SHA256: 8084d810820009da966c0802ae2f61a83995d755afdd57340c1bd8ab46930e3c

Unzip -n new ZIP into Downloads, then run:
  bash "$HOME/Downloads/R90_P0A_V13_H85_FULL1M_24BUILD_v1_1_SHA_FIXED_Ubuntu.sh"

DO NOT run old v1 first-run shell again: it has already left an immutable HOLD log. New shell uses separate log and refuses existing new output root. No Stage A/B, historical graph or original Python file changes. After new successful BUILD-only run, Search Recall/QPS on new 1M graphs is still pending.
On a later crash with intact preregister and complete SHA-verifiable records, use resume script ONLY with care; on partial/orphan output HOLD and report before recovery.
