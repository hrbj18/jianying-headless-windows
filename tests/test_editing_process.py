import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
from editing_process import Store, execute, write


class EditingProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / 'runs')
        self.run = self.store.create('real task', 'verify operation provenance')
        self.spec = dict(id=str(uuid.uuid4()), title='verify', stage='review', args=['verify-build','--build','unused'])

    def test_pause_and_unhandled_note_prevent_dispatch(self):
        write(self.store.folder(self.run)/'control.json', {'paused':True})
        with patch('editing_process.subprocess.Popen') as spawn:
            self.assertEqual(execute(self.store,self.run,self.spec)['status'],'paused')
            spawn.assert_not_called()
        write(self.store.folder(self.run)/'control.json', {'paused':False})
        (self.store.folder(self.run)/'inputs.jsonl').write_text(json.dumps({'id':str(uuid.uuid4()),'text':'change'})+'\n')
        with patch('editing_process.subprocess.Popen') as spawn:
            self.assertEqual(execute(self.store,self.run,self.spec)['status'],'waiting-user-input')
            spawn.assert_not_called()

    def test_completed_or_ambiguous_action_is_never_replayed(self):
        def fake_spawn(*args, **kwargs):
            kwargs['stdout'].write(b'{"status":"verified"}'); kwargs['stdout'].flush()
            class Child:
                pid=123
                def poll(self): return 0
            return Child()
        with patch('editing_process.subprocess.Popen', side_effect=fake_spawn) as spawn:
            self.assertEqual(execute(self.store,self.run,self.spec)['status'],'verified')
            self.assertFalse(execute(self.store,self.run,self.spec)['dispatched'])
            self.assertEqual(spawn.call_count,1)
        self.spec['title']='changed'
        with self.assertRaisesRegex(ValueError,'another plan'): execute(self.store,self.run,self.spec)
        self.spec.update(id=str(uuid.uuid4()),title='uncertain')
        with patch('editing_process.subprocess.Popen',side_effect=OSError('launch interrupted')):
            with self.assertRaises(OSError): execute(self.store,self.run,self.spec)
        with patch('editing_process.subprocess.Popen') as spawn:
            with self.assertRaisesRegex(ValueError,'never be replayed'): execute(self.store,self.run,self.spec)
            spawn.assert_not_called()

    def test_artifact_hash_is_bound_to_evidence(self):
        p=Path(self.temp.name)/'frame.png';p.write_bytes(b'example')
        with self.assertRaisesRegex(ValueError,'does not match'): self.store.artifact(self.run,p,'preview',expected_sha='wrong')
        self.assertEqual(len(self.store.events(self.run)),1)
        with self.assertRaises(ValueError): self.store.folder('../escape')

if __name__=='__main__':unittest.main()
