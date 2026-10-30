"""The emergency channel must never accept a different native confirmation."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
from agent_modal_recovery import validate_alert, EXPECTED_TEXT

class ModalRecoveryGuards(unittest.TestCase):
    def test_exact_pending_low_disk_alert_is_allowed(self):
        validate_alert(dict(EXPECTED_TEXT,visible=True,confirmedClose=False))

    def test_different_native_confirmation_is_rejected(self):
        for key in EXPECTED_TEXT:
            with self.subTest(key=key), self.assertRaisesRegex(RuntimeError,'not the verified'):
                validate_alert(dict(EXPECTED_TEXT,visible=True,confirmedClose=False,**{key:'删除草稿'}))

    def test_hidden_or_already_confirmed_alert_cannot_be_cancelled(self):
        for visible,confirmed in [(False,False),(True,True),(None,False)]:
            with self.subTest(visible=visible,confirmed=confirmed),self.assertRaisesRegex(RuntimeError,'not awaiting'):
                validate_alert(dict(EXPECTED_TEXT,visible=visible,confirmedClose=confirmed))

if __name__=='__main__':unittest.main()
