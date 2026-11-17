#!/usr/bin/env bash
# Read-only audit: print flags and checksums of R85 source/build artifacts.
# Does not create, patch, build, or change the H70/H85 trees.
set -uo pipefail
ROOT="${ANN_ROOT:-$HOME/ann-task-a}"
H70="$ROOT/experiments/H70/pipnn-clean-443a328"
H85="$ROOT/experiments/H85"
if [[ ! -d "$H70" || ! -d "$H85" ]]; then echo "ERROR missing H70/H85 under $ROOT" >&2; exit 2; fi
printf '\n=== H70 HEAD / DIRTY TREE / SOURCE ===\n'
git -C "$H70" rev-parse HEAD
git -C "$H70" status --short
for f in algorithms/PipNN/pipnn.h algorithms/PipNN/pipnn_utils.h algorithms/PipNN/neighbors.h algorithms/utils/graph.h algorithms/utils/r70_two_tier_lshgraph.h; do
  [[ -f "$H70/$f" ]] && sha256sum "$H70/$f"
done
printf '\n=== R85 BUILD CMAKE FLAGS ===\n'
for label in r85_a1_capacity_ablation/build_h17_flat r85_0_matched_baseline/build_stock r85_0_matched_baseline/build_d0; do
  d="$H85/$label"; echo "$label"
  if [[ -f "$d/CMakeCache.txt" ]]; then
    grep -E '^(R71_USE_H17|R70_USE_TIER):|^CMAKE_HOME_DIRECTORY:' "$d/CMakeCache.txt" || true
  else echo 'NOT_FOUND'; fi
  b="$d/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN"
  if [[ -f "$b" ]]; then sha256sum "$b"; else echo 'BINARY_NOT_FOUND'; fi
done
printf '\n=== SOURCE V4 VS CURRENT H70 (no writes) ===\n'
V4="$H85/r85_b1_controlled/isolation_v4/source"
for f in algorithms/PipNN/pipnn.h algorithms/PipNN/pipnn_utils.h algorithms/PipNN/CMakeLists.txt; do
  if [[ -f "$V4/$f" && -f "$H70/$f" ]]; then
    printf '%s: ' "$f"
    cmp -s "$V4/$f" "$H70/$f" && echo BYTE_IDENTICAL || echo DIFFERENT
    sha256sum "$V4/$f"
  else echo "$f: MISSING"; fi
done
printf '\n=== SELECTED MANIFESTS (read-only) ===\n'
python3 - "$H85" <<'PY'
import json,sys
from pathlib import Path
h=Path(sys.argv[1]);rels=[
'r85_a1_capacity_ablation/h17_binary_manifest.json',
'r85_scale1_bigann1m/bigann1m_20261112-022002_494222/manifest.json',
'r85_b1_controlled/isolation_v4/isolation_manifest.json']

def walk(p,val,level=0):
    if level>7:return
    if isinstance(val,dict):
        for k,v in val.items():
            kk=p+'.'+k if p else k
            if isinstance(v,(dict,list)):walk(kk,v,level+1)
            elif any(w in kk.lower() for w in ('sha256','binary','source','seed','flag','variant','original')):
                print(kk,':',str(v)[:210])
    elif isinstance(val,list):
        for i,v in enumerate(val[:12]):walk(f'{p}[{i}]',v,level+1)
for rel in rels:
    f=h/rel;print('\nMANIFEST',rel)
    if not f.is_file():print('NOT_FOUND');continue
    try:walk('',json.loads(f.read_text(encoding='utf-8')))
    except Exception as e:print('READ_ERROR',str(e))
PY
printf '\nR86_DAY2_PROVENANCE_AUDIT_DONE\n'
