"""Reviewed per-material circle-mask animation through the official Lyra CLI.

Some legacy drafts have inconsistent root/nested timeline selection. When the
normal saved readback is missing, reconciliation copies only the verified
requested root channel into the selected main via EncryptUtils.
Coordinates affect the mask itself; video clip transforms are never changed.
"""
from __future__ import annotations

from copy import deepcopy
import math
import re

PROPERTIES = {
    'width': ('KFTypeCommonMaskSizeWidth', .05, 1.0),
    'height': ('KFTypeCommonMaskSizeHeight', .05, 1.0),
    'center-x': ('KFTypeCommonMaskPositionX', -1.0, 1.0),
    'center-y': ('KFTypeCommonMaskPositionY', -1.0, 1.0),
    'feather': ('KFTypeCommonMaskFeather', 0.0, 1.0),
}
TYPES = {value[0]: key for key, value in PROPERTIES.items()}
PRESETS = {'mask/circle', 'mask/circle-soft'}


def _require(value, message):
    if not value:
        raise ValueError(message)


def _number(value, low, high, label):
    _require(type(value) in (int, float) and math.isfinite(value) and low <= value <= high,
             label + ' is outside the reviewed range')


def _timing(segment):
    source = segment.get('source_timerange', {})
    target = segment.get('target_timerange', {})
    # Trim/speed conversion exists in the shipped renderer, but is not yet
    # included in the pixel-reviewed public contract for mask animation.
    _require(type(source.get('start', 0)) is int and source.get('start', 0) == 0,
             'Mask animation currently requires an untrimmed source start')
    duration = target.get('duration')
    _require(type(duration) is int and duration > 0 and
             source.get('duration') == duration and
             type(segment.get('speed', 1.0)) in (int, float) and
             math.isclose(segment.get('speed', 1.0), 1.0, abs_tol=1e-9),
             'Mask animation currently requires ordinary 1x timing')
    _require(not segment.get('reverse') and not segment.get('is_reverse'),
             'Mask animation currently requires forward playback')
    return duration


def _target(action, timeline, *, temporal=True):
    sid = action.get('segment_id')
    _require(isinstance(sid, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,128}', sid),
             'Mask animation requires one exact segment_id')
    matches = [(track, seg) for track in timeline.get('tracks', [])
               for seg in track.get('segments', []) if seg.get('id') == sid]
    _require(len(matches) == 1 and matches[0][0].get('type') == 'video',
             'Mask animation target must be one existing video segment')
    segment = matches[0][1]
    if not temporal:
        return segment, None
    refs = segment.get('extra_material_refs', [])
    _require(isinstance(refs, list) and len(refs) == len(set(refs)),
             'Mask animation target has ambiguous material references')
    masks = [node for node in timeline.get('materials', {}).get('common_mask', [])
             if node.get('id') in refs]
    _require(len(masks) == 1 and masks[0].get('resource_type') == 'circle' and
             masks[0].get('type') == 'mask', 'Mask animation requires one bound circle mask')
    _require(sum(node.get('id') == masks[0]['id'] for nodes in timeline.get('materials', {}).values()
                 for node in nodes) == 1, 'Mask animation material identity is ambiguous')
    _timing(segment)
    for speed in timeline.get('materials', {}).get('speeds', []):
        if speed.get('id') in refs:
            value = speed.get('speed', 1.0)
            _require(not speed.get('curve_speed') and type(value) in (int, float) and
                     math.isfinite(value) and value == 1.0,
                     'Mask animation does not admit speed material remapping')
    return segment, masks[0]


