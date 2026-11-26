"""Host selection and a real launcher/server smoke test without model downloads."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

import installer
import memoire

ROOT = Path(__file__).resolve().parent


class SelectionTest(unittest.TestCase):
    def host(self, system='Windows', arch='amd64', vram=0, driver='580.0'):
        return dict(os=system, arch=arch, ram_gib=32, nvidia=[dict(name='test', vram_mib=vram, driver=driver)] if vram else [])

    def test_elitebook_small_gpu_uses_cpu(self):
        result = installer.plan(self.host(vram=4096))
        self.assertTrue(result['supported'])
        self.assertEqual((result['engine'], result['device']), ('omnivoice', 'cpu'))
        self.assertEqual(result['additional_engines'],['qwen-tts'])
        self.assertEqual(installer.plan(self.host(vram=4096),'qwen-tts')['environment'],'.venv-qwen')
        self.assertEqual(installer.plan(self.host(vram=4096),'qwen-tts')['device'],'cpu')

    def test_cuda_requires_memory_and_driver(self):
        self.assertEqual(installer.plan(self.host(vram=8192))['device'], 'cuda')
        self.assertEqual(installer.plan(self.host(vram=8192, driver='560.0'))['device'], 'cpu')
        self.assertFalse(installer.plan(self.host(vram=4096), device='cuda')['supported'])

    def test_explicit_cpu_omits_visual_engines_on_cuda_host(self):
        host = self.host(vram=12288)
        host['nvidia'][0]['compute_cap'] = 8.6
        self.assertEqual(installer.plan(host)['additional_engines'], ['qwen-tts', 'ltx', 'image'])
        self.assertEqual(installer.plan(host, device='cpu')['additional_engines'], ['qwen-tts'])

    def test_mlx_only_on_apple(self):
        self.assertFalse(installer.plan(self.host(), 'mlx')['supported'])
        self.assertFalse(installer.plan(self.host(), 'animation')['supported'])
        self.assertEqual(installer.plan(self.host('Darwin', 'arm64'))['engine'], 'mlx')
        self.assertFalse(installer.plan(self.host('Windows', 'arm64'))['supported'])

    def test_memory_probe(self):
        self.assertGreater(memoire.physique(), 0)
        self.assertGreater(memoire.disponible(), 0)
        self.assertGreater(memoire.empreinte(os.getpid()), 0)


class InstallationRetryTest(unittest.TestCase):
    def test_interrupted_managed_install_can_be_retried(self):
        host = dict(os='Windows', arch='amd64', ram_gib=32, nvidia=[])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(installer, 'ROOT', root), patch.object(installer, 'machine', return_value=host), \
                 patch.object(sys, 'argv', ['installer.py', '--device', 'cpu']), \
                 patch.object(sys, 'version_info', (3, 13)), \
                 patch.object(installer.shutil, 'which', return_value='available'), \
                 patch.object(installer.venv, 'EnvBuilder'), \
                 patch.object(installer.subprocess, 'run') as run:
                run.side_effect = subprocess.CalledProcessError(1, 'pip')
                with self.assertRaises(subprocess.CalledProcessError):
                    installer.main()
                runtime = root / '.venv-omnivoice'
                self.assertTrue((runtime / '.studio-managed.json').exists())
                self.assertFalse((runtime / '.studio-installation.json').exists())
                run.side_effect = None
                self.assertEqual(installer.main(), 0)
                self.assertEqual(json.loads((runtime / '.studio-installation.json').read_text())['device'], 'cpu')
                installer.venv.EnvBuilder.return_value.create.side_effect = subprocess.CalledProcessError(1, 'ensurepip')
                with self.assertRaises(subprocess.CalledProcessError):
                    installer.main()
                self.assertFalse((runtime / '.studio-installation.json').exists())

    def test_existing_runtime_keeps_its_python_abi(self):
        host = dict(os='Windows', arch='amd64', ram_gib=32, nvidia=[])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); runtime = root / '.venv-omnivoice'; runtime.mkdir()
            marker = runtime / '.studio-installation.json'
            marker.write_text('{"device": "cpu"}', encoding='utf-8')
            config = runtime / 'pyvenv.cfg'
            config.write_text('version = 3.12.10\n', encoding='utf-8')
            with patch.object(installer, 'ROOT', root), patch.object(installer, 'machine', return_value=host), \
                 patch.object(sys, 'argv', ['installer.py', '--engine', 'omnivoice']), \
                 patch.object(sys, 'version_info', (3, 13)), \
                 patch.object(installer.shutil, 'which', return_value='available'), \
                 patch.object(installer.venv, 'EnvBuilder') as builder:
                with self.assertRaisesRegex(SystemExit, 'Python 3.12.10'):
                    installer.main()
                builder.assert_not_called()
            self.assertEqual(config.read_text(encoding='utf-8'), 'version = 3.12.10\n')
            self.assertTrue(marker.is_file())

    def test_unmanaged_runtime_is_preserved(self):
        host = dict(os='Windows', arch='amd64', ram_gib=32, nvidia=[])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); runtime = root / '.venv-omnivoice'; runtime.mkdir()
            sentinel = runtime / 'existing.txt'; sentinel.write_text('keep')
            with patch.object(installer, 'ROOT', root), patch.object(installer, 'machine', return_value=host), \
                 patch.object(sys, 'argv', ['installer.py']), patch.object(sys, 'version_info', (3, 13)), \
                 patch.object(installer.shutil, 'which', return_value='available'), \
                 patch.object(installer.subprocess, 'run') as run:
                with self.assertRaises(SystemExit):
                    installer.main()
                run.assert_not_called()
                self.assertEqual(sentinel.read_text(), 'keep')


class LauncherTest(unittest.TestCase):
    def test_launch_from_another_directory_and_query_api(self):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
        env = dict(os.environ, STUDIO_PORT=str(port), PYTHONUTF8='1')
        # Test the actual batch entry point on Windows, including a path with spaces.
        command = ['cmd', '/d', '/c', 'call', str(ROOT / 'lancer.bat'), '--no-browser'] if os.name == 'nt' else [sys.executable, str(ROOT / 'lancer.py'), '--no-browser']
        with tempfile.TemporaryDirectory(prefix='studio launch ') as directory, tempfile.TemporaryFile() as logs:
            uploaded = None
            process = subprocess.Popen(command, cwd=directory, env=env, stdin=subprocess.DEVNULL, stdout=logs, stderr=logs)
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            try:
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        logs.seek(0); self.fail(logs.read().decode(errors='replace'))
                    try:
                        with opener.open(f'http://127.0.0.1:{port}/api/projets', timeout=1) as response:
                            json.load(response)
                        break
                    except OSError:
                        time.sleep(.2)
                else:
                    self.fail('Server not ready after 30 seconds')
                for route in ('/', '/api/modeles', '/api/voix'):
                    with opener.open(f'http://127.0.0.1:{port}{route}', timeout=10) as response:
                        self.assertEqual(response.status, 200)
                # Exercise the reported workflow: PUT a JPEG, refresh the library,
                # then fetch the image displayed in Mes avatars.
                ffmpeg = 'ffmpeg'
                if os.name == 'nt':
                    dependencies = json.loads((ROOT / 'windows-dependencies.json').read_text(encoding='utf-8'))
                    portable = Path(os.environ['LOCALAPPDATA']) / 'StudioAvatar' / 'tools' / dependencies['ffmpeg']['directory'] / 'bin' / 'ffmpeg.exe'
                    if portable.is_file():
                        ffmpeg = str(portable)
                jpeg = subprocess.check_output([ffmpeg, '-v', 'error', '-f', 'lavfi',
                    '-i', 'color=c=blue:s=16x16', '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'mjpeg', '-'])
                name = f'test-import-{port}.jpg'
                request = urllib.request.Request(f'http://127.0.0.1:{port}/api/envoi?dossier=sources&nom={name}', data=jpeg, method='PUT')
                with opener.open(request, timeout=5) as response:
                    uploaded = json.load(response)['nom']
                with opener.open(f'http://127.0.0.1:{port}/api/etat', timeout=10) as response:
                    state = json.load(response)
                self.assertIn(uploaded, [item['nom'] for item in state['fichiers']['sources']])
                with opener.open(f'http://127.0.0.1:{port}/f/sources/{uploaded}', timeout=5) as response:
                    self.assertEqual(response.headers['Content-Type'], 'image/jpeg')
                    self.assertEqual(response.read(), jpeg)
                with self.assertRaises(urllib.error.HTTPError) as error:
                    opener.open(f'http://127.0.0.1:{port}/f/audios/..%5Cstudio.py', timeout=2)
                self.assertEqual(error.exception.code, 404)
                error.exception.close()
            finally:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
                else:
                    process.send_signal(__import__('signal').SIGINT)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait()
                if uploaded:
                    (ROOT / 'sources' / uploaded).unlink(missing_ok=True)


if __name__ == '__main__':
    unittest.main()
