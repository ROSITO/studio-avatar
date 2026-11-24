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
import plateforme

ROOT = Path(__file__).resolve().parent


def machine():
    return plateforme.detecter()


def plan(host, engine='auto', device='auto'):
    automatique = engine == 'auto'
    apple = host['os'] == 'Darwin' and host['arch'] == 'arm64'
    if engine == 'auto':
        engine = 'mlx' if apple else 'omnivoice'
    result = dict(host=host, engine=engine, supported=True, device=None,
                  video='LTX-2-MLX: installation externe requise' if apple else 'Pas de moteur video compatible integre; interface et montage disponibles')
    if engine == 'interface':
        return result
    if engine in ('ltx','image'):
        reason=plateforme.raison_backend('ltx-torch' if engine=='ltx' else 'flux-torch',host)
        if reason:result.update(supported=False,reason=reason);return result
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
    cuda = plateforme.appareil_torch(host) == 'cuda'
    chosen = ('mps' if apple else 'cuda' if cuda else 'cpu') if device == 'auto' else device
    if (chosen == 'cuda' and not cuda) or (chosen == 'mps' and not apple):
        result.update(supported=False, reason='Backend GPU non admissible (CUDA: pilote 570+ et au moins 8 Gio VRAM requis par cette recette).')
        return result
    if engine in ('ltx','image') and chosen!='cuda':
        result.update(supported=False,reason='Ce moteur visuel natif requiert CUDA.');return result
    result['device'] = chosen
    if engine=='qwen-tts' and apple:
        result.update(supported=False,reason='Sur Apple Silicon, utilisez le moteur Qwen MLX.');return result
    result['environment'] = {'qwen-tts':'.venv-qwen','ltx':'.venv-ltx','image':'.venv-image'}.get(engine,'.venv-omnivoice')
    if automatique and not apple:
        result['additional_engines']=['qwen-tts']+[e for e,b in [('ltx','ltx-torch'),('image','flux-torch')] if plateforme.backend_compatible(b,host)]
        result['video']='LTX PyTorch avec lecture sur disque' if 'ltx' in result['additional_engines'] else plateforme.raison_backend('ltx-torch',host)
    result['note'] = 'CPU: synthese potentiellement lente; aucune garantie de rendu video.' if chosen == 'cpu' else 'Backend a verifier apres installation.'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', choices=('auto', 'interface', 'mlx', 'omnivoice', 'qwen-tts', 'ltx', 'image', 'animation'), default='auto')
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
        raise SystemExit('Prerequis FFmpeg absents. Sous Windows, lancez installer.bat pour les installer automatiquement.')
    engine = choice['engine']
    if engine == 'interface':
        print('Interface prete : lancer.bat (Windows) ou python3 lancer.py.')
        return 0
    if engine in ('omnivoice','qwen-tts','ltx','image') and sys.version_info[:2] not in ((3, 12), (3, 13)):
        raise SystemExit('Les moteurs PyTorch utilisent Python 3.12 ou 3.13 ; lancez installer.bat sous Windows.')
    if engine in ('mlx', 'animation'):
        subprocess.run([sys.executable, str(ROOT / ('installer_voix.py' if engine == 'mlx' else 'installer_animation.py'))], check=True)
        return 0
    target = ROOT / choice['environment']
    marker = target / '.studio-installation.json'
    owner = target / '.studio-managed.json'
    if target.exists() and not marker.exists() and not owner.exists():
        raise SystemExit(f'Runtime existant sans manifeste: conservez ou renommez {target.name} avant une installation propre.')
    if owner.exists() and json.loads(owner.read_text(encoding='utf-8')).get('device') != choice['device']:
        raise SystemExit(f'Installation incomplete avec un autre backend : renommez {target.name} pour le conserver puis relancez.')
    if marker.exists() and json.loads(marker.read_text(encoding='utf-8')).get('device') != choice['device']:
        raise SystemExit(f'Backend different du runtime existant: renommez {target.name} pour le conserver puis relancez.')
    target.mkdir(exist_ok=True)
    owner.write_text(json.dumps(dict(engine=engine, device=choice['device'])), encoding='utf-8')
    venv.EnvBuilder(with_pip=True).create(target)
    python = target / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    base = [str(python), '-m', 'pip', 'install']
    index = 'https://download.pytorch.org/whl/' + ('cu128' if choice['device'] == 'cuda' else 'cpu')
    torch_args = [] if choice['device'] == 'mps' else ['--index-url', index]
    # On failure the directory is retained for diagnostics, but has no success marker.
    marker.unlink(missing_ok=True)
    subprocess.run(base + ['torch==2.8.0', 'torchaudio==2.8.0'] + (['torchvision==0.23.0'] if engine in ('ltx','image') else []) + torch_args, check=True)
    subprocess.run(base + ['-r', str(ROOT / {'qwen-tts':'requirements-qwen.txt','ltx':'requirements-ltx.txt','image':'requirements-image.txt'}.get(engine,'requirements-omnivoice.txt'))], check=True)
    subprocess.run([str(python), '-m', 'pip', 'check'], check=True)
    imports={'qwen-tts':'import qwen_tts','ltx':'import ltx_pipelines.ti2vid_two_stages, ltx_pipelines.a2vid_two_stage','image':'from diffusers import Flux2KleinPipeline'}.get(engine,'import omnivoice')
    probe=("import torch, soundfile; " if engine in ("omnivoice","qwen-tts") else "import torch; ")+imports+"; device="+repr(choice['device'])+"; assert device=='cpu' or (torch.cuda.is_available() if device=='cuda' else torch.backends.mps.is_available()); print('Runtime OK:',device)"
    subprocess.run([str(python), '-c', probe], check=True)
    with (target / 'requirements-installed.txt').open('w', encoding='utf-8') as installed:
        subprocess.run([str(python), '-m', 'pip', 'freeze'], stdout=installed, check=True)
    marker.write_text(json.dumps(dict(engine=engine, device=choice['device'], python=platform.python_version()), indent=2), encoding='utf-8')
    for additional in choice.get('additional_engines',[]):
        subprocess.run([sys.executable,str(ROOT/'installer.py'),'--engine',additional,'--device',choice['device']],check=True)
    print('Runtimes installes et verifies. Telechargez ensuite les poids compatibles depuis Modeles.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f'Installation incomplete (code {exc.returncode}). Consultez la sortie ci-dessus; corrigez puis relancez.')
