"""Legacy scheduling tests using synthetic library metadata, without personal media."""
import unittest
from unittest.mock import patch
import studio


class LegacyTimelineTest(unittest.TestCase):
    def test_tag_parsing_and_legacy_schedule(self):
        segs = studio.segments('[neutral] Hello. [curious] A question? [excited] Great! [thoughtful] Let us think.')
        self.assertEqual([s['ton'] for s in segs], ['neutre', 'curieux', 'enthousiaste', 'reflechi'])
        for s, start in zip(segs, [0, 5.5, 11, 16.5]):
            s['debut'] = start
        library = dict(tons={k: [k + '.mp4'] for k in ['neutre', 'curieux', 'enthousiaste', 'reflechi']}, repos=['rest.mp4'])
        with patch.object(studio, 'lib_avatar', return_value=library), patch.object(studio, 'duree', side_effect=lambda f: 1.375 if 'pont-' in f.name else 4):
            plan = studio.timeline('avatar.png', segs, 22)
        self.assertAlmostEqual(sum(m['duree'] for m in plan), 22, places=2)
        self.assertEqual([m['ton'] for m in plan if m['role'] == 'geste'], ['neutre', 'curieux', 'enthousiaste', 'reflechi'])

    def test_legacy_blocks_and_frame_rounding(self):
        segs = [dict(ton='neutre', debut=0), dict(ton='curieux', debut=3.1), dict(ton='enthousiaste', debut=4.6), dict(ton='reflechi', debut=13)]
        blocks = studio.blocs_sur_mesure(segs, 15.5)
        self.assertAlmostEqual(sum(b['duree'] for b in blocks), 15.5)
        self.assertTrue(all(studio.MIN_BLOC <= b['duree'] <= studio.MAX_BLOC for b in blocks))
        for n in (20, 34, 97, 98):
            self.assertGreaterEqual(studio.images_ltx(n), n)
            self.assertEqual((studio.images_ltx(n) - 1) % 8, 0)


if __name__ == '__main__':
    unittest.main()
