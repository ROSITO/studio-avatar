import unittest
import balises

class BalisesTest(unittest.TestCase):
    def test_blocs_uniquement_aux_tags_visuels(self):
        b=balises.blocs('[curious] Bonjour. [laughs] Ah ! [serious] [sighs] Bon.',{'curious':'curieux','serious':'serieux'})
        self.assertEqual(b,[dict(ton='curieux',texte='Bonjour. [laughs] Ah !'),dict(ton='serieux',texte='[sighs] Bon.')])
    def test_balise_vocale_avant_tag_visuel_ne_cree_pas_un_rush(self):
        self.assertEqual(balises.blocs('[sighs] [curious] Bonjour.',{'curious':'curieux'}),[dict(ton='curieux',texte='[sighs] Bonjour.')])
    def test_compter_seulement_la_parole(self):
        self.assertEqual(balises.parle('[curious] Bonjour. [laughs] Ah !'),'Bonjour. Ah !')
    def test_emotion_vocale_explicite_independante_du_tag_visuel(self):
        texte='[curious] [voice:curious] Bonjour [laughs].'
        self.assertEqual(balises.pour_voix(texte,'drama3-mlx',{'curious':'curieux'}),'[curious] Bonjour [laughs].')
        self.assertEqual(balises.pour_voix(texte,'omnivoice',{'curious':'curieux'}),'Bonjour .')
