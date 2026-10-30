"""Offline admission boundaries for actual per-mask native animation channels."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'engine'))
import windows_mask_keyframes as mask


def timeline():
    return {'id': 'timeline', 'materials': {'common_mask': [
        {'id': 'mask-id', 'type': 'mask', 'resource_type': 'circle'}]},
        'tracks': [{'type': 'video', 'segments': [{
            'id': 'segment-id', 'material_id': 'media', 'extra_material_refs': ['mask-id'],
            'source_timerange': {'start': 0, 'duration': 4_000_000},
            'target_timerange': {'start': 3_000_000, 'duration': 4_000_000}}]}]}


def action():
    return {'op': 'video.mask.keyframe', 'segment_id': 'segment-id', 'preset': 'mask/circle',
            'property': 'width', 'points': [{'time_ms': 0, 'value': .2}, {'time_ms': 2000, 'value': .8}]}


def saved():
    value = timeline()
    value['tracks'][0]['segments'][0]['common_keyframes'] = [{
        'id': 'channel-id', 'material_id': 'mask-id', 'property_type': 'KFTypeCommonMaskSizeWidth',
        'keyframe_list': [{'id': 'point-a', 'values': [.2]},
                          {'id': 'point-b', 'time_offset': 2_000_000, 'values': [.8]}]}]
    return value


class MaskAnimationBoundaries(unittest.TestCase):
    def test_native_material_channel_and_local_timestamps_are_explicit(self):
        original = timeline()
        argv = mask.compile_keyframe(action(), original, 'local://sample')
        self.assertEqual(argv[argv.index('--keyframe-type') + 1], 'KFTypeCommonMaskSizeWidth')
        self.assertEqual(argv[argv.index('--material-id') + 1], 'mask-id')
        self.assertEqual(argv[argv.index('--points') + 1], '0ms:0.2,2000ms:0.8')
        self.assertNotIn('--animated-property', argv)
        self.assertEqual(original, timeline())

    def test_exact_binding_and_unique_target_are_required(self):
        for change in ('no-mask', 'two-mask', 'audio', 'duplicate-target'):
            value = timeline()
            if change == 'no-mask':
                value['tracks'][0]['segments'][0]['extra_material_refs'] = []
            elif change == 'two-mask':
                value['materials']['common_mask'].append({'id': 'mask-2', 'type': 'mask', 'resource_type': 'circle'})
                value['tracks'][0]['segments'][0]['extra_material_refs'].append('mask-2')
            elif change == 'audio':
                value['tracks'][0]['type'] = 'audio'
            else:
                value['tracks'][0]['segments'].append(deepcopy(value['tracks'][0]['segments'][0]))
            with self.subTest(change=change), self.assertRaises(ValueError):
                mask.compile_keyframe(action(), value, 'local://sample')

    def test_unsafe_values_times_curves_and_unknown_fields_fail_before_cli(self):
        for update in ({'property': 'opacity'}, {'curve': 'ease-in'}, {'other': True},
                       {'points': [{'time_ms': 0, 'value': .2}]},
                       {'points': [{'time_ms': 0, 'value': .2}, {'time_ms': 4001, 'value': .8}]},
                       {'points': [{'time_ms': 0, 'value': .2}, {'time_ms': 0, 'value': .8}]},
                       {'points': [{'time_ms': 0, 'value': .2}, {'time_ms': 2000, 'value': float('nan')}]},
                       {'points': [{'time_ms': 0, 'value': .2}, {'time_ms': True, 'value': .8}]},
                       {'property': 'feather', 'points': [{'time_ms': 0, 'value': 0},
                                                        {'time_ms': 2000, 'value': .5}]}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                mask.compile_keyframe({**action(), **update}, timeline(), 'local://sample')

    def test_trim_speed_and_nonordinary_time_domains_are_not_silently_remapped(self):
        for change in ({'speed': 2}, {'source_timerange': {'start': 1_000_000, 'duration': 4_000_000}},
                       {'source_timerange': {'duration': 8_000_000}}, {'reverse': True}, {'is_reverse': True}):
            value = timeline()
            value['tracks'][0]['segments'][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                mask.compile_keyframe(action(), value, 'local://sample')
        value = timeline()
        value['materials']['speeds'] = [{'id': 'speed', 'speed': 1, 'curve_speed': {'points': [0, 1]}}]
        value['tracks'][0]['segments'][0]['extra_material_refs'].append('speed')
        with self.assertRaises(ValueError):
            mask.compile_keyframe(action(), value, 'local://sample')

    def test_saved_channel_must_match_requested_points_and_binding(self):
        self.assertTrue(mask.verify_keyframe(action(), saved())['mask_itself_animated'])
        for update in ({'material_id': ''}, {'material_id': 'other'}, {'property_type': 'KFTypeScaleX'}):
            value = saved()
            value['tracks'][0]['segments'][0]['common_keyframes'][0].update(update)
            with self.subTest(update=update), self.assertRaises(ValueError):
                mask.verify_keyframe(action(), value)
        value = saved()
        value['tracks'][0]['segments'][0]['common_keyframes'][0]['keyframe_list'][1]['values'] = [.7]
        with self.assertRaises(ValueError):
            mask.verify_keyframe(action(), value)

    def test_unreviewed_material_channels_and_graph_controls_are_rejected(self):
        for update in ({'curveType': 'CurveOut'}, {'graph': {}},
                       {'left_control': {'x': 1, 'y': 0}}, {'values': [.2, .3]}):
            value = saved()
            value['tracks'][0]['segments'][0]['common_keyframes'][0]['keyframe_list'][0].update(update)
            with self.subTest(update=update), self.assertRaises(ValueError):
                mask.validate_keyframes(value['tracks'][0]['segments'][0], {'mask-id'})
        value = saved()
        value['tracks'][0]['segments'][0]['common_keyframes'][0]['property_type'] = 'KFTypeCommonMaskUnknown'
        with self.assertRaises(ValueError):
            mask.validate_keyframes(value['tracks'][0]['segments'][0], {'mask-id'})
        value['tracks'][0]['segments'][0]['common_keyframes'][0]['material_id'] = ''
        with self.assertRaises(ValueError):
            mask.validate_keyframes(value['tracks'][0]['segments'][0], {'mask-id'})

    def test_duplicate_channels_and_out_of_order_points_are_rejected(self):
        value = saved()
        segment = value['tracks'][0]['segments'][0]
        segment['common_keyframes'].append(deepcopy(segment['common_keyframes'][0]))
        with self.assertRaises(ValueError):
            mask.validate_keyframes(segment, {'mask-id'})
        value = saved()
        segment = value['tracks'][0]['segments'][0]
        segment['common_keyframes'][0]['keyframe_list'].reverse()
        with self.assertRaises(ValueError):
            mask.validate_keyframes(segment, {'mask-id'})

    def test_preflight_can_precede_mask_creation_but_still_validates_action_values(self):
        value = timeline()
        value['materials']['common_mask'] = []
        value['tracks'][0]['segments'][0]['extra_material_refs'] = []
        self.assertEqual(mask.compile_keyframe(action(), value, 'local://sample', temporal=False), [])
        with self.assertRaises(ValueError):
            mask.compile_keyframe({**action(), 'property': 'unknown'}, value, 'local://sample', temporal=False)

    def test_feather_is_available_only_on_the_reviewed_modern_mask_resource(self):
        feather = {**action(), 'property': 'feather',
                   'points': [{'time_ms': 0, 'value': 0}, {'time_ms': 2000, 'value': 1}]}
        with self.assertRaisesRegex(ValueError, 'modern circle-soft'):
            mask.compile_keyframe(feather, timeline(), 'local://sample')
        modern = {**feather, 'preset': 'mask/circle-soft'}
        argv = mask.compile_keyframe(modern, timeline(), 'local://sample')
        self.assertEqual(argv[argv.index('--keyframe-type') + 1], 'KFTypeCommonMaskFeather')
        value = saved()
        group = value['tracks'][0]['segments'][0]['common_keyframes'][0]
        group['property_type'] = 'KFTypeCommonMaskFeather'
        group['keyframe_list'][0]['values'] = [0]
        group['keyframe_list'][1]['values'] = [1]
        self.assertTrue(mask.verify_keyframe(modern, value)['mask_itself_animated'])
        with self.assertRaisesRegex(ValueError, 'Legacy circle'):
            mask.validate_keyframes(value['tracks'][0]['segments'][0], {'mask-id'})
        self.assertEqual(mask.validate_keyframes(value['tracks'][0]['segments'][0], {'mask-id'},
                                                soft_mask_ids={'mask-id'}), 1)

    def test_successful_normal_readback_needs_no_reconciliation_write(self):
        import native_export as native
        import windows_timeline_patch as commit
        with patch.object(native, 'read_draft', return_value=(Path('unused'), {}, saved(), {})), \
                patch.object(commit, 'commit') as writer:
            self.assertIsNone(mask.reconcile_after_cli(action(), 'unused', 'unused', {}))
            writer.assert_not_called()

    def test_declared_main_failure_never_reads_a_stale_root_mirror(self):
        import native_export as native
        import windows_timeline_patch as commit
        with patch.object(native, 'read_draft', return_value=(Path('unused'), {}, timeline(), {})), \
                patch.object(Path, 'exists', return_value=True), patch.object(commit, 'commit') as writer:
            with self.assertRaisesRegex(ValueError, 'stale root mirror was ignored'):
                mask.reconcile_after_cli(action(), 'unused', 'unused', {})
            writer.assert_not_called()


if __name__ == '__main__':
    unittest.main()
