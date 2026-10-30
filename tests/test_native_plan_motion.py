"""Native plan clocks and reviewed Windows static masks, without a GUI."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
import native_motion as motion
import native_resources as resources
import native_export as export
from runtime_profiles import WINDOWS_1147_PROFILE


class NativePlanMotion(unittest.TestCase):
    def test_trimmed_one_x_uses_native_source_clock(self):
        spec = {'duration_us': 4_000_000, 'source_start_us': 5_163_000_000, 'speed': 1,
                'keyframes': {'scale': [{'at_us': 0, 'value': 1},
                                        {'at_us': 1_000_000, 'value': 1.8},
                                        {'at_us': 4_000_000, 'value': 1}]}}
        motion.validate(spec, 'video')
        groups = motion.keyframe_groups(spec)
        self.assertEqual([n['time_offset'] for n in groups[0]['keyframe_list']],
                         [5_163_000_000, 5_164_000_000, 5_167_000_000])
        actual = {'common_keyframes': groups}
        motion.verify(actual, {}, spec, 'video', 0)
        local_clock = deepcopy(actual)
        for node in local_clock['common_keyframes'][0]['keyframe_list']:
            node['time_offset'] -= spec['source_start_us']
        with self.assertRaisesRegex(ValueError, 'Keyframe time changed'):
            motion.verify(local_clock, {}, spec, 'video', 0)

    def test_speed_remapping_stays_rejected(self):
        spec = {'duration_us': 1_000_000, 'speed': .5,
                'keyframes': {'scale': [{'at_us': 0, 'value': 1}, {'at_us': 1_000_000, 'value': 2}]}}
        with self.assertRaisesRegex(ValueError, 'speed-adjusted'):
            motion.validate(spec, 'video')

    def test_plain_text_clock_remains_local(self):
        spec = {'duration_us': 1_000_000,
                'keyframes': {'scale': [{'at_us': 0, 'value': .7}, {'at_us': 100_000, 'value': 1}]}}
        motion.validate(spec, 'text')
        self.assertEqual([n['time_offset'] for n in motion.keyframe_groups(spec)[0]['keyframe_list']], [0, 100_000])

    def test_trimmed_audio_envelope_needs_separate_acceptance(self):
        spec = {'duration_us': 1_000_000, 'source_start_us': 2_000_000,
                'keyframes': {'volume': [{'at_us': 0, 'value': 0}, {'at_us': 100_000, 'value': .2}]}}
        with self.assertRaisesRegex(ValueError, 'video only'):
            motion.validate(spec, 'audio')

    def test_reviewed_windows_mask_public_geometry_and_inventory(self):
        mask = {'preset': 'mask/circle-soft', 'config': {'width': .6, 'height': .285,
                'center_x': .1, 'center_y': .2, 'feather': .02}}
        motion.validate({'mask': mask}, 'video')
        config = motion.mask_config(mask)
        self.assertEqual((config['centerX'], config['centerY'], config['feather']), (.1, .2, .02))
        self.assertFalse(config['invert'])
        self.assertEqual(resources.wanted_keys({'tracks': [{'type': 'video', 'segments': [{'mask': mask}]}]}),
                         ['windows-mask/circle-soft'])

    def test_windows_mask_rejects_unknown_shape_fields_and_legacy_feather(self):
        for mask in ({'preset': 'mask/star'}, {'preset': 'mask/circle-soft', 'config': {'invert': True}},
                     {'preset': 'mask/circle-soft', 'shape': 'circle'},
                     {'preset': 'mask/circle', 'config': {'feather': .1}}):
            with self.assertRaises(ValueError):
                motion.validate({'mask': mask}, 'video')

    def test_windows_mask_protocol_identity_stays_strict(self):
        spec = {'mask': {'preset': 'mask/circle-soft', 'config': {'feather': .02}}}
        node = motion.mask_material(spec['mask'], Path(tempfile.gettempdir()) / 'future-draft')
        actual = {'enable_video_mask': True, 'extra_material_refs': [node['id']]}
        index = {node['id']: ('common_mask', node)}
        motion.verify(actual, index, spec, 'video', 0)
        node['is_old_version'] = True
        with self.assertRaisesRegex(ValueError, 'resource identity'):
            motion.verify(actual, index, spec, 'video', 0)

    def test_compact_windows_resource_path_keeps_full_hash_identity_and_rejects_collision(self):
        first = {'tree_sha256': '0123456789abcdef' + 'a' * 48, 'runtime_profile': WINDOWS_1147_PROFILE}
        second = {**first, 'tree_sha256': '0123456789abcdef' + 'b' * 48}
        self.assertEqual(resources.relative_path(first), 'Resources/vfx/0123456789abcdef')
        self.assertEqual(first['tree_sha256'], '0123456789abcdef' + 'a' * 48)
        resources.check_path_collisions([('a', first), ('same-package', deepcopy(first))])
        with self.assertRaisesRegex(ValueError, 'collision'):
            resources.check_path_collisions([('a', first), ('b', second)])
        self.assertIn('Resources/headless-native/' + first['tree_sha256'], resources.accepted_relative_paths(first))
        self.assertEqual(resources.relative_path({'tree_sha256': first['tree_sha256']}),
                         'Resources/headless-native/' + first['tree_sha256'])

    def test_actual_circle_package_publish_path_budget(self):
        entry = resources.definition('windows-mask/circle-soft')
        base = Path(tempfile.gettempdir()).anchor or 'C:\\'
        # An installation-style root, a full-length transaction stage and the
        # real Chinese project name reproduce the observed MAX_PATH boundary.
        root = Path(base) / 'Users' / 'Administrator' / 'AppData' / 'Local' / 'JianyingPro' / 'User Data' / 'Projects' / 'com.lveditor.draft'
        folders = [root / ('.jy14-headless-' + 'f' * 32), root / '粤仔精修03-四姐妹把广仔夸到躺平-新版1019']
        self.assertEqual(len(entry['files']), 27)
        for folder in folders:
            self.assertLess(max(len(str(folder / resources.relative_path(entry) / name)) for name in entry['files']), 240)

    def test_unpublished_build_checks_owned_vfx_copy_without_rewriting_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            future = root / 'future-draft'
            folder = root / 'build' / 'draft'
            owned = folder / 'Resources' / 'reviewed-package'
            owned.mkdir(parents=True)
            timeline = {'materials': {'common_mask': [{'id': 'mask1',
                        'path': str(future / 'Resources' / 'reviewed-package')}]}}
            before = deepcopy(timeline)
            with patch.object(export, 'windows_supported_features', return_value={'accepted': True}) as validate:
                result = export.windows_build_supported_features(timeline, {'target': str(future)}, folder)
            self.assertTrue(result['accepted'])
            self.assertEqual(validate.call_args.args[0]['materials']['common_mask'][0]['path'], str(owned))
            self.assertEqual(timeline, before)
            timeline['materials']['common_mask'][0]['path'] = str(root / 'outside')
            with self.assertRaisesRegex(ValueError, 'draft-owned'):
                export.windows_build_supported_features(timeline, {'target': str(future)}, folder)


if __name__ == '__main__':
    unittest.main()
