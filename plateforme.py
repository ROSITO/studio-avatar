"""Shared host/backend detection for setup, catalogue and generation screens."""
from functools import lru_cache
import platform
import shutil
import subprocess


@lru_cache(maxsize=1)
def nvidia():
    if not shutil.which('nvidia-smi'):
        return []
    try:
        try:
            result=subprocess.check_output(['nvidia-smi','--query-gpu=name,memory.total,driver_version,compute_cap','--format=csv,noheader,nounits'],text=True,timeout=10)
        except subprocess.SubprocessError:
            result=subprocess.check_output(['nvidia-smi','--query-gpu=name,memory.total,driver_version','--format=csv,noheader,nounits'],text=True,timeout=10)
        output=[]
        for line in result.splitlines():
            values=[value.strip() for value in line.split(',')];name,memory,driver=values[:3]
            try:compute=float(values[3])
            except (IndexError,ValueError):compute=None
            output.append(dict(name=name,vram_mib=int(memory),driver=driver,compute_cap=compute))
        return output
    except (OSError, ValueError, subprocess.SubprocessError):
        return []


@lru_cache(maxsize=1)
def ram_gib():
    import memoire
    return round(memoire.physique()/memoire.GIB,1)


def detecter():
    return dict(os=platform.system(), arch=platform.machine().lower(),
                ram_gib=ram_gib(), nvidia=nvidia())


def appareil_torch(host):
    if host['os'] == 'Darwin' and host['arch'] == 'arm64':
        return 'mps'
    if any(g['vram_mib'] >= 7680 and int(g['driver'].split('.')[0]) >= 570 for g in host['nvidia']):
        return 'cuda'
    return 'cpu'


def backend_compatible(backend, host=None):
    host = host or detecter()
    apple = host['os'] == 'Darwin' and host['arch'] == 'arm64'
    x64 = host['os'] in ('Windows', 'Linux') and host['arch'] in ('amd64', 'x86_64')
    if backend == 'omnivoice-torch':
        return apple or x64
    if backend == 'qwen-torch':
        return x64
    if backend in ('ltx-torch','flux-torch'):
        # Nominal 8/12 GB cards and 32 GB RAM report slightly less after hardware reservations.
        minimum=7680 if backend=='ltx-torch' else 11776
        return x64 and host['ram_gib']>=30 and any(g['vram_mib']>=minimum and int(g['driver'].split('.')[0])>=570 and float(g.get('compute_cap') or 0)>=8 for g in host['nvidia'])
    return apple if backend in ('ltx-mlx', 'mlx-audio', 'mflux', 'wan-mps', 'musetalk-mps') else False


def raison_backend(backend,host=None):
    host=host or detecter()
    if backend_compatible(backend,host):return ''
    if backend in ('ltx-torch','flux-torch'):
        minimum=8 if backend=='ltx-torch' else 12
        return f'{backend} : Windows/Linux x64, 32 Go RAM, NVIDIA {minimum} Go VRAM minimum, pilote 570+ et GPU Ampere ou plus récent requis.'
    if backend=='qwen-torch':return 'Qwen PyTorch nécessite Windows/Linux x64.'
    return 'Ce moteur MLX/MPS nécessite macOS Apple Silicon. Choisissez sa variante PyTorch compatible si elle est proposée.'
