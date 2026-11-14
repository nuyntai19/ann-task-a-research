#!/usr/bin/env python3
"""R85-B1 Step4 v3: safely stage instrumented PiPNN, omitting *dangling* symlinks.

This script never invokes a native ANN dataset BUILD; --configure/--compile are opt-in.
It uses the user's modified H70 tree as input, not a clean upstream checkout.
"""
import argparse
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

PINNED_SOURCE_SHA = 'f4391ad8712d7757423dca872f9042c3271660dffde384a85b93854b9692f288'
DEFAULT_ROOT = Path.home() / 'ann-task-a/experiments/H70/pipnn-clean-443a328'
DEFAULT_PATCH = Path.home() / 'ann-task-a/experiments/H85/r85_b1_controlled/patch_v1'
DEFAULT_OUT = Path.home() / 'ann-task-a/experiments/H85/r85_b1_controlled/isolation_v2'
IGNORE_DIRS = {'.git', '.cache', '__pycache__', '.venv', 'venv', 'build', 'build-debug', 'build-release',
               'cmake-build-debug', 'cmake-build-release', 'CMakeFiles', 'r70_integration_backups',
               'r71_h17_integration_backups', '.idea'}
IGNORE_FILES = {'.DS_Store'}


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def fail(msg):
    raise RuntimeError(msg)


def ignore(folder, names):
    return [s for s in names if s in IGNORE_DIRS or s in IGNORE_FILES or
            (s.startswith('cmake-build-') and (Path(folder) / s).is_dir())]


def roots(args):
    src = args.source.resolve(strict=True)
    patch = args.patch.resolve(strict=True)
    out = args.out.expanduser().resolve()
    if src == out or src in out.parents or out in src.parents:
        fail('REFUSE_NESTED_SOURCE_AND_DESTINATION')
    if src == patch or src in patch.parents or patch in src.parents:
        fail('PATCH_MUST_BE_OUTSIDE_SOURCE')
    if out == patch or patch in out.parents or out in patch.parents:
        fail('PATCH_AND_OUTPUT_MUST_BE_SEPARATE')
    return src, patch, out


def check_inputs(src, patch):
    original = src / 'algorithms/PipNN/pipnn.h'
    replacement = patch / 'pipnn.h.instrumented'
    manifest = patch / 'manifest.json'
    for p in (original, replacement, manifest, src / 'CMakeLists.txt', src / 'algorithms/PipNN/CMakeLists.txt'):
        if not p.is_file():
            fail('MISSING_INPUT ' + str(p))
    s = sha(original)
    if s != PINNED_SOURCE_SHA:
        fail('SOURCE_DRIFT ' + s)
    m = json.loads(manifest.read_text())
    if m.get('source_sha256') != PINNED_SOURCE_SHA or m.get('instrumented_header_sha256') != sha(replacement):
        fail('PATCH_MANIFEST_SHA_MISMATCH')
    txt = replacement.read_text()
    for marker in ('R85_B1_SNAPSHOT_BEGIN', 'R85_B1_SNAPSHOT_PASS', 'R85_B1_SNAPSHOT_DIR'):
        if marker not in txt:
            fail('MISSING_SNAPSHOT_MARKER ' + marker)
    cmake = (src / 'algorithms/PipNN/CMakeLists.txt').read_text()
    # CMake options and compiler macros are different identifiers.
    # Only these two options actually control the native PiPNN build.
    for pattern in (r'option\s*\(\s*R71_USE_H17\b',
                    r'option\s*\(\s*R70_USE_TIER\b',
                    r'if\s*\(\s*R71_USE_H17\s*\)',
                    r'if\s*\(\s*R70_USE_TIER\s*\)',
                    r'\bR71_H17_TOP2=1\b', r'\bR70_TWO_TIER=1\b'):
        if not re.search(pattern, cmake):
            fail('UNKNOWN_ACTUAL_CMAKE_OPTION_OR_DEFINITION ' + pattern)
    return {'original_sha256': s, 'instrumented_sha256': sha(replacement),
            'patch_manifest_sha256': sha(manifest)}


