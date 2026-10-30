"""Mask controls and narrow saved-draft reconciliation; no native launches."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
import native_export as native
import windows_mask_controls as controls
import windows_vfx as vfx
from runtime_profiles import WINDOWS_1147_PROFILE


def mask(identity='mask-1', **config):
    return {'id': identity, 'resource_type': 'circle', 'resource_id': 'reviewed-circle',
            'path': 'frozen-circle', 'is_old_version': False, 'name': 'REA-circle',
            'config': {'width': .65, 'height': .65, **config}}


def timeline(bound=True):
    return {'id': 'timeline-1', 'duration': 4_000_000,
            'materials': {'videos': [{'id': 'video-1', 'type': 'video'}],
                          'common_mask': [mask()] if bound else [],
                          'texts': [{'id': 'text-1', 'content': 'retain-main-text'}]},
            'tracks': [{'type': 'video', 'segments': [{'id': 'segment-1', 'material_id': 'video-1',
                'extra_material_refs': ['mask-1'] if bound else [],
                'source_timerange': {'start': 0, 'duration': 4_000_000},
                'target_timerange': {'start': 0, 'duration': 4_000_000},
                'clip': {'transform': {'x': 0, 'y': 0}}}]}]}


def action(op='video.mask.update', **config):
    return {'op': op, 'segment_id': 'segment-1', 'preset': 'mask/circle',
            'config': config or {'feather': .1}}


def reviewed_entry(bucket, node, **_):
    if bucket != 'common_mask' or node.get('resource_id') != 'reviewed-circle' or node.get('is_old_version', False):
        raise ValueError('Unreviewed mask resource')
    soft = node.get('name') == 'REA-circle-soft'
    controls.validate_native_config(node['config'], allow_feather=soft)
    return {'key': 'mask/circle-soft' if soft else 'mask/circle'}


class GeometryContracts(unittest.TestCase):
    def setUp(self):
        self.entry_patch = patch.object(vfx, 'entry_for_node', side_effect=reviewed_entry)
        self.entry_patch.start(); self.addCleanup(self.entry_patch.stop)

    def test_normalized_boundaries_and_default_config(self):
        values = controls.public_config({'width': .05, 'height': 1, 'center_x': -1,
                                         'center_y': 1, 'feather': 1}, complete=True)
        self.assertEqual(controls.native_values(values),
                         {'width': .05, 'height': 1, 'centerX': -1, 'centerY': 1, 'feather': 1})
        self.assertEqual(controls.public_config({}, complete=True), controls.DEFAULTS)

    def test_invalid_numbers_unknown_fields_and_types_are_rejected(self):
        for field, value in [('width', .049), ('width', 1.01), ('height', 0),
                             ('center_x', -1.01), ('center_y', 1.01), ('feather', -.01),
                             ('feather', 1.01), ('width', True), ('feather', float('nan')),
                             ('height', float('inf')), ('width', '.5'), ('rotation', 1)]:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                controls.public_config({field: value})
        for value in [None, [], '']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                controls.public_config(value)

    def test_native_unknown_protocol_fields_and_missing_dimensions_fail(self):
        for extra in [{'rotation': 1}, {'roundCorner': .1}, {'aspectRatio': 2}, {'expansion': .1},
                      {'invert': True}, {'invert': 0}, {'other': 0}, {'width': True}, {'centerX': float('nan')}]:
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                controls.validate_native_config({'width': .65, 'height': .65, **extra})
        with self.assertRaises(ValueError):
            controls.validate_native_config({'height': .65})

    def test_nonzero_feather_requires_the_reviewed_soft_preset(self):
        with self.assertRaisesRegex(ValueError, 'mask/circle-soft'):
            controls.compile_geometry(action(feather=.1), timeline(), 'local://test')
        with self.assertRaisesRegex(ValueError, 'mask/circle-soft'):
            controls.validate_native_config({'width': .5, 'height': .5, 'feather': .1})
        self.assertEqual(controls.validate_native_config(
            {'width': .5, 'height': .5, 'feather': 1}, allow_feather=True)['feather'], 1)
        soft = {**action('video.mask.set', feather=.1), 'preset': 'mask/circle-soft'}
        argv = controls.compile_geometry(soft, timeline(False), 'local://test')
        self.assertEqual(argv[argv.index('--name') + 1], 'REA-circle-soft')
        self.assertEqual(argv[argv.index('--feather') + 1], '0.1')

    def test_cli_add_complete_defaults_and_update_only_explicit_values(self):
        add = {'op': 'video.mask.set', 'segment_id': 'segment-1', 'preset': 'mask/circle'}
        argv = controls.compile_geometry(add, timeline(False), 'local://test-draft')
        self.assertEqual(argv[:4], ['draft', 'video', 'mask', 'add'])
        self.assertEqual(argv[argv.index('--width') + 1], '0.65')
        self.assertEqual(argv[argv.index('--center-x') + 1], '0')
        update = controls.compile_geometry(action(width=.4), timeline(), 'local://test-draft')
        self.assertEqual(update[:4], ['draft', 'video', 'mask', 'update'])
        self.assertEqual(update[update.index('--mask-id') + 1], 'mask-1')
        self.assertNotIn('--height', update)
        self.assertNotIn('--feather', update)

    def test_invalid_ref_selector_existing_add_and_empty_update_fail(self):
        for ref in ['local://中文', 'local://../draft', 'local://two,drafts', 'remote://draft']:
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                controls.compile_geometry(action(width=.4), timeline(), ref)
        for changed in [{'segment_id': '*'}, {'segment_id': 'segment-1,other'}, {'extra': 1}]:
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                controls.compile_geometry({**action(width=.4), **changed}, timeline(), 'local://test')
        with self.assertRaises(ValueError):
            controls.compile_geometry(action('video.mask.set', width=.4), timeline(), 'local://test')
        with self.assertRaises(ValueError):
            controls.compile_geometry({**action(), 'config': {}}, timeline(), 'local://test')

    def test_verified_readback_rejects_requested_value_mismatch(self):
        value = timeline(); value['materials']['common_mask'][0]['config']['centerY'] = .25
        result = controls.verify_geometry(action(center_y=.25), value)
        self.assertEqual(result['material_id'], 'mask-1')
        with self.assertRaisesRegex(ValueError, 'round-trip'):
            controls.verify_geometry(action(center_y=.5), value)


class NarrowReconciliation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='jy-mask-controls-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.source = self.root / 'draft'
        self.main = self.source / 'Timelines/timeline-1/draft_content.json'
        self.main.parent.mkdir(parents=True)
        self.mirror = self.source / 'draft_content.json'
        self.audit = self.root / 'audit'; self.audit.mkdir()
        self.current = timeline(); self.write(self.main, self.current); self.write(self.mirror, self.current)
        self.runtime = {'runtime_profile': WINDOWS_1147_PROFILE, 'app_build': '11.4.7.14462'}
        self.manifest = native.j.files_manifest
        for item in [patch.object(native, 'read_draft', side_effect=self.read),
                     patch.object(native.j.nd, 'helper', return_value=SimpleNamespace(
                         _encrypt_metadata_from_memory=self.encrypt, _decrypt_metadata_in_memory=self.decrypt)),
                     patch.object(vfx, 'entry_for_node', side_effect=reviewed_entry)]:
            item.start(); self.addCleanup(item.stop)

    @staticmethod
    def write(path, value):
        path.write_text(json.dumps(value), encoding='utf-8')

    @staticmethod
    def decrypt(path):
        return json.loads(Path(path).read_bytes())

    @staticmethod
    def encrypt(payload, path):
        with Path(path).open('xb') as stream:
            stream.write(payload)

    def read(self, source, runtime):
        return self.source, self.manifest(self.source), self.decrypt(self.main), {
            'source_timeline': str(self.main.relative_to(self.source))}

    def run_reconcile(self, request, name='step'):
        return controls.reconcile_after_cli(request, self.source, self.audit / name, self.runtime)

    def test_legacy_update_imports_only_requested_config_and_preserves_other_main_data(self):
        root = timeline(); root['materials']['common_mask'][0]['config'].update(width=.2, height=.3)
        root['materials']['texts'][0]['content'] = 'stale-root-text'
        root['tracks'][0]['segments'][0]['clip']['transform']['x'] = .9
        self.write(self.mirror, root); before_mirror = self.mirror.read_bytes()
        result = self.run_reconcile(action(height=.3))
        expected = timeline(); expected['materials']['common_mask'][0]['config']['height'] = .3
        self.assertEqual(self.decrypt(self.main), expected)
        self.assertEqual(self.mirror.read_bytes(), before_mirror)
        self.assertEqual(result['patch']['observed_from'], 'validated-root-candidate')
        self.assertTrue(result['source_other_files_unchanged'])
        self.assertTrue(Path(result['recovery_path']).is_file())

    def test_legacy_add_imports_one_mask_binding_and_preserves_unrelated_timeline(self):
        self.write(self.main, timeline(False))
        root = timeline(); root['materials']['common_mask'][0]['is_old_version'] = True
        root['materials']['texts'][0]['content'] = 'unrelated-root-change'; self.write(self.mirror, root)
        result = self.run_reconcile(action('video.mask.set', width=.65, height=.65))
        expected = timeline()
        expected['materials']['common_mask'][0]['config'].update(centerX=0, centerY=0, feather=0)
        self.assertEqual(self.decrypt(self.main), expected)
        self.assertEqual(result['patch']['mask_id'], 'mask-1')

    def test_normal_declared_main_uses_official_saved_values_without_root_changes(self):
        self.write(self.source / 'Timelines/project.json', {'main_timeline_id': 'timeline-1'})
        self.current['materials']['common_mask'][0]['config']['centerX'] = .1
        self.current['materials']['common_mask'][0]['is_old_version'] = True
        self.write(self.main, self.current); root_bytes = self.mirror.read_bytes()
        result = self.run_reconcile(action(center_x=.1))
        self.assertEqual(result['patch']['observed_from'], 'selected-main')
        self.assertFalse(self.decrypt(self.main)['materials']['common_mask'][0]['is_old_version'])
        self.assertEqual(self.mirror.read_bytes(), root_bytes)

    def soft_patches(self, original_path, frozen_path):
        entries = {}
        for key, name in [('mask/circle', 'REA-circle'), ('mask/circle-soft', 'REA-circle-soft')]:
            template = {k: v for k, v in mask().items() if k not in {'id', 'path'}}
            template['name'] = name
            entries[key] = {'key': key, 'bucket': 'common_mask', 'material_template': template}
        def verify(path, entry):
            wanted = frozen_path if entry['key'] == 'mask/circle-soft' else original_path
            if str(path) != str(wanted):
                raise ValueError('Resource byte manifest mismatch')
            return Path(path)
        return (patch.object(vfx, 'catalog', return_value={'resources': entries}),
                patch.object(vfx, 'verify_resource', side_effect=verify),
                patch.object(vfx, 'resource_path', return_value=frozen_path))

    def test_soft_add_binds_exact_modern_package_without_copying_other_root_content(self):
        frozen = self.root / 'modern-circle'
        original = self.root / 'exact-old-vimo-circle'
        node = self.current['materials']['common_mask'][0]
        node.update(path=str(original), name='REA-circle-soft', is_old_version=True)
        node['config']['feather'] = .1
        self.write(self.main, self.current)
        self.write(self.source / 'Timelines/project.json', {'main_timeline_id': 'timeline-1'})
        before = deepcopy(self.current); root_bytes = self.mirror.read_bytes()
        cp, vp, rp = self.soft_patches(original, frozen)
        with cp, vp, rp:
            result = self.run_reconcile({**action('video.mask.set', feather=.1), 'preset': 'mask/circle-soft'})
        before['materials']['common_mask'][0].update(path=str(frozen), is_old_version=False)
        before['materials']['common_mask'][0]['config'].update(centerX=0, centerY=0)
        self.assertEqual(self.decrypt(self.main), before)
        self.assertEqual(self.mirror.read_bytes(), root_bytes)
        self.assertEqual(result['patch']['modern_resource_binding'],
                         {'before': str(original), 'after': str(frozen)})

    def test_soft_binding_cannot_accept_arbitrary_old_package(self):
        node = self.current['materials']['common_mask'][0]
        node.update(path=str(self.root / 'unknown-resource'), name='REA-circle-soft', is_old_version=True)
        self.write(self.main, self.current); before = self.main.read_bytes()
        cp, vp, rp = self.soft_patches(self.root / 'exact-old-vimo-circle', self.root / 'modern-circle')
        with cp, vp, rp:
            with self.assertRaisesRegex(ValueError, 'manifest mismatch'):
                self.run_reconcile({**action('video.mask.set', width=.65, height=.65), 'preset': 'mask/circle-soft'})
        self.assertEqual(self.main.read_bytes(), before)

    def test_declared_main_mismatch_cannot_be_rescued_from_stale_root(self):
        self.write(self.source / 'Timelines/project.json', {'main_timeline_id': 'timeline-1'})
        root = timeline(); root['materials']['common_mask'][0]['config']['height'] = .3
        self.write(self.mirror, root); before = self.main.read_bytes()
        with self.assertRaises(ValueError):
            self.run_reconcile(action(height=.3))
        self.assertEqual(self.main.read_bytes(), before)

    def test_legacy_wrong_target_time_or_swapped_mask_id_fails_without_main_write(self):
        before = self.main.read_bytes()
        for name, changed in [('time', 'time'), ('id', 'id')]:
            root = timeline(); root['materials']['common_mask'][0]['config']['height'] = .3
            if changed == 'time':
                root['tracks'][0]['segments'][0]['target_timerange']['duration'] = 3_000_000
            else:
                root['materials']['common_mask'][0]['id'] = 'mask-2'
                root['tracks'][0]['segments'][0]['extra_material_refs'] = ['mask-2']
            self.write(self.mirror, root)
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                self.run_reconcile(action(height=.3), name)
            self.assertEqual(self.main.read_bytes(), before)

    def test_unknown_bound_mask_cannot_be_treated_as_missing(self):
        self.current['materials']['common_mask'][0]['resource_id'] = 'unknown-resource'
        self.write(self.main, self.current); before = self.main.read_bytes()
        with self.assertRaisesRegex(ValueError, 'Unreviewed'):
            self.run_reconcile(action('video.mask.set', width=.65, height=.65))
        self.assertEqual(self.main.read_bytes(), before)

    def test_idempotent_selected_main_writes_only_audit(self):
        result = self.run_reconcile(action(width=.65))
        self.assertEqual(result['status'], 'already-compatible')
        self.assertNotIn('recovery_path', result)
        self.assertEqual(len(list(self.audit.iterdir())), 1)

    def test_concurrent_source_change_retains_ciphertext_and_refuses_replacement(self):
        root = timeline(); root['materials']['common_mask'][0]['config']['height'] = .3
        self.write(self.mirror, root); before = self.main.read_bytes()
        def changed_manifest(source):
            (self.source / 'concurrent.txt').write_text('external change', encoding='utf-8')
            return self.manifest(source)
        with patch.object(native.j, 'files_manifest', side_effect=changed_manifest):
            with self.assertRaisesRegex(ValueError, 'concurrently'):
                self.run_reconcile(action(height=.3))
        self.assertEqual(self.main.read_bytes(), before)
        report = json.loads((self.audit / 'step.mask-controls.json').read_text(encoding='utf-8'))
        self.assertEqual(report['status'], 'failed-or-unverified')
        self.assertTrue(Path(report['recovery_path']).is_file())
        self.assertTrue(Path(report['temporary_path']).is_file())

    def test_other_runtime_rejected_before_saved_source_reads(self):
        with patch.object(native, 'read_draft') as read:
            with self.assertRaisesRegex(ValueError, 'exact Windows'):
                controls.reconcile_after_cli(action(), self.source, self.audit / 'other',
                                             {**self.runtime, 'app_build': '11.5.0.14471'})
            read.assert_not_called()


if __name__ == '__main__':
    unittest.main()
