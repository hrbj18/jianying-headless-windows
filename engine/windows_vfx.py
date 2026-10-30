"""Resource-specific Windows effects validated through official CLI and native pixels.

The catalog contains hashes and material contracts, never effect packages. Local
bindings point at frozen same-machine resources; exports may verify equivalent
draft-owned or staged copies by their complete file manifest.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
import stat

from local_config import load_config
from runtime_profiles import WINDOWS_1147_PROFILE

CATALOG = Path(__file__).with_name('windows-vfx-catalog.json')
CATALOG_SHA256 = 'f41e0e6677578b75444c4c4ed5bbf59df3034085a0f69086c5c7cfab46174d79'
OPS = {'video.effect.add': 'video_effects', 'video.filter.add': 'effects',
       'video.transition.add': 'transitions', 'video.mask.set': 'common_mask',
       'video.mask.update': 'common_mask', 'video.mask.keyframe': 'common_mask'}
ID = re.compile(r'[A-Za-z0-9_-]{1,128}')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def catalog():
    raw = CATALOG.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == CATALOG_SHA256,
            'Windows VFX catalog fingerprint changed; review the resource evidence')
    value = json.loads(raw)
    require(value.get('schema') == 'jy-windows-vfx-catalog/v1' and
            value.get('runtime_profile') == WINDOWS_1147_PROFILE,
            'Unsupported Windows VFX catalog')
    return value


def _profile(runtime):
    require(isinstance(runtime, dict) and runtime.get('runtime_profile') == WINDOWS_1147_PROFILE and
            runtime.get('app_build', '11.4.7.14462') == '11.4.7.14462',
            'Windows VFX is reviewed only for exact 11.4.7.14462')


def _number(value, low, high, label):
    require(type(value) in (int, float) and math.isfinite(value) and low <= value <= high,
            label + ' must be a finite number in ' + str((low, high)))
    return value


def _ordinary(info):
    return not (getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400))


def tree_manifest(folder):
    """Reject aliases, links, unknown files and changes before accepting a package."""
    folder = Path(folder)
    require(folder.is_absolute() and str(folder).isascii() and '..' not in folder.parts,
            'VFX resource path must be absolute ASCII without traversal')
    require(folder.is_dir() and not folder.is_symlink() and _ordinary(folder.lstat()) and
            folder.resolve() == folder, 'VFX resource directory must be canonical and not linked')
    files = {}
    for path in sorted(folder.rglob('*')):
        info = path.lstat()
        require(not path.is_symlink() and _ordinary(info), 'VFX resource links/reparse points are unsupported')
        if stat.S_ISDIR(info.st_mode):
            continue
        require(stat.S_ISREG(info.st_mode), 'VFX package contains a nonregular file')
        require(len(files) < 1024 and info.st_size <= 64 * 1024 * 1024,
                'VFX package exceeds the reviewed resource bounds')
        files[path.relative_to(folder).as_posix()] = {
            'size': info.st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    require(files, 'VFX package is empty')
    return files


def manifest_hash(files):
    return hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def verify_resource(folder, entry):
    actual = tree_manifest(folder)
    require(actual == entry['files'] and manifest_hash(actual) == entry['tree_sha256'],
            'Windows VFX resource bytes changed or contain unreviewed files: ' + entry['key'])
    return Path(folder)


def _exact(actual, expected):
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return set(actual) == set(expected) and all(_exact(actual[key], value) for key, value in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(_exact(a, b) for a, b in zip(actual, expected))
    return actual == expected


def resource_path(key):
    entries = catalog()['resources']
    require(isinstance(key, str) and key in entries, 'Unknown Windows VFX preset: ' + str(key))
    bindings = load_config().get('windows_vfx_resources', {})
    require(isinstance(bindings, dict) and isinstance(bindings.get(key), str),
            'Missing local windows_vfx_resources binding: ' + key)
    return verify_resource(bindings[key], entries[key])


def _shape_matches(bucket, node, entry):
    if not isinstance(node, dict) or bucket != entry['bucket']:
        return False
    # Official later CLI saves omit this protobuf-default false field.
    # An explicit true flag still selects the incompatible legacy protocol.
    if bucket == 'common_mask' and 'is_old_version' not in node:
        node = {**node, 'is_old_version': False}
    # Official filter saves omit the protobuf-default zero intensity. Interpret
    # only this known default; effect values still require an explicit field.
    if bucket == 'effects' and 'value' not in node:
        node = {**node, 'value': 0}
    template = entry['material_template']
    transition = bucket == 'transitions'
    mask = bucket == 'common_mask'
    required = set(template) | {'id', 'path'} | ({'duration'} if transition else set() if mask else {'value'})
    permitted = required | ({'adjust_params'} if entry.get('optional_adjust_params') else set())
    if entry.get('display_name') and bucket == 'effects':
        permitted.add('name')
        if 'name' in node and node['name'] not in ('', entry['display_name']):
            return False
    if not required <= set(node) <= permitted or any(not _exact(node.get(k), v) for k, v in template.items()
                                                   if not (mask and k == 'config')):
        return False
    if not isinstance(node.get('id'), str) or not ID.fullmatch(node['id']) or not isinstance(node.get('path'), str):
        return False
    try:
        if transition:
            require(type(node['duration']) is int and node['duration'] in
                    {value * 1000 for value in entry['duration_ms_values']}, 'Unreviewed transition duration')
        elif mask:
            from windows_mask_controls import validate_native_config
            validate_native_config(node['config'], allow_feather=entry['key'] == 'mask/circle-soft')
        else:
            _number(node['value'], *entry['value_range'], 'VFX value')
        if 'adjust_params' in node:
            params = node['adjust_params']; known = entry['optional_adjust_params']
            require(isinstance(params, list) and len(params) <= len(known), 'Unsupported effect parameter list')
            names = []
            for item in params:
                require(isinstance(item, dict) and set(item) == {'name', 'value'} and
                        item.get('name') in known, 'Unsupported effect adjustment parameter')
                names.append(item['name'])
                bounds = known[item['name']]
                _number(item['value'], bounds['min'], bounds['max'], 'VFX adjustment')
            require(len(names) == len(set(names)), 'Duplicate effect adjustment parameter')
    except ValueError:
        return False
    return True


def entry_for_node(bucket, node, verify_files=True):
    """Identify a native material by its full shape and resource bytes.

    Shape-only mode accepts only an exact frozen binding path, and still verifies
    that binding's bytes. Two filter templates otherwise have identical shapes.
    Production callers should keep the default to allow equivalent staged copies.
    """
    import native_lut_candidates
    experimental=native_lut_candidates.filter_entry(bucket,node)
    if experimental is not None:
        require(_shape_matches(bucket,node,experimental),'Unreviewed standard LUT filter material shape')
        verify_resource(node['path'],experimental)
        return deepcopy(experimental)
    candidates = []
    for entry in catalog()['resources'].values():
        if _shape_matches(bucket, node, entry):
            candidates.append(entry)
            # Historical saved drafts retain their exact reviewed resource bytes.
            # Revisions inherit the material contract, never an arbitrary path.
            for revision in entry.get('legacy_resources', []):
                candidates.append({**entry, **revision, 'legacy_resources': []})
    require(candidates, 'Unreviewed Windows VFX native material shape')
    if verify_files:
        actual = tree_manifest(node['path'])
        identity = manifest_hash(actual)
        matches = [entry for entry in candidates if identity == entry['tree_sha256'] and actual == entry['files']]
    else:
        matches = [entry for entry in candidates if not entry.get('legacy_resource') and
                   Path(node['path']) == resource_path(entry['key'])]
    require(len(matches) == 1, 'Unreviewed or ambiguous Windows VFX resource identity')
    return deepcopy(matches[0])


def _target(action, timeline):
    segment_id = action.get('segment_id')
    require(isinstance(segment_id, str) and ID.fullmatch(segment_id), 'VFX requires one exact segment_id')
    rows = [(track, segment) for track in timeline.get('tracks', []) for segment in track.get('segments', [])
            if segment.get('id') == segment_id]
    require(len(rows) == 1 and rows[0][0].get('type') == 'video', 'VFX target must identify one video segment')
    segment = rows[0][1]
    videos = [node for node in timeline.get('materials', {}).get('videos', [])
              if node.get('id') == segment.get('material_id')]
    require(len(videos) == 1 and videos[0].get('type') in {'video', 'photo'},
            'VFX target has no unique local video/photo material')
    return segment


def _transition_context(segment_id, timeline, duration_us, *, existing_id=None):
    """Only the observed silent, speed-1, handle-backed main-track overlap case."""
    left = _target({'segment_id': segment_id}, timeline)
    tracks = timeline.get('tracks', [])
    main = next((track for track in tracks if track.get('type') == 'video'), None)
    require(main is not None and any(segment is left for segment in main.get('segments', [])),
            'Transition requires the main video track')
    segments = list(main.get('segments', []))
    for segment in segments:
        span = segment.get('target_timerange', {})
        require(type(span.get('start', 0)) is int and type(span.get('duration')) is int and
                span.get('start', 0) >= 0 and span['duration'] > 0, 'Invalid transition target timerange')
    segments.sort(key=lambda segment: segment['target_timerange'].get('start', 0))
    index = next(i for i, segment in enumerate(segments) if segment is left)
    require(index + 1 < len(segments), 'Cannot add a transition to a tail segment')
    right = segments[index + 1]
    left_span, right_span = left['target_timerange'], right['target_timerange']
    cut = left_span.get('start', 0) + left_span['duration']
    require(cut == right_span.get('start', 0), 'Transition requires two exactly adjacent main video segments')
    materials = timeline.get('materials', {})
    video_by_id = {node.get('id'): node for node in materials.get('videos', [])}
    speed_by_id = {node.get('id'): node for node in materials.get('speeds', [])}
    half = duration_us // 2
    for segment in (left, right):
        material = video_by_id.get(segment.get('material_id'), {})
        require(material.get('type') == 'video', 'Transitions on still photos are unreviewed')
        require(type(segment.get('speed', 1)) in (int, float) and segment.get('speed', 1) == 1 and
                not segment.get('reverse') and not segment.get('is_reverse'),
                'Transition supports only forward speed-1 video')
        for identity in segment.get('extra_material_refs') or []:
            speed = speed_by_id.get(identity)
            if speed:
                require(not speed.get('curve_speed') and speed.get('speed', 1) == 1,
                        'Transition curve speed or speed material is unreviewed')
        volume = segment.get('volume', 1)
        require(type(volume) in (int, float) and math.isfinite(volume) and
                (volume == 0 or material.get('has_audio') is False),
                'Transition source audio must be muted or explicitly absent')
        require(not any(group.get('property_type') == 'KFTypeVolume'
                        for group in segment.get('common_keyframes', [])),
                'Transition source-audio volume keyframes are unreviewed')
        target_span = segment['target_timerange']
        source_span = segment.get('source_timerange', {})
        require(target_span['duration'] >= duration_us and
                type(source_span.get('start', 0)) is int and source_span.get('start', 0) >= 0 and
                type(source_span.get('duration')) is int and
                source_span['duration'] == target_span['duration'],
                'Transition requires sufficiently long equal source/target spans at speed 1')
        require(type(material.get('duration')) is int and material['duration'] > 0,
                'Transition requires known source media duration')
        require(source_span.get('start', 0) + source_span['duration'] <= material['duration'],
                'Transition source span exceeds its media duration')
    left_source, right_source = left['source_timerange'], right['source_timerange']
    require(left_source.get('start', 0) + left_source['duration'] + half <=
            video_by_id[left['material_id']]['duration'] and right_source.get('start', 0) >= half,
            'Transition requires source handles on both sides of the cut')
    transitions = {node.get('id'): node for node in materials.get('transitions', [])}
    windows = []
    for segment in segments:
        bound = [identity for identity in (segment.get('extra_material_refs') or []) if identity in transitions]
        require(len(bound) <= 1, 'A video segment cannot bind multiple outgoing transitions')
        for identity in bound:
            if identity == existing_id:
                continue
            require(segment is not left, 'Target already has an outgoing transition')
            node = transitions[identity]
            require(type(node.get('duration')) is int and node['duration'] > 0,
                    'Adjacent transition duration is invalid')
            boundary = segment['target_timerange'].get('start', 0) + segment['target_timerange']['duration']
            windows.append((boundary - node['duration'] / 2, boundary + node['duration'] / 2))
    require(all(cut + half <= start or cut - half >= end for start, end in windows),
            'Adjacent transition windows overlap')
    return {'left_segment_id': left['id'], 'right_segment_id': right['id'],
            'cut_us': cut, 'duration_us': duration_us, 'is_overlap': True}


def validate_timeline(timeline, runtime):
    _profile(runtime)
    import native_color
    import native_adjustment_track
    adjustment,timeline=native_adjustment_track.project(timeline)
    color_result=native_color.validate(timeline)
    if adjustment['tracks']:
        color_result['materials']+=adjustment['materials']
        color_result['packages']=sorted(set(color_result['packages']+adjustment['packages']))
    materials = timeline.get('materials', {})
    require(isinstance(materials, dict), 'VFX requires a material dictionary')
    require(all(track.get('type') in {'video', 'audio', 'text'} for track in timeline.get('tracks', [])),
            'Windows VFX only supports per-video bindings, not effect/filter tracks')
    for material in materials.get('texts', []):
        try:
            content = json.loads(material.get('content', '{}'))
        except (ValueError, TypeError) as error:
            raise ValueError('Invalid native rich-text content') from error
        require(isinstance(content, dict) and isinstance(content.get('styles', []), list) and
                all(isinstance(style, dict) and not style.get('effectStyle')
                    for style in content.get('styles', [])),
                'Native text effect styles are not reviewed on Windows')
    identities = []
    for nodes in materials.values():
        require(isinstance(nodes, list), 'Native material buckets must be lists')
        identities.extend(node.get('id') for node in nodes if isinstance(node, dict) and node.get('id'))
    require(len(identities) == len(set(identities)), 'Native material IDs must be globally unique')
    reviewed = {}
    for bucket in ('video_effects', 'effects', 'transitions', 'common_mask'):
        for node in materials.get(bucket, []):
            if native_color.is_node(bucket,node):continue
            entry = entry_for_node(bucket, node)
            reviewed[node['id']] = entry
    used = set()
    for track in timeline.get('tracks', []):
        for segment in track.get('segments', []):
            require(segment.get('material_id') not in reviewed, 'Windows VFX cannot be a primary track material')
            refs = segment.get('extra_material_refs') or []
            require(isinstance(refs, list) and len(refs) == len(set(refs)), 'Duplicate or invalid extra material references')
            bound = [identity for identity in refs if identity in reviewed]
            if bound:
                _target({'segment_id': segment.get('id')}, timeline)
                require(track.get('type') == 'video', 'Windows VFX requires a video extra-reference binding')
                buckets = [reviewed[identity]['bucket'] for identity in bound]
                require(len(buckets) == len(set(buckets)), 'Only one filter and one effect per video segment are reviewed')
                mask_ids = {identity for identity in bound if reviewed[identity]['bucket'] == 'common_mask'}
                require(not any(group.get('material_id') in set(bound) - mask_ids
                                for group in segment.get('common_keyframes', [])),
                        'Non-mask VFX material keyframes are unreviewed')
                for identity in bound:
                    if reviewed[identity]['bucket'] == 'transitions':
                        node = next(node for node in materials['transitions'] if node['id'] == identity)
                        _transition_context(segment['id'], timeline, node['duration'], existing_id=identity)
                used.update(bound)
            from windows_mask_keyframes import validate_keyframes
            mask_ids = {identity for identity in bound if reviewed[identity]['bucket'] == 'common_mask'}
            soft_mask_ids = {identity for identity in mask_ids if reviewed[identity]['key'] == 'mask/circle-soft'}
            mask_channels = validate_keyframes(segment, mask_ids, soft_mask_ids=soft_mask_ids)
            if mask_channels:
                for speed in materials.get('speeds', []):
                    if speed.get('id') in refs:
                        value = speed.get('speed', 1)
                        require(type(value) in (int, float) and math.isfinite(value) and value == 1 and
                                not speed.get('curve_speed'),
                                'Mask animation does not admit speed material remapping')
    require(used == set(reviewed), 'Windows VFX material has no verified segment binding')
    return {'native_color':color_result,'adjustment_tracks':adjustment,
            'effects': sum(entry['bucket'] == 'video_effects' for entry in reviewed.values()),
            'filters': sum(entry['bucket'] == 'effects' for entry in reviewed.values()),
            'transitions': sum(entry['bucket'] == 'transitions' for entry in reviewed.values()),
            'masks': sum(entry['bucket'] == 'common_mask' for entry in reviewed.values()),
            'resource_keys': sorted({entry['key'] for entry in reviewed.values()}),
            'scope': 'per-video filters/effects, reviewed circle geometry and mask keyframes, silent main-track transitions; exact resource bytes'}


def compile_action(action, timeline, ref, *, temporal=True):
    require(isinstance(action, dict), 'Windows VFX action must be an object')
    transition = action.get('op') == 'video.transition.add'
    mask = action.get('op') in {'video.mask.set', 'video.mask.update', 'video.mask.keyframe'}
    if mask:
        require(isinstance(ref, str) and re.fullmatch(r'local://[A-Za-z0-9][A-Za-z0-9_.-]*', ref),
                'VFX edit requires an explicit ASCII local draft reference')
        require(action.get('preset') in {'mask/circle', 'mask/circle-soft'}, 'Unknown reviewed circle preset')
        resource_path(action['preset'])
        segment = _target(action, timeline)
        if action['op'] == 'video.mask.keyframe':
            if temporal:
                from windows_mask_controls import bound_mask
                bound_mask(action, timeline)
            from windows_mask_keyframes import compile_keyframe
            return compile_keyframe(action, timeline, ref, temporal=temporal)
        if temporal and action['op'] == 'video.mask.set':
            refs = set(segment.get('extra_material_refs') or [])
            require(not any(node.get('id') in refs for node in timeline.get('materials', {}).get('common_mask', [])),
                    'Target already has a mask; use video.mask.update')
        from windows_mask_controls import compile_geometry
        return compile_geometry(action, timeline, ref, temporal=temporal)
    required = {'op', 'segment_id', 'preset'} | ({'duration_ms'} if transition else set())
    allowed = required if transition or mask else required | {'value'}
    require(required <= set(action) <= allowed, 'Missing or unsupported Windows VFX action fields')
    bucket = OPS.get(action['op'])
    require(bucket is not None, 'Unsupported Windows VFX action')
    require(isinstance(ref, str) and re.fullmatch(r'local://[A-Za-z0-9][A-Za-z0-9_.-]*', ref),
            'VFX edit requires an explicit ASCII local draft reference')
    entry = catalog()['resources'].get(action['preset'])
    require(entry is not None and entry['bucket'] == bucket, 'VFX preset kind does not match the operation')
    if transition:
        require(type(action['duration_ms']) is int and action['duration_ms'] in entry['duration_ms_values'],
                'Unreviewed transition duration_ms')
    elif not mask:
        value = action.get('value', entry['default_value'])
        _number(value, *entry['value_range'], 'VFX action value')
    segment = _target(action, timeline)
    if temporal:
        refs = set(segment.get('extra_material_refs') or [])
        require(not any(node.get('id') in refs for node in timeline.get('materials', {}).get(bucket, [])),
                'Target already has this VFX kind; replace/remove requires separate verified support')
    resource = resource_path(entry['key'])
    if transition:
        if temporal:
            _transition_context(action['segment_id'], timeline, action['duration_ms'] * 1000)
        resource_ref = ('local://' + resource.as_posix() if entry.get('compatibility_adapter') is True
                        else 'vimo://' + entry['resource_id'])
        return ['draft', 'video', 'transition', 'add', '--ref', ref, '--seg-id', action['segment_id'],
                '--resource', resource_ref, '--duration', str(action['duration_ms']) + 'ms',
                '--is-overlap', 'true']
    argv = ['draft', 'video', 'effect' if bucket == 'video_effects' else 'filter', 'add',
            '--ref', ref, '--seg-id', action['segment_id'], '--resource', 'local://' + resource.as_posix()]
    if bucket == 'effects':
        argv += ['--intensity', format(value, '.12g')]
    return argv


def verify_action(action, timeline):
    require(action.get('op') in OPS, 'Unsupported Windows VFX action')
    entry = catalog()['resources'].get(action.get('preset'))
    require(entry is not None and entry['bucket'] == OPS[action['op']], 'Unexpected VFX preset kind')
    if action['op'] in {'video.mask.set', 'video.mask.update'}:
        from windows_mask_controls import verify_geometry
        return {**verify_geometry(action, timeline), 'tree_sha256': entry['tree_sha256']}
    if action['op'] == 'video.mask.keyframe':
        from windows_mask_controls import bound_mask
        bound_mask(action, timeline)
        from windows_mask_keyframes import verify_keyframe
        return verify_keyframe(action, timeline)
    segment = _target(action, timeline)
    refs = set(segment.get('extra_material_refs') or [])
    nodes = [node for node in timeline.get('materials', {}).get(entry['bucket'], []) if node.get('id') in refs]
    require(len(nodes) == 1 and entry_for_node(entry['bucket'], nodes[0])['key'] == entry['key'],
            'Native VFX preset did not round-trip')
    if entry['bucket'] == 'common_mask':
        return {'preset': entry['key'], 'bucket': entry['bucket'], 'material_id': nodes[0]['id'],
                'config': nodes[0]['config'], 'is_old_version': False, 'tree_sha256': entry['tree_sha256']}
    if entry['bucket'] == 'transitions':
        expected_duration = action.get('duration_ms')
        require(type(expected_duration) is int and nodes[0].get('duration') == expected_duration * 1000,
                'Native transition duration did not round-trip')
        context = _transition_context(action['segment_id'], timeline, nodes[0]['duration'], existing_id=nodes[0]['id'])
        return {'preset': entry['key'], 'bucket': entry['bucket'], 'material_id': nodes[0]['id'],
                'tree_sha256': entry['tree_sha256'], **context}
    expected = action.get('value', entry['default_value'])
    saved_value = nodes[0].get('value', 0 if entry['bucket'] == 'effects' else None)
    require(type(saved_value) in (int, float) and
            math.isclose(saved_value, expected, rel_tol=1e-7, abs_tol=1e-7),
            'Native VFX strength did not round-trip')
    return {'preset': entry['key'], 'bucket': entry['bucket'], 'material_id': nodes[0]['id'],
            'value': saved_value, 'tree_sha256': entry['tree_sha256']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, epilog=
        'For an editable resource-complete draft use: jianying vfx freeze-draft --draft-dir ... --out ...')
    parser.add_argument('command', nargs='?', choices=['catalog'], default='catalog')
    parser.parse_args(argv)
    # Runtime validation remains explicit: listing presets cannot silently claim
    # that the installed DLL/signature has passed the normal doctor command.
    rows = []
    for key, entry in catalog()['resources'].items():
        row = {'preset': key, 'title': entry['title'], 'kind': entry['bucket'], 'tree_sha256': entry['tree_sha256']}
        if entry['bucket'] == 'transitions':
            row['duration_ms_values'] = entry['duration_ms_values']
            row['compatibility_adapter'] = entry.get('compatibility_adapter', False)
            if 'resource_revision' in entry:
                row['resource_revision'] = entry['resource_revision']
                row['paused_player_supported'] = entry['paused_player_supported']
                row['legacy_resource_trees'] = [old['tree_sha256'] for old in entry.get('legacy_resources', [])]
        elif entry['bucket'] == 'common_mask':
            from windows_mask_controls import FIELDS, DEFAULTS
            from windows_mask_keyframes import PROPERTIES
            row['config_ranges'] = {field: list(row[1:]) for field, row in FIELDS.items()}
            if entry['key'] == 'mask/circle':
                row['config_ranges']['feather'] = [0, 0]
            row['default_config'] = DEFAULTS
            row['keyframe_ranges'] = {field: list(spec[1:]) for field, spec in PROPERTIES.items()}
            if entry['key'] == 'mask/circle':
                row['keyframe_ranges'].pop('feather', None)
        else:
            row['value_range'] = entry['value_range']
        try:
            row['path'] = str(resource_path(key)); row['resource_status'] = 'verified'
        except (OSError, ValueError) as error:
            row['resource_status'] = 'unavailable'; row['error'] = str(error)
        rows.append(row)
    print(json.dumps({'schema': 'jy-windows-vfx-readiness/v1', 'app_build': '11.4.7.14462',
                      'runtime_validation': 'run doctor before native operations', 'presets': rows},
                     ensure_ascii=False, indent=2))
    return 0 if all(row['resource_status'] == 'verified' for row in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
