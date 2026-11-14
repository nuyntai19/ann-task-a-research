#!/usr/bin/env bash
# ANN PiPNN -- non-destructive unified project home.
# Creates a navigation/index directory only; NEVER moves/edits sources, graphs, data, logs or binaries.
# The generated files are marked and only those marked files may be refreshed by rerunning this script.
set -Eeuo pipefail
umask 022
MODE="${1:---setup}"
case "$MODE" in --setup|--check) ;; *) echo 'USAGE: bash ANN_Project_Home_Setup_v1_0.sh [--setup|--check]' >&2; exit 2;; esac
command -v python3 >/dev/null || { echo 'ERROR: python3 required' >&2; exit 2; }
python3 - "$HOME/ann-task-a" "$MODE" <<'PY'
from __future__ import annotations
import csv, hashlib, os, pathlib, struct, sys
from datetime import datetime, timezone

project = pathlib.Path(sys.argv[1]).expanduser()
mode = sys.argv[2]
hub = project / '00_PROJECT_HOME'
marker = '<!-- GENERATED_BY_ANN_PROJECT_HOME_V1_0. Keep personal notes in 09_MY_NOTES.md. -->'

if not project.is_dir():
    raise SystemExit(f'PROJECT_NOT_FOUND={project}; no changes made')

sections = [
    '01_SOURCE', '02_BINARIES', '03_DATA_AND_GT', '04_RUNS_AND_GRAPHS',
    '05_RESULTS_AND_COUNTERS', '06_LOGS', '07_SCRIPTS', '08_SEARCH_EVALUATOR'
]
if mode == '--setup':
    for p in [hub, *[hub / x for x in sections]]:
        if p.exists() and not p.is_dir():
            raise SystemExit(f'HUB_PATH_BLOCKED_NOT_DIRECTORY={p}')
        p.mkdir(parents=True, exist_ok=True)

records = []
missing = []
conflicts = []

def ref(rel: str, target: pathlib.Path, purpose: str):
    link = hub / rel
    target = target.expanduser().absolute()
    if not target.exists():
        state='MISSING_TARGET'
        missing.append(f'{rel}: {target}')
    elif mode == '--check':
        state='EXISTS_IN_SOURCE' if not link.is_symlink() else ('LINK_OK' if os.path.realpath(link)==str(target.resolve()) else 'LINK_DIFFERENT')
    elif link.is_symlink():
        state='LINK_OK' if os.path.realpath(link)==str(target.resolve()) else 'LINK_DIFFERENT_KEEP_EXISTING'
        if state.startswith('LINK_DIFFERENT'):
            conflicts.append(f'{link} already points to {os.readlink(link)}; expected {target}')
    elif link.exists():
        state='PATH_OCCUPIED_KEEP_EXISTING'
        conflicts.append(f'{link} already exists, not replaced')
    else:
        link.symlink_to(target, target_is_directory=target.is_dir())
        state='LINK_CREATED'
    records.append((state, rel, str(target), purpose))
    return state

r86 = project / 'experiments/R86'
source = r86 / 'r86_v1_2_source'
build = r86 / 'gates/highway_r85_four_binary_jvYREW'
run = r86 / 'benchmarks/sift100k_a0a4_hw85_7ueCvd'
export = r86 / 'analysis_exports/a0a4_sift100k_postbuild_0jSWm82d'
g2 = r86 / 'gates/g2_hw85_native10k_JWuLB9'

