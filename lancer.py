"""Portable launcher: validate prerequisites, wait for readiness, open the UI."""
import argparse
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    if sys.version_info < (3, 10):
        print('Python 3.10+ requis.', file=sys.stderr)
        return 1
    missing = [name for name in ('ffmpeg', 'ffprobe') if not shutil.which(name)]
    if missing:
        print('Installez FFmpeg et ajoutez ffmpeg et ffprobe au PATH : ' + ', '.join(missing), file=sys.stderr)
        return 1
    try:
        port = int(os.environ.get('STUDIO_PORT', '8765'))
        if not 1 <= port <= 65535:
            raise ValueError()
    except ValueError:
        print('STUDIO_PORT doit etre un entier entre 1 et 65535.', file=sys.stderr)
        return 1
    try:
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', port))
    except OSError:
        print(f'Port {port} indisponible. Fermez le serveur existant ou changez STUDIO_PORT.', file=sys.stderr)
        return 1
    root = Path(__file__).resolve().parent
    url = f'http://127.0.0.1:{port}'
    env = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    process = subprocess.Popen([sys.executable, '-X', 'utf8', str(root / 'studio.py')], cwd=root, env=env)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        deadline = time.monotonic() + 30
        while process.poll() is None and time.monotonic() < deadline:
            try:
                with opener.open(url + '/api/projets', timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(.2)
        else:
            print('Le serveur ne demarre pas. Consultez les erreurs ci-dessus.', file=sys.stderr)
            return 1
        print(f'Studio Avatar : {url}', flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        return process.wait()
    except KeyboardInterrupt:
        return 0
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == '__main__':
    raise SystemExit(main())
