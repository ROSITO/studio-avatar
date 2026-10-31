"""Keep delivery directions attached to speech across native Drama chunks.

Uses the runtime's own splitter (including paired tags and speaker handling).
Only monologue delivery cues are carried; reactions are never duplicated.
"""
import re

# Published Fish Audio Drama 3 serving recipe, identical for both output paths.
ECHANTILLONNAGE = dict(temperature=1.0, top_p=0.9, top_k=30)
PONCTUELLES = frozenset((
    'sighs', 'laughs', 'chuckling', 'small laugh', 'sobbing', 'crying loudly',
    'gasping', 'panting', 'groaning', 'clear throat', 'shaky breath', 'breath',
    'short pause', 'pause', 'long pause', 'soupir', 'rire', 'petit rire', 'rire discret', 'respiration',
))
TAG = re.compile(r'\[([^\[\]]+)\]')
FIN = re.compile(r'(?:\s*\[[^\[\]]+\])+\s*$')


def decouper(texte, natif, *args, **kwargs):
    chunks = list(natif(texte, *args, **kwargs))
    # Leave explicit multi-speaker scenes under the native speaker-aware rules.
    if '<|speaker:' in texte:
        return chunks
    for i in range(len(chunks)-1):
        match = FIN.search(chunks[i])
        if match and chunks[i][:match.start()].strip():
            cues = chunks[i][match.start():].strip()
            chunks[i] = chunks[i][:match.start()].rstrip()
            chunks[i+1] = cues + ' ' + chunks[i+1].lstrip()
    resultat = []
    active = None
    for chunk in chunks:
        tags = list(TAG.finditer(chunk))
        # An immediate direction supersedes the previous delivery. A point cue
        # (laugh, pause...) does not reset a delivery nor persist into the next.
        head = re.match(r'^\s*((?:\[[^\[\]]+\]\s*)+)', chunk)
        leading = TAG.findall(head[1]) if head else []
        if active and not any(t.strip().lower() not in PONCTUELLES for t in leading):
            chunk = active + ' ' + chunk
        for tag in tags:
            if tag[1].strip().lower() not in PONCTUELLES:
                active = tag[0]
        if chunk.strip():
            resultat.append(chunk)
    return resultat


def installer():
    from mlx_audio.tts.models.fish_drama3 import drama3, chunking
    if getattr(drama3.split_text, '_studio_direction', False):
        return
    natif = chunking.split_text

    def split_text(texte, *args, **kwargs):
        return decouper(texte, natif, *args, **kwargs)

    split_text._studio_direction = True
    drama3.split_text = split_text
    # Progress estimates and generation must share exactly the same boundaries.
    chunking.split_text = split_text
