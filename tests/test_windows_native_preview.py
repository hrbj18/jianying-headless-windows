"""VEF1 boundaries and preview staging; these tests never start native services."""
from copy import deepcopy
import json
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zlib

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'engine'))
import windows_native_preview as preview
from runtime_profiles import WINDOWS_1147_PROFILE, WINDOWS_PROFILE


def packet(*, magic=b'VEF1', version=1, header=40, width=16, height=16, stride=64,
           pixel_format=1, timestamp=1_000_000, sequence=3, payload=None):
    if payload is None:
        payload = b'\x11\x22\x33\xff' * (stride // 4) * height
    return preview.HEADER.pack(magic, version, header, width, height, stride, pixel_format, timestamp, sequence) + payload


def timeline():
    return {'id': 'timeline', 'new_version': '185.0.0', 'version': 360000, 'duration': 3_000_000,
            'fps': 30, 'canvas_config': {'width': 640, 'height': 360},
            'materials': {'videos': [{'id': 'media', 'type': 'video'}]},
            'tracks': [{'id': 'track', 'type': 'video', 'segments': [
                {'id': 'segment', 'material_id': 'media', 'target_timerange': {'duration': 3_000_000}}]}]}


class FramePackets(unittest.TestCase):
    def test_exact_header_and_pixels_roundtrip_with_padded_rows(self):
        data = packet(stride=68)
        info, rgba = preview.parse_packet(data, 16, 16, 1_000_000, 33334)
        self.assertEqual(len(rgba), 16 * 16 * 4)
        self.assertEqual(info['sequence'], 3)
        self.assertEqual(info['timestamp_error_us'], 0)
        self.assertEqual(rgba, b'\x11\x22\x33\xff' * 16 * 16)

    def test_rejects_invalid_or_unsupported_packet_contract(self):
        cases = [packet(magic=b'BAD!'), packet(version=2), packet(header=44), packet(width=17),
                 packet(pixel_format=2), packet(stride=60), packet(stride=66),
                 packet(payload=b'\0' * 5), b'VEF1', packet() + b'\0']
        for data in cases:
            with self.subTest(bytes=len(data)), self.assertRaises(ValueError):
                preview.parse_packet(data, 16, 16, 1_000_000, 33334)

    def test_timestamp_tolerance_is_bounded_by_one_frame(self):
        preview.parse_packet(packet(timestamp=1_033_334), 16, 16, 1_000_000, 33334)
        with self.assertRaises(preview.FrameNotAtTarget):
            preview.parse_packet(packet(timestamp=1_033_335), 16, 16, 1_000_000, 33334)
        with self.assertRaises(preview.FrameNotAtTarget):
            preview.parse_packet(packet(timestamp=0), 16, 16, 1_000_000, 33334)

    def test_png_has_valid_crc_dimensions_and_rgba_scanlines(self):
        rgba = b'\x11\x22\x33\xff' * 16 * 16
        data = preview.png_bytes(16, 16, rgba)
        self.assertEqual(data[:8], b'\x89PNG\r\n\x1a\n')
        offset = 8; chunks = {}
        while offset < len(data):
            size = struct.unpack_from('>I', data, offset)[0]
            kind = data[offset + 4:offset + 8]; payload = data[offset + 8:offset + 8 + size]
            crc = struct.unpack_from('>I', data, offset + 8 + size)[0]
            self.assertEqual(crc, zlib.crc32(kind + payload) & 0xffffffff)
            chunks[kind] = payload; offset += size + 12
        self.assertEqual(struct.unpack('>IIBBBBB', chunks[b'IHDR']), (16, 16, 8, 6, 0, 0, 0))
        self.assertEqual(zlib.decompress(chunks[b'IDAT']), (b'\0' + rgba[:64]) * 16)
        with self.assertRaises(ValueError):
            preview.png_bytes(16, 16, rgba[:-1])

    def test_settings_reject_invalid_time_and_excessive_dimensions(self):
        self.assertEqual(preview.preview_settings(timeline(), [0, 1.5])['height'], 540)
        for at in ([], [3], [float('nan')], [-.1], [True], [0, 0]):
            with self.subTest(at=at), self.assertRaises(ValueError):
                preview.preview_settings(timeline(), at)
        with self.assertRaises(ValueError):
            preview.preview_settings(timeline(), [0], 1920, 1920)
        portrait = timeline(); portrait['canvas_config'] = {'width': 1080, 'height': 1920}
        self.assertEqual(preview.preview_settings(portrait, [0])['height'], 1707)

    def test_player_load_uses_compact_json_without_changing_schema_or_user_text(self):
        value = timeline(); value['caption'] = '中文标题\n换行'
        before = deepcopy(value)
        params = preview.player_load_params(value, Path('C:/work/preview'))
        self.assertEqual(json.loads(params['draftJson']), before)
        self.assertNotIn('\n', params['draftJson'])
        self.assertEqual(value, before)
        self.assertEqual(json.loads(params['draftJson'])['new_version'], '185.0.0')


class RuntimeAndStaging(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='native-preview-test-'); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        pool_patch = patch.object(preview.native.media_store, 'default_pool', return_value=self.root / 'media-pool')
        pool_patch.start()
        self.addCleanup(pool_patch.stop)
        self.runtime = {'runtime_profile': WINDOWS_1147_PROFILE, 'app_build': '11.4.7.14462',
                        'app_version': '11.4.7', 'install_dir': str(self.root / 'app')}

    def test_exact_profile_and_all_component_hashes_are_required(self):
        install = Path(self.runtime['install_dir'])
        for name in preview.SERVICE_PINS:
            path = install / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'official component')
        def digest(path):
            return preview.SERVICE_PINS[Path(path).relative_to(install).as_posix()]
        with patch.object(preview._j.nd, 'IS_WINDOWS', True), patch.object(preview._j.nd, 'digest', side_effect=digest):
            self.assertEqual(len(preview.verify_service(self.runtime)), 4)
            with self.assertRaisesRegex(ValueError, 'exact Windows'):
                preview.verify_service({**self.runtime, 'runtime_profile': WINDOWS_PROFILE, 'app_build': '11.5.0.14471'})
        with patch.object(preview._j.nd, 'IS_WINDOWS', True), patch.object(preview._j.nd, 'digest', return_value='0' * 64):
            with self.assertRaisesRegex(ValueError, 'fingerprint changed'):
                preview.verify_service(self.runtime)

    def test_external_draft_media_are_copied_and_original_change_is_detected(self):
        source = self.root / '中文工程'; source.mkdir()
        original = self.root / '中文素材.mp4'; original.write_bytes(b'local original media')
        value = timeline(); value['materials']['videos'][0]['path'] = str(original)
        (source / 'draft_content.json').write_text(json.dumps(value), 'utf8')
        helper = SimpleNamespace(_decrypt_metadata_in_memory=preview._j.read_json)
        with patch.object(preview._j.nd, 'helper', return_value=helper):
            actual_source, actual, evidence, capabilities, stage, unchanged = preview.prepare_source(self.runtime, draft_dir=source)
        job = self.root / 'work' / 'preview'; job.mkdir(parents=True)
        staged, files = stage(job)
        copied = Path(staged['materials']['videos'][0]['path'])
        self.assertTrue(copied.is_relative_to(job)); self.assertEqual(copied.read_bytes(), b'local original media')
        self.assertEqual(actual['materials']['videos'][0]['path'], str(original))
        self.assertEqual(actual_source, source); self.assertTrue(files)
        unchanged()
        original.write_bytes(b'concurrent source replacement')
        with self.assertRaisesRegex(ValueError, 'media/font changed'):
            unchanged()
        self.assertEqual(copied.read_bytes(), b'local original media')

    def test_build_profile_mismatch_is_rejected_before_staging(self):
        record = {'runtime_profile': WINDOWS_PROFILE}
        with patch.object(preview.native, 'verified_build', return_value=(self.root, record, timeline())), \
             patch.object(preview.native, 'stage_timeline') as stage:
            with self.assertRaises(ValueError):
                preview.prepare_source(self.runtime, build=self.root)
            stage.assert_not_called()

    def test_client_checks_request_identity_and_does_not_store_base64(self):
        job = self.root / 'work'; job.mkdir()
        client = preview.NativeClient(self.root, r'\\.\pipe\test', job, {}, 10)
        def respond(*args, **kwargs):
            request = json.loads(kwargs['input'])['request']
            return SimpleNamespace(returncode=0, stdout=json.dumps({'id': request['id'], 'protocolVersion': 1,
                'ok': True, 'result': {'ready': True}}), stderr='')
        with patch.object(preview.subprocess, 'run', side_effect=respond):
            self.assertTrue(client.invoke('system', 'health')['result']['ready'])
        self.assertNotIn('packetBase64', (job / 'ipc-001.json').read_text('utf8'))
        with patch.object(preview.subprocess, 'run', return_value=SimpleNamespace(returncode=0,
                stdout=json.dumps({'id': 'wrong', 'protocolVersion': 1, 'ok': True}), stderr='')):
            with self.assertRaisesRegex(ValueError, 'identity differs'):
                client.invoke('system', 'health')


if __name__ == '__main__':
    unittest.main()
