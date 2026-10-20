"""Projets persistants : blocs TAG et transitions LTX indépendants."""
import json, math, secrets, threading, time, uuid
import montage
from pathlib import Path


def installer(studio):
    global S, RACINE
    S = studio
    RACINE = S.ICI / 'projets'
    RACINE.mkdir(exist_ok=True)

VERROU = threading.RLock()

def ident(): return uuid.uuid4().hex[:12]
def lire(pid):
    if not isinstance(pid, str) or not pid.isalnum(): raise ValueError('Projet invalide')
    f = RACINE / (pid + '.json')
    if not f.exists(): raise ValueError('Projet introuvable')
    p=json.loads(f.read_text())
    if p.get('montage_version',1)<montage.VERSION:
        p['montage_version']=montage.VERSION
        p['revision']+=1  # Old exports/preview revisions must not look current.
    return p
def sauver(p):
    p['modifie'] = time.time()
    f = RACINE / (p['id'] + '.json'); tmp = f.with_suffix('.tmp')
    tmp.write_text(json.dumps(p, ensure_ascii=False, indent=2)); tmp.replace(f)
def liste():
    with VERROU:
        return sorted([lire(f.stem) for f in RACINE.glob('*.json')], key=lambda p: -p['modifie'])
def actif(pid):
    return any(t['type'].startswith('projet_') and t['params'].get('projet') == pid and t['etat'] in ('en attente', 'en cours') for t in S.TACHES)
def seed_aleatoire(): return secrets.randbelow(2**31)

def bloc(ton='neutre', texte=''):
    cle = next(gs[0] for k, *_, gs in S.TONS if k == ton)
    return dict(id=ident(), ton=ton, texte=texte, prompt=S.GESTES[cle], duree=max(1.4, len(texte)/14), seed=seed_aleatoire(), seed_mode='auto', revision=0, clip=None, audio=None)
def relier(p):
    anciens = {(x['gauche'],x['droite']):x for x in p.get('transitions',[])}
    p['transitions'] = [anciens.get((a['id'],b['id'])) or dict(id=ident(),gauche=a['id'],droite=b['id'],duree=0.5,seed=seed_aleatoire(),seed_mode='auto',revision=0,clip=None) for a,b in zip(p['blocs'],p['blocs'][1:])]
def courant(b): return bool(b.get('clip') and b.get('rendu_revision') == b['revision'])
def pont_pret(p,b):
    a,z = [next(x for x in p['blocs'] if x['id']==b[k]) for k in ('gauche','droite')]
    r=montage.raccord(p,b)
    return courant(a) and courant(z) and courant(b) and b.get('extremites') == [a['clip'],z['clip']] and b.get('raccord_version')==montage.VERSION and b.get('coupe_frame')==r['coupe'] and b.get('frames_cible')==r['frames']
def creer(d):
    avatar=d.get('avatar','')
    if '/' in avatar or not (S.ICI/'sources'/avatar).is_file(): raise ValueError('Photo introuvable')
    if d.get('audio') and ('/' in d['audio'] or not (S.ICI/'audios'/d['audio']).is_file()): raise ValueError('Audio introuvable')
    p=dict(id=ident(),nom=d.get('nom') or 'Nouveau projet',avatar=avatar,voix=d.get('voix'),langue=d.get('langue','fr'),audio_source=d.get('audio'),blocs=[],transitions=[],revision=0,export=None,montage_version=montage.VERSION)
    # Une balise reconnue ouvre un bloc ; la ponctuation ne le découpe jamais.
    import re
    ton='neutre'; texte=''
    for morceau in re.split(r'(\[[^\]]+\])',d.get('texte','')):
        tag=re.fullmatch(r'\[([^\]]+)\]',morceau.strip())
        nouveau=S.BALISES.get(tag[1].strip().lower()) if tag else None
        if nouveau:
            if texte.strip(): p['blocs'].append(bloc(ton,' '.join(texte.split())))
            ton=nouveau; texte=''
        elif not tag: texte+=morceau
    if texte.strip(): p['blocs'].append(bloc(ton,' '.join(texte.split())))
    if not p['blocs']: p['blocs']=[bloc()]
    if p['audio_source']:
        total=S.duree(S.ICI/'audios'/p['audio_source']); n=sum(len(b['texte']) for b in p['blocs']) or 1; debut=0
        for b in p['blocs']:
            b['audio_debut']=debut; b['duree']=total*len(b['texte'])/n if b['texte'] else total/len(p['blocs']); b['audio_duree']=b['duree']; debut+=b['duree']
    relier(p)
    with VERROU: sauver(p)
    return p

