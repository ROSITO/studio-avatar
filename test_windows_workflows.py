"""Queue persistence and recovery without a running inference process."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import studio


class QueuePersistenceTest(unittest.TestCase):
    def test_failed_install_of_new_snapshot_preserves_previous_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'taches.json'
            avant = [dict(id='avance', etat='finie')]
            apres = [dict(id='à traiter', etat='en attente')]
            path.write_text(json.dumps(avant))
            with patch.object(studio,'FICHIER_TACHES',path), patch.object(studio,'TACHES',apres):
                with patch.object(Path,'replace',side_effect=PermissionError('Fichier ouvert')):
                    with self.assertRaises(PermissionError): studio.sauver()
                self.assertEqual(json.loads(path.read_text()),avant)
                studio.sauver()
                self.assertEqual(json.loads(path.read_text()),apres)

    def test_restart_does_not_queue_cancelled_tasks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'taches.json'
            path.write_text(json.dumps([
                dict(id='stop', etat='en cours', annuler=True),
                dict(id='ancien', etat='en attente', annuler=True),
                dict(id='reprise', etat='en cours'),
                dict(id='termine', etat='finie'),
            ]))
            taches = studio.lire_taches(path)
            self.assertEqual([t['etat'] for t in taches],['annulée','annulée','en attente','finie'])


if __name__=='__main__': unittest.main()
