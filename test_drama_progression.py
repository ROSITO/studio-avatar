import contextlib
import importlib.util
import io
import re
from types import SimpleNamespace
import unittest

@unittest.skipUnless(importlib.util.find_spec('mlx_audio'),'Optional voice runtime')
class ProgressionTest(unittest.TestCase):
    def test_sorties_intactes_et_progression_monotone(self):
        import drama_progression
        from mlx_audio.tts.models.fish_drama3.chunking import split_text
        text='Bonjour à tous. '*70
        chunks=split_text(text);model=SimpleNamespace(_frames=lambda:iter(range(32)))
        drama_progression.installer(model,text);out=io.StringIO()
        with contextlib.redirect_stdout(out):
            for _ in chunks:self.assertEqual(list(model._frames()),list(range(32)))
        values=[int(x) for x in re.findall(r'progression : (\d+)%',out.getvalue())]
        self.assertEqual(values,sorted(values));self.assertEqual(values[0],0);self.assertEqual(values[-1],99)
        self.assertIn(f'bloc {len(chunks)}/{len(chunks)}',out.getvalue())
