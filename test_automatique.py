"""Automatic orchestration, resumability and optional fixed seeds, without GPU."""
import unittest
from unittest.mock import patch
import studio, projets, test_projets

class AutomatiqueTest(unittest.TestCase):
    def setUp(self):
        self.fixture=test_projets.ProjetsTest();self.fixture.setUp();self.p=self.fixture.creer()
    def tearDown(self):self.fixture.tearDown()
    def test_automatique_exporte_et_reutilise_les_rendus(self):
        projets.lancer(self.p['id'],dict(action='automatique'));self.fixture.drain()
        p=projets.lire(self.p['id']);self.assertTrue(p['export']);self.assertEqual(len(self.fixture.generations),5)
        t=studio.TACHES[-1];self.assertEqual(t['automatique']['faits'],6);self.assertEqual(len(t['seeds']),5)
        projets.lancer(p['id'],dict(action='automatique'));self.fixture.drain()
        self.assertEqual(len(self.fixture.generations),5);self.assertEqual(projets.lire(p['id'])['export'],p['export'])
    def test_echec_stoppe_et_reprise_garde_premier_clip(self):
        projets.lancer(self.p['id'],dict(action='automatique'));t=studio.TACHES[-1];t['etat']='en cours'
        original=studio.ltx;calls=0
        def fail_second(*args,**kwargs):
            nonlocal calls
            calls+=1
            if calls==2:raise RuntimeError('Synthetic failure')
            return original(*args,**kwargs)
        with patch.object(studio,'ltx',side_effect=fail_second):
            with self.assertRaises(RuntimeError):projets.executer(t)
        t['etat']='erreur';p=projets.lire(self.p['id']);first=p['blocs'][0]['clip']
        self.assertTrue(first);self.assertIsNone(p['export']);self.assertEqual(len(studio.TACHES),1)
        projets.lancer(p['id'],dict(action='automatique'));self.fixture.drain();p=projets.lire(p['id'])
        self.assertEqual(p['blocs'][0]['clip'],first);self.assertTrue(p['export'])
    def test_seed_manuelle_fixe_et_aleatoire_par_relance(self):
        b=self.p['blocs'][0];pid=self.p['id'];self.assertEqual(b['seed_mode'],'auto')
        projets.modifier(pid,dict(action='modifier',element=b['id'],seed_mode='manuel',seed=42))
        for _ in range(2):projets.lancer(pid,dict(action='clip',element=b['id']));self.fixture.drain()
        self.assertEqual([x[3] for x in self.fixture.generations],[42,42])
        projets.modifier(pid,dict(action='modifier',element=b['id'],seed_mode='auto'))
        with patch.object(projets,'seed_aleatoire',side_effect=[100,101]):
            for _ in range(2):projets.lancer(pid,dict(action='clip',element=b['id']));self.fixture.drain()
        self.assertEqual([x[3] for x in self.fixture.generations][-2:],[100,101])
    def test_reprise_garde_seed_et_annulation_stoppe(self):
        projets.lancer(self.p['id'],dict(action='automatique'));t=studio.TACHES[-1];t['etat']='en cours'
        with patch.object(studio,'ltx',side_effect=RuntimeError('Synthetic failure')),patch.object(projets,'seed_aleatoire',return_value=789):
            with self.assertRaises(RuntimeError):projets.executer(t)
        self.assertEqual(t['seeds'][self.p['blocs'][0]['id']],789)
        # Resuming this same saved orchestration must retain the chosen draw.
        with patch.object(projets,'seed_aleatoire',return_value=999):projets.executer(t)
        self.assertEqual(self.fixture.generations[0][3],789)
        t['annuler']=True
        with self.assertRaises(RuntimeError):projets.executer(t)

if __name__=='__main__':unittest.main()
