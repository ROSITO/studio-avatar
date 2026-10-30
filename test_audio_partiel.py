import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import audio_partiel


class AudioPartielTest(unittest.TestCase):
    def test_snapshot_lisible_et_sans_perte(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'prise.wav';pcm=struct.pack('<4f',.1,-.2,.3,.4)
            audio_partiel.sauver(out,pcm,44100)
            p=audio_partiel.chemin(out)
            decoded=subprocess.check_output(['ffmpeg','-v','error','-i',str(p),'-f','f32le','-'])
            self.assertEqual(decoded,pcm)
            info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(p)]))['streams'][0]
            self.assertEqual(info['sample_rate'],'44100');self.assertEqual(info['channels'],1)
            self.assertFalse(out.exists())

    def test_ecriture_interrompue_conserve_snapshot_precedent(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'prise.wav';pcm=struct.pack('<f',.1)
            audio_partiel.sauver(out,pcm,44100);avant=audio_partiel.chemin(out).read_bytes()
            with patch.object(Path,'replace',side_effect=OSError('Disque indisponible')),self.assertRaises(OSError):
                audio_partiel.sauver(out,pcm*2,44100)
            self.assertEqual(audio_partiel.chemin(out).read_bytes(),avant)

    def test_survit_a_arret_force_du_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'prise.wav'
            code="import audio_partiel,struct,sys,time; audio_partiel.sauver(sys.argv[1],struct.pack('<f',.25)*44100,44100); print('saved',flush=True); time.sleep(30)"
            child=subprocess.Popen([sys.executable,'-c',code,str(out)],stdout=subprocess.PIPE,text=True,cwd=Path(__file__).parent)
            try:
                self.assertEqual(child.stdout.readline().strip(),'saved')
                child.kill();child.wait(timeout=5)
                self.assertEqual(len(subprocess.check_output(['ffmpeg','-v','error','-i',str(audio_partiel.chemin(out)),'-f','f32le','-'])),44100*4)
            finally:
                if child.poll() is None:child.kill();child.wait()
                child.stdout.close()


if __name__=='__main__':unittest.main()
