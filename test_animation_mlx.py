import importlib.util,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

@unittest.skipUnless(importlib.util.find_spec('mlx') and importlib.util.find_spec('torch'),'Optional MLX animation runtime')
class PontMlxTest(unittest.TestCase):
    def test_matrice_mlx_et_format_aten_coherents(self):
        import torch
        if not torch.backends.mps.is_available():self.skipTest('MPS required')
        from safetensors.torch import save_file
        from animation_quantification import CachePoidsQuantifies,LinearQuantifie
        from animation_mlx import CacheMLX,LinearMLX
        torch.manual_seed(133)
        with tempfile.TemporaryDirectory() as tmp,patch('memoire.disponible',return_value=24*1024**3):
            tmp=Path(tmp);p=tmp/'source.safetensors'
            w=torch.randn(128,256).bfloat16();b=torch.randn(128);save_file({'w':w,'b':b},str(p))
            index={k:dict(safetensors_file=str(p),weight_name=k,dtype='bfloat16' if k=='w' else 'float32') for k in ('w','b')}
            native=LinearQuantifie(CachePoidsQuantifies(index,tmp/'cache',4*1024**3),'w','b',256,128)
            bridge=LinearMLX(CacheMLX(index,tmp/'cache',16*1024**3),'w','b',256,128)
            with torch.no_grad():
                x=torch.randn(1,160,256,device='mps')
                expected=native(x);actual=bridge(x)
                error=((actual-expected).square().mean()/expected.square().mean()).sqrt().item()
                self.assertLess(error,.02)
                torch.testing.assert_close(bridge(x),actual,rtol=0,atol=0)
                self.assertEqual(bridge.cache.hits,1);self.assertEqual(bridge.cache.misses,1)
                self.assertLessEqual(bridge.cache.octets,bridge.cache.maximum)
                bridge.cache.clear();self.assertFalse(bridge.cache.pins)

    def test_transformer_et_caches_de_reference(self):
        import torch
        if not torch.backends.mps.is_available():self.skipTest('MPS required')
        from diffusers import WanAnimate2Transformer3DModel
        from lancer_animation import charger_disque
        torch.manual_seed(6)
        model=WanAnimate2Transformer3DModel(dim=64,ffn_dim=128,freq_dim=8,text_dim=32,text_len=8,num_heads=4,num_layers=1)
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp);model.save_pretrained(tmp/'model');del model
            model=charger_disque(WanAnimate2Transformer3DModel,tmp/'model',tmp/'offload','mps',mixte=True,backend='mlx',plafond=16*1024**3)
            k,v={},{}
            with torch.no_grad():
                model([torch.randn(16,2,4,4,device='mps')],grid_sizes=torch.tensor([[2,2,2]]),k_cache=k,v_cache=v,
                    clip_fea_ref=torch.randn(1,257,1280,device='mps'),y_ref=[torch.randn(20,2,4,4,device='mps')],
                    context_ref=[torch.randn(8,32,device='mps')],seq_len_ref=8,t=torch.ones(1,device='mps'),method='forward_ref')
                self.assertEqual(k[0].dtype,torch.bfloat16)
                out=model([torch.randn(16,3,4,4,device='mps')],k_cache=k,v_cache=v,clip_fea=torch.randn(1,257,1280,device='mps'),
                    y=[torch.randn(20,3,4,4,device='mps')],context=[torch.randn(8,32,device='mps')],seq_len=12,t=torch.ones(1,device='mps'),
                    grid_sizes_ref=torch.tensor([[2,2,2]]),origin_len=5,origin_area=[32,32],method='forward_gen')
            self.assertEqual(tuple(out[0].shape),(16,3,4,4));self.assertTrue(torch.isfinite(out[0]).all().item())
            self.assertGreater(model._studio_poids_quantifies.hits,0)
            model._studio_poids_quantifies.clear()
