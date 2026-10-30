"""Resource and timing regressions at the normal Windows VFX boundary.

These use complete, temporary frozen-byte manifests and the real admission
functions. They never require a local editor, D: drive, or native execution.
"""
from copy import deepcopy
from pathlib import Path
import sys
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
import windows_vfx as vfx
import windows_mask_controls as controls
from tests import test_windows_vfx as fixtures


class MaskAdmissionContracts(unittest.TestCase):
    def setUp(self):
        fixtures.NativeCircleContracts.setUp(self)
        legacy = Path(self.bindings['mask/circle'])
        for index in range(22):
            (legacy / ('asset-%02d.bin' % index)).write_bytes(b'legacy:' + str(index).encode())
        old = self.entries['mask/circle']
        old['files'] = vfx.tree_manifest(legacy)
        old['tree_sha256'] = vfx.manifest_hash(old['files'])
        self.assertEqual(len(old['files']), 23)

        modern = self.folder / 'circle-soft'
        modern.mkdir()
        (modern / 'config.json').write_bytes(b'modern-opaque-mask-protocol')
        for index in range(26):
            (modern / ('asset-%02d.bin' % index)).write_bytes(b'modern:' + str(index).encode())
        soft = deepcopy(old)
        soft.update(key='mask/circle-soft', files=vfx.tree_manifest(modern))
        soft['material_template']['name'] = 'REA-circle-soft'
        soft['tree_sha256'] = vfx.manifest_hash(soft['files'])
        self.assertEqual(len(soft['files']), 27)
        self.entries['mask/circle-soft'] = soft
        self.bindings['mask/circle-soft'] = str(modern)

        self.timeline['duration'] = 4_000_000
        segment = self.timeline['tracks'][0]['segments'][0]
        segment.update(source_timerange={'start': 0, 'duration': 4_000_000},
                       target_timerange={'start': 0, 'duration': 4_000_000})
        self.timeline['materials']['common_mask'] = [{
            **deepcopy(soft['material_template']), 'id': 'mask1', 'path': str(modern)}]
        segment['extra_material_refs'] = ['mask1']
        self.keyframe_action = {
            'op': 'video.mask.keyframe', 'segment_id': 'segment1',
            'preset': 'mask/circle-soft', 'property': 'feather',
            'points': [{'time_ms': 0, 'value': 0}, {'time_ms': 2000, 'value': .5}]}
        segment['common_keyframes'] = [{
            'id': 'channel1', 'material_id': 'mask1', 'property_type': 'KFTypeCommonMaskFeather',
            'keyframe_list': [{'id': 'point1', 'values': [0]},
                              {'id': 'point2', 'time_offset': 2_000_000, 'values': [.5]}]}]

    def test_modern_feather_compiles_verifies_and_passes_the_export_resource_gate(self):
        argv = vfx.compile_action(self.keyframe_action, self.timeline, 'local://sample')
        self.assertEqual(argv[argv.index('--material-id') + 1], 'mask1')
        self.assertTrue(vfx.verify_action(self.keyframe_action, self.timeline)['mask_itself_animated'])
        self.assertEqual(vfx.validate_timeline(self.timeline, self.runtime)['resource_keys'], ['mask/circle-soft'])

    def test_saved_readback_cannot_misidentify_exact_legacy_bytes_as_modern_feather(self):
        self.timeline['materials']['common_mask'][0] = {
            **deepcopy(self.entries['mask/circle']['material_template']),
            'id': 'mask1', 'path': self.bindings['mask/circle']}
        for operation in (
                lambda: vfx.compile_action(self.keyframe_action, self.timeline, 'local://sample'),
                lambda: vfx.verify_action(self.keyframe_action, self.timeline),
                lambda: vfx.validate_timeline(self.timeline, self.runtime)):
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                operation()

    def test_modern_name_with_exact_legacy_package_does_not_pass_normal_readback(self):
        # This transitional pair is allowed only during audited mask.add repair.
        self.timeline['materials']['common_mask'][0]['path'] = self.bindings['mask/circle']
        with self.assertRaises(ValueError):
            vfx.verify_action(self.keyframe_action, self.timeline)
        with self.assertRaises(ValueError):
            vfx.validate_timeline(self.timeline, self.runtime)

    def test_unknown_or_modified_resource_bytes_cannot_pass_keyframe_readback(self):
        folder = Path(self.bindings['mask/circle-soft'])
        (folder / 'config.json').write_bytes(b'unreviewed')
        with self.assertRaises(ValueError):
            vfx.verify_action(self.keyframe_action, self.timeline)
        with self.assertRaises(ValueError):
            vfx.compile_action(self.keyframe_action, self.timeline, 'local://sample')

    def test_bound_speed_material_cannot_bypass_mask_animation_time_contract(self):
        segment = self.timeline['tracks'][0]['segments'][0]
        segment['extra_material_refs'].append('speed1')
        segment['speed'] = 1
        for node in ({'id': 'speed1', 'type': 'speed', 'speed': 2},
                     {'id': 'speed1', 'type': 'speed', 'speed': True},
                     {'id': 'speed1', 'type': 'speed', 'speed': '1'},
                     {'id': 'speed1', 'type': 'speed', 'speed': 1,
                      'curve_speed': {'points': [0, 1]}}):
            self.timeline['materials']['speeds'] = [node]
            for operation in (
                    lambda: vfx.compile_action(self.keyframe_action, self.timeline, 'local://sample'),
                    lambda: vfx.verify_action(self.keyframe_action, self.timeline),
                    lambda: vfx.validate_timeline(self.timeline, self.runtime)):
                with self.subTest(node=node, operation=operation), self.assertRaises(ValueError):
                    operation()
        self.timeline['materials']['speeds'] = [{'id': 'speed1', 'type': 'speed'}]
        self.assertEqual(vfx.validate_timeline(self.timeline, self.runtime)['masks'], 1)

    def test_unbound_legacy_and_unknown_mask_channels_do_not_bypass_export_gate(self):
        for kind in ('KFTypeMaskFeather', 'KFTypeMaskSize', 'KFTypeMaskPostionX',
                     'KFTypeMaskUnknown', 'KFTypeCommonMaskUnknown'):
            value = deepcopy(self.timeline)
            group = value['tracks'][0]['segments'][0]['common_keyframes'][0]
            group.update(property_type=kind, material_id='')
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                vfx.validate_timeline(value, self.runtime)

    def test_static_updates_cannot_claim_to_change_a_keyframed_mask_property(self):
        update = {'op': 'video.mask.update', 'preset': 'mask/circle-soft',
                  'segment_id': 'segment1', 'config': {'feather': .5}}
        for operation in (
                lambda: vfx.compile_action(update, self.timeline, 'local://sample'),
                lambda: vfx.verify_action(update, self.timeline)):
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                operation()

        # A separate static axis remains independently editable.
        width = {**update, 'config': {'width': .65}}
        self.assertIn('--width', vfx.compile_action(width, self.timeline, 'local://sample'))
        self.assertEqual(vfx.verify_action(width, self.timeline)['config']['width'], .65)

        # With no animation channel the normalized static feather is meaningful.
        self.timeline['tracks'][0]['segments'][0].pop('common_keyframes')
        self.timeline['materials']['common_mask'][0]['config']['feather'] = .5
        self.assertIn('--feather', vfx.compile_action(update, self.timeline, 'local://sample'))
        self.assertEqual(vfx.verify_action(update, self.timeline)['config']['feather'], .5)

    def test_audited_set_transitions_only_exact_legacy_bytes_to_the_reviewed_modern_package(self):
        import native_export as native
        source = self.folder / 'draft'
        main = source / 'Timelines/timeline1/draft_content.json'
        main.parent.mkdir(parents=True)
        root = source / 'draft_content.json'
        audit = self.folder / 'audit'
        audit.mkdir()
        value = deepcopy(self.timeline)
        value['id'] = 'timeline1'
        value['tracks'][0]['segments'][0].pop('common_keyframes')
        node = value['materials']['common_mask'][0]
        node.update(path=self.bindings['mask/circle'], is_old_version=True)
        for path in (main, root):
            path.write_text(json.dumps(value), encoding='utf-8')
        (source / 'Timelines/project.json').write_text(
            json.dumps({'main_timeline_id': 'timeline1'}), encoding='utf-8')
        before_root = root.read_bytes()

        def decrypt(path):
            return json.loads(Path(path).read_bytes())

        def encrypt(payload, path):
            with Path(path).open('xb') as stream:
                stream.write(payload)

        def read(draft, runtime):
            return source, native.j.files_manifest(source), decrypt(main), {
                'source_timeline': str(main.relative_to(source))}

        request = {'op': 'video.mask.set', 'preset': 'mask/circle-soft', 'segment_id': 'segment1'}
        helper = SimpleNamespace(_encrypt_metadata_from_memory=encrypt,
                                 _decrypt_metadata_in_memory=decrypt)
        with patch.object(native, 'read_draft', side_effect=read), \
                patch.object(native.j.nd, 'helper', return_value=helper):
            result = controls.reconcile_after_cli(request, source, audit / 'exact', self.runtime)
        self.assertEqual(result['status'], 'patched-and-read-back')
        self.assertEqual(root.read_bytes(), before_root)
        after = decrypt(main)
        self.assertEqual(after['materials']['common_mask'][0]['path'], self.bindings['mask/circle-soft'])
        self.assertFalse(after['materials']['common_mask'][0]['is_old_version'])
        self.assertEqual(vfx.verify_action(request, after)['preset'], 'mask/circle-soft')

        # Reusing the same material shape cannot admit an altered 23-file package.
        main.write_text(json.dumps(value), encoding='utf-8')
        (Path(self.bindings['mask/circle']) / 'config.json').write_bytes(b'unknown-old-package')
        before_main = main.read_bytes()
        with patch.object(native, 'read_draft', side_effect=read), \
                patch.object(native.j.nd, 'helper', return_value=helper):
            with self.assertRaises(ValueError):
                controls.reconcile_after_cli(request, source, audit / 'tampered', self.runtime)
        self.assertEqual(main.read_bytes(), before_main)


if __name__ == '__main__':
    unittest.main()
