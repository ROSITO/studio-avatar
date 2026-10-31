import os
import unittest
from unittest.mock import patch
import drama_experts
import memoire


class CacheAdaptatifTest(unittest.TestCase):
    def cache(self):
        return drama_experts.CacheExperts(memoire.GIB,12*memoire.GIB,4*memoire.GIB)

    def test_croissance_progressive_bornee(self):
        c=self.cache()
        with patch('memoire.pression',return_value=1),patch('memoire.disponible',return_value=20*memoire.GIB),patch('memoire.empreinte',return_value=6*memoire.GIB):
            for _ in range(20):
                old=c.plafond;c.verifie=0;self.assertTrue(c.verifier())
                self.assertLessEqual(c.plafond-old,256*1024**2)
            self.assertEqual(c.plafond,4*memoire.GIB)

    def test_reserve_processus_et_reprise_apres_reduction(self):
        c=self.cache()
        with patch('memoire.pression',return_value=1),patch('memoire.disponible',return_value=20*memoire.GIB),patch('memoire.empreinte',return_value=11*memoire.GIB):
            c.verifier();self.assertEqual(c.plafond,0)
        with patch('memoire.pression',return_value=1),patch('memoire.disponible',return_value=20*memoire.GIB),patch('memoire.empreinte',return_value=7*memoire.GIB):
            c.verifie=0;self.assertTrue(c.verifier());self.assertEqual(c.plafond,256*1024**2)

    def test_reserve_systeme_et_mesure_indisponible(self):
        for available,footprint in [(5*memoire.GIB,7*memoire.GIB),(20*memoire.GIB,OSError())]:
            c=self.cache()
            with patch('memoire.pression',return_value=1),patch('memoire.disponible',return_value=available),patch('memoire.empreinte',side_effect=footprint if isinstance(footprint,Exception) else None,return_value=footprint):
                c.verifier();self.assertEqual(c.plafond,0)

    def test_reduction_libere_les_lignes(self):
        from types import SimpleNamespace
        c=self.cache();c.put('row',{'weight':SimpleNamespace(nbytes=32)})
        c.redimensionner(0)
        self.assertEqual(c.octets,0);self.assertFalse(c.lru)

    def test_budget_standard_limite_la_croissance_a_deux_gio(self):
        with patch.dict(os.environ,{'STUDIO_DRAMA_ADAPTIVE_CACHE':'1'},clear=True):
            read=drama_experts.lecteur(12*memoire.GIB)
            self.assertEqual(read.cache.maximum,2*memoire.GIB);read.close()

    def test_configuration_fixe_prioritaire(self):
        try:
            import numpy
        except ImportError:self.skipTest('Optional numpy runtime')
        with patch.dict(os.environ,{'STUDIO_DRAMA_EXPERT_CACHE_MB':'1024'},clear=True):
            read=drama_experts.lecteur(12*memoire.GIB)
            self.assertEqual(read.cache.budget,0);read.close()


if __name__=='__main__':unittest.main()
