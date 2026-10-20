"""CPU-only, cached rush previews using the same frame boundaries as export."""
import hashlib
import json
import subprocess
import threading
from pathlib import Path

ETATS = {}
VERROU = threading.RLock()

def installer(studio):
    global S
    S = studio

def elements(p):
    out=[]
    for i,b in enumerate(p['blocs']):
        out.append(dict(b,role='clip',pret=S.projets.courant(b)))
        if i<len(p['transitions']):
            tr=p['transitions'][i];out.append(dict(tr,role='transition',pret=S.projets.pont_pret(p,tr)))
    return out

def planifier(p,jonction=None):
    tous=elements(p)
    if jonction:
        i=next((i for i,b in enumerate(tous) if b['id']==jonction and b['role']=='transition'),None)
        if i is None: raise ValueError('Transition introuvable.')
        selection=tous[i-1:i+2]
        if not all(b['pret'] for b in selection): raise ValueError('Générez les deux clips et leur transition avant de lire cette jonction.')
    else:
        selection=[]
        for b in tous:
            if not b['pret']:break
            selection.append(b)
        # A transition without the following clip does not allow assessing a join.
        if selection and selection[-1]['role']=='transition':selection.pop()
        if not selection:raise ValueError('Générez au moins le premier clip pour prévisualiser la timeline.')
    morceaux=[]
    for b in selection:
        n=max(1,round(b['duree']*24))
        if b['role']=='clip': dossier,a,z='clips',0,n
        else:dossier,a,z='ponts',1,S.images_ltx(n+2)-1
        f=S.ICI/dossier/b['clip']
        if not f.is_file():raise ValueError('Un rush est absent du disque : régénérez cet élément.')
        morceaux.append(dict(id=b['id'],role=b['role'],nom=b.get('ton','Transition'),fichier=str(f),debut_frame=a,fin_frame=z,duree=n/24,audio=str(S.ICI/'audios'/b['audio']) if b.get('audio') and (S.ICI/'audios'/b['audio']).is_file() else None,version=f.stat().st_mtime_ns))
    signature=hashlib.sha256(json.dumps(morceaux,sort_keys=True).encode()).hexdigest()[:16]
    return dict(morceaux=morceaux,signature=signature,partiel=not jonction and len(selection)<len(tous),nombre=len(selection),total=len(tous),revision=p['revision'],jonction=jonction,duree=sum(m['duree'] for m in morceaux))

def etat(pid):
    with VERROU:return dict(ETATS.get(pid,dict(statut='absent')))

def demander(pid,jonction=None):
    with VERROU:
        if ETATS.get(pid,{}).get('statut')=='en cours':return etat(pid)
        p=S.projets.lire(pid);plan=planifier(p,jonction)
        nom=f".apercu-{pid}-{plan['signature']}.mp4"
        status={k:v for k,v in plan.items() if k!='morceaux'}
        temps=0;status['chapitres']=[]
        for m in plan['morceaux']:
            status['chapitres'].append(dict(id=m['id'],role=m['role'],debut=temps,fin=temps+m['duree']))
            temps+=m['duree']
        status.update(fichier=nom,statut='pret' if (S.ICI/'sequences'/nom).exists() else 'en cours')
        ETATS[pid]=status
        if status['statut']=='en cours':threading.Thread(target=construire,args=(pid,plan,nom),daemon=True).start()
        return etat(pid)

def construire(pid,plan,nom):
    out=S.ICI/'sequences'/nom;tmp=out.with_suffix('.tmp.mp4')
    try:
        args,flt=[],[];morceaux=plan['morceaux'];W,H=S.taille_image(Path(morceaux[0]['fichier']))
        # Lower resolution only: framing, timing, anchor trimming and audio match export.
        ratio=min(1,480/W,640/H);W=max(2,round(W*ratio/2)*2);H=max(2,round(H*ratio/2)*2)
        for k,m in enumerate(morceaux):
            args+=['-i',m['fichier']]
            a,z,d=m['debut_frame'],m['fin_frame'],m['duree']
            flt.append(f'[{k}:v]trim=start_frame={a}:end_frame={z},setpts=(PTS-STARTPTS)*{d*24/(z-a):.9f},fps=24,scale={W}:{H},setsar=1[v{k}]')
        offset=len(morceaux)
        for k,m in enumerate(morceaux):
            d=m['duree']
            args+=['-i',m['audio']] if m['audio'] else ['-f','lavfi','-t',str(d),'-i','anullsrc=r=44100:cl=mono']
            flt.append(f'[{offset+k}:a]aresample=44100,aformat=channel_layouts=mono,apad,atrim=duration={d:.9f},asetpts=PTS-STARTPTS[a{k}]')
        flt.append(''.join(f'[v{k}][a{k}]' for k in range(len(morceaux)))+f'concat=n={len(morceaux)}:v=1:a=1[v][a]')
        # Do not use studio.lancer: preview CPU work must never replace the GPU process handle.
        cmd=['ffmpeg','-v','error','-y',*args,'-filter_complex_threads','1','-filter_complex',';'.join(flt),'-map','[v]','-map','[a]','-c:v','libx264','-threads','2','-preset','veryfast','-crf','23','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart',str(tmp)]
        result=subprocess.run(cmd,capture_output=True,text=True)
        if result.returncode:
            out.with_suffix('.log').write_text(result.stderr)
            raise RuntimeError('La prévisualisation a échoué. Vérifiez les rushs et FFmpeg.')
        tmp.replace(out)
        with VERROU:ETATS[pid]['statut']='pret'
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        with VERROU:ETATS[pid].update(statut='erreur',erreur=str(exc))
