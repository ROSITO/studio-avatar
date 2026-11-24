"""JPEG avatars must be listed; generated video thumbnails must stay hidden."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
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


if __name__ == '__main__':
    unittest.main()
