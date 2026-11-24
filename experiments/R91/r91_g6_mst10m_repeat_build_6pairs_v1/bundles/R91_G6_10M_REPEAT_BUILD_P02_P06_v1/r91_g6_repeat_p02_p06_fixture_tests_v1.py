#!/usr/bin/env python3
"""Offline-only fixtures for source-receipt pairing, audit readback and aggregate."""
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import copy
import json
import hashlib
import importlib.util
import math

spec=importlib.util.spec_from_file_location('_fixture_p02_p06',Path(__file__).with_name('r91_g6_10m_repeat_build_p02_p06_v1.py'))
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def receipt(pid,arm):
 cap=int(arm[1:]);pnum=int(pid[1:]);wall=372+pnum*.04 if arm=='C512' else 358+pnum*.04
 return {'pair_id':pid,'arm':arm,'cap':cap,'native_time':{'wall_s':wall,'max_rss_kib':21_000_000 if arm=='C512' else 20_900_000,'major_faults':0},
  'resource':{'cg_peak_bytes':22_000_000_000 if arm=='C512' else 21_800_000_000,'swap_after':0,
              'events_delta':{'max':0,'oom':0,'oom_kill':0}},
  'graph':{'sha256':('a' if arm=='C512' else 'b')*64,'arcs':540_000_000+cap},
  'stage1_baseline_match':'STAGE1_COUNTERS_MATCH_V13_REFERENCE',
  'parsed':{'total_wp':156998418988 if arm=='C512' else 132495866066,
    'depth2_wp':52146043480 if arm=='C512' else 24296938546,
    'fallback_maxdepth_points':3325197 if arm=='C512' else 9983846,
    'fallback_shrink_points':1233469 if arm=='C512' else 239002,
    'passes':[{'depth':{'2':{'W_P':52598418988 if arm=='C512' else 28095866066}},'cap':{'leaf_count':1}}],
    'stage_times':{'buckets_total_s':147.14 if arm=='C512' else 128.49,
                   'leaf_total_s':156.14 if arm=='C512' else 161.60,
                   'final_prune_total_s':63.79 if arm=='C512' else 63.97}}}

class C:
 PINS={'g6_elf':'53be9510ead14aff25ec5adffc07d959c78d575f7ffcc9306435360ce9342690'}
 def setup(self,c,check):pass

with TemporaryDirectory() as td:
 root=Path(td);(root/'pairs').mkdir()
 (root/'pre.json').write_text('{}')
 stubseed={'source_sha256':'f'*64,'seed_555_markers':[530],'hash64_seed_markers':[456]}
 def fakecheck(_m,_c,pid,arm,full_graph=False):return receipt(pid,arm)
 def dummy_p01(_m,_c,full=False):
  x=receipt('p01','C512');y=receipt('p01','C64')
  return {'C512':m.summarize(x),'C64':m.summarize(y),'C64_minus_C512':{'wall_s':{'absolute':-14.0}}}
 def fake_digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
 with patch.object(m,'ROOT',root),patch.object(m,'PRE',root/'pre.json'),patch.object(m,'check_extension_preflight',lambda a,b:None),patch.object(m,'check_source',lambda x:stubseed),patch.object(m,'check_receipt',fakecheck),patch.object(m,'check_p01',dummy_p01):
  for pid in m.PAIRS:
   path=root/'pairs'/pid/'arms'
   for arm in ('C512','C64'):
    slot=path/arm;slot.mkdir(parents=True)
    (slot/'receipt.json').write_text('{}')
   result=m.audit_pair(None,C(),pid,verify_only=False,full_graph=False)
   assert result['order']==list(m.pair_order(pid))
   assert result['C64_minus_C512']['wall_s']['absolute']==-14
   result_again=m.audit_pair(None,C(),pid,verify_only=True,full_graph=False)
   assert result_again==result
  # mutation of immutable audit should be detected by read-only verification
  p=root/'pairs/p02/pair_audit.json';old=p.read_bytes();p.write_text(old.decode().replace('"PAIRED_BUILD_FULL_AUDIT_PASS"','"CORRUPTED"'))
  try:
   m.audit_pair(None,C(),'p02',verify_only=True,full_graph=False)
   raise AssertionError('tampering was not caught')
  except RuntimeError as e:assert 'PAIRED_AUDIT_READBACK_DRIFT' in str(e)
  p.write_bytes(old)
  m.collect_all(SimpleNamespace(setup=lambda *args:None),C(),verify_only=False)
  agg=m.readj(root/'repeat_6pair_summary.json')
  assert agg['status']=='SIX_PAIRED_FIXED_SEED_BUILDS_AUDIT_PASS_NO_SEARCH'
  assert agg['stats']['n_pairs']==6 and agg['stats']['C64_faster_pairs']==6
  assert agg['stats']['sign_test_one_sided_if_all_six_faster']==1/64
  assert agg['stats']['median_C512_minus_C64_s']==14
  m.collect_all(SimpleNamespace(setup=lambda *args:None),C(),verify_only=True)
  x=root/'repeat_6pair_summary.json';obj=m.readj(x);obj['stats']['n_pairs']=7;x.write_text(json.dumps(obj))
  try:
   m.collect_all(SimpleNamespace(setup=lambda *args:None),C(),verify_only=True)
   raise AssertionError('aggregate mutation was not caught')
  except RuntimeError as e:assert 'SIX_PAIR_SUMMARY_READBACK_DRIFT' in str(e)
print('R91_G6_REPEAT_P02_P06_V1_OFFLINE_SIX_PAIR_AUDIT_AND_TAMPER_FIXTURE_PASS')
