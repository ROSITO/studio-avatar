"""Profils vocaux et synthèse locale. Aucune dépendance au serveur VoiceStudio."""
import memoire
import json
import os
from pathlib import Path
import platform
import shutil
import threading
import time
import urllib.request
import urllib.parse
import uuid

ENGINES = ('omnivoice', 'qwen3-tts-mlx', 'drama3-mlx')

class Atelier:
    def __init__(self, studio):
        self.s=studio; self.lock=threading.RLock()
        self.root=studio.ICI/'voix';self.root.mkdir(exist_ok=True)
        self.path=self.root/'profils.json'
        self.python=Path(os.environ.get('STUDIO_TTS_PYTHON',str(studio.ICI/'.venv-voix'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')))).expanduser()
    def interpreteur(self,mid):
        if mid!='omnivoice':return self.python
        return Path(os.environ.get('STUDIO_OMNIVOICE_PYTHON',str(self.s.ICI/'.venv-omnivoice'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')))).expanduser()
    def lire(self):
        try:return json.loads(self.path.read_text())
        except FileNotFoundError:return []
    def sauver(self, profils):
        tmp=self.path.with_suffix('.tmp');tmp.write_text(json.dumps(profils,ensure_ascii=False,indent=2));tmp.replace(self.path)
    def catalogue(self):
        g=self.s.GESTION_MODELES; moteur=g.config['selection'].get('synthese','qwen3-tts-mlx')
        compatible=platform.system()=='Darwin' and platform.machine()=='arm64'
        engines=[]
        for mid in ENGINES:
            e=g.entry(mid);p=g.path(e);present=g.valid(e,p)
            support=compatible or mid=='omnivoice';runtime=self.interpreteur(mid).is_file()
            try:
                memoire.verifier(mid);memoire_ok=True;raison_memoire=''
            except ValueError as exc:memoire_ok=False;raison_memoire=str(exc)
            engines.append(dict(id=mid,display_name=e['nom'],available=support and runtime and present and memoire_ok,
                reason=raison_memoire if not memoire_ok else '' if support and runtime and present else 'Apple Silicon requis' if not support else 'Installez le runtime '+('.venv-omnivoice' if mid=='omnivoice' else '.venv-voix') if not runtime else 'Téléchargez les poids dans Modèles',supports_cloning=True,supports_voice_design=False))
        return dict(ok=True,actif=moteur,engines=engines)
    def liste(self):
        c=self.catalogue();pret=next(e['available'] for e in c['engines'] if e['id']==c['actif'])
        return dict(ok=pret,voix=self.lire(),moteur=c['actif'],engines=c['engines'])
    def profil(self,pid):
        p=next((p for p in self.lire() if pid in (p['id'],p.get('ancien_id'))),None)
        if not p:raise ValueError('Profil vocal introuvable dans Mes voix.')
        return p
    def enregistrer(self,d):
        with self.lock:
            nom=str(d.get('nom','')).strip();texte=str(d.get('texte','')).strip();ref=d.get('reference','')
            if not nom or not texte:raise ValueError('Nom et transcription de la référence requis.')
            if not isinstance(ref,str) or Path(ref).name!=ref or not (self.s.ICI/'references'/ref).is_file():raise ValueError('Référence audio introuvable.')
            if Path(ref).suffix.lower() not in ('.wav','.mp3','.m4a','.flac','.ogg'):raise ValueError('Importez un fichier audio.')
            duree=self.s.duree(self.s.ICI/'references'/ref)
            if not 2<=duree<=60:raise ValueError('La référence doit durer entre 2 et 60 secondes.')
            profils=self.lire();pid=d.get('id') or 'locale-'+uuid.uuid4().hex[:12]
            if d.get('id') and not any(p['id']==pid for p in profils):raise ValueError('Profil introuvable.')
            p=dict(id=pid,nom=nom,texte=texte,reference=ref,langue=d.get('langue','fr'),duree=duree)
            ancien=next((x for x in profils if x['id']==pid),{})
            if ancien.get('ancien_id'):p['ancien_id']=ancien['ancien_id']
            p['moteur_origine']=ancien.get('moteur_origine') or self.s.GESTION_MODELES.config['selection'].get('synthese','qwen3-tts-mlx')
            self.sauver([x for x in profils if x['id']!=pid]+[p]);return p
    def supprimer(self,pid):
        with self.lock:
            if any(t['etat'] in ('en cours','en attente') for t in self.s.TACHES):raise ValueError('Attendez la fin des calculs avant de supprimer une voix.')
            self.sauver([p for p in self.lire() if p['id']!=pid])
    def importer_ancien(self):
        # Action explicite, une copie des références ; aucune dépendance ensuite.
        with urllib.request.urlopen(self.s.VOICESTUDIO+'/profiles',timeout=5) as r:anciens=json.load(r)
        with urllib.request.urlopen(self.s.VOICESTUDIO+'/engines/tts',timeout=5) as r:moteur=json.load(r).get('active')
        ajoutes=0
        for a in anciens:
            with self.lock:
                profils=self.lire();existant=next((p for p in profils if p.get('ancien_id')==a['id']),None)
                if existant:
                    if moteur in ENGINES and not existant.get('moteur_origine'):
                        existant['moteur_origine']=moteur;self.sauver(profils)
                    continue
            if not a.get('ref_text'):continue
            ref='voix-'+uuid.uuid4().hex[:12]+'.wav';dest=self.s.ICI/'references'/ref
            # VoiceStudio expose souvent un nom relatif : passer par son export audio.
            url=self.s.VOICESTUDIO+'/profiles/'+urllib.parse.quote(str(a['id']),safe='')+'/audio'
            with urllib.request.urlopen(url,timeout=30) as r:dest.write_bytes(r.read())
            try:p=self.enregistrer(dict(nom=a.get('name',a['id']),texte=a['ref_text'],reference=ref,langue={'French':'fr','English':'en','Spanish':'es','German':'de','Italian':'it','Portuguese':'pt'}.get(a.get('language'),a.get('language') or 'fr')))
            except Exception:dest.unlink(missing_ok=True);raise
            with self.lock:
                profils=self.lire();profil=next(x for x in profils if x['id']==p['id']);profil['ancien_id']=a['id']
                if moteur in ENGINES:profil['moteur_origine']=moteur
                self.sauver(profils)
            ajoutes+=1
        return dict(ajoutes=ajoutes)
    def generer(self,t,texte,pid,langue,out,seed=42):
        profil=self.profil(pid);g=self.s.GESTION_MODELES
        choix=(t.get('modeles') or g.selection()).get('synthese')
        if not choix:raise ValueError('Choisissez un modèle de synthèse dans Modèles.')
        if choix['id'] not in ENGINES or not choix['installe']:raise ValueError('Installez les poids du moteur de voix dans Modèles.')
        plafond=memoire.verifier(choix['id'])
        origine=profil.get('moteur_origine')
        if origine and choix['id']!=origine:raise ValueError('Cette voix utilise '+origine+'. Sélectionnez ce moteur dans Mes voix ; changer de moteur modifie le timbre.')
        python=self.interpreteur(choix['id'])
        if not python.is_file():raise ValueError('Installez le moteur avec installer_voix.py.')
        if not texte.strip():raise ValueError('Texte vide.')
        t['memoire']=dict(budget_octets=plafond,reserve_systeme_octets=4*memoire.GIB,mode='essai_borne' if choix['id']=='drama3-mlx' else 'standard')
        req=self.root/(t['id']+'-requete.json');brut=self.root/(t['id']+'-brut.wav');tmp=out.with_suffix('.tmp.wav')
        req.write_text(json.dumps(dict(texte=texte,moteur=choix['id'],modele=choix['path'],reference=str(self.s.ICI/'references'/profil['reference']),transcription=profil['texte'],langue=langue,seed=int(seed),sortie=str(brut)),ensure_ascii=False))
        try:
            t['etape']='Synthèse vocale locale · '+g.entry(choix['id'])['nom'];self.s.sauver()
            self.s.lancer(t,[python,'-u',self.s.ICI/('lancer_omnivoice.py' if choix['id']=='omnivoice' else 'lancer_voix.py'),req],env={'STUDIO_TTS_EFFECTIVE_LIMIT':str(plafond),'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','HF_HOME':str(self.s.MODELES/'huggingface')})
            if not brut.is_file() or brut.stat().st_size<44:raise RuntimeError('Le moteur vocal n’a produit aucun audio. Consultez le journal.')
            self.s.lancer(t,['ffmpeg','-v','error','-y','-i',brut,'-ac','1','-ar','44100','-c:a','pcm_s24le',tmp])
            if t.get('annuler'):raise RuntimeError('Tâche annulée')
            tmp.replace(out)
            out.with_suffix('.json').write_text(json.dumps(dict(synthetique=True,moteur=choix['id'],profil=profil['id'],texte=texte,seed=seed),ensure_ascii=False))
        finally:
            for f in (req,brut,tmp):f.unlink(missing_ok=True)
    def essai(self,d):
        profil=self.profil(d.get('profil'));texte=str(d.get('texte','')).strip()
        if not texte or len(texte)>5000:raise ValueError('Saisissez entre 1 et 5000 caractères.')
        t=dict(id=uuid.uuid4().hex[:12],type='voix',params=dict(profil=profil['id'],texte=texte,langue=profil['langue']),modeles=self.s.GESTION_MODELES.selection(),etat='en attente',cree=time.time())
        with self.s.VERROU:self.s.TACHES.append(t)
        self.s.sauver()
        return t
    def executer(self,t):
        p=t['params'];out=self.s.ICI/'audios'/('voix-'+t['id']+'.wav')
        self.generer(t,p['texte'],p['profil'],p['langue'],out,seed=int(t['id'][:8],16)%2147483648)
        t['resultat']=dict(fichier=out.name,profil=p['profil'])
