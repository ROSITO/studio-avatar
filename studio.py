#!/usr/bin/env python3
"""Studio avatar : clips LTX-2.3 (local), ponts de retour à la pose, séquence continue, lipsync MuseTalk 1.5.
Serveur local sans dépendance (Python ≥ 3.10) + une page web. Lancer : python3 studio.py  → http://localhost:8765
Une seule tâche GPU à la fois (file d'attente)."""
import balises
import functools, json, math, os, re, secrets, shutil, subprocess, threading, time, uuid
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

ICI = Path(__file__).resolve().parent
# Configure external engines without storing machine-specific paths in source control.
import sys
LTX = Path(os.environ.get('STUDIO_LTX_BIN', 'ltx-2-mlx')).expanduser()
MODELES = Path(os.environ.get('STUDIO_MODELS_DIR', str(Path.home() / '.cache/studio-avatar/models'))).expanduser()
MUSE_PY = Path(os.environ.get('STUDIO_MUSE_PYTHON', sys.executable)).expanduser()
CV_PY = Path(os.environ.get('STUDIO_CV_PYTHON', sys.executable)).expanduser()
FFMPEG_BIN = os.environ.get('STUDIO_FFMPEG_BIN', '')
VOICESTUDIO = os.environ.get('STUDIO_VOICE_URL', 'http://127.0.0.1:3900').rstrip('/')
PORT = int(os.environ.get('STUDIO_PORT', '8765'))
MFLUX = Path(os.environ.get('STUDIO_MFLUX_BIN', str(Path(sys.executable).parent))).expanduser()   # dossier des commandes mflux-generate-*
MODELES_IMAGE = Path(os.environ['STUDIO_IMAGE_MODELS_DIR']).expanduser() if os.environ.get('STUDIO_IMAGE_MODELS_DIR') else None   # poids FLUX déjà installés ailleurs
DOSSIERS = ['sources', 'audios', 'clips', 'ponts', 'sequences', 'lipsync', 'videos', 'portraits', 'references', 'performances']
for d in DOSSIERS: (ICI / d).mkdir(exist_ok=True)

# Recettes validées sur la vidéo VoiceStudio (19/10/2026)
# Consignes neutres : on garde la personne et le décor de la photo tels quels (pas de « canapé » imposé).
BASE_CLIP = ("A YouTuber seated and facing the camera, exactly the same person, clothes and setting as in the image, with calm, composed body language. "
             "Her mouth stays closed for the entire video: her lips remain pressed gently together, she does not speak and her lips do not move. "
             "She keeps her head upright and her face turned straight toward the camera the whole time (no head tilt, no turning away). "
             "Her hands rest still on her lap the whole time: no hand gestures, her hands never move. "
             "Slow, soft, natural movements. Static camera, the background stays exactly the same.")
BASE_PONT = ("A YouTuber seated and facing the camera, exactly the same person, clothes and setting as in the image. Her mouth stays closed, her lips remain gently together and do not move. "
             "She calmly and smoothly settles back into her starting position, exactly as in the image, looking straight into the camera. "
             "Slow natural motion. Static camera, the background stays exactly the same.")
# Moteur a2v (photo + voix -> vidéo parlante, testé le 20/10/2026) : la bouche suit la voix, pas de MuseTalk.
BASE_PARLE = ("A YouTuber seated and facing the camera, exactly the same person, clothes and setting as in the image, "
              "talking naturally to the camera, her lips moving in sync with her speech. "
              "She keeps her head upright and her face turned straight toward the camera the whole time. "
              "Her hands rest still on her lap the whole time: no hand gestures, her hands never move. Static camera, the background stays exactly the same.")

# Portrait d'avatar : la pose dont a2v et MuseTalk ont besoin (de face, tête droite, bouche fermée, mains basses).
BASE_PORTRAIT = ("Photorealistic portrait photo of one person seated and facing the camera, centered in a vertical frame, "
                 "head upright, looking straight into the lens, mouth closed, relaxed natural expression, "
                 "both hands resting low on the lap and visible, upper body and knees in frame, calm uncluttered background, soft natural light.")
ROLES_REF = {'visage': 'the face, hair and skin tone of the person', 'tenue': 'the clothing', 'decor': 'the setting and background', 'style': 'the lighting and photographic style'}

# Gestes : visage et tête seulement, mains immobiles (un geste de main se raccorde mal dans les ponts).
# Ni bouche ni mains ici : la base du moteur (BASE_PARLE / BASE_CLIP) les fixe.
GESTES = {
    'hochement': 'She nods gently twice with a calm, friendly look.',
    'curieux': 'Looking straight into the camera with her head perfectly still and centered, she simply raises her eyebrows with an intrigued expression.',
    'sourire': 'Her face lights up: bright, lively eyes, raised eyebrows and a warm smile, with one small energetic nod.',
    'reflexion': 'She looks thoughtful, briefly lowering her eyes as if thinking, then looks back into the camera with a slight smile.',
    'penchee': 'She leans slightly forward toward the camera with an attentive, serious look, then gently sits back.',
    'vers-la-camera': 'She raises her eyebrows softly, smiles warmly and nods once in acknowledgement.',
}
# Clip « repos » : ancré au début ET à la fin (le mouvement reste minime) -> on peut le couper n'importe où,
# il comble les silences et les fins de phrase sans saut.
REPOS = 'She stays still and relaxed, breathing calmly and blinking naturally, with only very small natural movements of her head.'

