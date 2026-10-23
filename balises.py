"""Separate visual TAG blocks from inline voice delivery cues."""
import re

VOCALES = [dict(balise='sighs', nom='Soupir'), dict(balise='laughs', nom='Rire'), dict(balise='whispers', nom='Chuchoter')]
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
