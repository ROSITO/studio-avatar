"""Optional numerical checks: run with the installed MLX voice interpreter."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

@unittest.skipUnless(importlib.util.find_spec('mlx_audio'), 'Optional MLX voice runtime')
class ExpertsDisqueTest(unittest.TestCase):
    def test_routage_fp32_et_bfloat16(self):
        import mlx.core as mx
        import mlx.nn as nn
        from mlx.utils import tree_flatten
        from mlx_audio.lm.models.switch_layers import QuantizedSwitchLinear
        from mlx_audio.tts.models.fish_drama3 import drama3
        import drama_memoire
        if not mx.metal.is_available():self.skipTest('Metal required')
        appel=QuantizedSwitchLinear.__call__;device=mx.default_device();chunk=drama3.PREFILL_CHUNK
        try:
            for dtype,tries in ((mx.float32,False),(mx.bfloat16,False),(mx.float32,True),(mx.bfloat16,True)):
                with self.subTest(dtype=str(dtype),sorted=tries),tempfile.TemporaryDirectory() as dossier:
                    QuantizedSwitchLinear.__call__=appel;mx.set_default_device(mx.cpu)
                    modele=nn.Module();modele.backbone=nn.Module();modele.backbone.switch_mlp=nn.Module()
                    proj=QuantizedSwitchLinear(128,64,8,bias=False)
                    modele.backbone.switch_mlp.proj=proj
                    proj.scales=proj.scales.astype(dtype);proj.biases=proj.biases.astype(dtype)
                    x=mx.random.normal((2,1,1,128)).astype(dtype)
                    indices=mx.array([[0,1,1],[3,3,7]] if tries else [[1,3,1],[7,3,0]])
                    with mx.stream(mx.gpu):
                        attendu=proj(x,indices,sorted_indices=tries);mx.eval(attendu)
                    mx.save_safetensors(str(Path(dossier)/'model.safetensors'),dict(tree_flatten(modele.parameters())))
                    drama_memoire.activer(mx,modele,dossier)
                    obtenu=proj(x,indices,sorted_indices=tries)
                    self.assertTrue(mx.allclose(obtenu,attendu,atol=.02,rtol=.02).item())
                    import drama_experts
                    from unittest.mock import patch
                    with patch.dict('os.environ',{'STUDIO_DRAMA_EXPERT_CACHE_MB':'1','STUDIO_DRAMA_DIRECT_READ':'1'}):
                        reader=drama_experts.lecteur(12*1024**3)
                    with patch.object(reader.cache,'verifier',return_value=True):
                        drama_memoire.activer(mx,modele,dossier,lecteur=reader)
                        cached=proj(x,indices,sorted_indices=tries)
                        self.assertTrue(mx.array_equal(cached,obtenu).item())
                        read_bytes=reader.stats['octets_lus']
                        again=proj(x,indices,sorted_indices=tries)
                        self.assertTrue(mx.array_equal(again,cached).item())
                        self.assertEqual(reader.stats['octets_lus'],read_bytes)

        finally:
            QuantizedSwitchLinear.__call__=appel;mx.set_default_device(device);drama3.PREFILL_CHUNK=chunk

    def test_flux_audio_concatene_sans_silence_et_sans_lecteur(self):
        from types import SimpleNamespace
        from unittest.mock import Mock,patch
        import numpy as np
        from lancer_voix import generer_flux
        modele=SimpleNamespace(sample_rate=10,generate=Mock(return_value=iter([
            SimpleNamespace(audio=np.array([.1,.2],dtype=np.float32)),
            SimpleNamespace(audio=np.array([.3],dtype=np.float32))])))
        d=dict(texte='a'*200,reference='ref.wav',transcription='Bonjour')
        with tempfile.TemporaryDirectory() as dossier,patch('mlx_audio.audio_io.write') as ecrire:
            sortie=Path(dossier)/'sortie.wav'
            generer_flux(modele,d,sortie)
            import audio_partiel,struct
            sauvegarde=audio_partiel.chemin(sortie).read_bytes()
            self.assertEqual(sauvegarde[56:],np.array([.1,.2,.3],dtype='<f4').tobytes())
        self.assertTrue(modele.generate.call_args.kwargs['stream'])
        np.testing.assert_array_equal(ecrire.call_args.args[1],np.array([.1,.2,.3],dtype=np.float32))

if __name__=='__main__':unittest.main()