def modifier(pid,d):
    with VERROU:
        p=lire(pid)
        if actif(pid): raise ValueError('Attendez la fin des tâches de ce projet avant de le modifier.')
        action=d.get('action')
        if action=='ajouter':
            if p['audio_source']: raise ValueError('Créez un projet texte pour ajouter des blocs ; les blocs audio sont liés au fichier importé.')
            p['blocs'].append(bloc())
        else:
            x=next((b for b in p['blocs']+p['transitions'] if b['id']==d.get('element')),None)
            if not x: raise ValueError('Élément introuvable')
            if action=='supprimer':
                if x not in p['blocs'] or len(p['blocs'])==1: raise ValueError('Le projet doit garder au moins un bloc.')
                p['blocs'].remove(x)  # fichiers conservés, suppression du montage uniquement
            elif action=='deplacer':
                i=p['blocs'].index(x); j=i+int(d.get('sens',0))
                if 0<=j<len(p['blocs']): p['blocs'][i],p['blocs'][j]=p['blocs'][j],p['blocs'][i]
            elif action=='modifier':
                changements={}
                for k in ('texte','prompt','ton','duree','seed','seed_mode'):
                    if k not in d or (k not in x and k!='seed_mode'): continue
                    v=d[k]
                    if k=='duree':
                        v=float(v)
                        if not math.isfinite(v) or not .5<=v<=20: raise ValueError('Durée : entre 0,5 et 20 secondes.')
                    if k=='seed':
                        if isinstance(v,bool) or not math.isfinite(float(v)) or float(v)!=int(v): raise ValueError('La seed doit être un entier.')
                        v=int(v)
                        if not 0<=v<2**31: raise ValueError('Seed : entier entre 0 et 2147483647.')
                    if k=='seed_mode' and v not in ('auto','manuel'): raise ValueError('Mode de seed invalide')
                    if k=='ton' and v not in [a[0] for a in S.TONS]: raise ValueError('TAG inconnu')
                    if v!=x.get(k, 'auto' if k=='seed_mode' else None): changements[k]=v
                if changements:
                    if 'texte' in changements:
                        if p['audio_source']: raise ValueError('Le texte ne peut pas modifier un audio importé.')
                        x['audio']=None
                    x.update(changements); x['revision']+=1
            else: raise ValueError('Action inconnue')
        relier(p); p['revision']+=1; sauver(p); return p

def ajouter_tache(p,genre,e=None):
    params=dict(projet=p['id'],element=e['id'] if e else None)
    if any(t['type']=='projet_'+genre and t['params']==params and t['etat'] in ('en attente','en cours') for t in S.TACHES): return
    S.TACHES.append(dict(id=ident(),type='projet_'+genre,params=params,modeles=S.GESTION_MODELES.selection(),etat='en attente',cree=time.time()))
def lancer(pid,d):
    with VERROU:
        p=lire(pid); action=d['action']
        if action=='automatique':
            if actif(pid): return p
            if not p['audio_source'] and (not p.get('voix') or any(not b['texte'].strip() for b in p['blocs'])): raise ValueError('Complétez le texte de tous les blocs et choisissez une voix avant le lancement automatique.')
            ajouter_tache(p,'auto')
        elif action=='manquants':
            for b in p['blocs']:
                if not courant(b): ajouter_tache(p,'clip',b)
            # Les transitions attendent leurs deux clips dans la même file séquentielle.
            for b in p['transitions']:
                if not pont_pret(p,b): ajouter_tache(p,'pont',b)
        elif action in ('clip','pont'):
            b=next((b for b in p['blocs' if action=='clip' else 'transitions'] if b['id']==d.get('element')),None)
            if not b: raise ValueError('Élément introuvable')
            if action=='pont' and not all(courant(x) for x in p['blocs'] if x['id'] in (b['gauche'],b['droite'])): raise ValueError('Générez les deux clips voisins avant leur transition.')
            if any(t['type']=='projet_'+action and t['params'].get('projet')==pid and t['params'].get('element')==b['id'] and t['etat'] in ('en attente','en cours') for t in S.TACHES): return p
            # Invalider immédiatement les ponts adjacents, même si la génération échoue.
            b['revision']+=1
            p['revision']+=1; sauver(p); ajouter_tache(p,action,b)
        elif action=='export':
            if actif(pid): raise ValueError('Attendez la fin des générations avant d’assembler.')
            if not all(courant(b) for b in p['blocs']) or not all(pont_pret(p,b) for b in p['transitions']): raise ValueError('Des clips ou transitions restent à générer.')
            ajouter_tache(p,'export')
        else: raise ValueError('Action inconnue')
        S.sauver(); return p