# Links make this folder a single entry point. Targets remain authoritative in their original positions.
ref('01_SOURCE/R86_PINNED_SOURCE', source, 'Main 2026-11-13 instrumented PiPNN source; never silently edit')
ref('01_SOURCE/PIPNN_CORE_CODE', source/'algorithms/PipNN', 'Look at pipnn.h / pipnn_utils.h / CMakeLists.txt')
ref('01_SOURCE/H70_HISTORICAL_REFERENCE', project/'experiments/H70/pipnn-clean-443a328', 'Historical baseline; not the active build source')
ref('02_BINARIES/R86_HW85_FOUR_BINARIES', build, 'Pinned stock_off, stock_on, h17_off, h17_on builds and manifest')
ref('03_DATA_AND_GT/SIFT100K_BASE.fbin', project/'data/sift100k.fbin', '100,000 base vectors; dataset SHA from project runs')
ref('03_DATA_AND_GT/SIFT100K_GT300_CANDIDATE.ibin', project/'data/sift100k_gt300.ibin', 'Ground-truth candidate, NOT VERIFIED against query/base yet')
ref('03_DATA_AND_GT/SIFT1M_GT_DIFFERENT_DATASET.ibin', project/'data/sift1m_gt.ibin', 'Different dataset GT: do not use for SIFT100K unless independently proven')
ref('04_RUNS_AND_GRAPHS/SIFT100K_A0_A4_20_RUNS', run, '20 graph runs; runs.csv, build_only_summary.json and per-run folders')
ref('04_RUNS_AND_GRAPHS/SIFT10K_G2_VALIDATION', g2, '10K ON/OFF counter calibration; not the main 100K benchmark')
ref('05_RESULTS_AND_COUNTERS/SIFT100K_POSTBUILD_AUDIT', export, 'Audit summary and C_WORK_100K_counter_records.csv')
ref('05_RESULTS_AND_COUNTERS/audit_summary.json', export/'audit_summary.json', 'Postbuild verification overview')
ref('05_RESULTS_AND_COUNTERS/C_WORK_100K_counter_records.csv', export/'C_WORK_100K_counter_records.csv', 'Raw per-depth counters for 5 ON arms (upload this file when asked)')
ref('05_RESULTS_AND_COUNTERS/graph_sha_and_off_times.csv', export/'graph_sha_and_off_times.csv', 'Per-run graph SHA and OFF build timing')
ref('05_RESULTS_AND_COUNTERS/runs.csv', run/'runs.csv', '20 run IDs, protocol and paths')
ref('05_RESULTS_AND_COUNTERS/build_only_summary.json', run/'build_only_summary.json', 'A0-A4 build time/RSS and graph SHA stability')
ref('05_RESULTS_AND_COUNTERS/protocol.txt', run/'protocol.txt', 'Actual CPU affinity and command protocol')

logs = {
    'A0_A4_100K_BUILD_LAUNCHER.log': pathlib.Path.home()/'R86_HW85_A0A4_100K_launcher.log',
    'SIFT100K_POSTBUILD_AUDIT.log': pathlib.Path.home()/'R86_A0A4_100K_postbuild_audit.log',
    'HW85_FOUR_BINARY_BUILD.log': pathlib.Path.home()/'R86_HW85_four_build_launcher.log',
    'G2_10K_V1_2.log': pathlib.Path.home()/'R86_HW85_G2_v1_2_launcher.log',
    'HW85_STOCK_CONTROL.log': pathlib.Path.home()/'R86_G1_Highway_R85_launcher.log',
}
for name,p in logs.items(): ref('06_LOGS/'+name,p,'Launcher log; per-run log is inside SIFT100K_A0_A4_20_RUNS/<run_id>/')
script_names = [
'R86_HW85_SIFT100K_A0_A4_Build_Counters_v1_0.sh',
'R86_HW85_SIFT100K_PostBuild_Audit_v1_0.sh',
'R86_HW85_G2_Native10K_Resume_v1_2.sh',
'R86_Highway_R85_Four_Binaries_v1_0.sh',
'R86_G1_Highway_R85_OneBinary_Control_v1_0.sh',
]
for name in script_names:
    ref('07_SCRIPTS/'+name, pathlib.Path.home()/'Downloads'/name, 'Original experiment script in Downloads; do not rewrite')
ref('08_SEARCH_EVALUATOR/R70_RECALL_RUNNER_CANDIDATE.py', project/'experiments/H70/tools/R70_recall_kit/r70_run_recall.py', 'Historical evaluator candidate, NOT yet certified for 100K')
ref('08_SEARCH_EVALUATOR/R71_FACTORIAL_EVALUATOR_CANDIDATE.py', project/'experiments/H70/tools/R71_factorial_quality_kit/r71_evaluate_12_graphs.py', 'Historical evaluator candidate, NOT yet certified for 100K')
ref('08_SEARCH_EVALUATOR/PIPNN_NATIVE_GRAPH_IO_AND_SEARCH_CODE', source/'algorithms/PipNN', 'Reference for native graph loading/search options')

# Conservative data inventory: do not silently select a query file based on filename alone.
queries=[]
data_dir=project/'data'
if data_dir.is_dir():
    for pat in ('*query*','*queries*','*q100k*'):
        queries.extend(p for p in data_dir.rglob(pat) if p.is_file() and p.suffix.lower() in {'.fbin','.fvecs','.bin','.npy','.npz'})
queries=sorted(set(queries))

