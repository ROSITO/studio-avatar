"""Check Git-tracked content only; local runtime data must remain untracked."""
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
files = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
private_dirs = {'performances', 'voix', 'sources', 'audios', 'clips', 'ponts', 'sequences', 'lipsync', 'videos', 'projets', 'taches', 'models'}
errors = []
for name in filter(None, files):
    p = Path(name)
    if p.parts[0] in private_dirs or p.name in {'taches.json', '.env', 'brandkit.png', 'modeles.json', '.modeles-etat.json', '.modeles-plans.json'} or p.suffix in {'.mp4', '.wav', '.mp3', '.pth', '.safetensors'}:
        errors.append(name + ': private/runtime artifact')
    data = (root / p).read_bytes()
    # Assembled patterns keep this checker from matching itself.
    for pattern in (b'/' + b'Users/', b'/' + b'Volumes/', b'gh' + b'p_', b'gh' + b'o_', b'-----BEGIN ' + b'PRIVATE KEY-----'):
        if pattern in data:
            errors.append(name + ': personal path or credential marker')
if errors:
    raise SystemExit('\n'.join(errors))
print('Publication boundary OK: no tracked personal runtime data or credential markers.')
