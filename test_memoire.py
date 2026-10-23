import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch,Mock
import memoire

class BudgetMemoireTest(unittest.TestCase):
    def test_drama_admis_pour_essai_borne(self):
        mx=Mock()
        with patch.dict(os.environ,{'STUDIO_TTS_MAX_RAM_GB':'16'}),patch.object(memoire,'physique',return_value=36*memoire.GIB),patch.object(memoire,'disponible',return_value=24*memoire.GIB),patch.object(memoire,'pression',return_value=1):
            self.assertEqual(memoire.configurer_mlx(mx,'drama3-mlx'),16*memoire.GIB)
        mx.set_memory_limit.assert_called_once_with(16*memoire.GIB)
    def test_drama_reserve_quatre_gio_aux_applications(self):
        with patch.object(memoire,'budget',return_value=16*memoire.GIB),patch.object(memoire,'disponible',return_value=10*memoire.GIB),patch.object(memoire,'pression',return_value=1):
            self.assertEqual(memoire.verifier('drama3-mlx'),6*memoire.GIB)
    def test_superviseur_externe_tue_uniquement_enfant(self):
        import io
        child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(5)'])
        try:
            with patch.object(memoire,'empreinte',return_value=1025),patch.object(memoire,'pression',return_value=1):
                log=io.StringIO();self.assertEqual(memoire.attendre(child,1024,log),73)
            self.assertIsNotNone(child.poll());self.assertIn('Protection mémoire externe',log.getvalue())
        finally:
            if child.poll() is None:child.kill();child.wait()
    def test_alerte_moderee_conserve_reserve(self):
        with patch.object(memoire,'disponible',return_value=6*memoire.GIB):
            self.assertFalse(memoire.danger_systeme(2))
            self.assertTrue(memoire.danger_systeme(4))
        with patch.object(memoire,'disponible',return_value=3*memoire.GIB):
            self.assertTrue(memoire.danger_systeme(2))
    def test_limites_mlx_et_cache(self):
        mx=Mock()
        with patch.dict(os.environ,{'STUDIO_TTS_MAX_RAM_GB':'16'}),patch.object(memoire,'physique',return_value=36*memoire.GIB),patch.object(memoire,'disponible',return_value=20*memoire.GIB),patch.object(memoire,'pression',return_value=1):
            self.assertEqual(memoire.configurer_mlx(mx,'qwen3-tts-mlx'),16*memoire.GIB)
        mx.set_memory_limit.assert_called_once_with(16*memoire.GIB)
        mx.set_cache_limit.assert_called_once_with(256*1024**2)
    def test_marge_et_pression(self):
        with patch.object(memoire,'budget',return_value=16*memoire.GIB),patch.object(memoire,'pression',return_value=2):
            with self.assertRaisesRegex(ValueError,'pression mémoire'):memoire.verifier('omnivoice')
        with patch.object(memoire,'budget',return_value=16*memoire.GIB),patch.object(memoire,'pression',return_value=1),patch.object(memoire,'disponible',return_value=10*memoire.GIB):
            with self.assertRaisesRegex(ValueError,'Mémoire disponible insuffisante'):memoire.verifier('omnivoice')
    def test_budget_ne_depasse_pas_moitie_ram(self):
        with patch.dict(os.environ,{'STUDIO_TTS_MAX_RAM_GB':'100'}),patch.object(memoire,'physique',return_value=36*memoire.GIB):self.assertEqual(memoire.budget(),18*memoire.GIB)
    @unittest.skipIf(os.name=='nt','Watchdog Unix ps')
    def test_watchdog_interrompt_uniquement_son_processus(self):
        p=subprocess.run([sys.executable,'-c','import memoire,time; memoire.pression=lambda:4; memoire.surveiller(1024**4); time.sleep(5)'],cwd=Path(__file__).parent,capture_output=True,timeout=7)
        self.assertEqual(p.returncode,73);self.assertIn(b'Protection memoire',p.stderr)

if __name__=='__main__':unittest.main()
