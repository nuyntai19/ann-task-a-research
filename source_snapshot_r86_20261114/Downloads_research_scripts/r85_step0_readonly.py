#!/usr/bin/env python3
"""R85 step-0: read-only phase audit from pre-existing local BUILD logs.
No rebuild, search, file writes, or network calls.
"""
from pathlib import Path
import json
import re
import statistics as st

HOME = Path.home()
EXPERIMENTS = [
    ("R85-A3.3", HOME / "ann-task-a/experiments/H85/r85_a3_2_a3_3_tuning/runs_partition_20261110-000716"),
    ("R85-A4", HOME / "ann-task-a/experiments/H85/r85_a4_paired_sift1m/runs_20261111-162423"),
]
PATTERNS = {
    "buckets": re.compile(r"\bbuckets time\b\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)", re.I),
    "leaf": re.compile(r"\bbuild leaf time\b\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)", re.I),
    "prune": re.compile(r"\bFinal prune time\b\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)", re.I),
    "membership": re.compile(r"\bTotal points\b\s*[:=]?\s*([0-9]+)", re.I),
    "leaves": re.compile(r"\bTotal buckets\b\s*[:=]?\s*([0-9]+)", re.I),
}

def extract(log: Path):
    vals={k:[] for k in PATTERNS}
    phase_lines=[]
    for line in log.read_text(encoding="utf-8",errors="replace").splitlines():
        for key, regex in PATTERNS.items():
            if key in ("buckets","leaf","prune") and key.replace("buckets", "buckets time").replace("leaf", "build leaf time").replace("prune", "Final prune time").lower() in line.lower():
                phase_lines.append(line.strip())
            m=regex.search(line)
            if m: vals[key].append(float(m.group(1)) if key in ("buckets","leaf","prune") else int(m.group(1)))
    return vals, phase_lines

def main():
    print("R85_STEP0_READONLY_PHASE_AUDIT")
    for label, run in EXPERIMENTS:
        print("\n===",label,str(run),"===")
        build_file=run/"build_results.json"
        if not build_file.is_file():
            print("MISSING_BUILD_RESULTS",build_file)
            continue
        rows=json.loads(build_file.read_text(encoding="utf8"))
        by_arm={}
        for row in rows:
            arm=row.get("arm",row.get("variant",row.get("tag","UNKNOWN")))
            tag=row.get("tag","")
            target=Path(row.get("log") or (run/(tag+".log")))
            if not target.is_file():
                print("MISSING_BUILD_LOG",tag,target)
                continue
            vals,phase_lines=extract(target)
            n=int(row.get("num_clusters",2 if "N2" in str(arm) or arm in ("D0","STOCK") else 1))
            counts=[len(vals[k]) for k in ("buckets","leaf","prune")]
            if counts != [n,n,1]:
                print("PHASE_PARSE_UNVERIFIED",tag,"expected",[n,n,1],"got",counts)
                for line in phase_lines[:12]: print(" RAW_PHASE:",line[:240])
                continue
            w=float(row["wall_s"])
            b=sum(vals["buckets"]);leaf=sum(vals["leaf"]);prune=sum(vals["prune"])
            remainder=w-b-leaf-prune
            if remainder < -max(0.2,0.05*w):
                print("WARNING_NEGATIVE_REMAINDER",tag,round(remainder,3),"check timer units/overlap")
            rec={"tag":tag,"wall":w,"buckets":b,"leaf":leaf,"prune":prune,"unattributed":remainder,
                 "membership":sum(vals["membership"]) if len(vals["membership"])==n else None,
                 "leaves":sum(vals["leaves"]) if len(vals["leaves"])==n else None}
            by_arm.setdefault(str(arm),[]).append(rec)
        print(f"{'ARM':20s} {'N':>2s} {'WALL':>8s} {'BUCKET':>8s} {'LEAF':>8s} {'PRUNE':>8s} {'OTHER':>8s} {'LEAF%':>7s} {'MEMBERS':>12s} {'LEAVES':>10s}")
        for arm,records in sorted(by_arm.items()):
            med=lambda k:st.median(z[k] for z in records)
            members=[z["membership"] for z in records if z["membership"] is not None]
            leaves=[z["leaves"] for z in records if z["leaves"] is not None]
            print(f"{arm[:20]:20s} {len(records):2d} {med('wall'):8.2f} {med('buckets'):8.2f} {med('leaf'):8.2f} {med('prune'):8.2f} {med('unattributed'):8.2f} {100*med('leaf')/med('wall'):6.1f}% {str(int(st.median(members))) if members else 'NA':>12s} {str(int(st.median(leaves))) if leaves else 'NA':>10s}")
        print("PHASE_AUDIT_PARSED",sum(len(v) for v in by_arm.values()),"OF",len(rows),"BUILDS")
    print("R85_STEP0_READONLY_DONE_NO_BUILD_NO_SEARCH_NO_WRITES")

if __name__ == "__main__":main()
