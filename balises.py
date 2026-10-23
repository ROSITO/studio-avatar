"""Separate visual TAG blocks from inline voice delivery cues."""
import re

# Suggested natural-language directions, not a closed vocabulary. Local rendering varies by voice.
# https://docs.fish.audio/features/text-to-speech/drama-3
VOCALES = [
    {'balise': 'happy', 'nom': 'Joyeux', 'groupe': 'Émotions'},
    {'balise': 'sad', 'nom': 'Triste', 'groupe': 'Émotions'},
    {'balise': 'angry', 'nom': 'En colère', 'groupe': 'Émotions'},
    {'balise': 'excited', 'nom': 'Enthousiaste', 'groupe': 'Émotions'},
    {'balise': 'calm', 'nom': 'Calme', 'groupe': 'Émotions'},
    {'balise': 'curious', 'nom': 'Curieux', 'groupe': 'Émotions'},
    {'balise': 'serious', 'nom': 'Sérieux', 'groupe': 'Émotions'},
    {'balise': 'surprised', 'nom': 'Surpris', 'groupe': 'Émotions'},
    {'balise': 'nervous', 'nom': 'Nerveux', 'groupe': 'Émotions'},
    {'balise': 'scared', 'nom': 'Effrayé', 'groupe': 'Émotions'},
    {'balise': 'confident', 'nom': 'Confiant', 'groupe': 'Émotions'},
    {'balise': 'embarrassed', 'nom': 'Gêné', 'groupe': 'Émotions'},
    {'balise': 'frustrated', 'nom': 'Frustré', 'groupe': 'Émotions'},
    {'balise': 'proud', 'nom': 'Fier', 'groupe': 'Émotions'},
    {'balise': 'sarcastic', 'nom': 'Sarcastique', 'groupe': 'Émotions'},
    {'balise': 'hopeful', 'nom': 'Plein d’espoir', 'groupe': 'Émotions'},
    {'balise': 'tired', 'nom': 'Fatigué', 'groupe': 'Émotions'},
    {'balise': 'empathetic', 'nom': 'Empathique', 'groupe': 'Émotions'},
    {'balise': 'whispers', 'nom': 'Chuchoter', 'groupe': 'Interprétation'},
    {'balise': 'shouting', 'nom': 'Crier', 'groupe': 'Interprétation'},
    {'balise': 'soft voice', 'nom': 'Voix douce', 'groupe': 'Interprétation'},
    {'balise': 'breathy', 'nom': 'Voix soufflée', 'groupe': 'Interprétation'},
    {'balise': 'emphasis', 'nom': 'Insister', 'groupe': 'Interprétation'},
    {'balise': 'speaking slowly', 'nom': 'Parler lentement', 'groupe': 'Interprétation'},
    {'balise': 'speaking quickly', 'nom': 'Parler vite', 'groupe': 'Interprétation'},
    {'balise': 'warm', 'nom': 'Chaleureux', 'groupe': 'Interprétation'},
    {'balise': 'friendly', 'nom': 'Amical', 'groupe': 'Interprétation'},
    {'balise': 'calm, measured storyteller voice', 'nom': 'Narrateur posé', 'groupe': 'Interprétation'},
    {'balise': 'voice breaking', 'nom': 'Voix qui se brise', 'groupe': 'Interprétation'},
    {'balise': 'sighs', 'nom': 'Soupir', 'groupe': 'Réactions'},
    {'balise': 'laughs', 'nom': 'Rire', 'groupe': 'Réactions'},
    {'balise': 'chuckling', 'nom': 'Petit rire', 'groupe': 'Réactions'},
    {'balise': 'small laugh', 'nom': 'Rire discret', 'groupe': 'Réactions'},
    {'balise': 'sobbing', 'nom': 'Sangloter', 'groupe': 'Réactions'},
    {'balise': 'crying loudly', 'nom': 'Pleurer', 'groupe': 'Réactions'},
    {'balise': 'gasping', 'nom': 'Sursaut', 'groupe': 'Réactions'},
    {'balise': 'panting', 'nom': 'Haleter', 'groupe': 'Réactions'},
    {'balise': 'groaning', 'nom': 'Gémir', 'groupe': 'Réactions'},
    {'balise': 'clear throat', 'nom': 'Se racler la gorge', 'groupe': 'Réactions'},
    {'balise': 'shaky breath', 'nom': 'Souffle tremblant', 'groupe': 'Réactions'},
    {'balise': 'breath', 'nom': 'Respiration', 'groupe': 'Réactions'},
    {'balise': 'short pause', 'nom': 'Pause courte', 'groupe': 'Pauses'},
    {'balise': 'pause', 'nom': 'Pause', 'groupe': 'Pauses'},
    {'balise': 'long pause', 'nom': 'Pause longue', 'groupe': 'Pauses'},
]
PATTERN = r'\[[^\]]+\]'

def parle(texte):
    return ' '.join(re.sub(PATTERN, ' ', texte or '').split())

def blocs(texte, visuelles):
    resultat=[];ton='neutre';courant=''
    for morceau in re.split('('+PATTERN+')', texte or ''):
        tag=re.fullmatch(r'\[([^\]]+)\]',morceau.strip())
        nouveau=visuelles.get(tag[1].strip().lower()) if tag else None
        if nouveau:
            if parle(courant):
                resultat.append(dict(ton=ton,texte=' '.join(courant.split())));courant=''
            ton=nouveau
        else:courant+=morceau
    if courant.strip():resultat.append(dict(ton=ton,texte=' '.join(courant.split())))
    return resultat

def pour_voix(texte,moteur,visuelles):
    if moteur!='drama3-mlx':return parle(texte)
    def remplacer(m):
        tag=m[0][1:-1].strip()
        # Explicit namespace permits vocal emotion even when its name is a visual TAG.
        if tag.lower().startswith('voice:'):return '['+tag.split(':',1)[1].strip()+']'
        return ' ' if tag.lower() in visuelles else m[0]
    return ' '.join(re.sub(PATTERN,remplacer,texte or '').split())
