"""Two real processes contend for the same Agent command lock."""
import os, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
from agent_entry import AgentLock
from live_editor import paths

@unittest.skipUnless(os.name=='nt','Windows process lock')
class SharedAgentLock(unittest.TestCase):
    def test_second_client_is_refused_then_can_acquire_after_release(self):
        with tempfile.TemporaryDirectory() as t:
            script=('import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);'
                    'from live_editor import paths;paths.STATE_ROOT=Path(sys.argv[2]);'
                    'from agent_entry import AgentLock;lock=AgentLock();lock.__enter__();'
                    'print("acquired");lock.__exit__()')
            command=[sys.executable,'-X','utf8','-B','-c',script,str(ROOT/'engine'),t]
            with patch.object(paths,'STATE_ROOT',Path(t)):
                with AgentLock():
                    denied=subprocess.run(command,capture_output=True,text=True,timeout=15)
                    self.assertNotEqual(denied.returncode,0)
                    self.assertIn('AGENT_BUSY',denied.stderr)
                granted=subprocess.run(command,capture_output=True,text=True,timeout=15)
                self.assertEqual(granted.returncode,0,granted.stderr)
                self.assertIn('acquired',granted.stdout)

if __name__=='__main__':unittest.main()
