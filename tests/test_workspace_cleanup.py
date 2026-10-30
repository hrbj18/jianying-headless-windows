from pathlib import Path
import hashlib
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
import workspace_cleanup as cache


class RegenerableCacheCleanup(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.job = self.root / 'task'
        self.folder = self.job / 'preview' / 'Resources'
        self.folder.mkdir(parents=True)
        (self.folder / 'staged.wav').write_bytes(b'regenerable staged audio')
        self.original = self.root / 'original.wav'
        self.original.write_bytes(b'untouched user original')
        self.build = self.job / 'build'
        snapshot = self.build / 'draft'
        (snapshot / 'Resources').mkdir(parents=True)
        (snapshot / 'Resources' / 'source.wav').write_bytes(b'retained owned editable media')
        (snapshot / 'draft_content.json').write_bytes(b'retained editable timeline')
        cache.save(self.build / 'plan.json', {'source': str(self.original)})
        record = {'schema': 'jy14-headless-build/v1', 'files': cache.inventory(snapshot),
                  'plan_sha256': cache.digest(self.build / 'plan.json'),
                  'assets': [{'source': str(self.original), 'sha256': cache.digest(self.original),
                              'size': self.original.stat().st_size}]}
        cache.save(self.build / 'build.json', record)
        self.preview = self.folder.parent
        cache.save(self.preview / 'timeline.json', {'timeline': 'retained native playback input'})
        self.png = self.preview / 'frame-000.png'
        self.png.write_bytes(b'preserved preview frame')
        cache.save(self.preview / 'inputs.json', {'files': {
            'Resources/staged.wav': {'sha256': cache.digest(self.folder / 'staged.wav'),
                                     'size': (self.folder / 'staged.wav').stat().st_size}},
            'timeline_sha256': cache.digest(self.preview / 'timeline.json')})
        cache.save(self.preview / 'preview.json', {'schema': 'jy-windows-native-preview/v1',
            'status': 'native-frames-captured', 'source_unchanged': True,
            'source': {'build': str(self.build), 'build_sha256': cache.digest(self.build / 'build.json')},
            'frames': [{'png': str(self.png), 'png_sha256': cache.digest(self.png)}]})
        self.request = self.root / 'request.json'
        self.plan = self.root / 'plan.json'

    def prepare(self, **overrides):
        value = {'schema': 'jy-cache-cleanup-request/v1', 'allowed_roots': [str(self.job)],
                 'protected_files': [str(self.original)], 'regenerable_directories': [str(self.folder)],
                 'reason': 'completed preview dependencies', 'regenerable_from': ['retained build']}
        value.update(overrides)
        cache.save(self.request, value)
        return cache.prepare(self.request, self.plan)

    def test_referenced_input_prevents_preparation(self):
        with self.assertRaisesRegex(ValueError, 'still referenced'):
            self.prepare(protected_files=[str(self.folder / 'staged.wav')])

    def test_cannot_remove_authorized_root_itself_or_arbitrary_folder(self):
        with self.assertRaisesRegex(ValueError, 'strict child'):
            self.prepare(regenerable_directories=[str(self.job)])
        with self.assertRaisesRegex(ValueError, 'Only dependency'):
            self.prepare(regenerable_directories=[str(self.folder.parent)])

    def test_changed_cache_blocks_before_any_deletion(self):
        self.prepare()
        (self.folder / 'staged.wav').write_bytes(b'user changed the cache after review')
        with patch('windows_runtime._ensure_editor_closed'), self.assertRaisesRegex(ValueError, 'changed after'):
            cache.apply(self.plan, self.root / 'audit')
        self.assertTrue((self.folder / 'staged.wav').is_file())
        self.assertEqual(self.original.read_bytes(), b'untouched user original')
        self.assertTrue(self.png.is_file())
        self.assertTrue((self.build / 'draft/Resources/source.wav').is_file())

    def test_removes_only_verified_cache_and_preserves_user_source(self):
        self.prepare()
        with patch('windows_runtime._ensure_editor_closed'):
            result = cache.apply(self.plan, self.root / 'audit')
        self.assertEqual(result['files_removed'], 1)
        self.assertFalse(self.folder.exists())
        self.assertTrue(self.folder.parent.is_dir())
        self.assertEqual(self.original.read_bytes(), b'untouched user original')
        journal = (self.root / 'audit/deleted.jsonl').read_text(encoding='utf-8').splitlines()
        self.assertEqual(json.loads(journal[0])['sha256'], hashlib.sha256(b'regenerable staged audio').hexdigest())

    def test_delivery_file_inside_cache_is_rejected(self):
        (self.folder / 'render.mp4').write_bytes(b'keep this deliverable')
        with self.assertRaisesRegex(ValueError, 'Delivery, build'):
            self.prepare()

    def test_draft_resources_are_rejected_even_with_an_authorized_parent(self):
        with self.assertRaisesRegex(ValueError, 'Editable draft/Resources'):
            self.prepare(regenerable_directories=[str(self.build / 'draft/Resources')])
        self.assertTrue((self.build / 'draft/Resources/source.wav').is_file())

    def test_resources_name_without_completed_native_marker_is_insufficient(self):
        (self.preview / 'preview.json').unlink()
        with self.assertRaisesRegex(ValueError, 'completed native'):
            self.prepare()

    def test_failed_native_marker_cannot_authorize_cleanup(self):
        marker = cache.read(self.preview / 'preview.json')
        marker['status'] = 'failed'
        cache.save(self.preview / 'preview.json', marker)
        with self.assertRaisesRegex(ValueError, 'successful native preview'):
            self.prepare()

    def test_changed_retained_build_manifest_rejects_preparation(self):
        (self.build / 'draft/Resources/source.wav').write_bytes(b'a changed editable input')
        with self.assertRaisesRegex(ValueError, 'full manifest'):
            self.prepare()

    def test_build_record_hash_must_match_actual_native_evidence(self):
        record = cache.read(self.build / 'build.json')
        record['changed'] = True
        cache.save(self.build / 'build.json', record)
        with self.assertRaisesRegex(ValueError, 'SHA-256 differs'):
            self.prepare()

    def test_same_size_changed_original_blocks_before_cache_deletion(self):
        self.prepare()
        self.original.write_bytes(b'Z' * self.original.stat().st_size)
        with patch('windows_runtime._ensure_editor_closed'), self.assertRaisesRegex(ValueError, 'SHA-256 differs'):
            cache.apply(self.plan, self.root / 'audit')
        self.assertTrue((self.folder / 'staged.wav').exists())
        self.assertTrue((self.root / 'audit/failure.json').is_file())

    def test_same_audit_resumes_after_delete_before_commit_record(self):
        self.prepare()
        unlink = cache.unlink_owned_file

        def interrupted(*args, **kwargs):
            unlink(*args, **kwargs)
            raise RuntimeError('interrupted after unlink')

        with patch('windows_runtime._ensure_editor_closed'), \
                patch.object(cache, 'unlink_owned_file', side_effect=interrupted), self.assertRaises(RuntimeError):
            cache.apply(self.plan, self.root / 'audit')
        self.assertFalse((self.folder / 'staged.wav').exists())
        self.assertTrue((self.root / 'audit/failure.json').exists())
        with patch('windows_runtime._ensure_editor_closed'):
            result = cache.apply(self.plan, self.root / 'audit')
        self.assertEqual(result['files_removed'], 1)
        self.assertFalse(result['allocation_statistics_complete'])
        self.assertFalse(self.folder.exists())
        self.assertEqual(self.original.read_bytes(), b'untouched user original')

    def test_recreated_cache_is_not_blindly_deleted_on_resume(self):
        self.prepare()
        with patch('windows_runtime._ensure_editor_closed'):
            cache.apply(self.plan, self.root / 'audit')
        self.folder.mkdir()
        path = self.folder / 'staged.wav'
        path.write_bytes(b'regenerable staged audio')
        with patch('windows_runtime._ensure_editor_closed'), self.assertRaisesRegex(ValueError, 'was recreated'):
            cache.apply(self.plan, self.root / 'audit')
        self.assertTrue(path.exists())

    def test_unexplained_missing_cache_requires_manual_inspection(self):
        self.prepare()
        (self.folder / 'staged.wav').unlink()
        with patch('windows_runtime._ensure_editor_closed'), self.assertRaisesRegex(ValueError, 'without a cleanup intent'):
            cache.apply(self.plan, self.root / 'audit')

    def test_symlink_parent_is_rejected_before_traversal(self):
        alias = self.job / 'alias'
        try:
            alias.symlink_to(self.preview, target_is_directory=True)
        except OSError as error:
            self.skipTest('Symlink unavailable: ' + str(error))
        try:
            with self.assertRaisesRegex(ValueError, 'Symlink/reparse'):
                self.prepare(regenerable_directories=[str(alias / 'Resources')])
        finally:
            alias.unlink()

    def test_native_probes_directory_is_not_an_allowed_cache_kind(self):
        path = self.job / 'native-probes'
        path.mkdir()
        with self.assertRaisesRegex(ValueError, 'Only dependency/compiler'):
            self.prepare(regenerable_directories=[str(path)])

    def test_completed_export_compiler_cache_is_bound_and_preserves_render(self):
        (self.preview / 'preview.json').unlink()
        compiler = self.preview / 'compiler-tmp'
        cwd = compiler / 'compile-once'
        cwd.mkdir(parents=True)
        (cwd / 'native-export-helper.obj').write_bytes(b'regenerable object bytes')
        render = self.preview / 'render.mp4'
        render.write_bytes(b'preserved final export')
        cache.save(self.preview / 'result.json', {'schema': 'jy14-native-export/v1',
            'status': 'encoded-and-decoded', 'source_build_unchanged': True,
            'build': str(self.build), 'build_sha256': cache.digest(self.build / 'build.json'),
            'output': str(render), 'output_sha256': cache.digest(render), 'output_bytes': render.stat().st_size,
            'windows_toolchain': {'compiler_cwd': str(cwd)}})
        self.prepare(regenerable_directories=[str(compiler)])
        with patch('windows_runtime._ensure_editor_closed'):
            result = cache.apply(self.plan, self.root / 'audit')
        self.assertEqual(result['files_removed'], 1)
        self.assertFalse(compiler.exists())
        self.assertEqual(render.read_bytes(), b'preserved final export')

    def test_plan_output_cannot_overwrite_a_protected_source(self):
        value = {'schema': 'jy-cache-cleanup-request/v1', 'allowed_roots': [str(self.job)],
                 'protected_files': [str(self.original)], 'regenerable_directories': [str(self.folder)],
                 'reason': 'test'}
        cache.save(self.request, value)
        with self.assertRaisesRegex(ValueError, 'must be a new file'):
            cache.prepare(self.request, self.original)
        self.assertEqual(self.original.read_bytes(), b'untouched user original')

    def test_omitted_dependency_in_a_modified_plan_is_rejected_before_deletion(self):
        self.prepare()
        value = cache.read(self.plan)
        del value['retained_files'][str(self.build / 'draft/Resources/source.wav')]
        cache.save(self.plan, value)
        with patch('windows_runtime._ensure_editor_closed'), self.assertRaisesRegex(ValueError, 'omitted a retained'):
            cache.apply(self.plan, self.root / 'audit')
        self.assertTrue((self.folder / 'staged.wav').exists())


if __name__ == '__main__':
    unittest.main()