# Situations : chacune correspond aux balises de ton de la voix ([curious], [excited]… comme ElevenLabs v4).
# (clé, libellé, emoji, balises reconnues, gestes de la préparation)
TONS = [
    ('neutre', 'Neutre', '😐', ['neutral', 'neutre', 'calm', 'calme'], ['hochement']),
    ('curieux', 'Curieux', '🤔', ['curious', 'curieux', 'questioning', 'intrigued'], ['curieux']),
    ('enthousiaste', 'Enthousiaste', '🤩', ['excited', 'enthousiaste', 'happy', 'enthusiastic', 'cheerful'], ['sourire']),
    ('reflechi', 'Réfléchi', '💭', ['thoughtful', 'reflechi', 'réfléchi', 'pensive', 'reflective'], ['reflexion']),
    ('serieux', 'Sérieux', '🧐', ['serious', 'serieux', 'sérieux', 'concerned', 'firm'], ['penchee']),
    ('chaleureux', 'Chaleureux', '😊', ['warm', 'chaleureux', 'friendly', 'kind', 'gentle'], ['vers-la-camera']),
]
TON_DU_GESTE = {g: k for k, *_, gs in TONS for g in gs} | {'une-main': 'neutre', 'paumes-ouvertes': 'enthousiaste', 'mains-jointes': 'reflechi'}   # anciens clips de bibliothèque (gestes de mains retirés)
BALISES = {b: k for k, _, _, bs, _ in TONS for b in bs + [k]}

TACHES, VERROU = [], threading.Lock()
EN_COURS = {'proc': None, 'id': None}
FICHIER_TACHES = ICI / 'taches.json'
if FICHIER_TACHES.exists():
    TACHES = json.loads(FICHIER_TACHES.read_text())
    for t in TACHES:
        if t['etat'] == 'en cours': t['etat'] = 'en attente'   # reprise après redémarrage : la tâche repart de zéro

def sauver():
    with VERROU: FICHIER_TACHES.write_text(json.dumps(TACHES, ensure_ascii=False, indent=1))

def nom_sur(s): return re.sub(r'[^A-Za-z0-9._-]+', '-', s).strip('-') or 'sans-nom'

def duree(p):
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(p)], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)

@functools.lru_cache(maxsize=4096)
def _duree_fichier(chemin, mtime_ns, taille): return duree(chemin)
def duree_cache(f):
    """Durée relue seulement si le fichier change : /api/etat lançait un ffprobe par média à chaque rafraîchissement."""
    st = f.stat(); return _duree_fichier(str(f), st.st_mtime_ns, st.st_size)

def taille_image(p):
    r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', str(p)], capture_output=True, text=True)
    w, h = r.stdout.strip().split(',')[:2]; return int(w), int(h)

def resolution(src, aire=576 * 896):
    """Garde le format de l'image, multiples de 32, environ 576 × 896 pixels (testé : ~7 min pour 4 s)."""
    w, h = taille_image(src); ar = w / h
    W = max(256, round((aire * ar) ** 0.5 / 32) * 32); H = max(256, round((aire / ar) ** 0.5 / 32) * 32)
    return W, H

def mouvement(p):
    """Écart max à la 1re image (0-255). Repères : figé ≈ 1,6 ; geste doux validé ≈ 25."""
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(p), '-vf', 'scale=96:144,format=gray', '-f', 'rawvideo', '-'], capture_output=True).stdout
    n = 96 * 144; fr = [raw[i:i + n] for i in range(0, len(raw) - n + 1, n)]
    if not fr: return 0
    f0 = fr[0]; return round(max(sum(abs(a - b) for a, b in zip(f0[::5], x[::5])) / len(f0[::5]) for x in fr[::6]), 1)

def apercu(p):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(p), '-vf', "select='not(mod(n\\,12))',scale=-2:200,tile=9x1", '-frames:v', '1', str(p.with_suffix('.jpg'))])

def meta(p, **kw):
    m = p.with_suffix('.json'); d = json.loads(m.read_text()) if m.exists() else {}
    d.update(kw); m.write_text(json.dumps(d, ensure_ascii=False, indent=1)); return d

def lancer(t, cmd, env=None):
    if t.get("annuler"): raise RuntimeError("Tâche annulée")
    with open(ICI / 'taches' / f"{t['id']}.log", 'a') as log:
        log.write('$ ' + ' '.join(map(str, cmd)) + '\n'); log.flush()
        p = subprocess.Popen([str(c) for c in cmd], stdout=log, stderr=subprocess.STDOUT, env={**os.environ, **(env or {})}, cwd=ICI)
        EN_COURS['proc'] = p
        try:
            if env and (env.get('STUDIO_TTS_EFFECTIVE_LIMIT') or env.get('STUDIO_ANIMATION_EFFECTIVE_LIMIT')):
                import memoire
                code=memoire.attendre(p,int(env.get('STUDIO_ANIMATION_EFFECTIVE_LIMIT') or env['STUDIO_TTS_EFFECTIVE_LIMIT']),log)
            else:code=p.wait()
        finally:EN_COURS['proc'] = None
    if t.get('annuler'): raise RuntimeError('Tâche annulée')
    if code==73: raise RuntimeError('Protection mémoire : calcul arrêté pour préserver les applications.')
    if code: raise RuntimeError(f'commande terminée avec le code {code} (voir le journal)')

def ltx(t, images, prompt, W, H, frames, seed, sortie, audio=None):
    """Sans audio : geste muet (generate). Avec audio : vidéo parlante (a2v) ; l'audio doit couvrir les frames/24 s."""
    choix = t.get('modeles') or GESTION_MODELES.selection()
    video, texte = choix['video'], choix['texte']
    if not video['installe']: raise RuntimeError('Installez ou importez le modèle vidéo dans la page Modèles.')
    if not texte['installe']: raise RuntimeError('Installez l’encodeur Gemma dans la page Modèles.')
    cmd = [LTX, 'a2v' if audio else 'generate', '--model', video['path'], '--gemma', texte['path']]
    for img, idx, *force in images: cmd += ['--image', img, idx, force[0] if force else '1.0']
    tmp = sortie.with_suffix('.tmp.mp4')
    cmd += ['--prompt', prompt, '--distilled', '--low-ram', '-H', H, '-W', W, '-f', frames, '--frame-rate', '24', '--seed', seed, '-o', tmp]
    cmd += ['--audio', audio] if audio else ['--no-audio']
    lancer(t, cmd, {'HF_HOME': str(MODELES / 'huggingface'), 'HF_HUB_OFFLINE': '1', 'PATH': (f"{FFMPEG_BIN}:" if FFMPEG_BIN else "") + os.environ['PATH']})
    tmp.rename(sortie)

