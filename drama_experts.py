"""Small bounded CPU cache for immutable quantized expert rows, no math changes."""
from collections import OrderedDict
import os
import time


class CacheExperts:
    def __init__(self, plafond, budget=0, maximum=None):
        self.plafond=plafond;self.octets=0;self.lru=OrderedDict();self.hits=0;self.misses=0
        self.verifie=0;self.actif=True
        self.base=plafond;self.budget=budget
        self.maximum=plafond if maximum is None else maximum

    def redimensionner(self, plafond):
        self.plafond=max(0,int(plafond))
        while self.lru and self.octets>self.plafond:
            _,old=self.lru.popitem(last=False)
            self.octets-=sum(a.nbytes for a in old.values())

    def verifier(self):
        if time.monotonic()-self.verifie<1:return self.actif
        import memoire
        self.verifie=time.monotonic()
        niveau=memoire.pression();dispo=memoire.disponible()
        avant=self.actif
        self.actif=niveau<4 and not (niveau>=2 and dispo<4.5*memoire.GIB)
        if not self.actif:self.lru.clear();self.octets=0
        if self.budget:
            old=self.plafond
            try:
                footprint=memoire.empreinte(os.getpid())
                # Two GiB inside the worker for transient model allocations;
                # six GiB outside it for the system and other applications.
                spare=min(self.budget-footprint-2*memoire.GIB,dispo-6*memoire.GIB)
                target=min(self.maximum,max(0,self.octets+spare))
                if niveau>=2:target=min(target,self.base)
                if not self.actif:target=0
                # Grow gradually; reclaim immediately when headroom falls.
                step=256*1024**2
                target=int(target//step)*step
                self.redimensionner(min(target,self.plafond+step))
            except (OSError,ValueError):
                self.redimensionner(0)
                self.actif=False
            if old!=self.plafond:
                print(f'Cache experts adaptatif : {self.plafond/1024**2:.0f} Mio maximum ; utilisé {self.octets/1024**2:.0f} Mio',flush=True)
        if avant!=self.actif:print(f"Cache experts {'actif' if self.actif else 'libéré'} · pression {niveau}, disponible {dispo/memoire.GIB:.1f} Gio",flush=True)
        return self.actif

    def get(self,key):
        if key not in self.lru:self.misses+=1;return None
        self.hits+=1;self.lru.move_to_end(key);return self.lru[key]

    def put(self,key,value):
        size=sum(a.nbytes for a in value.values())
        if size>self.plafond:return
        if key in self.lru:self.octets-=sum(a.nbytes for a in self.lru.pop(key).values())
        # A decode visits all model layers in order. LRU eviction would replace
        # the entire cache every frame when the working set exceeds its size.
        # Retain a bounded subset instead, reusable on the next decode frame.
        if self.octets+size>self.plafond:return
        self.lru[key]=value;self.octets+=size


def lecteur(plafond, actif=True):
    import numpy as np
    try:configured=float(os.environ.get('STUDIO_DRAMA_EXPERT_CACHE_MB','1024'))
    except ValueError:raise ValueError('STUDIO_DRAMA_EXPERT_CACHE_MB invalide.')
    if not 0<=configured<=1024:raise ValueError('Cache expert : entre 0 et 1024 Mio.')
    adaptive=actif and os.environ.get('STUDIO_DRAMA_ADAPTIVE_CACHE','0')=='1'
    base=int(min(configured*1024**2,plafond/8)) if actif else 0
    cache=CacheExperts(base,budget=plafond if adaptive else 0,
        # Keep a conservative 10 GiB allowance for the model and transient buffers.
        # At the standard 12 GiB budget this admits at most a 2 GiB cache.
        maximum=int(max(base,min(4*1024**3,plafond/3,plafond-10*1024**3))) if adaptive else base)
    print(f'Cache experts : {cache.plafond/1024**2:.0f} Mio maximum',flush=True)
    from drama_lecture import LectureDirecte
    direct = LectureDirecte() if actif and os.environ.get('STUDIO_DRAMA_DIRECT_READ', '1') == '1' else None
    print('Lecture experts : '+('directe, sans mapping complet' if direct is not None else 'mapping temporaire'),flush=True)
    stats=dict(octets_lus=0,secondes_lecture=0.0,appels=0)
    optimiser_copies=os.environ.get('STUDIO_DRAMA_COPY_REDUCTION','1')!='0'

    def lire(banques,uniques,identifiant):
        start=time.perf_counter();stats['appels']+=1
        # Prefill requests touch many experts: do not fill the cache with a
        # one-off wide batch, evicting the experts useful during decoding.
        healthy=cache.verifier() if cache.maximum>0 else False
        active=healthy and len(uniques)<=16
        found={};missing=[]
        for expert in uniques.tolist():
            value=cache.get((identifiant,expert)) if active else None
            if value is None:missing.append(expert)
            else:found[expert]=value
        loaded={}
        if missing:
            for key,(description,_dtype) in banques.items():
                fichier,type_numpy,decalage,forme=description
                if direct is not None:
                    loaded[key]=direct(description,missing)
                else:
                    bank=np.memmap(fichier,mode='r',dtype=type_numpy,offset=decalage,shape=forme)
                    try:loaded[key]=np.array(bank[missing],copy=True)
                    finally:bank._mmap.close()
                stats['octets_lus']+=loaded[key].nbytes
            for i,expert in enumerate(missing):
                row={key:array[i] for key,array in loaded.items()}
                found[expert]=row
                # Avoid allocating an entire expert copy just to have a full
                # cache reject it. Missing experts cannot already be cached.
                admissible=cache.octets+sum(v.nbytes for v in row.values())<=cache.plafond
                if active and (not optimiser_copies or admissible):
                    cache.put((identifiant,expert),{k:np.array(v,copy=True) for k,v in row.items()})
        if not active or (optimiser_copies and len(missing)==len(uniques)):
            result=loaded  # All rows were read in the original sorted order.
        else:
            result={key:np.stack([found[int(e)][key] for e in uniques]) for key in banques}
        stats['secondes_lecture']+=time.perf_counter()-start
        return result

    lire.close=direct.close if direct is not None else lambda:None
    lire.cache=cache;lire.stats=stats
    return lire
