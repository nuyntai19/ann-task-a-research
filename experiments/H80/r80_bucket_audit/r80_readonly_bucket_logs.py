#!/usr/bin/env python3
"""R80: read-only bounded scan of old PiPNN BUILD logs; does NOT estimate memory copies."""
import argparse
import json
import os
import re
from pathlib import Path

PAT = {
    "bucket_bytes": re.compile(r"^\s*buckets size \(bytes\):\s*(\d+)\s*$", re.M),
    "num_buckets": re.compile(r"^\s*Total buckets:\s*(\d+)\s*$", re.M),
    "total_points": re.compile(r"^\s*Total points:\s*(\d+)\s*$", re.M),
    "buckets_time_s": re.compile(r"(?:^|\n)\s*(?:Parlay time:\s*)?buckets time:\s*([\d.]+)", re.I),
}
EXCLUDE = ("pipnn-clean-", "build-r70", "r71-bin", "r78", ".git")
EXT = {".log", ".out", ".txt"}

def parse_text(s):
    items = {k: [float(x) if k.endswith("_s") else int(x)
                 for x in pat.findall(s)] for k,pat in PAT.items()}
    if not any(items.values()):
        return None
    # Each cluster contributes one bucket-size/point/bucket count. NOT unique points.
    ret = {"cluster_records":max([len(items[k]) for k in ("bucket_bytes","num_buckets","total_points")]),
           "bucket_bytes_total":sum(items["bucket_bytes"]),
           "bucket_rows_total":sum(items["num_buckets"]),
           "point_memberships_total":sum(items["total_points"]),
           "bucket_phase_times_s":items["buckets_time_s"][:64],
           "records_by_field":{k:len(v) for k,v in items.items()}}
    return ret

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root",type=Path,default=Path.home()/"ann-task-a"/"experiments"/"H70")
    ap.add_argument("--max-files",type=int,default=2000)
    ap.add_argument("--max-bytes",type=int,default=12_000_000)
    ap.add_argument("--limit",type=int,default=100)
    ap.add_argument("--selftest",action="store_true")
    a=ap.parse_args()
    if a.selftest:
        s="""Parlay time: buckets time: 35.297\nbuckets size (bytes): 128000\nTotal buckets: 52\nTotal points: 3000\nParlay time: buckets time: 22.1\nbuckets size (bytes): 256000\nTotal buckets: 101\nTotal points: 6000\n"""
        r=parse_text(s)
        assert r["cluster_records"]==2 and r["bucket_bytes_total"]==384000
        assert r["point_memberships_total"]==9000 and len(r["bucket_phase_times_s"])==2
        print("R80_READONLY_LOG_PARSER_SELFTEST_PASS")
        return
    if not a.root.is_dir():
        raise SystemExit("R80_NO_LOG_ROOT: "+str(a.root))
    examined=0;skipped_large=0;reports=[]
    for base, dirs, files in os.walk(a.root, followlinks=False):
        # Avoid scanning project source, CMake deps, Git metadata, previous pilots.
        dirs[:] = sorted(d for d in dirs
                         if not d.startswith("pipnn-clean-")
                         and d not in ("build-r70", "r71-bin", ".git")
                         and not d.lower().startswith("r78"))
        for name in sorted(files):
            path = Path(base) / name
            if path.is_symlink() or path.suffix.lower() not in EXT:
                continue
            examined += 1
            if examined > a.max_files: break
            try:
                size = path.stat().st_size
                if size > a.max_bytes:
                    skipped_large += 1
                    continue
                data = path.read_text(encoding="utf-8", errors="replace")
                row = parse_text(data)
            except (OSError, UnicodeError):
                continue
            if row and row["cluster_records"]:
                reports.append({"path":str(path.relative_to(a.root)),"log_bytes":size,**row})
        if examined > a.max_files: break
    print("R80_READONLY_LOG_SCAN_COMPLETE files_examined=%d matching=%d oversized_skipped=%d"%(min(examined,a.max_files),len(reports),skipped_large))
    for item in reports[:max(0,a.limit)]:
        print("R80_MATCH "+json.dumps(item,ensure_ascii=False,sort_keys=True))
    if len(reports)>a.limit:print("R80_MATCHES_TRUNCATED %d"%(len(reports)-a.limit))
    print("R80_LOGS_ARE_FINAL_BUCKET_SUMMARIES_NOT_MEMORY_COPY_COUNTS")
    print("R80_NO_BUILD_NO_FILES_WRITTEN")

if __name__=="__main__":main()
