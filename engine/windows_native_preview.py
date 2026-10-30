"""Capture saved-timeline frames directly through the official native player.

Only an isolated resource-complete snapshot is loaded. No export, video decode,
desktop capture, mouse, keyboard or GUI host process is used for preview.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import time
import uuid
import zlib

import native_export as native
from local_config import configure_environment
from runtime_profiles import WINDOWS_1147_PROFILE, validate_export_profiles

HERE = Path(__file__).resolve().parent
CLIENT = HERE / 'windows_preview_client.mjs'
SCHEMA = 'jy-windows-native-preview/v1'
SERVICE_PINS = {
    'videoeditor_addon.node': 'd9997bc0421a9da9ecafba4835bb8b4c1363de7a8c50e46be81b081766300be9',
    'bun.exe': '27ad10bef00a8a296d66a2983072ed8e824f05e1910dc505dd72b912083689e0',
    'Resources/canvas_agent/runtime/videoeditor-service.mjs': '83a1b2515b3ebac99e6a0d83b8040c361f593cde29a437aa5b1c02e673b2e585',
    'Resources/canvas_agent/runtime/agent-runtime-addon-preload.mjs': '85106d290b0aeb3fe86d5b871a2daa4baa9a88a84e5493c728da87871b59d9e6',
}
HEADER = struct.Struct('<4sHHIIIIQQ')
MAX_PACKET = 12 * 1024 * 1024
_j = native.j


class FrameNotAtTarget(ValueError):
    pass


def verify_service(runtime):
    _j.require(_j.nd.IS_WINDOWS and runtime.get('runtime_profile') == WINDOWS_1147_PROFILE and
               runtime.get('app_build') == '11.4.7.14462',
               'Native preview is reviewed only for exact Windows 11.4.7.14462')
    install = Path(runtime['install_dir'])
    hashes = {}
    for relative, expected in SERVICE_PINS.items():
        path = install / relative
        _j.require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(install.resolve()),
                   'Native preview runtime component is missing: ' + relative)
        actual = _j.nd.digest(path)
        _j.require(actual == expected, 'Native preview runtime component fingerprint changed: ' + relative)
        hashes[relative] = actual
    return hashes


def preview_settings(timeline, at, width=960, height=None):
    _j.require(type(width) is int and 16 <= width <= 1920, 'Preview width must be 16..1920')
    canvas = timeline.get('canvas_config', {})
    cw, ch = canvas.get('width'), canvas.get('height')
    _j.require(type(cw) is int and type(ch) is int and cw > 0 and ch > 0, 'Preview requires an explicit canvas')
    if height is None:
        height = max(16, round(width * ch / cw))
    _j.require(type(height) is int and 16 <= height <= 1920 and min(width, height) <= 1080,
               'Preview dimensions exceed the reviewed CPU-frame limits')
    _j.require(isinstance(at, (list, tuple)) and 1 <= len(at) <= 16, 'Use 1..16 preview times in seconds')
    duration = timeline.get('duration', 0)
    _j.require(type(duration) is int and duration > 0, 'Cannot preview an empty timeline')
    positions = []
    for value in at:
        _j.require(type(value) in (int, float) and math.isfinite(value) and value >= 0,
                   'Preview times must be finite nonnegative seconds')
        micros = round(value * 1_000_000)
        _j.require(micros < duration, 'Preview time is outside the saved timeline')
        _j.require(micros not in positions, 'Preview times must be distinct')
        positions.append(micros)
    fps = timeline.get('fps', 30)
    _j.number(fps, 'Preview fps', 1, 120)
    return {'width': width, 'height': height, 'fps': fps, 'positions_us': positions,
            'timestamp_tolerance_us': math.ceil(1_000_000 / fps)}


def parse_packet(packet, width, height, requested_us, tolerance_us):
    """Validate the VEF1 RGBA8 envelope before consuming native pixel bytes."""
    _j.require(isinstance(packet, bytes) and HEADER.size <= len(packet) <= MAX_PACKET, 'Invalid VEF1 packet size')
    magic, version, header_size, actual_w, actual_h, stride, pixel_format, timestamp, sequence = HEADER.unpack_from(packet)
    _j.require(magic == b'VEF1' and version == 1 and header_size == HEADER.size, 'Unsupported VEF1 header')
    _j.require(type(width) is int and type(height) is int and 16 <= width <= 1920 and 16 <= height <= 1920 and
               min(width, height) <= 1080 and (actual_w, actual_h) == (width, height), 'VEF1 dimensions changed')
    _j.require(pixel_format == 1, 'Unsupported VEF1 pixel format; expected RGBA8')
    _j.require(width * 4 <= stride <= width * 4 + 256 and stride % 4 == 0, 'Invalid VEF1 row stride')
    _j.require(len(packet) == header_size + stride * height, 'VEF1 pixel payload size differs')
    _j.require(type(requested_us) is int and requested_us >= 0 and type(tolerance_us) is int and tolerance_us >= 0,
               'Invalid requested VEF1 timestamp')
    if abs(timestamp - requested_us) > tolerance_us:
        raise FrameNotAtTarget('Native frame timestamp has not reached requested position')
    rgba = b''.join(packet[header_size + y * stride:header_size + y * stride + width * 4] for y in range(height))
    return {'width': width, 'height': height, 'stride': stride, 'pixel_format': 'RGBA8',
            'timestamp_us': timestamp, 'requested_us': requested_us, 'timestamp_error_us': abs(timestamp - requested_us),
            'sequence': sequence, 'packet_sha256': hashlib.sha256(packet).hexdigest()}, rgba


def png_bytes(width, height, rgba):
    _j.require(type(width) is int and type(height) is int and 16 <= width <= 1920 and 16 <= height <= 1920 and
               min(width, height) <= 1080 and isinstance(rgba, bytes) and len(rgba) == width * height * 4,
               'PNG requires bounded RGBA8 pixels')
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    scanlines = b''.join(b'\0' + rgba[y * width * 4:(y + 1) * width * 4] for y in range(height))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(scanlines, 6)) + chunk(b'IEND', b''))


def _save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n', encoding='utf-8')


def upgrade_preview_resources(timeline, files, job):
    """Upgrade only a known fog revision in the isolated player snapshot.

    Saved v2 drafts stay byte-identical. Both the old and replacement packages
    must match complete catalog manifests; no shader, duration or material shape
    is inferred from a resource name. Export retains its original saved resource.
    """
    import windows_vfx as vfx
    from windows_vfx_packaging import _package_files

    value, copied_files, audit = deepcopy(timeline), dict(files), []
    for node in value.get('materials', {}).get('transitions', []):
        entry = vfx.entry_for_node('transitions', node)
        if entry['key'] != 'transition/fog-compat' or not entry.get('legacy_resource'):
            continue
        current = vfx.catalog()['resources'][entry['key']]
        _j.require(current.get('paused_player_supported') is True and
                   current['tree_sha256'] != entry['tree_sha256'],
                   'No reviewed paused-player replacement exists for this fog resource')
        origin = vfx.resource_path(entry['key'])
        destination = job / 'Resources' / 'native-preview-vfx' / current['tree_sha256']
        _package_files(origin, destination, current)
        before = node['path']
        node['path'] = destination.as_posix()
        for relative, info in current['files'].items():
            copied_files[str(destination.relative_to(job) / relative)] = info
        audit.append({'preset': entry['key'], 'material_id': node['id'],
                      'source_tree_sha256': entry['tree_sha256'],
                      'replacement_tree_sha256': current['tree_sha256'],
                      'source_path': before, 'snapshot_path': node['path'],
                      'scope': 'isolated preview snapshot only'})
    return value, copied_files, audit


def player_load_params(timeline, job):
    # The reviewed addon accepted compact JSON; pretty JSON returned accepted
    # but restored a zero-duration/zero-canvas draft. Keep the input schema intact.
    return {'draftJson': json.dumps(timeline, ensure_ascii=False, allow_nan=False, separators=(',', ':')),
            'workspacePath': str(job), 'timelineId': timeline['id']}


def prepare_source(runtime, build=None, draft_dir=None):
    """Share export's immutable source checks and dependency stagers."""
    _j.require((build is None) != (draft_dir is None), 'Specify exactly one of --build or --draft-dir')
    dependencies = {}
    if build is not None:
        source, record, timeline = native.verified_build(build)
        validate_export_profiles(record['runtime_profile'], runtime['runtime_profile'])
        capabilities = native.windows_build_supported_features(timeline, record, source / 'draft', runtime)
        build_hash = _j.nd.digest(source / 'build.json')
        def stage(job):
            return native.stage_timeline(timeline, record, source / 'draft', job, runtime)
        def unchanged():
            _j.require(_j.files_manifest(source / 'draft') == record['files'] and
                       _j.nd.digest(source / 'build.json') == build_hash, 'Source build changed during preview')
        return source, timeline, {'build': str(source), 'build_sha256': build_hash}, capabilities, stage, unchanged
    source, before, timeline, evidence = native.read_draft(draft_dir, runtime)
    timeline, evidence['canvas_selection'] = native.draft_export_canvas(timeline)
    record = {'runtime_profile': runtime['runtime_profile'], 'runtime': runtime}
    capabilities = native.windows_saved_draft_supported_features(timeline, record, source, runtime)
    def stage(job):
        return native.stage_draft_timeline(timeline, source, job, runtime, dependencies)
    def unchanged():
        _j.require(_j.files_manifest(source) == before, 'Source draft changed during preview')
        _j.require(all(Path(path).is_file() and Path(path).stat().st_size == info['size'] and
                       _j.nd.digest(path) == info['sha256'] for path, info in dependencies.items()),
                   'Source draft media/font changed during preview')
    evidence['source_manifest'] = before
    return source, timeline, evidence, capabilities, stage, unchanged


