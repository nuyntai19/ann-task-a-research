#!/usr/bin/env python3
"""Audit completed experimental runs and verify the old workflow is unchanged."""
from collections import defaultdict
import json
from run import HERE, check_protected, read_queries, sha, save


def main():
    validated=[]
    for path in sorted((HERE/'runs').glob('*/summary.json')):
        m=json.loads(path.read_text())
        if m.get('status')!='PASS':continue
        t=m['telemetry'];by_depth=defaultdict(lambda:[0,0,0,0])
        for line in (path.parent/'buckets.jsonl').read_text().splitlines():
            b=json.loads(line);hist={int(f):n for f,n in b['fanout_histogram'].items()}
            assert sum(hist.values())==b['points']
            assert all(1<=f<=b['max_fanout'] for f in hist)
            assert sum(f*n for f,n in hist.items())==b['actual_assignments']<=b['nominal_assignments']
            assert b['points']*b['max_fanout']==b['nominal_assignments']
            if m['mode']=='fixed' or b['depth']<m['min_depth']:
                assert b['actual_assignments']==b['nominal_assignments']
            a=by_depth[b['depth']];a[0]+=b['points'];a[1]+=b['actual_assignments'];a[2]+=b['nominal_assignments'];a[3]+=1
        for d in t['by_depth']:
            assert by_depth[d['depth']]==[d['points'],d['actual_assignments'],d['nominal_assignments'],d['buckets']]
        assert sum(d['actual_assignments'] for d in t['by_depth'])==t['actual_assignments']
        assert t['leaf_points']<=t['directed_proposals']<=2*t['leaf_points']
        assert 0<m['reachable_from_start0']<=m['rows']
        assert sha(path.parent/'index.graph')==m['graph']['sha256']
        arrays=read_queries(path.parent/'query_metrics.csv',m['beams'],m['queries'])
        for row in m['search']:
            assert abs(arrays[row['beam']][:,1].mean()-row['recall_at_10'])<1e-6
        validated.append({'run':path.parent.name,'mode':m['mode'],'rows':m['rows'],'queries':m['queries']})
    result={'status':'PASS','protected_original_files':check_protected(),'runs_validated':len(validated),
            'checks':['per-bucket counts and histograms','no zero or out-of-cap fanout','root preserved at min_depth1',
                      'summary matches bucket trace','actual proposal bounds','graph SHA256',
                      'complete per-query metrics and aggregate Recall parity'], 'runs':validated}
    save(HERE/'validation.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='runs'},indent=2))


if __name__=='__main__':main()
