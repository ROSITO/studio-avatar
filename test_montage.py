"""Integrated return joins must replace frames, retain speech and add no pause."""
import array
import json
import math
import subprocess
import unittest
from unittest.mock import patch
import montage, projets, studio, test_projets

class MontageIntegreTest(unittest.TestCase):
    def setUp(self):
        self.fixture=test_projets.ProjetsTest();self.fixture.setUp()
        self.p=self.fixture.creer();projets.lancer(self.p['id'],dict(action='automatique'));self.fixture.drain();self.p=projets.lire(self.p['id'])
    def tearDown(self):self.fixture.tearDown()
    def test_duree_et_voix_continue_pendant_retours(self):
        plan=montage.morceaux(studio,self.p)
        self.assertAlmostEqual(sum(m['duree'] for m in plan),3.75)
        elapsed=0;out=studio.ICI/'videos'/self.p['export']['fichier']
        for m in plan:
            if m['role']=='transition':
                self.assertIsNotNone(m['audio']);self.assertAlmostEqual(m['audio_debut'],.75)
                raw=subprocess.check_output(['ffmpeg','-v','error','-ss',str(elapsed+.05),'-i',str(out),'-t','0.2','-ac','1','-ar','44100','-f','f32le','-'])
                samples=array.array('f',raw);rms=math.sqrt(sum(x*x for x in samples)/len(samples))
                self.assertGreater(rms,.01,'The bridge must carry the previous block speech, not silence.')
            elapsed+=m['duree']
    def test_raccord_ancre_au_nouveau_point_de_coupe(self):
        tr=self.p['transitions'][0];r=montage.raccord(self.p,tr)
        self.assertEqual(r,dict(coupe=18,frames=12,duree=.5))
        with patch.object(studio,'lancer',wraps=studio.lancer) as run:
            projets.lancer(self.p['id'],dict(action='pont',element=tr['id']));self.fixture.drain()
        self.assertTrue(any('select=eq(n\\,17)' in c.args[1] for c in run.call_args_list))
        p=projets.lire(self.p['id']);self.assertTrue(projets.pont_pret(p,p['transitions'][0]))
        self.assertEqual(p['transitions'][0]['coupe_frame'],18)
    def test_anciens_raccords_et_exports_sont_perimes_sans_perdre_les_rushs(self):
        old=self.p;old.pop('montage_version');old['export'].pop('montage_version')
        for tr in old['transitions']:tr.pop('raccord_version')
        (projets.RACINE/(old['id']+'.json')).write_text(json.dumps(old))
        p=projets.lire(old['id']);self.assertEqual(p['revision'],old['revision']+1)
        self.assertEqual(p['montage_version'],2);self.assertTrue(all(projets.courant(b) for b in p['blocs']))
        self.assertTrue(all(not projets.pont_pret(p,tr) for tr in p['transitions']))
        self.assertEqual([b['clip'] for b in p['blocs']],[b['clip'] for b in old['blocs']])
        self.assertEqual(projets.lire(p['id'])['revision'],p['revision'])
        projets.sauver(p);self.assertEqual(projets.lire(p['id'])['revision'],p['revision'])
    def test_arrondi_cumule_et_retour_borne(self):
        p=dict(blocs=[dict(id=str(i),duree=d) for i,d in enumerate([2.32,2.12,2.32])])
        self.assertEqual(sum(montage.frames_blocs(p).values()),round(6.76*24))
        r=montage.raccord(p,dict(gauche='0',duree=20))
        self.assertEqual(r['coupe'],1);self.assertEqual(r['frames'],55)

if __name__=='__main__':unittest.main()