def executer(t):
    pid=t['params']['projet']; p=lire(pid); genre=t['type'][7:]
    if genre=='auto': automatique(t,p); return
    x=next((b for b in p['blocs']+p['transitions'] if b['id']==t['params'].get('element')),None)
    suffix=f"projet-{pid}-{t.get('generation_id', t['id'])}"
    # Une sortie déjà validée avant l’arrêt du serveur ne repasse pas dans LTX.
    if x and x.get('clip') == suffix+'.mp4' and (courant(x) if genre=='clip' else pont_pret(p,x)): return
    if genre in ('clip','pont'):
        if not x: raise ValueError('Élément supprimé')
        # Persist the drawn seed on the task BEFORE inference: restart/retry uses
        # the same draw, while a new regeneration gets a new random draw.
        if 'seed_effective' not in t:
            t['seed_effective'] = seed_aleatoire() if x.get('seed_mode','auto')=='auto' else x['seed']
            S.sauver()
        x['seed'] = t['seed_effective']
    if genre=='clip':
        if not x: raise ValueError('Bloc supprimé')
        audio=S.ICI/'audios'/f'{suffix}.wav'
        if not x.get('audio'):
            t['etape']='Audio du bloc'; S.sauver()
            if p['audio_source']:
                S.lancer(t,['ffmpeg','-v','error','-y','-ss',x['audio_debut'],'-i',S.ICI/'audios'/p['audio_source'],'-t',x['audio_duree'],'-ar','44100','-ac','1',audio])
            else:
                if not x['texte'].strip() or not p['voix']: raise ValueError('Texte et voix nécessaires pour ce bloc.')
                S.voix(t,x['texte'],p['voix'],p['langue'],audio)
            x['audio']=audio.name; x['duree']=max(.5,S.duree(audio))
            with VERROU: sauver(p)  # checkpoint conservé si LTX échoue
        W,H=S.resolution(S.ICI/'sources'/p['avatar']); out=S.ICI/'clips'/f'{suffix}.mp4'
        t['etape']='Mini-clip LTX'; S.sauver()
        S.ltx(t,[(S.ICI/'sources'/p['avatar'],0)],S.BASE_CLIP+' '+x['prompt'],W,H,S.images_ltx(math.ceil(x['duree']*24)),x['seed'],out)
        S.lancer(t,['ffmpeg','-v','error','-y','-i',out,'-frames:v','1','-vf','scale=320:-2',out.with_suffix('.jpg')])
        x['clip']=out.name; x['rendu_revision']=x['revision']
    elif genre=='pont':
        a,z=[next(b for b in p['blocs'] if b['id']==x[k]) for k in ('gauche','droite')]
        if not courant(a) or not courant(z): raise ValueError('Les deux clips voisins doivent être prêts.')
        premiere=S.ICI/'ponts'/f'{suffix}-debut.png'; derniere=S.ICI/'ponts'/f'{suffix}-fin.png'
        # Dernière image réellement retenue au montage (le clip LTX peut dépasser la durée du bloc).
        retour=montage.raccord(p,x);n=retour['coupe']
        S.lancer(t,['ffmpeg','-v','error','-y','-i',S.ICI/'clips'/a['clip'],'-vf',f'select=eq(n\\,{n-1})','-frames:v','1','-update','1',premiere])
        S.lancer(t,['ffmpeg','-v','error','-y','-i',S.ICI/'clips'/z['clip'],'-frames:v','1','-update','1',derniere])
        W,H=S.taille_image(S.ICI/'clips'/a['clip']); out=S.ICI/'ponts'/f'{suffix}.mp4'
        t['etape']='Retour intégré à la pose commune'; S.sauver()
        prompt='The same person smoothly moves from the first pose to the final pose. Mouth closed. Natural gentle motion, consistent face, clothing and background. Static camera.'
        S.ltx(t,[(premiere,0),(derniere,'last')],prompt,W,H,S.images_ltx(retour['frames']+2),x['seed'],out)
        S.lancer(t,['ffmpeg','-v','error','-y','-i',out,'-frames:v','1','-vf','scale=320:-2',out.with_suffix('.jpg')])
        x['clip']=out.name; x['rendu_revision']=x['revision']; x['extremites']=[a['clip'],z['clip']]
        x.update(raccord_version=montage.VERSION,coupe_frame=retour['coupe'],frames_cible=retour['frames'])
    else:
        exporter(t,p); return
    if t.get('annuler'): raise RuntimeError('Tâche annulée')
    x['modele'] = (t.get('modeles') or S.GESTION_MODELES.selection())['video']['id']
    p['revision'] += 1  # New rushes also invalidate older partial previews/exports.
    with VERROU: sauver(p)
    t['resultat']=dict(projet=pid,element=x['id'],fichier=x['clip'])

