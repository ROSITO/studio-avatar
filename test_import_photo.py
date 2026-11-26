"""JPEG avatars must be listed; generated video thumbnails must stay hidden."""
from pathlib import Path
import json
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlencode
import studio


class PhotoLibraryTest(unittest.TestCase):
    def test_jpeg_photos_are_kept_but_video_thumbnails_are_hidden(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in studio.DOSSIERS:
                (root / name).mkdir()
            for folder in ('sources', 'portraits', 'references'):
                for name in ('photo.jpg', 'majuscules.JPG', 'autre.jpeg', 'longue-extension.JPEG', 'image.png'):
                    (root / folder / name).write_bytes(b'fixture')
            (root / 'clips' / 'clip.jpg').write_bytes(b'thumbnail')
            (root / 'clips' / 'clip.JPG').write_bytes(b'thumbnail')
            (root / 'sources' / 'photo.json').write_text('{}')
            with patch.object(studio, 'ICI', root):
                library = studio.fichiers()
            for folder in ('sources', 'portraits', 'references'):
                self.assertEqual({item['nom'] for item in library[folder]},
                                 {'photo.jpg', 'majuscules.JPG', 'autre.jpeg', 'longue-extension.JPEG', 'image.png'})
            self.assertEqual(library['clips'], [])

    def test_import_preserves_existing_photos_and_lists_windows_safe_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for folder in studio.DOSSIERS:
                (root / folder).mkdir()
            sources = root / 'sources'
            (sources / 'Alice.jpg').write_bytes(b'original')
            with patch.object(studio, 'ICI', root):
                imports = {}
                for label in ('alice.JPG', 'Alice.png', 'CON.jpg', 'LPT².jpg', '.portrait.jpg', 'fin-Éva.JPG', 'portrait.tmp.jpg'):
                    handler = SimpleNamespace(path='/api/envoi?'+urlencode(dict(dossier='sources', nom=label)),
                                              corps=lambda: label.encode(), json=Mock())
                    studio.H.do_PUT(handler)
                    (result,), _ = handler.json.call_args
                    imports[label] = result['nom']
                    self.assertEqual((sources / result['nom']).read_bytes(), label.encode())
                noms = {item['nom'] for item in studio.fichiers()['sources']}
                self.assertEqual(noms, {'Alice.jpg', *imports.values()})
                self.assertEqual((sources / 'Alice.jpg').read_bytes(), b'original')
                self.assertEqual(imports['alice.JPG'], 'alice-2.JPG')
                self.assertEqual(imports['Alice.png'], 'Alice-3.png')
                self.assertEqual(imports['CON.jpg'], 'media-CON.jpg')
                self.assertEqual(imports['LPT².jpg'], 'media-LPT².jpg')
                self.assertEqual(imports['fin-Éva.JPG'], 'fin-Éva.JPG')

    def test_portrait_copy_leaves_existing_media_and_delete_uses_exact_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for folder in ('sources', 'portraits', 'references'):
                (root / folder).mkdir()
            original = root / 'sources' / 'Éva.png'
            original.write_bytes(b'original')
            (root / 'portraits' / 'Portrait existant.png').write_bytes(b'portrait')
            png = root / 'references' / 'Éva 1.png'
            jpg = png.with_suffix('.jpg')
            png.touch()
            jpg.touch()

            def post(path, **data):
                handler = SimpleNamespace(path=path, corps=lambda: json.dumps(data).encode(), json=Mock())
                studio.H.do_POST(handler)
                return handler.json.call_args.args[0]

            with patch.object(studio, 'ICI', root):
                resultat = post('/api/portraits/utiliser', fichier='Portrait existant.png', nom='Éva')
                self.assertEqual(resultat['nom'], 'Éva-2.png')
                self.assertEqual(original.read_bytes(), b'original')
                self.assertEqual((original.parent / resultat['nom']).read_bytes(), b'portrait')
                self.assertTrue(post('/api/supprimer', dossier='references', nom=png.name)['ok'])
                self.assertFalse(png.exists())
                self.assertTrue(jpg.exists())


if __name__ == '__main__':
    unittest.main()
