"""Video-driven character animation: validated inputs and isolated, supervised jobs."""
import json
import math
import os
from pathlib import Path
import secrets
import shutil
import time
import uuid

MODEL_ID = 'wan-animate2'
MODEL_REPO = 'Wan-AI/Wan2.2-Animate-2-14B-Diffusers'
RUNTIME_REVISION = '14f482c30c91021cc0e363a0a17a115b44972aee'


def plafond():
    import memoire
    try: asked = float(os.environ.get('STUDIO_ANIMATION_MAX_RAM_GB', '12'))
    except ValueError: raise ValueError('Budget animation invalide.')
    if not math.isfinite(asked) or asked <= 0: raise ValueError('Budget animation invalide.')
    return int(min(asked * memoire.GIB, memoire.physique() / 2))


def budget(diagnostic=False):
    import memoire
    cap=plafond()
    minimum=(2 if diagnostic else 10)*memoire.GIB
    if cap<minimum:raise ValueError('Budget de calcul Wan insuffisant : augmentez STUDIO_ANIMATION_MAX_RAM_GB.')
    if memoire.pression()>=4 or memoire.disponible()<4*memoire.GIB:
        raise ValueError('Moins de 4 Gio disponibles ou pression mémoire critique : essai Wan refusé.')
    # Available-memory estimates fluctuate with file caches and compressible apps.
    # Keep the configured process ceiling, with admission and live pressure guards.
    return cap