def portrait(t):
    """FLUX (mflux) : 1 à 4 variantes en un seul chargement du modèle ; refs = [{dossier, nom, role}]."""
    p = t['params']; m = (t.get('modeles') or GESTION_MODELES.selection())['image']
    if not m['installe']: raise RuntimeError('Installez un modèle image (FLUX) dans la page Modèles.')
    refs = []
    for r in p.get('refs', [])[:4]:
        f = ICI / r['dossier'] / nom_sur(r['nom'])
        if r['dossier'] not in ('references', 'sources') or not f.is_file(): raise ValueError('Image de référence introuvable')
        refs.append((f, ROLES_REF.get(r.get('role'), ROLES_REF['visage'])))
    consigne = ' '.join(f'Reference image {k + 1}: copy {role}.' for k, (_, role) in enumerate(refs)) + ' ' + BASE_PORTRAIT + ' ' + p.get('prompt', '')
    if 'seeds' not in t: t['seeds'] = [secrets.randbelow(10 ** 7) for _ in range(max(1, min(4, int(p.get('nombre', 4)))))]; sauver()   # même tirage à la reprise
    flux3 = m['id'].startswith('flux3')
    cmd = [MFLUX / f"mflux-generate-{'flux3' if flux3 else 'flux2'}{'-edit' if refs else ''}", '--model', m['path'], '--prompt', consigne.strip(),
           '--width', 768, '--height', 1200, '--seed', *t['seeds'], '--output', ICI / 'portraits' / f"{t['id']}.png"]   # plusieurs seeds : mflux ajoute _seed_N
    if refs: cmd += ['--image-paths', *[f for f, _ in refs]]
    if not flux3: cmd += ['--steps', 4, '--guidance', '1.0', '--quantize', 8]   # recette Klein distillé
    t['etape'] = 'Génération des portraits'; sauver()
    lancer(t, cmd, {'HF_HUB_OFFLINE': '1'})
    images = sorted(f.name for f in (ICI / 'portraits').glob(f"{t['id']}*.png"))
    if not images: raise RuntimeError('Aucune image produite (voir le journal).')
    t['resultat'] = dict(images=images, modele=m['id'], consigne=consigne.strip())

def faire(t):
    p = t['params']
    if 'modeles' not in t: t['modeles'] = GESTION_MODELES.selection()
    if t['type'].startswith('projet_'):
        projets.executer(t); return
    if t['type'] == 'animation': ATELIER_ANIMATION.executer(t); return
    if t['type'] == 'voix': ATELIER_VOIX.executer(t); return
    if t['type'] == 'portrait': portrait(t); return
    if t['type'] == 'clip':
        src = ICI / 'sources' / p['source']; W, H = resolution(src)
        out = ICI / 'clips' / f"{nom_sur(p['nom'])}.mp4"
        imgs = [(src, 0)] + ([(src, 'last')] if p.get('ancre_fin') else [])
        ltx(t, imgs, f"{p.get('base') or BASE_CLIP} {p['geste']}", W, H, int(p.get('images', 97)), int(p.get('seed', 7)), out)
        apercu(out); t['resultat'] = meta(out, source=p['source'], geste=p['geste'], seed=p.get('seed'), mouvement=mouvement(out), taille=f'{W}x{H}',
                                          ton=p.get('ton') or ('repos' if p.get('ancre_fin') else TON_DU_GESTE.get(p.get('cle', ''))))
    elif t['type'] == 'pont':
        clip = ICI / 'clips' / p['clip']; src_nom = json.loads(clip.with_suffix('.json').read_text())['source']
        fin = ICI / 'ponts' / f"fin-{clip.stem}.png"
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-sseof', '-0.05', '-i', clip, '-frames:v', '1', '-update', '1', fin], check=True)
        W, H = taille_image(clip); out = ICI / 'ponts' / f"pont-{clip.stem}.mp4"
        ltx(t, [(fin, 0), (ICI / 'sources' / src_nom, 'last')], f"{p.get('extra', '')} {BASE_PONT}".strip(), W, H, int(p.get('images', 33)), int(p.get('seed', 5)), out)
        apercu(out); t['resultat'] = meta(out, clip=p['clip'], mouvement=mouvement(out))
    elif t['type'] == 'sequence':
        cible = duree(ICI / 'audios' / p['audio']) if p.get('audio') else float(p['duree'])
        out = ICI / 'sequences' / f"{nom_sur(p['nom'])}.mp4"
        morceaux, tot, k = [], 0.0, 0
        while tot < cible - 0.01:   # clip + sa transition, en boucle jusqu'à la durée
            c = p['clips'][k % len(p['clips'])]; k += 1
            for f in (ICI / 'clips' / c, ICI / 'ponts' / f'pont-{Path(c).stem}.mp4'):
                if f.exists() and tot < cible - 0.01: d = min(duree(f), cible - tot); morceaux.append((f, d)); tot += d
        concat(t, morceaux, out); t['resultat'] = meta(out, morceaux=[f.name for f, _ in morceaux], duree=round(tot, 2))
    elif t['type'] == 'lipsync':
        dossier, video = p['video'].split('/', 1)
        out = ICI / 'lipsync' / f"{nom_sur(p['nom'])}.mp4"
        musetalk(t, ICI / dossier / video, ICI / 'audios' / p['audio'], out, int(p.get('bbox_shift', 0)))
        t['resultat'] = meta(out, video=p['video'], audio=p['audio'])
    elif t['type'] == 'video':   # parcours complet : texte balisé -> voix par segment -> timeline des situations -> lipsync
        nom = nom_sur(p['nom']); segs = segments(p.get('texte', '')); t['etape'] = 'Création de la voix'
        if p.get('audio'):
            audio = p['audio']; total = duree(ICI / 'audios' / audio)
            n = sum(len(balises.parle(x['texte'])) for x in segs) or 1; d0 = 0.0
            for x in segs: x['debut'] = round(d0, 3); d0 += total * len(balises.parle(x['texte'])) / n   # alignement approché au nombre de caractères
        else:
            audio = f'{nom}.wav'; voix_segments(t, segs, p['voix'], p.get('langue', 'fr'), ICI / 'audios' / audio)
            total = duree(ICI / 'audios' / audio)
        seq = ICI / 'sequences' / f'{nom}-sequence.mp4'
        if p.get('mode', 'sur-mesure') == 'sur-mesure':
            plan = sur_mesure(t, p['avatar'], segs, total, seq)
        else:
            if not lib_avatar(p['avatar'])['pret']:
                raise RuntimeError("L'avatar n'a pas de bibliothèque prête pour le mode rapide : choisis le mode sur mesure, ou lance sa préparation.")
            t['etape'] = 'Montage des situations'; sauver()
            plan = timeline(p['avatar'], segs, total)
            concat(t, [(m['fichier'], m['duree']) for m in plan], seq)
        out = ICI / 'videos' / f'{nom}.mp4'; t['etape'] = 'Synchronisation des lèvres'; sauver()
        musetalk(t, seq, ICI / 'audios' / audio, out, 0)
        t['resultat'] = meta(out, avatar=p['avatar'], audio=audio, texte=p.get('texte', ''), segments=segs, plan=[dict(m, fichier=Path(m['fichier']).name) for m in plan])
    elif t['type'] == 'variante':   # une variante de plus pour une situation (clip + sa transition)
        src, ton = p['avatar'], p['ton']; cle = next(gs for k, *_, gs in TONS if k == ton)[0] if ton != 'repos' else 'repos'
        seed = int(time.time()) % 1000; base = Path(src).stem
        t2 = dict(t, params=dict(source=src, geste=REPOS if ton == 'repos' else GESTES[cle], nom=f'{base}-{cle}-v{seed}', seed=seed, images=97, ton=ton, ancre_fin=ton == 'repos'))
        faire(dict(t2, type='clip'))
        if ton != 'repos': faire(dict(t, params=dict(clip=f'{base}-{cle}-v{seed}.mp4', images=33)))

