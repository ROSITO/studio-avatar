"""Persistent reference-prefix cache, never a cache of the requested speech."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import time
import uuid

VERSION=1

def cle(requete):
    modele=Path(requete['modele']).resolve()
    fichiers=[(str(p.relative_to(modele)),p.stat().st_size,p.stat().st_mtime_ns)
              for p in sorted(modele.rglob('*')) if p.is_file() and not any(x.startswith('.') for x in p.relative_to(modele).parts)]
    h=hashlib.sha256(Path(requete['reference']).read_bytes())
    contenu=dict(version=VERSION,modele=str(modele),fichiers=fichiers,
        transcription=requete['transcription'],audio=h.hexdigest(),
        runtime=[importlib.metadata.version(x) for x in ('mlx','mlx-audio')],
        adaptateur=hashlib.sha256(Path(__file__).with_name('drama_memoire.py').read_bytes()).hexdigest())
    return hashlib.sha256(json.dumps(contenu,sort_keys=True).encode()).hexdigest()

def sauver(mx,path,voice,system_rows):
    tableaux={};groupes=[]
    for gi,groupe in enumerate(voice.prefix):
        objets=[]
        for ci,c in enumerate(groupe):
            if type(c).__name__ not in ('KVCache','ArraysCache'):raise ValueError('Type de cache non pris en charge')
            etat=[]
            for ai,v in enumerate(c.state):
                nom=f'{gi}.{ci}.{ai}' if v is not None else None
                if nom is not None:tableaux[nom]=v
                etat.append(nom)
            objets.append(dict(type=type(c).__name__,etat=etat,meta=c.meta_state))
        groupes.append(objets)
    for i,(_,codes) in enumerate(voice.references):tableaux[f'reference.{i}']=codes
    info=dict(version=VERSION,groupes=groupes,system_rows=system_rows,references=[t for t,_ in voice.references])
    tmp=path.with_name(path.stem+'-'+uuid.uuid4().hex+'.tmp.safetensors')
    try:
        mx.save_safetensors(str(tmp),tableaux,metadata={'studio':json.dumps(info)})
        tmp.replace(path)
    finally:tmp.unlink(missing_ok=True)

def charger(mx,path,voice,system_rows,tailles):
    from mlx_audio.lm.models.cache import KVCache,ArraysCache
    types={'KVCache':KVCache,'ArraysCache':ArraysCache}
    tableaux,metadata=mx.load(str(path),return_metadata=True)
    info=json.loads(metadata['studio'])
    if info['version']!=VERSION or info['system_rows']!=system_rows:raise ValueError('Préparation incompatible')
    if info['references']!=[t for t,_ in voice.references]:raise ValueError('Transcription différente')
    if [len(g) for g in info['groupes']]!=list(tailles):raise ValueError('Architecture différente')
    for i,(_,codes) in enumerate(voice.references):
        if not mx.array_equal(tableaux[f'reference.{i}'],codes).item():raise ValueError('Référence encodée différente')
    return tuple([types[o['type']].from_state([tableaux[n] if n is not None else None for n in o['etat']],o['meta']) for o in g] for g in info['groupes'])

def installer(mx,modele,requete):
    if os.environ.get('STUDIO_DRAMA_CACHE','1')=='0':return
    try:
        dossier=Path(requete['modele'])/'.studio-avatar-cache';dossier.mkdir(exist_ok=True)
        path=dossier/(cle(requete)+'.safetensors')
    except (OSError,ValueError) as exc:
        print('Cache vocal indisponible : '+str(exc),flush=True);return
    origine=modele._start_caches
    tailles=(len(modele.backbone.make_cache()),len(modele.tower.make_cache()))
    def commencer(frames,system_rows,voice):
        if voice.prefix is None and path.is_file():
            debut=time.perf_counter()
            try:
                voice.prefix=charger(mx,path,voice,system_rows,tailles)
                path.touch()
                print(f'Référence vocale réutilisée depuis le T7 ({time.perf_counter()-debut:.2f} s)',flush=True)
            except (OSError,ValueError,KeyError,RuntimeError,TypeError) as exc:
                voice.prefix=None;print('Cache vocal ignoré : '+str(exc),flush=True)
        absent=voice.prefix is None
        resultat=origine(frames,system_rows,voice)
        if absent:
            try:
                sauver(mx,path,voice,system_rows)
                # At most 2 GiB, retaining the entry just created.
                autres=sorted((p for p in dossier.glob('*.safetensors') if p!=path and '.tmp.' not in p.name),key=lambda p:p.stat().st_mtime,reverse=True)
                total=path.stat().st_size
                if total>2*1024**3:
                    path.unlink();raise ValueError('Préparation supérieure à la limite de cache de 2 Gio')
                for p in autres:
                    total+=p.stat().st_size
                    if total>2*1024**3:p.unlink()
                print('Préparation de la référence enregistrée sur le T7',flush=True)
            except (OSError,ValueError,RuntimeError,TypeError) as exc:print('Cache vocal non enregistré : '+str(exc),flush=True)
        return resultat
    modele._start_caches=commencer
