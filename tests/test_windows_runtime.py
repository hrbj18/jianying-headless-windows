"""Windows 运行时适配：真机事务、加解密回环与平台门禁。

仅在 Windows 上运行，且不会触碰真实的剪映草稿目录。
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / 'work/windows-runtime-tests'
WORK.mkdir(parents=True, exist_ok=True)

if os.name == 'nt':
    import sys
    sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'bridge')]
    import jy14_headless as j
    import windows_runtime as runtime

WINDOWS_ONLY = unittest.skipUnless(os.name == 'nt', 'Windows 专用适配测试')
RUNTIME_MISSING = '未安装已审核的 Windows 剪映运行时'


def runtime_available():
    if os.name != 'nt':
        return False
    try:
        runtime.doctor()
    except Exception:  # noqa: BLE001 - 任何缺失都视为不可运行
        return False
    return True


@WINDOWS_ONLY
class CryptoBridge(unittest.TestCase):
    def test_encrypt_decrypt_roundtrip_is_exact(self):
        if not runtime_available():
            self.skipTest(RUNTIME_MISSING)
        payload = json.dumps({'id': 'fixture', 'tracks': [], '中文': '值'}).encode('utf-8')
        cipher = runtime._crypto('encrypt', payload)
        self.assertNotEqual(cipher, payload)
        self.assertEqual(runtime._crypto('decrypt', cipher), payload)

    def test_strict_json_rejects_hostile_payloads(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'[]', b'{"x":1e999}'):
            with self.subTest(raw=raw), self.assertRaises(runtime.ApplyError):
                runtime._parse_strict_json(raw, 'fixture')
        self.assertEqual(runtime._parse_strict_json(b'{"x":2}', 'fixture'), {'x': 2})

    def test_dacl_roundtrip_preserves_security_descriptor(self):
        # 首页登记时源文件与临时文件位于同一目录，这里复现同样的关系。
        folder = Path(tempfile.mkdtemp(prefix='case-', dir=WORK))
        source, target = folder / 'root_meta_info.json', folder / '.root_meta_info.headless.tmp'
        source.write_bytes(b'{"x":1}')
        target.write_bytes(b'{"x":2}')
        attributes = runtime.read_xattrs(source)
        copied, changed = runtime.copy_xattrs(attributes, target, folder, source)
        self.assertEqual(attributes, copied)
        self.assertEqual(changed, [])
        with self.assertRaises(runtime.ApplyError):
            runtime.copy_xattrs(attributes, target, folder, None)

    def test_snapshot_detects_changed_bytes(self):
        path = Path(tempfile.mkdtemp(prefix='case-', dir=WORK)) / 'snapshot.json'
        path.write_bytes(b'{"x":1}')
        snapshot = runtime._snapshot_file(path, 'fixture')
        runtime._revalidate_snapshot(snapshot, 'unchanged')
        path.write_bytes(b'{"x":2}')
        with self.assertRaises(runtime.ApplyError):
            runtime._revalidate_snapshot(snapshot, 'changed')


@WINDOWS_ONLY
class PublishTransaction(unittest.TestCase):
    """真实 Win32 事务：目录锁、ACL 复制、排他放置与索引替换。"""

    def setUp(self):
        if not runtime_available():
            self.skipTest(RUNTIME_MISSING)
        self.folder = Path(tempfile.mkdtemp(prefix='case-', dir=WORK))
        self.root = self.folder / 'projects'
        self.root.mkdir()
        self.original = {'root_path': str(self.root), 'draft_ids': 7,
                         'all_draft_store': [{'draft_id': 'existing', 'draft_name': 'untouched',
                                              'draft_fold_path': str(self.root / 'existing')}]}
        (self.root / 'root_meta_info.json').write_bytes(runtime.packed(self.original))
        self.build = self.folder / 'build'
        (self.build / 'draft').mkdir(parents=True)
        runtime._encrypt_metadata_from_memory(
            runtime.packed({'draft_id': 'new-id', 'draft_name': 'new-draft',
                            'draft_fold_path': str(self.root / 'new-draft'),
                            'draft_timeline_materials_size_': 0}),
            self.build / 'draft/draft_meta_info.json')
        self.record = {'runtime_profile': runtime.doctor()['runtime_profile'],
                       'target': str(self.root / 'new-draft'), 'draft_id': 'new-id',
                       'files': j.files_manifest(self.build / 'draft')}
        for context in (patch.object(j.nd, 'DRAFT_ROOT', self.root),
                        patch.object(runtime, '_ensure_editor_closed', lambda _: {'confirmed_by_user': True})):
            context.start()
            self.addCleanup(context.stop)

    def publish(self, name, resume=False, live=None):
        return j.publish(self.build, self.folder / name, resume=resume,
                         verify_build_fn=lambda _: self.record,
                         verify_live_fn=live or (lambda _: {'status': 'verified'}))

    def test_commit_preserves_existing_entries_and_acls(self):
        before = runtime.read_xattrs(self.root / 'root_meta_info.json')
        result = self.publish('ok')
        self.assertEqual(result['status'], 'created')
        after = json.loads((self.root / 'root_meta_info.json').read_bytes())
        self.assertEqual(after['draft_ids'], 8)
        self.assertEqual(after['all_draft_store'][1:], self.original['all_draft_store'])
        self.assertEqual(after['all_draft_store'][0]['draft_id'], 'new-id')
        self.assertEqual(runtime.read_xattrs(self.root / 'root_meta_info.json'), before)
        self.assertTrue((self.root / '.jianying-headless.lock').is_file())
        manifest = j.files_manifest(self.root / 'new-draft')
        self.assertEqual(manifest, self.record['files'])

    def test_republish_is_idempotent_only_through_resume(self):
        self.publish('first')
        with self.assertRaisesRegex(ValueError, 'publish requires a new target'):
            self.publish('second')
        result = self.publish('resumed', resume=True)
        self.assertEqual(result['status'], 'already_registered')
        self.assertFalse(result['index_written'])
        after = json.loads((self.root / 'root_meta_info.json').read_bytes())
        self.assertEqual(after['draft_ids'], 8)
        self.assertEqual(after['all_draft_store'][1:], self.original['all_draft_store'])

    def test_dacl_failure_blocks_before_the_draft_is_placed(self):
        with patch.object(runtime, 'copy_xattrs', side_effect=runtime.ApplyError('DACL 无法保留')):
            with self.assertRaisesRegex(ValueError, 'DACL 无法保留'):
                self.publish('denied')
        self.assertFalse((self.root / 'new-draft').exists())
        self.assertEqual(json.loads((self.root / 'root_meta_info.json').read_bytes()), self.original)

    def test_interrupted_commit_is_recoverable_and_reported(self):
        with patch.object(j.os, 'replace', side_effect=OSError('injected commit failure')):
            with self.assertRaisesRegex(ValueError, 'injected'):
                self.publish('interrupted')
        failure = json.loads((self.folder / 'interrupted/failure.json').read_bytes())
        self.assertEqual(failure['phase'], 'draft_placed')
        self.assertFalse(failure['files_deleted'])
        self.assertEqual(json.loads((self.root / 'root_meta_info.json').read_bytes()), self.original)
        self.assertEqual(self.publish('recover', resume=True)['status'], 'created')
        self.assertEqual(json.loads((self.root / 'root_meta_info.json').read_bytes())['draft_ids'], 8)


@WINDOWS_ONLY
class PlatformGates(unittest.TestCase):
    def test_native_export_platform_gate_accepts_reviewed_windows_adapter(self):
        import native_export
        import runtime_profiles as profiles
        self.assertIsNone(native_export.require_supported_platform())
        self.assertIn(profiles.WINDOWS_PROFILE, profiles.EXPORT_PROFILES)
        profiles.validate_export_profiles(profiles.WINDOWS_PROFILE, profiles.WINDOWS_PROFILE)

    def test_timeline_filename_follows_the_platform(self):
        self.assertEqual(runtime.TIMELINE_FILE, 'draft_content.json')
        self.assertEqual(j.nd.TIMELINE_FILE, 'draft_content.json')

    def test_windows_timeline_schema_is_reviewed(self):
        import runtime_profiles as profiles
        old = {'new_version': '185.0.0', 'version': 360000}
        new = {'new_version': '187.0.0', 'version': 360000}
        profiles.validate_timeline_schema(old, profiles.WINDOWS_PROFILE)
        profiles.validate_timeline_schema(new, profiles.WINDOWS_PROFILE)
        with self.assertRaises(ValueError):
            profiles.validate_timeline_schema(new, profiles.PROFILE_PREFIX + '11.4.2')


if __name__ == '__main__':
    unittest.main()
