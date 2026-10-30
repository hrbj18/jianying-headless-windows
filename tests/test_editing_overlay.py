from pathlib import Path
from datetime import datetime,timezone
import sys,tempfile,time,unittest,uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
from editing_process import Store,write
from editing_overlay import dock_rect,snapshot,select_run,hidden_reason


class CompanionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(self.temp.name);self.run=self.store.create('recent task','a real goal');self.folder=self.store.folder(self.run)
    def test_completed_task_is_standby_and_preserves_real_changes(self):
        self.store.event(self.run,'action',actionId=str(uuid.uuid4()),state='verified',title='export',changes=[dict(label='字号',before=8.2,after=7.6)])
        value=snapshot(self.folder)
        self.assertEqual(value['state'],'idle');self.assertIn('待命',value['status'])
        self.assertIn('8.2 → 7.6',value['text']);self.assertIn('没有正在执行',value['text'])
    def test_recent_heartbeat_and_missing_receipt_are_distinguished(self):
        action=str(uuid.uuid4());self.store.event(self.run,'action',actionId=action,state='running',title='preview',reason='check framing')
        write(self.folder/'heartbeat.json',dict(actionId=action,at=time.time()))
        self.assertEqual(snapshot(self.folder)['state'],'running')
        self.assertEqual(snapshot(self.folder,clock=time.time()+30)['state'],'uncertain')
        # A partially written append cannot turn a running action into success.
        with (self.folder/'events.jsonl').open('a') as f:f.write('{"unfinished":')
        self.assertEqual(snapshot(self.folder)['state'],'running')
    def test_latest_run_and_project_isolation(self):
        self.assertEqual(select_run(self.temp.name),self.folder)
        with self.assertRaises(ValueError):select_run(self.temp.name,'../elsewhere')
        self.assertEqual(snapshot(None)['state'],'idle')
    def test_relative_dock_follows_editor_and_clamps_multiple_monitors(self):
        a=dock_rect((0,0,1600,900),(0,0,1920,1040),(366,330))
        b=dock_rect((100,70,1700,970),(0,0,1920,1040),(366,330))
        self.assertEqual((b[0]-a[0],b[1]-a[1]),(100,70))
        x,y,width,height=dock_rect((-1900,-100,-300,800),(-1920,0,0,1040),(366,330),(-5000,5000))
        self.assertGreaterEqual(x,-1920);self.assertLessEqual(x+width,0);self.assertGreaterEqual(y,0);self.assertLessEqual(y+height,1040)
        self.assertEqual(dock_rect((0,0,1600,900),(0,0,1920,1040),(366,36))[3],36)
    def test_companion_hides_with_editor_and_never_covers_other_apps(self):
        self.assertIsNone(hidden_reason(10,False,1,1,2))
        self.assertIsNone(hidden_reason(10,False,2,1,2))
        self.assertEqual(hidden_reason(10,True,1,1,2),'editor-minimized')
        self.assertEqual(hidden_reason(10,False,3,1,2),'editor-in-background')
        self.assertEqual(hidden_reason(None,False,1,1,2),'waiting-editor-window')

if __name__=='__main__':unittest.main()
