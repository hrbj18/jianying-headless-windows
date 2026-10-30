"""Reviewed circle geometry and narrow saved-draft reconciliation.

Public center values use half-canvas coordinates: +X is right and +Y is up.
Feather is the native normalized control, not a pixel radius.
"""
from __future__ import annotations

from copy import deepcopy
import math
from pathlib import Path
import re

FIELDS = {'width': ('width', .05, 1), 'height': ('height', .05, 1),
          'center_x': ('centerX', -1, 1), 'center_y': ('centerY', -1, 1),
          'feather': ('feather', 0, 1)}
DEFAULTS = {'width': .65, 'height': .65, 'center_x': 0, 'center_y': 0, 'feather': 0}
FIXED = {'rotation': 0, 'roundCorner': 0, 'aspectRatio': 1, 'expansion': 0}
PRESETS = {'mask/circle': 'REA-circle', 'mask/circle-soft': 'REA-circle-soft'}


def require(value, message):
    if not value:
        raise ValueError(message)


def number(value, low, high, label):
    require(type(value) in (int, float) and math.isfinite(value) and low <= value <= high,
            label + ' must be a finite number in ' + str((low, high)))
    return value


def public_config(config, *, complete=False):
    require(isinstance(config, dict) and not set(config) - set(FIELDS),
            'Unsupported circle mask config fields')
    for field, value in config.items():
        number(value, *FIELDS[field][1:], 'Mask ' + field)
    return {**DEFAULTS, **config} if complete else dict(config)


def native_values(config):
    return {FIELDS[field][0]: value for field, value in config.items()}


def validate_native_config(config, *, allow_feather=False):
    require(isinstance(config, dict) and not set(config) -
            ({row[0] for row in FIELDS.values()} | set(FIXED) | {'invert'}),
            'Unreviewed circle mask geometry fields')
    for public, (field, low, high) in FIELDS.items():
        value = config.get(field, DEFAULTS[public] if field not in {'width', 'height'} else None)
        number(value, low, high, 'Native mask ' + field)
    require(allow_feather or config.get('feather', 0) == 0,
            'Legacy circle resources do not render soft feather; use mask/circle-soft')
    for field, expected in FIXED.items():
        value = config.get(field, expected)
        require(type(value) in (int, float) and math.isfinite(value) and value == expected,
                'Unreviewed circle mask fixed geometry: ' + field)
    require(type(config.get('invert', False)) is bool and not config.get('invert', False),
            'Circle mask inversion is not reviewed')
    return config


def matches(config, wanted):
    return all(type(config.get(field, 0)) in (int, float) and
               math.isclose(config.get(field, 0), value, rel_tol=1e-7, abs_tol=1e-7)
               for field, value in wanted.items())


def bound_mask(action, timeline, *, allow_legacy=False):
    import windows_vfx as vfx
    segment = vfx._target(action, timeline)
    refs = segment.get('extra_material_refs') or []
    nodes = [node for node in timeline.get('materials', {}).get('common_mask', []) if node.get('id') in refs]
    require(len(nodes) == 1 and refs.count(nodes[0]['id']) == 1, 'Expected one bound circle mask')
    candidate = deepcopy(nodes[0])
    if allow_legacy:
        require(type(candidate.get('is_old_version', False)) is bool, 'Ambiguous mask protocol flag')
        candidate['is_old_version'] = False
    preset = action.get('preset', 'mask/circle')
    require(preset in PRESETS, 'Unknown reviewed circle preset')
    if allow_legacy and preset == 'mask/circle-soft':
        entry = vfx.catalog()['resources'][preset]
        require(vfx._shape_matches('common_mask', candidate, entry), 'Unreviewed modern circle material shape')
        try:
            vfx.verify_resource(candidate['path'], entry)
        except ValueError:
            # Official mask.add only supports Vimo and resolves this old circle.
            # Admit its exact captured bytes solely for the audited path binding.
            vfx.verify_resource(candidate['path'], vfx.catalog()['resources']['mask/circle'])
            candidate['path'] = str(vfx.resource_path(preset))
    require(vfx.entry_for_node('common_mask', candidate)['key'] == preset,
            'Mask preset differs from the bound reviewed resource')
    return segment, nodes[0]


def _unanimated_fields(segment, mask, config):
    from windows_mask_keyframes import PROPERTIES
    requested = {PROPERTIES[field.replace('_', '-')][0] for field in config}
    require(not any(group.get('material_id') == mask['id'] and group.get('property_type') in requested
                    for group in segment.get('common_keyframes', [])),
            'Mask config field is animated; use video.mask.keyframe for that property')


