"""Processus MLX isolé : libère toute la mémoire avant le prochain calcul LTX."""
from contextlib import contextmanager
import json
import os
import tempfile
import signal
from pathlib import Path
import sys

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

def main():
    def interrompre(signum, frame):raise SystemExit('Synthèse interrompue')
    signal.signal(signal.SIGTERM,interrompre)
    d=json.loads(Path(sys.argv[1]).read_text())
    import memoire
    plafond=memoire.verifier(d['moteur'])
    import mlx.core as mx
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
        modele=load_model(str(vue))
        print('Génération de la prise',flush=True)
        lang={'fr':'French','en':'English','es':'Spanish','de':'German','it':'Italian','pt':'Portuguese','zh':'Chinese','ja':'Japanese','ko':'Korean'}.get(d['langue'],d['langue'])
        out=Path(d['sortie'])
        generate_audio(model=modele,text=d['texte'],ref_audio=d['reference'],ref_text=d['transcription'],lang_code=lang,
            output_path=str(out.parent),file_prefix=out.stem,audio_format='wav',join_audio=True,play=False,stream=False,max_tokens=256 if d['moteur']=='drama3-mlx' else 4096,verbose=True)
        if not out.is_file() or out.stat().st_size<44:raise RuntimeError('La synthèse a échoué : aucune prise produite.')
    print('Prise terminée',flush=True)

if __name__=='__main__':main()
