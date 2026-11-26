"""One compatibility policy for installation, catalogue and task admission."""
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import installer
import modeles
import plateforme
import projets
import studio


class PlateformeTest(unittest.TestCase):
    def test_small_windows_gpu_selects_native_cpu_voices(self):
        host=dict(os='Windows',arch='amd64',ram_gib=32,nvidia=[dict(name='test',vram_mib=4096,driver='580.0')])
        with patch.object(plateforme,'detecter',return_value=host):
            for mid in ('qwen3-tts-torch','qwen3-tts-17b-torch','omnivoice'):
                entry=next(e for e in modeles.CATALOGUE if e['id']==mid)
                status=modeles.compatibilite(entry)
                self.assertTrue(status['compatible']);self.assertEqual(status['appareil'],'cpu')
            for mid in ('ltx23-q4','qwen3-tts-mlx','flux2-klein4b'):
                self.assertFalse(modeles.compatibilite(next(e for e in modeles.CATALOGUE if e['id']==mid))['compatible'])
            self.assertEqual(installer.plan(host)['device'],'cpu')
            host['nvidia'][0]['vram_mib']=16384
            self.assertEqual(installer.plan(host)['device'],'cuda')
            self.assertEqual(modeles.compatibilite(next(e for e in modeles.CATALOGUE if e['id']=='qwen3-tts-torch'))['appareil'],'cuda')

    def test_task_api_refuses_incompatible_engines_before_enqueue(self):
        for kind,role in [('clip','video'),('avatar','video'),('portrait','image'),('lipsync','lipsync')]:
            handler=SimpleNamespace(path='/api/tache',corps=lambda:json.dumps(dict(type=kind,params={})).encode(),json=Mock())
            with patch.object(studio,'TACHES',[]),patch.object(studio.GESTION_MODELES,'verifier_role',side_effect=ValueError('Moteur indisponible')) as check:
                studio.H.do_POST(handler)
                check.assert_called_once_with(role)
                self.assertEqual(handler.json.call_args.args,({'erreur':'Moteur indisponible'},400))
                self.assertEqual(studio.TACHES,[])

    def test_timeline_admission_refuses_before_modifying_project(self):
        with patch.object(projets,'lire',return_value={}),patch.object(projets.S.GESTION_MODELES,'verifier_role',side_effect=ValueError('Moteur indisponible')),patch.object(projets,'sauver') as save:
            with self.assertRaisesRegex(ValueError,'Moteur indisponible'):projets.lancer('id',dict(action='clip'))
            save.assert_not_called()

    def test_legacy_video_requires_musetalk_even_on_a_native_ltx_host(self):
        handler=SimpleNamespace(path='/api/tache',corps=lambda:b'{"type":"video"}',json=Mock())
        checks=[]
        def verifier(role):
            checks.append(role)
            if role=='lipsync': raise ValueError('MuseTalk indisponible')
        with patch.object(studio,'TACHES',[]),patch.object(studio.GESTION_MODELES,'verifier_role',side_effect=verifier):
            studio.H.do_POST(handler)
            self.assertEqual(studio.TACHES,[])
        self.assertEqual(checks,['video','lipsync'])
        self.assertEqual(handler.json.call_args.args,({'erreur':'MuseTalk indisponible'},400))


if __name__=='__main__':unittest.main()
