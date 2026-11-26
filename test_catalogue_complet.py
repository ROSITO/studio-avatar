"""A partial native checkpoint must not be advertised as installed."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
import modeles


class CompleteCheckpointTest(unittest.TestCase):
    def test_files_required_by_upstream_loaders(self):
        cases=[('qwen3-tts-torch','generation_config.json'),
               ('gemma3-torch','processor_config.json'),
               ('gemma3-torch','tokenizer_config.json'),
               ('flux2-klein4b-torch','text_encoder/model-00002-of-00002.safetensors'),
               ('flux2-klein4b-torch','scheduler/scheduler_config.json'),
               ('flux2-klein4b-torch','tokenizer/chat_template.jinja')]
        for mid,missing in cases:
            with self.subTest(model=mid,missing=missing),tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                manager=modeles.Gestionnaire(SimpleNamespace(ICI=root,MODELES=root/'models',TACHES=[]))
                entry=manager.entry(mid);folder=manager.target(entry)
                for name in entry['required']:
                    path=folder/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'fixture')
                self.assertTrue(manager.valid(entry,folder))
                self.assertTrue((folder/missing).exists())
                (folder/missing).unlink()
                self.assertFalse(manager.valid(entry,folder))


if __name__=='__main__':unittest.main()