# Mode sur mesure, en PETITS BLOCS INDÉPENDANTS : chaque phrase = un bloc qui part de la photo d'origine
# (jamais d'une image générée : aucune dérive, quelle que soit la longueur), fait le geste de son ton, puis une
# liaison LTX ramène à la photo. Le bloc suivant repart de la photo : collage invisible.
# (Essai du 20/10 en chaîne, chaque phrase partant de la dernière image de la précédente : dérive énorme du visage.)
# Contrôle visage : un geste dont le visage se déplace de plus de 0,2 largeur de visage (tête tournée / penchée,
# mauvais pour le lipsync) est refait avec une autre graine. Étalonné le 20/10 : « curieux » raté 0,22-0,25 ;
# gestes validés 0,06-0,18.
SEUIL_VISAGE, ESSAIS = 0.2, 3
LIAISON = 25                 # images de la liaison vers la photo (≈ 1 s) ; la 1re = image de coupe, non répétée
MIN_BLOC, MAX_BLOC = 2.4, 5.0  # bloc = geste (≥ 1,4 s) + liaison (1 s) ; au-delà de 5 s, plusieurs blocs

def blocs_sur_mesure(segs, total):
    """Phrases -> blocs [{ton, duree, suite}] : phrases < 2,4 s regroupées avec la précédente, > 5 s découpées."""
    bruts = []
    for k, sg in enumerate(segs):
        d = (segs[k + 1]['debut'] if k + 1 < len(segs) else total) - sg['debut']
        if bruts and (d < MIN_BLOC or bruts[-1]['duree'] < MIN_BLOC): bruts[-1]['duree'] += d; continue
        bruts.append(dict(ton=sg['ton'], duree=d))
    out = []
    for b in bruts:
        n = max(1, math.ceil(b['duree'] / MAX_BLOC))
        out += [dict(ton=b['ton'], duree=b['duree'] / n, suite=i > 0) for i in range(n)]
    return out

def images_ltx(n):   # LTX : 8k+1 images, au moins n
    return max(17, math.ceil((n - 1) / 8) * 8 + 1)

