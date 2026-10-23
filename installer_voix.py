"""Installe le runtime choisi ; les poids restent gérés par le catalogue."""
import argparse
from pathlib import Path
import platform
import subprocess
import sys
import venv

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--moteur',choices=['mlx','omnivoice'],default='mlx');args=parser.parse_args()
    if args.moteur=='mlx' and (platform.system()!='Darwin' or platform.machine()!='arm64'):raise SystemExit('MLX nécessite Apple Silicon.')
    if args.moteur=='omnivoice' and sys.version_info>=(3,14):raise SystemExit('Utilisez Python 3.12 ou 3.13 pour le runtime OmniVoice / PyTorch 2.8.')
    parent=Path(__file__).resolve().parent;root=parent/('.venv-omnivoice' if args.moteur=='omnivoice' else '.venv-voix')
    venv.EnvBuilder(with_pip=True).create(root)
    python=root/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
    req=parent/('requirements-omnivoice.txt' if args.moteur=='omnivoice' else 'requirements-voix.txt')
    subprocess.run([str(python),'-m','pip','install','-r',str(req)],check=True)
    print('Runtime installé. Choisissez le moteur et les poids dans Modèles.')
