"""Verify rush preview continuity, cache invalidation and independent CPU rendering."""
import time
from pathlib import Path
import unittest
from unittest.mock import patch
import apercus
import projets
import studio
import test_projets

class ApercusTest(unittest.TestCase):
    def setUp(self):
        self.fixture=test_projets.ProjetsTest();self.fixture.setUp();apercus.installer(studio);apercus.ETATS.clear()
        self.p=projets.creer(dict(avatar='avatar.png',voix='test',texte='[curious] First. [excited] Second. [serious] Third.'))
        for b in self.p['blocs'][:2]:projets.lancer(self.p['id'],dict(action='clip',element=b['id']))
        self.fixture.drain();p=projets.lire(self.p['id']);projets.lancer(p['id'],dict(action='pont',element=p['transitions'][0]['id']));self.fixture.drain()
        self.p=projets.lire(p['id'])
    def tearDown(self):self.fixture.tearDown()
    def test_prefix_continu_et_coupes_identiques(self):
        plan=apercus.planifier(self.p)
        self.assertTrue(plan['partiel']);self.assertEqual(plan['nombre'],3);self.assertEqual(plan['total'],5)
        a,tr,b=plan['morceaux'];self.assertEqual(tr['debut_frame'],1);self.assertEqual(tr['fin_frame'],studio.images_ltx(round(tr['duree']*24)+2)-1)
        # Preview never uses the GPU launcher or MuseTalk.
        apercus.ETATS[self.p['id']]={}
        with patch.object(studio,'lancer',side_effect=AssertionError('GPU launcher must stay untouched')),patch.object(studio,'musetalk',side_effect=AssertionError('No lipsync')):
            apercus.construire(self.p['id'],plan,'.preview.mp4')
        self.assertEqual(apercus.etat(self.p['id'])['statut'],'pret')
        out=studio.ICI/'sequences'/'.preview.mp4'
        self.assertAlmostEqual(studio.duree(out),plan['duree'],delta=.12)
    def test_jonction_et_invalidation(self):
        tid=self.p['transitions'][0]['id'];plan=apercus.planifier(self.p,tid)
        self.assertFalse(plan['partiel']);self.assertEqual(len(plan['morceaux']),3)
        with self.assertRaises(ValueError):apercus.planifier(self.p,self.p['transitions'][1]['id'])
        projets.lancer(self.p['id'],dict(action='clip',element=self.p['blocs'][1]['id']))
        newer=projets.lire(self.p['id']);self.assertEqual(apercus.planifier(newer)['nombre'],1)
        with self.assertRaises(ValueError):apercus.planifier(newer,tid)
    def test_cache_sans_nouveau_montage(self):
        plan=apercus.planifier(self.p);name=f".apercu-{self.p['id']}-{plan['signature']}.mp4"
        (studio.ICI/'sequences'/name).write_bytes(b'cached')
        with patch.object(apercus.threading,'Thread',side_effect=AssertionError('Should reuse cache')):
            state=apercus.demander(self.p['id'])
        self.assertEqual(state['statut'],'pret');self.assertEqual(len(state['chapitres']),3)
        self.assertAlmostEqual(state['chapitres'][-1]['fin'],state['duree'])

if __name__=='__main__':unittest.main()
