"""Offline boundaries and partial-commit evidence; never launch the editor."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'engine'))
import windows_edit_actions as actions


def timeline():
    return {'id': 'timeline', 'duration': 4_000_000, 'materials': {
        'videos': [{'id': 'media', 'type': 'video'}], 'audios': [{'id': 'sound', 'type': 'music'}]},
        'tracks': [{'type': 'video', 'segments': [{'id': 'video-id', 'material_id': 'media',
                    'target_timerange': {'start': 0, 'duration': 4_000_000}}]},
                   {'type': 'audio', 'segments': [{'id': 'audio-id', 'material_id': 'sound',
                    'target_timerange': {'start': 0, 'duration': 4_000_000}}]}]}


def position():
    return {'op': 'keyframe.add', 'segment_id': 'video-id', 'property': 'position-x',
            'points': [{'time_ms': 0, 'value': -.65}, {'time_ms': 500, 'value': .45}]}


class ActionBoundaries(unittest.TestCase):
    def test_coordinate_and_time_units_are_explicit_and_do_not_modify_input(self):
        action = position(); original = deepcopy(action)
        argv = actions.compile_action(action, timeline(), 'local://test')
        self.assertEqual(argv[argv.index('--points') + 1], '0ms:-65%,500ms:45%')
        self.assertEqual(argv.count('--seg-id'), 1)
        self.assertNotIn('--target-track', argv)
        self.assertEqual(action, original)

    def test_unknown_target_wide_selector_and_unknown_field_are_rejected(self):
        for extra in ({'segment_id': 'unknown'}, {'segment_id': 'video-id,audio-id'},
                      {'segment_id': '*'}, {'track': 0}, {'op': 'raw-command'}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                actions.compile_action({**position(), **extra}, timeline(), 'local://test')

    def test_points_reject_invalid_time_value_duplicate_and_overrun(self):
        for points in ([{'time_ms': 0, 'value': 0}],
                       [{'time_ms': 0, 'value': 0}, {'time_ms': 0, 'value': 1}],
                       [{'time_ms': 0, 'value': 0}, {'time_ms': 4001, 'value': 1}],
                       [{'time_ms': 0, 'value': 0}, {'time_ms': 1.5, 'value': 1}],
                       [{'time_ms': 0, 'value': False}, {'time_ms': 100, 'value': 1}],
                       [{'time_ms': 0, 'value': 0}, {'time_ms': 100, 'value': float('nan')}],
                       [{'time_ms': 0, 'value': 0}, {'time_ms': 100, 'value': 1.1}]):
            with self.subTest(points=points), self.assertRaises(ValueError):
                actions.compile_action({**position(), 'points': points}, timeline(), 'local://test')

    def test_property_type_boundaries(self):
        for prop, segment in (('position-x', 'audio-id'), ('volume', 'missing'), ('unknown', 'video-id')):
            with self.subTest(prop=prop), self.assertRaises(ValueError):
                actions.compile_action({**position(), 'property': prop, 'segment_id': segment}, timeline(), 'local://test')

    def test_curve_requires_a_real_existing_point(self):
        action = {'op': 'keyframe.curve', 'segment_id': 'video-id', 'property': 'position-x',
                  'time_ms': 0, 'curve': 'ease-out'}
        with self.assertRaisesRegex(ValueError, 'existing point'):
            actions.compile_action(action, timeline(), 'local://test')
        actions.compile_action(action, timeline(), 'local://test', temporal=False)
        action['curve'] = ['arbitrary']
        with self.assertRaisesRegex(ValueError, 'curve'):
            actions.compile_action(action, timeline(), 'local://test', temporal=False)

    def test_speed_rejects_photos_and_nonpositive_values(self):
        action = {'op': 'video.speed', 'segment_id': 'video-id', 'speed': 1.5}
        value = timeline(); value['materials']['videos'][0]['type'] = 'photo'
        with self.assertRaisesRegex(ValueError, 'Still images'):
            actions.compile_action(action, value, 'local://test')
        for speed in (0, -1, True, 11):
            with self.subTest(speed=speed), self.assertRaises(ValueError):
                actions.compile_action({**action, 'speed': speed}, timeline(), 'local://test')

    def test_only_tested_normalized_adjustments_are_exposed(self):
        base = {'op': 'video.adjust', 'segment_id': 'video-id'}
        for extra in ({}, {'brightness': 5}, {'color-temperature': .2}, {'enable': True}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                actions.compile_action({**base, **extra}, timeline(), 'local://test')
        argv = actions.compile_action({**base, 'brightness': .03, 'contrast': .1}, timeline(), 'local://test')
        self.assertEqual(argv[-4:], ['--brightness', '0.03', '--contrast', '0.1'])

    def test_fade_units_and_overlap(self):
        base = {'op': 'audio.fade', 'segment_id': 'audio-id', 'in_ms': 500, 'out_ms': 800}
        argv = actions.compile_action(base, timeline(), 'local://test')
        self.assertEqual(argv[-4:], ['--in', '500ms', '--out', '800ms'])
        for extra in ({'out_ms': 3501}, {'in_ms': -1}, {'segment_id': 'video-id'}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                actions.compile_action({**base, **extra}, timeline(), 'local://test')

    def test_background_color_and_blur_have_separate_contracts(self):
        base = {'op': 'video.background', 'segment_id': 'video-id'}
        for extra in ({'type': 'none'}, {'type': 'color', 'color': 'red'},
                      {'type': 'blur', 'blur': 1.1}, {'type': 'blur', 'blur': .3, 'color': '#000000'}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                actions.compile_action({**base, **extra}, timeline(), 'local://test')
        argv = actions.compile_action({**base, 'type': 'color', 'color': '#101828'}, timeline(), 'local://test')
        self.assertEqual(argv[-4:], ['--type', 'color', '--color', '#101828'])

    def test_readback_rejects_accepted_command_without_native_value(self):
        with self.assertRaisesRegex(ValueError, 'channels'):
            actions.verify_action(position(), timeline())
        with self.assertRaisesRegex(ValueError, 'speed'):
            actions.verify_action({'op': 'video.speed', 'segment_id': 'video-id', 'speed': 1.5}, timeline())
        with self.assertRaisesRegex(ValueError, 'adjustment'):
            actions.verify_action({'op': 'video.adjust', 'segment_id': 'video-id', 'brightness': .1}, timeline())


class AuditedBatch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='edit-actions-test-'); self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name).resolve() / 'work'; self.work.mkdir()
        self.source = self.work / 'drafts' / 'test'; self.source.mkdir(parents=True)
        (self.source / 'draft_content.json').write_bytes(b'original encrypted draft bytes')
        self.native = timeline(); self.runtime = {'runtime_profile': 'test', 'app_build': '11.4.7.14462'}
        self.calls = []
        def read(path, runtime):
            return self.source, actions._j.files_manifest(self.source), deepcopy(self.native), {'source_timeline_sha256': 'a' * 64}
        for target, value in ((actions.dr.windows_runtime, self.runtime),):
            p = patch.object(target, 'validate_runtime', return_value=value); p.start(); self.addCleanup(p.stop)
        p = patch.object(actions.native, 'read_draft', side_effect=read); p.start(); self.addCleanup(p.stop)
        p = patch.object(actions.dr, 'ensure_editor_running'); p.start(); self.addCleanup(p.stop)
        p = patch.object(actions.dr, 'run_lyra', side_effect=self.official); p.start(); self.addCleanup(p.stop)
        p = patch.object(actions, 'configure_environment'); p.start(); self.addCleanup(p.stop)

    def official(self, argv, cwd, timeout, rw, ro):
        self.calls.append(argv)
        self.assertEqual(cwd, self.source.parent); self.assertEqual(rw, [self.source]); self.assertEqual(ro, [])
        segment = self.native['tracks'][0]['segments'][0]
        if argv[:3] == ['draft', 'keyframe', 'add']:
            segment['common_keyframes'] = [{'property_type': 'KFTypePositionX', 'keyframe_list': [
                {'time_offset': 0, 'values': [-.65]}, {'time_offset': 500000, 'values': [.45]}]}]
            (self.source / 'draft_content.json').write_bytes(b'committed first edit')
            return {'result': {'err_code': 0}}
        raise RuntimeError('official second action rejected')

    def run_plan(self, edits):
        path = self.work / 'plan.json'
        path.write_text(json.dumps({'schema': actions.SCHEMA, 'draft_dir': str(self.source), 'actions': edits}), 'utf8')
        return actions.run(path, self.work / 'audit')

    def test_preflight_invalid_later_action_prevents_all_mutations(self):
        with self.assertRaises(ValueError):
            self.run_plan([position(), {'op': 'delete-everything', 'segment_id': 'video-id'}])
        self.assertEqual(self.calls, [])
        self.assertFalse((self.work / 'audit').exists())

    def test_partial_failure_keeps_before_snapshot_and_stops_remaining_actions(self):
        report = self.run_plan([position(), {'op': 'video.speed', 'segment_id': 'video-id', 'speed': 1.5}, position()])
        self.assertEqual(report['status'], 'failed'); self.assertEqual(report['completed_count'], 1)
        self.assertFalse(report['atomic']); self.assertEqual(len(self.calls), 2)
        self.assertEqual((self.work / 'audit/before/draft_content.json').read_bytes(), b'original encrypted draft bytes')
        self.assertEqual((self.source / 'draft_content.json').read_bytes(), b'committed first edit')
        self.assertTrue((self.work / 'audit/step-001.official.json').is_file())
        self.assertTrue((self.work / 'audit/step-001.timeline.json').is_file())

    def test_success_requires_readback_and_does_not_claim_export(self):
        report = self.run_plan([position()])
        self.assertEqual(report['status'], 'applied-and-read-back')
        self.assertEqual(report['export_status'], 'not-tested-by-this-command')
        self.assertEqual(report['completed_count'], 1)

    def test_audit_cannot_be_inside_target_draft(self):
        path = self.work / 'plan.json'
        path.write_text(json.dumps({'schema': actions.SCHEMA, 'draft_dir': str(self.source), 'actions': [position()]}), 'utf8')
        with self.assertRaisesRegex(ValueError, 'separate'):
            actions.run(path, self.source / 'work' / 'audit')
        self.assertEqual(self.calls, [])

    def test_external_change_after_snapshot_stops_before_official_edit(self):
        def concurrent_edit():
            (self.source / 'draft_content.json').write_bytes(b'concurrent GUI save')
        with patch.object(actions.dr, 'ensure_editor_running', side_effect=concurrent_edit):
            report = self.run_plan([position()])
        self.assertEqual(report['status'], 'failed')
        self.assertIn('outside this edit batch', report['error'])
        self.assertEqual(self.calls, [])
        self.assertEqual((self.source / 'draft_content.json').read_bytes(), b'concurrent GUI save')
        self.assertEqual((self.work / 'audit/before/draft_content.json').read_bytes(), b'original encrypted draft bytes')

    def test_successful_envelope_without_native_roundtrip_is_failure(self):
        with patch.object(actions.dr, 'run_lyra', return_value={'result': {'err_code': 0}}):
            report = self.run_plan([position()])
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['completed_count'], 0)
        self.assertEqual(report['steps'][0]['status'], 'failed-or-unverified')
        self.assertTrue((self.work / 'audit/step-001.official.json').is_file())
        self.assertIn('channels', report['error'])


if __name__ == '__main__':
    unittest.main()