def compile_keyframe(action, timeline, ref, *, temporal=True):
    required = {'op', 'segment_id', 'preset', 'property', 'points'}
    _require(isinstance(action, dict) and required <= set(action) <= required | {'curve'},
             'Missing or unsupported mask animation action fields')
    _require(action.get('op') == 'video.mask.keyframe' and action.get('preset') in PRESETS,
             'Unsupported mask animation operation or preset')
    prop = action.get('property')
    _require(isinstance(prop, str) and prop in PROPERTIES, 'Unsupported mask animation property')
    _require(prop != 'feather' or action.get('preset') == 'mask/circle-soft',
             'Feather animation requires the reviewed modern circle-soft resource')
    _require(action.get('curve', 'linear') == 'linear', 'Only linear mask animation has been reviewed')
    _require(isinstance(ref, str) and re.fullmatch(r'local://[A-Za-z0-9][A-Za-z0-9_.-]*', ref),
             'Mask animation requires an ASCII local draft reference')
    segment, mask = _target(action, timeline, temporal=temporal)
    kind, low, high = PROPERTIES[prop]
    points = action.get('points')
    _require(isinstance(points, list) and 2 <= len(points) <= 256,
             'Use 2..256 strictly ordered mask animation points')
    duration = _timing(segment) if temporal else None
    previous = -1
    values = []
    for point in points:
        _require(isinstance(point, dict) and set(point) == {'time_ms', 'value'},
                 'Mask animation point requires time_ms and value')
        when = point['time_ms']
        _require(type(when) is int and when >= 0 and when > previous and
                 (duration is None or when * 1000 <= duration),
                 'Mask animation point is unordered or outside the target segment')
        _number(point['value'], low, high, 'Mask animation value')
        values.append(str(when) + 'ms:' + format(point['value'], '.12g'))
        previous = when
    _require(points[0]['time_ms'] == 0, 'Mask animation must start at local time zero')
    # Preflight can precede a mask.set action in the same non-atomic batch.
    # Actual invocation always recompiles with temporal=True and a real mask ID.
    if not temporal:
        return []
    return ['draft', 'keyframe', 'add', '--ref', ref, '--seg-id', action['segment_id'],
            '--keyframe-type', kind, '--material-id', mask['id'],
            '--points', ','.join(values), '--curve', 'linear']


def validate_keyframes(segment, bound_mask_ids, *, soft_mask_ids=()):
    """Admit only the five reviewed linear channels with exact mask binding."""
    masks = set(bound_mask_ids)
    soft_masks = set(soft_mask_ids)
    _require(soft_masks <= masks, 'Soft mask identities must bind a reviewed mask')
    _require(len(masks) <= 1, 'Only one animated mask per segment is reviewed')
    groups = segment.get('common_keyframes', [])
    _require(isinstance(groups, list), 'Mask keyframes must be a list')
    seen = set()
    count = 0
    duration = None
    for group in groups:
        _require(isinstance(group, dict), 'Mask keyframe group must be an object')
        kind, mid = group.get('property_type'), group.get('material_id')
        if kind not in TYPES:
            _require(mid not in masks and not (isinstance(kind, str) and
                     kind.startswith(('KFTypeCommonMask', 'KFTypeMask'))),
                     'Unreviewed mask material keyframe channel')
            continue
        _require(mid in masks and mid and len(masks) == 1,
                 'Mask keyframe channel must bind the exact mask material ID')
        _require(kind != 'KFTypeCommonMaskFeather' or mid in soft_masks,
                 'Legacy circle resources cannot render reviewed feather animation')
        _require(set(group) <= {'id', 'material_id', 'property_type', 'keyframe_list'} and
                 isinstance(group.get('id'), str) and group['id'], 'Unsupported mask keyframe group fields')
        _require(kind not in seen, 'Duplicate mask animation channel')
        seen.add(kind)
        if duration is None:
            duration = _timing(segment)
        points = group.get('keyframe_list')
        _require(isinstance(points, list) and 2 <= len(points) <= 256, 'Invalid mask keyframe point count')
        _require(points[0].get('time_offset', 0) == 0, 'Mask animation must start at source time zero')
        low, high = PROPERTIES[TYPES[kind]][1:]
        previous = -1
        for point in points:
            _require(isinstance(point, dict) and
                     not set(point) - {'id', 'time_offset', 'values', 'curveType', 'left_control', 'right_control'},
                     'Unsupported mask keyframe point fields')
            when = point.get('time_offset', 0)
            _require(type(when) is int and previous < when <= duration and when >= 0,
                     'Mask keyframe timestamp is unordered or outside the source')
            _require(isinstance(point.get('id'), str) and point['id'] and
                     point.get('curveType', 'Line') == 'Line', 'Only linear mask keyframes are reviewed')
            values = point.get('values')
            _require(isinstance(values, list) and len(values) == 1, 'Mask keyframe requires one scalar value')
            _number(values[0], low, high, 'Saved mask keyframe value')
            for field in ('left_control', 'right_control'):
                control = point.get(field, {'x': 0, 'y': 0})
                _require(isinstance(control, dict) and set(control) <= {'x', 'y'} and
                         all(type(control.get(axis, 0)) in (int, float) and control.get(axis, 0) == 0
                             for axis in ('x', 'y')), 'Mask animation control handles are unreviewed')
            previous = when
        count += 1
    return count


