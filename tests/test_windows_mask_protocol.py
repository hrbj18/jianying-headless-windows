import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))
import native_export as native
import windows_mask_protocol as masks
from runtime_profiles import WINDOWS_1147_PROFILE


class MaskRuntimeTests(unittest.TestCase):
    def test_pinned_catalog_has_exact_runtime_and_both_resource_manifests(self):
        catalog = masks.runtime_manifest()
        self.assertEqual(len(catalog['builtin_files']), 48)
        self.assertEqual(len(catalog['mask_circle']['files']), 23)
        self.assertEqual(catalog['mask_circle']['resource_id'], '7356934080102928946')

    def test_other_build_is_rejected_before_resource_reads(self):
        with patch.object(masks.resources, 'tree_manifest') as tree:
            with self.assertRaisesRegex(ValueError, 'exact Windows'):
                masks.verify_builtin_runtime({'runtime_profile': WINDOWS_1147_PROFILE, 'app_build': '11.5.0.14471'})
            tree.assert_not_called()

    def test_unicode_install_and_changed_builtin_bytes(self):
        with tempfile.TemporaryDirectory(prefix='jy-mask-runtime-') as tmp:
            install = Path(tmp) / '正版剪映'
            root = install / 'Resources/lumi_js_resources_video'
            root.mkdir(parents=True)
            runtime = {'runtime_profile': WINDOWS_1147_PROFILE, 'app_build': '11.4.7.14462', 'install_dir': str(install)}
            expected = masks.runtime_manifest()['builtin_files']
            with patch.object(masks.resources, 'tree_manifest', return_value=expected):
                self.assertEqual(masks.verify_builtin_runtime(runtime), root.resolve())
            with patch.object(masks.resources, 'tree_manifest', return_value={}):
                with self.assertRaisesRegex(ValueError, 'bytes differ'):
                    masks.verify_builtin_runtime(runtime)


class MaskRepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='jy-mask-protocol-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.source = self.root / 'draft'
        self.main = self.source / 'Timelines/timeline-1/draft_content.json'
        self.main.parent.mkdir(parents=True)
        self.audit = self.root / 'audit'
        self.audit.mkdir()
        self.resource = self.root / 'circle-resource'
        self.resource.mkdir()
        self.catalog = masks.runtime_manifest()
        self.mask = {key: self.catalog['mask_circle'][key] for key in
                     ('resource_id', 'resource_type', 'type', 'category', 'category_id', 'name')}
        self.mask.update(id='mask-1', path=str(self.resource), config={'width': .65, 'height': .65},
                         is_old_version=True, retained_unknown_metadata={'owner': 'preserve'})
        self.timeline = {'id': 'timeline-1', 'materials': {'common_mask': [self.mask]},
                         'tracks': [{'type': 'video', 'segments': [{'id': 'segment-1', 'extra_material_refs': ['mask-1']}]}]}
        self.main.write_text(json.dumps(self.timeline), encoding='utf-8')
        self.mirror = self.source / 'draft_content.json'
        self.mirror.write_bytes(b'old-root-mirror-must-remain-byte-identical')
        self.action = {'op': 'video.mask.set', 'segment_id': 'segment-1', 'preset': 'mask/circle'}
        self.runtime = {'runtime_profile': WINDOWS_1147_PROFILE, 'app_build': '11.4.7.14462'}
        self.original_manifest = native.j.files_manifest
        self.patches = [
            patch.object(native, 'read_draft', side_effect=self.read_draft),
            patch.object(native.j.nd, 'helper', return_value=SimpleNamespace(
                _encrypt_metadata_from_memory=self.encrypt, _decrypt_metadata_in_memory=self.decrypt)),
            patch.object(masks.resources, 'tree_manifest', return_value=self.catalog['mask_circle']['files']),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def encrypt(self, payload, path):
        with Path(path).open('xb') as output:
            output.write(payload)

    def decrypt(self, path):
        return json.loads(Path(path).read_bytes())

    def read_draft(self, source, runtime):
        timeline = self.decrypt(self.main)
        return self.source, self.original_manifest(self.source), timeline, {
            'source_timeline': str(self.main.relative_to(self.source))}

    def test_only_declared_main_changes_and_other_metadata_and_root_mirror_survive(self):
        before_mirror = self.mirror.read_bytes()
        before_timeline = json.loads(self.main.read_bytes())
        report = masks.repair_after_action(self.action, self.source, self.audit / 'step-001', self.runtime)
        self.assertEqual(report['status'], 'repaired-and-read-back')
        self.assertFalse(self.decrypt(self.main)['materials']['common_mask'][0]['is_old_version'])
        before_timeline['materials']['common_mask'][0]['is_old_version'] = False
        self.assertEqual(self.decrypt(self.main), before_timeline)
        self.assertEqual(self.mirror.read_bytes(), before_mirror)
        self.assertTrue(Path(report['recovery_path']).is_file())
        self.assertEqual(Path(report['recovery_path']).read_bytes(), json.dumps(self.timeline).encode())
        self.assertTrue((self.audit / 'step-001.mask-protocol.json').is_file())

    def test_repeat_false_is_idempotent_without_ciphertext_replacement(self):
        self.timeline['materials']['common_mask'][0]['is_old_version'] = False
        self.main.write_text(json.dumps(self.timeline), encoding='utf-8')
        before = self.original_manifest(self.source)
        report = masks.repair_after_action(self.action, self.source, self.audit / 'step-002', self.runtime)
        self.assertEqual(report['status'], 'already-native-protocol')
        self.assertEqual(self.original_manifest(self.source), before)

    def test_concurrent_change_stops_before_replacing_main_and_retains_evidence(self):
        original = self.main.read_bytes()
        def changed_manifest(source):
            (self.source / 'external-edit.txt').write_text('concurrent', encoding='utf-8')
            return self.original_manifest(source)
        with patch.object(native.j, 'files_manifest', side_effect=changed_manifest):
            with self.assertRaisesRegex(ValueError, 'concurrently'):
                masks.repair_after_action(self.action, self.source, self.audit / 'step-003', self.runtime)
        self.assertEqual(self.main.read_bytes(), original)
        report = json.loads((self.audit / 'step-003.mask-protocol.json').read_text(encoding='utf-8'))
        self.assertEqual(report['status'], 'failed-or-unverified')
        self.assertTrue(Path(report['recovery_path']).is_file())
        self.assertTrue(Path(report['temporary_path']).is_file())

    def test_unknown_resource_or_geometry_is_rejected_before_writes(self):
        before = self.original_manifest(self.source)
        with patch.object(masks.resources, 'tree_manifest', return_value={}):
            with self.assertRaisesRegex(ValueError, 'resource bytes differ'):
                masks.repair_after_action(self.action, self.source, self.audit / 'bad-resource', self.runtime)
        self.assertEqual(self.original_manifest(self.source), before)
        self.timeline['materials']['common_mask'][0]['config']['feather'] = .1
        self.main.write_text(json.dumps(self.timeline), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'fixed reviewed geometry'):
            masks.repair_after_action(self.action, self.source, self.audit / 'bad-geometry', self.runtime)

    def test_unrelated_actions_do_not_touch_runtime_or_source(self):
        with patch.object(masks, 'runtime_manifest') as catalog:
            self.assertIsNone(masks.repair_after_action({'op': 'audio.fade'}, 'missing', 'missing', {}))
            catalog.assert_not_called()


if __name__ == '__main__':
    unittest.main()
