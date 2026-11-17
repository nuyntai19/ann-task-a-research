#!/usr/bin/env bash
# One-shot d0 launcher (VPN-safe: everything runs inside tmux with done markers).
# 1) remaining Phase 0 gates: fgraft B=32 determinism + published-main frozen hash
#    must equal fgraft --harvest-blocks 0 on the smoke config;
# 2) if the gate passes, Phase 1 paired builds on GloVe then SIFT.
#   bash bench/d0_launch_phase1.sh        (from /mnt/claude/graft-work/fgraft)
set -u
cd /mnt/claude/graft-work/fgraft
mkdir -p results/phase1; rm -f GATE_DONE GATE_FAIL PHASE1_DONE
tmux kill-session -t fgraft 2>/dev/null
tmux new -d -s fgraft bash -c '
cd /mnt/claude/graft-work/fgraft
SM="--synthetic clustered --n 200000 --d 128 --T 16 --ef 64 --check-determinism"
{ echo "== fgraft B=32";  graft-ann/src/fg $SM --harvest-blocks 32 2>&1 | grep determinism:
  echo "== fgraft B=0";   graft-ann/src/fg $SM 2>&1 | grep determinism:
  echo "== main frozen";  graft-main/src/fg $SM 2>&1 | grep determinism:
} > gate.log 2>&1
h0=$(grep -A1 "B=0" gate.log | grep -o "hash(threads=1)=[0-9a-f]*" | head -1)
hm=$(grep -A1 "main frozen" gate.log | grep -o "hash(threads=1)=[0-9a-f]*" | head -1)
if grep -q "MISMATCH\|DIFFER" gate.log || [ -z "$h0" ] || [ "$h0" != "$hm" ]; then
  echo "GATE FAILED: frozen=$h0 main=$hm" >> gate.log; touch GATE_FAIL; exit 1
fi
echo "GATE OK: frozen path reproduces main ($h0)" >> gate.log; touch GATE_DONE
export FG=/mnt/claude/graft-work/fgraft/graft-ann/src/fg PIPNN=/mnt/claude/graft-work/fgraft/PiPNN
export DATA=data BLOCKS=10 COOL=5 THREADS=64 SEED=1 DS=glove,sift OUT=results/phase1
/mnt/claude/graft-work/misifu/.venv/bin/python bench/d0_phase1.py > results/phase1.log 2>&1
touch PHASE1_DONE'
sleep 1; tmux ls
