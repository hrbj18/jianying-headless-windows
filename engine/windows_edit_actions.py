"""Typed, audited saved-draft edits through the official Windows Lyra runtime.

Every action commits immediately. A failed batch stops and retains a byte-exact
before snapshot; it does not claim atomicity or silently restore the draft.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import shutil
import sys

import draftediting_runtime as dr
import native_export as native
import windows_vfx as vfx
from local_config import configure_environment

SCHEMA = 'jy-windows-edit-actions/v1'
RESULT_SCHEMA = 'jy-windows-edit-actions-result/v1'
PROPERTY_TYPES = {
    'position-x': ('KFTypePositionX',), 'position-y': ('KFTypePositionY',),
    'scale': ('KFTypeScaleX', 'KFTypeScaleY'), 'scale-x': ('KFTypeScaleX',),
    'scale-y': ('KFTypeScaleY',), 'rotation': ('KFTypeRotation',),
    'opacity': ('KFTypeAlpha',), 'volume': ('KFTypeVolume',),
}
CURVES = {'linear': 'Line', 'ease-in': 'CurveIn', 'ease-out': 'CurveOut',
          'ease-in-out': 'CurveInOut', 'free-in': 'FreeIn', 'free-out': 'FreeOut',
          'free-in-out': 'FreeInOut'}
ADJUST_FIELDS = ('brightness', 'contrast', 'saturation')
_j = native.j


def _keys(value, required, optional=()):
    _j.require(isinstance(value, dict), 'Expected an action object')
    _j.require(set(required) <= set(value) and not set(value) - set(required) - set(optional),
               'Missing or unsupported fields: ' + ', '.join(sorted(set(value))))


def _number(value, low, high, label):
    return _j.number(value, label, low, high)


def _time(value, label):
    return _j.integer(value, label, 0)


def _scalar(value):
    return format(value, '.12g')


def _segments(timeline):
    return {segment['id']: (track['type'], segment)
            for track in timeline.get('tracks', []) for segment in track.get('segments', [])}


def _target(action, timeline):
    segment_id = action.get('segment_id')
    _j.require(isinstance(segment_id, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,128}', segment_id),
               'segment_id must identify exactly one existing segment')
    rows = _segments(timeline)
    _j.require(segment_id in rows, 'Target segment does not exist: ' + segment_id)
    return rows[segment_id]


def _groups(segment, prop):
    types = PROPERTY_TYPES[prop]
    return [group for group in segment.get('common_keyframes', [])
            if group.get('property_type') in types and not group.get('material_id')]


def _property(prop, track_type):
    _j.require(isinstance(prop, str) and prop in PROPERTY_TYPES, 'Unsupported animated property')
    _j.require(track_type in {'video', 'audio', 'text'}, 'Unsupported keyframe target type')
    _j.require((prop == 'volume' and track_type in {'video', 'audio'}) or
               (prop != 'volume' and track_type in {'video', 'text'}),
               'Animated property is incompatible with the target segment')


def compile_action(action, timeline, ref, *, temporal=True):
    """Validate one exact target and compile argv; never invoke a shell."""
    _j.require(isinstance(action, dict), 'Action must be an object')
    op = action.get('op')
    if op in vfx.OPS:
        return vfx.compile_action(action, timeline, ref, temporal=temporal)
    track_type, segment = _target(action, timeline)
    common = ['--ref', ref, '--seg-id', action['segment_id']]
    duration_us = segment.get('target_timerange', {}).get('duration', 0)
    if op == 'keyframe.add':
        _keys(action, ('op', 'segment_id', 'property', 'points'), ('curve',))
        prop = action['property']; _property(prop, track_type)
        points = action['points']
        _j.require(isinstance(points, list) and 2 <= len(points) <= 256,
                   'Use 2..256 strictly ordered keyframe points')
        last = -1
        compiled = []
        for point in points:
            _keys(point, ('time_ms', 'value'))
            time_ms = _time(point['time_ms'], 'Keyframe time_ms')
            _j.require(time_ms > last, 'Keyframe times must be unique and increasing')
            if temporal:
                _j.require(time_ms * 1000 <= duration_us, 'Keyframe exceeds the current segment duration')
            last = time_ms
            bounds = (-1, 1) if prop.startswith('position-') else (
                (.01, 10) if prop.startswith('scale') else ((-360, 360) if prop == 'rotation' else
                                                        ((0, 4) if prop == 'volume' else (0, 1))))
            value = _number(point['value'], *bounds, 'Keyframe value')
            scalar = (_scalar(value * 100) + '%' if prop.startswith('position-') or prop in {'opacity', 'volume'}
                      else _scalar(value) + ('deg' if prop == 'rotation' else 'x'))
            compiled.append(str(time_ms) + 'ms:' + scalar)
        argv = ['draft', 'keyframe', 'add', *common, '--animated-property', prop,
                '--points', ','.join(compiled)]
        if 'curve' in action:
            _j.require(isinstance(action['curve'], str) and action['curve'] in CURVES, 'Unsupported keyframe curve')
            argv += ['--curve', action['curve']]
        return argv
    if op == 'keyframe.curve':
        _keys(action, ('op', 'segment_id', 'property', 'time_ms', 'curve'))
        prop = action['property']; _property(prop, track_type)
        at = _time(action['time_ms'], 'Curve time_ms')
        _j.require(isinstance(action['curve'], str) and action['curve'] in CURVES, 'Unsupported keyframe curve')
        if temporal:
            groups = _groups(segment, prop)
            _j.require(len(groups) == len(PROPERTY_TYPES[prop]) and all(
                any(point.get('time_offset', 0) == at * 1000 for point in group.get('keyframe_list', []))
                for group in groups), 'Curve requires an existing point on every selected property channel')
        return ['draft', 'keyframe', 'curve', 'set', *common, '--animated-property', prop,
                '--at', str(at) + 'ms', '--curve', action['curve']]
    if op == 'video.speed-curve':
        import native_speed_curves
        _keys(action, ('op', 'segment_id', 'points'))
        _j.require(track_type == 'video','video.speed-curve requires a video segment')
        native_speed_curves.average(action['points'])
        return ['draft','video','speed',*common,'--curve-points',
                json.dumps(action['points'],allow_nan=False,separators=(',',':'))]
    if op == 'video.speed':
        _keys(action, ('op', 'segment_id', 'speed'))
        _j.require(track_type == 'video', 'video.speed requires a video segment')
        _number(action['speed'], .1, 10, 'Video speed')
        material = next((node for node in timeline.get('materials', {}).get('videos', [])
                         if node.get('id') == segment.get('material_id')), {})
        _j.require(material.get('type') == 'video', 'Still images do not support speed')
        return ['draft', 'video', 'speed', *common, '--speed', _scalar(action['speed'])]
    if op == 'video.adjust':
        _keys(action, ('op', 'segment_id'), ADJUST_FIELDS)
        _j.require(track_type == 'video', 'video.adjust requires a video segment')
        fields = [key for key in ADJUST_FIELDS if key in action]
        _j.require(fields, 'video.adjust requires at least one tested adjustment field')
        argv = ['draft', 'video', 'adjust', *common]
        for field in fields:
            _number(action[field], -1, 1, field)
            argv += ['--' + field, _scalar(action[field])]
        return argv
    if op == 'audio.fade':
        _keys(action, ('op', 'segment_id', 'in_ms', 'out_ms'))
        _j.require(track_type == 'audio', 'audio.fade requires an audio segment')
        fade_in = _time(action['in_ms'], 'Fade in_ms')
        fade_out = _time(action['out_ms'], 'Fade out_ms')
        if temporal:
            _j.require((fade_in + fade_out) * 1000 <= duration_us, 'Audio fades overlap or exceed the segment')
        return ['draft', 'audio', 'fade', *common, '--in', str(fade_in) + 'ms', '--out', str(fade_out) + 'ms']
    if op == 'video.background':
        kind = action.get('type')
        _j.require(isinstance(kind, str) and kind in {'color', 'blur'}, 'Background type must be color or blur')
        _keys(action, ('op', 'segment_id', 'type', 'color' if kind == 'color' else 'blur'))
        _j.require(track_type == 'video', 'video.background requires a video segment')
        argv = ['draft', 'video', 'background', *common, '--type', kind]
        if kind == 'color':
            _j.require(isinstance(action['color'], str) and re.fullmatch(r'#[0-9a-fA-F]{6}', action['color']),
                       'Background color must be #RRGGBB')
            return argv + ['--color', action['color']]
        _number(action['blur'], 0, 1, 'Background blur')
        return argv + ['--blur', _scalar(action['blur'])]
    raise ValueError('Unsupported edit action: ' + str(op))


def verify_action(action, timeline):
    """Check authoritative native draft values, not only CLI err_code."""
    if action.get('op') in vfx.OPS:
        return vfx.verify_action(action, timeline)
    _, segment = _target(action, timeline)
    materials = timeline.get('materials', {})
    refs = set(segment.get('extra_material_refs', []))
    op = action['op']
    def close(actual, expected):
        return type(actual) in (int, float) and math.isclose(actual, expected, rel_tol=1e-7, abs_tol=1e-7)
    if op in {'keyframe.add', 'keyframe.curve'}:
        prop = action['property']; groups = _groups(segment, prop)
        _j.require(len(groups) == len(PROPERTY_TYPES[prop]), 'Keyframe channels are missing or ambiguous')
        wanted = action['points'] if op == 'keyframe.add' else [{'time_ms': action['time_ms']}]
        for group in groups:
            for wanted_point in wanted:
                found = [point for point in group.get('keyframe_list', [])
                         if point.get('time_offset', 0) == wanted_point['time_ms'] * 1000]
                _j.require(len(found) == 1, 'Native keyframe timestamp did not round-trip')
                if 'value' in wanted_point:
                    values = found[0].get('values', [])
                    _j.require(len(values) == 1 and close(values[0], wanted_point['value']),
                               'Native keyframe value did not round-trip')
                if 'curve' in action:
                    _j.require(found[0].get('curveType', 'Line') == CURVES[action['curve']],
                               'Native keyframe curve did not round-trip')
        return {'property': prop, 'channels': [group['property_type'] for group in groups], 'points_verified': len(wanted)}
    if op == 'video.speed-curve':
        import native_speed_curves
        result=native_speed_curves.validate(timeline)
        bound=[node for node in materials.get('speeds',[]) if node['id'] in refs]
        _j.require(len(bound)==1 and bound[0].get('curve_speed',{}).get('speed_points')==action['points'],
                   'Native speed curve points did not round-trip')
        return {'points':action['points'],'average_speed':bound[0]['speed'],
                'target_timerange':segment['target_timerange'],**result}
    if op == 'video.speed':
        _j.require(close(segment.get('speed', 1), action['speed']), 'Native speed did not round-trip')
        return {'speed': segment.get('speed', 1), 'target_timerange': segment['target_timerange']}
    bucket = {'audio.fade': 'audio_fades', 'video.background': 'canvases', 'video.adjust': 'effects'}[op]
    bound = [node for node in materials.get(bucket, []) if node.get('id') in refs]
    if op == 'audio.fade':
        _j.require(any(node.get('type') == 'audio_fade' and
                       node.get('fade_in_duration', 0) == action['in_ms'] * 1000 and
                       node.get('fade_out_duration', 0) == action['out_ms'] * 1000 for node in bound),
                   'Native audio fade did not round-trip')
    elif op == 'video.background':
        _j.require(any(node.get('type') == 'canvas_' + action['type'] and
                       (str(node.get('color', '')).lower() == action['color'].lower() if action['type'] == 'color'
                        else close(node.get('blur', .75), action['blur'])) for node in bound),
                   'Native canvas background did not round-trip')
    else:
        for key in ADJUST_FIELDS:
            if key in action:
                _j.require(any(node.get('type') == key and close(node.get('value'), action[key]) for node in bound),
                           'Native adjustment did not round-trip: ' + key)
    return {'bound_materials': bound}


def _save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def run(plan_path, out, timeout=120):
    configure_environment()
    plan = _j.read_json(plan_path)
    _keys(plan, ('schema', 'draft_dir', 'actions'), ('source_timeline_sha256',))
    _j.require(plan['schema'] == SCHEMA, 'Unsupported Windows edit-actions schema')
    _j.require(isinstance(plan['draft_dir'], str) and plan['draft_dir'] and Path(plan['draft_dir']).is_absolute(),
               'draft_dir must be an absolute path')
    _j.require(type(timeout) is int and 1 <= timeout <= 600, 'Timeout must be 1..600 seconds per action')
    runtime = dr.windows_runtime.validate_runtime()
    source, before, timeline, evidence = native.read_draft(plan['draft_dir'], runtime)
    dr.require_ascii_path(source, '草稿路径')
    _j.require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', source.name), 'Draft name must be a simple ASCII local reference')
    actions = plan['actions']
    _j.require(isinstance(actions, list) and 1 <= len(actions) <= 128, 'Use 1..128 explicit edit actions')
    ref = 'local://' + source.name
    for action in actions:
        compile_action(action, timeline, ref, temporal=False)
    if 'source_timeline_sha256' in plan:
        _j.require(plan['source_timeline_sha256'] == evidence['source_timeline_sha256'], 'Draft timeline precondition changed')
    audit = Path(out)
    _j.require(audit.is_absolute(), 'Audit output must be absolute')
    dr.require_ascii_path(audit, '审计路径')
    audit = audit.resolve()
    _j.require('work' in [part.lower() for part in audit.parts], 'Audit output must be under an ASCII work directory')
    _j.require(not audit.is_relative_to(source) and not source.is_relative_to(audit), 'Audit and draft directories must be separate')
    audit = _j.nd.fresh_directory(audit)
    report = {'schema': RESULT_SCHEMA, 'status': 'running', 'atomic': False,
              'draft_dir': str(source), 'audit_dir': str(audit), 'runtime': runtime,
              'before_manifest': before, 'source': evidence, 'steps': [],
              'export_status': 'not-tested-by-this-command',
              'network_requested': any(action['op'] in {'video.mask.set', 'video.transition.add'} for action in actions),
              'official_resource_resolution': 'Vimo resolution may use the existing official connection; no credentials are read',
              'account_data_read': False}
    _save(audit / 'plan.json', plan)
    try:
        shutil.copytree(source, audit / 'before', symlinks=False)
        _j.require(_j.files_manifest(audit / 'before') == before == _j.files_manifest(source),
                   'Draft changed during before-snapshot copy')
        _save(audit / 'before-timeline.json', timeline)
        expected_files = before
        dr.ensure_editor_running()
        for index, action in enumerate(actions, 1):
            prefix = audit / ('step-' + str(index).zfill(3))
            _, current_files, current, _ = native.read_draft(source, runtime)
            _j.require(current_files == expected_files, 'Draft changed outside this edit batch; refusing the next action')
            argv = compile_action(action, current, ref)
            _save(prefix.with_suffix('.before-timeline.json'), current)
            step = {'index': index, 'action': action, 'command': argv, 'status': 'started'}
            report['steps'].append(step)
            _save(audit / 'result.json', report)
            read_paths = [vfx.resource_path(action['preset'])] if action['op'] in vfx.OPS else []
            official = dr.run_lyra(argv, source.parent, timeout, [source], read_paths)
            _save(prefix.with_suffix('.official.json'), official)
            step['official_err_code'] = official['result']['err_code']
            if action['op'] in {'video.mask.set', 'video.mask.update'}:
                from windows_mask_controls import reconcile_after_cli
                step['native_protocol_repair'] = reconcile_after_cli(action, source, prefix, runtime)
            elif action['op'] == 'video.mask.keyframe':
                from windows_mask_keyframes import reconcile_after_cli
                step['native_keyframe_reconciliation'] = reconcile_after_cli(action, source, prefix, runtime)
            _, expected_files, after, _ = native.read_draft(source, runtime)
            _save(prefix.with_suffix('.timeline.json'), after)
            step['readback'] = verify_action(action, after)
            step['status'] = 'applied-and-read-back'
            _save(audit / 'result.json', report)
        report['status'] = 'applied-and-read-back'
        report['completed_count'] = len(actions)
        report['after_manifest'] = expected_files
    except Exception as error:
        report['status'] = 'failed'
        report['error'] = str(error)
        if report['steps'] and report['steps'][-1]['status'] == 'started':
            report['steps'][-1]['status'] = 'failed-or-unverified'
            report['steps'][-1]['error'] = str(error)
        report['completed_count'] = sum(step.get('status') == 'applied-and-read-back' for step in report['steps'])
        report['recovery'] = 'Stopped immediately. Inspect evidence and before/; no automatic rollback was attempted.'
        report['after_manifest'] = _j.files_manifest(source)
    _save(audit / 'result.json', report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True)
    parser.add_argument('--out', required=True, help='New absolute ASCII audit directory under work/')
    parser.add_argument('--timeout', type=int, default=120)
    args = parser.parse_args(argv)
    report = run(args.plan, args.out, args.timeout)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['status'] == 'applied-and-read-back' else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print('Windows edit-actions failed: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
