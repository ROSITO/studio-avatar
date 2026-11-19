import contextlib,io,re,unittest
from animation_progression import SuiviWan
from lancer_animation import reglages_animation,guidage_animation

class SuiviTest(unittest.TestCase):
    def test_progression_depuis_les_couches(self):
        s=SuiviWan(2,2,8,2);log=io.StringIO()
        with contextlib.redirect_stdout(log):
            for _ in range(2):
                s.avant('forward_ref');s.couche(7)
                for step in range(2):
                    for uncond in (False,True):
                        s.avant('forward_gen',uncond)
                        for layer in range(8):s.couche(layer)
                    s.terminer(step)
        values=list(map(float,re.findall(r'avancement : ([\d.]+)%',log.getvalue())))
        self.assertEqual(values,sorted(values));self.assertEqual(values[0],6.2);self.assertEqual(values[-1],99)
    def test_apercu_explicite_et_ancien_mode_conserve(self):
        self.assertEqual(guidage_animation({'profil':'apercu'}),1)
        self.assertEqual(guidage_animation({'diagnostic_run':True,'mesurer_etape':True}),3)
        self.assertEqual(guidage_animation({}),3)
        self.assertEqual(reglages_animation({},True),(40,24,256,384))
        self.assertEqual(reglages_animation({'profil':'apercu'},True),(4,24,256,384))
        self.assertEqual(reglages_animation({'diagnostic_run':True,'mesurer_etape':True,'int4':True},True),(2,24,256,384))
