#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 h31_r0_audit.py --mode selftest
python3 h31_r0_audit.py --mode discover
python3 h31_r0_audit.py --mode auto
