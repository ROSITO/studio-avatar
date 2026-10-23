"""OmniVoice officiel, autonome : référence et réglages conservés, sortie brute."""
import json
from pathlib import Path
import signal
import sys
from lancer_voix import vue_modele

def main():
    def interrompre(signum,frame):raise SystemExit('Synthèse interrompue')
    signal.signal(signal.SIGTERM,interrompre)
    d=json.loads(Path(sys.argv[1]).read_text())
    import torch
    import soundfile as sf
    from omnivoice import OmniVoice
    device='mps' if torch.backends.mps.is_available() else 'cuda' if torch.cuda.is_available() else 'cpu'
    torch.manual_seed(d['seed'])
    print('Chargement OmniVoice · '+device,flush=True)
    with vue_modele(d['modele'],str(Path(d['sortie']).parent)) as vue:
        model=OmniVoice.from_pretrained(str(vue),device_map=device,dtype=torch.float32 if device=='cpu' else torch.float16,load_asr=False)
        print('Clonage depuis la référence originale · 16 étapes · guidance 2',flush=True)
        audio=model.generate(text=d['texte'],ref_audio=d['reference'],ref_text=d['transcription'],language=d['langue'],
            num_step=16,guidance_scale=2.,speed=1.,postprocess_output=False)
        if not audio or len(audio[0])==0:raise RuntimeError('OmniVoice n’a produit aucun audio')
        prise=audio[0]
        if isinstance(prise,torch.Tensor):prise=prise.detach().float().cpu().numpy()
        sf.write(d['sortie'],prise,int(getattr(model,'sampling_rate',24000)),subtype='PCM_24')
    print('Prise OmniVoice terminée',flush=True)

if __name__=='__main__':main()
