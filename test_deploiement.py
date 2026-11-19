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

    def test_cuda_requires_memory_and_driver(self):
        self.assertEqual(installer.plan(self.host(vram=8192))['device'], 'cuda')
        self.assertEqual(installer.plan(self.host(vram=8192, driver='560.0'))['device'], 'cpu')
        self.assertFalse(installer.plan(self.host(vram=4096), device='cuda')['supported'])

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
        command = ['cmd', '/c', str(ROOT / 'lancer.bat'), '--no-browser'] if os.name == 'nt' else [sys.executable, str(ROOT / 'lancer.py'), '--no-browser']
        with tempfile.TemporaryDirectory(prefix='studio launch ') as directory, tempfile.TemporaryFile() as logs:
            process = subprocess.Popen(command, cwd=directory, env=env, stdout=logs, stderr=logs)
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


if __name__ == '__main__':
    unittest.main()
