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
        finally:
            QuantizedSwitchLinear.__call__=appel;mx.set_default_device(device);drama3.PREFILL_CHUNK=chunk

if __name__=='__main__':unittest.main()
