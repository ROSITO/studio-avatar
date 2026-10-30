import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


@unittest.skipUnless(importlib.util.find_spec('mlx_audio'),'Optional MLX voice runtime')
class CacheVitesseTest(unittest.TestCase):
    def test_lecture_cachee_identique_et_bornee(self):
        import numpy as np
        import drama_experts
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'weights.bin';data=np.arange(16*32,dtype=np.uint32).reshape(16,32);p.write_bytes(data.tobytes())
            banks={'weight':((p,'uint32',0,data.shape),None)}
            with patch.dict('os.environ',{'STUDIO_DRAMA_EXPERT_CACHE_MB':'1'}):read=drama_experts.lecteur(12*1024**3)
            with patch.object(read.cache,'verifier',return_value=True):
                a=read(banks,np.array([1,3,8]),'module');before=read.stats['octets_lus']
                b=read(banks,np.array([1,3,8]),'module')
                np.testing.assert_array_equal(a['weight'],data[[1,3,8]])
                np.testing.assert_array_equal(a['weight'],b['weight']);self.assertEqual(read.stats['octets_lus'],before)
                read(banks,np.array([1,5,8]),'module')
                self.assertEqual(read.stats['octets_lus']-before,data[5].nbytes)
                self.assertLessEqual(read.cache.octets,read.cache.plafond)
            with patch('memoire.pression',return_value=2),patch('memoire.disponible',return_value=3*1024**3):
                read.cache.verifie=0;self.assertFalse(read.cache.verifier());self.assertEqual(read.cache.octets,0)

    def test_prefixe_causal_identique_et_moins_de_calcul(self):
        import mlx.core as mx
        from mlx_audio.lm.models.cache import ArraysCache,KVCache
        from mlx_audio.tts.models.fish_drama3 import drama3
        import drama_contexte
        class Backbone:
            def __call__(self,unused,cache,input_embeddings):
                previous=cache[0][0] if cache[0][0] is not None else mx.zeros((1,1,2))
                out=mx.cumsum(input_embeddings,axis=1)+previous
                cache[0][0]=out[:,-1:]
                cache[1].update_and_fetch(input_embeddings[:,None],input_embeddings[:,None])
                return out
        class Tower:
            def prefill(self,hidden,current,following,cache):
                old=cache[0][0] if cache[0][0] is not None else mx.array(0)
                cache[0][0]=old+following.sum()
                cache[1].update_and_fetch(following[:,None],following[:,None])
        def model():
            m=SimpleNamespace(backbone=SimpleNamespace(model=Backbone()),tower=Tower(),calls=[])
            def build(refs,history,text):
                rows=[mx.full((3,2),refs)]
                for turn,codes in history:rows.extend([mx.full((4,2),len(turn)),codes.T,mx.ones((4,2))])
                rows.append(mx.full((10,2),len(text)))
                return mx.concatenate(rows),3
            def prefill(frames,caches,start,stop):
                m.calls.append((start,stop));return drama3.Model._prefill(m,frames,caches,start,stop)
            m._embed=lambda f:f.astype(mx.float32);m.build_frames=build;m._prefill=prefill
            return m
        a,b=model(),model();drama_contexte.installer(mx,b)
        def run(m,history,text='target',refs=1):
            frames,system=m.build_frames(refs,history,text);caches=([ArraysCache(1),KVCache()],[ArraysCache(1),KVCache()])
            # Identical fresh system preparation, excluded from the cached history.
            drama3.Model._prefill(m,frames,caches,0,system)
            hidden=m._prefill(frames,caches,system,frames.shape[0]);mx.eval(hidden)
            return hidden,caches
        first=('pinned',mx.arange(2*340).reshape(2,340))
        h=[first]
        for history in (h,h+[('latest',mx.ones((2,70),dtype=mx.int32))]):
            ha,ca=run(a,history);hb,cb=run(b,history)
            self.assertTrue(mx.array_equal(ha,hb).item())
            for ga,gb in zip(ca,cb):
                for xa,xb in zip(ga,gb):
                    self.assertTrue(mx.array_equal(xa.state[0],xb.state[0]).item())
                    if isinstance(xa,KVCache):self.assertEqual(xa.offset,xb.offset)
        self.assertGreater(b._studio_contexte_stats['reutilisees'],0)
        self.assertLess(sum(z-x for x,z in b.calls),sum(z-x for x,z in a.calls))
        old=b._studio_contexte_stats['reutilisees']
        run(b,h,refs=9);self.assertEqual(old,b._studio_contexte_stats['reutilisees'])


if __name__=='__main__':unittest.main()
