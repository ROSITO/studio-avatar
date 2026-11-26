"""Native visual adapters: hardware selection, official CLI and server routing."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import installer
import lancer_visuel
import memoire
import modeles
import plateforme
import studio


class NativeVisualTest(unittest.TestCase):
    def host(self,memory):
        return dict(os='Windows',arch='amd64',ram_gib=32,nvidia=[dict(name='test',vram_mib=memory,driver='580.0',compute_cap=8.6)])

    def test_hardware_admission_and_default_native_models(self):
        self.assertFalse(plateforme.backend_compatible('ltx-torch',self.host(4096)))
        self.assertFalse(plateforme.backend_compatible('flux-torch',self.host(8192)))
        self.assertFalse(installer.plan(self.host(16384),'ltx','cpu')['supported'])
        self.assertEqual(installer.plan(self.host(16384))['additional_engines'],['qwen-tts','ltx','image'])
        reserved=self.host(8000);reserved['ram_gib']=31.7
        self.assertTrue(plateforme.backend_compatible('ltx-torch',reserved))
        old=self.host(16384);old['nvidia'][0]['compute_cap']=7.5
        self.assertFalse(plateforme.backend_compatible('ltx-torch',old))
        for memory,video,image in [(4096,False,False),(8192,True,False),(16384,True,True)]:
            with self.subTest(memory=memory),tempfile.TemporaryDirectory() as directory,patch.object(plateforme,'detecter',return_value=self.host(memory)):
                root=Path(directory);manager=modeles.Gestionnaire(SimpleNamespace(ICI=root,MODELES=root/'models',TACHES=[],VOICESTUDIO='',LTX='missing'))
                self.assertEqual(manager.capacites()['video']['compatible'],video)
                self.assertEqual(manager.capacites()['image']['compatible'],image)
                if video:
                    self.assertEqual(manager.selection()['video']['id'],'ltx23-torch')
                    self.assertEqual(manager.selection()['texte']['id'],'gemma3-torch')
                if image:self.assertEqual(manager.selection()['image']['id'],'flux2-klein4b-torch')

    def data(self):
        return dict(modele='weights',gemma='gemma',prompt='hello',height=896,width=576,
                    frames=33,seed=42,sortie='output.mp4',images=[['first.jpg',0],['last.jpg','last',.8]])

    def test_official_cli_conditions_audio_and_disk_offload(self):
        data=self.data();args=lancer_visuel.arguments_ltx(data)
        self.assertEqual(args[0],'ltx_pipelines.ti2vid_two_stages')
        self.assertEqual(args[args.index('--offload')+1],'disk')
        index=args.index('last.jpg');self.assertEqual(args[index+1:index+3],['32','0.8'])
        audio=lancer_visuel.arguments_ltx(dict(data,audio='voice.wav'))
        self.assertEqual(audio[0],'ltx_pipelines.a2vid_two_stage')
        self.assertEqual(audio[audio.index('--audio-path')+1],'voice.wav')
        for frames in (10,9999):
            with self.assertRaises(ValueError):lancer_visuel.arguments_ltx(dict(data,frames=frames))

    def test_windows_ltx_staging_uses_anonymous_mapping_without_unix_flags(self):
        def windows_mmap(fileno,length):return fileno,length
        windows=SimpleNamespace(mmap=windows_mmap)
        buffers=SimpleNamespace(mmap=windows)
        with patch.dict('sys.modules',{'mmap':windows,'ltx_core':SimpleNamespace(),
                                      'ltx_core.loader':SimpleNamespace(buffers=buffers)}):
            lancer_visuel.adapter_mmap_ltx_windows()
        flags=buffers.mmap.MAP_PRIVATE|buffers.mmap.MAP_ANONYMOUS
        self.assertEqual(buffers.mmap.mmap(-1,2**21,flags=flags),(-1,2**21))
        self.assertIs(windows.mmap,windows_mmap)

    def test_studio_preserves_speech_and_atomically_replaces_clip(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);out=root/'clip.mp4';out.write_bytes(b'old clip')
            task=dict(id='test',modeles=dict(video=dict(id='ltx23-torch',path='native',installe=True),texte=dict(id='gemma3-torch',path='gemma',installe=True)))
            def native(t,engine,data):
                self.assertEqual(engine,'ltx');self.assertEqual(data['audio'],'voice.wav')
                Path(data['sortie']).write_bytes(b'raw')
            def run(t,cmd,env=None):
                self.assertIn('1:a:0',cmd);Path(cmd[-1]).write_bytes(b'new clip')
            with patch.object(studio,'lancer_natif',side_effect=native),patch.object(studio,'lancer',side_effect=run):
                studio.ltx(task,[(root/'first.jpg',0),(root/'last.jpg','last')],'hello',576,896,33,42,out,'voice.wav')
            self.assertEqual(out.read_bytes(),b'new clip')
            self.assertFalse(list(root.glob('*native.mp4')));self.assertFalse(list(root.glob('*.tmp.mp4')))

    def test_studio_routes_native_portrait_references_and_seeds(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for folder in ('portraits','references'):(root/folder).mkdir()
            (root/'references'/'face.jpg').write_bytes(b'photo')
            task=dict(id='test',params=dict(prompt='seated',refs=[dict(dossier='references',nom='face.jpg')]),seeds=[42],modeles=dict(image=dict(id='flux2-klein4b-torch',path='native',installe=True)))
            def native(t,engine,data):
                self.assertEqual(engine,'image');self.assertEqual(data['seeds'],[42])
                self.assertEqual(data['references'],[str(root/'references'/'face.jpg')])
                (root/'portraits'/'test-42.png').write_bytes(b'png')
            with patch.object(studio,'ICI',root),patch.object(studio,'sauver'),patch.object(studio,'lancer_natif',side_effect=native):studio.portrait(task)
            self.assertEqual(task['resultat']['images'],['test-42.png'])

    def test_native_image_pipeline_uses_offline_offload_and_atomic_output(self):
        with tempfile.TemporaryDirectory() as directory:
            image=Mock();image.save.side_effect=lambda path:Path(path).write_bytes(b'png')
            pipe=Mock(return_value=SimpleNamespace(images=[image]));loader=Mock();loader.from_pretrained.return_value=pipe
            cuda=SimpleNamespace(is_available=lambda:True,device_count=lambda:3,set_device=Mock(),
                get_device_properties=lambda i:SimpleNamespace(total_memory=(4 if i==0 else 16)*memoire.GIB,major=7 if i==1 else 8),
                set_per_process_memory_fraction=Mock())
            torch=SimpleNamespace(cuda=cuda,
                bfloat16='bf16',Generator=lambda device:SimpleNamespace(manual_seed=lambda seed:'generator'))
            d=dict(type='image',modele='weights',references=[],seeds=[42],prompt='hello',id='test',dossier=directory)
            with patch.dict('sys.modules',{'torch':torch,'diffusers':SimpleNamespace(Flux2KleinPipeline=loader),'PIL':SimpleNamespace(Image=Mock())}), \
                 patch.dict('os.environ',{'STUDIO_ANIMATION_EFFECTIVE_LIMIT':str(8*memoire.GIB)}), \
                 patch.object(plateforme,'raison_backend',return_value=''),patch.object(memoire,'disponible',return_value=20*memoire.GIB),patch.object(memoire,'surveiller',return_value=Mock()):
                lancer_visuel.generer(d)
            self.assertTrue(loader.from_pretrained.call_args.kwargs['local_files_only'])
            cuda.set_device.assert_called_once_with(2)
            cuda.set_per_process_memory_fraction.assert_called_once_with(.5,2)
            pipe.enable_sequential_cpu_offload.assert_called_once_with(device='cuda:2')
            self.assertEqual((Path(directory)/'test-42.png').read_bytes(),b'png')
            self.assertFalse(list(Path(directory).glob('*.tmp.png')))


if __name__=='__main__':unittest.main()
