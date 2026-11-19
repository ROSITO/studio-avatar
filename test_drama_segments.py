import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave

import drama_segments as segments
import voix


class DecoupageTest(unittest.TestCase):
    def test_mots_balises_reactions_pauses_et_limites(self):
        text = '[curious] ' + 'Une phrase assez longue pour plusieurs passages. '*12
        text += '[laughs] Encore une phrase. [pause] [warm] La conclusion.'
        plan=segments.plan(text)
        parts=plan['segments']
        self.assertEqual(segments.spoken(text),segments.spoken(' '.join(x['texte'] for x in parts)))
        self.assertEqual(' '.join(x['texte'] for x in parts).count('[laughs]'),1)
        self.assertTrue(any(x['pause_apres']==.35 for x in parts))
        self.assertTrue(all(len(x['texte'].encode())<=280 and len(segments.spoken(x['texte']))<=140 for x in parts))
        self.assertTrue(all(x['texte'].startswith('[curious]') for x in parts[:-1]))
        self.assertTrue(parts[-1]['texte'].startswith('[warm]'))

    def test_accents_decimal_sans_couper_mots_et_pause_initiale(self):
        text='[pause] [voice:chaleureuse] '+('Voilà un chiffre 3.14, et une explication élégante ! '*9)
        p=segments.plan(text)
        self.assertEqual(p['segments'][0]['pause_avant'],.35)
        self.assertEqual(segments.spoken(text),segments.spoken(' '.join(s['texte'] for s in p['segments'])))
        self.assertTrue(all('[chaleureuse]' in s['texte'] for s in p['segments']))

    def test_refus_explicit_avant_calcul(self):
        for value in ('[pause]', '[balise cassée', '[[]]', '<|speaker:0|> Bonjour',
                      '[laughs]', 'a'*281, '[x]'+'é'*150, 12):
            with self.subTest(value=str(value)[:35]), self.assertRaises(segments.Validation):
                segments.plan(value)

    def test_indications_consecutives_conservees_et_finale_sans_parole_refusee(self):
        p=segments.plan('[warm] [soft voice] Bonjour. [curious] Pourquoi ?')
        self.assertTrue(p['segments'][0]['texte'].startswith('[warm] [soft voice]'))
        self.assertTrue(p['segments'][-1]['texte'].startswith('[curious]'))
        with self.assertRaises(segments.Validation):segments.plan('Bonjour. [warm]')


class ProductionTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        for d in ('audios','references','taches'): (self.root/d).mkdir()
        (self.root/'references/ref.wav').write_bytes(b'reference-originale')
        selection={'synthese':{'id':'drama3-mlx','path':'poids-locaux','installe':True}}
        self.s=SimpleNamespace(ICI=self.root,TACHES=[],VERROU=threading.Lock(),
            sauver=lambda:None,GESTION_MODELES=SimpleNamespace(selection=lambda:selection))
        self.a=voix.Atelier(self.s)
        self.a.sauver([dict(id='helie',nom='Hélie',texte='Référence.',reference='ref.wav',langue='fr',moteur_origine='drama3-mlx')])
        self.t=self.a.preparer_essai(dict(profil='helie',texte='[curious] Bonjour. [pause] [warm] Salut.',seed=42))
        self.t['etat']='en cours';self.s.TACHES.append(self.t)
        self.calls=[]

    def render(self,child,text,pid,lang,out,seed):
        self.calls.append((child['id'],text,seed))
        with wave.open(str(out),'wb') as f:
            f.setparams((1,3,44100,0,'NONE','not compressed'))
            f.writeframes(b'\x01\x00\x00'*8820)

    def test_deux_processus_logiques_assemblage_et_reprise_sans_recalcul(self):
        with patch.object(self.a,'generer',side_effect=self.render):
            self.a.executer(self.t)
            self.a.executer(self.t)
        self.assertEqual(len(self.calls),2)
        self.assertNotEqual(self.calls[0][0],self.calls[1][0])
        p=self.root/'audios'/self.t['resultat']['fichier']
        self.assertAlmostEqual(segments.duration(p),.75)
        m=json.loads(p.with_suffix('.json').read_text())
        self.assertEqual(m['texte'],self.t['params']['texte'])
        self.assertEqual(m['segmentation']['termines'],2)
        self.assertFalse(list((self.root/'audios').glob('*.tmp.wav')))

    def test_echec_reprise_conserve_premier_passage(self):
        def render(child,text,pid,lang,out,seed):
            if '[warm]' in text:raise RuntimeError('protection mémoire')
            self.render(child,text,pid,lang,out,seed)
        with patch.object(self.a,'generer',side_effect=render),self.assertRaisesRegex(RuntimeError,'après 3 essais'):
            self.a.executer(self.t)
        self.assertEqual(self.t['segmentation']['termines'],1)
        self.assertFalse((self.root/'audios'/('voix-'+self.t['id']+'.wav')).exists())
        self.assertTrue(self.t['erreur_detail']['relancable'])
        self.t['etat']='erreur'
        self.assertIs(self.a.essai({'reprendre':self.t['id']}),self.t)
        with patch.object(self.a,'generer',side_effect=self.render):self.a.executer(self.t)
        self.assertEqual(len(self.calls),2)  # Only the missing passage is rendered.

    def test_retry_change_seed_sans_changer_texte(self):
        def render(child,text,pid,lang,out,seed):
            if seed==42:raise RuntimeError('silence prolongé')
            self.render(child,text,pid,lang,out,seed)
        with patch.object(self.a,'generer',side_effect=render):self.a.executer(self.t)
        self.assertTrue(all(seed==43 for _,_,seed in self.calls))
        self.assertTrue(all(x['essais']==2 for x in self.t['segmentation']['segments']))

    def test_annulation_pas_de_final_et_reprise_idempotente(self):
        def render(*args,**kwargs):
            self.render(*args,**kwargs);self.t['annuler']=True
        with patch.object(self.a,'generer',side_effect=render),self.assertRaisesRegex(RuntimeError,'annulée'):
            self.a.executer(self.t)
        self.assertNotIn('resultat',self.t)
        self.t['etat']='annulée'
        self.a.essai({'reprendre':self.t['id']})
        self.assertNotIn('annuler',self.t)
        self.assertIs(self.a.essai({'reprendre':self.t['id']}),self.t)
        self.assertEqual(len(self.s.TACHES),1)

    def test_reference_changee_refuse_de_melanger(self):
        with patch.object(self.a,'generer',side_effect=self.render):self.a.executer(self.t)
        (self.root/'references/ref.wav').write_bytes(b'autre-voix')
        with self.assertRaisesRegex(RuntimeError,'ont changé'):self.a.executer(self.t)

    def test_checkpoint_corrompu_regenere_uniquement_ce_passage(self):
        with patch.object(self.a,'generer',side_effect=self.render):self.a.executer(self.t)
        broken=self.root/'audios'/self.t['segmentation']['segments'][0]['fichier']
        broken.write_bytes(b'corrompu')
        with patch.object(self.a,'generer',side_effect=self.render):self.a.executer(self.t)
        self.assertEqual(len(self.calls),3)
        self.assertEqual(self.t['segmentation']['termines'],2)

    def test_validation_ne_met_rien_en_file(self):
        before=len(self.s.TACHES)
        for data in ({'profil':'helie','texte':'[balise'}, {'profil':'inconnu','texte':'Bonjour.'},
                     {'profil':'helie','texte':['Bonjour']}, {'profil':'helie','texte':'Bonjour','seed':True}):
            with self.assertRaises(segments.Validation):self.a.essai(data)
        self.assertEqual(len(self.s.TACHES),before)


if __name__=='__main__':unittest.main()
