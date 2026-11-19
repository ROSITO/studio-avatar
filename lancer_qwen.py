"""Official Qwen-TTS PyTorch worker, offline local weights and monitored memory."""
import json
import os
from pathlib import Path
import signal
import sys


def generer(d):
    os.environ['HF_HUB_OFFLINE']='1'
    os.environ['TRANSFORMERS_OFFLINE']='1'
    import memoire
    plafond=memoire.verifier(d['moteur'])
    garde=memoire.surveiller(plafond)
    import torch
    import soundfile as sf
    from qwen_tts import Qwen3TTSModel
    device='cuda:0' if torch.cuda.is_available() else 'cpu'
    if device!='cpu':
        total=torch.cuda.get_device_properties(0).total_memory
        torch.cuda.set_per_process_memory_fraction(min(.9,plafond/total))
    torch.manual_seed(d['seed'])
    path=Path(d['modele']).resolve()
    if not path.is_dir():raise ValueError('Poids Qwen PyTorch introuvables.')
    print('Chargement Qwen-TTS PyTorch · '+device,flush=True)
    model=Qwen3TTSModel.from_pretrained(str(path),device_map=device,
        dtype=torch.float32 if device=='cpu' else torch.float16,
        attn_implementation='sdpa',local_files_only=True)
    langue={'fr':'French','en':'English','es':'Spanish','de':'German','it':'Italian',
            'pt':'Portuguese','zh':'Chinese','ja':'Japanese','ko':'Korean','ru':'Russian'}.get(d['langue'],'Auto')
    print('Clonage Qwen-TTS depuis la référence originale',flush=True)
    audio,sr=model.generate_voice_clone(text=d['texte'],language=langue,
        ref_audio=d['reference'],ref_text=d['transcription'],x_vector_only_mode=False,
        max_new_tokens=4096,temperature=.5,top_p=.8,top_k=20)
    if not audio or len(audio[0])==0:raise RuntimeError('Qwen-TTS n’a produit aucun audio.')
    sf.write(d['sortie'],audio[0],sr,subtype='PCM_24')
    garde.set()


def main():
    def interrompre(signum,frame):raise SystemExit('Synthèse interrompue')
    signal.signal(signal.SIGTERM,interrompre)
    generer(json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')))


if __name__=='__main__':main()
