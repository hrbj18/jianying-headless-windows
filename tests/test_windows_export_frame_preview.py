"""Fog preview must use native player VEF1, never an encoded-video fallback.

All process and IPC boundaries are simulated, without a machine installation.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
import windows_native_preview as preview
from runtime_profiles import WINDOWS_1147_PROFILE


class FogNativePlayerPreview(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='jy-player-preview-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.source = self.root / 'source'; self.source.mkdir()
        self.job = self.root / 'work' / 'preview'
        self.runtime = {'runtime_profile': WINDOWS_1147_PROFILE, 'app_build': '11.4.7.14462',
                        'install_dir': str(self.root / 'reviewed-app')}
        self.timeline = {'id': 'timeline', 'duration': 1_000_000, 'fps': 30,
                         'canvas_config': {'width': 16, 'height': 16}, 'materials': {}, 'tracks': []}
        self.staged = deepcopy(self.timeline); self.files = {}
        self.caps = {'windows_vfx': {'resource_keys': ['transition/fog-compat']}}
        self.stage = Mock(return_value=(self.staged, self.files))
        self.upgrade = Mock(return_value=(self.staged, self.files, []))
        self.unchanged = Mock(name='source_integrity_check')
        self.pixels = b'\x40\x80\xc0\xff' * 16 * 16
        self.service = SimpleNamespace(pid=43210, returncode=None)
        self.service.poll = Mock(side_effect=lambda: self.service.returncode)
        self.service.wait = Mock(side_effect=self.wait)
        self.service.terminate = Mock(side_effect=self.terminate)
        self.service.kill = Mock(side_effect=self.kill)
        self.popen = Mock(return_value=self.service)
        self.client = SimpleNamespace(invoke=Mock(side_effect=self.invoke))
        self.client_factory = Mock(return_value=self.client)
        self.health_pid = self.service.pid; self.shutdown_pid = self.service.pid
        self.position = 0; self.capture_count = 0; self.capture_times = []
        self.packet_magic = b'VEF1'; self.capture_error = None; self.destroy_error = None
        self.capture_state = 'ready'
        self.renderer = Mock(side_effect=AssertionError('Preview must not invoke ExportService'))
        self.process_run = Mock(side_effect=AssertionError('Preview must not decode or compose via FFmpeg'))
        self.prepared = (self.source, self.timeline, {'source_draft': str(self.source)},
                         self.caps, self.stage, self.unchanged)
        for item in [patch.object(preview, 'configure_environment'),
                     patch.object(preview._j.nd, 'validate_runtime', return_value=self.runtime),
                     patch.object(preview, 'verify_service', return_value={'component': 'reviewed'}),
                     patch.object(preview, 'prepare_source', return_value=self.prepared),
                     patch.object(preview, 'upgrade_preview_resources', self.upgrade, create=True),
                     patch.object(preview._j.nd, 'DRAFT_ROOT', self.root / 'live-drafts'),
                     patch.object(preview.native, '_run_export', self.renderer),
                     patch.object(preview.subprocess, 'run', self.process_run),
                     patch.object(preview.subprocess, 'Popen', self.popen),
                     patch.object(preview, 'NativeClient', self.client_factory),
                     patch.object(preview.time, 'sleep')]:
            item.start(); self.addCleanup(item.stop)

    def wait(self, **_):
        if self.service.returncode is None:
            self.service.returncode = 0
        return self.service.returncode

    def terminate(self):
        self.service.returncode = -15

    def kill(self):
        self.service.returncode = -9

    def invoke(self, domain, operation, params=None, target=None, packet=None, check=True):
        response = {'ok': True, 'result': {'accepted': True}}
        if (domain, operation) == ('system', 'health'):
            response['result'] = {'ready': True, 'pid': self.health_pid}
        elif (domain, operation) == ('player', 'create'):
            self.assertEqual(params, {'kind': 'draft', 'serviceGeneration': 1})
            response['result'] = {'sessionId': 'owned-player', 'kind': 'draft'}
        elif (domain, operation) == ('player', 'load'):
            self.assertEqual(target, 'owned-player')
            self.assertEqual(json.loads(params['draftJson']), self.staged)
            self.assertNotIn('\n', params['draftJson'])
        elif (domain, operation) == ('player', 'getState'):
            status = self.capture_state if self.capture_count else 'ready'
            response['result'] = {'status': status, 'durationUs': self.staged['duration'],
                                  'positionUs': self.position}
        elif (domain, operation) == ('player', 'seek'):
            self.assertEqual(target, 'owned-player'); self.assertEqual(params['seekMode'], 'done')
            self.position = params['positionUs']
        elif (domain, operation) == ('player', 'captureFrame'):
            self.capture_count += 1
            self.assertEqual(target, 'owned-player'); self.assertEqual(params, {'width': 16, 'height': 16})
            self.assertFalse(check)
            if self.capture_error:
                return {'ok': False, 'error': {'code': self.capture_error}}
            timestamp = self.capture_times.pop(0) if self.capture_times else self.position
            data = preview.HEADER.pack(self.packet_magic, 1, 40, 16, 16, 64, 1,
                                       timestamp, self.capture_count) + self.pixels
            Path(packet).write_bytes(data)
            response['result'] = {'packet': {'bytes': len(data)}}
        elif (domain, operation) == ('player', 'destroy'):
            self.assertEqual(target, 'owned-player')
            if self.destroy_error:
                raise ValueError(self.destroy_error)
        elif (domain, operation) == ('system', 'shutdown'):
            self.assertEqual(params, {'expectedPid': self.service.pid})
            response['result'] = {'pid': self.shutdown_pid}
        else:
            self.fail('Unexpected native preview operation: ' + domain + '.' + operation)
        return response

    def run_preview(self, at=None):
        return preview.run(self.job, [.25] if at is None else at, width=16, height=16,
                           timeout=10, draft_dir=self.source)

    def operations(self):
        return [(call.args[0], call.args[1]) for call in self.client.invoke.call_args_list]

    def assert_no_export_or_decode(self):
        self.renderer.assert_not_called(); self.process_run.assert_not_called()

    def test_fog_normal_entry_returns_direct_player_vef1_png_and_pid_checked_cleanup(self):
        result = self.run_preview()
        self.assertEqual(result['status'], 'native-frames-captured')
        self.assertIn('player.captureFrame', result['renderer'])
        self.assertEqual(result['preview_route'], 'native-player-capture-frame')
        self.assertFalse(result['export_used'])
        self.assertFalse(result.get('lossy_encoded_frame_preview', False))
        self.assertFalse(result['external_frame_decode_and_resize'])
        self.assertFalse(result['desktop_screenshot']); self.assertFalse(result['mouse_keyboard_used'])
        self.assertTrue(result['source_unchanged'])
        self.stage.assert_called_once_with(self.job)
        self.upgrade.assert_called_once_with(self.staged, self.files, self.job)
        self.popen.assert_called_once(); self.client_factory.assert_called_once()
        command = self.popen.call_args.args[0]
        self.assertEqual(Path(command[0]).name, 'bun.exe')
        self.assertTrue(any(str(x).endswith('videoeditor-service.mjs') for x in command))
        for operation in [('player', 'create'), ('player', 'load'), ('player', 'seek'),
                          ('player', 'captureFrame'), ('player', 'destroy'), ('system', 'shutdown')]:
            self.assertIn(operation, self.operations())
        frame = result['frames'][0]
        self.assertEqual((frame['timestamp_us'], frame['requested_us'], frame['timestamp_error_us']),
                         (250000, 250000, 0))
        self.assertEqual(frame['player_state']['status'], 'ready')
        self.assertNotIn('native_export_frame_index', frame)
        info, pixels = preview.parse_packet(Path(frame['packet']).read_bytes(), 16, 16, 250000, 33334)
        self.assertEqual(pixels, self.pixels)
        self.assertEqual(frame['packet_sha256'], info['packet_sha256'])
        png = Path(frame['png']).read_bytes()
        self.assertEqual(png[:8], b'\x89PNG\r\n\x1a\n')
        self.assertEqual(struct.unpack_from('>II', png, 16), (16, 16))
        self.assertEqual(frame['png_sha256'], hashlib.sha256(png).hexdigest())
        self.assertEqual(result['cleanup']['owned_service_pid'], self.service.pid)
        self.assertTrue(result['cleanup']['identity_checked'])
        self.assertTrue(result['cleanup']['player_destroyed'])
        self.assertTrue(result['cleanup']['shutdown_accepted'])
        self.service.terminate.assert_not_called()
        self.assert_no_export_or_decode()

    def test_nonfog_capabilities_use_the_same_player_route(self):
        self.caps['windows_vfx']['resource_keys'] = ['transition/dissolve-compat', 'mask/circle-soft']
        result = self.run_preview()
        self.assertEqual(result['status'], 'native-frames-captured')
        self.assertIn(('player', 'captureFrame'), self.operations())
        self.assert_no_export_or_decode()

    def test_multiple_frames_keep_requested_native_timestamps_and_independent_packets(self):
        result = self.run_preview([.25, .5])
        self.assertEqual(result['status'], 'native-frames-captured')
        self.assertEqual([f['timestamp_us'] for f in result['frames']], [250000, 500000])
        self.assertEqual(len({f['packet'] for f in result['frames']}), 2)
        stored = json.loads((self.job / 'preview.json').read_text(encoding='utf-8'))
        self.assertEqual(stored['frames'], result['frames'])
        self.assert_no_export_or_decode()

    def test_stale_packet_retries_until_requested_timestamp_arrives(self):
        self.capture_times = [150000, 250000]
        result = self.run_preview()
        self.assertEqual(result['status'], 'native-frames-captured')
        self.assertEqual(self.capture_count, 2)
        self.assertEqual(result['frames'][0]['attempt'], 2)
        self.assertEqual(result['frames'][0]['timestamp_us'], 250000)
        self.assertTrue((self.job / 'frame-000-attempt-00.packet').exists())
        self.assert_no_export_or_decode()

    def test_permanently_stale_packets_fail_without_export_fallback(self):
        self.capture_times = [150000] * 12
        result = self.run_preview()
        self.assertEqual(result['status'], 'failed')
        self.assertIn('requested timestamp', result['error'])
        self.assertEqual(result['frames'], [])
        self.assertEqual(self.capture_count, 12)
        self.assertTrue(result['cleanup']['shutdown_accepted'])
        self.assert_no_export_or_decode()

    def test_bad_vef1_packet_stops_before_png_and_still_cleans_up_player(self):
        self.packet_magic = b'BAD!'
        result = self.run_preview()
        self.assertEqual(result['status'], 'failed')
        self.assertIn('VEF1', result['error'])
        self.assertFalse((self.job / 'frame-000.png').exists())
        self.assertTrue(result['cleanup']['player_destroyed'])
        self.assertTrue(result['cleanup']['shutdown_accepted'])
        self.assert_no_export_or_decode()

    def test_unexpected_capture_error_is_not_retried_through_export_or_ffmpeg(self):
        self.capture_error = 'native_error'
        result = self.run_preview()
        self.assertEqual(result['status'], 'failed')
        self.assertIn('Native frame capture failed', result['error'])
        self.assertEqual(self.capture_count, 1); self.assertEqual(result['frames'], [])
        self.assert_no_export_or_decode()

    def test_playing_state_after_capture_is_rejected_as_unpaused(self):
        self.capture_state = 'playing'
        result = self.run_preview()
        self.assertEqual(result['status'], 'failed')
        self.assertIn('paused', result['error'])
        self.assertFalse(any(frame.get('player_state') for frame in result['frames']))
        self.assertTrue(result['cleanup']['shutdown_accepted'])
        self.assert_no_export_or_decode()

    def test_source_change_before_service_start_prevents_native_processes(self):
        self.unchanged.side_effect = ValueError('Source draft changed during preview')
        result = self.run_preview()
        self.assertEqual(result['status'], 'failed'); self.assertFalse(result['source_unchanged'])
        self.popen.assert_not_called(); self.client_factory.assert_not_called()
        self.assert_no_export_or_decode()

    def test_source_change_after_capture_marks_failure_and_retains_native_evidence(self):
        checks = 0
        def unchanged():
            nonlocal checks
            checks += 1
            if checks >= 2:
                raise ValueError('Source draft media/font changed during preview')
        self.unchanged.side_effect = unchanged
        result = self.run_preview()
        self.assertEqual(result['status'], 'failed'); self.assertFalse(result['source_unchanged'])
        self.assertIn('media/font changed', result['source_check_error'])
        self.assertTrue((self.job / 'frame-000-attempt-00.packet').exists())
        self.assertTrue((self.job / 'preview.json').exists())
        self.assertTrue(result['cleanup']['shutdown_accepted'])
        self.assert_no_export_or_decode()

    def test_health_pid_mismatch_never_creates_player_or_shuts_down_unknown_peer(self):
        self.health_pid += 1
        result = self.run_preview()
        self.assertEqual(result['status'], 'failed'); self.assertIn('PID differs', result['error'])
        self.assertFalse(result['cleanup']['identity_checked'])
        self.assertNotIn(('player', 'create'), self.operations())
        self.assertNotIn(('system', 'shutdown'), self.operations())
        self.service.terminate.assert_called_once()
        self.assert_no_export_or_decode()

    def test_shutdown_pid_mismatch_retains_diagnostic_and_terminates_only_owned_process(self):
        self.shutdown_pid += 1
        result = self.run_preview()
        self.assertIn('Shutdown service PID differs', result['cleanup']['shutdown_error'])
        self.assertTrue(result['cleanup']['identity_checked'])
        self.assertEqual(result['cleanup']['owned_service_pid'], self.service.pid)
        self.service.terminate.assert_called_once(); self.service.kill.assert_not_called()
        self.assert_no_export_or_decode()

    def test_destroy_failure_does_not_skip_pid_checked_service_shutdown(self):
        self.destroy_error = 'native destroy failed'
        result = self.run_preview()
        self.assertEqual(result['cleanup']['player_destroy_error'], 'native destroy failed')
        self.assertTrue(result['cleanup']['shutdown_accepted'])
        self.service.wait.assert_called_once_with(timeout=10)
        self.assert_no_export_or_decode()

    def test_unreviewed_source_is_rejected_before_player_export_or_decoder(self):
        with patch.object(preview, 'prepare_source', side_effect=ValueError('Unreviewed Windows VFX bytes')):
            with self.assertRaisesRegex(ValueError, 'Unreviewed'):
                self.run_preview()
        self.popen.assert_not_called(); self.client_factory.assert_not_called()
        self.assert_no_export_or_decode()


if __name__ == '__main__':
    unittest.main()
