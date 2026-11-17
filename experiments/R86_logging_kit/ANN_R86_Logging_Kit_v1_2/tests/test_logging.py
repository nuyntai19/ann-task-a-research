"""Synthetic correctness tests, not PiPNN research measurements."""
import csv
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

ROOT=Path(__file__).resolve().parents[1]
PYTHON=sys.executable
CLI=str(ROOT/'scripts'/'r86_log.py')

class LoggerTest(unittest.TestCase):
    def call(self,*args,rc=0):
        p=subprocess.run([PYTHON,CLI,*map(str,args)],text=True,capture_output=True)
        self.assertEqual(p.returncode,rc,p.stdout+'\n'+p.stderr)
        return p

    def test_init_import_leaf_export(self):
        with TemporaryDirectory() as t:
            run=Path(t)/'TEST_A3_ON'
            self.call('init','--output',t,'--run-id','TEST_A3_ON','--arm-id','A3','--n','100','--dim','128','--N','2','--mode','instrumented','--slot-bytes','8')
            self.assertTrue((run/'logs'/'A_system.log').is_file())
            a=json.loads((run/'A_system.json').read_text())
            self.assertEqual(a['M_reservoir_model_B'],100*65*8)
            self.assertIsNone(a['T_build_s'])
            ev=Path(t)/'counter.jsonl'
            lines=[(1,3,'leaf_count',2),(1,3,'leaf_size_sum',4),(1,3,'W_L',10),(1,3,'W_pairs',3),
                   (1,0,'W_P',2000),(0,None,'prune_distance_calls',23)]
            ev.write_text(''.join(json.dumps({'pass_id':p,'depth':d,'metric_code':m,'observed':v})+'\n' for p,d,m,v in lines))
            self.call('import-counters','--run',run,'--events',ev)
            leaf=Path(t)/'leaf.jsonl'
            leaf.write_text('\n'.join(json.dumps({'pass_id':1,'depth':3,'size':x}) for x in (1,3))+'\n')
            self.call('import-leaf-sizes','--run',run,'--events',leaf)
            self.call('export-csv','--run',run)
            with (run/'sheet_csv'/'C_WORK.csv').open(encoding='utf-8-sig',newline='') as f:
                records=list(csv.DictReader(f))
            leaf_row=next(r for r in records if r['metric_code']=='W_L')
            self.assertEqual(float(leaf_row['per_n']),0.1)
            self.assertEqual(int(leaf_row['observed']),10)
            self.assertEqual(leaf_row['pass_id'],'1')
            self.assertNotIn('COUNTER_MISMATCH',(run/'logs'/'C_work.log').read_text())
            self.call('import-counters','--run',run,'--events',ev,rc=1)

    def test_timed_capture_and_summary(self):
        with TemporaryDirectory() as t:
            run=Path(t)/'TIMED'
            self.call('init','--output',t,'--run-id','TIMED','--arm-id','A1','--n','1000','--mode','timed')
            self.call('capture-build','--run',run,'--',PYTHON,'-c','print("TEST_ONLY")')
            a=json.loads((run/'A_system.json').read_text())
            self.assertIsNotNone(a['T_build_s'])
            self.assertIsNone(a['T_partition_s'])
            self.assertIn('TEST_ONLY',(run/'raw'/'stdout.log').read_text())
            self.call('summarize','--root',t)
            s=json.loads((Path(t)/'R86_summary.json').read_text())
            self.assertEqual(s['summary'][0]['T_build_n'],1)
            self.assertIsNone(s['summary'][0]['T_build_IQR_s'])
            self.assertEqual(s['summary'][0]['run_count'],1)

    def test_leaf_mismatch_fails(self):
        with TemporaryDirectory() as t:
            run=Path(t)/'MISMATCH'
            self.call('init','--output',t,'--run-id','MISMATCH','--arm-id','A4','--n','100')
            x=Path(t)/'events.jsonl'
            x.write_text(json.dumps({'pass_id':1,'depth':2,'metric_code':'W_L','observed':99})+'\n')
            self.call('import-counters','--run',run,'--events',x)
            y=Path(t)/'leaf.jsonl'
            y.write_text(json.dumps({'pass_id':1,'depth':2,'size':4})+'\n')
            self.call('import-leaf-sizes','--run',run,'--events',y,rc=2)
            self.call('validate','--run',run,rc=2)

if __name__=='__main__':unittest.main()
