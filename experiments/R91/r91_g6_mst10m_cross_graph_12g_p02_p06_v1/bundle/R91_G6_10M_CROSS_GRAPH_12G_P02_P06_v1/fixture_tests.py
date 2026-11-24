import tempfile
from pathlib import Path
from unittest.mock import patch
import r91_g6_10m_cross_graph_p02_p06_v1 as e

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
            reject(lambda:e.prior_chain('p03',{},'fixture'))
            e.pairfile('p02').parent.mkdir(parents=True);e.pairfile('p02').write_text('{}')
            e.prior_chain('p03',{},'fixture');assert seen==['p02','p02']
            (e.OUT/'pairs'/'p04').mkdir();reject(lambda:e.prior_chain('p03',{},'fixture'))
        s=[{'arm':a,'metrics':[{'beam':b,'recall_at10':.999,'qps':300,'avg_visited':500} for b in e.BEAMS]} for a in e.ARMS]
        f=e.pairfile('p02');f.unlink();e.atom(f,e.pair_summary('p02',s,'fixture'))
        with patch.object(e,'verify_slot',side_effect=lambda pid,a,*args:next(x for x in s if x['arm']==a)):
            e.verify_pair('p02',{},'fixture');f.write_text('{}');reject(lambda:e.verify_pair('p02',{},'fixture'))
print('OFFLINE_FIXTURE_PASS_PREDECESSOR_AND_TAMPER_NO_NATIVE_SEARCH')