def check_symlinks(src):
    """Audit symlinks without following them during staging.

    Only relative links resolving to *existing* in-tree paths are preserved.
    Dangling links are excluded (never dereferenced), and every exclusion is
    recorded in the isolation manifest. Live external or absolute links fail.
    """
    errors, omitted, kept = [], [], []
    for dirpath, dirnames, filenames in os.walk(src, followlinks=False):
        dirnames[:] = [n for n in dirnames if n not in IGNORE_DIRS and not n.startswith('cmake-build-')]
        for n in dirnames + filenames:
            p = Path(dirpath) / n
            if not p.is_symlink():
                continue
            raw = os.readlink(p)
            rel = str(p.relative_to(src))
            # A broken symlink never supplies source code. Omitting it is safer
            # than keeping an accidental dependency on its outside location.
            if not p.exists():
                omitted.append({'path': rel, 'target': raw, 'reason': 'dangling'})
                continue
            if os.path.isabs(raw):
                errors.append(rel + ' -> ' + raw + ' (absolute live target)')
                continue
            target = p.resolve(strict=True)
            if target != src and src not in target.parents:
                errors.append(rel + ' -> ' + str(target) + ' (external live target)')
                continue
            kept.append({'path': rel, 'target': raw})
    if errors:
        fail('LIVE_EXTERNAL_OR_ABSOLUTE_SYMLINKS ' + repr(errors[:12]))
    return omitted, kept


def stage_ignore(folder, names):
    """Keep the old ignored build directories and omit dangling symlinks."""
    skipped = set(ignore(folder, names))
    for name in names:
        p = Path(folder) / name
        if p.is_symlink() and not p.exists():
            skipped.add(name)
    return sorted(skipped)


def stage(args, src, patch, out):
    checks = check_inputs(src, patch)
    stage_root = out / 'source'
    state = out / 'isolation_manifest.json'
    if state.exists():
        m = json.loads(state.read_text())
        if m.get('checks') != checks or sha(stage_root / 'algorithms/PipNN/pipnn.h') != checks['instrumented_sha256']:
            fail('EXISTING_STAGE_DRIFT')
        print('R85_B1_STEP4_STAGE_REUSE_VERIFIED ' + str(stage_root), flush=True)
        return stage_root
    if out.exists():
        fail('EXISTING_UNMANAGED_OUTPUT_REFUSE ' + str(out))
    omitted, kept = check_symlinks(src)
    for item in omitted:
        print('R85_B1_STEP4_SKIPPED_DANGLING_SYMLINK ' + item['path'] + ' -> ' + item['target'], flush=True)
    print('R85_B1_STEP4_SYMLINK_AUDIT kept=' + str(len(kept)) + ' skipped=' + str(len(omitted)), flush=True)
    out.mkdir(parents=True, exist_ok=False)
    try:
        shutil.copytree(src, stage_root, symlinks=True, ignore=stage_ignore)
        dest = stage_root / 'algorithms/PipNN/pipnn.h'
        if sha(dest) != checks['original_sha256']:
            fail('STAGED_SOURCE_MISMATCH')
        shutil.copy2(patch / 'pipnn.h.instrumented', dest)
        if sha(dest) != checks['instrumented_sha256']:
            fail('INSTRUMENTATION_COPY_SHA_MISMATCH')
        if sha(src / 'algorithms/PipNN/pipnn.h') != checks['original_sha256']:
            fail('H70_SOURCE_CHANGED_DURING_STAGE')
        state.write_text(json.dumps({
            'checks': checks, 'omitted_dangling_symlinks': omitted,
            'preserved_in_tree_symlinks': kept, 'source': str(src), 'patch': str(patch),
            'staged_source': str(stage_root), 'cmake_build': str(out / 'cmake-build'),
            'variant': 'H17_FLAT', 'created_at_utc': datetime.now(timezone.utc).isoformat(),
            'scope': 'STAGING_AND_OPTIONAL_COMPILATION_ONLY_NO_NATIVE_BUILD'}, indent=2) + '\n')
    except Exception:
        # Leave partial output for inspection; NEVER delete existing user's work.
        print('R85_B1_STEP4_PARTIAL_STAGE ' + str(out), file=sys.stderr)
        raise
    print('R85_B1_STEP4_STAGED_H70_UNCHANGED ' + str(stage_root), flush=True)
    print('R85_B1_STEP4_INSTRUMENTED_SHA256 ' + checks['instrumented_sha256'], flush=True)
    return stage_root


def runlog(cmd, log, cwd=None):
    print('R85_B1_STEP4_COMMAND ' + ' '.join(map(str,cmd)), flush=True)
    with log.open('w') as f:
        p = subprocess.run(cmd, cwd=cwd, stdout=f, stderr=subprocess.STDOUT, text=True)
    if p.returncode:
        tail = log.read_text(errors='replace')[-3500:]
        fail(f'COMMAND_FAILED rc={p.returncode} log={log}\n{tail}')
    print('R85_B1_STEP4_LOG ' + str(log), flush=True)


