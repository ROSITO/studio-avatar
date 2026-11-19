"""Conversion locale voix vers voix, modèles personnels déclarés hors du code."""
import json
import os
from pathlib import Path
import time
import uuid

class Atelier:
    def __init__(self, studio):
        self.s = studio
        self.configuration = studio.ICI / 'voix' / 'conversion.json'

    def config(self):
        return json.loads(self.configuration.read_text()) if self.configuration.exists() else {'modeles': []}

    def etat(self):
        c = self.config()
        runtime = Path(c.get('runtime', ''))
        models = []
        for m in c.get('modeles', []):
            ok = all(Path(m.get(k, '')).is_file() for k in ('poids', 'index')) and (runtime / '.venv/bin/python').is_file() and (runtime / 'infer/cli.py').is_file()
            models.append(dict(id=m['id'], nom=m['nom'], disponible=ok))
        return dict(modeles=models)

    def demander(self, d):
        c = self.config()
        m = next((m for m in c.get('modeles', []) if m['id'] == d.get('modele')), None)
        if not m or not any(x['id'] == m['id'] and x['disponible'] for x in self.etat()['modeles']):
            raise ValueError('Modèle de conversion indisponible. Vérifiez le disque des poids et le runtime RVC.')
        dossier = d.get('dossier')
        nom = d.get('source', '')
        if dossier not in ('audios', 'performances', 'videos') or Path(nom).name != nom or not nom:
            raise ValueError('Source audio ou vidéo invalide.')
        src = self.s.ICI / dossier / nom
        if not src.is_file() or src.suffix.lower() not in ('.wav','.mp3','.m4a','.flac','.ogg','.mp4','.mov','.m4v','.webm'):
            raise ValueError('Source introuvable ou format non pris en charge.')
        duration = self.s.duree(src)
        if not 0 < duration <= 600:
            raise ValueError('Choisissez un extrait de dix minutes maximum.')
        pitch = d.get('pitch', 0)
        if isinstance(pitch, bool) or not isinstance(pitch, int) or not -12 <= pitch <= 12:
            raise ValueError('La hauteur doit être un entier entre −12 et +12 demi-tons.')
        t = dict(id=uuid.uuid4().hex[:8], type='conversion', etat='en attente', cree=time.time(), params=dict(source=nom,dossier=dossier,modele=m['id'],nom_voix=m['nom'],pitch=pitch), conversion=dict(runtime=c['runtime'], **m))
        with self.s.VERROU: self.s.TACHES.append(t)
        self.s.sauver()
        return dict(id=t['id'])

    def executer(self, t):
        p, m = t['params'], t['conversion']
        root = self.s.ICI
        src = root / p['dossier'] / p['source']
        out = root / 'audios' / ('conversion-' + t['id'] + '.wav')
        temp = root / 'audios' / ('.conversion-' + t['id'] + '.wav')
        extrait = root / 'audios' / ('.source-' + t['id'] + '.wav')
        video = src.suffix.lower() in ('.mp4','.mov','.m4v','.webm')
        target = root / 'videos' / ('conversion-' + t['id'] + '.mp4')
        try:
            t['etape'] = 'Extraction de la voix source'; self.s.sauver()
            self.s.lancer(t, ['ffmpeg','-v','error','-y','-i',src,'-vn','-ac','1','-ar','22050',extrait])
            t['etape'] = 'Conversion RVC · ' + m['nom']; self.s.sauver()
            runtime = Path(m['runtime'])
            self.s.lancer(t, [runtime/'.venv/bin/python','-u',root/'lancer_conversion.py',runtime,m['poids'],m['index'],extrait,temp,str(p['pitch'])], env={'STUDIO_TTS_EFFECTIVE_LIMIT':str(12*1024**3)})
            if not temp.is_file() or temp.stat().st_size < 100: raise RuntimeError('RVC n’a pas produit d’audio.')
            t['etape'] = 'Finalisation'; self.s.sauver()
            self.s.lancer(t, ['ffmpeg','-v','error','-y','-i',temp,'-af',f'apad,atrim=duration={self.s.duree(src)}',out])
            if video:
                self.s.lancer(t, ['ffmpeg','-v','error','-y','-i',src,'-i',out,'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k','-shortest','-movflags','+faststart',target])
            self.s.meta(out, moteur='rvc', modele=m['id'], source=src.name)
            t['resultat'] = dict(audio=out.name, video=target.name if video else None)
        except BaseException:
            out.unlink(missing_ok=True); target.unlink(missing_ok=True)
            raise
        finally:
            temp.unlink(missing_ok=True); extrait.unlink(missing_ok=True)
