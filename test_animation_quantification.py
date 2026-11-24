import importlib.util
import tempfile
from pathlib import Path
import unittest

@unittest.skipUnless(importlib.util.find_spec('torch'),'Optional isolated animation runtime')
class QuantificationTest(unittest.TestCase):
    def test_kernel_cache_disque_et_borne(self):
        import torch
        if not torch.backends.mps.is_available():self.skipTest('MPS required')
        from safetensors.torch import save_file
        from animation_quantification import CachePoidsQuantifies,LinearQuantifie
        from unittest.mock import patch
        memory_patch=patch('memoire.disponible',return_value=16*1024**3);memory_patch.start();self.addCleanup(memory_patch.stop)
        torch.manual_seed(40)
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp);source=tmp/'original.safetensors'
            w=torch.randn(128,256).bfloat16();b=torch.randn(128);save_file({'w':w,'b':b},str(source))
            index={k:dict(safetensors_file=str(source),weight_name=k,dtype='bfloat16' if k=='w' else 'float32') for k in ('w','b')}
            cache=CachePoidsQuantifies(index,tmp/'q4',4*1024**3);layer=LinearQuantifie(cache,'w','b',256,128)
            x=torch.randn(3,7,256,device='mps')
            with torch.no_grad():
                out=layer(x);again=layer(x)
                torch.testing.assert_close(out,again,rtol=0,atol=0)
                expected=torch.nn.functional.linear(x.bfloat16(),w.to('mps')).float()+b.to('mps')
                nrmse=((out-expected).square().mean()/expected.square().mean()).sqrt().item()
                self.assertLess(nrmse,.12)
                self.assertEqual(cache.hits,1);self.assertEqual(cache.convertis,1)
                from unittest.mock import patch
                batch=torch.randn(160,256,device='mps')
                with patch.dict('os.environ',{'STUDIO_WAN_Q4_KERNEL':'gemv'}):gemv=layer(batch)
                with patch.dict('os.environ',{'STUDIO_WAN_Q4_KERNEL':'gemm'}):gemm=layer(batch)
                difference=((gemv-gemm).square().mean()/gemv.square().mean()).sqrt().item()
                self.assertLess(difference,.02)
                self.assertLessEqual(cache.octets,cache.maximum)
                cache.clear()
                disk=CachePoidsQuantifies(index,tmp/'q4',2*1024**3)
                no_pin=LinearQuantifie(disk,'w','b',256,128);reloaded=no_pin(x)
                torch.testing.assert_close(out,reloaded,rtol=0,atol=0)
                self.assertEqual(disk.convertis,0);self.assertFalse(disk.pins)
                no_pin(x);self.assertEqual(disk.misses,2)

    def test_stockage_8_bits_preserve_la_precision(self):
        import torch
        if not torch.backends.mps.is_available():self.skipTest('MPS required')
        from safetensors.torch import save_file
        from animation_quantification import CachePoidsQuantifies,LinearQuantifie
        from unittest.mock import patch
        torch.manual_seed(55)
        with tempfile.TemporaryDirectory() as tmp,patch('memoire.disponible',return_value=16*1024**3):
            tmp=Path(tmp);p=tmp/'source.safetensors';w=torch.randn(128,256).bfloat16()
            save_file({'w':w},str(p));index={'w':dict(safetensors_file=str(p),weight_name='w',dtype='bfloat16')}
            cache=CachePoidsQuantifies(index,tmp/'q8',4*1024**3,bits=8);layer=LinearQuantifie(cache,'w',None,256,128)
            with torch.no_grad():
                x=torch.randn(160,256,device='mps');actual=layer(x)
                expected=torch.nn.functional.linear(x.bfloat16(),w.to('mps')).float()
                error=((actual-expected).square().mean()/expected.square().mean()).sqrt().item()
                self.assertLess(error,.015)
                cache.clear();again=layer(x);torch.testing.assert_close(actual,again,rtol=0,atol=0)
