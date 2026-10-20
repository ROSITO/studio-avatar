"""Local model catalogue, resumable verified downloads and persisted selection.
Only curated Hugging Face repositories are downloadable; no remote code is loaded.
"""
import fnmatch
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

VIDEO_FILES = ['config.json','transformer-distilled.safetensors','connector.safetensors','vae_decoder.safetensors','vae_encoder.safetensors','audio_vae.safetensors','vocoder.safetensors','spatial_upscaler_x2_v1_1.safetensors']
MUSE_FILES = ['musetalkV15/unet.pth','musetalkV15/musetalk.json','sd-vae/config.json','sd-vae/diffusion_pytorch_model.bin','whisper/config.json','whisper/pytorch_model.bin','whisper/preprocessor_config.json','dwpose/dw-ll_ucoco_384.pth','face-parse-bisent/79999_iter.pth','face-parse-bisent/resnet18-5c106cde.pth']
CATALOGUE = [dict(id='ltx23-'+bits,nom='LTX-2.3 '+label,role='video',ram=ram,description='Clips et transitions · Apple Silicon · mode distilled',sources=[dict(repo='dgrauet/ltx-2.3-mlx'+suffix,include=VIDEO_FILES+['*.json','LICENSE*'],prefix='')],required=VIDEO_FILES) for bits,label,suffix,ram in [('q4','Q4','-q4',16),('q8','Q8','-q8',32),('bf16','BF16','',64)]]
CATALOGUE += [dict(id='gemma3',nom='Gemma 3 12B · 4 bits',role='texte',ram=0,description='Encodeur de texte partagé par les trois modèles LTX-2.3.',sources=[dict(repo='mlx-community/gemma-3-12b-it-4bit',include=['*.json','*.safetensors','*.model','LICENSE*'],prefix='')],required=['config.json','tokenizer.json','model.safetensors.index.json','model-00001-of-00002.safetensors','model-00002-of-00002.safetensors']),dict(id='musetalk15',nom='MuseTalk 1.5 · composants',role='lipsync',ram=0,description='Lipsync avec VAE, Whisper, DWPose et analyse du visage. Moteur Python à installer séparément.',required=MUSE_FILES,sources=[dict(repo='TMElyralab/MuseTalk',include=['musetalkV15/*','LICENSE*'],prefix=''),dict(repo='stabilityai/sd-vae-ft-mse',include=['config.json','diffusion_pytorch_model.bin'],prefix='sd-vae'),dict(repo='openai/whisper-tiny',include=['*.json','pytorch_model.bin'],prefix='whisper'),dict(repo='yzd-v/DWPose',include=['dw-ll_ucoco_384.pth'],prefix='dwpose'),dict(repo='ManyOtherFunctions/face-parse-bisent',include=['*.pth'],prefix='face-parse-bisent')])]

class SansFuiteToken(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        redirected=super().redirect_request(req,fp,code,msg,headers,newurl)
        if redirected and urllib.parse.urlparse(newurl).hostname!='huggingface.co': redirected.remove_header('Authorization')
        return redirected

def ouvrir(url,headers=None):
    h={'User-Agent':'StudioAvatar-model-manager/1',**(headers or {})}
    token=os.environ.get('HF_TOKEN')
    if token and urllib.parse.urlparse(url).hostname=='huggingface.co': h['Authorization']='Bearer '+token
    return urllib.request.build_opener(SansFuiteToken()).open(urllib.request.Request(url,headers=h),timeout=30)

def lire_json(path,default):
    try:return json.loads(path.read_text())
    except FileNotFoundError:return default

def atomique(path,data):
    path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2));tmp.replace(path)

def safe_path(root,name):
    p=PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or '\\' in name: raise ValueError('Chemin de modèle invalide')
    result=(root/name).resolve()
    if not result.is_relative_to(root.resolve()): raise ValueError('Chemin hors du dossier des modèles')
    return result

