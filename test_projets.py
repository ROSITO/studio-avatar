"""Tests isolés : états persistants, dépendances, reprise et vrai montage ffmpeg.
LTX et MuseTalk sont remplacés par des médias synthétiques ; aucun calcul GPU.
"""
import json, shutil, subprocess, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import studio
import projets

class ProjetsTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); root=Path(self.tmp.name)
        self.patches=[patch.object(projets.montage,'analyser',self.analyser),patch.object(studio,'ICI',root),patch.object(studio,'TACHES',[]),patch.object(studio,'sauver',lambda:None),patch.object(studio,'resolution',lambda p:(64,64)),patch.object(studio,'apercu',lambda p:None),patch.object(studio,'ltx',self.ltx),patch.object(studio,'voix',self.voix),patch.object(studio,'musetalk',self.muse)]
        for p in self.patches:p.start()
        for d in studio.DOSSIERS+['taches']:(root/d).mkdir()
        projets.installer(studio); self.root=root; self.generations=[]; self.voix_count=0; self.audios_a2v=[]; self.muse_count=0; self.voix_seeds=[]
        (root/'sources'/'avatar.png').write_bytes(b'photo test')
    def analyser(self,studio,t,p,tr):
        total=projets.montage.frames_blocs(p)[tr['gauche']]
        return dict(version=projets.montage.VERSION,sources=[b['clip'] for b in p['blocs'] if b['id'] in (tr['gauche'],tr['droite'])],revision=tr['revision'],total=total,frames=15,mode='ltx',score=.1)
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def ff(self,args): subprocess.run(['ffmpeg','-v','error','-y',*map(str,args)],check=True)
    def ltx(self,t,images,prompt,W,H,frames,seed,out,audio=None):
        self.generations.append((out.name,images,frames,seed))
        if audio: self.audios_a2v.append((studio.duree(audio),frames/24))
        self.ff(['-f','lavfi','-i','color=c=blue:s=64x64:r=24','-frames:v',frames,'-c:v','libx264','-pix_fmt','yuv420p',out])
    def voix(self,t,texte,profil,langue,out,seed=42):
        self.voix_count+=1; self.voix_seeds.append(seed)
        self.ff(['-f','lavfi','-i','sine=frequency=440:sample_rate=44100','-t','1.25',out])
    def muse(self,t,video,audio,out,shift):
        self.muse_count+=1
        self.ff(['-i',video,'-i',audio,'-map','0:v','-map','1:a','-c:v','copy','-c:a','aac','-shortest',out])
    def creer(self):return projets.creer(dict(avatar='avatar.png',voix='test',texte='[curious] Première phrase. Deuxième phrase. [laughs] Toujours curieux. [excited] Formidable ! [serious] Attention.'))
    def drain(self):
        for t in studio.TACHES:
            if t['etat']=='en attente':
                t['etat']='en cours'; projets.executer(t); t['etat']='finie'
    def test_pipeline_reprise_et_invalidation_locale(self):
        p=self.creer(); pid=p['id']
        self.assertEqual(len(p['blocs']),3)
        self.assertIn('Deuxième phrase.',p['blocs'][0]['texte'])
        self.assertIn('Toujours curieux.',p['blocs'][0]['texte'])
        self.assertEqual(studio.TACHES,[])
        projets.lancer(pid,dict(action='manquants')); self.drain(); p=projets.lire(pid)
        self.assertEqual(len(self.generations),5)
        self.assertTrue(all(projets.pont_pret(p,b) for b in p['transitions']))
        # Rejouer la tâche finie après un arrêt ne régénère pas le fichier.
        projets.executer(studio.TACHES[0]); self.assertEqual(len(self.generations),5)
        # Montage réel, avec silences des transitions et audio par bloc.
        projets.lancer(pid,dict(action='export')); self.drain(); p=projets.lire(pid)
        self.assertAlmostEqual(studio.duree(self.root/'videos'/p['export']['fichier']),3.75,delta=.1)
        ancien=[b['clip'] for b in p['blocs']]; audios=[b['audio'] for b in p['blocs']]
        projets.lancer(pid,dict(action='clip',element=p['blocs'][1]['id'])); self.drain(); p=projets.lire(pid)
        self.assertEqual(p['blocs'][0]['clip'],ancien[0]); self.assertEqual(p['blocs'][2]['clip'],ancien[2]); self.assertNotEqual(p['blocs'][1]['clip'],ancien[1])
        self.assertEqual([b['audio'] for b in p['blocs']],audios); self.assertEqual(self.voix_count,3)
        self.assertTrue(all(not projets.pont_pret(p,b) for b in p['transitions']))
        with self.assertRaises(ValueError):projets.lancer(pid,dict(action='export'))
        projets.lancer(pid,dict(action='manquants')); self.drain(); self.assertEqual(len(self.generations),8)
        p=projets.lire(pid); projets.modifier(pid,dict(action='supprimer',element=p['blocs'][1]['id'])); p=projets.lire(pid)
        self.assertEqual(len(p['transitions']),1); self.assertFalse(projets.pont_pret(p,p['transitions'][0])); self.assertTrue((self.root/'clips'/ancien[1]).exists())
    def test_seules_les_transitions_adjacentes_expirent(self):
        p=self.creer(); pid=p['id']; projets.modifier(pid,dict(action='ajouter'))
        p=projets.lire(pid); dernier=p['blocs'][-1]
        projets.modifier(pid,dict(action='modifier',element=dernier['id'],texte='Dernier bloc.'))
        projets.lancer(pid,dict(action='manquants')); self.drain(); p=projets.lire(pid)
        pont_eloigne=p['transitions'][2]['clip']
        projets.lancer(pid,dict(action='clip',element=p['blocs'][1]['id'])); self.drain(); p=projets.lire(pid)
        self.assertFalse(projets.pont_pret(p,p['transitions'][0])); self.assertFalse(projets.pont_pret(p,p['transitions'][1]))
        self.assertTrue(projets.pont_pret(p,p['transitions'][2])); self.assertEqual(p['transitions'][2]['clip'],pont_eloigne)

    def test_audio_importe_et_limites_conservees(self):
        audio=self.root/'audios'/'source.wav'; self.voix(None,'','',None,audio)
        p=projets.creer(dict(avatar='avatar.png',audio='source.wav',texte='[curious] Bonjour. [excited] Salut !!'))
        self.assertEqual(len(p['blocs']),2)
        self.assertAlmostEqual(sum(b['audio_duree'] for b in p['blocs']),1.25,places=2)
        projets.lancer(p['id'],dict(action='manquants')); self.drain(); p=projets.lire(p['id'])
        self.assertTrue(all(projets.courant(b) for b in p['blocs']))
        with self.assertRaises(ValueError): projets.modifier(p['id'],dict(action='modifier',element=p['blocs'][0]['id'],texte='Autre texte'))

    def test_echec_conserve_audio_et_anciens_rendus(self):
        p=self.creer(); b=p['blocs'][0]
        projets.lancer(p['id'],dict(action='clip',element=b['id'])); t=studio.TACHES[-1]; t['etat']='en cours'
        with patch.object(studio,'ltx',side_effect=RuntimeError('GPU indisponible')):
            with self.assertRaises(RuntimeError):projets.executer(t)
        t['etat']='erreur'; p=projets.lire(p['id']); self.assertTrue(p['blocs'][0]['audio']); self.assertFalse(p['blocs'][0]['clip'])
        projets.lancer(p['id'],dict(action='clip',element=b['id'])); self.drain(); self.assertEqual(self.voix_count,1)
    def test_refaire_voix(self):
        p=self.creer(); b=p['blocs'][1]
        projets.lancer(p['id'],dict(action='clip',element=b['id'])); self.drain(); p=projets.lire(p['id'])
        ancien=p['blocs'][1]['audio']; self.assertEqual(self.voix_count,1)
        p=projets.modifier(p['id'],dict(action='refaire_voix',element=b['id']))
        self.assertIsNone(p['blocs'][1]['audio']); self.assertFalse(projets.courant(p['blocs'][1]))
        projets.lancer(p['id'],dict(action='clip',element=b['id'])); self.drain(); p=projets.lire(p['id'])
        self.assertEqual(self.voix_count,2); self.assertNotEqual(p['blocs'][1]['audio'],ancien); self.assertNotEqual(self.voix_seeds[0],self.voix_seeds[1]); self.assertEqual(p['blocs'][1]['texte'],b['texte'])
    def test_ponts_relances_si_raccord_mauvais(self):
        p=self.creer(); pid=p['id']
        for b in p['blocs']: projets.lancer(pid,dict(action='clip',element=b['id']))
        self.drain(); p=projets.lire(pid); avant=len(self.generations)
        ecarts=iter([6.0,5.0,4.5, 3.0])
        with patch.object(projets.montage,'ecart_raccord',lambda *a:next(ecarts)):
            projets.lancer(pid,dict(action='pont',element=p['transitions'][0]['id'])); self.drain()
            self.assertEqual(len(self.generations)-avant,3)            # 3 essais, aucun sous le seuil
            projets.lancer(pid,dict(action='pont',element=p['transitions'][1]['id'])); self.drain()
            self.assertEqual(len(self.generations)-avant,4)            # bon du premier coup
        p=projets.lire(pid); t0=p['transitions'][0]
        self.assertEqual(t0['ecart'],4.5); self.assertEqual(t0['seed'],self.generations[avant+2][3]); self.assertTrue(projets.pont_pret(p,t0))
        self.assertFalse(list((self.root/'ponts').glob('*-essai*.mp4')))
    def test_projet_vide_refuse(self):
        for d in (dict(avatar='avatar.png'),dict(avatar='avatar.png',voix='test',texte='  '),dict(avatar='avatar.png',audio='',texte='Bonjour')):
            with self.assertRaises(ValueError): projets.creer(d)
    def test_edition_deplacement_et_validation(self):
        p=self.creer(); pid=p['id']; b=p['blocs'][0]
        with self.assertRaises(ValueError):projets.modifier(pid,dict(action='modifier',element=b['id'],duree=-1))
        projets.modifier(pid,dict(action='deplacer',element=b['id'],sens=1)); p=projets.lire(pid); self.assertEqual(p['blocs'][1]['id'],b['id'])
        projets.lancer(pid,dict(action='clip',element=b['id']))
        with self.assertRaises(ValueError):projets.modifier(pid,dict(action='supprimer',element=b['id']))
        # Double clic ne duplique pas une tâche.
        projets.lancer(pid,dict(action='clip',element=b['id'])); self.assertEqual(len(studio.TACHES),1)
    def test_moteur_a2v_et_musetalk(self):
        p=self.creer(); self.assertEqual(p['moteur'],'a2v')
        projets.lancer(p['id'],dict(action='automatique')); self.drain(); p=projets.lire(p['id'])
        # Clips et ponts parlants, chaque voix couvre toute la vidéo (silence ajouté), pas de MuseTalk.
        self.assertEqual(len(self.audios_a2v),5); self.assertTrue(all(a>=v for a,v in self.audios_a2v))
        self.assertEqual(self.muse_count,0); self.assertTrue(p['export'])
        projets.modifier(p['id'],dict(action='moteur',moteur='musetalk')); p=projets.lire(p['id'])
        self.assertFalse(any(projets.courant(b) for b in p['blocs']))
        projets.lancer(p['id'],dict(action='automatique')); self.drain()
        self.assertEqual(len(self.audios_a2v),5); self.assertEqual(self.muse_count,1)
    def test_decoupe_bloc_long_aux_phrases(self):
        phrase='Une phrase de trois secondes environ.'
        p=projets.creer(dict(avatar='avatar.png',voix='test',texte='[serious] '+' '.join([phrase]*5)+' [excited] Court.'))
        self.assertEqual([b['ton'] for b in p['blocs']],['serieux']*3+['enthousiaste'])
        self.assertTrue(all(len(b['texte'])<=projets.BLOC_MAX*projets.CARACTERES_SECONDE for b in p['blocs']))
        self.assertEqual(' '.join(b['texte'] for b in p['blocs'][:3]),' '.join([phrase]*5))
        # Une phrase plus longue que le plafond n’est jamais coupée.
        long='Une '+'très '*40+'longue phrase.'
        self.assertEqual(projets.decouper(long),[long])
    def test_controle_visage_optionnel(self):
        p=self.creer(); b=p['blocs'][0]; scores=iter([.3,.25,.1])
        with patch.object(projets,'visage',lambda t,v:next(scores)) as _:
            projets.lancer(p['id'],dict(action='clip',element=b['id'])); self.drain()
            self.assertEqual(len(self.generations),1)   # décoché par défaut : un seul essai
            projets.modifier(p['id'],dict(action='controle_visage',actif=True)); p=projets.lire(p['id'])
            self.assertTrue(projets.courant(p['blocs'][0]))   # cocher n’invalide rien
            projets.lancer(p['id'],dict(action='clip',element=b['id'])); self.drain(); p=projets.lire(p['id'])
        self.assertEqual(len(self.generations),4); self.assertEqual(p['blocs'][0]['visage'],.1)
        self.assertEqual(p['blocs'][0]['seed'],self.generations[-1][3])

if __name__=='__main__': unittest.main()
