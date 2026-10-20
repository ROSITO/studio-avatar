"""Shared frame/audio edit decisions for integrated return-to-pose joins."""
from pathlib import Path

VERSION = 2
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
            r=raccord(p,b);dossier,a,z,d,audio,offset='ponts',1,studio.images_ltx(r['frames']+2)-1,r['duree'],blocs[b['gauche']].get('audio'),r['coupe']/FPS
        f=studio.ICI/dossier/b['clip']
        if not f.is_file():raise ValueError('Un rush est absent du disque : régénérez cet élément.')
        son=studio.ICI/'audios'/audio if audio else None
        out.append(dict(id=b['id'],role=b['role'],nom=b.get('ton','Retour à la pose'),fichier=str(f),debut_frame=a,fin_frame=z,duree=d,audio=str(son) if son and son.is_file() else None,audio_debut=offset,version=f.stat().st_mtime_ns,montage_version=VERSION))
    return out