gt=project/'data/sift100k_gt300.ibin'
gt_message='NOT_PRESENT'
if gt.is_file():
    b=gt.read_bytes()
    if len(b)>=8:
        nq,k=struct.unpack('<II',b[:8])
        expected=8+nq*k*4
        if 0<nq<=1_000_000 and 0<k<=100000 and expected==len(b):
            count=nq*k
            ids=struct.unpack('<'+str(count)+'I',b[8:]) if count<1_000_000 else ()
            gt_message=(f'FORMAT_PLAUSIBLE: n_queries={nq}, neighbors_per_query={k}, bytes={len(b)}, '
                        f'min_id={min(ids) if ids else "NOT_CHECKED"}, max_id={max(ids) if ids else "NOT_CHECKED"}. '
                        'NOT VERIFIED: exact distances, query alignment, or base-dataset identity')
        else:
            gt_message=f'HEADER_UNVERIFIED: first_u32={nq},{k}, bytes={len(b)}, expected_if_u32={expected}'
    else:
        gt_message='FILE_TOO_SHORT'

runs_path=run/'runs.csv'
run_report='NOT_AVAILABLE'
if runs_path.is_file():
    with runs_path.open(newline='') as f:
        rows=list(csv.DictReader(f))
    found=0; nonempty=0;missing_graphs=[]
    for row in rows:
        run_id=row.get('run_id','')
        gp=run/run_id/(run_id+'.graph')
        if gp.is_file():
            found+=1
            if gp.stat().st_size>0:nonempty+=1
        else:missing_graphs.append(run_id)
    run_report=f'runs.csv={len(rows)} rows; graph_present={found}; graph_nonempty={nonempty}; graph_missing={len(missing_graphs)}'

# Write only files owned and marked by this setup tool; never overwrite unmarked personal files.
def write_generated(name: str, content: str):
    path=hub/name
    if mode=='--check': return
    body=marker+'\n'+content
    if path.exists() and not path.is_file():
        conflicts.append(f'{path}: existing non-file; keeping')
        return
    if path.exists() and not path.read_text(encoding='utf-8').startswith(marker):
        conflicts.append(f'{path}: personal file (no generation marker), not replaced')
        return
    temp=path.with_suffix(path.suffix+'.new')
    temp.write_text(body,encoding='utf-8')
    temp.replace(path)

where=f'''# ANN / PiPNN -- PROJECT HOME

**One place to navigate:** `{hub}`. **Important:** this is a SAFE INDEX built from symlinks; source, input data, graphs and logs stay at their original paths. Do not manually move the old folders.

## Open these files first

| Need | Open here | What it is |
|---|---|---|
| Main C++ source | `01_SOURCE/PIPNN_CORE_CODE/pipnn.h` and `pipnn_utils.h` | R86 PiPNN implementation used in the 100K builds |
| Full pinned source tree | `01_SOURCE/R86_PINNED_SOURCE/` | CMake + PiPNN sources |
| Compiled binaries | `02_BINARIES/R86_HW85_FOUR_BINARIES/` | `build_stock_off`, `build_stock_on`, `build_h17_off`, `build_h17_on` |
| Base vectors | `03_DATA_AND_GT/SIFT100K_BASE.fbin` | n=100,000 input |
| Candidate ground truth | `03_DATA_AND_GT/SIFT100K_GT300_CANDIDATE.ibin` | NOT YET CERTIFIED; query must match |
| Built ANN graphs | `04_RUNS_AND_GRAPHS/SIFT100K_A0_A4_20_RUNS/` | 20 graph files in subdirs named `run_id` |
| Build stdout logs | `04_RUNS_AND_GRAPHS/SIFT100K_A0_A4_20_RUNS/<run_id>/<run_id>.build.log` | Per-graph logs; do not use random old Hxx logs |
| High-level logs | `06_LOGS/` | nohup launch log and audit log |
| Summary of timings/RSS | `05_RESULTS_AND_COUNTERS/build_only_summary.json` | Five arm medians + SHA stability |
| Counter identities | `05_RESULTS_AND_COUNTERS/audit_summary.json` | 20 graph SHA checks and 5/5 counter checks |
| Detailed counter CSV | `05_RESULTS_AND_COUNTERS/C_WORK_100K_counter_records.csv` | Data to upload for full per-depth Sheet import |
| Status of search | `08_SEARCH_EVALUATOR/` and `PROJECT_STATUS.md` | Evaluator is a candidate; query and exact GT not yet confirmed |
| Study notes | `09_MY_NOTES.md` | Your own notes, safe to edit |

## 100K experiment arms

A0 = Stock PiPNN C160 K1024 N2; A1 = H17-only C160 K1024 N2; A2 = H17 C64 K1024 N2; A3 = H17 C64 K512 N2; A4 = H17 C64 K512 N1. Each arm has 3 OFF timing runs + 1 ON counter run.

## What is verified, what is missing?

- Verified: 20/20 graph files nonempty and SHA checked by the separate postbuild audit; 5/5 ON counter mathematical identities pass. Build wall-time medians (A0..A4) = 3.26, 2.68, 2.66, 2.08, 1.10 s; peak RSS KiB = 415664, 414848, 339940, 341152, 336868.
- CAUTION: all five arms have non-identical graph SHA across repeats, and at least the OFF graph byte lengths differ. Independent graph adjacency validation and Recall are NOT DONE.
- Not yet measured: SIFT100K exact-GT-matched Recall@10, search latency, p95/p99, QPS and NDC. Do not call A4 the best ANN configuration before these are checked.
- Detailed counter CSV is already linked here; do not move it out of the original export directory.

## Google report destinations

- Google Sheet (A_SYSTEM, B_SEARCH, C_WORK, E_PROTOCOL, ABLATION, WEEK_PLAN): https://docs.google.com/spreadsheets/d/12ApqgMV8YykflyFXUT2VMbUhgyiGirtoOmRWCXCz3Ek/edit
- Google Doc (methodology and H45 post-build audit): https://docs.google.com/document/d/185pgBkUudDkF-HvqxM2xPgV3f1Q7hwjbIuusq6AnIbc/edit

## Quick commands

```bash
cd "$HOME/ann-task-a/00_PROJECT_HOME"
cat PROJECT_STATUS.md
ls -la 05_RESULTS_AND_COUNTERS
ls 04_RUNS_AND_GRAPHS/SIFT100K_A0_A4_20_RUNS | head
# Open the whole hub in Files (GNOME):
xdg-open "$HOME/ann-task-a/00_PROJECT_HOME"
```

**Rule from now on:** any future campaign produces raw files under `experiments/R86/...`; link its final output here and register the run in Google Sheets. Never create a second 'main project' directory.
'''
status=f'''# PROJECT STATUS (auto-generated)

Generated at UTC: {datetime.now(timezone.utc).isoformat(timespec='seconds')}

- Main project root: `{project}`
- Navigation hub: `{hub}`
- Current active code: `{source}`
- Main 100K campaign: `{run}`
- Graph inventory: **{run_report}**
- 100K counter audit: `COUNTER_IDENTITIES_PASS_ALL_FIVE_100K` (from user terminal log; files under analysis_exports)
- 100K search: **NOT RUN / B_SEARCH not filled**
- Ground-truth SIFT100K candidate `{gt.name}`: {gt_message}
- Candidate query files found under `data` with obvious names: **{len(queries)}**
'''
if queries:
    status+='\nCandidate queries (not yet chosen):\n'+'\n'.join('- `'+str(p)+'`' for p in queries[:50])+'\n'
