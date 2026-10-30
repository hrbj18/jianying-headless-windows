"""The official Windows homepage stores forward-slash paths."""
from pathlib import Path
import sys
import subprocess
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
import jy14_headless as j


@unittest.skipUnless(sys.platform == 'win32', 'native Windows path semantics')
class WindowsIndexPaths(unittest.TestCase):
    def test_native_forward_slashes_and_case_are_the_same_directory(self):
        with patch.object(j.nd, 'IS_WINDOWS', True):
            self.assertTrue(j.same_native_path('C:/Fixture/Projects/', Path(r'c:\fixture\Projects')))
            self.assertFalse(j.same_native_path('C:/Fixture/Projects-other', Path(r'C:\Fixture\Projects')))
            self.assertFalse(j.same_native_path(None, Path(r'C:\Fixture\Projects')))

    def test_macos_identity_is_not_case_folded(self):
        with patch.object(j.nd, 'IS_WINDOWS', False):
            self.assertFalse(j.same_native_path('/draft/Name', '/draft/name'))

    def test_closed_process_check_handles_localized_tasklist_bytes(self):
        import windows_runtime as runtime
        done = subprocess.CompletedProcess([], 0, '信息: 没有运行的任务。'.encode('gbk'), b'')
        with patch.object(runtime.subprocess, 'run', return_value=done):
            self.assertTrue(runtime._ensure_editor_closed(True)['main_process_closed'])
        done.stdout = b'"JianyingPro.exe","1234"'
        with patch.object(runtime.subprocess, 'run', return_value=done), self.assertRaises(runtime.ApplyError):
            runtime._ensure_editor_closed(True)


if __name__ == '__main__':
    unittest.main()
