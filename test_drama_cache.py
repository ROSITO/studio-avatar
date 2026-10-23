import importlib.util
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import drama_cache

class CleCacheTest(unittest.TestCase):
    def test_reference_transcription_et_poids_invalident_le_cache(self):
        with tempfile.TemporaryDirectory() as tmp,patch('importlib.metadata.version',return_value='test'):
            root=Path(tmp);model=root/'model';model.mkdir();(model/'model.safetensors').write_bytes(b'weights')
            ref=root/'ref.wav';ref.write_bytes(b'audio')
            d=dict(modele=str(model),reference=str(ref),transcription='Bonjour')
            initial=drama_cache.cle(d)
            cache=model/'.studio-avatar-cache';cache.mkdir();(cache/'x').write_bytes(b'cache')
            self.assertEqual(initial,drama_cache.cle(d))
            self.assertEqual(initial,drama_cache.cle(dict(d,texte='Une autre phrase.',seed=99)))
            self.assertNotEqual(initial,drama_cache.cle(dict(d,transcription='Salut')))
            ref.write_bytes(b'autre audio');self.assertNotEqual(initial,drama_cache.cle(d))
            ref.write_bytes(b'audio');(model/'model.safetensors').write_bytes(b'new weights')
            self.assertNotEqual(initial,drama_cache.cle(d))

@unittest.skipUnless(importlib.util.find_spec('mlx_audio'),'Optional MLX voice runtime')
class EtatCacheTest(unittest.TestCase):
    def test_etats_kv_et_lineaires_sans_perte(self):
        import mlx.core as mx
        from mlx_audio.lm.models.cache import KVCache,ArraysCache
        k=KVCache();k.update_and_fetch(mx.ones((1,2,3,4)),mx.full((1,2,3,4),2))
        a=ArraysCache(2);a[0]=mx.arange(12).reshape(1,3,4)
        voice=SimpleNamespace(prefix=([a,k],[k]),references=[('Bonjour',mx.arange(6).reshape(2,3))])
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'prefix.safetensors';drama_cache.sauver(mx,path,voice,3)
            prefix=drama_cache.charger(mx,path,voice,3,(2,1))
            self.assertEqual(prefix[0][1].offset,3);self.assertIsNone(prefix[0][0][1])
            for groupes in zip(voice.prefix,prefix):
                for ancien,nouveau in zip(*groupes):
                    for x,y in zip(ancien.state,nouveau.state):
                        if x is not None:self.assertTrue(mx.array_equal(x,y).item())
            autre=SimpleNamespace(references=[('Bonjour',mx.ones((2,3),dtype=mx.int32))])
            with self.assertRaisesRegex(ValueError,'Référence encodée différente'):
                drama_cache.charger(mx,path,autre,3,(2,1))
            self.assertEqual(list(Path(tmp).glob('*.tmp.safetensors')),[])

    def test_reprise_et_repli_si_fichier_abime(self):
        import mlx.core as mx
        from mlx_audio.lm.models.cache import KVCache
        import contextlib,io
        with tempfile.TemporaryDirectory() as tmp,patch('importlib.metadata.version',return_value='test'):
            root=Path(tmp);modeldir=root/'model';modeldir.mkdir();(modeldir/'model.safetensors').write_bytes(b'weights')
            ref=root/'reference.wav';ref.write_bytes(b'audio')
            requete=dict(modele=str(modeldir),reference=str(ref),transcription='Bonjour')
            builds=[]
            def construire():
                def start(frames,rows,voice):
                    if voice.prefix is None:
                        builds.append(True);k=KVCache();k.update_and_fetch(mx.ones((1,1,2,2)),mx.ones((1,1,2,2)));voice.prefix=([k],[k])
                    return voice.prefix
                return SimpleNamespace(_start_caches=start,backbone=SimpleNamespace(make_cache=lambda:[KVCache()]),tower=SimpleNamespace(make_cache=lambda:[KVCache()]))
            def executer():
                modele=construire();drama_cache.installer(mx,modele,requete)
                voice=SimpleNamespace(prefix=None,references=[('Bonjour',mx.arange(4).reshape(2,2))])
                return modele._start_caches(None,2,voice)
            with contextlib.redirect_stdout(io.StringIO()) as log:
                executer();executer()
                self.assertEqual(len(builds),1);self.assertIn('réutilisée',log.getvalue())
                next((modeldir/'.studio-avatar-cache').glob('*.safetensors')).write_bytes(b'cache casse')
                executer();self.assertEqual(len(builds),2);self.assertIn('ignoré',log.getvalue())
