"""Unicode saved drafts reach native rendering only through verified ASCII VFX."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
import media_store
import native_export as export
import windows_native_preview as preview
import windows_vfx as vfx
from runtime_profiles import WINDOWS_1147_PROFILE


class SavedUnicodeResourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='jy-unicode-vfx-')
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / '四姐妹漫画互动版'
        self.package = self.source / 'Resources' / '漫画圆蒙版'
        self.package.mkdir(parents=True)
        self.config = self.package / 'config.json'
        self.config.write_bytes(b'known mask resource fixture')
        self.entry = deepcopy(vfx.catalog()['resources']['mask/circle-soft'])
        self.entry['files'] = {'config.json': {'sha256': export.j.nd.digest(self.config),
                                               'size': self.config.stat().st_size}}
        self.entry['tree_sha256'] = vfx.manifest_hash(self.entry['files'])
        self.catalog_patch = patch.object(vfx, 'catalog', return_value={'resources': {'mask/circle-soft': self.entry}})
        self.catalog_patch.start()
        self.pool_patch = patch.object(media_store, 'default_pool', return_value=self.root / 'media-pool')
        self.pool_patch.start()
        self.windows_patch = patch.object(export.j.nd, 'IS_WINDOWS', True)
        self.windows_patch.start()
        self.runtime_patch = patch('windows_mask_protocol.verify_builtin_runtime', return_value={})
        self.runtime_patch.start()
        self.runtime = {'runtime_profile': WINDOWS_1147_PROFILE, 'app_build': '11.4.7.14462',
                        'app_version': '11.4.7', 'install_dir': str(self.root / 'app')}
        self.video = self.source / 'Resources' / 'live.mp4'
        self.video.write_bytes(b'staged video bytes')
        self.timeline = {'id': 'main', 'new_version': '185.0.0', 'version': 360000,
            'duration': 1_000_000, 'fps': 30, 'canvas_config': {'width': 640, 'height': 360},
            'materials': {'videos': [{'id': 'video1', 'type': 'video', 'path': str(self.video)}],
                         'common_mask': [{**deepcopy(self.entry['material_template']),
                                          'id': 'mask1', 'path': str(self.package)}]},
            'tracks': [{'id': 'track1', 'type': 'video', 'segments': [
                {'id': 'segment1', 'material_id': 'video1', 'extra_material_refs': ['mask1'],
                 'target_timerange': {'start': 0, 'duration': 1_000_000},
                 'source_timerange': {'start': 0, 'duration': 1_000_000}}]}]}

    def tearDown(self):
        self.runtime_patch.stop()
        self.windows_patch.stop()
        self.pool_patch.stop()
        self.catalog_patch.stop()
        for directory, _, names in os.walk(self.root, topdown=False):
            for name in names:
                path = Path(directory) / name
                if path.exists():
                    media_store._unlink(path)
        self.temp.cleanup()

    def test_public_vfx_api_remains_ascii_only(self):
        with self.assertRaisesRegex(ValueError, 'absolute ASCII'):
            vfx.entry_for_node('common_mask', self.timeline['materials']['common_mask'][0])

    def test_capabilities_validate_actual_bytes_through_ascii_snapshot_only(self):
        original = deepcopy(self.timeline)
        before = export.j.files_manifest(self.source)
        with patch.object(vfx, 'entry_for_node', wraps=vfx.entry_for_node) as identify:
            result = export.windows_saved_draft_supported_features(self.timeline,
                {'runtime_profile': WINDOWS_1147_PROFILE}, self.source, self.runtime)
        self.assertEqual(result['windows_vfx']['resource_keys'], ['mask/circle-soft'])
        self.assertTrue(all(str(call.args[1]['path']).isascii() for call in identify.call_args_list))
        self.assertEqual(result['saved_vfx_source_checks'][0]['tree_sha256'], self.entry['tree_sha256'])
        self.assertEqual(self.timeline, original)
        self.assertEqual(export.j.files_manifest(self.source), before)

    def test_actual_stage_freezes_resource_to_ascii_and_retains_original_dependency(self):
        before = export.j.files_manifest(self.source)
        job = self.root / 'job'
        job.mkdir()
        dependencies = {}
        staged, files = export.stage_draft_timeline(self.timeline, self.source, job, self.runtime, dependencies)
        resource = Path(staged['materials']['common_mask'][0]['path'])
        self.assertTrue(str(resource).isascii())
        self.assertTrue(resource.is_relative_to(job))
        self.assertEqual(vfx.verify_resource(resource, self.entry), resource)
        self.assertIn(str(self.config), dependencies)
        self.assertEqual(dependencies[str(self.config)], self.entry['files']['config.json'])
        self.assertTrue((job / 'source-vfx-materialization.json').is_file())
        self.assertEqual(export.j.files_manifest(self.source), before)
        self.assertTrue(any('native-export-vfx' in name for name in files))

    def test_repeated_package_copies_once_and_still_validates_each_node(self):
        second=deepcopy(self.timeline['materials']['common_mask'][0]);second['id']='mask2'
        self.timeline['materials']['common_mask'].append(second)
        segment=deepcopy(self.timeline['tracks'][0]['segments'][0]);segment.update(id='segment2',extra_material_refs=['mask2'])
        segment['target_timerange']['start']=1000000
        self.timeline['tracks'][0]['segments'].append(segment);self.timeline['duration']=2000000
        with patch.object(export,'_snapshot_saved_vfx',wraps=export._snapshot_saved_vfx) as copy:
            result=export.windows_saved_draft_supported_features(self.timeline,{},self.source,self.runtime)
        self.assertEqual(copy.call_count,1)
        self.assertEqual(len(result['saved_vfx_source_checks']),2)
        self.timeline['materials']['common_mask'][1]['config']['width']=2
        with self.assertRaises(ValueError):
            export.windows_saved_draft_supported_features(self.timeline,{},self.source,self.runtime)

    def test_reused_snapshot_does_not_hide_source_change_before_validation_finishes(self):
        original=export._snapshot_saved_vfx
        def snapshot_then_change(*args):
            result=original(*args)
            self.config.write_bytes(b'Z'*self.config.stat().st_size)
            return result
        with patch.object(export,'_snapshot_saved_vfx',side_effect=snapshot_then_change):
            with self.assertRaisesRegex(ValueError,'source changed during'):
                export.windows_saved_draft_supported_features(self.timeline,{},self.source,self.runtime)

    def test_modified_resource_bytes_and_extra_files_remain_rejected(self):
        self.config.write_bytes(b'corrupted package')
        with self.assertRaisesRegex(ValueError, 'resource identity'):
            export.windows_saved_draft_supported_features(self.timeline, {}, self.source, self.runtime)
        self.config.write_bytes(b'known mask resource fixture')
        (self.package / 'unreviewed.lua').write_bytes(b'unreviewed code')
        with self.assertRaisesRegex(ValueError, 'resource identity'):
            export.windows_saved_draft_supported_features(self.timeline, {}, self.source, self.runtime)

    def test_traversal_is_rejected_before_path_resolution(self):
        node = self.timeline['materials']['common_mask'][0]
        node['path'] = str(self.package / '..' / self.package.name)
        with self.assertRaisesRegex(ValueError, 'resource traversal'):
            export.windows_saved_draft_supported_features(self.timeline, {}, self.source, self.runtime)

    def test_reparse_source_is_not_resolved_away_before_validation(self):
        alias = self.root / 'resource-alias'
        try:
            alias.symlink_to(self.package, target_is_directory=True)
        except OSError as error:
            self.skipTest('Symlink unavailable: ' + str(error))
        try:
            self.timeline['materials']['common_mask'][0]['path'] = str(alias)
            with self.assertRaisesRegex(ValueError, 'Symlink/reparse'):
                export.windows_saved_draft_supported_features(self.timeline, {}, self.source, self.runtime)
        finally:
            alias.unlink()

    def test_original_resource_change_is_still_caught_by_preview_final_boundary(self):
        # External package is outside the draft manifest; dependency checks must
        # still catch it after staging, even when the saved timeline is unchanged.
        external = self.root / '外部蒙版'
        self.package.rename(external)
        config = external / 'config.json'
        self.timeline['materials']['common_mask'][0]['path'] = str(external)
        (self.source / 'draft_content.json').write_text(json.dumps(self.timeline), encoding='utf-8')
        helper = SimpleNamespace(_decrypt_metadata_in_memory=export.j.read_json)
        with patch.object(export.j.nd, 'helper', return_value=helper):
            _, _, _, capabilities, stage, unchanged = preview.prepare_source(self.runtime, draft_dir=self.source)
        self.assertEqual(capabilities['windows_vfx']['masks'], 1)
        job = self.root / 'job'
        job.mkdir()
        staged, _ = stage(job)
        unchanged()
        config.write_bytes(b'Z' * config.stat().st_size)
        with self.assertRaisesRegex(ValueError, 'media/font changed'):
            unchanged()
        resource = Path(staged['materials']['common_mask'][0]['path'])
        self.assertEqual(hashlib.sha256((resource / 'config.json').read_bytes()).hexdigest(),
                         self.entry['files']['config.json']['sha256'])


if __name__ == '__main__':
    unittest.main()