def configure(args, out, stage_root):
    b = out / 'cmake-build'
    cm = shutil.which('cmake')
    if not cm:
        fail('CMAKE_NOT_FOUND')
    # Keep all CMake-generated artifacts in H85 rather than H70.
    cmd = [cm, '-S', str(stage_root), '-B', str(b),
           '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
           # Discard flags from failed v2 configure; they were unused options.
           '-UR71_H17_TOP2', '-UR70_TWO_TIER',
           '-DR71_USE_H17=ON', '-DR70_USE_TIER=OFF']
    if args.configure_opt:
        for opt in args.configure_opt:
            if not opt.startswith('-D') or '=' not in opt:
                fail('BAD_CMAKE_OPTION ' + opt)
            cmd.append(opt)
    runlog(cmd, out / 'cmake_configure.log')
    cache = (b / 'CMakeCache.txt').read_text()
    for key, expected in [('R71_USE_H17', 'ON'), ('R70_USE_TIER', 'OFF')]:
        mm = re.search(r'^' + key + r':\w+=(.*)$', cache, re.MULTILINE)
        if mm is None or mm.group(1) != expected:
            fail('CMAKE_VARIANT_NOT_CONFIRMED ' + key + ' expected=' + expected)
    # CMake accepts unused -D flags. Validate actual compiler commands, not just cache entries.
    compiledb = b / 'compile_commands.json'
    if not compiledb.is_file():
        fail('MISSING_COMPILE_COMMANDS_CANNOT_VERIFY_H17_VARIANT')
    records = json.loads(compiledb.read_text())
    h17_flat_targets = []
    for rec in records:
        cmd_text = rec.get('command') or ' '.join(rec.get('arguments', []))
        if 'neighborsTime.C' not in rec.get('file', ''):
            continue
        has_h17 = re.search(r'(?<!\S)-DR71_H17_TOP2(?:=1)?(?=\s|$)', cmd_text)
        has_tier = re.search(r'(?<!\S)-DR70_TWO_TIER(?:=1)?(?=\s|$)', cmd_text)
        m_target = re.search(r'CMakeFiles/([^/]+)\.dir/', cmd_text)
        if has_h17 and not has_tier and m_target:
            h17_flat_targets.append(m_target.group(1))
    h17_flat_targets = sorted(set(h17_flat_targets))
    if not h17_flat_targets:
        p = stage_root / 'algorithms/PipNN/CMakeLists.txt'
        context = '\n'.join(f'{i}: {s}' for i,s in enumerate(p.read_text().splitlines(),1)
                            if ('R71' in s or 'R70' in s or 'if(' in s or 'option(' in s))
        fail('NO_ACTUAL_H17_FLAT_COMPILER_COMMAND; check CMake option names. Relevant CMake lines:\n' + context)
    (out / 'verified_h17_flat_targets.json').write_text(json.dumps(h17_flat_targets,indent=2)+'\n')
    print('R85_B1_STEP4_CMAKE_VERIFIED_H17_FLAT_TARGETS ' + json.dumps(h17_flat_targets), flush=True)
    return b


def compile_target(args, out):
    b = out / 'cmake-build'
    if not (b / 'CMakeCache.txt').exists():
        fail('RUN_--configure_FIRST')
    r = subprocess.run(['cmake', '--build', str(b), '--target', 'help'], stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, text=True)
    if r.returncode:
        fail('CMAKE_TARGET_HELP_FAILED ' + r.stdout[-2000:])
    candidates = sorted(set(re.findall(r'neighbors-pipnn_[A-Za-z0-9_+.-]+', r.stdout)))
    targetfile = out / 'verified_h17_flat_targets.json'
    if not targetfile.is_file():
        fail('NO_VERIFIED_H17_FLAT_TARGETS_RUN_--configure_FIRST')
    verified = json.loads(targetfile.read_text())
    candidates = sorted(set(candidates) & set(verified))
    print('R85_B1_STEP4_VERIFIED_BUILD_TARGET_CANDIDATES ' + json.dumps(candidates), flush=True)
    target = args.target
    if not target:
        if len(candidates) != 1:
            fail('AMBIGUOUS_VERIFIED_H17_FLAT_TARGET: specify --target using one of the printed candidates')
        target = candidates[0]
    if target not in candidates:
        fail('TARGET_NOT_VERIFIED_H17_FLAT ' + target)
    runlog(['cmake', '--build', str(b), '--target', target, '--parallel', '2'], out / 'cmake_compile.log')
    possible = [p for p in b.rglob(target) if p.is_file() and os.access(p, os.X_OK)]
    if len(possible) != 1:
        fail('BINARY_NOT_UNIQUE ' + repr([str(x) for x in possible]))
    binary = possible[0]
    print('R85_B1_STEP4_NATIVE_BINARY ' + str(binary), flush=True)
    print('R85_B1_STEP4_NATIVE_BINARY_SHA256 ' + sha(binary), flush=True)
    print('R85_B1_STEP4_COMPILE_PASS_NO_DATASET_BUILD', flush=True)


