"""Model-manager regression tests; no weights, GPU, or external network required."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import modeles

class Response(io.BytesIO):
    def __init__(self,data,status=200,headers=None):super().__init__(data);self.status=status;self.headers=headers or {}

class ModelesTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.s=SimpleNamespace(ICI=self.root,MODELES=self.root/'weights',TACHES=[],VOICESTUDIO='http://127.0.0.1:3900',LTX='missing-ltx')
        self.m=modeles.Gestionnaire(self.s)
    def tearDown(self):self.tmp.cleanup()
    def fichier(self,data=b'example'):
        return dict(nom='config.json',repo='example/model',revision='abcd',source='config.json',taille=len(data),sha256=hashlib.sha256(data).hexdigest())
    def test_reprise_range_et_integrite(self):
        self.s.MODELES.mkdir(); f=self.fichier(); (self.s.MODELES/'config.json.part').write_bytes(b'exa')
        with patch.object(modeles,'ouvrir',return_value=Response(b'mple',206,{'Content-Range':'bytes 3-6/7'})) as get:
            self.m.telecharger(self.s.MODELES,f,0)
            self.assertEqual(get.call_args.args[1],{'Range':'bytes=3-'})
        self.assertEqual((self.s.MODELES/'config.json').read_bytes(),b'example')
        with patch.object(modeles,'ouvrir',side_effect=AssertionError('Already downloaded')):
            self.m.telecharger(self.s.MODELES,f,0)
    def test_serveur_ignore_range_et_fichier_corrompu(self):
        self.s.MODELES.mkdir();f=self.fichier();(self.s.MODELES/'config.json.part').write_bytes(b'exa')
        with patch.object(modeles,'ouvrir',return_value=Response(b'example')):self.m.telecharger(self.s.MODELES,f,0)
        (self.s.MODELES/'config.json').unlink()
        with patch.object(modeles,'ouvrir',return_value=Response(b'corrupt')):
            with self.assertRaises(ValueError):self.m.telecharger(self.s.MODELES,f,0)
        self.assertFalse((self.s.MODELES/'config.json').exists());self.assertFalse((self.s.MODELES/'config.json.part').exists())
    def test_selection_persistante_et_verrouillage(self):
        e=self.m.entry('ltx23-q8');target=self.m.target(e);target.mkdir(parents=True)
        for name in e['required']:(target/name).write_bytes(b'x')
        self.m.choisir(e['id']);snapshot=self.m.selection();self.assertEqual(snapshot['video']['id'],e['id'])
        self.assertEqual(modeles.Gestionnaire(self.s).selection()['video']['id'],e['id'])
        self.s.TACHES=[dict(etat='en cours')]
        with self.assertRaises(ValueError):self.m.choisir(e['id'])
        with self.assertRaises(ValueError):self.m.choisir('ltx23-q4')
        self.assertEqual(snapshot['video']['id'],e['id'])
    def test_manifeste_revision_filtres_et_chemins(self):
        e=dict(sources=[dict(repo='example/model',include=['*.json'],prefix='')],required=['config.json'],id='test')
        info=dict(sha='pinned123',siblings=[dict(rfilename='config.json',size=2,blobId=hashlib.sha1(b'blob 2\0{}').hexdigest()),dict(rfilename='malicious.py',size=100)])
        with patch.object(modeles,'ouvrir',return_value=Response(json.dumps(info).encode())):plan=self.m.analyser(e)
        self.assertEqual(len(plan['fichiers']),1);self.assertEqual(plan['fichiers'][0]['revision'],'pinned123')
        for bad in ('../secret','/absolute','sub/../../secret','bad\\path'):
            with self.assertRaises(ValueError):modeles.safe_path(self.root,bad)
        self.assertEqual(plan['total'],2)
    def test_annulation_et_reprise_apres_redemarrage(self):
        self.s.MODELES.mkdir();self.m.cancel.set()
        with patch.object(modeles,'ouvrir',return_value=Response(b'example')):
            with self.assertRaises(InterruptedError):self.m.telecharger(self.s.MODELES,self.fichier(),0)
        modeles.atomique(self.m.etat_path,dict(statut='telechargement',id='gemma3'))
        self.assertEqual(modeles.Gestionnaire(self.s).etat['statut'],'interrompu')
    def test_disque_insuffisant_ne_telecharge_pas(self):
        e=self.m.entry('ltx23-q4');self.m.plans[e['id']]=dict(total=7,fichiers=[self.fichier()])
        with patch.object(modeles.shutil,'disk_usage',return_value=SimpleNamespace(free=0)),patch.object(self.m,'telecharger') as download:
            self.m.travailler(e,True)
        self.assertEqual(self.m.etat['statut'],'erreur');download.assert_not_called()
    def test_redirection_ne_transmet_pas_token(self):
        req=modeles.urllib.request.Request('https://huggingface.co/x',headers={'Authorization':'Bearer test'})
        handler=modeles.SansFuiteToken()
        redirected=handler.redirect_request(req,None,302,'redirect',{},'https://cdn.example.test/file')
        self.assertFalse(redirected.has_header('Authorization'))
    def test_import_ne_copie_pas_et_refuse_mauvaise_version(self):
        p=self.root/'existing';p.mkdir()
        for name in modeles.VIDEO_FILES:(p/name).write_bytes(b'x')
        (p/'config.json').write_text('{"model_version":"2.5.0"}')
        with self.assertRaises(ValueError):self.m.importer(str(p),'Existing')
        (p/'config.json').write_text('{"model_version":"2.3.0"}')
        self.m.importer(str(p),'Existing');e=self.m.config['locaux'][0]
        self.assertEqual(self.m.path(e),p.resolve());self.assertEqual(len(self.m.config['locaux']),1)

if __name__=='__main__':unittest.main()