def sur_mesure(t, src, segs, total, seq):
    bl = blocs_sur_mesure(segs, total); photo = ICI / 'sources' / src; W, H = resolution(photo)
    tmp = ICI / 'sequences' / f"tmp-{t['id']}"; tmp.mkdir(exist_ok=True); faits, tour, cumul, morceaux = [], {}, 0.0, []
    try:
        for i, b in enumerate(bl):
            n = round((cumul + b['duree']) * 24) - round(cumul * 24); cumul += b['duree']   # arrondi cumulé : pas de glissement
            ng = n - (LIAISON - 1)                                                          # images du geste
            cles = next(gs for k, *_, gs in TONS if k == b['ton']); cle = cles[tour.get(b['ton'], 0) % len(cles)]; tour[b['ton']] = tour.get(b['ton'], 0) + 1
            t['etape'] = f'Bloc {i + 1}/{len(bl)} : geste'; sauver()
            g = tmp / f'{i:03d}-geste.mp4'
            a = 0 if i == 0 else 1   # image 0 du geste = la photo, déjà la dernière image du bloc précédent
            essais = []
            for e in range(ESSAIS):
                ge = tmp / f'{i:03d}-geste-{e}.mp4'
                if e: t['etape'] = f'Bloc {i + 1}/{len(bl)} : geste refait ({e + 1}/{ESSAIS}), visage pas assez de face'; sauver()
                ltx(t, [(photo, 0)], f"{BASE_CLIP} {SUITE if b['suite'] else GESTES[cle]}", W, H, images_ltx(ng + 1), 31 + i + 100 * e, ge)
                v = json.loads(subprocess.run([str(CV_PY), str(ICI / 'visage.py'), str(ge), str(a), str(a + ng)], capture_output=True, text=True).stdout or '{"decalage": 9}')
                essais.append((v['decalage'], ge))
                with open(ICI / 'taches' / f"{t['id']}.log", 'a') as log: log.write(f"bloc {i + 1} essai {e + 1} : visage {v}\n")
                if v['decalage'] <= SEUIL_VISAGE: break
            shutil.copy(min(essais)[1], g)
            coupe = tmp / f'{i:03d}-coupe.png'   # dernière image gardée du geste
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(g), '-vf', f'select=eq(n\\,{a + ng - 1})', '-frames:v', '1', '-update', '1', str(coupe)], check=True)
            t['etape'] = f'Bloc {i + 1}/{len(bl)} : liaison'; sauver()
            l = tmp / f'{i:03d}-liaison.mp4'
            ltx(t, [(coupe, 0), (photo, 'last')], BASE_PONT, W, H, LIAISON, 5 + i, l)
            morceaux += [(g, a, a + ng), (l, 1, LIAISON)]
            faits.append(dict(fichier=g.name, duree=round(b['duree'], 3), role='bloc', ton=b['ton'], geste=cle if not b['suite'] else 'suite',
                              essais=len(essais), visage=min(essais)[0]))
        args, flt = ['ffmpeg', '-v', 'error', '-y'], []
        for k, (f, a, z) in enumerate(morceaux):
            args += ['-i', str(f)]; flt.append(f'[{k}:v]setsar=1,trim=start_frame={a}:end_frame={z},setpts=PTS-STARTPTS[v{k}]')
        flt.append(''.join(f'[v{k}]' for k in range(len(morceaux))) + f'concat=n={len(morceaux)}:v=1:a=0,fps=25[o]')
        t['etape'] = 'Collage des blocs'; sauver()
        lancer(t, args + ['-filter_complex', ';'.join(flt), '-map', '[o]', '-c:v', 'libx264', '-crf', '14', '-pix_fmt', 'yuv420p', seq])
        apercu(seq)
    finally: shutil.rmtree(tmp, ignore_errors=True)
    return faits

SUITE = 'She continues naturally in the same mood, with small calm movements.'

def segments(texte):
    return balises.blocs(texte,BALISES) or [dict(ton='neutre',texte='')]

def voix_segments(t, segs, profil, langue, out):
    """Une synthèse VoiceStudio par segment : on connaît ainsi le début exact de chaque situation."""
    tmp = ICI / 'audios' / f"tmp-{t['id']}"; tmp.mkdir(exist_ok=True); liste, d0 = [], 0.0
    try:
        for k, x in enumerate(segs):
            w = tmp / f'{k:03d}.wav'; voix(t, x['texte'], profil, langue, w)
            x['debut'] = round(d0, 3); d0 += duree(w) + 0.2; liste.append(w)
        flt = ''.join(f'[{k}:a]aresample=44100,aformat=channel_layouts=mono,apad=pad_dur=0.2[a{k}];' for k in range(len(liste)))
        args = ['ffmpeg', '-v', 'error', '-y'] + sum((['-i', str(w)] for w in liste), [])
        subprocess.run(args + ['-filter_complex', flt + ''.join(f'[a{k}]' for k in range(len(liste))) + f'concat=n={len(liste)}:v=0:a=1[o]', '-map', '[o]', str(out)], check=True)
    finally: shutil.rmtree(tmp, ignore_errors=True)

def lib_avatar(src):
    """Bibliothèque d'un avatar : {ton: [clips avec transition]}, clips de repos, prêt ou non."""
    base, lib, repos = Path(src).stem, {}, []
    for c in clips_avatar(src):
        m = json.loads((ICI / 'clips' / c).with_suffix('.json').read_text())
        ton = m.get('ton') or TON_DU_GESTE.get(re.sub(r'-v\d+$', '', Path(c).stem[len(base) + 1:]))
        if ton == 'repos': repos.append(c)
        elif ton and (ICI / 'ponts' / f'pont-{c}').exists(): lib.setdefault(ton, []).append(c)
    return dict(tons=lib, repos=repos, pret=bool(lib))

