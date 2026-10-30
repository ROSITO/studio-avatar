import os
import unittest
from unittest.mock import Mock,patch
import drama_gpu

class MetalConfigurationTest(unittest.TestCase):
    def test_option_avant_import_et_override_respecte(self):
        with patch('platform.system',return_value='Darwin'),patch('platform.mac_ver',return_value=('26.1',(),'')),patch.dict(os.environ,{},clear=True):
            drama_gpu.preparer_environnement();self.assertEqual(os.environ['MLX_METAL_FAST_SYNCH'],'1')
            os.environ['MLX_METAL_FAST_SYNCH']='0';drama_gpu.preparer_environnement()
            self.assertEqual(os.environ['MLX_METAL_FAST_SYNCH'],'0')
        for system,version in [('Linux',''),('Darwin','14.7')]:
            with patch('platform.system',return_value=system),patch('platform.mac_ver',return_value=(version,(),'')),patch.dict(os.environ,{},clear=True):
                drama_gpu.preparer_environnement();self.assertNotIn('MLX_METAL_FAST_SYNCH',os.environ)

    def test_residence_optionnelle_bornee_et_refusee_sous_pression(self):
        mx=Mock();mx.device_info.return_value={'max_recommended_working_set_size':28*1024**3}
        with patch.dict(os.environ,{'STUDIO_DRAMA_WIRED_MB':'512'}),patch('memoire.pression',return_value=0),patch('memoire.disponible',return_value=10*1024**3):
            self.assertEqual(drama_gpu.configurer(mx,4*1024**3),256*1024**2)
            with patch('memoire.pression',return_value=2):self.assertEqual(drama_gpu.configurer(mx,12*1024**3),0)
            with patch('memoire.disponible',return_value=4*1024**3):self.assertEqual(drama_gpu.configurer(mx,12*1024**3),0)
        for bad in ('-1','513','nan','1.2'):
            with patch.dict(os.environ,{'STUDIO_DRAMA_WIRED_MB':bad}),self.assertRaises(ValueError):drama_gpu.configurer(mx,12*1024**3)
        with patch.dict(os.environ,{'STUDIO_DRAMA_WIRED_MB':'0'}):self.assertEqual(drama_gpu.configurer(mx,12*1024**3),0)
