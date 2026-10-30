"""Saved fog revisions must remain exact while only the preview copy upgrades."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
import windows_native_preview as preview
import windows_vfx as vfx


class FogPreviewResources(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='jy-fog-preview-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.old, self.current = self.root / 'old', self.root / 'current'
        for folder, data in ((self.old, b'reviewed v2'), (self.current, b'reviewed v3')):
            folder.mkdir(); (folder / 'config.json').write_bytes(data)
        old_files, current_files = vfx.tree_manifest(self.old), vfx.tree_manifest(self.current)
        self.entry = {'key': 'transition/fog-compat', 'bucket': 'transitions',
                      'material_template': {'is_overlap': True, 'resource_id': '', 'type': 'transition'},
                      'duration_ms_values': [400, 600, 800, 1200],
                      'files': current_files, 'tree_sha256': vfx.manifest_hash(current_files),
                      'paused_player_supported': True, 'resource_revision': 3,
                      'legacy_resources': [{'files': old_files, 'tree_sha256': vfx.manifest_hash(old_files),
                                            'legacy_resource': True, 'resource_revision': 2,
                                            'paused_player_supported': False}]}
        self.enterContext(patch.object(vfx, 'catalog', return_value={'resources': {self.entry['key']: self.entry}}))
        self.enterContext(patch.object(vfx, 'load_config', return_value={
            'windows_vfx_resources': {self.entry['key']: str(self.current)}}))
        self.node = {**self.entry['material_template'], 'id': 'fog1', 'duration': 600000, 'path': str(self.old)}
        self.timeline = {'materials': {'transitions': [self.node]}}
        self.job = self.root / 'work' / 'preview'; self.job.mkdir(parents=True)

    def test_full_identity_selects_legacy_but_new_actions_resolve_current(self):
        self.assertTrue(vfx.entry_for_node('transitions', self.node)['legacy_resource'])
        self.assertEqual(vfx.resource_path(self.entry['key']), self.current)
        current = {**self.node, 'path': str(self.current)}
        self.assertEqual(vfx.entry_for_node('transitions', current)['resource_revision'], 3)
        with self.assertRaises(ValueError):
            vfx.entry_for_node('transitions', self.node, verify_files=False)

    def test_old_draft_is_unchanged_and_snapshot_contains_exact_current_bytes(self):
        before = deepcopy(self.timeline)
        source_files = vfx.tree_manifest(self.old)
        result, files, audit = preview.upgrade_preview_resources(self.timeline, {}, self.job)
        destination = Path(result['materials']['transitions'][0]['path'])
        self.assertTrue(destination.is_relative_to(self.job))
        self.assertEqual(vfx.tree_manifest(destination), self.entry['files'])
        self.assertEqual(self.timeline, before)
        self.assertEqual(vfx.tree_manifest(self.old), source_files)
        self.assertEqual(audit[0]['source_tree_sha256'], self.entry['legacy_resources'][0]['tree_sha256'])
        self.assertEqual(audit[0]['replacement_tree_sha256'], self.entry['tree_sha256'])
        self.assertIn(str(destination.relative_to(self.job) / 'config.json'), files)

    def test_changed_old_or_replacement_bytes_are_rejected(self):
        (self.old / 'unexpected.txt').write_bytes(b'not reviewed')
        with self.assertRaisesRegex(ValueError, 'resource identity'):
            preview.upgrade_preview_resources(self.timeline, {}, self.job)
        (self.old / 'unexpected.txt').unlink()
        (self.current / 'config.json').write_bytes(b'changed replacement')
        with self.assertRaisesRegex(ValueError, 'bytes changed'):
            preview.upgrade_preview_resources(self.timeline, {}, self.job)

    def test_wrong_material_contract_never_selects_legacy(self):
        for key, value in (('duration', 500000), ('type', 'unknown'), ('resource_id', 'online-id')):
            with self.subTest(key=key), self.assertRaises(ValueError):
                preview.upgrade_preview_resources({'materials': {'transitions': [{**self.node, key: value}]}}, {}, self.job)

    def test_current_resource_does_not_get_rewritten(self):
        value = deepcopy(self.timeline); value['materials']['transitions'][0]['path'] = str(self.current)
        result, files, audit = preview.upgrade_preview_resources(value, {'existing': {}}, self.job)
        self.assertEqual(result, value); self.assertEqual(files, {'existing': {}}); self.assertEqual(audit, [])
        self.assertEqual(list(self.job.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
