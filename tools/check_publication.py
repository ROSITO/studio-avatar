"""Check Git-tracked content only; local runtime data must remain untracked."""
from pathlib import Path
import subprocess
import re

root = Path(__file__).resolve().parents[1]
files = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
private_dirs = {'performances', 'voix', 'sources', 'audios', 'clips', 'ponts', 'sequences', 'lipsync', 'videos', 'projets', 'taches', 'models', 'modeles', 'portraits', 'references'}
errors = []
for name in filter(None, files):
    p = Path(name)
    if p.parts[0] in private_dirs or p.name in {'taches.json', '.studio-python.txt', '.env', 'brandkit.png', 'modeles.json', '.modeles-etat.json', '.modeles-plans.json'} or p.suffix.lower() in {'.mp4', '.wav', '.mp3', '.pth', '.pt', '.ckpt', '.safetensors', '.pem', '.key', '.p12', '.pfx'}:
        errors.append(name + ': private/runtime artifact')
    data = (root / p).read_bytes()
    if (p.name.startswith('.env') and p.name != '.env.example') or p.parts[0] in {'.ssh', '.aws'}:
        errors.append(name + ': private configuration')
    for pattern in (rb'AKIA' + rb'[A-Z0-9]{16}', rb'github_' + rb'pat_[A-Za-z0-9_]{20,}', rb'hf' + rb'_[A-Za-z0-9]{30,}', rb'sk' + rb'-(?:proj-)?[A-Za-z0-9_-]{32,}', rb'-----BEGIN (?:RSA |EC |OPENSSH )?' + rb'PRIVATE KEY-----'):
        if re.search(pattern, data): errors.append(name + ': possible credential (value redacted)')
    # Assembled patterns keep this checker from matching itself.
    for pattern in (b'/' + b'Users/', b'/' + b'Volumes/', b'gh' + b'p_', b'gh' + b'o_', b'-----BEGIN ' + b'PRIVATE KEY-----'):
        if pattern in data:
            errors.append(name + ': personal path or credential marker')
if errors:
    raise SystemExit('\n'.join(errors))
print('Publication boundary OK: no tracked personal runtime data or credential markers.')
