import unittest
import drama_direction as direction
import balises


class DirectionTest(unittest.TestCase):
    def test_emotions_et_retours_ligne_conserves(self):
        text = '[curious] Bonjour.\n\n[excited] Super !'
        self.assertEqual(balises.pour_voix(text, 'drama3-mlx', {'curious': 'curieux', 'excited': 'enthousiaste'}), text)
        self.assertNotIn('[', balises.pour_voix(text, 'omnivoice', {}))

    def test_direction_suivante_reaction_unique_et_reprise(self):
        chunks = ['[intriguée] Première phrase. [amusée]', 'Deuxième phrase. [laughs]', 'Troisième phrase.', '[sérieuse] Dernière phrase.', 'Conclusion.']
        actual = direction.decouper('', lambda _: chunks)
        self.assertEqual(actual, ['[intriguée] Première phrase.', '[amusée] Deuxième phrase.', '[amusée] [laughs] Troisième phrase.', '[sérieuse] Dernière phrase.', '[sérieuse] Conclusion.'])
        self.assertEqual(' '.join(actual).count('[laughs]'), 1)
        self.assertEqual(balises.parle(' '.join(actual)), balises.parle(' '.join(chunks)))

    def test_multilocuteur_inchange(self):
        chunks = ['<|speaker:0|> [happy] Bonjour.', '<|speaker:1|> Salut.']
        self.assertEqual(direction.decouper(' '.join(chunks), lambda _: chunks), chunks)

    def test_reaction_non_propagee(self):
        self.assertEqual(direction.decouper('', lambda _: ['[laughs] Bonjour.', 'Salut.']), ['[laughs] Bonjour.', 'Salut.'])

    def test_reglages_identiques_flux_et_fichier(self):
        import lancer_voix
        self.assertEqual(lancer_voix.parametres_drama(), dict(temperature=1.0, top_p=0.9, top_k=30))

    def test_decoupage_runtime_et_installation_idempotente(self):
        try:
            from mlx_audio.tts.models.fish_drama3 import chunking, drama3
        except ImportError:
            self.skipTest('Optional MLX voice runtime')
        native = chunking.split_text
        original = drama3.split_text
        try:
            direction.installer()
            installed = drama3.split_text
            direction.installer()
            self.assertIs(installed, drama3.split_text)
            self.assertIs(installed, chunking.split_text)
            text = '[intriguée] ' + 'Une première phrase. '*20 + '[amusée] ' + 'Une seconde phrase. '*20 + '[laughs] Fin.'
            chunks = installed(text)
            self.assertEqual(balises.parle(' '.join(chunks)), balises.parle(text))
            self.assertEqual(' '.join(chunks).count('[laughs]'), 1)
            for chunk in chunks[:-1]:
                self.assertIsNone(direction.FIN.search(chunk))
            self.assertTrue(all(chunk.startswith('[') for chunk in chunks))
        finally:
            chunking.split_text = native
            drama3.split_text = original


if __name__ == '__main__':
    unittest.main()