def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        r = Path(td) / 'repo'; (r / 'algorithms/PipNN').mkdir(parents=True)
        (r / 'CMakeLists.txt').write_text('project(Fake)\n')
        (r / 'algorithms/PipNN/CMakeLists.txt').write_text('''
option(R71_USE_H17 "h17" OFF)
option(R70_USE_TIER "tier" OFF)
if(R71_USE_H17)
  target_compile_definitions(${TARGET_NAME} PRIVATE R71_H17_TOP2=1)
endif()
if(R70_USE_TIER)
  target_compile_definitions(${TARGET_NAME} PRIVATE R70_TWO_TIER=1)
endif()
''')
        (r / '.git').mkdir(); (r / '.git/never_copy').write_text('x')
        (r / 'build').mkdir(); (r / 'build/never_copy').write_text('x')
        z = Path(td) / 'out'; shutil.copytree(r,z, symlinks=True,ignore=ignore)
        assert not (z / '.git').exists() and not (z / 'build').exists()
        assert (z / 'algorithms/PipNN/CMakeLists.txt').is_file()
        # v2 regression: broken links are omitted, but live internal links are preserved.
        (r / 'algorithms' / 'bench').mkdir()
        (r / 'algorithms' / 'bench' / 'parlay').symlink_to('missing-parlay')
        (r / 'algorithms' / 'bench' / 'valid').symlink_to('../PipNN/CMakeLists.txt')
        omitted, kept = check_symlinks(r)
        assert [x['path'] for x in omitted] == ['algorithms/bench/parlay'], omitted
        assert [x['path'] for x in kept] == ['algorithms/bench/valid'], kept
        z2 = Path(td) / 'out2'
        shutil.copytree(r, z2, symlinks=True, ignore=stage_ignore)
        assert not (z2 / 'algorithms/bench/parlay').is_symlink()
        assert (z2 / 'algorithms/bench/valid').is_symlink()
        assert (z2 / 'algorithms/bench/valid').is_file()
        # No valid symlink may resolve outside the tree, nor point absolutely.
        outer = Path(td) / 'outside'; outer.write_text('x')
        (r / 'algorithms/bench/leak').symlink_to(outer)
        try:
            check_symlinks(r)
            raise AssertionError('external live symlink accepted')
        except RuntimeError as e:
            assert 'LIVE_EXTERNAL_OR_ABSOLUTE_SYMLINKS' in str(e)
        # Verify real CMake option/definition names, not misleading macro-as-option flags.
        assert re.search(r'option\s*\(\s*R71_USE_H17\b', (r/'algorithms/PipNN/CMakeLists.txt').read_text())
        assert '-DR71_USE_H17=ON' in inspect.getsource(configure)
        assert '-DR70_USE_TIER=OFF' in inspect.getsource(configure)
        assert '-DR71_H17_TOP2=ON' not in inspect.getsource(configure)
        assert '-DR70_TWO_TIER=OFF' not in inspect.getsource(configure)
    print('R85_B1_STEP4_V3_SELFTEST_PASS_NO_BUILD', flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--selftest', action='store_true')
    p.add_argument('--source', type=Path, default=DEFAULT_ROOT)
    p.add_argument('--patch', type=Path, default=DEFAULT_PATCH)
    p.add_argument('--out', type=Path, default=DEFAULT_OUT)
    p.add_argument('--stage', action='store_true')
    p.add_argument('--configure', action='store_true')
    p.add_argument('--compile', action='store_true')
    p.add_argument('--target', help='CMake neighbors-pipnn_* target, only for --compile')
    p.add_argument('--configure-opt', action='append', help='Optional CMake -DNAME=VALUE, repeatable')
    args = p.parse_args()
    if args.selftest:
        selftest(); return
    if not (args.stage or args.configure or args.compile):
        p.error('choose --stage, --configure and/or --compile')
    src, patch, out = roots(args)
    if args.stage:
        staged = stage(args, src, patch, out)
    else:
        checks = check_inputs(src, patch)
        state = out / 'isolation_manifest.json'
        if not state.is_file() or json.loads(state.read_text()).get('checks') != checks:
            fail('NO_VERIFIED_ISOLATED_STAGE_RUN_--stage_FIRST')
        staged = out / 'source'
        if sha(staged / 'algorithms/PipNN/pipnn.h') != checks['instrumented_sha256']:
            fail('STAGED_HEADER_DRIFT')
    if args.configure:
        configure(args, out, staged)
    if args.compile:
        compile_target(args, out)

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('R85_B1_STEP4_FAIL_CLOSED ' + repr(exc), file=sys.stderr)
        sys.exit(2)
