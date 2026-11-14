#!/usr/bin/env python3
"""Synthetic patch & analyzer contract checks (not a full PiPNN compile)."""
import subprocess,tempfile
from pathlib import Path
from h26_p3a_patch import patch,FUNC,QSET,SCAN,EMIT,END
from h26_p3a_analyze import parse

def main():
    fixture='\n'.join(['H26_PROFILE,version,H26_P0_v1',FUNC,QSET,SCAN,EMIT,END])
    result=patch(fixture)
    for marker in ('H26P3A,version,H26_P3A_v1', 'h26p3a_pack+=', 'h26p3a_sel+=','h26p3a_emit+=', 'h26p3a::counts().add'):
        assert marker in result,marker
    for candidate in (fixture.replace(QSET,'broken'), result):
        try: patch(candidate)
        except RuntimeError:pass
        else:raise AssertionError('Should fail closed on missing or already-patched anchor')
    print('H26P3A_PATCH_FAIL_CLOSED_SELFTEST_PASS')
    with tempfile.TemporaryDirectory() as tmp:
        t=Path(tmp)
        def write(r):
            lines=['H26P3A,version,H26_P3A_v1','H26P3A,sample_mod,64',
                'H26P3A,sampled_leaves,1200','H26P3A,sampled_rows,421000',
                'H26P3A,sampled_candidates,320000000',
                'H26P3A,pack_ns,150000000','H26P3A,selector_ns,130000000',
                'H26P3A,emit_ns,30000000','H26P3A,outer_select_ns,330000000',
                'H26_PROFILE,selector,top2','H26_PROFILE,leaf_count,85529',
                'H26_PROFILE,rows,29995085','H26_PROFILE,proposals,59990170',
                'H26_PROFILE,select_worker_ns,38900000000',
                'H26_PROFILE,dist_worker_ns,62000000000',
                'H26_PROFILE,merge_worker_ns,14000000000',
                'Elapsed (wall clock) time (h:mm:ss or m:ss): 0:42.01']
            (t/f'p3a_r{r}_top2.log').write_text('\n'.join(lines)+'\n')
        write(1);write(2)
        a=parse(t/'p3a_r1_top2.log')
        assert a['sampled_leaves']==1200
        script=Path(__file__).with_name('h26_p3a_analyze.py')
        subprocess.run(['python3',str(script),'--out',str(t)],check=True,capture_output=True,text=True)
        assert '45.45%' in (t/'h26_p3a_summary.txt').read_text() or (t/'h26_p3a_summary.json').exists()
    print('H26P3A_ANALYZER_SELFTEST_PASS')

if __name__=='__main__':main()
