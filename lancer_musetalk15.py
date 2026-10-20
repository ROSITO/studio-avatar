#!/usr/bin/env python3
"""Lipsync MuseTalk 1.5 en local, d'après scripts/inference.py officiel (version v15) :
poids musetalkV15, marge de 10 px sous le menton, mélange sur la mâchoire (FaceParsing joues 90), 2 trames audio de contexte.
Usage : .venv-musetalk/bin/python lancer_musetalk15.py <vidéo 25 i/s> <audio 16 kHz> <sortie.mp4> [bbox_shift]"""
import os, sys, subprocess, tempfile, glob
from pathlib import Path
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"
SRC, AUD, OUT = (Path(a).resolve() for a in sys.argv[1:4]); SHIFT = int(sys.argv[4]) if len(sys.argv) > 4 else 0
ROOT = Path(os.environ.get("STUDIO_MUSETALK_ROOT", "musetalk")).expanduser().resolve(); sys.path.insert(0, str(ROOT)); os.chdir(ROOT)
import torch, cv2, numpy as np
_orig = torch.load; torch.load = lambda *a, **k: _orig(*a, **{**k, "weights_only": False})
from transformers import WhisperModel
from musetalk.utils.utils import load_all_model, datagen
from musetalk.utils.audio_processor import AudioProcessor
from musetalk.utils.face_parsing import FaceParsing
from musetalk.utils.preprocessing import get_landmark_and_bbox, coord_placeholder
from musetalk.utils.blending import get_image
EXTRA_MARGIN, FPS, BATCH = 10, 25, 8
dev = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
vae, unet, pe = load_all_model(unet_model_path="models/musetalkV15/unet.pth", vae_type="sd-vae",
                               unet_config="models/musetalkV15/musetalk.json", device=dev)
pe, vae.vae, unet.model = pe.to(dev), vae.vae.to(dev), unet.model.to(dev)
dtype = unet.model.dtype; timesteps = torch.tensor([0], device=dev)
ap = AudioProcessor(feature_extractor_path="models/whisper")
whisper = WhisperModel.from_pretrained("models/whisper").to(device=dev, dtype=dtype).eval(); whisper.requires_grad_(False)
fp = FaceParsing(left_cheek_width=90, right_cheek_width=90)

tmp = Path(tempfile.mkdtemp()); (tmp / "in").mkdir(); (tmp / "out").mkdir()
subprocess.run(["ffmpeg", "-v", "error", "-i", str(SRC), "-start_number", "0", str(tmp / "in/%08d.png")], check=True)
imgs = sorted(glob.glob(str(tmp / "in/*.png")))
feats, length = ap.get_audio_feature(str(AUD))
chunks = ap.get_whisper_chunk(feats, dev, dtype, whisper, length, fps=FPS, audio_padding_length_left=2, audio_padding_length_right=2)
coords, frames = get_landmark_and_bbox(imgs, SHIFT)
latents = []
for (x1, y1, x2, y2), fr in zip(coords, frames):
    if (x1, y1, x2, y2) == coord_placeholder: latents.append(None); continue
    y2 = min(y2 + EXTRA_MARGIN, fr.shape[0])
    latents.append(vae.get_latents_for_unet(cv2.resize(fr[y1:y2, x1:x2], (256, 256), interpolation=cv2.INTER_LANCZOS4)))
ok = [l for l in latents if l is not None]; assert ok, "aucun visage détecté"
lat_in = [l if l is not None else ok[0] for l in latents]
i = 0
for wb, lb in datagen(chunks, lat_in, BATCH, device=dev):
    with torch.no_grad():
        pred = unet.model(lb.to(dev, dtype=dtype), timesteps, encoder_hidden_states=pe(wb.to(dev))).sample
        res = vae.decode_latents(pred)
    for r in res:
        k = i % len(frames); fr = frames[k].copy(); c = coords[k]
        if c != coord_placeholder:
            x1, y1, x2, y2 = c; y2 = min(y2 + EXTRA_MARGIN, fr.shape[0])
            fr = get_image(fr, cv2.resize(r.astype(np.uint8), (x2 - x1, y2 - y1)), [x1, y1, x2, y2], mode="jaw", fp=fp)
        cv2.imwrite(str(tmp / f"out/{i:08d}.png"), fr); i += 1
subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", str(tmp / "out/%08d.png"), "-i", str(AUD),
                "-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(OUT)], check=True)
print("ok", OUT, i, "images")
