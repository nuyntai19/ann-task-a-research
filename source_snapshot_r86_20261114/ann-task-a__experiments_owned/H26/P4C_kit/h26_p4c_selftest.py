#!/usr/bin/env python3
"""Synthetic format/parsing self-test. Never interpretable as performance evidence."""
import tempfile
import pathlib
import sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from h26_p4c_analyze import parse_perf, summarize, EXPECTED

STATS='''100000.0;msec;task-clock;100.00;100.00;;
200000000000;;cycles;100.00;100.00;;
150000000000;;instructions;100.00;100.00;;
9000000000;;cache-references;100.00;100.00;;
300000000;;cache-misses;100.00;100.00;;
20000000000;;branches;100.00;100.00;;
100000000;;branch-misses;100.00;100.00;;
'''
LOG='''H26_PROFILE,leaf_count,85529
H26_PROFILE,rows,29995085
H26_PROFILE,proposals,59990170
H26_PROFILE,dist_worker_ns,65000000000
H26_PROFILE,select_worker_ns,40000000000
H26_PROFILE,merge_worker_ns,14000000000
Parlay time: build leaf time: 31.1
Parlay time: buckets time: 9.1
Parlay time: Final prune time: 3.7
        User time (seconds): 160.0
        System time (seconds): 4.0
        Elapsed (wall clock) time (h:mm:ss or m:ss): 0:42.20
        Voluntary context switches: 7700
        Involuntary context switches: 640
'''
with tempfile.TemporaryDirectory() as wd:
    d=pathlib.Path(wd)
    for k in EXPECTED:
        (d/(k+'.log')).write_text(LOG)
        if k.endswith('_perf'):(d/(k+'.perf.csv')).write_text(STATS)
    x=summarize(d)
    assert x['runs']['r1_4t_perf']['perf']['ipc']==0.75
    assert 0.9<x['derived']['speedup_leaf_1_to_2_PMU_single_pilot']<1.1
    assert 'cache_mpki' in parse_perf(d/'r1_4t_perf.perf.csv')
    (d/'r1_4t_perf.perf.csv').write_text(STATS.replace('200000000000','<not counted>',1))
    try:
        parse_perf(d/'r1_4t_perf.perf.csv')
        raise AssertionError('not counted PMU failed closed incorrectly')
    except ValueError: pass
    print('H26P4C_SYNTHETIC_ANALYZER_PASS')