class Gestionnaire:
    def __init__(self,studio):
        self.s=studio; self.lock=threading.RLock(); self.cancel=threading.Event(); self.thread=None
        self.config_path=studio.ICI/'modeles.json'; self.etat_path=studio.ICI/'.modeles-etat.json'
        self.config=lire_json(self.config_path,dict(selection={'video':'ltx23-q4','texte':'gemma3','lipsync':'musetalk15'},locaux=[]))
        self.etat=lire_json(self.etat_path,{})
        if self.etat.get('statut') in ('analyse','telechargement','verification'): self.etat['statut']='interrompu'
        self.plans=lire_json(studio.ICI/'.modeles-plans.json',{})
        self.muse_root=Path(os.environ.get('STUDIO_MUSETALK_ROOT',str(getattr(studio,'MIMIC',studio.ICI)/'musetalk'))).expanduser().resolve()
    def entries(self):return CATALOGUE+self.config.get('locaux',[])
    def entry(self,mid):
        e=next((e for e in self.entries() if e['id']==mid),None)
        if not e:raise ValueError('Modèle inconnu')
        return e
    def target(self,e):
        if e.get('path'):return Path(e['path'])
        if e['id']=='musetalk15':return self.muse_root/'models'
        return self.s.MODELES/'catalogue'/e['id']
    def path(self,e):
        target=self.target(e)
        if self.valid(e,target):return target
        if e['id']=='ltx23-q4':
            ancien=self.s.MODELES/'ltx-2.3-q4'
            if self.valid(e,ancien):return ancien
        if e['id']=='gemma3':
            cache=self.s.MODELES/'huggingface'/'hub'/'models--mlx-community--gemma-3-12b-it-4bit'/'snapshots'
            for p in sorted(cache.glob('*')):
                if self.valid(e,p):return p
        return target
    def valid(self,e,path):return all((path/name).is_file() and (path/name).stat().st_size>0 for name in e['required'])
    def selection(self):
        with self.lock:
            out={}
            for role,mid in self.config['selection'].items():
                e=self.entry(mid); p=self.path(e)
                out[role]=dict(id=mid,path=str(p),installe=self.valid(e,p))
            if self.config.get('voix_engine'): out['voix'] = dict(id=self.config['voix_engine'])
            return out
    def catalogue(self):
        with self.lock:
            entries=[]
            for e in self.entries():
                p=self.path(e); plan=self.plans.get(e['id'])
                entries.append(dict(id=e['id'],nom=e['nom'],role=e['role'],ram=e['ram'],description=e['description'],path=str(p),installe=self.valid(e,p),actif=self.config['selection'].get(e['role'])==e['id'],octets=plan.get('total') if plan else None,sources=[s['repo'] for s in e.get('sources',[])],local=bool(e.get('path'))))
            return dict(catalogue=entries,selection=self.selection(),transfert=self.etat,voix_url=self.s.VOICESTUDIO,moteurs=dict(ltx=bool(shutil.which(str(self.s.LTX))),musetalk=self.muse_root.is_dir()),dossier=str(self.s.MODELES))
    def voix_catalogue(self):
        try:
            with urllib.request.urlopen(self.s.VOICESTUDIO+'/engines/tts',timeout=3) as r:data=json.load(r)
            return dict(ok=True,actif=self.config.get('voix_engine') or data.get('active'),modele=data.get('active_model'),engines=[{k:b.get(k) for k in ('id','display_name','available','reason','supports_cloning','supports_voice_design')} for b in data.get('backends',[])])
        except (OSError,ValueError):return dict(ok=False,engines=[])
    def choisir_voix(self,mid):
        with self.lock:
            if any(t['etat'] in ('en attente','en cours') for t in self.s.TACHES): raise ValueError('Terminez les tâches avant de changer de moteur de voix.')
            data=self.voix_catalogue()
            if not any(b['id']==mid and b['available'] for b in data['engines']):raise ValueError('Moteur indisponible dans VoiceStudio.')
            self.config['voix_engine']=mid;atomique(self.config_path,self.config)
    def choisir(self,mid):
        with self.lock:
            if any(t['etat'] in ('en attente','en cours') for t in self.s.TACHES):raise ValueError('Terminez ou annulez les tâches avant de changer de modèle.')
            e=self.entry(mid)
            if not self.valid(e,self.path(e)):raise ValueError('Installez ou importez ce modèle avant de l’activer.')
            self.config['selection'][e['role']]=mid;atomique(self.config_path,self.config)
    def importer(self,path,nom):
        with self.lock:
            p=Path(path).expanduser().resolve(); e=dict(id='local-'+hashlib.sha256(str(p).encode()).hexdigest()[:12],nom=nom or p.name,role='video',ram=0,description='Pack LTX-2.3 local importé ; aucune copie des poids.',required=VIDEO_FILES,path=str(p),sources=[])
            if not self.valid(e,p):raise ValueError('Pack incomplet : fichiers LTX distilled requis absents.')
            config=lire_json(p/'config.json',{})
            if not str(config.get('model_version','')).startswith('2.3'):raise ValueError('Seuls les packs LTX-2.3 sont compatibles avec cette recette.')
            self.config['locaux']=[x for x in self.config['locaux'] if x['id']!=e['id']]+[e];atomique(self.config_path,self.config)
    def maj(self,**kw):
        with self.lock:self.etat.update(kw);atomique(self.etat_path,self.etat)
    def analyser(self,e):
        files=[]
        for source in e['sources']:
            with ouvrir('https://huggingface.co/api/models/'+source['repo']+'?blobs=true') as r:info=json.load(r)
            revision=info['sha']
            for f in info['siblings']:
                name=f['rfilename']
                if not any(fnmatch.fnmatch(name,pat) for pat in source['include']):continue
                dest=str(PurePosixPath(source['prefix'])/name)
                safe_path(self.target(e),dest)
                files.append(dict(nom=dest,repo=source['repo'],revision=revision,source=name,taille=f['size'],sha256=(f.get('lfs') or {}).get('sha256'),git_sha=f.get('blobId')))
        names={x['nom'] for x in files}
        if not set(e['required']).issubset(names):raise ValueError('Le dépôt distant ne contient plus tous les fichiers requis. Catalogue à mettre à jour.')
        return dict(total=sum(f['taille'] for f in files),fichiers=files)
    def commencer(self,mid,installer=False):
        with self.lock:
            e=self.entry(mid)
            if not e.get('sources'):raise ValueError('Ce modèle local ne dispose pas de source de téléchargement.')
            if self.thread and self.thread.is_alive():raise ValueError('Un transfert est déjà en cours.')
            if installer and mid not in self.plans:raise ValueError('Vérifiez d’abord la taille du téléchargement.')
            if installer and any(t['etat'] in ('en attente','en cours') for t in self.s.TACHES): raise ValueError('Terminez les calculs avant d’installer des poids de modèles.')
            self.cancel.clear(); self.etat=dict(id=mid,statut='analyse' if not installer else 'telechargement',recu=0,total=0,fichier='',erreur='');atomique(self.etat_path,self.etat)
            self.thread=threading.Thread(target=self.travailler,args=(e,installer),daemon=True);self.thread.start()
    def travailler(self,e,installer):
        try:
            if not installer:
                plan=self.analyser(e)
                with self.lock:self.plans[e['id']]=plan;atomique(self.s.ICI/'.modeles-plans.json',self.plans)
                self.maj(statut='taille_disponible',total=plan['total']);return
            plan=self.plans[e['id']];root=self.target(e);root.mkdir(parents=True,exist_ok=True)
            # Files already in place need not be downloaded again.
            reste=sum(max(0,f['taille']-(safe_path(root,f['nom']).stat().st_size if safe_path(root,f['nom']).is_file() and safe_path(root,f['nom']).stat().st_size==f['taille'] else (safe_path(root,f['nom']+'.part').stat().st_size if safe_path(root,f['nom']+'.part').exists() else 0))) for f in plan['fichiers'])
            if shutil.disk_usage(root).free<reste+256*1024**2:raise ValueError('Espace disque insuffisant pour ce téléchargement.')
            done=0;self.maj(total=plan['total'])
            for f in plan['fichiers']:
                if self.cancel.is_set():raise InterruptedError('Téléchargement annulé ; les fragments sont conservés pour la reprise.')
                self.telecharger(root,f,done);done+=f['taille'];self.maj(recu=done)
            atomique(root/('.studio-'+e['id']+'.json'),plan)
            self.maj(statut='installe',fichier='')
        except InterruptedError as exc:self.maj(statut='interrompu',erreur=str(exc))
        except urllib.error.HTTPError as exc:self.maj(statut='erreur',erreur=f'HTTP {exc.code} : accès refusé ou dépôt indisponible. Si nécessaire, acceptez la licence sur Hugging Face puis configurez HF_TOKEN dans votre environnement.')
        except Exception as exc:self.maj(statut='erreur',erreur=str(exc))
    def verifier(self,path,f):
        if path.stat().st_size!=f['taille']:return False
        if f.get('sha256'):h=hashlib.sha256();expected=f['sha256']
        elif f.get('git_sha'):
            h=hashlib.sha1();h.update(f"blob {f['taille']}\0".encode());expected=f['git_sha']
        else:raise ValueError('Empreinte de fichier absente du manifeste distant.')
        with path.open('rb') as stream:
            while chunk:=stream.read(4*1024**2):
                if self.cancel.is_set():raise InterruptedError('Vérification annulée ; reprise disponible.')
                h.update(chunk)
        return h.hexdigest()==expected
    def telecharger(self,root,f,done):
        target=safe_path(root,f['nom']);part=safe_path(root,f['nom']+'.part');target.parent.mkdir(parents=True,exist_ok=True)
        self.maj(fichier=f['nom'],statut='verification')
        if target.exists() and self.verifier(target,f):return
        offset=part.stat().st_size if part.exists() else 0
        if offset>f['taille']:part.unlink();offset=0
        url='https://huggingface.co/'+f['repo']+'/resolve/'+f['revision']+'/'+urllib.parse.quote(f['source'],safe='/')
        if offset<f['taille']:
            headers={'Range':f'bytes={offset}-'} if offset else {}
            with ouvrir(url,headers) as r:
                if offset and (r.status!=206 or not r.headers.get('Content-Range','').startswith(f'bytes {offset}-')):offset=0
                self.maj(statut='telechargement',recu=done+offset)
                last=0
                with part.open('ab' if offset else 'wb') as stream:
                    while chunk:=r.read(1024**2):
                        if self.cancel.is_set():raise InterruptedError('Téléchargement annulé ; reprise disponible.')
                        stream.write(chunk);offset+=len(chunk)
                        if time.monotonic()-last>.5:self.maj(recu=done+offset);last=time.monotonic()
        if f['taille']==0: part.touch(exist_ok=True)
        self.maj(statut='verification')
        if not self.verifier(part,f):part.unlink(missing_ok=True);raise ValueError('Fichier corrompu ou incomplet : relancez le téléchargement.')
        part.replace(target)
