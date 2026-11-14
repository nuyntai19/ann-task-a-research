#!/usr/bin/env python3
"""R80.2: isolated, real-PiPNN MergeBuckets microbench in separate OS processes.

NEVER modifies H70. Reads R80.1 differential fixture and existing pinned H70
compiler/link flags. Small, synthetic function-level experiment only.
"""
import argparse
import hashlib
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys

EXP = Path.home() / "ann-task-a" / "experiments"
HERE = Path(__file__).resolve().parent
R801 = EXP / "H80" / "r80_1_mergebuckets_native"
SRC801 = R801 / "r80_1_mergebuckets_native.cc"
R801SHA = "a20d925512f680c1f434a11b1f4a6176ee8b1fb7866a709ae93df3b2555cd3b8"


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def fail(message):
    print("R80_2_BLOCKED: " + message, file=sys.stderr, flush=True)
    raise SystemExit(2)


def generate_source():
    import run_r80_1_native as r801
    r801.pin_check()
    if not SRC801.is_file():
        fail("R80.1 source missing; install original R80.1 kit under H80")
    actual = sha256(SRC801)
    if actual != R801SHA:
        fail(f"R80.1 file hash mismatch actual={actual} expected={R801SHA}")
    data = SRC801.read_text(encoding="utf-8")
    sentinel = "int main(int argc, char** argv) {"
    at = data.find(sentinel)
    if at < 0 or data.count(sentinel) != 1:
        fail("R80.1 main entry not found uniquely")
    header = data[:at]
    suffix = r'''
#include <sys/resource.h>
#include <iomanip>
int main(int argc, char** argv) {
  try {
    if (argc != 5) throw std::runtime_error("usage: <stock|move> <buckets> <seed> <kind>");
    const std::string arm(argv[1]);
    const size_t n=std::strtoull(argv[2], nullptr, 10);
    const unsigned seed=static_cast<unsigned>(std::strtoul(argv[3], nullptr, 10));
    const int kind=std::atoi(argv[4]);
    if (arm != "stock" && arm != "move") throw std::runtime_error("arm not stock/move");
    if (n < 64 || n > 40000 || kind < 0 || kind > 6) throw std::runtime_error("invalid size/fixture");
    // Generate the SAME fixture before timing for both independent processes.
    auto buckets = make_fixture(n,seed,kind);
    Cluster cluster;
    cluster.MIN_CLUSTER_SIZE=64;
    cluster.MAX_CLUSTER_SIZE=512;
    cluster.MAX_MERGED_CLUSTER_SIZE=(kind==5 ? 165u : 512u);
    cluster.NO_MERGE=(kind==6);
    std::vector<Bucket> finished;
    Seq remaining;
    PopCounters counts;
    const auto t0=std::chrono::steady_clock::now();
    if (arm=="stock") cluster.MergeBuckets(buckets,finished,remaining);
    else move_heap_merge(cluster,buckets,finished,remaining,counts);
    const auto t1=std::chrono::steady_clock::now();
    const double ms=std::chrono::duration<double,std::milli>(t1-t0).count();
    const auto sig=signature(remaining,finished);
    struct rusage ru{};
    if(getrusage(RUSAGE_SELF,&ru)!=0) throw std::runtime_error("getrusage failed");
    // ru_maxrss KiB on Linux, process lifetime peak (includes fixture creation).
    std::cout << std::setprecision(12)
              << "R80_2_MICRO_RESULT arm="<<arm
              << " kind="<<kind<<" seed="<<seed<<" n="<<n
              << " elapsed_ms="<<ms<<" VmHWM_KiB="<<ru.ru_maxrss
              << " checksum="<<sig
              << " finished="<<finished.size()<<" remaining="<<remaining.size()
              << " pop_events="<<counts.popped
              << " avoided_copy_ID_bytes="<<counts.original_copy_id_bytes_avoided
              << "\nR80_2_SYNTHETIC_MERGEBUCKETS_ONLY_NOT_ANN_BUILD_RECALL\n";
    return 0;
  } catch(const std::exception& e) {
    std::cerr << "R80_2_MICRO_FAIL: " << e.what() << "\n";
    return 2;
  }
}
'''
    src = HERE / "r80_2_generated_native.cc"
    src.write_text(header + suffix, encoding="utf-8")
    return src, r801


