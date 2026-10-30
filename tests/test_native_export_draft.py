"""Ordinary saved drafts use the same isolated native-export contract."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'engine'))
import native_export as export
from runtime_profiles import WINDOWS_1147_PROFILE


class SavedDraftExportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='draft-export-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        pool_patch = patch.object(export.media_store, 'default_pool', return_value=self.root / 'media-pool')
        pool_patch.start()
        self.addCleanup(pool_patch.stop)
        self.source = self.root / 'draft'
        self.source.mkdir()
        self.runtime = {'runtime_profile': WINDOWS_1147_PROFILE,
                        'app_version': '11.4.7', 'install_dir': str(self.root / 'app')}
        self.timeline = {'id': 'main', 'new_version': '185.0.0', 'version': 360000,
                         'duration': 1_000_000, 'canvas_config': {'width': 640, 'height': 360},
                         'materials': {'videos': [{'id': 'media', 'type': 'video'}]},
                         'tracks': [{'id': 'track', 'type': 'video', 'segments': [
                             {'id': 'segment', 'material_id': 'media',
                              'target_timerange': {'start': 0, 'duration': 1_000_000}}]}]}

    def save(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding='utf-8')

    def test_selects_declared_main_timeline_without_modifying_stale_root(self):
        old = deepcopy(self.timeline)
        old['duration'] = 2_000_000
        self.save(self.source / 'draft_content.json', old)
        self.save(self.source / 'Timelines/main/draft_content.json', self.timeline)
        self.save(self.source / 'Timelines/project.json',
                  {'main_timeline_id': 'main', 'timelines': [{'id': 'main'}]})
        before = export.j.files_manifest(self.source)
        helper = SimpleNamespace(_decrypt_metadata_in_memory=export.j.read_json)
        with patch.object(export.j.nd, 'helper', return_value=helper):
            source, snapshot, timeline, evidence = export.read_draft(self.source, self.runtime)
        self.assertEqual(timeline['duration'], 1_000_000)
        self.assertTrue(evidence['root_mirror_differs'])
        self.assertEqual(evidence['source_timeline'], str(Path('Timelines/main/draft_content.json')))
        self.assertEqual(snapshot, before)
        self.assertEqual(export.j.files_manifest(source), before)

    def test_rejects_ambiguous_multiple_timelines_without_project(self):
        for name in ('first', 'second'):
            self.save(self.source / 'Timelines' / name / 'draft_content.json', self.timeline)
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            export.read_draft(self.source, self.runtime)

    def test_stages_external_local_media_without_changing_source_timeline(self):
        original = self.root / '外部素材.mp4'
        original.write_bytes(b'media bytes for isolated-copy test')
        self.timeline['materials']['videos'][0]['path'] = str(original)
        before = deepcopy(self.timeline)
        out = self.root / 'export'
        out.mkdir()
        dependencies = {}
        staged, files = export.stage_draft_timeline(self.timeline, self.source, out,
                                                    self.runtime, dependencies)
        copied = Path(staged['materials']['videos'][0]['path'])
        self.assertTrue(copied.is_relative_to(out))
        self.assertEqual(copied.read_bytes(), original.read_bytes())
        self.assertEqual(self.timeline, before)
        self.assertEqual(files[str(copied.relative_to(out))], dependencies[str(original)])

    def test_unstaged_resource_and_online_paths_are_rejected(self):
        for extra in ({'mystery_path': str(self.root / 'unknown.bin')},
                      {'resource_url': 'https://example.invalid/asset'}):
            with self.subTest(extra=extra):
                out = self.root / ('case-' + next(iter(extra)))
                out.mkdir()
                value = deepcopy(self.timeline)
                value.update(extra)
                with self.assertRaisesRegex(ValueError, 'Unstaged|Online'):
                    export.stage_draft_timeline(value, self.source, out, self.runtime, {})

    def test_fps_defaults_to_30_and_runtime_scope_uses_actual_version(self):
        self.assertEqual(export.settings_for(self.timeline, 4_000_000, 60)['fps'], 30)
        features = export.windows_supported_features(self.timeline, {}, self.runtime)
        self.assertIn('11.4.7', features['content_scope'])
        self.assertNotIn('11.5', features['content_scope'])

    def test_official_implicit_canvas_uses_unique_video_dimensions_without_mutating_source(self):
        self.timeline['canvas_config'] = {}
        self.timeline['materials']['videos'][0].update(width=640, height=360)
        before = deepcopy(self.timeline)
        value, origin = export.draft_export_canvas(self.timeline)
        self.assertEqual(value['canvas_config'], {'width': 640, 'height': 360})
        self.assertEqual(origin, 'unique used video dimensions')
        self.assertEqual(self.timeline, before)

    def test_ambiguous_canvas_requires_explicit_dimensions_and_keeps_saved_canvas(self):
        self.assertEqual(export.draft_export_canvas(self.timeline), (self.timeline, 'saved canvas'))
        self.timeline['canvas_config'] = {}
        self.timeline['materials']['videos'][0].update(width=640, height=360)
        self.timeline['materials']['videos'].append({'id': 'second', 'width': 360, 'height': 640})
        self.timeline['tracks'][0]['segments'].append({'material_id': 'second'})
        with self.assertRaisesRegex(ValueError, 'unambiguous'):
            export.draft_export_canvas(self.timeline)
        with self.assertRaisesRegex(ValueError, 'both'):
            export.draft_export_canvas(self.timeline, width=1920)
        value, origin = export.draft_export_canvas(self.timeline, width=1920, height=1080)
        self.assertEqual(value['canvas_config'], {'width': 1920, 'height': 1080})
        self.assertEqual(origin, 'explicit export dimensions')

    def test_generated_platform_metadata_uses_discovered_version(self):
        blueprint = {'timeline': {'platform': {'app_version': 'blueprint provenance'}}}
        original = deepcopy(blueprint)
        plan = {'canvas': {'width': 640, 'height': 360, 'fps': 30}, 'tracks': []}
        with patch.object(export.j.nd, 'IS_WINDOWS', True):
            value, _ = export.j.timeline_for(plan, {}, self.source, 'new', blueprint, {}, self.runtime)
        self.assertEqual(value['platform']['app_version'], '11.4.7')
        self.assertEqual(value['last_modified_platform']['app_version'], '11.4.7')
        self.assertEqual(blueprint, original)

    def test_windows_plain_text_omits_crashing_empty_animation_binding(self):
        blueprint = export.j.blueprint()
        original = deepcopy(blueprint)
        plan = {'canvas': {'width': 640, 'height': 360, 'fps': 30},
                'tracks': [{'type': 'text', 'segments': [
                    {'text': 'Windows native text', 'duration_us': 1_000_000}]}]}
        for windows in (True, False):
            with self.subTest(windows=windows), patch.object(export.j.nd, 'IS_WINDOWS', windows):
                value, _ = export.j.timeline_for(plan, {}, self.source, 'new', blueprint, {}, self.runtime)
            animation_ids = {node['id'] for node in value['materials']['material_animations']}
            refs = value['tracks'][0]['segments'][0].get('extra_material_refs', [])
            self.assertEqual(bool(animation_ids.intersection(refs)), not windows)
        self.assertEqual(blueprint, original)

    def test_windows_export_rejects_existing_text_animation_bindings_before_native_init(self):
        value = deepcopy(self.timeline)
        value['materials']['material_animations'] = [{'id': 'empty-animation', 'type': 'sticker_animation'}]
        value['tracks'].append({'type': 'text', 'segments': [{'extra_material_refs': ['empty-animation']}]})
        with self.assertRaisesRegex(ValueError, '空占位'):
            export.windows_supported_features(value, {}, self.runtime)


if __name__ == '__main__':
    unittest.main()
