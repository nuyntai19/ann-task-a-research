#!/usr/bin/env python3
"""Safely add opt-in H17 packed top-2 to an already-integrated R70 worktree.

Extract ONLY the `if (MST_DEG == 2)` selection branch from the exact H17
phase3 snapshot. Keep the pinned stock Highway selection path byte-for-byte
when R71_USE_H17=OFF. Do not copy H17 profiling or any H25 changes.
"""
import argparse
import hashlib
import pathlib
import re
import subprocess

PINNED_HEAD = "443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd"
PINNED_GRAPH_BLOB = "7c5b8c1196a3ad741dfd22fe8f35b72acae2b19f"
PINNED_UTILS_SHA256 = "ee2048738ad4462f21bdfea4a1cf7c2ac140f72fbd8875d869bc4f613d93db53"
PINNED_PHASE3_SHA256 = "b4a7e39a1ddf6c9f41f136360773aa9aef50ae7d19921b0b49b6422408c4c520"
START = "  std::vector<double> Q;\n  Q.reserve(N);"
END = "\n  // the problem with this approach is that we only merge one neighbor at a time."
MARKER = "R71_H17_PACKED_TOP2_ISOLATED"


def git(w, *argv):
    return subprocess.check_output(["git", "-C", str(w), *argv], text=True).strip()


def sha(b):
    return hashlib.sha256(b).hexdigest()


def block(reason):
    raise SystemExit("R71_H17_INTEGRATION_BLOCKED " + reason)


