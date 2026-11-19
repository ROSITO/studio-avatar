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
        result = subprocess.check_output(['nvidia-smi', '--query-gpu=name,memory.total,driver_version',
            '--format=csv,noheader,nounits'], text=True, timeout=10)
        output = []
        for line in result.splitlines():
            name, memory, driver = [value.strip() for value in line.rsplit(',', 2)]
            output.append(dict(name=name, vram_mib=int(memory), driver=driver))
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
    if any(g['vram_mib'] >= 8192 and int(g['driver'].split('.')[0]) >= 570 for g in host['nvidia']):
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
    return apple if backend in ('ltx-mlx', 'mlx-audio', 'mflux', 'wan-mps', 'musetalk-mps') else False