class NativeClient:
    def __init__(self, install, endpoint, job, env, timeout, client_path=None):
        self.install, self.endpoint, self.job, self.env, self.timeout = install, endpoint, job, env, timeout
        self.count = 0
        self.client_path = Path(client_path) if client_path is not None else CLIENT
        self.bound_session = None

    def invoke(self, domain, operation, params=None, target=None, packet=None, check=True):
        self.count += 1
        request = {'id': str(uuid.uuid4()), 'protocolVersion': 1, 'domain': domain, 'operation': operation}
        if params is not None:
            request['params'] = params
        if target is not None:
            request['targetId'] = target
        data = {'endpoint': self.endpoint, 'request': request, 'timeoutMs': min(self.timeout * 1000, 15000)}
        if packet is not None:
            data['packetPath'] = str(packet)
        if self.bound_session is not None:
            data['boundSessionId'] = self.bound_session
        process = subprocess.run([str(self.install / 'bun.exe'), str(self.client_path)], input=json.dumps(data) + '\n',
            capture_output=True, text=True, encoding='utf-8', errors='replace', env=self.env, cwd=self.job,
            timeout=min(self.timeout, 15) + 5, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            response = json.loads(process.stdout)
        except ValueError:
            raise RuntimeError('Native preview JSONL client failed: ' + process.stderr[-1000:])
        summary = deepcopy(request)
        if operation == 'load':
            summary['params']['draftJson'] = {'bytes': len(params['draftJson'].encode('utf-8')),
                'sha256': hashlib.sha256(params['draftJson'].encode('utf-8')).hexdigest()}
        _save(self.job / ('ipc-' + str(self.count).zfill(3) + '.json'), {'request': summary, 'response': response})
        _j.require(response.get('id') == request['id'] and response.get('protocolVersion') == 1,
                   'Native preview IPC response identity differs')
        if check:
            _j.require(process.returncode == 0 and response.get('ok') is True and
                       response.get('result', {}).get('accepted') is not False,
                       'Native preview request failed: ' + json.dumps(response, ensure_ascii=False)[:1000])
        return response


def run(out, at, width=960, height=None, timeout=90, *, build=None, draft_dir=None):
    configure_environment()
    _j.require(type(timeout) is int and 10 <= timeout <= 600, 'Preview timeout must be 10..600 seconds')
    runtime = _j.nd.validate_runtime()
    component_hashes = verify_service(runtime)
    source, timeline, source_evidence, capabilities, stage, unchanged = prepare_source(runtime, build, draft_dir)
    settings = preview_settings(timeline, at, width, height)
    job = Path(out)
    _j.require(job.is_absolute() and str(job).isascii() and not job.exists() and not job.is_symlink(),
               'Preview output must be a new absolute ASCII directory')
    _j.require('work' in [part.lower() for part in job.parts], 'Preview output must be under work/')
    job = job.resolve()
    _j.require(not job.is_relative_to(source) and not source.is_relative_to(job) and
               not job.is_relative_to(_j.nd.DRAFT_ROOT.resolve()), 'Preview output must be separate from source/live drafts')
    job = _j.nd.fresh_directory(job)
    report = {'schema': SCHEMA, 'status': 'preparing', 'runtime': runtime, 'components': component_hashes,
              'source': source_evidence, 'settings': settings, 'capabilities': capabilities, 'frames': [],
              'renderer': 'Official videoeditor-service player.captureFrame',
              'preview_route': 'native-player-capture-frame', 'export_used': False,
              'external_frame_decode_and_resize': False, 'desktop_screenshot': False,
              'mouse_keyboard_used': False, 'gui_host_required': False, 'network_requested': False,
              'network_sandbox_enforced': False, 'out': str(job)}
    process = None; client = None; player = None; identity_checked = False
    try:
        staged, files = stage(job)
        staged, files, upgrades = upgrade_preview_resources(staged, files, job)
        report['resource_upgrades'] = upgrades
        unchanged()
        timeline_path = job / 'timeline.json'
        _save(timeline_path, staged)
        _save(job / 'inputs.json', {'files': files, 'timeline_sha256': _j.nd.digest(timeline_path)})
        verify_service(runtime)
        install = Path(runtime['install_dir'])
        endpoint = '\\\\.\\pipe\\jy-native-preview-' + uuid.uuid4().hex
        env = dict(os.environ)
        for key in ('CUSTOM_AGENT_SANDBOX_OWNER', 'CUSTOM_AGENT_PARENT_PROCESS_ID',
                    'AGENT_HOST_PARENT_PROCESS_ID', 'CUSTOM_AGENT_PROCESS_NAME'):
            env.pop(key, None)
        env.update(VIDEOEDITOR_ADDON_PATH=str(install / 'videoeditor_addon.node'),
                   CUSTOM_AGENT_NATIVE_ADDON_DIR=str(install), AGENT_RUNTIME_ADDON_PATH=str(install / 'agent_runtime_addon.node'),
                   AGENT_HOST_PACKAGE_ROOT=str(install), PATH=str(install) + os.pathsep + env.get('PATH', ''))
        command = [str(install / 'bun.exe'), '--preload',
                   str(install / 'Resources/canvas_agent/runtime/agent-runtime-addon-preload.mjs'),
                   str(install / 'Resources/canvas_agent/runtime/videoeditor-service.mjs'), '--endpoint', endpoint]
        with (job / 'service.stdout.log').open('wb') as stdout, (job / 'service.stderr.log').open('wb') as stderr:
            process = subprocess.Popen(command, cwd=job, env=env, stdout=stdout, stderr=stderr,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        report['service_pid'] = process.pid
        client = NativeClient(install, endpoint, job, env, timeout)
        deadline = time.monotonic() + min(timeout, 20)
        while True:
            _j.require(process.poll() is None, 'Native preview service exited before becoming ready')
            health = client.invoke('system', 'health', check=False)
            if health.get('ok') and health.get('result', {}).get('ready'):
                _j.require(health['result'].get('pid') == process.pid, 'Native preview service PID differs')
                identity_checked = True
                report['health'] = health['result']
                break
            _j.require(time.monotonic() < deadline, 'Native preview service did not become ready')
            time.sleep(.2)
        created = client.invoke('player', 'create', {'kind': 'draft', 'serviceGeneration': 1})
        player = created['result'].get('sessionId')
        _j.require(isinstance(player, str) and player and created['result'].get('kind') == 'draft', 'Native draft player was not created')
        client.invoke('player', 'load', player_load_params(staged, job), player)
        time.sleep(.5)
        deadline = time.monotonic() + min(timeout, 20)
        while True:
            state = client.invoke('player', 'getState', target=player)
            native_state = state.get('result', {})
            if (native_state.get('status') == 'ready' and
                    type(native_state.get('durationUs')) in (int, float) and
                    abs(native_state['durationUs'] - staged['duration']) <= settings['timestamp_tolerance_us']):
                report['loaded_state'] = state['result']
                break
            _j.require(time.monotonic() < deadline, 'Native player did not become ready')
            time.sleep(.2)
        for index, position in enumerate(settings['positions_us']):
            client.invoke('player', 'seek', {'positionUs': position, 'seekMode': 'done'}, player)
            time.sleep(.2)
            captured = None
            for attempt in range(12):
                packet_path = job / ('frame-' + str(index).zfill(3) + '-attempt-' + str(attempt).zfill(2) + '.packet')
                frame = client.invoke('player', 'captureFrame', {'width': settings['width'], 'height': settings['height']},
                                      player, packet_path, check=False)
                if frame.get('ok') and frame.get('result', {}).get('packet'):
                    packet = packet_path.read_bytes()
                    try:
                        info, pixels = parse_packet(packet, settings['width'], settings['height'], position,
                                                    settings['timestamp_tolerance_us'])
                    except FrameNotAtTarget:
                        time.sleep(.2)
                        continue
                    png = png_bytes(settings['width'], settings['height'], pixels)
                    png_path = job / ('frame-' + str(index).zfill(3) + '.png')
                    png_path.write_bytes(png)
                    captured = {**info, 'png': str(png_path), 'png_sha256': hashlib.sha256(png).hexdigest(),
                                'packet': str(packet_path), 'attempt': attempt + 1}
                    report['frames'].append(captured)
                    _save(job / 'preview.json', report)
                    break
                error = frame.get('error', {})
                _j.require(error.get('code') == 'frame_unavailable',
                           'Native frame capture failed: ' + json.dumps(frame, ensure_ascii=False)[:1000])
                time.sleep(.2)
            _j.require(captured is not None, 'Native frame did not arrive at the requested timestamp')
            state = client.invoke('player', 'getState', target=player)['result']
            _j.require(state.get('status') in {'ready', 'paused'},
                       'Preview frame was not captured from a paused ready player')
            captured['player_state'] = state
        unchanged()
        report['source_unchanged'] = True
        report['status'] = 'native-frames-captured'
    except Exception as error:
        report['status'] = 'failed'
        report['error'] = str(error)
    finally:
        cleanup = {'owned_service_pid': process.pid if process else None, 'identity_checked': identity_checked}
        if process is not None:
            if process.poll() is None and client is not None and identity_checked:
                if player:
                    try:
                        client.invoke('player', 'destroy', target=player)
                        cleanup['player_destroyed'] = True
                    except Exception as error:
                        cleanup['player_destroy_error'] = str(error)
                try:
                    response = client.invoke('system', 'shutdown', {'expectedPid': process.pid})
                    _j.require(response.get('result', {}).get('pid') == process.pid, 'Shutdown service PID differs')
                    cleanup['shutdown_accepted'] = True
                    process.wait(timeout=10)
                except Exception as error:
                    cleanup['shutdown_error'] = str(error)
            if process.poll() is None:
                process.terminate()
                cleanup['owned_process_terminated'] = True
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=5)
                    cleanup['owned_process_killed'] = True
            cleanup['service_exit_code'] = process.returncode
        report['cleanup'] = cleanup
        try:
            unchanged()
            report['source_unchanged'] = True
        except Exception as error:
            report['source_unchanged'] = False
            report['status'] = 'failed'
            report['source_check_error'] = str(error)
        _save(job / 'preview.json', report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--build'); source.add_argument('--draft-dir')
    parser.add_argument('--out', required=True)
    parser.add_argument('--at', type=float, nargs='+', required=True, help='Frame positions in seconds; end is exclusive')
    parser.add_argument('--width', type=int, default=960)
    parser.add_argument('--height', type=int, help='Default follows the saved canvas aspect ratio')
    parser.add_argument('--timeout', type=int, default=90)
    args = parser.parse_args(argv)
    report = run(args.out, args.at, args.width, args.height, args.timeout, build=args.build, draft_dir=args.draft_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['status'] == 'native-frames-captured' else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print('Native preview failed: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
