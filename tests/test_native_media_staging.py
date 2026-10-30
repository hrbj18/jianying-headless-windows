"""Repeated clip references share staging work without weakening hash boundaries."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
import media_store
import native_export as export
import windows_native_preview as preview
from runtime_profiles import WINDOWS_1147_PROFILE


class RepeatedMediaStaging(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='jy-stage-once-')
        self.root = Path(self.temporary.name).resolve()
        self.source = self.root / 'saved-draft'
        self.source.mkdir()
        self.original = self.root / 'external.mp4'
        self.payload = b'one original reused by several trims' * 128
        self.original.write_bytes(self.payload)
        self.runtime = {'runtime_profile': WINDOWS_1147_PROFILE, 'app_build': '11.4.7.14462',
                        'app_version': '11.4.7', 'install_dir': str(self.root / 'app')}
        self.pool_patch = patch.object(media_store, 'default_pool', return_value=self.root / 'media-pool')
        self.pool_patch.start()
        self.windows_patch = patch.object(export.j.nd, 'IS_WINDOWS', True)
        self.windows_patch.start()

    def tearDown(self):
        self.windows_patch.stop()
        self.pool_patch.stop()
        for directory, _, names in os.walk(self.root, topdown=False):
            for name in names:
                path = Path(directory) / name
                if path.exists():
                    media_store._unlink(path)
        self.temporary.cleanup()

    def timeline(self, path, count=12):
        return {'id': 'main', 'new_version': '185.0.0', 'version': 360000,
                'duration': count * 1_000_000, 'fps': 30,
                'canvas_config': {'width': 640, 'height': 360},
                'materials': {'videos': [{'id': 'media-' + str(i), 'type': 'video', 'path': str(path)}
                                         for i in range(count)]},
                'tracks': [{'id': 'main-video', 'type': 'video', 'segments': [
                    {'id': 'segment-' + str(i), 'material_id': 'media-' + str(i),
                     'target_timerange': {'start': i * 1_000_000, 'duration': 1_000_000},
                     'source_timerange': {'start': i * 3_000_000, 'duration': 1_000_000}}
                    for i in range(count)]}]}

    def build_fixture(self, count=12):
        build = self.root / 'build'
        folder = build / 'draft'
        media = folder / 'Resources' / 'headless-media' / 'same-source.mp4'
        media.parent.mkdir(parents=True)
        media.write_bytes(self.payload)
        target = self.root / 'future-draft'
        relative = media.relative_to(folder)
        record = {'target': str(target), 'runtime_profile': WINDOWS_1147_PROFILE, 'font_assets': [],
                  'files': {str(relative): {'sha256': export.j.nd.digest(media), 'size': media.stat().st_size}}}
        timeline = self.timeline(target / relative, count)
        (build / 'build.json').write_text(json.dumps(record), encoding='utf-8')
        return build, folder, media, record, timeline

    def test_saved_draft_repeated_trims_materialize_once_per_snapshot_layer(self):
        timeline = self.timeline(self.original)
        before = deepcopy(timeline)
        job = self.root / 'job'
        job.mkdir()
        dependencies = {}
        with patch.object(media_store, 'materialize_immutable', wraps=media_store.materialize_immutable) as materialize:
            staged, files = export.stage_draft_timeline(timeline, self.source, job, self.runtime, dependencies)
        # A saved draft has two distinct destinations: frozen source snapshot,
        # then the renderer workspace. Each receives one actual hard link.
        self.assertEqual(materialize.call_count, 2)
        destinations = [Path(call.args[1]) for call in materialize.call_args_list]
        self.assertEqual(sum(path.is_relative_to(job / 'source-snapshot') for path in destinations), 1)
        self.assertEqual(len(files), 1)
        self.assertEqual(len(dependencies), 1)
        paths = {node['path'] for node in staged['materials']['videos']}
        self.assertEqual(len(paths), 1)
        self.assertEqual(Path(next(iter(paths))).read_bytes(), self.payload)
        self.assertEqual(timeline, before)
        self.assertEqual(staged['tracks'], before['tracks'])
        self.assertEqual(self.original.read_bytes(), self.payload)

    def test_build_repeated_trims_materialize_only_once(self):
        _, folder, media, record, timeline = self.build_fixture()
        job = self.root / 'job'
        job.mkdir()
        before = deepcopy(timeline)
        with patch.object(media_store, 'materialize_immutable', wraps=media_store.materialize_immutable) as materialize:
            staged, files = export.stage_timeline(timeline, record, folder, job, self.runtime)
        self.assertEqual(materialize.call_count, 1)
        self.assertEqual(len(files), 1)
        self.assertEqual(len({n['path'] for n in staged['materials']['videos']}), 1)
        self.assertEqual(staged['tracks'], before['tracks'])
        self.assertEqual(timeline, before)
        self.assertEqual(media.read_bytes(), self.payload)

    def test_changed_fingerprint_on_a_repeated_reference_is_still_rejected(self):
        self._check_changed_repeated_fingerprint(update_record=False,
                                                message='differs from the verified build manifest')

    def test_changed_cached_fingerprint_is_rejected_even_if_record_is_also_modified(self):
        self._check_changed_repeated_fingerprint(update_record=True,
                                                message='Repeated dependency fingerprint differs')

    def _check_changed_repeated_fingerprint(self, *, update_record, message):
        _, folder, media, record, timeline = self.build_fixture(count=2)
        job = self.root / 'job'
        job.mkdir()
        actual_digest = export.j.nd.digest
        source_reads = 0

        def concurrent_change(path):
            nonlocal source_reads
            if Path(path) == media:
                source_reads += 1
                # First reference: source fingerprint, then post-copy check.
                # Change bytes immediately before the second reference is checked.
                if source_reads == 3:
                    media.write_bytes(b'Z' * len(self.payload))
                    if update_record:
                        record['files'][str(media.relative_to(folder))] = {
                            'sha256': actual_digest(media), 'size': media.stat().st_size}
            return actual_digest(path)

        with patch.object(export.j.nd, 'digest', side_effect=concurrent_change), \
                patch.object(media_store, 'materialize_immutable', wraps=media_store.materialize_immutable) as materialize, \
                self.assertRaisesRegex(ValueError, message):
            export.stage_timeline(timeline, record, folder, job, self.runtime)
        self.assertEqual(materialize.call_count, 1)

    def test_preview_final_source_check_catches_same_size_change_after_cached_staging(self):
        value = self.timeline(self.original)
        (self.source / 'draft_content.json').write_text(json.dumps(value), encoding='utf-8')
        helper = SimpleNamespace(_decrypt_metadata_in_memory=export.j.read_json)
        with patch.object(export.j.nd, 'helper', return_value=helper):
            _, _, _, _, stage, unchanged = preview.prepare_source(self.runtime, draft_dir=self.source)
        job = self.root / 'job'
        job.mkdir()
        with patch.object(media_store, 'materialize_immutable', wraps=media_store.materialize_immutable) as materialize:
            staged, _ = stage(job)
        self.assertEqual(materialize.call_count, 2)
        unchanged()
        self.original.write_bytes(b'Z' * len(self.payload))
        with self.assertRaisesRegex(ValueError, 'media/font changed'):
            unchanged()
        self.assertEqual(Path(staged['materials']['videos'][0]['path']).read_bytes(), self.payload)

    def test_export_final_source_check_catches_media_and_saved_timeline_changes(self):
        value = self.timeline(self.original)
        saved_timeline = self.source / 'draft_content.json'
        saved_timeline.write_text(json.dumps(value), encoding='utf-8')
        helper = SimpleNamespace(_decrypt_metadata_in_memory=export.j.read_json)

        def inspect_render_boundary(source, out, timeline, record, runtime, evidence,
                                    stage_source, verify_source, unchanged_key, bitrate, timeout):
            out = Path(out)
            out.mkdir()
            staged, _ = stage_source(out)
            verify_source()
            self.original.write_bytes(b'Z' * len(self.payload))
            with self.assertRaisesRegex(ValueError, 'media changed during export'):
                verify_source()
            self.original.write_bytes(self.payload)
            verify_source()
            saved_timeline.write_bytes(b'concurrent saved timeline edit')
            with self.assertRaisesRegex(ValueError, 'Source draft changed during export'):
                verify_source()
            self.assertEqual(Path(staged['materials']['videos'][0]['path']).read_bytes(), self.payload)
            return {'status': 'test-only-boundary-inspection', 'native_started': False}

        with patch.object(export.j.nd, 'helper', return_value=helper), \
                patch.object(export.j.nd, 'validate_runtime', return_value=self.runtime), \
                patch.object(export, '_run_export', side_effect=inspect_render_boundary):
            result = export.run_draft(self.source, self.root / 'export-job')
        self.assertFalse(result['native_started'])

    def test_build_preview_final_check_keeps_full_manifest_and_record_boundaries(self):
        build, folder, media, record, timeline = self.build_fixture()
        with patch.object(export, 'verified_build', return_value=(build, record, timeline)), \
                patch.object(export, 'windows_build_supported_features', return_value={}):
            _, _, _, _, stage, unchanged = preview.prepare_source(self.runtime, build=build)
        job = self.root / 'job'
        job.mkdir()
        stage(job)
        unchanged()
        media.write_bytes(b'Z' * len(self.payload))
        with self.assertRaisesRegex(ValueError, 'Source build changed during preview'):
            unchanged()
        media.write_bytes(self.payload)
        unchanged()
        (build / 'build.json').write_bytes(b'a changed build record')
        with self.assertRaisesRegex(ValueError, 'Source build changed during preview'):
            unchanged()


if __name__ == '__main__':
    unittest.main()
