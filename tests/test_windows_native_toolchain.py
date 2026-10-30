"""Compiler discovery and Unicode paths, with a process boundary test double."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
import windows_native_toolchain as toolchain


class WindowsCompilerTests(unittest.TestCase):
    def test_discovers_visual_studio_bundled_llvm_without_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            install = Path(temporary)
            vcvars = install / 'VC/Auxiliary/Build/vcvars64.bat'
            clang = install / 'VC/Tools/Llvm/x64/bin/clang-cl.exe'
            for path in (vcvars, clang):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'fixture')
            result = subprocess.CompletedProcess([], 0, str(install) + '\n', '')
            with patch.object(toolchain.os, 'name', 'nt'), \
                    patch.object(toolchain, '_vswhere', return_value=install / 'vswhere.exe'), \
                    patch.object(toolchain.shutil, 'which', return_value=None), \
                    patch.object(toolchain.subprocess, 'run', return_value=result):
                self.assertEqual(toolchain._toolchain(), (vcvars, clang))

    def test_unicode_source_and_destination_never_enter_compiler_argv(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / '中文源码' / '原生导出.cpp'
            output = root / '中文结果' / 'helper.exe'
            staging = root / '编译临时目录'
            for folder in (source.parent, output.parent, staging):
                folder.mkdir()
            original = '// 中文注释\nint main() { return 0; }\n'.encode('utf-8')
            source.write_bytes(original)
            calls = []

            def execute(argv, **kwargs):
                cwd = Path(kwargs['cwd'])
                self.assertTrue(str(cwd).isascii())
                calls.append(argv)
                if '--version' not in argv:
                    self.assertEqual((cwd / 'native_export.cpp').read_bytes(), original)
                    self.assertNotIn('cmd.exe', argv)
                    self.assertNotIn(str(source), argv)
                    self.assertNotIn(str(output), argv)
                    self.assertIn('/Fo:native-export-helper.obj', argv)
                    (cwd / 'native-export-helper.exe').write_bytes(b'compiled helper')
                    (cwd / 'native-export-helper.obj').write_bytes(b'object')
                    return subprocess.CompletedProcess(argv, 0, b'', b'')
                return subprocess.CompletedProcess(argv, 0, 'clang version test\n', '')

            with patch.object(toolchain, '_toolchain', return_value=(Path('C:/BuildTools/vcvars64.bat'),
                                                                      Path('C:/BuildTools/clang-cl.exe'))), \
                    patch.object(toolchain, 'compiler_environment', return_value=({}, {'vcvars_executed':False})), \
                    patch.object(toolchain.subprocess, 'run', side_effect=execute):
                result, identity = toolchain.compile_helper(source, output, staging)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(output.read_bytes(), b'compiled helper')
            self.assertEqual(source.read_bytes(), original)
            self.assertFalse((source.parent / 'native-export-helper.obj').exists())
            self.assertEqual(len(calls), 2)
            self.assertFalse(Path(identity['compiler_cwd']).exists())


if __name__ == '__main__':
    unittest.main()
