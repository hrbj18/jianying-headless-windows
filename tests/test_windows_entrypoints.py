"""Boundaries for the normal CLI and its installed Codex skill binding."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


entry = load_module('normal_windows_entry', ROOT / 'jianying.py')
installer = load_module('windows_skill_installer', ROOT / 'tools/install_codex_skill.py')


@unittest.skipUnless(sys.platform == 'win32', 'normal CLI uses the Windows runtime')
class NormalDoctorTests(unittest.TestCase):
    def doctor(self, editing):
        with patch('windows_runtime.validate_runtime', return_value={'app_build': '11.4.7.14462'}), \
                patch('draftediting_runtime.doctor', return_value=editing), \
                patch('windows_native_toolchain._toolchain', return_value=(Path('vcvars64.bat'), Path('clang-cl.exe'))):
            return entry.doctor()

    def test_missing_official_worker_prevents_ready(self):
        with self.assertRaisesRegex(ValueError, 'missing official'):
            self.doctor({'official_worker_files_present': False})

    def test_stopped_editor_and_pending_bun_copy_do_not_prevent_ready(self):
        editing = {'official_worker_files_present': True, 'status': 'warning',
                   'editor_running': False, 'packaged_bun': {'exists': False}}
        result = self.doctor(editing)
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(result['official_editing_runtime'], editing)


class WorkspaceTests(unittest.TestCase):
    def test_suggested_reference_uses_unique_job_name(self):
        with tempfile.TemporaryDirectory(prefix='jy-entry-') as temporary, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            entry.new_workspace(['--name', 'demo', '--root', temporary])
            result = json.loads(output.getvalue())
        self.assertEqual(result['suggested_ref'], 'local://' + Path(result['job']).name)
        self.assertNotEqual(result['suggested_ref'], 'local://demo')


class SkillBindingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='jy-skill-test-')
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name).resolve()
        self.destination = self.folder / 'skill'

    def prior_binding(self, value):
        binding = self.destination / 'references/local.json'
        binding.parent.mkdir(parents=True)
        binding.write_text(json.dumps({'project_root': value}), encoding='utf-8')
        return binding

    def test_default_refuses_another_checkout(self):
        binding = self.prior_binding(str(self.folder / 'old-project'))
        before = binding.read_bytes()
        with self.assertRaisesRegex(ValueError, '--rebind'):
            installer.install(self.destination)
        self.assertEqual(binding.read_bytes(), before)

    def test_explicit_rebind_updates_managed_skill(self):
        binding = self.prior_binding(str(self.folder / 'old-project'))
        result = installer.install(self.destination, rebind=True)
        self.assertEqual(result['status'], 'skill-installed')
        self.assertEqual(json.loads(binding.read_text(encoding='utf-8'))['project_root'], str(installer.ROOT))
        self.assertTrue((self.destination / 'SKILL.md').is_file())

    def test_rebind_does_not_overwrite_unmanaged_directory(self):
        self.destination.mkdir()
        with self.assertRaisesRegex(ValueError, 'not managed'):
            installer.install(self.destination, rebind=True)

    def test_rejects_symlink_before_resolving_its_target(self):
        with patch.object(Path, 'is_symlink', return_value=True), \
                patch.object(Path, 'resolve') as resolve:
            with self.assertRaisesRegex(ValueError, 'real directory'):
                installer.install(self.destination, rebind=True)
        resolve.assert_not_called()


if __name__ == '__main__':
    unittest.main()