def compile_geometry(action, timeline, ref, *, temporal=True):
    import windows_vfx as vfx
    op = action.get('op')
    require(op in {'video.mask.set', 'video.mask.update'}, 'Unsupported mask geometry action')
    required = {'op', 'segment_id', 'preset'}
    require(required <= set(action) <= required | {'config'} and action['preset'] in PRESETS,
            'Missing or unsupported circle mask action fields')
    require(isinstance(ref, str) and re.fullmatch(r'local://[A-Za-z0-9][A-Za-z0-9_.-]*', ref),
            'Mask edit requires an explicit ASCII local draft reference')
    segment = vfx._target(action, timeline)
    if temporal and op == 'video.mask.set':
        refs = segment.get('extra_material_refs') or []
        require(not any(node.get('id') in refs for node in timeline.get('materials', {}).get('common_mask', [])),
                'Target already has a mask; use video.mask.update')
    config = public_config(action.get('config', {}), complete=op == 'video.mask.set')
    require(action['preset'] == 'mask/circle-soft' or config.get('feather', 0) == 0,
            'Legacy circle resources do not render soft feather; use mask/circle-soft')
    if op == 'video.mask.update':
        require(config, 'Mask update requires at least one config field')
    argv = ['draft', 'video', 'mask', 'add' if op == 'video.mask.set' else 'update',
            '--ref', ref, '--seg-id', action['segment_id']]
    if op == 'video.mask.set':
        argv += ['--resource', 'vimo://7356934080102928946', '--resource-type', 'circle',
                 '--name', PRESETS[action['preset']]]
    elif temporal:
        segment, mask = bound_mask(action, timeline)
        _unanimated_fields(segment, mask, config)
        argv += ['--mask-id', mask['id']]
    else:
        # Preflight validates a batch before a preceding set action has committed.
        argv += ['--mask-id', 'resolved-at-execution']
    for field, value in config.items():
        argv += ['--' + field.replace('_', '-'), format(value, '.12g')]
    return argv


def verify_geometry(action, timeline):
    segment, mask = bound_mask(action, timeline)
    public = public_config(action.get('config', {}), complete=action['op'] == 'video.mask.set')
    if action['op'] == 'video.mask.update':
        _unanimated_fields(segment, mask, public)
    expected = native_values(public)
    require(matches(mask['config'], expected), 'Native mask geometry did not round-trip')
    return {'preset': action['preset'], 'bucket': 'common_mask', 'material_id': mask['id'],
            'config': mask['config'], 'is_old_version': False}


def reconcile_after_cli(action, source, audit_prefix, runtime):
    """Admit only the requested circle fields, preserving unrelated main content.

    CLI writes can differ on historical draft layouts without project.json. A
    root candidate is accepted only when its exact target and requested values
    validate; the whole root timeline is never copied over the selected main.
    """
    from windows_timeline_patch import commit
    import native_export as native
    import windows_vfx as vfx
    expected = native_values(public_config(action.get('config', {}), complete=action['op'] == 'video.mask.set'))
    def mutate(timeline, source):
        segment = vfx._target(action, timeline)
        refs = segment.get('extra_material_refs') or []
        if any(node.get('id') in refs for node in timeline.get('materials', {}).get('common_mask', [])):
            _, observed = bound_mask(action, timeline, allow_legacy=True)
        else:
            observed = None
        if observed is None or not matches(observed['config'], expected):
            require(not (source / 'Timelines' / 'project.json').exists(),
                    'CLI mask values did not reach the declared main timeline; refusing a root fallback')
            root = source / 'draft_content.json'
            require(root.is_file() and not root.is_symlink() and root.resolve().is_relative_to(source),
                    'CLI mask result is absent from the selected main and no regular root candidate exists')
            mirror = native.j.nd.helper()._decrypt_metadata_in_memory(root)
            mirror_segment, candidate = bound_mask(action, mirror, allow_legacy=True)
            require(all(mirror_segment.get(field) == segment.get(field) for field in
                        ('id', 'material_id', 'source_timerange', 'target_timerange')),
                    'CLI mask candidate targets a different segment or timerange')
            require(matches(candidate['config'], expected), 'CLI root mask values differ from the requested action')
            if action['op'] == 'video.mask.update':
                require(observed is not None and candidate['id'] == observed['id'],
                        'Mask update changed the bound material identity')
            selected = candidate
            observed_from = 'validated-root-candidate'
        else:
            selected = observed
            observed_from = 'selected-main'
        if observed is None:
            require(action['op'] == 'video.mask.set', 'Mask update requires an existing circle')
            identities = [node.get('id') for nodes in timeline.get('materials', {}).values() for node in nodes]
            require(selected['id'] not in identities, 'New circle mask ID collides with an existing material')
            changed = deepcopy(selected)
            timeline['materials'].setdefault('common_mask', []).append(changed)
            segment.setdefault('extra_material_refs', []).append(changed['id'])
        else:
            changed = observed
        changed['config'].update(expected)
        changed['is_old_version'] = False
        resource_binding = None
        if action['preset'] == 'mask/circle-soft':
            entry = vfx.catalog()['resources'][action['preset']]
            try:
                vfx.verify_resource(changed['path'], entry)
            except ValueError:
                vfx.verify_resource(changed['path'], vfx.catalog()['resources']['mask/circle'])
                resource_binding = {'before': changed['path'], 'after': str(vfx.resource_path(action['preset']))}
                changed['path'] = resource_binding['after']
        vfx.entry_for_node('common_mask', changed)
        return {'segment_id': action['segment_id'], 'mask_id': changed['id'],
                'observed_from': observed_from, 'config_fields': expected, 'is_old_version': False,
                'modern_resource_binding': resource_binding}
    return commit(source, audit_prefix, runtime, 'mask-controls', mutate)
