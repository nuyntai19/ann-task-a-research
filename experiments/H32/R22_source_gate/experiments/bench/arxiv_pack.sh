#!/usr/bin/env bash
# Stage, verify and pack the arXiv tarballs for both papers (dense: the long
# version, multi-file since 2026-10-06: dense.tex + body.tex + appendix-long.tex
# + dense.bbl).
#   bash bench/arxiv_pack.sh            # both
#   bash bench/arxiv_pack.sh dense      # one
# Verification simulates arXiv exactly: LaTeX only, three passes, NO .bib
# present, so a stale or missing .bbl shows up as undefined citations here
# rather than on the submission server.
# (bash 3.2 compatible -- macOS ships no associative arrays.)
set -e
S="${TMPDIR:-/tmp}/arxiv-stage"; OUT="${OUT:-$HOME/Desktop}"
TARGETS="${@:-fgraft dense}"
rm -rf "$S"; mkdir -p "$S"
for N in $TARGETS; do
  case "$N" in
    fgraft) SUB=FGRAFTPaper; FILES="fgraft.tex fgraft.bbl fig_sweep.pdf" ;;
    dense)  SUB=DensePaper;  FILES="dense.tex body.tex appendix-long.tex dense.bbl" ;;
    *) echo "unknown paper: $N (expected fgraft or dense)"; exit 2 ;;
  esac
  D="$HOME/code/claude/IA/$SUB"
  cd "$D"
  pdflatex -interaction=nonstopmode "$N" >/dev/null 2>&1
  bibtex "$N" >/dev/null 2>&1
  pdflatex -interaction=nonstopmode "$N" >/dev/null 2>&1
  pdflatex -interaction=nonstopmode "$N" >/dev/null 2>&1
  mkdir -p "$S/$N"; cp $FILES "$S/$N/"

  T=$(mktemp -d); cp "$S/$N"/* "$T/"; cd "$T"          # arXiv simulation
  for i in 1 2 3; do pdflatex -interaction=nonstopmode "$N" >/dev/null 2>&1; done
  echo "--- $N: errors $(grep -cE '^!' "$N.log") | undefined $(grep -cE 'Citation .* undefined|Reference .* undefined' "$N.log") | overfull $(grep -c Overfull "$N.log") | $(grep -oE '[0-9]+ pages' "$N.log" | head -1)"
  rm -rf "$T"

  cd "$S/$N"
  COPYFILE_DISABLE=1 tar --no-xattrs -czf "$OUT/arxiv-$N.tar.gz" $FILES
  echo "    -> $OUT/arxiv-$N.tar.gz ($(du -h "$OUT/arxiv-$N.tar.gz" | cut -f1)): $(tar -tzf "$OUT/arxiv-$N.tar.gz" | tr '\n' ' ')"
done