def timeline(src, segs, total):
    """Chaque situation commence au début de sa phrase : geste du ton + sa transition (retour à la pose),
    répété si la phrase est longue ; les creux sont comblés par le clip de repos (coupable n'importe où).
    Tout part et revient à la photo source : aucune coupe visible."""
    L = lib_avatar(src); plan, cur, tour = [], 0.0, {}
    def repos(d):
        nonlocal cur
        while d > 0.04:
            if L['repos']:
                f = ICI / 'clips' / L['repos'][len(plan) % len(L['repos'])]; x = min(d, duree(f))
            else: f, x = immobile(src), min(d, 4.0)
            plan.append(dict(fichier=str(f), duree=round(x, 3), role='repos')); cur += x; d -= x
    for k, sg in enumerate(segs):
        fin = segs[k + 1]['debut'] if k + 1 < len(segs) else total
        if cur < sg['debut']: repos(sg['debut'] - cur)
        premier = True
        while True:
            variantes = L['tons'].get(sg['ton']) or L['tons'].get('neutre') or next(iter(L['tons'].values()))
            c = variantes[tour.get(sg['ton'], 0) % len(variantes)]
            f, pont = ICI / 'clips' / c, ICI / 'ponts' / f'pont-{c}'; u = duree(f) + duree(pont)
            reste = fin - cur
            if not (reste >= 0.6 * u or (premier and reste >= 2.0)): break
            tour[sg['ton']] = tour.get(sg['ton'], 0) + 1; premier = False
            plan += [dict(fichier=str(f), duree=round(duree(f), 3), role='geste', ton=sg['ton']), dict(fichier=str(pont), duree=round(duree(pont), 3), role='transition')]
            cur += u
    if cur < total: repos(total - cur)
    # couper ce qui dépasse la fin de l'audio
    t0, coupe = 0.0, []
    for m in plan:
        if t0 >= total - 0.01: break
        m = dict(m, duree=round(min(m['duree'], total - t0), 3)); coupe.append(m); t0 += m['duree']
    return coupe

def immobile(src):
    """Secours sans clip de repos : la photo fixe, à la taille des clips."""
    out = ICI / 'clips' / f'.immobile-{Path(src).stem}.mp4'
    if not out.exists():
        c = clips_avatar(src); W, H = taille_image(ICI / 'clips' / c[0]) if c else resolution(ICI / 'sources' / src)
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-loop', '1', '-t', '4', '-i', str(ICI / 'sources' / src), '-vf', f'scale={W}:{H},fps=24',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(out)], check=True)
    return out

def concat(t, morceaux, out):
    W, H = taille_image(morceaux[0][0]); args, flt = ['ffmpeg', '-v', 'error', '-y'], []
    for k, (f, d) in enumerate(morceaux):   # même taille et pixels carrés partout (la photo fixe de secours n'a pas le même SAR)
        args += ['-i', str(f)]; flt.append(f'[{k}:v]fps=24,scale={W}:{H},setsar=1,trim=duration={d:.3f},setpts=PTS-STARTPTS[v{k}]')
    flt.append(''.join(f'[v{k}]' for k in range(len(morceaux))) + f'concat=n={len(morceaux)}:v=1:a=0,fps=25[o]')
    lancer(t, args + ['-filter_complex', ';'.join(flt), '-map', '[o]', '-c:v', 'libx264', '-crf', '14', '-pix_fmt', 'yuv420p', out])
    apercu(out)

def preparation(src):
    """Situations d'un avatar : un geste par ton (deux pour « neutre »), leurs transitions, et un clip de repos.
    Ce qui existe déjà (clip ou transition) n'est pas refait. ≈ 80 min pour un avatar neuf."""
    base, taches, k = Path(src).stem, [], 0
    cles = [g for *_, gs in TONS for g in gs]
    for g in cles:
        if not (ICI / 'clips' / f'{base}-{g}.mp4').exists():
            taches.append(dict(type='clip', params=dict(source=src, geste=GESTES[g], cle=g, nom=f'{base}-{g}', seed=11 + k, images=97))); k += 1
    if not lib_avatar(src)['repos'] and not (ICI / 'clips' / f'{base}-repos.mp4').exists():
        taches.append(dict(type='clip', params=dict(source=src, geste=REPOS, nom=f'{base}-repos', seed=9, images=97, ancre_fin=True, ton='repos')))
    for g in cles:
        if not (ICI / 'ponts' / f'pont-{base}-{g}.mp4').exists():
            taches.append(dict(type='pont', params=dict(clip=f'{base}-{g}.mp4', images=33)))
    return taches

def clips_avatar(source):
    return [f.name for f in sorted((ICI / 'clips').glob('*.mp4'))
            if f.with_suffix('.json').exists() and json.loads(f.with_suffix('.json').read_text()).get('source') == source]

def musetalk(t, video, audio, out, shift):
    choix = t.get('modeles') or GESTION_MODELES.selection()
    if not choix['lipsync']['installe']: raise RuntimeError('Installez le pack MuseTalk dans la page Modèles.')
    wav = ICI / 'lipsync' / f"{t['id']}-16k.wav"; v25 = ICI / 'lipsync' / f"{t['id']}-25fps.mp4"
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', audio, '-ar', '16000', '-ac', '1', wav], check=True)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', video, '-vf', 'fps=25', '-an', '-c:v', 'libx264', '-crf', '14', '-pix_fmt', 'yuv420p', v25], check=True)
    brut = out.with_suffix('.tmp.mp4')
    try: lancer(t, [MUSE_PY, ICI / 'lancer_musetalk15.py', v25, wav, brut, shift], {'PYTORCH_ENABLE_MPS_FALLBACK': '1', 'STUDIO_MUSETALK_ROOT': str(GESTION_MODELES.muse_root)})
    finally: wav.unlink(missing_ok=True); v25.unlink(missing_ok=True)
    # MuseTalk remet l'audio 16 kHz : on remet l'audio d'origine en pleine qualité
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', brut, '-i', audio, '-map', '0:v', '-map', '1:a', '-c:v', 'copy',
                    '-c:a', 'aac', '-b:a', '192k', '-shortest', '-movflags', '+faststart', out], check=True)
    brut.unlink(missing_ok=True); apercu(out)

def voix(t, texte, profil, langue, out, seed=42):
    """Synthèse intégrée ; les anciens identifiants migrés restent reconnus."""
    return ATELIER_VOIX.generer(t,texte,profil,langue,out,seed)