else:
    status+='\n**BLOCKER:** no suitable query candidate found by this filename scan under `data`. A query file may exist elsewhere/under another name. Do not run Recall using a guessed query.\n'
status+='''
## Next work

1. Verify native graph adjacency format and one or more 100K graph variants (no rebuild).
2. Find/verify a query dataset and match it to the `sift100k_gt300.ibin` candidate; independently recompute a sample of exact neighbor answers using SIFT100K base.
3. Pin ONE evaluator and CPU/query protocol; run matched-Recall search on already-built graphs; upload B_SEARCH metrics.
4. Only after B_SEARCH, draw A0..A4 conclusion and n-scaling plots.
'''

manifest=['\t'.join(['status','hub_link','target','description'])]
manifest.extend('\t'.join(z.replace('\t',' ') for z in row) for row in records)
write_generated('00_START_HERE.md',where)
write_generated('PROJECT_STATUS.md',status)
write_generated('LINK_MAP.tsv','\n'.join(manifest)+'\n')
notes=hub/'09_MY_NOTES.md'
if mode=='--setup' and not notes.exists():
    notes.write_text('# My research notes\n\n(Write freely here: this file is never overwritten by the setup script.)\n',encoding='utf-8')

print('ANN_PROJECT_HOME_MODE='+mode)
print('HUB='+str(hub))
print('GRAPHS='+run_report)
print('SIFT100K_GT='+gt_message)
print('QUERY_CANDIDATES='+str(len(queries)))
print('LINKS_PRESENT_OR_CREATED='+str(sum(x[0] in {'LINK_OK','LINK_CREATED','EXISTS_IN_SOURCE'} for x in records)))
print('LINKS_MISSING_TARGET='+str(sum(x[0]=='MISSING_TARGET' for x in records)))
if missing:
    for s in missing: print('MISSING_REFERENCE='+s)
if conflicts:
    for s in conflicts:print('KEEP_EXISTING_CONFLICT='+s)
print('NO_SOURCE_DATA_GRAPH_BINARY_OR_LOG_WAS_MODIFIED')
print('PROJECT_HUB_READY' if mode=='--setup' else 'PROJECT_HUB_CHECK_COMPLETE')
PY