def verify_keyframe(action, timeline):
    # Re-run the same public contract before accepting a saved channel.
    compile_keyframe(action, timeline, 'local://verify')
    segment, mask = _target(action, timeline)
    validate_keyframes(segment, {mask['id']},
                       soft_mask_ids={mask['id']} if action['preset'] == 'mask/circle-soft' else set())
    kind = PROPERTIES[action['property']][0]
    groups = [group for group in segment.get('common_keyframes', [])
              if group.get('property_type') == kind and group.get('material_id') == mask['id']]
    _require(len(groups) == 1, 'Requested mask animation channel did not round-trip')
    group = groups[0]
    _require(len(group['keyframe_list']) == len(action['points']), 'Saved mask animation point count differs')
    for saved, wanted in zip(group['keyframe_list'], action['points']):
        _require(saved.get('time_offset', 0) == wanted['time_ms'] * 1000 and
                 math.isclose(saved['values'][0], wanted['value'], abs_tol=1e-9, rel_tol=1e-9),
                 'Saved mask animation timestamp or value differs')
    return {'property': action['property'], 'property_type': kind, 'material_id': mask['id'],
            'points': deepcopy(action['points']), 'curve': 'linear', 'mask_itself_animated': True}


def reconcile_after_cli(action, source, audit_prefix, runtime):
    """Repair only a legacy draft without a declared project timeline.

    Proper project.json drafts must round-trip through their selected main;
    an old root mirror may never rescue a failed normal-project readback.
    """
    import native_export as native
    import windows_timeline_patch as patch

    source, _, timeline, _ = native.read_draft(source, runtime)
    try:
        verify_keyframe(action, timeline)
        return None
    except ValueError as error:
        _require(not (source / 'Timelines' / 'project.json').exists(),
                 'Declared main mask animation failed readback; stale root mirror was ignored: ' + str(error))

    def mutate(updated, draft):
        root = draft / native.j.nd.TIMELINE_FILE
        _require(root.is_file() and not root.is_symlink(), 'Official root mirror is missing or redirected')
        canonical = native.j.nd.helper()._decrypt_metadata_in_memory(root)
        _require(canonical.get('id') == updated.get('id'), 'Official root timeline identity differs')
        proof = verify_keyframe(action, canonical)
        root_segment, root_mask = _target(action, canonical)
        main_segment, main_mask = _target(action, updated)
        _require(root_mask['id'] == main_mask['id'] and root_segment['id'] == main_segment['id'],
                 'Official mask binding differs from the declared main timeline')
        _require(root_segment.get('material_id') == main_segment.get('material_id'),
                 'Legacy root source material differs from the selected timeline')
        for field in ('source_timerange', 'target_timerange'):
            left, right = root_segment.get(field, {}), main_segment.get(field, {})
            _require((left.get('start', 0), left.get('duration')) ==
                     (right.get('start', 0), right.get('duration')),
                     'Legacy root source/target timing differs from the selected timeline')
        kind = proof['property_type']
        copied = next(group for group in root_segment['common_keyframes']
                      if group.get('material_id') == main_mask['id'] and group.get('property_type') == kind)
        previous = deepcopy(main_segment.get('common_keyframes', []))
        groups = [group for group in previous
                  if not (group.get('material_id') == main_mask['id'] and group.get('property_type') == kind)]
        groups.append(deepcopy(copied))
        main_segment['common_keyframes'] = groups
        verify_keyframe(action, updated)
        return {**proof, 'source_root_sha256': native.j.nd.digest(root),
                'copied_fields': ['tracks[segment_id=' + action['segment_id'] + '].common_keyframes[' + kind + ']'],
                'previous_groups': previous, 'official_root_group': deepcopy(copied),
                'clip_transform_preserved': True, 'other_main_fields_preserved': True}

    return patch.commit(source, audit_prefix, runtime, 'mask-keyframes', mutate)