def travailleur():
    (ICI / 'taches').mkdir(exist_ok=True)
    while True:
        attente = [x for x in TACHES if x['etat'] == 'en attente']
        # les vidéos passent avant les préparations de bibliothèque (facultatives depuis le mode sur mesure)
        t = next((x for x in attente if x['type'] == 'video'), None) or (attente[0] if attente else None)
        if not t: time.sleep(1); continue
        t['etat'], t['debut'] = 'en cours', time.time(); EN_COURS['id'] = t['id']; sauver()
        try: faire(t); t['etat'] = 'finie'
        except Exception as e:
            msg = str(e)
            if msg.startswith('commande terminée'): msg = 'un outil de calcul a échoué (détail dans le journal du mode avancé)'
            t['etat'], t['erreur'] = ('annulée' if t.get('annuler') else 'erreur'), (f"pendant « {t['etape']} » : {msg}" if t.get('etape') else msg)
        t['fin'] = time.time(); EN_COURS['id'] = None; sauver()

def fichiers():
    out = {}
    for d in DOSSIERS:
        l = []
        for f in sorted((ICI / d).iterdir(), key=lambda f: -f.stat().st_mtime):
            if not f.is_file() or f.name.startswith(('.', 'fin-')) or f.suffix in ('.json', '.jpg') or '.tmp.' in f.name or f.name.endswith('-16k.wav') or '-25fps' in f.name: continue
            m = f.with_suffix('.json'); l.append(dict(nom=f.name, meta=json.loads(m.read_text()) if m.exists() else {},
                                                  apercu=f.with_suffix('.jpg').exists(), duree=round(duree_cache(f), 2) if f.suffix in ('.mp4', '.mov', '.m4v', '.webm', '.wav', '.mp3', '.m4a') else None))
        out[d] = l
    return out

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode(); self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8'); self.send_header('Content-Length', len(b)); self.end_headers(); self.wfile.write(b)
    def corps(self): return self.rfile.read(int(self.headers.get('Content-Length', 0)))
    def do_GET(self):
        u = urlparse(self.path)
        if u.path == '/': return self.envoyer(ICI / 'index.html', 'text/html; charset=utf-8')
        if u.path == '/api/etat':
            libs = {s.name: lib_avatar(s.name) for s in (ICI / 'sources').iterdir() if not s.name.startswith('.')}
            return self.json(dict(taches=TACHES[-60:][::-1], fichiers=fichiers(), t7=GESTION_MODELES.selection()['video']['installe'], base_clip=BASE_CLIP,
                                  tons=[dict(cle=k, nom=n, emoji=e, balise=bs[0], geste=GESTES[gs[0]]) for k, n, e, bs, gs in TONS], balises=BALISES, balises_vocales=balises.VOCALES, libs=libs))
        if u.path == '/api/apercu': return self.json(apercus.etat(parse_qs(u.query).get('projet', [''])[0]))
        if u.path == '/api/modeles/voix': return self.json(GESTION_MODELES.voix_catalogue())
        if u.path == '/api/modeles': return self.json(GESTION_MODELES.catalogue())
        if u.path == '/api/projets': return self.json(projets.liste())
        if u.path == '/api/animation': return self.json(ATELIER_ANIMATION.etat())
        if u.path == '/api/voix': return self.json(ATELIER_VOIX.liste())
        if u.path.startswith('/api/journal/'):
            f = ICI / 'taches' / f"{nom_sur(u.path.rsplit('/', 1)[1])}.log"
            txt = f.read_text(errors='replace')[-4000:] if f.exists() else ''
            return self.json(dict(texte=re.sub(r'.*\r', '', txt)))
        if u.path.startswith('/f/'):
            d, _, n = unquote(u.path[3:]).partition('/')
            if d in DOSSIERS and '/' not in n and n: return self.envoyer(ICI / d / n)
        self.send_error(404)
    def envoyer(self, f, ctype=None):
        if not f.exists(): return self.send_error(404)
        ctype = ctype or {'.mp4': 'video/mp4', '.jpg': 'image/jpeg', '.png': 'image/png', '.wav': 'audio/wav', '.mp3': 'audio/mpeg', '.json': 'application/json'}.get(f.suffix.lower(), 'application/octet-stream')
        taille = f.stat().st_size; debut, fin = 0, taille - 1
        r = re.match(r'bytes=(\d*)-(\d*)', self.headers.get('Range', ''))   # lecture vidéo avec avance/retour
        if r and (r[1] or r[2]):
            debut = int(r[1]) if r[1] else taille - int(r[2]); fin = int(r[2]) if r[1] and r[2] else taille - 1
            self.send_response(206); self.send_header('Content-Range', f'bytes {debut}-{fin}/{taille}')
        else: self.send_response(200)
        self.send_header('Content-Type', ctype); self.send_header('Accept-Ranges', 'bytes'); self.send_header('Content-Length', fin - debut + 1)
        self.send_header('Cache-Control', 'no-store'); self.end_headers()
        with open(f, 'rb') as fh:
            fh.seek(debut); reste = fin - debut + 1
            try:
                while reste > 0:
                    b = fh.read(min(1 << 20, reste))
                    if not b: break
                    self.wfile.write(b); reste -= len(b)
            except (BrokenPipeError, ConnectionResetError): pass
    def do_PUT(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        if u.path == '/api/envoi' and q.get('dossier', [''])[0] in ('sources', 'audios', 'references', 'performances'):
            if q['dossier'][0]=='performances':
                name=q.get('nom',[''])[0]
                size=int(self.headers.get('Content-Length',0))
                if not 0<size<=1024**3 or Path(name).suffix.lower() not in ('.mp4','.mov','.m4v','.webm'):
                    self.close_connection=True
                    return self.json(dict(erreur='Vidéo MP4, MOV ou WebM de 1 Go maximum requise.'),400)
            n = nom_sur(q['nom'][0]); (ICI / q['dossier'][0] / n).write_bytes(self.corps())
            return self.json(dict(nom=n))
        self.send_error(400)
    def do_POST(self):
        u = urlparse(self.path); d = json.loads(self.corps() or b'{}')
        if u.path in ('/api/animation','/api/animation/diagnostic'):
            try: return self.json(ATELIER_ANIMATION.demander(d,diagnostic=u.path.endswith('/diagnostic')))
            except (ValueError, OSError, KeyError) as e: return self.json(dict(erreur=str(e)),400)
        if u.path.startswith('/api/voix/'):
            try:
                action=u.path.rsplit('/',1)[1]
                if action=='enregistrer': resultat=ATELIER_VOIX.enregistrer(d)
                elif action=='supprimer': ATELIER_VOIX.supprimer(d.get('id')); resultat=dict(ok=True)
                elif action=='essai': resultat=ATELIER_VOIX.essai(d)
                elif action=='importer-voicestudio': resultat=ATELIER_VOIX.importer_ancien()
                else: raise ValueError('Action vocale inconnue')
                return self.json(resultat)
            except (ValueError, OSError, KeyError) as e: return self.json(dict(erreur=str(e)),400)
        if u.path == '/api/apercu':
            try: return self.json(apercus.demander(d.get('projet'), d.get('jonction')))
            except (ValueError, KeyError) as e: return self.json(dict(erreur=str(e)), 400)
        if u.path == '/api/modeles':
            try:
                action = d.get('action')
                if action == 'analyser': GESTION_MODELES.commencer(d.get('id'))
                elif action == 'telecharger': GESTION_MODELES.commencer(d.get('id'), True)
                elif action == 'annuler': GESTION_MODELES.cancel.set()
                elif action == 'voix': GESTION_MODELES.choisir_voix(d.get('id'))
                elif action == 'choisir': GESTION_MODELES.choisir(d.get('id'))
                elif action == 'importer': GESTION_MODELES.importer(d.get('path', ''), d.get('nom', ''))
                else: raise ValueError('Action inconnue')
                return self.json(GESTION_MODELES.catalogue())
            except (ValueError, OSError) as e: return self.json(dict(erreur=str(e)), 400)
        if u.path.startswith('/api/projets'):
            try:
                if u.path == '/api/projets': resultat = projets.creer(d)
                elif u.path == '/api/projets/modifier': resultat = projets.modifier(d.get('projet'), d)
                elif u.path == '/api/projets/lancer': resultat = projets.lancer(d.get('projet'), d)
                else: return self.json(dict(erreur='Action inconnue'), 404)
                return self.json(resultat)
            except (ValueError, KeyError, TypeError) as e: return self.json(dict(erreur=str(e)), 400)
        if u.path == '/api/tache':
            if d.get('type') not in ('clip', 'pont', 'sequence', 'lipsync', 'video', 'avatar', 'variante', 'portrait'): return self.json(dict(erreur='type inconnu'), 400)
            if d['type'] == 'avatar': nouvelles = preparation(d['params']['source'])
            else: nouvelles = [d]
            with VERROU:
                for n in nouvelles: TACHES.append(dict(id=uuid.uuid4().hex[:8], type=n['type'], params=n.get('params', {}), etat='en attente', cree=time.time()))
            sauver(); return self.json(dict(ajoutees=len(nouvelles)))
        if u.path == '/api/annuler':
            t = next((x for x in TACHES if x['id'] == d.get('id')), None)
            if t and t['etat'] == 'en attente': t['etat'] = 'annulée'
            elif t and t['etat'] == 'en cours':
                t['annuler'] = True
                if EN_COURS['proc']: EN_COURS['proc'].terminate()
            sauver(); return self.json(dict(ok=True))
        if u.path == '/api/supprimer_avatar':   # la photo et tous ses mouvements / transitions
            src = nom_sur(d.get('nom', ''))
            for c in clips_avatar(src):
                for x in (ICI / 'clips' / c, ICI / 'ponts' / f'pont-{c}'):
                    for y in (x, x.with_suffix('.json'), x.with_suffix('.jpg')): y.unlink(missing_ok=True)
            (ICI / 'sources' / src).unlink(missing_ok=True); return self.json(dict(ok=True))
        if u.path == '/api/portraits/utiliser':   # un portrait généré devient une photo d'avatar
            f = ICI / 'portraits' / nom_sur(d.get('fichier', ''))
            if not f.is_file(): return self.json(dict(erreur='Portrait introuvable'), 400)
            n = nom_sur(d.get('nom') or f.stem) + '.png'; shutil.copy(f, ICI / 'sources' / n); return self.json(dict(nom=n))
        if u.path == '/api/supprimer' and d.get('dossier') in DOSSIERS:
            f = ICI / d['dossier'] / nom_sur(d.get('nom', ''))
            for x in (f, f.with_suffix('.json'), f.with_suffix('.jpg')): x.unlink(missing_ok=True)
            return self.json(dict(ok=True))
        self.send_error(404)

import projets
import modeles
import apercus
import voix as voix_locale
import animation
apercus.installer(sys.modules[__name__])
GESTION_MODELES = modeles.Gestionnaire(sys.modules[__name__])
projets.installer(sys.modules[__name__])
ATELIER_VOIX = voix_locale.Atelier(sys.modules[__name__])
ATELIER_ANIMATION = animation.Atelier(sys.modules[__name__])

if __name__ == '__main__':
    threading.Thread(target=travailleur, daemon=True).start()
    print(f'Studio avatar : http://localhost:{PORT}')
    ThreadingHTTPServer(('127.0.0.1', PORT), H).serve_forever()