def extract_h17_if_branch(src):
    """Exact if-block only, excluding Phase3's profiling and fallback code."""
    sig = "void eigen_knn(GraphH &G, parlay::sequence<uint32_t> &active_indices, PR &Points, size_t MST_DEG)"
    if src.count(sig) != 1:
        block("missing or repeated Phase3 eigen_knn signature")
    start = src.index(sig)
    needle = "  if (MST_DEG == 2) {"
    if src.count(needle, start) != 1:
        block("missing or repeated Phase3 H17 selection branch")
    x = src.index(needle, start)
    opening = src.index("{", x)
    level = 0
    ending = -1
    # The pinned branch contains ordinary C++ control-flow braces, not brace-bearing strings.
    for j in range(opening, len(src)):
        if src[j] == "{":
            level += 1
        elif src[j] == "}":
            level -= 1
            if level == 0:
                ending = j + 1
                break
    if ending < 0 or not re.match(r"\s*else\s*\{", src[ending:ending+32]):
        block("Phase3 H17 branch structure unexpected")
    branch = src[x:ending]
    required = [
        "double first = std::numeric_limits<double>::infinity();",
        "double second = std::numeric_limits<double>::infinity();",
        "packFloatAndInt(dist_ij, j)",
        "unpackDouble(first)",
        "unpackDouble(second)",
        "directed_edges.emplace_back(",
    ]
    for item in required:
        if item not in branch:
            block("unexpected historical H17 selection: missing " + item)
    if "h17_" in branch.lower() or "std::chrono" in branch:
        block("H17 branch unexpectedly contains profiling instrumentation")
    return branch


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--worktree", required=True)
    p.add_argument("--phase3", required=True)
    args = p.parse_args()
    w = pathlib.Path(args.worktree).expanduser().resolve()
    historical = pathlib.Path(args.phase3).expanduser().resolve()
    if (w.name != "pipnn-clean-443a328" or w.parent.name != "H70" or w.parent.parent.name != "experiments"):
        block("worktree must be experiments/H70/pipnn-clean-443a328")
    if not w.is_dir() or git(w, "rev-parse", "HEAD") != PINNED_HEAD:
        block("worktree commit is not pinned PiPNN")
    if git(w, "hash-object", "algorithms/utils/graph.h") != PINNED_GRAPH_BLOB:
        block("stock graph.h has changed")
    if not historical.is_file() or sha(historical.read_bytes()) != PINNED_PHASE3_SHA256:
        block("historical H17 Phase3 snapshot SHA256 mismatch; do not guess")

    ph = w / "algorithms/PipNN/pipnn.h"
    utils = w / "algorithms/PipNN/pipnn_utils.h"
    cm = w / "algorithms/PipNN/CMakeLists.txt"
    if not all(x.is_file() for x in (ph, utils, cm)):
        block("missing live PiPNN files")
    source_bytes = utils.read_bytes()
    ph_before = ph.read_text()
    cm_before = cm.read_text()
    if any(MARKER in x for x in (ph_before, cm_before, source_bytes.decode())):
        if all(MARKER in x for x in (ph_before, cm_before, source_bytes.decode())):
            print("R71_H17_INTEGRATION_ALREADY_PRESENT")
            return
        block("partial H17 insertion detected; inspect before retry")
    if sha(source_bytes) != PINNED_UTILS_SHA256:
        block("worktree pipnn_utils.h differs from exact pinned stock")
    if "R70_COMPILE_TIME_RESERVOIR_SELECTION" not in ph_before or "R70_USE_TIER" not in cm_before:
        block("R70 stock/tier integration missing")
    if "R70GraphStorage lsh_graph(" not in ph_before:
        block("R70 source selection not found")
    live_pch = "        target_precompile_headers(${TARGET_NAME} PRIVATE neighbors.h)"
    if cm_before.splitlines().count(live_pch) != 1:
        block("unexpected PipNN CMake target precompiled-header block")
    if "R71_USE_H17" in cm_before or "R71_H17_TOP2" in cm_before:
        block("H17 CMake flag exists but integration marker is absent")

    source = source_bytes.decode("utf-8")
    sig = "void eigen_knn(GraphH &G, parlay::sequence<uint32_t> &active_indices, PR &Points, size_t MST_DEG)"
    if source.count(sig) != 1:
        block("unexpected stock eigen_knn signature")
    funpos = source.index(sig)
    if source.count(START, funpos) != 1 or source.count(END, funpos) != 1:
        block("stock Highway candidate selection anchors not unique")
    a = source.index(START, funpos)
    b = source.index(END, a)
    stock_block = source[a:b]
    if not all(s in stock_block for s in ("VQPartialSort(", "packFloatAndInt(", "unpackDouble(")):
        block("stock selection semantics unexpected")
    branch = extract_h17_if_branch(historical.read_text())
    # H17 OFF: original C++ stock selection block is unaltered, except for
    # preprocessor lines that disappear in preprocessing.
    replacement = (
        "  // " + MARKER + ": exact H17 Phase3 Packed Top-2; only MST_DEG==2.\n"
        "#if defined(R71_H17_TOP2)\n"
        + branch + " else {\n"
        "#endif\n"
        + stock_block + "\n"
        "#if defined(R71_H17_TOP2)\n"
        "  }\n"
        "#endif"
    )
    source_after = source[:a] + replacement + source[b:]
    if source_after.count("VQPartialSort(") != source.count("VQPartialSort("):
        block("stock comparator altered")
    if source_after.count("h17_matrix_ns") != 0:
        block("profiling instrumentation leaked into R71")

    # Build-time flag lives on same six PiPNN targets as R70; no extra dependencies.
    option = (
        "# " + MARKER + "\n"
        "option(R71_USE_H17 \"Enable H17 packed top2 for MST_DEG==2\" OFF)\n"
    )
    cm_after = option + cm_before
    cm_after = cm_after.replace(
        live_pch,
        live_pch + "\n" +
        "        if(R71_USE_H17)\n"
        "            target_compile_definitions(${TARGET_NAME} PRIVATE R71_H17_TOP2=1)\n"
        "        endif()",
        1,
    )
    banner_anchor = "        R70GraphStorage lsh_graph(Points.size(), (size_t)table_size, H, /*allocate=*/false);"
    if ph_before.count(banner_anchor) != 1:
        block("unexpected R70 graph storage constructor line")
    banner = (
        "        // " + MARKER + ": emit once per BUILD for binary provenance.\n"
        "#ifdef R71_H17_TOP2\n"
        "        std::cout << \"R71_SELECTION_VARIANT=H17_PACKED_TOP2\" << std::endl;\n"
        "#else\n"
        "        std::cout << \"R71_SELECTION_VARIANT=STOCK_HIGHWAY\" << std::endl;\n"
        "#endif\n"
    )
    ph_after = ph_before.replace(banner_anchor, banner + banner_anchor, 1)

    backup = w / "r71_h17_integration_backups"
    if backup.exists():
        block("R71 backup dir exists; refusing overwrite")
    backup.mkdir()
    (backup / "pipnn_utils.h.r70_before_h17").write_bytes(source_bytes)
    (backup / "pipnn.h.r70_before_h17").write_text(ph_before)
    (backup / "CMakeLists.pipnn.r70_before_h17").write_text(cm_before)
    # Writes only inside the isolated H70 worktree.
    utils.write_text(source_after)
    ph.write_text(ph_after)
    cm.write_text(cm_after)
    print("R71_H17_SELECTION_EXTRACTED_FROM_PHASE3")
    print("R71_H17_ONLY_MST_DEG_2_SELECT")
    print("R71_H17_INTEGRATION_PATCH_PASS")
    print("R71_INSTRUMENTATION_NOT_IMPORTED")
    print("R71_R70_TWO_TIER_RETAINED")
    print("R71_STOCK_GRAPH_H_UNCHANGED", git(w, "hash-object", "algorithms/utils/graph.h"))
    print("R71_STOCK_SELECTION_PRESERVED_WITH_FLAG_OFF")
    print("R71_BACKUP", backup)
    print("R71_BENCHMARK_NOT_RUN")


if __name__ == "__main__":
    main()
