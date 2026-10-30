from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
import windows_vfx as vfx
from runtime_profiles import WINDOWS_1147_PROFILE


class WindowsVfxContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='jy-vfx-')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name).resolve()
        self.entries = {}
        self.bindings = {}
        for key, bucket, contents in [('effect/oobe-glow', 'video_effects', b'glow'),
                                      ('filter/cyberpunk', 'effects', b'cyan'),
                                      ('filter/blanca', 'effects', b'grey'),
                                      ('transition/white-flash', 'transitions', b'flash')]:
            folder = self.folder / key.split('/')[1]; folder.mkdir()
            (folder / 'config.json').write_bytes(contents)
            files = {'config.json': {'size': len(contents), 'sha256': hashlib.sha256(contents).hexdigest()}}
            template = {'type': 'video_effect', 'render_index': 11000, 'resource_id': ''} if bucket == 'video_effects' else {
                'type': 'filter', 'resource_id': '', 'beauty_face_auto_retouch_info': {},
                'multi_language_current': '', 'sub_type': 'none'}
            self.entries[key] = {'key': key, 'bucket': bucket, 'material_template': template,
                                 'files': files, 'tree_sha256': vfx.manifest_hash(files),
                                 'value_range': [1, 1] if bucket == 'video_effects' else [0, 1], 'default_value': 1}
            self.bindings[key] = str(folder)
        self.entries['transition/white-flash'].update(
            material_template={'category_id': '5914136', 'effect_id': '7343136487182963211',
                               'is_overlap': True, 'name': '白光快闪', 'resource_id': '7343136487182963211',
                               'source_platform': 1, 'type': 'transition'},
            resource_id='7343136487182963211', duration_ms_values=[600], default_duration_ms=600)
        self.entries['transition/white-flash'].pop('value_range')
        self.entries['transition/white-flash'].pop('default_value')
        self.cpatch = patch.object(vfx, 'catalog', return_value={'resources': self.entries})
        self.cpatch.start(); self.addCleanup(self.cpatch.stop)
        self.spatch = patch.object(vfx, 'load_config', return_value={'windows_vfx_resources': self.bindings})
        self.spatch.start(); self.addCleanup(self.spatch.stop)
        self.runtime = {'runtime_profile': WINDOWS_1147_PROFILE, 'app_build': '11.4.7.14462'}
        self.timeline = {'materials': {'videos': [{'id': 'video1', 'type': 'video', 'path': 'local.mp4'}]},
                         'tracks': [{'id': 'track1', 'type': 'video', 'segments': [
                             {'id': 'segment1', 'material_id': 'video1', 'extra_material_refs': []}]}]}

    def material(self, key, identity='fx1', value=1):
        if key.startswith('transition/'):
            return {**deepcopy(self.entries[key]['material_template']), 'id': identity,
                    'duration': 600000, 'path': self.bindings[key]}
        return {**deepcopy(self.entries[key]['material_template']), 'id': identity,
                'value': value, 'path': self.bindings[key]}

    def bind(self, key, value=1):
        entry = self.entries[key]
        self.timeline['materials'][entry['bucket']] = [self.material(key, value=value)]
        self.timeline['tracks'][0]['segments'][0]['extra_material_refs'] = ['fx1']

    def test_same_filter_shape_selected_by_bytes(self):
        node = self.material('filter/blanca')
        self.assertEqual(vfx.entry_for_node('effects', node)['key'], 'filter/blanca')
        # A changed basename cannot turn identical template fields into an identity.
        node['path'] = self.bindings['filter/cyberpunk']
        self.assertEqual(vfx.entry_for_node('effects', node)['key'], 'filter/cyberpunk')

    def test_modified_and_extra_resource_files_fail(self):
        folder = Path(self.bindings['filter/cyberpunk'])
        (folder / 'config.json').write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'bytes changed'):
            vfx.resource_path('filter/cyberpunk')
        (folder / 'config.json').write_bytes(b'cyan')
        (folder / 'unexpected.shader').write_bytes(b'new')
        with self.assertRaisesRegex(ValueError, 'bytes changed'):
            vfx.resource_path('filter/cyberpunk')

    def test_unreviewed_material_fields_fail(self):
        node = self.material('effect/oobe-glow'); node['effect_id'] = 'unknown'
        with self.assertRaisesRegex(ValueError, 'material shape'):
            vfx.entry_for_node('video_effects', node)
        node = self.material('filter/cyberpunk'); node['resource_id'] = 'paid-other-resource'
        with self.assertRaisesRegex(ValueError, 'material shape'):
            vfx.entry_for_node('effects', node)

    def test_unknown_effect_parameters_fail(self):
        node = self.material('effect/oobe-glow'); node['adjust_params'] = [{'name': 'unknown', 'value': .5}]
        with self.assertRaises(ValueError):
            vfx.entry_for_node('video_effects', node)

    def test_official_filter_zero_omission_roundtrips_without_mutating_saved_shape(self):
        self.bind('filter/blanca', 0)
        node = self.timeline['materials']['effects'][0]
        del node['value']
        action = {'op': 'video.filter.add', 'segment_id': 'segment1',
                  'preset': 'filter/blanca', 'value': 0}
        self.assertEqual(vfx.verify_action(action, self.timeline)['value'], 0)
        self.assertEqual(vfx.validate_timeline(self.timeline, self.runtime)['filters'], 1)
        self.assertNotIn('value', node)
        with self.assertRaisesRegex(ValueError, 'strength did not round-trip'):
            vfx.verify_action({**action, 'value': .5}, self.timeline)
        self.bind('effect/oobe-glow')
        del self.timeline['materials']['video_effects'][0]['value']
        with self.assertRaises(ValueError):
            vfx.entry_for_node('video_effects', self.timeline['materials']['video_effects'][0])

    def test_unreviewed_text_styles_and_effect_tracks_cannot_bypass_material_gate(self):
        self.timeline['materials']['texts'] = [{'id': 'text1', 'content': json.dumps({'styles': [
            {'effectStyle': {'id': 'unknown', 'path': 'existing-local-directory'}}]})}]
        with self.assertRaisesRegex(ValueError, 'text effect styles'):
            vfx.validate_timeline(self.timeline, self.runtime)
        self.timeline['materials']['texts'] = []
        self.timeline['tracks'][0]['type'] = 'effect'
        with self.assertRaisesRegex(ValueError, 'effect/filter tracks'):
            vfx.validate_timeline(self.timeline, self.runtime)

    def test_timeline_binding_and_exact_runtime(self):
        self.bind('filter/cyberpunk', .4)
        result = vfx.validate_timeline(self.timeline, self.runtime)
        self.assertEqual(result['filters'], 1)
        with self.assertRaisesRegex(ValueError, 'exact 11.4.7'):
            vfx.validate_timeline(self.timeline, {'runtime_profile': 'jy14-headless-windows-11.5.0.14471'})

    def test_orphan_and_wrong_track_fail(self):
        self.bind('filter/cyberpunk')
        self.timeline['tracks'][0]['segments'][0]['extra_material_refs'] = []
        with self.assertRaisesRegex(ValueError, 'no verified'):
            vfx.validate_timeline(self.timeline, self.runtime)
        self.timeline['tracks'][0]['segments'][0]['extra_material_refs'] = ['fx1']
        self.timeline['tracks'][0]['type'] = 'audio'
        with self.assertRaisesRegex(ValueError, 'video segment'):
            vfx.validate_timeline(self.timeline, self.runtime)

    def test_duplicate_material_id_and_primary_binding_fail(self):
        self.bind('filter/cyberpunk')
        self.timeline['materials']['texts'] = [{'id': 'fx1', 'type': 'text'}]
        with self.assertRaisesRegex(ValueError, 'globally unique'):
            vfx.validate_timeline(self.timeline, self.runtime)
        self.timeline['materials'].pop('texts')
        self.timeline['tracks'][0]['segments'][0]['material_id'] = 'fx1'
        with self.assertRaisesRegex(ValueError, 'primary'):
            vfx.validate_timeline(self.timeline, self.runtime)

    def test_compile_explicit_resource_and_normalized_intensity(self):
        action = {'op': 'video.filter.add', 'segment_id': 'segment1', 'preset': 'filter/cyberpunk', 'value': .4}
        argv = vfx.compile_action(action, self.timeline, 'local://my-draft')
        self.assertEqual(argv[:4], ['draft', 'video', 'filter', 'add'])
        self.assertEqual(argv[-2:], ['--intensity', '0.4'])
        self.assertIn('local://' + Path(self.bindings['filter/cyberpunk']).as_posix(), argv)

    def test_compile_rejects_wrong_kind_bad_value_and_extra_keys(self):
        base = {'op': 'video.filter.add', 'segment_id': 'segment1', 'preset': 'filter/cyberpunk'}
        for change in ({'value': True}, {'value': 1.1}, {'value': float('nan')},
                       {'preset': 'effect/oobe-glow'}, {'unknown': 1}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                vfx.compile_action({**base, **change}, self.timeline, 'local://my-draft')

    def test_duplicate_kind_rejected_at_execution(self):
        self.bind('filter/cyberpunk')
        action = {'op': 'video.filter.add', 'segment_id': 'segment1', 'preset': 'filter/blanca'}
        with self.assertRaisesRegex(ValueError, 'already has'):
            vfx.compile_action(action, self.timeline, 'local://my-draft')
        self.assertTrue(vfx.compile_action(action, self.timeline, 'local://my-draft', temporal=False))

    def test_readback_checks_material_preset_and_strength(self):
        self.bind('filter/cyberpunk', .4)
        action = {'op': 'video.filter.add', 'segment_id': 'segment1', 'preset': 'filter/cyberpunk', 'value': .4}
        self.assertEqual(vfx.verify_action(action, self.timeline)['material_id'], 'fx1')
        with self.assertRaisesRegex(ValueError, 'strength'):
            vfx.verify_action({**action, 'value': .8}, self.timeline)
        with self.assertRaisesRegex(ValueError, 'preset'):
            vfx.verify_action({**action, 'preset': 'filter/blanca'}, self.timeline)

    def transition_timeline(self):
        self.timeline['materials']['videos'] = [
            {'id': identity, 'type': 'video', 'path': 'local-' + identity + '.mp4', 'duration': 5000000}
            for identity in ('video1', 'video2')]
        self.timeline['tracks'][0]['segments'] = [
            {'id': identity, 'material_id': material, 'volume': 0,
             'source_timerange': {'start': 1000000, 'duration': 3000000},
             'target_timerange': {'start': start, 'duration': 3000000}, 'extra_material_refs': []}
            for identity, material, start in [('segment1', 'video1', 0), ('segment2', 'video2', 3000000)]]
        return {'op': 'video.transition.add', 'segment_id': 'segment1',
                'preset': 'transition/white-flash', 'duration_ms': 600}

    def test_transition_compile_uses_metadata_resource_and_overlap(self):
        action = self.transition_timeline()
        argv = vfx.compile_action(action, self.timeline, 'local://my-draft')
        self.assertEqual(argv[:4], ['draft', 'video', 'transition', 'add'])
        self.assertIn('vimo://7343136487182963211', argv)
        self.assertEqual(argv[-4:], ['--duration', '600ms', '--is-overlap', 'true'])
        for change in ({'duration_ms': 500}, {'duration_ms': True}, {'value': 1}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                vfx.compile_action({**action, **change}, self.timeline, 'local://my-draft')

    def test_transition_tail_gap_speed_photo_audio_and_handles_fail(self):
        action = self.transition_timeline()
        original = deepcopy(self.timeline)
        for edit in ('tail', 'gap', 'speed', 'photo', 'audio', 'handles', 'volume-keyframe'):
            self.timeline = deepcopy(original)
            left, right = self.timeline['tracks'][0]['segments']
            local_action = deepcopy(action)
            if edit == 'tail':
                local_action['segment_id'] = 'segment2'
            elif edit == 'gap':
                right['target_timerange']['start'] += 1
            elif edit == 'speed':
                left['speed'] = 1.5
            elif edit == 'photo':
                self.timeline['materials']['videos'][1]['type'] = 'photo'
            elif edit == 'audio':
                left['volume'] = 1
            elif edit == 'handles':
                right['source_timerange']['start'] = 0
            else:
                left['common_keyframes'] = [{'property_type': 'KFTypeVolume', 'keyframe_list': []}]
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                vfx.compile_action(local_action, self.timeline, 'local://my-draft')

    def test_transition_readback_and_binding_validation(self):
        action = self.transition_timeline()
        self.bind('transition/white-flash')
        result = vfx.validate_timeline(self.timeline, self.runtime)
        self.assertEqual(result['transitions'], 1)
        readback = vfx.verify_action(action, self.timeline)
        self.assertEqual(readback['cut_us'], 3000000)
        self.assertEqual(readback['right_segment_id'], 'segment2')
        with self.assertRaisesRegex(ValueError, 'duration'):
            vfx.verify_action({**action, 'duration_ms': 400}, self.timeline)
        with self.assertRaisesRegex(ValueError, 'already has'):
            vfx.compile_action(action, self.timeline, 'local://my-draft')

    def test_transition_metadata_bool_is_not_integer(self):
        node = self.material('transition/white-flash')
        node['is_overlap'] = 1
        with self.assertRaisesRegex(ValueError, 'shape'):
            vfx.entry_for_node('transitions', node)


class ShippedVfxCatalog(unittest.TestCase):
    def test_new_default_resources_do_not_admit_unverified_slider_states(self):
        entries = vfx.catalog()['resources']
        for key, parameter in [('effect/mild-shake', 'effects_adjust_speed'),
                               ('effect/mild-shake', 'effects_adjust_range'),
                               ('effect/blur', 'effects_adjust_blur'),
                               ('filter/retro-lomo', 'effects_adjust_filter'),
                               ('filter/silent-film', 'effects_adjust_filter')]:
            entry = entries[key]
            node = {**deepcopy(entry['material_template']), 'id': 'verified-resource',
                    'path': '/fixture-resource', 'value': entry['default_value']}
            with self.subTest(preset=key, parameter=parameter):
                self.assertTrue(vfx._shape_matches(entry['bucket'], node, entry))
                node['adjust_params'] = [{'name': parameter, 'value': .5}]
                self.assertFalse(vfx._shape_matches(entry['bucket'], node, entry))

    def test_catalog_fingerprint_and_no_machine_paths(self):
        catalog = vfx.catalog()
        self.assertEqual(set(catalog['resources']), {'effect/oobe-glow', 'filter/cyberpunk', 'filter/blanca',
                                                   'transition/white-flash', 'mask/circle',
                                                   'transition/dissolve-compat', 'transition/fog-compat',
                                                   'mask/circle-soft', 'transition/slide-left-compat',
                                                   'transition/slide-right-compat', 'effect/mild-shake',
                                                   'effect/blur', 'filter/retro-lomo', 'filter/silent-film'})
        text = json.dumps(catalog)
        self.assertNotIn('D:\\', text)
        for entry in catalog['resources'].values():
            self.assertEqual(vfx.manifest_hash(entry['files']), entry['tree_sha256'])


class NativeCircleContracts(unittest.TestCase):
    def setUp(self):
        WindowsVfxContracts.setUp(self)
        folder = self.folder / 'circle'; folder.mkdir()
        (folder / 'config.json').write_bytes(b'circle')
        files = vfx.tree_manifest(folder)
        self.entries['mask/circle'] = {
            'key': 'mask/circle', 'bucket': 'common_mask', 'resource_id': '7356934080102928946',
            'material_template': {'type': 'mask', 'resource_type': 'circle', 'name': 'REA-circle',
                                  'is_old_version': False, 'config': {'width': .65, 'height': .65}},
            'files': files, 'tree_sha256': vfx.manifest_hash(files)}
        self.bindings['mask/circle'] = str(folder)
        self.action = {'op': 'video.mask.set', 'segment_id': 'segment1', 'preset': 'mask/circle'}

    def bind_mask(self):
        node = {**deepcopy(self.entries['mask/circle']['material_template']),
                'id': 'mask1', 'path': self.bindings['mask/circle']}
        self.timeline['materials']['common_mask'] = [node]
        self.timeline['tracks'][0]['segments'][0]['extra_material_refs'] = ['mask1']
        return node

    def test_mask_compile_has_compatible_defaults_and_configurable_geometry(self):
        argv = vfx.compile_action(self.action, self.timeline, 'local://my-draft')
        self.assertIn('vimo://7356934080102928946', argv)
        self.assertEqual(argv[argv.index('--width') + 1], '0.65')
        with self.assertRaises(ValueError):
            vfx.compile_action({**self.action, 'value': 1}, self.timeline, 'local://my-draft')
        argv = vfx.compile_action({**self.action, 'config': {'width': .2, 'center_y': .3}},
                                  self.timeline, 'local://my-draft')
        self.assertEqual(argv[argv.index('--width') + 1], '0.2')
        self.assertEqual(argv[argv.index('--center-y') + 1], '0.3')

    def test_saved_mask_must_have_reviewed_protocol_geometry_and_no_value(self):
        original = self.bind_mask()
        self.assertEqual(vfx.verify_action(self.action, self.timeline)['is_old_version'], False)
        self.assertEqual(vfx.validate_timeline(self.timeline, self.runtime)['masks'], 1)
        canonical = deepcopy(original); canonical.pop('is_old_version')
        self.assertEqual(vfx.entry_for_node('common_mask', canonical)['key'], 'mask/circle')
        for update in ({'is_old_version': True}, {'config': {'width': .01, 'height': .65}}, {'value': 1},
                       {'config': {'width': .5, 'height': .65, 'rotation': 90}}):
            node = {**original, **update}
            with self.subTest(update=update), self.assertRaises(ValueError):
                vfx.entry_for_node('common_mask', node)

    def test_native_config_values_and_requested_readback_are_both_checked(self):
        node = self.bind_mask()
        node['config'] = {'width': .3, 'height': .6, 'centerX': -.4, 'feather': 0}
        self.assertEqual(vfx.entry_for_node('common_mask', node)['key'], 'mask/circle')
        updated = {'op': 'video.mask.update', 'segment_id': 'segment1', 'preset': 'mask/circle',
                   'config': {'width': .3, 'center_x': -.4}}
        self.assertEqual(vfx.verify_action(updated, self.timeline)['config']['width'], .3)
        with self.assertRaisesRegex(ValueError, 'did not round-trip'):
            vfx.verify_action({**updated, 'config': {'width': .4}}, self.timeline)

    def test_unknown_mask_channel_cannot_bypass_the_resource_gate(self):
        self.bind_mask()
        self.timeline['tracks'][0]['segments'][0]['common_keyframes'] = [
            {'property_type': 'KFTypeCommonMaskSizeWidth', 'material_id': 'unbound'}]
        with self.assertRaises(ValueError):
            vfx.validate_timeline(self.timeline, self.runtime)


if __name__ == '__main__':
    unittest.main()
