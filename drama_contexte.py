"""Reuse an exact, aligned causal history prefix within one Drama generation.

Never drops history or changes text/chunking. Cache matching includes the next
teacher-forced frame and follows the native PREFILL_CHUNK grid exactly.
"""
import os


def installer(mx, modele):
    if os.environ.get('STUDIO_DRAMA_CONTEXT_CACHE','1')=='0':return
    import numpy as np
    from mlx_audio.tts.models.fish_drama3.drama3 import _copy_cache,PREFILL_CHUNK
    build,prefill=modele.build_frames,modele._prefill
    current={};saved={};stats=dict(reutilisees=0,preparations=0)

    def construire(references,history,target):
        frames,system=build(references,history,target)
        current.clear()
        if history:
            first,_=build(references,history[:1],target)
            empty,_=build(references,[],target)
            boundary=system+first.shape[0]-empty.shape[0]
            aligned=system+((boundary-system)//PREFILL_CHUNK)*PREFILL_CHUNK
            if system<aligned<frames.shape[0]:
                current.update(system=system,end=aligned,prefix=np.array(frames[:aligned+1],copy=True))
        return frames,system

    def copier(groups):
        result=tuple([_copy_cache(c) for c in group] for group in groups)
        mx.eval([[c.state for c in group] for group in result])
        return result

    def preparer(frames,caches,start,stop):
        end=current.get('end',0)
        if start!=current.get('system') or not start<end<stop:
            return prefill(frames,caches,start,stop)
        prefix=current['prefix']
        if saved.get('system')==start and saved.get('end')==end and np.array_equal(saved.get('prefix'),prefix):
            reused=copier(saved['caches'])
            if [len(g) for g in reused]!=[len(g) for g in caches]:
                saved.clear();return prefill(frames,caches,start,stop)
            for target,source in zip(caches,reused):target[:]=source
            stats['reutilisees']+=end-start
            print(f'Contexte vocal réutilisé : {end-start} trames, sans recalcul',flush=True)
            return prefill(frames,caches,end,stop)
        prefill(frames,caches,start,end)
        size=sum(a.nbytes for group in caches for c in group for a in c.state if a is not None)
        if size<=256*1024**2:
            saved.update(system=start,end=end,prefix=prefix.copy(),caches=copier(caches))
            stats['preparations']+=1
            print(f'Contexte vocal mis en cache : {end-start} trames ({size/1024**2:.1f} Mio)',flush=True)
        else:saved.clear()
        return prefill(frames,caches,end,stop)

    modele.build_frames=construire;modele._prefill=preparer
    modele._studio_contexte_stats=stats
