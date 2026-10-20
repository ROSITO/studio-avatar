"""Création d'avatar (FLUX via mflux) : commande, références, variantes et détection des poids. Aucun GPU."""
import tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import modeles, studio

class PortraitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        for d in ('portraits', 'references', 'sources'): (self.root / d).mkdir()
        (self.root / 'references' / 'visage.png').write_bytes(b'x')
        self.cmds = []
        def lancer(t, cmd, env=None):
            self.cmds.append([str(c) for c in cmd])
            sortie = self.cmds[-1][self.cmds[-1].index('--output') + 1]
            for s in t['seeds']: Path(sortie.replace('.png', f'_seed_{s}.png' if len(t['seeds']) > 1 else '.png')).write_bytes(b'png')   # comme mflux
        self.patches = [patch.object(studio, 'ICI', self.root), patch.object(studio, 'sauver', lambda: None), patch.object(studio, 'lancer', lancer)]
        for p in self.patches: p.start()
    def tearDown(self):
        for p in self.patches: p.stop()
        self.tmp.cleanup()
    def tache(self, modele, **params):
        return dict(id='t1', params=params, modeles=dict(image=dict(id=modele, path='/poids', installe=True)))

    def test_flux2_texte_seul_puis_edition_avec_reference(self):
        t = self.tache('flux2-klein4b', prompt='a woman', nombre=3); studio.portrait(t)
        cmd = self.cmds[-1]
        self.assertTrue(cmd[0].endswith('mflux-generate-flux2')); self.assertIn('--quantize', cmd); self.assertNotIn('--image-paths', cmd)
        self.assertEqual(len(t['resultat']['images']), 3); self.assertIn('mouth closed', t['resultat']['consigne'])
        t = self.tache('flux2-klein4b', prompt='', refs=[dict(dossier='references', nom='visage.png', role='visage')]); studio.portrait(t)
        cmd = self.cmds[-1]
        self.assertTrue(cmd[0].endswith('mflux-generate-flux2-edit')); self.assertIn(str(self.root / 'references' / 'visage.png'), cmd)
        self.assertTrue(t['resultat']['consigne'].startswith('Reference image 1: copy the face'))
    def test_flux3_sans_recette_distillee_et_refs_controlees(self):
        studio.portrait(self.tache('flux3-klein8', prompt='a man', nombre=1))
        self.assertTrue(self.cmds[-1][0].endswith('mflux-generate-flux3')); self.assertNotIn('--quantize', self.cmds[-1])
        with self.assertRaises(ValueError): studio.portrait(self.tache('flux3-klein8', refs=[dict(dossier='videos', nom='visage.png')]))
    def test_modele_absent(self):
        t = self.tache('flux2-klein4b'); t['modeles']['image']['installe'] = False
        with self.assertRaises(RuntimeError): studio.portrait(t)
    def test_poids_deja_installes_detectes(self):
        ailleurs = self.root / 'ailleurs' / 'flux2' / 'klein-4b'
        s = SimpleNamespace(ICI=self.root, MODELES=self.root / 'weights', TACHES=[], VOICESTUDIO='', LTX='x', MODELES_IMAGE=self.root / 'ailleurs')
        m = modeles.Gestionnaire(s); entree = m.entry('flux2-klein4b')
        self.assertFalse(m.selection()['image']['installe'])
        for f in entree['required']: (ailleurs / f).parent.mkdir(parents=True, exist_ok=True); (ailleurs / f).write_bytes(b'x')
        self.assertEqual(m.selection()['image'], dict(id='flux2-klein4b', path=str(ailleurs), installe=True))

if __name__ == '__main__': unittest.main()
