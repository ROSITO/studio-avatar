"""Installe uniquement le runtime MLX, jamais les poids (catalogue dans l’application)."""
from pathlib import Path
import platform
import subprocess
import sys
import venv

if __name__=='__main__':
    if platform.system()!='Darwin' or platform.machine()!='arm64':raise SystemExit('Les moteurs MLX nécessitent un Mac Apple Silicon.')
    root=Path(__file__).resolve().parent/'.venv-voix'
    venv.EnvBuilder(with_pip=True).create(root)
    subprocess.run([str(root/'bin/python'),'-m','pip','install','-r',str(Path(__file__).with_name('requirements-voix.txt'))],check=True)
    print('Moteur installé. Téléchargez les poids dans Modèles → Synthèse vocale.')
