#!/usr/bin/env python3
"""H32-R59: read-only occupancy audit for PiPNN post-reservoir candidate ID dump.

Does NOT estimate actual peak build occupancy, OS RSS, or any ANN quality metric.
Input layout: exactly n*cap little-endian uint32 IDs; valid IDs are [0,n),
other IDs are padding. This assumption must match the exporter specification.
"""
import argparse, json, os, hashlib, sys
from pathlib import Path
from array import array


def audit(path: Path, n: int, cap: int, batch: int):
    if n <= 0 or cap <= 0 or batch <= 0 or n >= 2**32:
        raise ValueError('n, cap, batch must be positive and n < 2^32')
    size = path.stat().st_size
    expected = n * cap * 4
    if size != expected:
        raise ValueError(f'file byte length mismatch: got {size}, expected {expected}')
    hist = [0] * (cap+1)
    valid = 0
    invalid_values = {}
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        remaining = n
        rowid = 0
        while remaining:
            take = min(batch, remaining)
            raw = f.read(take * cap * 4)
            if len(raw) != take * cap * 4:
                raise ValueError('premature EOF')
            digest.update(raw)
            arr = array('I')
            if arr.itemsize != 4:
                raise RuntimeError('platform uint32 unsupported')
            arr.frombytes(raw)
            if sys.byteorder != 'little':
                arr.byteswap()
            for off in range(0, len(arr), cap):
                row = arr[off:off+cap]
                seen_padding = False
                seen_ids = set()
                k = 0
                for v in row:
                    if v == 0xffffffff:
                        seen_padding = True
                    elif v >= n:
                        raise ValueError(f'non-sentinel out-of-range ID {v} at row {rowid}')
                    else:
                        if seen_padding:
                            raise ValueError(f'non-padding ID after padding at row {rowid}')
                        if v == rowid:
                            raise ValueError(f'self-candidate at row {rowid}')
                        if v in seen_ids:
                            raise ValueError(f'duplicate candidate ID at row {rowid}')
                        seen_ids.add(v)
                        k += 1
                hist[k] += 1
                valid += k
                rowid += 1
            remaining -= take
        if f.read(1):
            raise ValueError('unexpected trailing bytes')
    def percentile(p):
        target = max(1, int((p/100*n) + .99999999))
        s = 0
        for i,h in enumerate(hist):
            s += h
            if s >= target:
                return i
        return cap
    # Raw candidate-slot memory only; excludes sentinel, offsets, locks, allocators.
    used_bytes = valid*8
    allocated_candidate_bytes = n*cap*8
    return {
      'gate':'H32-R59', 'input_file':str(path.resolve()),
      'sha256':digest.hexdigest(), 'n':n, 'capacity_per_vertex':cap,
      'candidate_file_bytes':size, 'valid_ids':valid,
      'mean_occupancy':valid/n, 'fraction_slots_used':valid/(n*cap),
      'rows_empty':hist[0], 'rows_full':hist[cap],
      'occupancy_p10':percentile(10), 'occupancy_p50':percentile(50),
      'occupancy_p90':percentile(90), 'occupancy_p99':percentile(99),
      'histogram':hist, 'padding_id_examples':invalid_values,
      'nominal_fixed_candidate_slots_bytes':allocated_candidate_bytes,
      'nominal_live_candidate_slots_bytes':used_bytes,
      'nominal_unused_candidate_slots_bytes':allocated_candidate_bytes-used_bytes,
      'interpretation': 'post-reservoir snapshot only; not peak RSS, occupancy over time, or builder speedup',
    }


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd',required=True)
    sub.add_parser('selftest')
    a=sub.add_parser('audit')
    a.add_argument('--pool',type=Path,required=True)
    a.add_argument('--n',type=int,default=1000000)
    a.add_argument('--capacity',type=int,default=160)
    a.add_argument('--batch-rows',type=int,default=1024)
    a.add_argument('--output',type=Path,required=True)
    a.add_argument('--expected-sha256',type=str,default=None)
    args=ap.parse_args()
    if args.cmd=='selftest':
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'p.bin'
            vals=array('I',[1,2,0xffffffff,2,0xffffffff,0xffffffff,0,0xffffffff,0xffffffff,0,1,2])
            if sys.byteorder!='little': vals.byteswap()
            path.write_bytes(vals.tobytes())
            r=audit(path,4,3,2)
            assert r['histogram']==[0,2,1,1] and r['valid_ids']==7, r
            assert r['occupancy_p50']==1 and r['occupancy_p90']==3
        print('R59_SELFTEST_PASS')
        return
    if args.output.exists():
        raise FileExistsError(f'Output already exists: {args.output}')
    result=audit(args.pool,args.n,args.capacity,args.batch_rows)
    if args.expected_sha256 and result['sha256'].lower() != args.expected_sha256.lower():
        raise ValueError('Pool SHA256 mismatch: refusing to report a different BUILD as R26a')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output,'x',encoding='utf-8') as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    print('R59_READONLY_POST_RESERVOIR_OCCUPANCY_PASS')
    print('R59_MEAN',result['mean_occupancy'],'P50',result['occupancy_p50'],'P90',result['occupancy_p90'],'P99',result['occupancy_p99'])
    print('R59_REPORT',args.output)

if __name__ == '__main__':
    main()
