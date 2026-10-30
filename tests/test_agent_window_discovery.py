"""Unfocused Qt lookup must be unique and stable before window invocation."""
import struct,sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
from live_editor.window_state import current_main_window
from live_editor.errors import LiveEditError

class WindowDiscovery(unittest.TestCase):
    def setUp(self):
        self.editor=Mock();self.editor.process={'pid':123,'modules':{'Qt6Gui.dll':{'base':0x10000000}}}
        self.editor.context.return_value={'token':'bound'}
        self.reader=Mock();self.reader.pointer.return_value=0
        self.header=struct.pack('<QQq',1,0x2000,2);self.pointers=struct.pack('<QQ',30,40)
        self.reader.read.side_effect=lambda address,n:self.header if address==0x10697740 else self.pointers
        self.reader_patch=patch('live_editor.window_state.Reader');self.factory=self.reader_patch.start();self.addCleanup(self.reader_patch.stop)
        self.factory.return_value.__enter__.return_value=self.reader
        self.editor.get.side_effect=lambda obj,key:('MainWindow' if obj==40 else 'HomeWindow') if key=='objectName' else '剪映专业版'
    def test_unfocused_unique_editor_is_selected(self):
        root,ctx=current_main_window(self.editor);self.assertEqual(root,40)
        self.editor.run.assert_not_called()
    def test_ambiguous_editor_is_refused(self):
        self.editor.get.side_effect=lambda obj,key:'MainWindow' if key=='objectName' else '剪映专业版'
        with self.assertRaises(LiveEditError) as caught:current_main_window(self.editor)
        self.assertEqual(caught.exception.code,'EDITOR_WINDOW_NOT_UNIQUE')
    def test_window_list_race_is_refused(self):
        self.reader.read.side_effect=[self.header,self.pointers,struct.pack('<QQq',1,0x2000,3)]
        with self.assertRaises(LiveEditError) as caught:current_main_window(self.editor)
        self.assertEqual(caught.exception.code,'EDITOR_WINDOW_LIST_CHANGED')
    def test_stale_session_is_refused(self):
        self.editor.context.side_effect=[{'token':'bound'},{'token':'changed'}]
        with self.assertRaises(LiveEditError) as caught:current_main_window(self.editor)
        self.assertEqual(caught.exception.code,'SESSION_CHANGED')

if __name__=='__main__':unittest.main()
