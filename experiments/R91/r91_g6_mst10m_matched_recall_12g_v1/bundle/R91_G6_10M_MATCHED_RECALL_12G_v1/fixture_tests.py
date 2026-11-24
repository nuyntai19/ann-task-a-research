import tempfile
from pathlib import Path
from unittest.mock import patch
import r91_g6_matched_recall_12g_v1 as e

def reject(fn):
    try:fn()
    except RuntimeError:return
    raise AssertionError('expected rejection')
with tempfile.TemporaryDirectory() as tmp:
    with patch.object(e,'OUT',Path(tmp)):
        seen=[]
        def fake_verify(pid,pp,pre,rehash=False):
            seen.append(pid)
            if not e.pairfile(pid).exists():raise RuntimeError('missing prior')
        with patch.object(e,'verify_pair',fake_verify):
            reject(lambda:e.prior_chain('p02',{},'fixture'))
            e.pairfile('p01').parent.mkdir(parents=True);e.pairfile('p01').write_text('{}')
            e.prior_chain('p02',{},'fixture');assert seen==['p01','p01']
            (e.OUT/'pairs'/'p03').mkdir();reject(lambda:e.prior_chain('p02',{},'fixture'))
        slots=[{'arm':a,'metrics':[{'beam':b,'recall_at10':r,'qps':q*(1 if a=='C512' else 1.01),'avg_visited':500} for b,r,q in zip(e.BEAMS,[.989,.991,.9979,.9981,.9982],[900,800,340,330,320])]} for a in e.ARMS]
        f=e.pairfile('p01');f.unlink()
        original=e.load
        old={'pairs':{'p01':{'slots':slots}}}
        with patch.object(e,'load',side_effect=lambda p:old if p==e.old.OUT/'cross_graph_12g_summary.json' else original(p)):
            e.atom(f,e.pair_summary('p01',slots,'fixture'))
            with patch.object(e,'verify_slot',side_effect=lambda pid,a,*args:next(x for x in slots if x['arm']==a)):
                z=e.verify_pair('p01',{},'fixture');assert all(abs(r['ratio_C64_over_C512']-1.01)<1e-12 for r in z['comparisons'])
                f.write_text('{}');reject(lambda:e.verify_pair('p01',{},'fixture'))
print('OFFLINE_FIXTURE_PASS_PREDECESSOR_TAMPER_INTERPOLATION_NO_NATIVE_SEARCH')
