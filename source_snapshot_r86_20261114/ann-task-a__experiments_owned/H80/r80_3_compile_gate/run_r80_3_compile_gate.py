#!/usr/bin/env python3
"""R80.3: fail-closed, compile-only integration of move-heap MergeBuckets.

Read-only to H70, R70-R80 previous artifacts and datasets. All new writes are
contained in the r80_3_compile_gate folder next to this runner. No CMake,
object file, graph creation, ANN BUILD or query execution.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

ROOT = Path.home() / "ann-task-a" / "experiments"
WORK = ROOT / "H70" / "pipnn-clean-443a328"
BUILD = ROOT / "H70" / "build-r70"
HERE = Path(__file__).resolve().parent
SHADOW = HERE / "shadow_algorithms"
PIP = SHADOW / "PipNN"
PROBE = HERE / "r80_3_buildpath_probe.cc"
HEAD = "443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd"
PINS = {
    "PipNN/pipnn.h": "f4391ad8712d7757423dca872f9042c3271660dffde384a85b93854b9692f288",
    "PipNN/pipnn_utils.h": "7083e8183554a1cb586b70cdb4c57920f49ec5a50680096aecf6b873f596595d",
    "utils/graph.h": "17e51779f32db56c9c50b6d514a8ff68539fd19b734804df3abdb63f88dd443e",
    "utils/r70_two_tier_lshgraph.h": "ac0bece4804c7bc552b30db0df57ee92492033065cef62330ddb58a19d470af1",
}

# Mirrors the source-equivalent, independently native-tested R80.1 operator.
# Changes ONLY the way buckets leave the min-size heap, not merge/dedup logic.
MOVE_HEAP_FUNCTION = r'''  void MergeBuckets(
      parlay::sequence<Bucket>& clusters,
      std::vector<Bucket>& finished_buckets,
      parlay::sequence<Bucket>& remaining_clusters) {
    if (NO_MERGE) {
      remaining_clusters = std::move(clusters);
      return;
    }

    // R80_3_MOVE_HEAP: same std::push_heap/pop_heap size comparator as
    // std::priority_queue, but move the extracted Bucket rather than copying
    // the const top() result. No change to downstream HashPrune/topology rules.
    CompareBucketsBySize cmp;
    std::vector<Bucket> heap;
    const auto push_bucket = [&](Bucket&& b) {
      heap.push_back(std::move(b));
      std::push_heap(heap.begin(), heap.end(), cmp);
    };
    const auto pop_bucket = [&]() -> Bucket {
      CHECK(!heap.empty());
      std::pop_heap(heap.begin(), heap.end(), cmp);
      Bucket moved = std::move(heap.back());
      heap.pop_back();
      return moved;
    };

    for (size_t i = 0; i < clusters.size(); ++i) {
      push_bucket(std::move(clusters[i]));
    }
    clusters.resize(0);

    while (heap.size() > 1) {
      if (heap.front().size() >= MIN_CLUSTER_SIZE) break;

      size_t merged_size = heap.front().size();
      std::vector<Bucket> merged_buckets;
      merged_buckets.emplace_back(pop_bucket());

      while (!heap.empty() && merged_size < MIN_CLUSTER_SIZE &&
             merged_size + heap.front().size() <= MAX_MERGED_CLUSTER_SIZE) {
        merged_size += heap.front().size();
        merged_buckets.emplace_back(pop_bucket());
      }

      if (merged_buckets.size() == 1) {
        CHECK(merged_buckets[0].size() <= MAX_CLUSTER_SIZE);
        if (merged_buckets[0].size() > MAX_CLUSTER_SIZE) {
          std::cout << "Pushing a cluster that is too large: "
                    << merged_buckets[0].size() << std::endl;
        }
        finished_buckets.emplace_back(std::move(merged_buckets[0]));
        break;
      }

      CHECK(merged_size > 0);
      auto new_bucket =
          parlay::sequence<uint32_t>::uninitialized(merged_size);
      size_t pos = 0;
      for (auto& b : merged_buckets) {
        std::memcpy(new_bucket.begin() + pos, b.begin(),
                    b.size() * sizeof(uint32_t));
        pos += b.size();
      }
      new_bucket = parlay::remove_duplicates(new_bucket);
      CHECK(new_bucket.size() > 0);

      if (new_bucket.size() >= MIN_CLUSTER_SIZE &&
          new_bucket.size() <= MAX_CLUSTER_SIZE) {
        finished_buckets.push_back(std::move(new_bucket));
      } else {
        push_bucket(std::move(new_bucket));
      }
    }

    while (!heap.empty()) {
      remaining_clusters.emplace_back(pop_bucket());
    }
  }
'''

PROBE_SOURCE = r'''// R80.3: force full compiled BUILD / Final Prune with R80 move heap;
// no main, no execution, no binary, no ANN graph BUILD.
#include <cstdint>
#include <string>
#include "utils/euclidian_point.h"
#include "utils/point_range.h"
#include "PipNN/pipnn.h"

namespace r80_buildpath_gate {
using Id = std::uint32_t;
using Point = parlayANN::Euclidian_Point<float>;
using PR = parlayANN::PointRange<Point>;
using Hash = ::SketchHash<Point,PR,Id>;
using Tier = parlayANN::TwoTierLSHGraph<Id,float,Hash>;

void force_h17_tier_move_heap_build_path(parlayANN::Graph<Id>& out,
                                         ::commandLine& cli,
                                         PR& points,
                                         Tier& reservoir) {
  parlayANN::pipnn_index<Point,PR,Id> index;
  index.build_index_impl(
      out, cli, points,
      2L, 1024L, 2L,
      true, true, 1.1,
      64L, 100L, 1, 0, 0.005,
      std::string("10,3,1"), 12, 160L,
      reservoir, 0UL);
}
}
'''


def fail(msg: str) -> None:
    print("R80_3_COMPILE_GATE_BLOCKED:", msg, flush=True)
    raise SystemExit(2)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def validate():
    if not HERE.resolve().is_relative_to((ROOT / "H80").resolve()):
        fail("refusing to write outside ~/ann-task-a/experiments/H80")
    g = subprocess.run(["git","-C",str(WORK),"rev-parse","HEAD"],capture_output=True,text=True)
    if g.returncode or g.stdout.strip()!=HEAD:
        fail("original H70 HEAD mismatch")
    for rel,pin in PINS.items():
        path=WORK / "algorithms" / rel
        if not path.is_file() or sha256(path)!=pin:
            fail(f"H70 pinned file mismatch: {rel}")
    print("R80_3_H70_SOURCE_PINS_PASS",flush=True)


def write_new_or_verify(path: Path, data: str) -> None:
    if path.is_symlink():
        fail(f"refusing to overwrite symlink {path}")
    if path.exists():
        if not path.is_file() or path.read_text(encoding="utf8")!=data:
            fail(f"existing file differs; refusing overwrite: {path}")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf8") as f:
            f.write(data)


def stage():
    PIP.mkdir(parents=True,exist_ok=True)
    for name in ("utils","bench"):
        link=SHADOW / name
        target=WORK / "algorithms" / name
        if not link.exists() and not link.is_symlink():
            link.symlink_to(target, target_is_directory=True)
        if not link.is_symlink() or link.resolve()!=target.resolve():
            fail(f"shadow {name} is not symlink to expected original read-only path")
    for filename in ("pipnn_utils.h",):
        x=(WORK / "algorithms" / "PipNN" / filename).read_text(encoding="utf8")
        write_new_or_verify(PIP / filename,x)
    original=(WORK / "algorithms" / "PipNN" / "pipnn.h").read_text(encoding="utf8")
    marker="  void MergeBuckets(\n"
    next_marker="  // Base-case handler for duplicates / near-duplicates."
    if original.count(marker)!=1 or original.count(next_marker)!=1:
        fail("original MergeBuckets anchors ambiguous")
    start=original.index(marker)
    end=original.index(next_marker,start)
    oldbody=original[start:end]
    for expected in ("std::priority_queue<Bucket", "merged_buckets.emplace_back(top)","remaining_clusters.emplace_back(pq.top())"):
        if expected not in oldbody:
            fail("original MergeBuckets body differs from audited source")
    modified=original[:start]+MOVE_HEAP_FUNCTION+"\n"+original[end:]
    if modified.count("R80_3_MOVE_HEAP")!=1:
        fail("source patch check failed")
    write_new_or_verify(PIP/"pipnn.h",modified)
    write_new_or_verify(PROBE,PROBE_SOURCE)
    print("R80_3_SHADOW_SOURCE_PATCH_PASS",flush=True)
    print("[R80.3] shadow modified pipnn.h SHA256:",sha256(PIP/"pipnn.h"),flush=True)
    print("[R80.3] original H70 pipnn.h unchanged SHA256:",sha256(WORK/"algorithms"/"PipNN"/"pipnn.h"),flush=True)


def compiler_args():
    path=BUILD/"compile_commands.json"
    if not path.is_file(): fail("missing existing H70 compile database")
    db=json.loads(path.read_text(encoding="utf8"))
    source=(WORK/"algorithms"/"PipNN"/"r70_native_tests.cc").resolve()
    options=[entry for entry in db if Path(entry.get("file","")).resolve()==source]
    if len(options)!=1:fail("expected one compile spec for R70 native tests")
    entry=options[0]
    argv=entry.get("arguments") or shlex.split(entry["command"])
    if "-c" not in argv or "-o" not in argv: fail("unexpected R70 compiler spec")
    args=list(argv)
    for opt in ("-o","-c","-MF","-MT","-MQ"):
        if opt in args:
            idx=args.index(opt)
            if idx+1>=len(args):fail(f"malformed compile spec {opt}")
            del args[idx:idx+2]
    for opt in ("-MD","-MMD","-MP","-save-temps"):
        args=[a for a in args if a!=opt]
    for a in args:
        if a.endswith(("r70_native_tests.cc","r70_native_tests.cc.o")):
            fail("old source or object input remained after filtering")
    # Explicitly keep H80 shadow BEFORE H70 source's -I to ensure the patched
    # header is used. H70 worktree is not touched by compiler -fsyntax-only.
    args[1:1]=["-I"+str(SHADOW), "-DR70_TWO_TIER=1", "-DR71_H17_TOP2=1"]
    args.extend(["-fsyntax-only",str(PROBE)])
    return args,Path(entry["directory"])


def main():
    print("========== R80.3 ISOLATED H17+TIER+MOVEHEAP FULL BUILD TEMPLATE CHECK ==========")
    validate()
    stage()
    argv,cwd=compiler_args()
    print("[R80.3] compile command:",shlex.join(argv),flush=True)
    print("[R80.3] NO CMAKE, NO object/binary, NO ANN BUILD, H70 READ-ONLY",flush=True)
    result=subprocess.run(argv,cwd=cwd,check=False)
    if result.returncode:fail(f"C++ syntax-only compile exited {result.returncode}")
    print("R80_3_FULL_BUILDPATH_TEMPLATE_PASS",flush=True)
    print("R80_3_NO_FULL_BUILD_NO_RSS_NO_RECALL",flush=True)
    print("R80_3_COMPILE_GATE_COMPLETE",flush=True)

if __name__=="__main__":
    try:main()
    except (OSError,ValueError,IndexError,json.JSONDecodeError) as e:fail(str(e))
