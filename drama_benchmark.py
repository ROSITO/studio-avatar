"""Queued preparation benchmark, no fake speech output or history truncation."""
import json
from pathlib import Path
import time


def mesurer(mx, modele, d):
    voice=modele._voice(d['reference'],d['transcription'])
    if not voice.references:raise ValueError('Une référence vocale est requise.')
    codes=voice.references[0][1][:,:128]
    history=[('Bonjour.',codes)]
    results=[];states=[]
    for label in ('sans_reutilisation','avec_reutilisation'):
        frames,system=modele.build_frames(voice.references,history,'Un essai de préparation.')
        caches=modele._start_caches(frames,system,voice)
        start=time.perf_counter();hidden=modele._prefill(frames,caches,system,frames.shape[0]);mx.eval(hidden)
        elapsed=time.perf_counter()-start
        results.append(dict(mode=label,secondes=elapsed,trames=frames.shape[0]-system))
        states.append((hidden,tuple([type(c).from_state(c.state,c.meta_state) for c in group] for group in caches)))
        print(f'Mesure {label} : {elapsed:.2f} s',flush=True)
    exact=mx.array_equal(states[0][0],states[1][0]).item()
    for ga,gb in zip(states[0][1],states[1][1]):
        for ca,cb in zip(ga,gb):
            exact=exact and ca.meta_state==cb.meta_state
            for a,b in zip(ca.state,cb.state):
                exact=exact and ((a is None and b is None) or (a is not None and b is not None and mx.array_equal(a,b).item()))
    report=dict(mesures=results,etats_identiques=bool(exact),gain=results[0]['secondes']/max(.001,results[1]['secondes']),
                contexte=modele._studio_contexte_stats)
    Path(d['sortie']).with_suffix('.json').write_text(json.dumps(report,indent=2))
    print('MESURE CONTEXTE : '+json.dumps(report),flush=True)
    if not exact:raise RuntimeError('Les états ne sont pas identiques : optimisation non validée.')
