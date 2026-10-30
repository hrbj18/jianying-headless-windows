"""Bounded 11.4.7 font/audio-fade export extensions, without a native runtime."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'engine'))
import native_export as export
from runtime_profiles import WINDOWS_1147_PROFILE, WINDOWS_PROFILE


class WindowsExportExtensionTests(unittest.TestCase):
    def setUp(self):
        self.runtime = {'runtime_profile': WINDOWS_1147_PROFILE, 'app_version': '11.4.7',
                        'install_dir': str(ROOT / 'unavailable-test-install')}
        self.record = {'runtime_profile': WINDOWS_1147_PROFILE, 'runtime': self.runtime}
        self.timeline = {'materials': {
            'audios': [{'id': 'music', 'type': 'music'}],
            'audio_fades': [{'id': 'fade', 'type': 'audio_fade', 'fade_type': 4,
                             'fade_in_duration': 500_000, 'fade_out_duration': 800_000}]},
            'tracks': [{'type': 'audio', 'segments': [{'material_id': 'music',
                        'extra_material_refs': ['fade'], 'target_timerange': {'duration': 4_000_000}}]}]}

    def features(self, timeline=None, record=None, runtime=None):
        return export.windows_supported_features(timeline or self.timeline,
                                                   record or self.record, runtime or self.runtime)

    def test_observed_bound_fade_preserves_input_and_reports_scope(self):
        before = deepcopy(self.timeline)
        result = self.features()
        self.assertEqual(result['audio_fade_materials'], 1)
        self.assertIn('type 4', result['content_scope'])
        self.assertEqual(self.timeline, before)

    def test_other_profiles_cannot_gain_fades(self):
        for profile in (WINDOWS_PROFILE, 'unknown', None):
            runtime = dict(self.runtime, runtime_profile=profile)
            with self.subTest(profile=profile), self.assertRaisesRegex(ValueError, '精确 11.4.7'):
                self.features(record=dict(self.record, runtime_profile=profile), runtime=runtime)

    def test_cross_profile_build_runtime_pair_still_rejected(self):
        with self.assertRaisesRegex(ValueError, 'differs'):
            self.features(runtime=dict(self.runtime, runtime_profile=WINDOWS_PROFILE))

    def test_global_feature_gate_does_not_gain_windows_fades(self):
        with self.assertRaisesRegex(ValueError, 'audio_fades'):
            export.supported_features(self.timeline)

    def test_unknown_fade_fields_and_types_remain_blocked(self):
        for update in ({'unknown': 0}, {'type': 'audio_effect'}, {'fade_type': 3}, {'fade_type': True}):
            changed = deepcopy(self.timeline)
            changed['materials']['audio_fades'][0].update(update)
            with self.subTest(update=update), self.assertRaisesRegex(ValueError, 'Unverified audio fade'):
                self.features(changed)

    def test_fade_durations_reject_bool_float_negative_and_unbounded(self):
        for value in (True, .5, -1, 43_200_000_001, float('nan')):
            changed = deepcopy(self.timeline)
            changed['materials']['audio_fades'][0]['fade_in_duration'] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'duration'):
                self.features(changed)

    def test_fade_durations_must_fit_without_overlap(self):
        changed = deepcopy(self.timeline)
        changed['materials']['audio_fades'][0]['fade_in_duration'] = 3_500_000
        with self.assertRaisesRegex(ValueError, 'without overlap'):
            self.features(changed)

    def test_zero_duration_edges_are_safe_bounded_values(self):
        self.timeline['materials']['audio_fades'][0].update(fade_in_duration=0, fade_out_duration=0)
        self.assertEqual(self.features()['audio_fade_materials'], 1)

    def test_orphan_fade_and_missing_reference_are_rejected(self):
        self.timeline['tracks'][0]['segments'][0]['extra_material_refs'] = []
        with self.assertRaisesRegex(ValueError, 'no valid segment reference'):
            self.features()

    def test_primary_fade_and_video_fade_bindings_are_rejected(self):
        changed = deepcopy(self.timeline)
        changed['tracks'][0]['segments'][0]['material_id'] = 'fade'
        with self.assertRaisesRegex(ValueError, 'primary'):
            self.features(changed)
        changed = deepcopy(self.timeline)
        changed['tracks'][0]['type'] = 'video'
        with self.assertRaisesRegex(ValueError, 'audio segment'):
            self.features(changed)

    def test_duplicate_material_ids_or_segment_references_are_rejected(self):
        changed = deepcopy(self.timeline)
        changed['materials']['audio_fades'].append(deepcopy(changed['materials']['audio_fades'][0]))
        with self.assertRaisesRegex(ValueError, 'unique'):
            self.features(changed)
        changed = deepcopy(self.timeline)
        changed['tracks'][0]['segments'][0]['extra_material_refs'] *= 2
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            self.features(changed)

    def test_static_font_inventory_only_for_exact_profile(self):
        record = dict(self.record, font_assets=[{'relative': 'Resources/headless-fonts/a.ttf',
                                               'sha256': 'a' * 64, 'size': 123, 'format': 'ttf'}])
        self.assertTrue(self.features(record=record)['static_local_fonts'])
        for profile in (WINDOWS_PROFILE, 'unknown'):
            with self.subTest(profile=profile), self.assertRaisesRegex(ValueError, '精确 11.4.7'):
                self.features(record=dict(record, runtime_profile=profile),
                              runtime=dict(self.runtime, runtime_profile=profile))
        record['font_assets'][0]['format'] = 'variable-ttf'
        with self.assertRaisesRegex(ValueError, '静态 TTF/OTF'):
            self.features(record=record)

    def test_unknown_materials_and_canvas_blur_still_fail_closed(self):
        changed = deepcopy(self.timeline)
        changed['materials']['mystery_effects'] = [{'id': 'unknown'}]
        with self.assertRaisesRegex(ValueError, 'mystery_effects'):
            self.features(changed)
        changed = deepcopy(self.timeline)
        changed['materials']['canvases'] = [{'id': 'canvas', 'type': 'canvas_blur'}]
        with self.assertRaisesRegex(ValueError, 'solid canvas'):
            self.features(changed)

    @unittest.skipUnless(Path(r'C:\Windows\Fonts\arial.ttf').is_file(), 'real static Windows test font unavailable')
    def test_saved_font_snapshot_remaps_outer_and_serialized_paths_without_source_changes(self):
        with tempfile.TemporaryDirectory(prefix='font-snapshot-') as temporary:
            root = Path(temporary).resolve()
            source, out = root / 'draft', root / 'export'
            source.mkdir(); out.mkdir()
            font = Path(r'C:\Windows\Fonts\arial.ttf')
            timeline = {'materials': {'texts': [{'id': 'text', 'type': 'text', 'font_path': str(font),
                'content': json.dumps({'text': 'Font snapshot', 'styles': [{'font': {'id': '', 'path': str(font)}}]})}]},
                'tracks': []}
            before = deepcopy(timeline); dependencies = {}
            with patch.object(export.j.nd, 'IS_WINDOWS', True):
                staged, files = export.stage_draft_timeline(timeline, source, out, self.runtime, dependencies)
            material = staged['materials']['texts'][0]
            copied = Path(material['font_path'])
            self.assertTrue(copied.is_relative_to(out))
            self.assertTrue(copied.is_file())
            self.assertEqual(copied.read_bytes(), font.read_bytes())
            self.assertEqual(json.loads(material['content'])['styles'][0]['font']['path'], str(copied))
            self.assertIn(str(font), dependencies)
            self.assertIn(str(copied.relative_to(out)), files)
            self.assertEqual(timeline, before)


if __name__ == '__main__':
    unittest.main()
