import json
from pathlib import Path
import tempfile
import types
import unittest
from conversion import Atelier

class ConversionTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name); (root/'voix').mkdir()
        self.a=Atelier(types.SimpleNamespace(ICI=root))
    def test_sans_configuration(self):
        self.assertEqual(self.a.etat(), {'modeles':[]})
        with self.assertRaises(ValueError): self.a.demander({'modele':'absent'})
    def test_disque_absent(self):
        self.a.configuration.write_text(json.dumps({'runtime':'/absent','modeles':[{'id':'test','nom':'Test','poids':'/absent/a','index':'/absent/b'}]}))
        self.assertFalse(self.a.etat()['modeles'][0]['disponible'])
    def test_refuse_traversee_et_hauteur(self):
        self.a.config=lambda: {'runtime':'/runtime','modeles':[{'id':'test','nom':'Test'}]}
        self.a.etat=lambda: {'modeles':[{'id':'test','disponible':True}]}
        for dossier,source in [('audios','../secret.wav'),('references','a.wav')]:
            with self.assertRaises(ValueError): self.a.demander({'modele':'test','dossier':dossier,'source':source})

if __name__=='__main__':unittest.main()
