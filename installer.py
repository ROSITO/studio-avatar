"""Install only engines supported by the detected host, in isolated environments."""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parent


def machine():
    gpu = []
    if shutil.which('nvidia-smi'):
        try:
            lines = subprocess.check_output(['nvidia-smi', '--query-gpu=name,memory.total,driver_version',
                '--format=csv,noheader,nounits'], text=True, timeout=10).splitlines()
            for line in lines:
                name, memory, driver = [part.strip() for part in line.rsplit(',', 2)]
                gpu.append(dict(name=name, vram_mib=int(memory), driver=driver))
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    import memoire
    return dict(os=platform.system(), arch=platform.machine().lower(), ram_gib=round(memoire.physique()/memoire.GIB, 1), nvidia=gpu)


def plan(host, engine='auto', device='auto'):
    apple = host['os'] == 'Darwin' and host['arch'] == 'arm64'
    if engine == 'auto':
        engine = 'mlx' if apple else 'omnivoice'
    result = dict(host=host, engine=engine, supported=True, device=None,
                  video='LTX-2-MLX: installation externe requise' if apple else 'Pas de moteur video compatible integre; interface et montage disponibles')
    if engine == 'interface':
        return result
    if engine in ('mlx', 'animation'):
        if not apple:
            result.update(supported=False, reason='Ce moteur requiert macOS Apple Silicon.')
        else:
            result['device'] = 'mps'
        return result
    if not apple and not (host['os'] in ('Windows', 'Linux') and host['arch'] in ('amd64', 'x86_64')):
        result.update(supported=False, reason='OmniVoice: architecture non validee par cet installateur.')
        return result
    # CUDA 12.8 needs a recent NVIDIA driver; leave low-VRAM laptops on CPU.
    cuda = any(g['vram_mib'] >= 8192 and int(g['driver'].split('.')[0]) >= 570 for g in host['nvidia'])
    chosen = ('mps' if apple else 'cuda' if cuda else 'cpu') if device == 'auto' else device
    if (chosen == 'cuda' and not cuda) or (chosen == 'mps' and not apple):
        result.update(supported=False, reason='Backend GPU non admissible (CUDA: pilote 570+ et au moins 8 Gio VRAM requis par cette recette).')
        return result
    result['device'] = chosen
    result['environment'] = '.venv-omnivoice'
    result['note'] = 'CPU: synthese potentiellement lente; aucune garantie de rendu video.' if chosen == 'cpu' else 'Backend a verifier apres installation.'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', choices=('auto', 'interface', 'mlx', 'omnivoice', 'animation'), default='auto')
    parser.add_argument('--device', choices=('auto', 'cpu', 'cuda', 'mps'), default='auto')
    parser.add_argument('--plan', action='store_true', help='Detecter sans installer')
    args = parser.parse_args()
    choice = plan(machine(), args.engine, args.device)
    print(json.dumps(choice, ensure_ascii=False, indent=2), flush=True)
    if not choice['supported']:
        return 1
    if args.plan:
        return 0
    if sys.version_info < (3, 10):
        raise SystemExit('Python 3.10+ requis.')
    missing = [name for name in ('ffmpeg', 'ffprobe') if not shutil.which(name)]
    if missing:
        raise SystemExit('Installez FFmpeg, puis ajoutez ffmpeg et ffprobe au PATH avant de relancer.')
    engine = choice['engine']
    if engine == 'interface':
        print('Interface prete : lancer.bat (Windows) ou python3 lancer.py.')
        return 0
    if engine == 'omnivoice' and sys.version_info[:2] not in ((3, 12), (3, 13)):
        raise SystemExit('OmniVoice: lancez cet installateur avec Python 3.12 ou 3.13 (Windows: py -3.12 installer.py).')
    if engine in ('mlx', 'animation'):
        subprocess.run([sys.executable, str(ROOT / ('installer_voix.py' if engine == 'mlx' else 'installer_animation.py'))], check=True)
        return 0
    target = ROOT / '.venv-omnivoice'
    marker = target / '.studio-installation.json'
    if target.exists() and not marker.exists():
        raise SystemExit('Runtime existant sans manifeste: conservez-le ou renommez .venv-omnivoice avant une installation propre.')
    if marker.exists() and json.loads(marker.read_text(encoding='utf-8')).get('device') != choice['device']:
        raise SystemExit('Backend different du runtime existant: renommez .venv-omnivoice pour le conserver puis relancez.')
    venv.EnvBuilder(with_pip=True).create(target)
    python = target / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    base = [str(python), '-m', 'pip', 'install']
    index = 'https://download.pytorch.org/whl/' + ('cu128' if choice['device'] == 'cuda' else 'cpu')
    torch_args = [] if choice['device'] == 'mps' else ['--index-url', index]
    # On failure the directory is retained for diagnostics, but has no success marker.
    marker.unlink(missing_ok=True)
    subprocess.run(base + ['torch==2.8.0', 'torchaudio==2.8.0'] + torch_args, check=True)
    subprocess.run(base + ['-r', str(ROOT / 'requirements-omnivoice.txt')], check=True)
    subprocess.run([str(python), '-m', 'pip', 'check'], check=True)
    probe = "import torch, omnivoice, soundfile; device=" + repr(choice['device']) + "; assert device == 'cpu' or (torch.cuda.is_available() if device == 'cuda' else torch.backends.mps.is_available()); print('Runtime OK:', device)"
    subprocess.run([str(python), '-c', probe], check=True)
    marker.write_text(json.dumps(dict(engine=engine, device=choice['device'], python=platform.python_version()), indent=2), encoding='utf-8')
    with (target / 'requirements-installed.txt').open('w', encoding='utf-8') as installed:
        subprocess.run([str(python), '-m', 'pip', 'freeze'], stdout=installed, check=True)
    print('Runtime installe et verifie. Telechargez ensuite les poids OmniVoice depuis Modeles. Aucune voix personnelle incluse.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f'Installation incomplete (code {exc.returncode}). Consultez la sortie ci-dessus; corrigez puis relancez.')
