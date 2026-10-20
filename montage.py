"""Shared frame/audio edit decisions for integrated return-to-pose joins."""
from pathlib import Path

VERSION = 3
FPS = 24

def frames_blocs(p):
    """Cumulative rounding keeps the whole timeline within one frame of speech."""
    out={};cum=0.;avant=0
    for b in p['blocs']:
        cum+=b['duree'];fin=round(cum*FPS)
        out[b['id']]=max(1,fin-avant);avant=fin
    return out

def raccord(p,tr):
    counts=frames_blocs(p);n=counts[tr['gauche']]
    if n<2:raise ValueError('Le bloc précédent est trop court pour contenir un raccord.')
    analyse=tr.get('analyse_pose',{})
    sources=[b.get('clip') for b in p['blocs'] if b['id'] in (tr['gauche'],tr.get('droite'))]
    if (analyse.get('version')==VERSION and analyse.get('sources')==sources
            and analyse.get('revision')==tr.get('revision') and analyse.get('total')==n):
        retour=analyse['frames']
    else:
        retour=min(max(1,round(tr['duree']*FPS)),n-1)
    return dict(coupe=n-retour,frames=retour,duree=retour/FPS)

def morceaux(studio,p,selection=None):
    """Return video cuts AND the exact source speech slice for every image range.

    A bridge replaces the end of its left block. It adds no time and carries
    that block's speech. A partial preview's last clip can play untrimmed when
    its outgoing bridge is not yet available.
    """
    if selection is None:
        selection=[]
        for i,b in enumerate(p['blocs']):
            selection.append(dict(b,role='clip'))
            if i<len(p['transitions']):selection.append(dict(p['transitions'][i],role='transition'))
    ids={b['id'] for b in selection};counts=frames_blocs(p)
    blocs={b['id']:b for b in p['blocs']}
    sortantes={t['gauche']:t for t in p['transitions'] if t['id'] in ids}
    out=[]
    for b in selection:
        if b['role']=='clip':
            tr=sortantes.get(b['id']);n=raccord(p,tr)['coupe'] if tr else counts[b['id']]
            dossier,a,z,d,audio,offset='clips',0,n,n/FPS,b.get('audio'),0
        else:
            if raccord(p,b)['frames']==0:continue
            r=raccord(p,b);dossier,a,z,d,audio,offset='ponts',1,studio.images_ltx(r['frames']+2)-1,r['duree'],blocs[b['gauche']].get('audio'),r['coupe']/FPS
        f=studio.ICI/dossier/b['clip']
        if not f.is_file():raise ValueError('Un rush est absent du disque : régénérez cet élément.')
        son=studio.ICI/'audios'/audio if audio else None
        out.append(dict(id=b['id'],role=b['role'],nom=b.get('ton','Retour à la pose'),fichier=str(f),debut_frame=a,fin_frame=z,duree=d,audio=str(son) if son and son.is_file() else None,audio_debut=offset,version=f.stat().st_mtime_ns,montage_version=VERSION))
    return out


def choisir_pose(images, cible, total, souhait):
    """Compare central body thumbnails; return a native LTX duration (8k-1).

    Whole-image similarity is only a conservative visual proxy, not a skeleton
    estimator. A direct cut is reserved for practically identical thumbnails.
    """
    def distance(a,b):return sum(abs(x-y) for x,y in zip(a,b))/(255*len(a))
    if len(images)<total or not cible:raise ValueError('Analyse des images du rush incomplète.')
    fin=distance(images[total-1],cible)
    if fin<0.008 and distance(images[total-2],images[total-1])<0.005:
        return dict(frames=0,score=fin,mode='coupe')
    candidats=[]
    for frames in range(7,min(total-1,31)+1,8):
        i=total-frames-1
        ecart=distance(images[i],cible)
        vitesse=distance(images[max(0,i-1)],images[i])*FPS
        # Penalize rapid returns, motion at the cut, and needlessly long joins.
        score=ecart/(frames/FPS)+0.15*vitesse+0.025*abs(frames/FPS-souhait)
        candidats.append((score,frames,ecart))
    if not candidats:raise ValueError('Bloc trop court pour analyser un retour naturel.')
    _,frames,ecart=min(candidats)
    return dict(frames=frames,score=ecart,mode='ltx')

def analyser(studio,t,p,tr):
    blocs={b['id']:b for b in p['blocs']};a=blocs[tr['gauche']];z=blocs[tr['droite']]
    total=frames_blocs(p)[a['id']];taille=48*64*3
    fichiers=[]
    try:
        for nom,b,nb in [('poses',a,total),('cible',z,1)]:
            dest=studio.ICI/'ponts'/f"{t['id']}-{nom}.rgb";fichiers.append(dest)
            studio.lancer(t,['ffmpeg','-v','error','-y','-i',studio.ICI/'clips'/b['clip'],
                '-vf','fps=24,crop=iw*0.7:ih:iw*0.15:0,scale=48:64',
                '-frames:v',nb,'-pix_fmt','rgb24','-f','rawvideo',dest])
        data=fichiers[0].read_bytes();cible=fichiers[1].read_bytes()
        decision=choisir_pose([data[i:i+taille] for i in range(0,len(data),taille)],cible,total,tr['duree'])
        decision.update(version=VERSION,sources=[a['clip'],z['clip']],revision=tr['revision'],total=total)
        return decision
    finally:
        for f in fichiers:f.unlink(missing_ok=True)
