"""Real isolated file/index transactions; no native runtime or user drafts."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
import delivery_lifecycle as dl


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def read(path):
    return json.loads(Path(path).read_text('utf-8'))


class FakeBackend:
    def __init__(self, root):
        self.draft_root = root
        self.running = False
        self.acquired = self.released = 0
        self.builds = {}
        self.copies = []
        self.acl_failure = False

    def validate_runtime(self):
        return {'runtime_profile': 'isolated-test'}

    def ensure_closed(self):
        if self.running:
            raise ValueError('editor is running')

    def acquire(self, root):
        assert root == self.draft_root
        self.acquired += 1
        return object()

    def release(self, token):
        self.released += 1

    def attributes(self, path):
        return {'fixture.dacl': b'preserved'}

    def copy_attributes(self, attrs, destination, audit, source):
        return ({'fixture.dacl': b'changed'} if self.acl_failure else dict(attrs)), []

    def verify_build(self, build):
        return deepcopy(self.builds[str(build)])

    def metadata(self, path):
        return read(path)

    def entry(self, metadata, target):
        return deepcopy(metadata)

    def copy_draft(self, source, destination, record):
        self.copies.append((source, destination))
        shutil.copytree(source, destination)
        return [{'mode': 'fixture-byte-copy'}]


class DeliveryLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='jy-delivery-')
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name).resolve()
        self.root = self.folder / 'native-root'; self.root.mkdir()
        self.archive = self.folder / 'archive'
        self.backend = FakeBackend(self.root)
        self.owned = []
        entries = []
        for i in range(8):
            name = ('中文工程-' + str(i)) if i != 7 else '.jy14-headless-failed-fixture'
            path = self.root / name
            self.make_draft(path, 'owner-' + str(i))
            row = {'draft_id': 'owner-' + str(i), 'path': str(path), 'files': dl.files_manifest(path)}
            self.owned.append(row)
            entries.append(self.metadata(path, row['draft_id']))
        self.other = [self.metadata(self.root / 'NEURAL-other', 'other-1'),
                      self.metadata(self.root / 'PRISM-other', 'other-2')]
        entries.insert(2, deepcopy(self.other[0])); entries.append(deepcopy(self.other[1]))
        self.index_path = self.root / 'root_meta_info.json'
        self.initial_index = {'root_path': self.root.as_posix(), 'all_draft_store': entries,
                              'draft_ids': 49, 'native_unknown': {'preserve': True}}
        dump(self.index_path, self.initial_index)
        self.manifest_path = self.folder / 'delivery.json'
        manifest = {'schema': dl.SCHEMA, 'delivery_id': 'live-20261019', 'draft_root': str(self.root),
                    'archive_root': str(self.archive), 'expected_index_sha256': self.hash(self.index_path),
                    'owned_drafts': self.owned,
                    'slots': [{'slot_id': 'slot-' + str(slot), 'draft_id': self.owned[i]['draft_id'],
                               'path': self.owned[i]['path']} for slot, i in enumerate([0, 1, 6, 3])],
                    'source_original': 'protected-original', 'protected': {'keep': 'unknown fields'}}
        dump(self.manifest_path, manifest)
        self.initial_manifest_bytes = self.manifest_path.read_bytes()
        self.initial_index_bytes = self.index_path.read_bytes()
        self.audit_number = 0

    @staticmethod
    def hash(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    @staticmethod
    def metadata(path, identity):
        return {'draft_id': identity, 'draft_fold_path': path.as_posix(), 'draft_name': path.name,
                'tm_duration': 1000000, 'keep_native_field': [1, 2, 3]}

    def make_draft(self, path, identity):
        media = path / 'Resources' / 'headless-media'; media.mkdir(parents=True)
        (media / 'source.mp4').write_bytes(('fixture-' + identity).encode())
        dump(path / 'draft_meta_info.json', self.metadata(path, identity))
        dump(path / 'draft_info.json', {'id': 'timeline-' + identity})

    def audit(self):
        self.audit_number += 1
        return self.folder / ('audit-' + str(self.audit_number))

    def reconcile(self):
        return dl.reconcile(self.manifest_path, self.audit(), _backend=self.backend)

    def make_build(self):
        build = self.folder / 'build'; build.mkdir()
        target = self.root / '新版本-incoming'
        self.make_draft(build / 'draft', 'incoming-9')
        # Native metadata already names its eventual independent live target.
        dump(build / 'draft' / 'draft_meta_info.json', self.metadata(target, 'incoming-9'))
        record = {'target': str(target), 'draft_id': 'incoming-9',
                  'runtime_profile': 'isolated-test',
                  'files': dl.files_manifest(build / 'draft')}
        dump(build / 'build.json', record)
        dump(build / 'plan.json', {'schema': 'isolated-plan-fixture'})
        self.backend.builds[str(build)] = record
        return build, target

    def assert_only_four_owned_visible(self):
        manifest, index = read(self.manifest_path), read(self.index_path)
        owned_ids = {r['draft_id'] for r in manifest['owned_drafts']}
        visible = [e for e in index['all_draft_store'] if e['draft_id'] in owned_ids]
        self.assertEqual(len(visible), 4)
        self.assertEqual({e['draft_id'] for e in visible}, {s['draft_id'] for s in manifest['slots']})
        self.assertEqual([e for e in index['all_draft_store'] if e['draft_id'].startswith('other-')], self.other)
        self.assertEqual(index['draft_ids'], 49)
        self.assertEqual(index['native_unknown'], {'preserve': True})
        self.assertEqual(manifest['protected'], {'keep': 'unknown fields'})
        self.assertEqual(manifest['expected_index_sha256'], self.hash(self.index_path))

    def test_inspect_is_read_only_and_identifies_four_exact_retirements(self):
        before = {p.name for p in self.folder.iterdir()}
        result = dl.inspect(self.manifest_path, _backend=self.backend)
        self.assertEqual(result['task_visible_count'], 8)
        self.assertEqual({r['draft_id'] for r in result['archive_candidates']},
                         {'owner-2', 'owner-4', 'owner-5', 'owner-7'})
        self.assertEqual({p.name for p in self.folder.iterdir()}, before)
        self.assertEqual(self.index_path.read_bytes(), self.initial_index_bytes)
        self.assertEqual(self.backend.acquired, 0)

    def test_reconcile_archives_only_owned_old_four_with_complete_records(self):
        result = self.reconcile()
        self.assert_only_four_owned_visible()
        self.assertEqual(len(result['archives']), 4)
        for row in result['archives']:
            self.assertFalse(Path(row['original_path']).exists())
            self.assertTrue(Path(row['path']).is_relative_to(self.archive))
            self.assertEqual(dl.files_manifest(row['path']), row['files'])
            self.assertEqual(read(Path(row['path']).parent / 'record.json')['entry'], row['entry'])
        self.assertEqual(self.backend.acquired, self.backend.released)
        self.assertFalse(any(p.name.startswith('.jy14-') for p in self.root.iterdir()))

    def test_reconcile_again_does_not_archive_current_slots(self):
        self.reconcile(); result = self.reconcile()
        self.assert_only_four_owned_visible()
        self.assertEqual(len(result['archives']), 4)

    def test_index_conflict_preserves_every_owned_directory(self):
        index = read(self.index_path); index['new_external_field'] = True; dump(self.index_path, index)
        changed = self.index_path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'index hash conflict'):
            self.reconcile()
        self.assertEqual(self.index_path.read_bytes(), changed)
        self.assertEqual(self.manifest_path.read_bytes(), self.initial_manifest_bytes)
        self.assertTrue(all(Path(r['path']).is_dir() for r in self.owned))

    def test_changed_owned_file_is_not_archived(self):
        (Path(self.owned[4]['path']) / 'draft_info.json').write_bytes(b'edited')
        with self.assertRaisesRegex(ValueError, 'hash conflict'):
            self.reconcile()
        self.assertTrue(all(Path(r['path']).is_dir() for r in self.owned))
        self.assertEqual(self.index_path.read_bytes(), self.initial_index_bytes)

    def test_running_editor_blocks_transaction_before_lock(self):
        self.backend.running = True
        with self.assertRaisesRegex(ValueError, 'editor is running'):
            self.reconcile()
        self.assertEqual(self.backend.acquired, 0)
        self.assertEqual(self.index_path.read_bytes(), self.initial_index_bytes)

    def test_path_escape_and_archive_inside_scan_root_are_rejected(self):
        manifest = read(self.manifest_path)
        manifest['owned_drafts'][0]['path'] = str(self.root / '..' / 'outside')
        dump(self.manifest_path, manifest)
        with self.assertRaisesRegex(ValueError, 'Unsafe absolute path'):
            self.reconcile()
        manifest = json.loads(self.initial_manifest_bytes)
        manifest['archive_root'] = str(self.root / 'archives')
        dump(self.manifest_path, manifest)
        with self.assertRaisesRegex(ValueError, 'outside the scan root'):
            self.reconcile()

    def test_symlink_in_owned_tree_is_rejected_before_any_move(self):
        source = self.folder / 'outside.bin'; source.write_bytes(b'outside')
        alias = Path(self.owned[4]['path']) / 'alias.bin'
        try:
            alias.symlink_to(source)
        except OSError as error:
            self.skipTest('symlink unavailable: ' + str(error))
        with self.assertRaisesRegex(ValueError, 'Symlinks/reparse'):
            self.reconcile()
        self.assertEqual(self.index_path.read_bytes(), self.initial_index_bytes)
        self.assertTrue(all(Path(r['path']).is_dir() for r in self.owned))

    def test_windows_reparse_attribute_is_rejected(self):
        path = Path(self.owned[0]['path']) / 'draft_info.json'
        real = Path.lstat
        def lstat(current, *args, **kwargs):
            value = real(current, *args, **kwargs)
            if current == path:
                return SimpleNamespace(st_mode=value.st_mode, st_file_attributes=0x400)
            return value
        with patch.object(Path, 'lstat', lstat), self.assertRaisesRegex(ValueError, 'reparse'):
            dl.files_manifest(self.owned[0]['path'])

    def test_acl_failure_rolls_back_moves_without_replacing_index(self):
        self.backend.acl_failure = True
        audit = self.audit()
        with self.assertRaisesRegex(ValueError, 'Security attributes'):
            dl.reconcile(self.manifest_path, audit, _backend=self.backend)
        self.assertEqual(self.index_path.read_bytes(), self.initial_index_bytes)
        self.assertEqual(self.manifest_path.read_bytes(), self.initial_manifest_bytes)
        self.assertTrue(all(Path(r['path']).is_dir() for r in self.owned))
        self.assertTrue(read(audit / 'transaction.json')['precommit_moves_rolled_back'])

    def test_second_move_failure_retains_journal_and_restores_first(self):
        actual = dl.j.exclusive_rename
        count = 0
        def rename(source, destination):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError('injected archive move failure')
            return actual(source, destination)
        audit = self.audit()
        with patch.object(dl.j, 'exclusive_rename', side_effect=rename), self.assertRaisesRegex(ValueError, 'injected'):
            dl.reconcile(self.manifest_path, audit, _backend=self.backend)
        self.assertTrue(all(Path(r['path']).is_dir() for r in self.owned))
        self.assertEqual(self.index_path.read_bytes(), self.initial_index_bytes)
        self.assertEqual(read(audit / 'transaction.json')['phase'], 'failed')

    def test_failure_after_index_commit_retains_next_manifest_for_recovery(self):
        actual = dl.os.replace
        def replace(source, destination):
            if Path(destination) == self.manifest_path:
                raise OSError('injected manifest commit failure')
            return actual(source, destination)
        audit = self.audit()
        with patch.object(dl.os, 'replace', side_effect=replace), self.assertRaisesRegex(ValueError, 'manifest commit'):
            dl.reconcile(self.manifest_path, audit, _backend=self.backend)
        journal = read(audit / 'transaction.json')
        self.assertTrue(journal['index_committed'])
        self.assertFalse(journal['manifest_committed'])
        self.assertEqual(len(read(audit / 'manifest.next.json')['archives']), 4)
        self.assertEqual(self.manifest_path.read_bytes(), self.initial_manifest_bytes)
        self.assertEqual(dl.inspect(self.manifest_path, _backend=self.backend)['status'], 'delivery-conflict')

    def test_promote_replaces_one_slot_and_uses_private_dependency_copy(self):
        self.reconcile(); build, target = self.make_build()
        before = read(self.manifest_path)
        audit = self.audit()
        result = dl.promote(self.manifest_path, 'slot-2', build, audit, _backend=self.backend)
        self.assert_only_four_owned_visible()
        self.assertTrue(target.exists())
        self.assertEqual(result['slots'][2]['draft_id'], 'incoming-9')
        self.assertEqual(len(result['archives']), len(before['archives']) + 1)
        self.assertTrue(self.backend.copies)
        self.assertFalse(self.backend.copies[0][1].is_relative_to(self.root))
        self.assertEqual(read(audit / 'incoming-media.json')['materialization'], [{'mode': 'fixture-byte-copy'}])

    def test_promote_rejects_unreconciled_delivery(self):
        build, target = self.make_build()
        with self.assertRaisesRegex(ValueError, 'Reconcile'):
            dl.promote(self.manifest_path, 'slot-2', build, self.audit(), _backend=self.backend)
        self.assertFalse(target.exists())
        self.assertEqual(self.index_path.read_bytes(), self.initial_index_bytes)

    def test_private_restore_never_changes_home_or_adds_fifth_slot(self):
        result = self.reconcile(); saved = result['archives'][0]
        index_before = self.index_path.read_bytes(); manifest_before = self.manifest_path.read_bytes()
        result = dl.restore(self.manifest_path, saved['archive_id'], self.audit(), _backend=self.backend)
        self.assertEqual(dl.files_manifest(result['out']), saved['files'])
        self.assertFalse(result['registered']); self.assertFalse(result['native_bindings_rebased'])
        self.assertTrue((Path(result['audit']) / 'restore-media.json').is_file())
        self.assertEqual(self.index_path.read_bytes(), index_before)
        self.assertEqual(self.manifest_path.read_bytes(), manifest_before)
        self.assert_only_four_owned_visible()

    def test_explicit_slot_restore_replaces_current_and_restores_original_path(self):
        result = self.reconcile()
        saved = next(a for a in result['archives'] if a['draft_id'] == 'owner-2')
        result = dl.restore(self.manifest_path, saved['archive_id'], self.audit(), slot_id='slot-2', _backend=self.backend)
        self.assert_only_four_owned_visible()
        self.assertTrue(Path(saved['original_path']).exists())
        self.assertFalse(Path(saved['path']).exists())
        self.assertEqual(result['slots'][2]['draft_id'], 'owner-2')
        self.assertEqual(next(a for a in result['archives'] if a['archive_id'] == saved['archive_id'])['state'], 'restored')


@unittest.skipUnless(sys.platform == 'win32' and os.environ.get('JY_RUN_NATIVE_DELIVERY_ACL') == '1',
                     'explicit isolated Windows C/D ACL integration check')
class NativeCrossVolumeACLTests(unittest.TestCase):
    def test_real_backend_archives_on_c_and_atomically_updates_manifest_on_d(self):
        self.run_native_fixture(different_parent_acls=False)

    def test_distinct_parent_dacls_reject_cross_parent_copy_and_accept_same_parent_commit(self):
        self.run_native_fixture(different_parent_acls=True)

    def run_native_fixture(self, different_parent_acls):
        if not Path('C:/').is_dir() or not Path('D:/').is_dir():
            self.skipTest('C and D volumes required')
        c_parent = dl._path('C:/JianyingHeadless/work/lifecycle-tests', exists=False)
        d_parent = dl._path('D:/JianyingHeadless/work', directory=True)
        c_parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='acl-c-', dir=c_parent) as c_tmp, \
                tempfile.TemporaryDirectory(prefix='acl-d-', dir=d_parent) as d_tmp:
            c_root, d_root = Path(c_tmp).resolve(), Path(d_tmp).resolve()
            native_parent = c_root / 'native-parent'; native_parent.mkdir()
            archive_parent = c_root / 'archive-parent'; archive_parent.mkdir()
            if different_parent_acls:
                import windows_runtime
                # Modify only the new isolated fixture parents. Different
                # inherited ACE sets reproduce the real deployment boundary;
                # production DACL copying/validation remains unchanged.
                windows_runtime._powershell(r'''
function Set-FixtureAcl([string]$fixturePath, [string]$fixtureExtraSid, [string]$fixtureRights) {
  $fixtureAcl = [System.Security.AccessControl.DirectorySecurity]::new()
  $fixtureIdentity = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
  $fixtureAcl.SetOwner($fixtureIdentity)
  $fixtureAcl.SetAccessRuleProtection($true, $false)
  $fixtureInheritance = [System.Security.AccessControl.InheritanceFlags]'ContainerInherit,ObjectInherit'
  foreach ($fixtureOwnerSid in @($fixtureIdentity.Value, 'S-1-5-18', 'S-1-5-32-544')) {
    $fixtureRule = [System.Security.AccessControl.FileSystemAccessRule]::new(
      [System.Security.Principal.SecurityIdentifier]::new($fixtureOwnerSid),
      [System.Security.AccessControl.FileSystemRights]::FullControl, $fixtureInheritance,
      [System.Security.AccessControl.PropagationFlags]::None,
      [System.Security.AccessControl.AccessControlType]::Allow)
    $fixtureAcl.AddAccessRule($fixtureRule)
  }
  $fixtureExtraRule = [System.Security.AccessControl.FileSystemAccessRule]::new(
    [System.Security.Principal.SecurityIdentifier]::new($fixtureExtraSid),
    [System.Security.AccessControl.FileSystemRights]$fixtureRights, $fixtureInheritance,
    [System.Security.AccessControl.PropagationFlags]::None,
    [System.Security.AccessControl.AccessControlType]::Allow)
  $fixtureAcl.AddAccessRule($fixtureExtraRule)
  [System.IO.Directory]::SetAccessControl($fixturePath, $fixtureAcl)
}
Set-FixtureAcl $env:JY_FIXTURE_NATIVE 'S-1-5-32-545' 'ReadAndExecute'
Set-FixtureAcl $env:JY_FIXTURE_ARCHIVE 'S-1-5-11' 'Modify'
''', {'JY_FIXTURE_NATIVE': str(native_parent), 'JY_FIXTURE_ARCHIVE': str(archive_parent)})
            native_root = native_parent / 'native-root'; native_root.mkdir()
            archive = archive_parent / 'archive'
            rows, entries = [], []
            for i in range(5):
                path = native_root / ('中文小样-' + str(i)); path.mkdir()
                (path / 'fixture.txt').write_text('fixture-' + str(i), encoding='utf-8')
                row = {'draft_id': 'fixture-' + str(i), 'path': str(path), 'files': dl.files_manifest(path)}
                rows.append(row)
                entries.append({'draft_id': row['draft_id'], 'draft_fold_path': path.as_posix()})
            index_path = native_root / 'root_meta_info.json'
            dump(index_path, {'root_path': native_root.as_posix(), 'draft_ids': 91, 'all_draft_store': entries})
            manifest_path = d_root / 'delivery.json'
            dump(manifest_path, {'schema': dl.SCHEMA, 'delivery_id': 'native-acl-fixture',
                 'draft_root': str(native_root), 'archive_root': str(archive),
                 'expected_index_sha256': hashlib.sha256(index_path.read_bytes()).hexdigest(),
                 'owned_drafts': rows, 'slots': [{'slot_id': 'slot-' + str(i),
                     'draft_id': rows[i]['draft_id'], 'path': rows[i]['path']} for i in range(4)]})
            backend = dl.NativeBackend()
            # Only this backend instance is rebound; nd.DRAFT_ROOT and the real
            # user's index are neither patched nor written by the fixture.
            backend.draft_root = native_root
            index_acl, manifest_acl = backend.attributes(index_path), backend.attributes(manifest_path)
            if different_parent_acls:
                cross_parent = archive_parent / 'cross-parent-index.tmp'
                cross_parent.write_bytes(index_path.read_bytes())
                proof = d_root / 'cross-parent-acl-proof'; proof.mkdir()
                self.assertNotEqual(backend.attributes(cross_parent), index_acl)
                with self.assertRaisesRegex(RuntimeError, 'windows.dacl'):
                    backend.copy_attributes(index_acl, cross_parent, proof, index_path)
            result = dl.reconcile(manifest_path, d_root / 'audit', _backend=backend)
            self.assertEqual(result['task_visible_count'], 4)
            self.assertEqual(backend.attributes(index_path), index_acl)
            self.assertEqual(backend.attributes(manifest_path), manifest_acl)
            self.assertEqual(read(index_path)['draft_ids'], 91)
            self.assertEqual(read(manifest_path)['expected_index_sha256'], hashlib.sha256(index_path.read_bytes()).hexdigest())
            self.assertTrue(Path(result['archives'][0]['path']).is_relative_to(archive))
            self.assertTrue((d_root / 'audit' / 'index-security' / 'index-attributes-staged.json').is_file())
            self.assertTrue((d_root / 'audit' / 'manifest-security' / 'index-attributes-staged.json').is_file())
            events = [json.loads(line) for line in (d_root / 'audit' / 'events.jsonl').read_text('utf-8').splitlines()]
            prepared = next(e for e in events if e['phase'] == 'commit_prepared')
            self.assertEqual(Path(prepared['prepared_index']).parent, native_root)


if __name__ == '__main__':
    unittest.main()
