"""Native Qwen adapter contract without downloading weights or running inference."""
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import memoire
import lancer_qwen


class QwenNativeTest(unittest.TestCase):
    def test_cpu_and_cuda_use_local_native_weights_and_reference(self):
        for cuda in (False, True):
            with self.subTest(cuda=cuda), tempfile.TemporaryDirectory() as root:
                model=Mock(); model.generate_voice_clone.return_value=([[.1,.2]],24000)
                loader=Mock(); loader.from_pretrained.return_value=model
                torch=SimpleNamespace(cuda=SimpleNamespace(is_available=lambda:cuda,device_count=lambda:2,
                    get_device_properties=lambda index:SimpleNamespace(total_memory=(8 if index else 4)*memoire.GIB),
                    set_device=Mock(),set_per_process_memory_fraction=Mock()),manual_seed=Mock(),float32='fp32',float16='fp16')
                sound=Mock(); stop=Mock()
                d=dict(modele=root,moteur='qwen3-tts-torch',texte='Bonjour.',reference='reference.wav',
                       transcription='Texte exact.',langue='fr',seed=42,sortie=str(Path(root)/'out.wav'))
                with patch.dict('sys.modules',{'torch':torch,'qwen_tts':SimpleNamespace(Qwen3TTSModel=loader),'soundfile':sound}), \
                     patch.object(memoire,'verifier',return_value=8*memoire.GIB), \
                     patch.object(memoire,'surveiller',return_value=stop),patch.dict(os.environ,{},clear=False):
                    lancer_qwen.generer(d)
                    self.assertEqual(os.environ['HF_HUB_OFFLINE'],'1')
                    self.assertEqual(os.environ['TRANSFORMERS_OFFLINE'],'1')
                args=loader.from_pretrained.call_args
                self.assertEqual(args.args,(str(Path(root).resolve()),))
                self.assertEqual(args.kwargs['device_map'],'cuda:1' if cuda else 'cpu')
                if cuda:
                    torch.cuda.set_device.assert_called_once_with(1)
                    torch.cuda.set_per_process_memory_fraction.assert_called_once_with(.9,1)
                else:torch.cuda.set_device.assert_not_called()
                self.assertEqual(args.kwargs['dtype'],'fp16' if cuda else 'fp32')
                self.assertEqual(args.kwargs['attn_implementation'],'sdpa')
                self.assertTrue(args.kwargs['local_files_only'])
                self.assertEqual(model.generate_voice_clone.call_args.kwargs['ref_text'],'Texte exact.')
                self.assertEqual(model.generate_voice_clone.call_args.kwargs['language'],'French')
                sound.write.assert_called_once_with(d['sortie'],[.1,.2],24000,subtype='PCM_24')
                stop.set.assert_called_once()


if __name__=='__main__':unittest.main()