def automatique(t,p):
    """One resumable orchestration task, no dependent jobs left queued on failure."""
    pid=p['id']; etapes=[]
    for i,b in enumerate(p['blocs']):
        etapes.append(('clip',b['id']))
        if i: etapes.append(('pont',p['transitions'][i-1]['id']))
    etapes.append(('export',None))
    class SousTache(dict):
        def __setitem__(self,key,value):
            super().__setitem__(key,value)
            if key=='etape':
                t['etape']=f"Automatique {numero+1}/{len(etapes)} · {value}"
            if key=='seed_effective':
                t.setdefault('seeds',{})[element]=value
        def get(self,key,default=None):
            if key=='annuler': return t.get('annuler',False)
            return super().get(key,default)
    for numero,(genre,element) in enumerate(etapes):
        if t.get('annuler'): raise RuntimeError('Génération automatique annulée')
        p=lire(pid)
        x=next((x for x in p['blocs']+p['transitions'] if x['id']==element),None)
        pret=courant(x) if genre=='clip' else pont_pret(p,x) if genre=='pont' else bool(p.get('export') and p['export']['revision']==p['revision'] and p['export'].get('montage_version')==montage.VERSION and (S.ICI/'videos'/p['export']['fichier']).is_file())
        t['automatique']=dict(faits=numero,total=len(etapes));S.sauver()
        if pret: continue
        child=SousTache(id=t['id'],type='projet_'+genre,params=dict(projet=pid,element=element),generation_id=t['id']+'-'+str(element),modeles=t.get('modeles') or S.GESTION_MODELES.selection())
        if element in t.get('seeds',{}):dict.__setitem__(child,'seed_effective',t['seeds'][element])
        executer(child)
    t['automatique']=dict(faits=len(etapes),total=len(etapes));t['resultat']=dict(projet=pid,export=lire(pid)['export']);S.sauver()


def exporter(t,p):
    if not all(courant(b) for b in p['blocs']) or not all(pont_pret(p,b) for b in p['transitions']): raise ValueError('Timeline incomplète')
    suffix=f"projet-{p['id']}-{t['id']}"; seq=S.ICI/'sequences'/f'{suffix}.mp4'; audio=S.ICI/'audios'/f'{suffix}.wav'
    plan=montage.morceaux(S,p)
    if any(not m['audio'] for m in plan): raise ValueError('Un audio de bloc est absent du disque.')
    args=['ffmpeg','-v','error','-y'];vf=[];af=[]
    W,H=S.taille_image(Path(plan[0]['fichier']))
    for k,m in enumerate(plan):
        args+=['-i',m['fichier']]
        a,z,d=m['debut_frame'],m['fin_frame'],m['duree']
        vf.append(f'[{k}:v]trim=start_frame={a}:end_frame={z},setpts=(PTS-STARTPTS)*{d*24/(z-a):.9f},fps=24,scale={W}:{H},setsar=1[v{k}]')
    vf.append(''.join(f'[v{k}]' for k in range(len(plan)))+f'concat=n={len(plan)}:v=1:a=0[o]')
    t['etape']='Assemblage de la timeline'; S.sauver()
    S.lancer(t,args+['-filter_complex',';'.join(vf),'-map','[o]','-c:v','libx264','-pix_fmt','yuv420p',seq])
    args=['ffmpeg','-v','error','-y']
    for k,m in enumerate(plan):
        d=m['duree'];args+=['-ss',str(m['audio_debut']),'-i',m['audio']]
        af.append(f'[{k}:a]aresample=44100,aformat=channel_layouts=mono,apad,atrim=duration={d:.9f},asetpts=PTS-STARTPTS[a{k}]')
    af.append(''.join(f'[a{k}]' for k in range(len(plan)))+f'concat=n={len(plan)}:v=0:a=1[o]')
    S.lancer(t,args+['-filter_complex',';'.join(af),'-map','[o]',audio])
    out=S.ICI/'videos'/f'{suffix}.mp4'; t['etape']='Synchronisation des lèvres'; S.sauver()
    S.musetalk(t,seq,audio,out,0)
    if t.get('annuler'): raise RuntimeError('Tâche annulée')
    p['export']=dict(fichier=out.name,revision=p['revision'],montage_version=montage.VERSION); sauver(p)
    t['resultat']=S.meta(out,projet=p['id'],nom=p['nom'],avatar=p['avatar'])
