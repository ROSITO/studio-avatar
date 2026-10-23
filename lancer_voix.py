"""Processus MLX isolé : libère toute la mémoire avant le prochain calcul LTX."""
from contextlib import contextmanager
import json
import os
import tempfile
import signal
from pathlib import Path
import sys
import time

@contextmanager
def vue_modele(source, parent):
    """Ignore AppleDouble metadata on external volumes, without copying weights."""
    source=Path(source)
    with tempfile.TemporaryDirectory(prefix='.modele-',dir=parent) as tmp:
        vue=Path(tmp)
        for dossier,dirs,files in os.walk(source):
            dirs[:]=[d for d in dirs if not d.startswith('.')]
            dest=vue/Path(dossier).relative_to(source);dest.mkdir(parents=True,exist_ok=True)
            for nom in files:
                if not nom.startswith('.'):(dest/nom).symlink_to((Path(dossier)/nom).resolve())
        yield vue

def limite_drama(texte):
    # About 22 audio frames/s, allowing slower delivery and nonverbal cues.
    from balises import parle
    return 1024 if len(parle(texte))>120 else 256

def generer_flux(modele,d,out):
    """Decode causally without the CLI helper's forced audio playback."""
    import numpy as np
    from mlx_audio.audio_io import write
    morceaux=[];total=0
    for resultat in modele.generate(text=d['texte'],ref_audio=d['reference'],ref_text=d['transcription'],
            stream=True,streaming_interval=1.0,max_tokens=limite_drama(d['texte'])):
        morceau=np.array(resultat.audio)
        morceaux.append(morceau);total+=len(morceau)
        print(f'Audio décodé : {total/modele.sample_rate:.2f} s',flush=True)
    if not morceaux:raise RuntimeError('Aucun audio généré')
    write(str(out),np.concatenate(morceaux),modele.sample_rate,format='wav')

def main():
    def interrompre(signum, frame):raise SystemExit('Synthèse interrompue')
    signal.signal(signal.SIGTERM,interrompre)
    d=json.loads(Path(sys.argv[1]).read_text())
    import memoire
    plafond=memoire.verifier(d['moteur'])
    import mlx.core as mx
    if d['moteur']=='drama3-mlx':
        # CPU keeps MoE weights pageable instead of pinning the full model on Metal.
        mx.set_default_device(mx.cpu)
        print('Drama 3 : chargement différé, experts lus sur disque',flush=True)
    memoire.configurer_mlx(mx,d['moteur'])
    # Drama may map more weights than its resident footprint: the external
    # supervisor limits actual process memory, not the virtual mapped size.
    mesure=None if d['moteur']=='drama3-mlx' else lambda:mx.get_active_memory()+mx.get_cache_memory()
    garde=memoire.surveiller(plafond,mesure)
    from mlx_audio.tts.utils import load_model
    from mlx_audio.tts.generate import generate_audio
    mx.random.seed(d['seed'])
    print('Chargement du modèle vocal local',flush=True)
    with vue_modele(d['modele'],str(Path(d['sortie']).parent)) as vue:
        modele=load_model(str(vue),lazy=d['moteur']=='drama3-mlx')
        if d['moteur']=='drama3-mlx' and mx.metal.is_available():
            # Codec convolutions have a very slow CPU fallback. Keep only this
            # small component on Metal; the large MoE backbone stays on CPU.
            def sur_gpu(fn):
                def appel(*args,**kwargs):
                    with mx.stream(mx.gpu):
                        resultat=fn(*args,**kwargs)
                        mx.eval(resultat)
                    return resultat
                return appel
            for nom in ('encode','streaming_step'):
                setattr(modele.codec,nom,sur_gpu(getattr(modele.codec,nom)))
            import drama_memoire
            drama_memoire.activer(mx,modele,vue)
            print('GPU : experts sélectionnés uniquement, banques conservées sur disque',flush=True)
        if d['moteur']=='drama3-mlx':
            import drama_cache
            drama_cache.installer(mx,modele,d)
            prefill=modele._prefill
            def pre_remplir(frames,caches,debut,fin):
                print(f'Préparation vocale : {fin-debut} trames',flush=True)
                chrono=time.perf_counter()
                resultat=prefill(frames,caches,debut,fin)
                print(f'Préparation vocale terminée ({time.perf_counter()-chrono:.2f} s)',flush=True)
                return resultat
            modele._prefill=pre_remplir
            frames_origine=modele._frames
            def trames(*args,**kwargs):
                for i,trame in enumerate(frames_origine(*args,**kwargs),1):
                    if i==1 or i%16==0:print(f'Voix : {i} trames générées',flush=True)
                    yield trame
            modele._frames=trames
        print('Génération de la prise',flush=True)
        lang={'fr':'French','en':'English','es':'Spanish','de':'German','it':'Italian','pt':'Portuguese','zh':'Chinese','ja':'Japanese','ko':'Korean'}.get(d['langue'],d['langue'])
        out=Path(d['sortie'])
        flux=d['moteur']=='drama3-mlx' and limite_drama(d['texte'])>256
        if flux:generer_flux(modele,d,out)
        else:
            generate_audio(model=modele,text=d['texte'],ref_audio=d['reference'],ref_text=d['transcription'],lang_code=lang,
                output_path=str(out.parent),file_prefix=out.stem,audio_format='wav',join_audio=True,play=False,stream=False,max_tokens=limite_drama(d['texte']) if d['moteur']=='drama3-mlx' else 4096,verbose=True)
        if not out.is_file() or out.stat().st_size<44:raise RuntimeError('La synthèse a échoué : aucune prise produite.')
    print('Prise terminée',flush=True)

if __name__=='__main__':main()