class Atelier:
    def __init__(self, studio): self.s = studio

    def runtime(self):
        return Path(os.environ.get('STUDIO_ANIMATION_PYTHON', str(self.s.ICI / '.venv-animation/bin/python'))).expanduser()

    def modele(self):
        e = self.s.GESTION_MODELES.entry(MODEL_ID)
        return self.s.GESTION_MODELES.path(e)

    def etat(self):
        e = self.s.GESTION_MODELES.entry(MODEL_ID)
        path = self.modele()
        try:
            marker=json.loads((self.runtime().parent.parent/'.studio-animation-runtime.json').read_text())
        except (OSError,ValueError):marker={}
        runtime = self.runtime().is_file() and marker.get('revision')==RUNTIME_REVISION
        installed = self.s.GESTION_MODELES.valid(e, path)
        transfer=self.s.GESTION_MODELES.etat
        downloading=transfer.get('id')==MODEL_ID and transfer.get('statut') in ('analyse','telechargement','verification')
        memory_error=''
        if runtime and installed:
            try:budget()
            except ValueError as exc:memory_error=str(exc)
        return dict(modele=MODEL_ID, installe=installed, runtime=runtime, experimental=True,
                    pret=runtime and installed and not memory_error, limite_secondes=3, budget_go=round(plafond()/1024**3,1),
                    raison=memory_error or ('Prêt pour un essai expérimental de 1 à 3 secondes.' if runtime and installed else
                    'Téléchargement en cours : progression dans Modèles.' if downloading else
                    'Installez les poids dans Modèles.' if runtime else 'Installez le moteur avec python3 installer_animation.py.'),
                    capacites=['transfert_performance'],
                    note='Le personnage reprend la performance dans le décor de son image. Le remplacement dans le décor original n’est pas encore proposé.')

    def fichier(self, folder, name):
        if not isinstance(name, str) or not name or Path(name).name != name or name.startswith('.') or '\\' in name:
            raise ValueError('Nom de fichier invalide.')
        root = (self.s.ICI / folder).resolve()
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file(): raise ValueError('Fichier introuvable.')
        return path

    def valider(self, d):
        image = self.fichier('sources', d.get('avatar'))
        video = self.fichier('performances', d.get('video'))
        if image.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp'): raise ValueError('Image d’avatar requise.')
        if video.suffix.lower() not in ('.mp4', '.mov', '.m4v', '.webm'): raise ValueError('Vidéo MP4, MOV ou WebM requise.')
        try: start, length = float(d.get('debut', 0)), float(d.get('duree', 1))
        except (TypeError, ValueError): raise ValueError('Début ou durée invalide.')
        total = self.s.duree(video)
        if not all(math.isfinite(x) for x in (start, length, total)) or start < 0 or not 1 <= length <= 3 or start + length > total + .04:
            raise ValueError('Choisissez un extrait de 1 à 3 secondes situé dans la vidéo.')
        prompt = str(d.get('prompt', '')).strip()
        if not prompt or len(prompt) > 2000: raise ValueError('Décrivez l’apparence de l’avatar et son décor (1 à 2000 caractères).')
        seed = d.get('seed')
        if seed is None: seed = secrets.randbelow(2**31)
        if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**31: raise ValueError('Seed invalide.')
        return dict(avatar=image.name, video=video.name, debut=start, duree=length, prompt=prompt, seed=seed,
                    conserver_audio=bool(d.get('conserver_audio', True)))

    def demander(self, d, diagnostic=False):
        params = self.valider(d)
        status=self.etat()
        if not status['pret'] and not (diagnostic and status['runtime'] and status['installe']): raise ValueError(status['raison'])
        budget(diagnostic=diagnostic)  # Also checked again when the queue reaches this job.
        t = dict(id=uuid.uuid4().hex[:12], type='animation', params=params, etat='en attente', cree=time.time(),
                 diagnostic_run=bool(diagnostic), modeles={'animation': dict(id=MODEL_ID, path=str(self.modele()), installe=True)})
        with self.s.VERROU: self.s.TACHES.append(t)
        self.s.sauver()
        return t

    def executer(self, t):
        import tempfile
        cap = budget(diagnostic=t.get('diagnostic_run',False))
        p = self.valider(t['params'])
        model = t['modeles']['animation']
        if not self.s.GESTION_MODELES.valid(self.s.GESTION_MODELES.entry(MODEL_ID), Path(model['path'])):
            raise ValueError('Les poids Wan-Animate-2 sont incomplets ou le disque est déconnecté.')
        if shutil.disk_usage(model['path']).free < 2*1024**3:
            raise ValueError('Gardez au moins 2 Go libres sur le disque des modèles pour les fichiers temporaires.')
        out = self.s.ICI / 'videos' / ('animation-' + t['id'] + '.mp4')
        with tempfile.TemporaryDirectory(prefix='.animation-', dir=self.s.ICI / 'performances') as tmp:
            tmp = Path(tmp)
            clip, raw, mux = tmp / 'extrait.mp4', tmp / 'muet.mp4', tmp / 'final.mp4'
            t['etape'] = 'Préparation de l’extrait'; self.s.sauver()
            self.s.lancer(t, ['ffmpeg', '-v', 'error', '-y', '-ss', p['debut'], '-i', self.fichier('performances', p['video']),
                              '-t', p['duree'], '-an', '-vf', 'fps=24,scale=384:384:force_original_aspect_ratio=decrease,pad=ceil(iw/2)*2:ceil(ih/2)*2',
                              '-c:v', 'libx264', '-pix_fmt', 'yuv420p', clip])
            request = tmp / 'requete.json'
            request.write_text(json.dumps(dict(image=str(self.fichier('sources', p['avatar'])), video=str(clip),
                                              model=model['path'], output=str(raw), prompt=p['prompt'], seed=p['seed'],
                                              max_ram=cap, seconds=p['duree'], diagnostic_run=t.get('diagnostic_run',False))))
            t['etape'] = 'Diagnostic technique Wan-Animate-2 · une étape' if t.get('diagnostic_run') else 'Transfert de performance Wan-Animate-2 · expérimental'; self.s.sauver()
            self.s.lancer(t, [self.runtime(), '-u', self.s.ICI / 'lancer_animation.py', request],
                          {'STUDIO_ANIMATION_EFFECTIVE_LIMIT': str(cap), 'HF_HOME': str(self.s.MODELES / 'huggingface'),
                           'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'PYTORCH_ENABLE_MPS_FALLBACK': '1'})
            t['etape'] = 'Export avec la voix d’origine' if p['conserver_audio'] else 'Export vidéo'; self.s.sauver()
            cmd = ['ffmpeg', '-v', 'error', '-y', '-i', raw]
            if p['conserver_audio']:
                cmd += ['-ss', p['debut'], '-i', self.fichier('performances', p['video']), '-map', '0:v:0', '-map', '1:a:0?', '-c:a', 'aac']
            cmd += ['-t', p['duree'], '-c:v', 'copy', '-movflags', '+faststart', mux]
            self.s.lancer(t, cmd)
            mux.replace(out)
        self.s.meta(out, synthetique=True, moteur=MODEL_ID, diagnostic_run=t.get('diagnostic_run',False),
                    nom='Diagnostic technique Wan (qualité non évaluée)' if t.get('diagnostic_run') else 'Performance · '+Path(p['avatar']).stem, **p)
        t['resultat'] = dict(fichier=out.name, seed=p['seed'], duree=self.s.duree(out), diagnostic_run=t.get('diagnostic_run',False))
