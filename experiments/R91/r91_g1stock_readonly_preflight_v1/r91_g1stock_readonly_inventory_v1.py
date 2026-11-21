#!/usr/bin/env python3
"""R91 G1STOCK source/CLI/resource inventory. READ ONLY to historical artifacts. NO ANN BUILD."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import time

EXPECTED = {
    "stock_elf": "13bef65c01d4638959b16b74fc2b8b6130b433ebc09fff8f436c8b1503e688c9",
    "fast_elf": "fcfb16d0ca2b498f94db8383dfc311c2e7ba88cb3036281accd5f30c6d876793",
    "compile_manifest": None,
    "g1_result": "bd46f8327e634e05ebdf3975c602d3c069df749be8dc3a6e140f286a606e3835",
    "g1_graph": "4055dedc2ccb3b6406fed45ed28de2ec57c46fe2b085b5046ae13cd943702429",
    "base": "e7756f6b54a07e8af171c7644ce2e1be6d7053ee2a2c30c4b02f99e85984b700",
    "query": "48d087a17bec15a5ec9ea526fe9bd14ac31bbbb5cd200817b341adbb77695644",
    "gt": "77b558bd3b77e4cc1149384996b953b040e412477eb0df9889718fc13e17aff2",
}

def sha256(path: Path, block: int = 4 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(block), b''):
            h.update(b)
    return h.hexdigest()

def status_path(path: Path) -> dict:
    if path.is_symlink():
        return {"path": str(path), "status": "SYMLINK_HOLD"}
    if not path.is_file():
        return {"path": str(path), "status": "MISSING_HOLD"}
    st = path.stat()
    return {"path": str(path), "status": "REGULAR_FILE", "size": st.st_size,
            "executable": bool(st.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))}

def read_matching_lines(path: Path, max_bytes=1_500_000) -> dict:
    d = status_path(path)
    if d['status'] != 'REGULAR_FILE':
        return d
    if d['size'] > max_bytes:
        d['status'] = 'TOO_LARGE_FOR_SOURCE_LINES_HOLD'
        return d
    d['sha256'] = sha256(path)
    raw = path.read_text(encoding='utf-8', errors='replace').splitlines()
    patt = re.compile(r'(?i)(stock_off|fast_off|build_index|num_clusters|cluster_size|table_size|top_level_leaders|fanout_scheme|mst_deg|prune_degree|hash_bits|alpha|systemd-run|memorymax|memoryswapmax|PARLAY_NUM_THREADS|taskset|graphs/|MSTuring10M|base\.10M)')
    d['matching_source_lines'] = [f'{i}: {line[:350]}' for i, line in enumerate(raw, 1) if patt.search(line)][:100]
    return d

def walk_stock_binaries(root: Path) -> tuple[list, bool]:
    found = []
    visited = 0
    if not root.is_dir() or root.is_symlink():
        return found, False
    for here, subdirs, files in os.walk(root, followlinks=False):
        visited += 1
        if visited > 9000:
            return found, True
        subdirs[:] = [d for d in subdirs if d not in {'logs', 'graphs', 'data', 'outputs', 'runs', 'CMakeFiles', '.git', '__pycache__', 'third_party', 'external'}]
        for f in files:
            if not (f == 'neighbors-pipnn_FLOAT_T_EUCLIDEAN' or f == 'stock_off'):
                continue
            p = Path(here) / f
            v = status_path(p)
            if v['status'] == 'REGULAR_FILE' and v['size'] < 128 * 1024 * 1024:
                v['sha256'] = sha256(p)
                v['matches_stock_pin'] = v['sha256'] == EXPECTED['stock_elf']
            found.append(v)
    return found, False

def meminfo() -> dict:
    p = Path('/proc/meminfo')
    if not p.exists(): return {}
    rows = {}
    for line in p.read_text().splitlines():
        m = re.match(r'^(MemTotal|MemAvailable|SwapTotal|SwapFree):\s+(\d+) kB', line)
        if m: rows[m.group(1)+'_KiB'] = int(m.group(2))
    return rows

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--stock-elf', default='', help='optional explicit path to old stock_off ELF, sha pinned')
    a = ap.parse_args()
    if a.selftest:
        assert hashlib.sha256(b'abc').hexdigest() == 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'
        assert re.search('table_size', '-table_size 160')
        print('R91_G1STOCK_READONLY_INVENTORY_V1_SELFTEST_PASS_NO_BUILD')
        return 0
    home = Path.home()
    project = home/'ann-task-a'
    original = project/'experiments/R90/r90_p0a_v13_historical_highway_6bc2_controlled_v1'
    out = project/'experiments/R91/r91_g1stock_readonly_preflight_v1'
    if out.exists() or out.is_symlink():
        print('R91_G1STOCK_READONLY_OUTPUT_EXISTS_HOLD_DO_NOT_RERUN', file=sys.stderr)
        return 2
    g1result = project/'experiments/R91/r91_g1_one_fastv2_flat_c160_mst10m_24g_v1/r91_g1_single10m_result.json'
    compile_manifest = original/'compile_manifest.json'
    files = {
        'g1_result': g1result,
        'historical_compile_manifest': compile_manifest,
        'g1_runner_python': home/'Downloads/r91_g07_g1_mst10m_hardcap_v1.py',
        'g1_runner_shell': home/'Downloads/R91_G1_ONE_FASTV2_MST10M_24G_NOSWAP_v1_Ubuntu.sh',
        'base10m': project/'data/MSTuring_10M_v1/base.10M.fbin',
        'query100k': project/'data/MSTuring_10M_v1/query.public.100K.fbin',
        'gt100k': project/'data/MSTuring_10M_v1/groundtruth.public.100K.ibin',
        'fast_graph': project/'experiments/R91/r91_g1_one_fastv2_flat_c160_mst10m_24g_v1/graphs/MSTuring10M_fast_off_C160_K1024_N2.graph',
    }
    report = {'status': 'NOT_ASSESSED', 'scope': 'READ_ONLY_SOURCE_RESOURCE_INVENTORY_NO_ANN_BUILD',
              'timestamp_utc_epoch': time.time(), 'expected_shas': EXPECTED,
              'files': {k:status_path(v) for k,v in files.items()}, 'checks': {}, 'warnings': [],
              'binary_candidates': [], 'source_snippets': {}}
    chk = report['checks']
    def isreg(key): return report['files'][key]['status'] == 'REGULAR_FILE'
    if isreg('historical_compile_manifest'):
        report['files']['historical_compile_manifest']['sha256'] = sha256(compile_manifest)
        try:
            obj = json.loads(compile_manifest.read_text())
            chk['pinned_v13_compile_manifest_stock_off_matches'] = obj['binaries']['stock_off'] == EXPECTED['stock_elf']
            chk['pinned_v13_compile_manifest_fast_off_matches'] = obj['binaries']['fast_off'] == EXPECTED['fast_elf']
        except Exception as e: chk['compile_manifest_parse_error'] = str(e)
    if isreg('g1_result'):
        report['files']['g1_result']['sha256'] = sha256(g1result)
        chk['original_g1_result_sha_matches'] = report['files']['g1_result']['sha256'] == EXPECTED['g1_result']
        try:
            g1 = json.loads(g1result.read_text())
            report['g1_result_top_keys'] = list(g1.keys())
            report['g1_command_related_fields'] = {k: str(v)[:1800] for k,v in g1.items() if re.search('(?i)command|args|argv|flags|binary|builder|graph_sha',k)}
        except Exception as e: chk['g1_json_parse_error'] = str(e)
    for k in ('g1_runner_python', 'g1_runner_shell'):
        report['source_snippets'][k] = read_matching_lines(files[k])
    stock_candidates, truncated = walk_stock_binaries(original)
    if a.stock_elf:
        explicit = Path(a.stock_elf).expanduser()
        v = status_path(explicit)
        if v['status'] == 'REGULAR_FILE' and v['size'] < 128 * 1024 * 1024:
            v['sha256'] = sha256(explicit)
            v['matches_stock_pin'] = v['sha256'] == EXPECTED['stock_elf']
        v['provided_explicitly'] = True
        stock_candidates.append(v)
    report['binary_candidates'] = stock_candidates
    chk['binary_scan_limited'] = truncated
    chk['found_exact_stock_elf_sha'] = any(x.get('matches_stock_pin') for x in stock_candidates)
    for k in ('base10m','query100k','gt100k','fast_graph'):
        chk['file_exists_'+k] = isreg(k)
    # Large input/graph content previously SHA-pinned by G1/G1B-C; here record byte sizes only.
    # Full rehash belongs to the eventual exact Stock preflight / one-shot runner.
    try:
        disk = shutil.disk_usage(project)
        report['disk'] = {'free_bytes': disk.free, 'total_bytes': disk.total, 'free_GiB': disk.free/(1<<30)}
    except OSError as e: report['disk_error'] = str(e)
    report['memory'] = meminfo()
    report['cpu'] = {'available_affinity_cpu_ids': sorted(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else None,
                     'four_target_cpus_present_in_affinity': set((0,2,4,6)).issubset(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else False}
    report['cgroup'] = {'v2_controllers_exist':Path('/sys/fs/cgroup/cgroup.controllers').exists(),
                        'systemd_run_available':shutil.which('systemd-run') is not None,
                        'NOTE': 'No cgroup created here. Exact hard cap & 0-swap must be verified inside future builder scope.'}
    report['warnings'].extend([
        'NO ANN BUILD in this script; no new Search; no hardware 24GiB scope was created',
        'Original 10M data/graph are stat-only here, full SHA must be rechecked for the actual Stock one-shot',
        'No automatic GO_BUILD without exact command equivalence and actual cgroup/disk gates',
        'Do NOT infer Stock10M wall/RSS or speedup from 1M results'
    ])
    essential = ['pinned_v13_compile_manifest_stock_off_matches','pinned_v13_compile_manifest_fast_off_matches',
                 'original_g1_result_sha_matches','found_exact_stock_elf_sha','file_exists_base10m',
                 'file_exists_query100k','file_exists_gt100k','file_exists_fast_graph']
    ok = all(chk.get(x) is True for x in essential) and all(report['source_snippets'][x]['status']=='REGULAR_FILE' for x in report['source_snippets'])
    report['status'] = 'R91_G1STOCK_READONLY_INVENTORY_READY_FOR_MANUAL_CLI_REVIEW_NO_BUILD' if ok else 'R91_G1STOCK_READONLY_INVENTORY_HOLD_NEEDS_REVIEW_NO_BUILD'
    out.parent.mkdir(parents=True,exist_ok=True)
    out.mkdir(exist_ok=False)
    dest = out/'inventory.json'
    with dest.open('x', encoding='utf-8') as f: json.dump(report,f,ensure_ascii=False,indent=2,sort_keys=True)
    print('R91_G1STOCK_READONLY_INVENTORY_REPORT',dest,'sha256',sha256(dest))
    print('R91_G1STOCK_READONLY_STATUS',report['status'])
    print('R91_G1STOCK_MATCHED_STOCK_BINARIES',sum(1 for x in stock_candidates if x.get('matches_stock_pin')))
    print('R91_G1STOCK_DISK_FREE_GiB',round(report.get('disk',{}).get('free_GiB',-1),3))
    print('R91_G1STOCK_NO_BUILD_NO_SEARCH_COMPLETE')
    return 0 if ok else 2

if __name__ == '__main__':
    sys.exit(main())
