#!/usr/bin/env python3
import importlib.util
import json
import tempfile
from pathlib import Path
import struct
import sys
import unittest

PATH=Path(__file__).resolve().parents[1]/'r86_g1_off_equivalence.py'
spec=importlib.util.spec_from_file_location('r86_g1',PATH)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class R86G1ProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r85=json.loads((PATH.parent/'pins/r85_manifest.json').read_text())['identity']

    def test_arms_and_exact_command_replacement(self):
        # Uploaded pinned manifest uses /home/tai; local CI may use another $HOME.
        m.BASE=Path('/home/tai/ann-task-a/data/bigann1m_prefix.fbin')
        for a,cfg in m.ARMS.items():
            p=Path('/G1/TEST')/(a+'.graph.tmp')
            cmd=m.make_build_cmd(self.r85,a,p)
            self.assertEqual(cmd[:6],['taskset','-c','0,2,4,6','/usr/bin/time','-f','R86_G1_TIME wall_s=%e peak_rss_kib=%M'])
            self.assertEqual(cmd.count(str(p)),1)
            self.assertIn(str(m.BASE),cmd)
            self.assertEqual(cmd[cmd.index('-table_size')+1],str(cfg['table']))
            self.assertEqual(cmd[cmd.index('-cluster_size')+1],str(cfg['cluster']))
            self.assertEqual(cmd[cmd.index('-num_clusters')+1],'2')
            self.assertEqual(cmd[cmd.index('-fanout_scheme')+1],'10,3,1')
            self.assertIn(str(m.BUILD_ROOT/cfg['r86_arm']/'algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'),cmd)
            self.assertNotIn('/R85_SCALE1_DRY_RUN_GRAPH.graph',cmd)

    def test_partition_log_matches_all_historical_per_arm(self):
        base=PATH.parent/'pins'
        if not base.is_dir():self.skipTest('historical log not present')
        for arm,filename in [('stock_c160_k1024_n2','t4_r1_STOCK.build.log'),
                             ('h17_c64_k512_n2','t4_r1_C64_K512_N2.build.log')]:
            result,err=m.partition_extract((base/filename).read_text(),m.ARMS[arm])
            self.assertEqual(err,[])
            self.assertEqual(result['buckets'],m.ARMS[arm]['buckets'])

    def test_partition_detects_expected_deviation(self):
        cfg=m.ARMS['stock_c160_k1024_n2']
        log='Total buckets: 85027\nTotal buckets: 86507\n# of comparisons during clustering: 4728316379\n# of comparisons during clustering: 9478487005\nAverage table size: 55\nR70_RESERVOIR_VARIANT=STOCK_FLAT_C160\nR71_SELECTION_VARIANT=STOCK_HIGHWAY\nData: detected 1000000 points with dimension 128'
        _,e=m.partition_extract(log,cfg)
        self.assertEqual(e,['BUCKETS_MISMATCH'])

    def test_graph_validator_accepts_one_arc_million_graph(self):
        # 1m nodes and one legal arc; tests streaming graph parser.
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'x.graph.tmp'
            with p.open('wb') as f:
                f.write(struct.pack('<II',1000000,64))
                f.write(struct.pack('<I',1));f.write(b'\0'*3999996)
                f.write(struct.pack('<I',1))
            s=m.graph_audit(p)
            self.assertEqual(s['arcs'],1)
            self.assertEqual(s['graph_bytes'],4000012)

    def test_graph_validator_rejects_selfloop(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'x.graph.tmp'
            with p.open('wb') as f:
                f.write(struct.pack('<II',1000000,64))
                f.write(struct.pack('<I',1));f.write(b'\0'*3999996)
                f.write(struct.pack('<I',0))
            with self.assertRaisesRegex(RuntimeError,'GRAPH_INVALID_NEIGHBORS_NODE_0'):
                m.graph_audit(p)

if __name__=='__main__': unittest.main(verbosity=2)
