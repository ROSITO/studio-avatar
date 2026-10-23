"""Native voice profiles and queue, without MLX or a VoiceStudio service."""
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
import studio, voix, test_projets

class VoixIntegreesTest(unittest.TestCase):
    def setUp(self):
        self.fixture=test_projets.ProjetsTest();self.fixture.setUp()
        self.memoire_patch=patch('memoire.verifier',return_value=16*1024**3);self.memoire_patch.start()
        self.addCleanup(self.memoire_patch.stop)
        self.atelier=voix.Atelier(studio)
        ref=studio.ICI/'references'/'ref.wav'
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','sine=frequency=440:duration=3',str(ref)],check=True)
        self.profil=self.atelier.enregistrer(dict(nom='Ma voix',texte='Bonjour depuis la référence.',reference='ref.wav',langue='fr'))
    def tearDown(self):self.fixture.tearDown()
    def test_vue_modele_exclut_appledouble_sans_copier_les_poids(self):
        from lancer_voix import vue_modele
        source=self.fixture.root/'poids';source.mkdir();(source/'speech_tokenizer').mkdir()
        (source/'speech_tokenizer'/'model.safetensors').write_bytes(b'poids')
        (source/'speech_tokenizer'/'._model.safetensors').write_bytes(b'metadonnees macOS')
        with vue_modele(source,self.atelier.root) as vue:
            files=list((vue/'speech_tokenizer').glob('*.safetensors'))
            self.assertEqual(len(files),1);self.assertTrue(files[0].is_symlink())
            self.assertEqual(files[0].read_bytes(),b'poids');self.assertEqual(files[0].resolve(),(source/'speech_tokenizer'/'model.safetensors').resolve())
        self.assertFalse(vue.exists())
    def test_profils_persistants_et_validation(self):
        self.assertEqual(voix.Atelier(studio).profil(self.profil['id'])['nom'],'Ma voix')
        with self.assertRaises(ValueError):self.atelier.enregistrer(dict(nom='x',texte='x',reference='../ref.wav'))
        with self.assertRaises(ValueError):self.atelier.enregistrer(dict(nom='x',texte='',reference='ref.wav'))
        self.assertFalse(list(self.atelier.root.glob('*.tmp')))
    def test_catalogue_ne_contacte_pas_voicestudio(self):
        with patch('urllib.request.urlopen',side_effect=AssertionError('No external server')):
            d=self.atelier.liste()
        self.assertEqual(len(d['engines']),3);self.assertEqual(len(d['voix']),1)
    def test_prise_normalisee_sans_fondu_et_requete_nettoyee(self):
        python=self.fixture.root/'python';python.touch();self.atelier.python=python
        t=dict(id='abcdef123456',params={},modeles=dict(synthese=dict(id='qwen3-tts-mlx',path='local',installe=True)))
        out=studio.ICI/'audios'/'test.wav';run=studio.lancer
        def lancer(t,cmd,env=None):
            if cmd[0]==python:
                self.assertEqual(env['HF_HUB_OFFLINE'],'1')
                d=json.loads(Path(cmd[-1]).read_text());self.assertEqual(d['transcription'],self.profil['texte'])
                self.assertEqual(d['seed'],7)
                subprocess.run(['ffmpeg','-v','error','-y','-i',studio.ICI/'references'/'ref.wav',d['sortie']],check=True)
            else:run(t,cmd,env)
        with patch.object(studio,'lancer',side_effect=lancer):self.atelier.generer(t,'Un essai.',self.profil['id'],'fr',out,7)
        self.assertAlmostEqual(studio.duree(out),3,places=2)
        self.assertTrue(json.loads(out.with_suffix('.json').read_text())['synthetique'])
        self.assertFalse(list(self.atelier.root.glob('*requete.json')))
        self.assertFalse(list(self.atelier.root.glob('*brut.wav')))
    def test_moteur_original_utilise_le_worker_autonome(self):
        profils=self.atelier.lire();profils[0]['moteur_origine']='omnivoice';self.atelier.sauver(profils)
        python=self.fixture.root/'python';python.touch()
        t=dict(id='abcdef123456',modeles=dict(synthese=dict(id='omnivoice',path='local',installe=True)))
        def lancer(t,cmd,env=None):
            if cmd[0]==python:
                self.assertEqual(Path(cmd[2]).name,'lancer_omnivoice.py')
                d=json.loads(Path(cmd[-1]).read_text());self.assertEqual(d['moteur'],'omnivoice')
                subprocess.run(['ffmpeg','-v','error','-y','-i',studio.ICI/'references'/'ref.wav',d['sortie']],check=True)
            else:subprocess.run(list(map(str,cmd)),check=True)
        with patch.object(self.atelier,'interpreteur',return_value=python),patch.object(studio,'lancer',side_effect=lancer),patch('urllib.request.urlopen',side_effect=AssertionError('No VoiceStudio synthesis')):
            self.atelier.generer(t,'Essai',self.profil['id'],'fr',studio.ICI/'audios'/'omni.wav')
        self.assertTrue((studio.ICI/'audios'/'omni.wav').exists())
    def test_changer_de_moteur_ne_change_pas_silencieusement_identite(self):
        profils=self.atelier.lire();profils[0]['moteur_origine']='omnivoice';self.atelier.sauver(profils)
        t=dict(id='abcdef123456',modeles=dict(synthese=dict(id='qwen3-tts-mlx',path='local',installe=True)))
        with self.assertRaisesRegex(ValueError,'Cette voix utilise omnivoice'):
            self.atelier.generer(t,'Essai',self.profil['id'],'fr',studio.ICI/'audios'/'refuse.wav')
    def test_balises_transmises_uniquement_a_drama(self):
        python=self.fixture.root/'python';python.touch();self.atelier.python=python
        profils=self.atelier.lire();profils[0].pop('moteur_origine',None);self.atelier.sauver(profils)
        texte='[curious] Bonjour. [laughs] On recommence !'
        for moteur,attendu in [('drama3-mlx','Bonjour. [laughs] On recommence !'),('qwen3-tts-mlx','Bonjour. On recommence !')]:
            with self.subTest(moteur=moteur):
                t=dict(id='abcdef123456',modeles=dict(synthese=dict(id=moteur,path='local',installe=True)))
                out=studio.ICI/'audios'/(moteur+'.wav')
                def lancer(t,cmd,env=None):
                    if cmd[0]==python:
                        d=json.loads(Path(cmd[-1]).read_text());self.assertEqual(d['texte'],attendu)
                        subprocess.run(['ffmpeg','-v','error','-y','-i',studio.ICI/'references'/'ref.wav',d['sortie']],check=True)
                    else:subprocess.run(list(map(str,cmd)),check=True)
                with patch.object(studio,'lancer',side_effect=lancer):
                    self.atelier.generer(t,texte,self.profil['id'],'fr',out)
                meta=json.loads(out.with_suffix('.json').read_text())
                self.assertEqual(meta['texte'],texte);self.assertEqual(meta['texte_synthese'],attendu)
    def test_echec_ne_remplace_pas_une_prise_existante(self):
        self.atelier.python=self.fixture.root/'python';self.atelier.python.touch()
        t=dict(id='abcdef123456',modeles=dict(synthese=dict(id='qwen3-tts-mlx',path='local',installe=True)))
        out=studio.ICI/'audios'/'ancienne.wav';out.write_bytes(b'ancienne prise')
        with patch.object(studio,'lancer',side_effect=RuntimeError('Erreur moteur')):
            with self.assertRaises(RuntimeError):self.atelier.generer(t,'Essai',self.profil['id'],'fr',out)
        self.assertEqual(out.read_bytes(),b'ancienne prise');self.assertFalse(list(self.atelier.root.glob('*requete.json')))
    def test_seed_essai_optionnelle_et_bornee(self):
        t=self.atelier.essai(dict(profil=self.profil['id'],texte='Bonjour.',seed=7))
        self.assertEqual(t['params']['seed'],7)
        autre=self.atelier.essai(dict(profil=self.profil['id'],texte='Bonjour.'))
        self.assertNotIn('seed',autre['params'])
        for valeur in (-1,2**31,True,'7',1.5):
            with self.assertRaisesRegex(ValueError,'Seed vocale'):
                self.atelier.essai(dict(profil=self.profil['id'],texte='Bonjour.',seed=valeur))
    def test_ancien_id_et_file_capture_le_modele(self):
        profils=self.atelier.lire();profils[0]['ancien_id']='ancien';self.atelier.sauver(profils)
        self.assertEqual(self.atelier.profil('ancien')['id'],self.profil['id'])
        with patch.object(studio,'sauver',side_effect=lambda:self.assertFalse(studio.VERROU.locked(),'Save must not reacquire the held queue lock')):
            t=self.atelier.essai(dict(profil='ancien',texte='Bonjour.'))
        self.assertIn(t,studio.TACHES);self.assertIn('synthese',t['modeles'])
        with self.assertRaises(ValueError):self.atelier.supprimer(self.profil['id'])

if __name__=='__main__':unittest.main()
