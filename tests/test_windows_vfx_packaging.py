"""Offline filesystem/transaction tests; these do not assert native crypto behavior."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
import windows_vfx_packaging as freeze
import windows_vfx as vfx
from runtime_profiles import WINDOWS_1147_PROFILE


class FreezeDraftBoundaries(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='jy-vfx-freeze-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / 'work'; self.root.mkdir()
        self.source = self.root / 'draft'; self.source.mkdir()
        self.resource = self.root / 'external'; self.resource.mkdir()
        (self.resource / 'config.json').write_bytes(b'payload')
        # An empty installed-package tag is valid and must survive the backup.
        (self.resource / 'effect.tag').write_bytes(b'')
        files = {path.name: {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'size': path.stat().st_size}
                 for path in self.resource.iterdir()}
        self.entry = {'key': 'filter/test', 'bucket': 'effects', 'files': files,
                      'tree_sha256': vfx.manifest_hash(files)}
        self.relative_main = str(Path('Timelines/main/draft_content.json'))
        self.main = self.source / self.relative_main; self.main.parent.mkdir(parents=True)
        self.timeline = {'id': 'main', 'materials': {'effects': [
            {'id': 'filter1', 'type': 'filter', 'value': .4, 'path': str(self.resource)}]},
            'tracks': [{'type': 'video', 'segments': [{'id': 'video1', 'extra_material_refs': ['filter1']}]}]}
        self.main.write_text(json.dumps(self.timeline), encoding='utf-8')
        (self.source / 'draft_content.json').write_bytes(b'ROOT MIRROR MUST STAY IDENTICAL')
        (self.source / 'note.txt').write_bytes(b'other user bytes')
        self.before = freeze._manifest(self.source)
        self.encrypt_count = 0
        self.after_encryption_hook = None

        def encrypt(payload, path):
            self.encrypt_count += 1
            with Path(path).open('xb') as stream:
                stream.write(payload)
            if self.after_encryption_hook:
                self.after_encryption_hook()

        self.helper = SimpleNamespace(_encrypt_metadata_from_memory=encrypt,
                                      _decrypt_metadata_in_memory=lambda path: json.loads(Path(path).read_bytes()))
        self.patch(freeze, 'configure_environment', return_value={})
        self.patch(freeze.native.j.nd, 'validate_runtime', return_value={'runtime_profile': WINDOWS_1147_PROFILE})
        self.patch(freeze.native.j.nd, 'helper', return_value=self.helper)

        def read_draft(path, runtime):
            path = Path(path)
            timeline = json.loads((path / self.relative_main).read_bytes())
            return path, freeze._manifest(path), timeline, {'source_timeline': self.relative_main}

        def validate(timeline, runtime):
            for node in timeline['materials']['effects']:
                vfx.verify_resource(node['path'], self.entry)
            return {'filters': 1, 'resource_keys': ['filter/test']}

        self.patch(freeze.native, 'read_draft', side_effect=read_draft)
        self.patch(freeze.vfx, 'validate_timeline', side_effect=validate)
        self.patch(freeze.vfx, 'entry_for_node', return_value=self.entry)

    def patch(self, target, name, **options):
        context = patch.object(target, name, **options)
        result = context.start(); self.addCleanup(context.stop)
        return result

    @property
    def owned(self):
        return self.source / 'Resources/reviewed-vfx' / self.entry['tree_sha256']

    def test_freezes_all_bytes_and_only_main_paths_then_is_idempotent(self):
        report = freeze.run(self.source, self.root / 'audit1')
        self.assertEqual(report['status'], 'frozen-and-read-back')
        self.assertEqual(self.encrypt_count, 1)
        self.assertEqual((self.owned / 'effect.tag').read_bytes(), b'')
        after = json.loads(self.main.read_bytes())
        expected = deepcopy(self.timeline)
        expected['materials']['effects'][0]['path'] = self.owned.as_posix()
        self.assertEqual(after, expected)
        self.assertEqual((self.source / 'draft_content.json').read_bytes(), b'ROOT MIRROR MUST STAY IDENTICAL')
        self.assertEqual(freeze._manifest(self.root / 'audit1/before'), self.before)
        self.assertEqual((self.root / 'audit1/before.enc').read_bytes(),
                         (self.root / 'audit1/before' / self.relative_main).read_bytes())
        again = freeze.run(self.source, self.root / 'audit2')
        self.assertEqual(again['status'], 'already-draft-owned')
        self.assertEqual(self.encrypt_count, 1)
        self.assertFalse(again['main_replaced'])

    def test_concurrent_user_edit_prevents_main_replacement_and_is_retained(self):
        before_main = self.main.read_bytes()
        self.after_encryption_hook = lambda: (self.source / 'note.txt').write_bytes(b'concurrent user edit')
        report = freeze.run(self.source, self.root / 'audit')
        self.assertEqual(report['status'], 'failed-or-unverified')
        self.assertIn('Concurrent draft change', report['error'])
        self.assertFalse(report['main_replaced'])
        self.assertEqual(self.main.read_bytes(), before_main)
        self.assertEqual((self.source / 'note.txt').read_bytes(), b'concurrent user edit')
        self.assertTrue(Path(report['retained_temporary_ciphertext']).is_file())
        self.assertTrue((self.root / 'audit/before.enc').is_file())

    def test_existing_owned_package_must_match_before_main_mutation(self):
        self.owned.mkdir(parents=True)
        (self.owned / 'config.json').write_bytes(b'tampered')
        report = freeze.run(self.source, self.root / 'audit')
        self.assertEqual(report['status'], 'failed-or-unverified')
        self.assertFalse(report['main_replaced'])
        self.assertEqual(self.encrypt_count, 0)
        self.assertEqual(json.loads(self.main.read_bytes()), self.timeline)

    def test_partial_copy_failure_retains_source_and_recovery(self):
        original = freeze._copy_file
        def fail_tag(source, target):
            if Path(source).name == 'effect.tag':
                raise OSError('simulated copy interruption')
            return original(source, target)
        self.patch(freeze, '_copy_file', side_effect=fail_tag)
        report = freeze.run(self.source, self.root / 'audit')
        self.assertEqual(report['status'], 'failed-or-unverified')
        self.assertIn('copy interruption', report['error'])
        self.assertEqual(self.encrypt_count, 0)
        self.assertTrue((self.owned / 'config.json').is_file())
        self.assertEqual(json.loads(self.main.read_bytes()), self.timeline)
        self.assertTrue((self.root / 'audit/before.enc').is_file())

    def test_audit_inside_source_or_existing_directory_is_rejected(self):
        for target in [self.source / 'audit', self.root]:
            with self.subTest(target=target), self.assertRaises(ValueError):
                freeze.run(self.source, target)
        self.assertEqual(self.encrypt_count, 0)

    def test_reparse_marker_is_rejected(self):
        with patch.object(Path, 'lstat', return_value=SimpleNamespace(st_file_attributes=0x400, st_mode=stat.S_IFDIR)):
            with self.assertRaisesRegex(ValueError, 'reparse'):
                freeze._ordinary(self.resource)


if __name__ == '__main__':
    unittest.main()
