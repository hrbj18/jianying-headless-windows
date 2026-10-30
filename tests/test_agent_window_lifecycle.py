"""Lifecycle safety boundaries: no forced close and no replacement on a race."""
import hashlib,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
from agent_window_lifecycle import close_saved_editor
from live_editor.errors import LiveEditError

class CloseSafety(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.source=self.root/'draft.json';self.source.write_text('{}')
        self.before=dict(status='saved-and-read-back',files=[dict(path=str(self.source),
            sha256=hashlib.sha256(b'{}').hexdigest())],snapshot=dict(token='bound',preview=dict(playing=False)))
        self.editor=Mock();self.editor.run.return_value=False
        self.window=patch('agent_window_lifecycle.current_main_window',return_value=(42,dict(token='bound')))
        self.window.start();self.addCleanup(self.window.stop)
        self.probe=patch('agent_window_lifecycle.NativeEditor');self.factory=self.probe.start();self.addCleanup(self.probe.stop)
    def run_close(self):return close_saved_editor(self.editor,self.before,self.root/'audit')
    def test_unsaved_or_playing_never_dispatches(self):
        for field in ('unsaved','playing'):
            if field=='unsaved':self.before['status']='pending'
            else:self.before['status']='saved-and-read-back';self.before['snapshot']['preview']['playing']=True
            with self.assertRaises(LiveEditError):self.run_close()
        self.editor.run.assert_not_called()
    def test_changed_saved_bytes_never_dispatches(self):
        self.source.write_text('{"changed":true}')
        with self.assertRaises(LiveEditError):self.run_close()
        self.editor.run.assert_not_called()
    def test_racing_draft_is_not_replaced(self):
        self.factory.return_value.__enter__.return_value.status.return_value={'snapshot':{'token':'other'}}
        with self.assertRaises(LiveEditError) as caught:self.run_close()
        self.assertEqual(caught.exception.code,'SESSION_CHANGED')
        self.assertEqual(self.editor.run.call_count,1)
    def test_home_evidence_confirms_even_when_custom_close_handler_returns_false(self):
        self.factory.return_value.__enter__.side_effect=LiveEditError('NO_EDIT_DRAFT','Home')
        result=self.run_close()
        self.assertEqual(result['editor_state'],'home-without-edit-draft')
        self.assertFalse(result['window']['simulated_input'])
        self.assertEqual((self.root/'audit/saved-before-close/00-draft.json').read_bytes(),b'{}')
        self.editor.run.assert_called_once_with(42,1,'close',return_type=1,ctx=dict(token='bound'))
    def test_cancelled_close_stays_unconfirmed(self):
        self.factory.return_value.__enter__.return_value.status.return_value={'snapshot':{'token':'bound'}}
        with patch('agent_window_lifecycle.time.monotonic',side_effect=[0,0,16]),patch('agent_window_lifecycle.time.sleep'):
            with self.assertRaises(LiveEditError) as caught:self.run_close()
        self.assertEqual(caught.exception.code,'CLOSE_NOT_CONFIRMED')
        self.assertEqual(self.editor.run.call_count,1)

if __name__=='__main__':unittest.main()
