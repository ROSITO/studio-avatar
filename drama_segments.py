"""Bounded, independent Drama utterances and lossless, checkpointed assembly."""
import hashlib
import json
from pathlib import Path
import re
import wave

VERSION = 1
MAX_CHARS = 140
MAX_BYTES = 280  # Runtime native splitter uses 300 UTF-8 bytes, including cues.
TAG = re.compile(r'\[[^\[\]]+\]')
PAUSES = {'pause': .35, 'short pause': .2, 'long pause': .7,
          'pause courte': .2, 'pause longue': .7}
PUNCTUAL = {'laughs', 'sighs', 'chuckling', 'small laugh', 'sobbing',
            'crying loudly', 'gasping', 'panting', 'groaning', 'clear throat',
            'shaky breath', 'breath', 'soupir', 'rire', 'petit rire',
            'rire discret', 'respiration'}


class Validation(ValueError):
    def __init__(self, code, message, champ='texte', suggestion='Corriger le texte puis resoumettre.'):
        super().__init__(message)
        self.detail = dict(code=code, champ=champ, message=message,
                           suggestion=suggestion, relancable=False)


def spoken(text):
    return ' '.join(TAG.sub(' ', text).split())


def plan(text):
    if not isinstance(text, str):
        raise Validation('texte_invalide', 'Le texte doit être une chaîne UTF-8.')
    if not spoken(text):
        raise Validation('texte_vide', 'Le texte ne contient aucun mot à prononcer.')
    if any(x in text for x in ('<|', '|>', '<whisper>', '</whisper>')):
        raise Validation('format_non_pris_en_charge', 'Les tokens structurels, scènes multi-locuteurs et balises XML ne sont pas pris en charge par la synthèse segmentée.', suggestion='Utiliser une voix unique et des indications entre crochets.')
    without = TAG.sub('', text)
    if '[' in without or ']' in without:
        raise Validation('balise_mal_formee', 'Une balise entre crochets est vide, imbriquée ou non fermée.')
    if '\x00' in text:
        raise Validation('texte_invalide', 'Le texte contient un caractère nul.')
    result = []
    delivery = ''
    pending_direction = False
    cues = []
    leading_pause = 0
    for part in re.split(r'(\[[^\[\]]+\])', text):
        if TAG.fullmatch(part):
            name = part[1:-1].strip()
            if name.lower().startswith('voice:'):
                name = name.split(':', 1)[1].strip()
                part = '[' + name + ']'
            if name.lower() in PAUSES:
                if result:
                    result[-1]['pause_apres'] += PAUSES[name.lower()]
                else:
                    leading_pause += PAUSES[name.lower()]
            elif name.lower() in PUNCTUAL:
                cues.append(part)
            else:
                delivery = (delivery+' '+part).strip() if pending_direction else part
                pending_direction = True
            continue
        words = part.split()
        if words:pending_direction = False
        while words:
            prefix = ' '.join(([delivery] if delivery else []) + cues)
            count = 0
            for n in range(1, len(words) + 1):
                body = ' '.join(words[:n])
                candidate = (prefix + ' ' + body).strip()
                if len(body) > MAX_CHARS or len(candidate.encode('utf-8')) > MAX_BYTES:
                    break
                count = n
            if not count:
                raise Validation('segment_impossible', 'Un mot ou une indication vocale dépasse la limite d’un passage indépendant.', suggestion='Raccourcir l’indication vocale ou le mot exceptionnellement long ; conserver les mots parlés ordinaires.')
            # Prefer the last sentence/clause boundary inside the safe window.
            if count < len(words):
                boundaries = [n for n in range(1, count + 1)
                              if re.search(r'[.!?;,:…]["»”\')]*$', words[n-1])]
                if boundaries:
                    count = boundaries[-1]
            body = ' '.join(words[:count])
            result.append(dict(ordre=len(result)+1, texte=(prefix+' '+body).strip(),
                pause_avant=leading_pause if not result else 0, pause_apres=0,
                etat='en attente', essais=0))
            words = words[count:]
            cues = []  # Reactions happen once; delivery persists.
    if cues or pending_direction:
        raise Validation('indication_sans_parole', 'Une réaction finale ne possède aucun texte à interpréter.')
    if len(result) > 100:
        raise Validation('trop_de_segments', 'Le texte crée plus de 100 passages indépendants.', suggestion='Répartir ce texte en plusieurs demandes.')
    if spoken(' '.join(x['texte'] for x in result)) != spoken(text):
        raise Validation('decoupage_incoherent', 'Le découpage ne conserve pas tous les mots. Demande refusée.')
    return dict(version=VERSION, total=len(result), termines=0, segments=result)


def signature(text, profile, model, seed, reference):
    payload = json.dumps(dict(version=VERSION, texte=text, profil=profile,
        modele=model, seed=seed, reference=hashlib.sha256(Path(reference).read_bytes()).hexdigest()),
        sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def duration(path):
    with wave.open(str(path), 'rb') as source:
        if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 3, 44100):
            raise ValueError('Le passage doit être WAV PCM 24 bits mono 44100 Hz.')
        if source.getnframes() < 4410:
            raise ValueError('Passage vide ou trop court.')
        return source.getnframes()/44100


def assemble(root, segments, output, cancelled=lambda: False):
    temporary = output.with_suffix('.tmp.wav')
    try:
        with wave.open(str(temporary), 'wb') as destination:
            destination.setparams((1, 3, 44100, 0, 'NONE', 'not compressed'))
            for segment in segments:
                if cancelled():
                    raise RuntimeError('Tâche annulée')
                if segment['etat'] != 'finie':
                    raise RuntimeError('Assemblage refusé : passage incomplet.')
                path = root / segment['fichier']
                duration(path)
                destination.writeframes(bytes(round(segment.get('pause_avant', 0)*44100)*3))
                with wave.open(str(path), 'rb') as source:
                    while data := source.readframes(65536):
                        if cancelled():
                            raise RuntimeError('Tâche annulée')
                        destination.writeframes(data)
                destination.writeframes(bytes(round(segment.get('pause_apres', 0)*44100)*3))
        if cancelled():
            raise RuntimeError('Tâche annulée')
        duration(temporary)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
