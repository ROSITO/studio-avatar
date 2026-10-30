#!/usr/bin/env python3
"""Install an isolated experimental MPS runtime, without downloading model weights."""
import json
from pathlib import Path
import subprocess
import sys
import venv
from animation import RUNTIME_REVISION


def main():
    root=Path(__file__).resolve().parent
    if sys.version_info<(3,11):raise SystemExit('Python 3.11 ou plus récent requis.')
    target=root/'.venv-animation'
    venv.EnvBuilder(with_pip=True).create(target)
    py=target/'bin/python'
    subprocess.run([str(py),'-m','pip','install','torch==2.15.0','transformers==5.22.0','accelerate==1.15.0',
        'safetensors','sentencepiece','protobuf','opencv-python-headless','imageio[ffmpeg]','pillow','ftfy','einops',
        f'git+https://github.com/kelseyee/diffusers.git@{RUNTIME_REVISION}'],check=True)
    if sys.platform=='darwin':subprocess.run([str(py),str(root/'adapter_animation.py')],check=True)
    subprocess.run([str(py),str(root/'lancer_animation.py'),'--diagnostic'],check=True)
    subprocess.run([str(py),'-m','unittest','test_animation.KernelTests','test_animation.TransformerTests','-q'],cwd=root,check=True)
    (target/'.studio-animation-runtime.json').write_text(json.dumps(dict(revision=RUNTIME_REVISION,experimental=True)))
    print('Moteur installé. Téléchargez les poids Wan-Animate-2 dans Modèles.')


if __name__=='__main__':main()