def compile_only(src, r801):
    cc, wd = r801.compiler()
    link, idx, lwd = r801.linker()
    if "-c" not in cc or "-o" not in cc or "-o" not in link:
        fail("R80.1 original compiler metadata format changed")
    obj = HERE / "r80_2_native.o"
    exe = HERE / "r80_2_native"
    cc[cc.index("-c") + 1] = str(src)
    cc[cc.index("-o") + 1] = str(obj)
    cc[1:1] = ["-DR71_H17_TOP2=1"]
    print("[R80.2] compile isolated PiPNN native microbench", flush=True)
    subprocess.run(cc, cwd=wd, check=True)
    link[idx] = str(obj)
    link[link.index("-o") + 1] = str(exe)
    print("[R80.2] link isolated PiPNN native microbench", flush=True)
    subprocess.run(link, cwd=lwd, check=True)
    print("R80_2_COMPILE_LINK_PASS", flush=True)
    return exe


def run_process(exe, arm, kind, seed, n):
    env = dict(os.environ, PARLAY_NUM_THREADS="1", OMP_NUM_THREADS="1")
    p = subprocess.run([str(exe),arm,str(n),str(seed),str(kind)], cwd=HERE,
                       text=True,capture_output=True,env=env)
    if p.returncode != 0:
        fail("native process failed " + str((arm,kind,seed,p.returncode)) + "\n" + p.stderr[-2400:])
    rows = [s for s in p.stdout.splitlines() if s.startswith("R80_2_MICRO_RESULT ")]
    if len(rows)!=1:
        fail("missing/duplicate result marker " + str((arm,kind,seed)))
    row = dict(kv.split("=",1) for kv in rows[0].split()[1:])
    if row.get("arm")!=arm or int(row.get("kind","-1"))!=kind or int(row.get("seed","-1"))!=seed:
        fail("result identity mismatch")
    print(rows[0],flush=True)
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--buckets",type=int,default=20000)
    parser.add_argument("--reps",type=int,default=3)
    parser.add_argument("--kinds",default="0,1,2,3,4,5")
    args=parser.parse_args()
    if not 500 <= args.buckets <= 40000 or not 2 <= args.reps <= 5:
        fail("bounded protocol: buckets 500..40000; reps 2..5")
    kinds=[int(x) for x in args.kinds.split(",")]
    if not kinds or len(set(kinds))!=len(kinds) or any(k<0 or k>6 for k in kinds):
        fail("bad kinds; use e.g. --kinds 0,1,2,3,4,5")
    print("========== R80.2 ORIGINAL PIPNN MERGEBUCKETS MICROBENCH GATE ==========",flush=True)
    sys.path.insert(0,str(R801))
    src,r801=generate_source()
    exe=compile_only(src,r801)
    all_results={k:{"stock":[],"move":[]} for k in kinds}
    for kind in kinds:
      for rep in range(args.reps):
        seed=(7,191,3889,5501,8819)[rep]
        order=("stock","move") if (kind+rep)%2==0 else ("move","stock")
        pair={arm:run_process(exe,arm,kind,seed,args.buckets) for arm in order}
        a,b=pair["stock"],pair["move"]
        for field in ("checksum","finished","remaining"):
            if a[field]!=b[field]:
                fail(f"PARITY FAIL kind={kind} rep={rep} field={field}: {a[field]} vs {b[field]}")
        for arm in order:
            all_results[kind][arm].append(pair[arm])
        print(f"R80_2_PAIR_CHECKSUM_PARITY_PASS kind={kind} rep={rep} checksum={a['checksum']}",flush=True)
    print("R80_2_MEDIANS_BEGIN",flush=True)
    for kind in kinds:
        a=all_results[kind]["stock"];b=all_results[kind]["move"]
        x=statistics.median(float(z["elapsed_ms"]) for z in a)
        y=statistics.median(float(z["elapsed_ms"]) for z in b)
        xa=statistics.median(int(z["VmHWM_KiB"]) for z in a)
        ya=statistics.median(int(z["VmHWM_KiB"]) for z in b)
        saved=statistics.median(int(z["avoided_copy_ID_bytes"]) for z in b)
        if min(x,y)<=0:fail("invalid elapsed timing")
        print(f"R80_2_KIND_SUMMARY kind={kind} stock_ms={x:.6f} move_ms={y:.6f} "
              f"move_over_stock={y/x:.6f} stock_VmHWM_KiB={xa} move_VmHWM_KiB={ya} "
              f"avoided_copy_ID_bytes_median={saved}",flush=True)
    print("R80_2_NO_REAL_ANN_BUILD_NO_RECALL_NO_SIFT_RSS",flush=True)
    print("R80_2_BOUNDED_NATIVE_GATE_COMPLETE",flush=True)

if __name__ == "__main__":
    try: main()
    except (OSError,subprocess.CalledProcessError,ValueError,KeyError,IndexError) as e:
        fail("compile/link/parse failure: "+str(e))
