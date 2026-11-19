import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

@unittest.skipUnless(importlib.util.find_spec('torch'),'Optional animation runtime')
class PoidsTest(unittest.TestCase):
    def test_direct_exact_et_lectures_courtes(self):
        import torch,os
        from safetensors.torch import save_file
        from animation_poids import PoidsDirects
        for dtype in (torch.float32,torch.bfloat16,torch.float16):
            with tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp)/'weights.safetensors';data={'w':torch.randn(17,19).to(dtype),'scalar':torch.tensor(.5).to(dtype)}
                save_file(data,str(p));index={k:dict(safetensors_file=str(p),weight_name=k,dtype='float32') for k in data}
                read=PoidsDirects(index)
                try:
                    for k,v in data.items():torch.testing.assert_close(read[k],v.float(),rtol=0,atol=0)
                    original=os.preadv
                    with patch('os.preadv',side_effect=lambda fd,b,o:original(fd,[b[0][:11]],o)):
                        torch.testing.assert_close(read['w'],data['w'].float(),rtol=0,atol=0)
                    self.assertEqual(len(read.files),1)
                finally:read.close()
                self.assertFalse(read.files)

    def test_lineaire_mixte_et_temps_fp32(self):
        import torch
        from animation_poids import lineaires_mixtes
        module=torch.nn.Module();module.proj=torch.nn.Linear(32,16);module.time_projection=torch.nn.Sequential(torch.nn.Linear(32,16))
        original=module.proj.weight.detach().clone();bias=module.proj.bias.detach().clone()
        self.assertEqual(lineaires_mixtes(module),1)
        self.assertEqual(module.time_projection[0].weight.dtype,torch.float32)
        self.assertEqual(module.proj.weight.dtype,torch.bfloat16)
        x=torch.randn(4,32)
        expected=torch.nn.functional.linear(x.bfloat16(),original.bfloat16(),bias.bfloat16()).float()
        torch.testing.assert_close(module.proj(x),expected,rtol=0,atol=0)


class BudgetMpsTest(unittest.TestCase):
    def test_budget_mps_utilise_la_reference_metal(self):
        from unittest.mock import Mock
        from lancer_animation import configurer_budget_mps
        torch=Mock();torch.mps.recommended_max_memory.return_value=28*1024**3
        self.assertEqual(configurer_budget_mps(torch,12*1024**3),10*1024**3)
        torch.mps.set_per_process_memory_fraction.assert_called_once_with(10/28)
