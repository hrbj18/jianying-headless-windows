"""Windows 运行时适配：真机事务、加解密回环与平台门禁。

仅在 Windows 上运行，且不会触碰真实的剪映草稿目录。
"""
from copy import deepcopy
from contextlib import ExitStack
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
class ReviewedInstallations(unittest.TestCase):
    """Identity and discovery checks use synthetic files, never an editor DLL."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='identity-', dir=WORK)
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)

    def installation(self, build, base=None):
        folder = (base or self.folder) / build
        folder.mkdir(parents=True)
        (folder / 'videoeditor.dll').write_bytes(b'not a real DLL')
        (folder / 'JianyingPro.exe').write_bytes(b'not a real executable')
        return folder

    def discover(self, folder, version, fingerprint):
        with patch.object(runtime, '_install_candidates', return_value=iter([folder])), \
                patch.object(runtime, '_executable_version', return_value=version), \
                patch.object(runtime, 'digest', return_value=fingerprint):
            return runtime.discover_installation()

    def test_both_exact_reviewed_identities_are_accepted(self):
        self.assertEqual(runtime.WINDOWS_PROFILES, {
            '11.4.7.14462': 'fa89997a94e96cf97c8ee436a56ab028ea5f87731214696ba43ff74c0fdc0fa0',
            '11.5.0.14471': '37cadef37daff82e2ecdcd65080b9cbd7f6f9436f5e56c1ffb90c52c408eb7fb'})
        for build, fingerprint in runtime.WINDOWS_PROFILES.items():
            with self.subTest(build=build):
                folder = self.installation(build)
                self.assertEqual(self.discover(folder, build, fingerprint),
                                 (folder.resolve(), build, fingerprint))

    def test_unknown_build_hash_and_mislabeled_executable_are_rejected(self):
        known = '11.4.7.14462'
        fingerprint = runtime.WINDOWS_PROFILES[known]
        known_folder = self.installation(known)
        unknown_folder = self.installation('11.4.7.14463')
        cases = [(unknown_folder, '11.4.7.14463', fingerprint),
                 (known_folder, known, '0' * 64),
                 (known_folder, '11.5.0.14471', fingerprint)]
        for folder, version, value in cases:
            with self.subTest(folder=folder.name, version=version, fingerprint=value):
                with self.assertRaises(ValueError):
                    self.discover(folder, version, value)

    def test_missing_pe_version_is_rejected_without_hashing_or_loading_dll(self):
        folder = self.installation('11.4.7.14462')
        with patch.object(runtime, '_install_candidates', return_value=iter([folder])), \
                patch.object(runtime, '_executable_version', side_effect=ValueError('no version')), \
                patch.object(runtime, 'digest') as fingerprint:
            with self.assertRaises(ValueError):
                runtime.discover_installation()
            fingerprint.assert_not_called()

    def test_explicit_environment_installation_has_priority(self):
        explicit = self.folder / 'explicit'
        with patch.dict(os.environ, {'JIANYING_INSTALL_DIR': str(explicit)}), \
                patch.object(runtime, 'load_config') as config:
            self.assertEqual(list(runtime._install_candidates()), [explicit])
            config.assert_not_called()

    def test_local_configuration_precedes_default_installation(self):
        configured = self.folder / 'configured'
        appdata = self.folder / 'AppData'
        default = self.installation('11.5.0.14471', appdata / 'JianyingPro/Apps')
        with patch.dict(os.environ, {'JIANYING_INSTALL_DIR': '', 'LOCALAPPDATA': str(appdata)}), \
                patch.object(runtime, 'load_config', return_value={'jianying_install_dir': str(configured)}):
            self.assertEqual(list(runtime._install_candidates()), [configured, default])

    def test_doctor_reports_the_selected_build_version(self):
        draft_root = self.folder / 'drafts'
        draft_root.mkdir()
        (draft_root / 'root_meta_info.json').write_bytes(b'{}')
        for build, fingerprint in runtime.WINDOWS_PROFILES.items():
            with self.subTest(build=build), ExitStack() as contexts:
                contexts.enter_context(patch.object(runtime, 'DRAFT_ROOT', draft_root))
                contexts.enter_context(patch.object(runtime, 'discover_installation',
                                                    return_value=(self.folder, build, fingerprint)))
                contexts.enter_context(patch.object(runtime.shutil, 'which', return_value='tool.exe'))
                configure = contexts.enter_context(patch.object(runtime, 'configure_environment'))
                info = runtime.doctor()
                self.assertEqual(info['app_version'], '.'.join(build.split('.')[:3]))
                self.assertEqual(info['app_build'], build)
                self.assertEqual(info['runtime_profile'], runtime.PROFILE_PREFIX + build)
                configure.assert_called_once_with()

    def test_version_reader_reads_python_pe_without_executing_it(self):
        version = runtime._executable_version(Path(sys.executable))
        self.assertRegex(version, r'^\d+\.\d+\.\d+\.\d+$')
        self.assertEqual(version.split('.')[:2], [str(sys.version_info.major), str(sys.version_info.minor)])

    def test_version_reader_rejects_a_file_without_version_resources(self):
        path = self.folder / 'fixture.exe'
        path.write_bytes(b'not a PE file')
        with self.assertRaises(ValueError):
            runtime._executable_version(path)

    def test_signature_and_publisher_validation_remain_required(self):
        before = {'install_dir': str(self.folder)}
        for output in ('NotSigned|', 'Valid|CN=Unrelated publisher'):
            with self.subTest(output=output), \
                    patch.object(runtime, 'doctor', return_value=before), \
                    patch.object(runtime.subprocess, 'run',
                                 return_value=type('Result', (), {'returncode': 0, 'stdout': output})()):
                with self.assertRaisesRegex(ValueError, 'Authenticode'):
                    runtime.validate_runtime()


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

    def test_failed_incoming_copy_is_outside_editor_scan_root(self):
        def fail_copy(source, destination, record):
            Path(destination).mkdir()
            (Path(destination) / 'partial').write_bytes(b'partial copy')
            raise OSError('injected incomplete dependency copy')

        with patch.object(j, 'copy_draft_dependencies', side_effect=fail_copy):
            with self.assertRaisesRegex(ValueError, 'incomplete dependency'):
                self.publish('failed-copy')
        failure = json.loads((self.folder / 'failed-copy/failure.json').read_bytes())
        retained = Path(failure['staged_draft']).resolve()
        self.assertNotIn(self.root.resolve(), retained.parents)
        self.assertTrue((retained / 'partial').is_file())
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
