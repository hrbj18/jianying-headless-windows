#!/usr/bin/env python3
"""Export a verified, immutable build with Jianying's local native renderer.

Only an explicit export command invokes this module. It creates a new private
job, never writes a live draft, and cannot access accounts or the network.
"""
import argparse
from copy import deepcopy
from fractions import Fraction
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

import jy14_headless as j
import native_edit as edit
import native_fonts as fonts
import native_motion as motion
import native_resources as resources
import native_compound as compound
import native_color
import native_audio_processing
import windows_vfx
import media_store
from runtime_profiles import (EXPORT_PROFILES, WINDOWS_1147_PROFILE,
                              validate_export_profiles, validate_timeline_schema)

HERE = Path(__file__).resolve().parent
SCHEMA = 'jy14-native-export/v1'


def captured_mask(node):
    """Only the six captured static mask identities and parameter kinds."""
    catalog = resources.catalog()['resources']
    shapes = {catalog['mask/' + shape]['material']['resource_type']: shape for shape in resources.SHAPES}
    native_type = node.get('resource_type')
    j.require(isinstance(native_type, str) and native_type in shapes, 'Unverified native mask shape')
    shape = shapes[native_type]
    entry = catalog['mask/' + shape]
    j.require(all(node.get(key) == entry['material'][key]
                  for key in ('type', 'category', 'category_id', 'resource_type', 'resource_id')),
              'Unverified native mask resource identity')
    config = node.get('config', {})
    mapping = {'centerX': 'x', 'centerY': 'y', 'width': 'width', 'height': 'height',
               'rotation': 'rotation', 'feather': 'feather', 'invert': 'invert', 'roundCorner': 'round_corner'}
    j.require(isinstance(config, dict) and not set(config) - (set(mapping) | {'aspectRatio'}),
              'Unverified native mask parameter')
    aspect = config.get('aspectRatio', entry['aspect_ratio'])
    j.number(aspect, 'Mask aspect ratio', 0.001, 100)
    j.require(math.isclose(aspect, entry['aspect_ratio'], abs_tol=1e-7), 'Unverified mask aspect ratio')
    spec = {'shape': shape, **{target: config[key] for key, target in mapping.items() if key in config
                              and not (shape == 'line' and key in {'width', 'height'})}}
    motion.validate({'mask': spec}, 'video')
    return entry


def captured_video_effect(node):
    """Only the non-member light-shake capture has isolated pixel evidence."""
    entry = resources.definition('effect/light-shake')
    j.require(entry['usage']['paid_badge_observed'] is False, 'Member effect isolation is not verified')
    template = entry['material']
    for field in ('type', 'effect_id', 'resource_id', 'source_platform', 'apply_target_type', 'category_id'):
        j.require(node.get(field) == template[field], 'Unverified native video effect identity: ' + field)
    j.require(type(node.get('value')) in (int, float) and node['value'] == 1,
              'Unverified native video effect strength')
    expected = {item['name'] for item in template['adjust_params']}
    params = node.get('adjust_params', [])
    j.require(isinstance(params, list) and len(params) == len(expected) and
              all(isinstance(p, dict) and isinstance(p.get('name'), str) and
                  set(p) <= {'name', 'value', 'default_value'} for p in params) and
              {p.get('name') for p in params} == expected, 'Unverified native video effect parameters')
    for param in params:
        j.number(param.get('value'), 'Native video effect parameter', 0, 1)
    return entry


def captured_filter_or_text_effect(node):
    """Retired resources must fail, including in older frozen snapshots."""
    raise ValueError('Native filter/text effect support has been removed; do not silently omit effects')


def check_filter_and_text_bindings(timeline):
    materials = timeline.get('materials', {})
    effects = materials.get('effects', [])
    filters = {n.get('id'): n for n in effects if n.get('type') == 'filter'}
    flowers = {n.get('id'): n for n in effects if n.get('type') == 'text_effect'}
    j.require(None not in filters and None not in flowers, 'Missing filter/text effect material ID')
    texts = {n.get('id'): n for n in materials.get('texts', [])}
    used_filters, used_flowers = set(), set()
    for track in timeline.get('tracks', []):
        for segment in track.get('segments', []):
            primary = segment.get('material_id')
            refs = set(segment.get('extra_material_refs') or [])
            if track.get('type') == 'filter':
                j.require(primary in filters and not refs.intersection(filters),
                          'Filter track must bind the captured filter as its primary material')
                j.require(not segment.get('common_keyframes'), 'Filter keyframes are not yet verified')
                used_filters.add(primary)
            else:
                j.require(primary not in filters and not refs.intersection(filters),
                          'Captured filter is only verified on a filter track')
            flower_refs = refs.intersection(flowers)
            j.require(primary not in flowers, 'Text effect must be an extra reference on a text segment')
            if track.get('type') != 'text':
                j.require(not flower_refs, 'Captured text effect requires a text segment')
                continue
            material = texts.get(primary)
            j.require(material is not None, 'Text segment has no text material')
            content = j.nd.helper()._parse_strict_json(material.get('content', '').encode('utf-8'), 'native text content')
            styles = content.get('styles', [])
            if not flower_refs:
                j.require(all(not s.get('effectStyle') for s in styles), 'Text effect style has no captured material binding')
                continue
            j.require(len(flower_refs) == 1 and styles, 'Ambiguous or missing captured text effect style')
            node = flowers[next(iter(flower_refs))]
            for style in styles:
                effect_style = style.get('effectStyle', {})
                j.require(effect_style == {'id': node['resource_id'], 'path': node.get('path')},
                          'Text effect style identity/path differs from its captured material')
                fill = style.get('fill', {})
                fill_content = fill.get('content', {})
                solid = fill_content.get('solid', {})
                color = solid.get('color', [])
                j.require(fill_content.get('render_type') == 'solid' and len(color) == 3
                          and all(type(v) in (int, float) and abs(v - 1) < 1e-5 for v in color)
                          and fill.get('alpha', 1) == solid.get('alpha', 1) == 1 and not style.get('strokes'),
                          'Unverified text effect base fill or stroke')
            used_flowers.update(flower_refs)
    j.require(used_filters == set(filters) and used_flowers == set(flowers),
              'Captured filter/text effect has no verified track binding')


def local_supported_features(timeline, *, validated_audio_fades=False, validated_windows_vfx=False,
                             validated_speed_curves=False, validated_audio_processing=False,
                             validated_color=False, validated_adjustments=False):
    """Fail closed on effects that this isolated rendering path has not passed."""
    materials = timeline.get('materials', {})
    if not validated_windows_vfx:
        for node in materials.get('common_mask', []):
            captured_mask(node)
        for node in materials.get('video_effects', []):
            captured_video_effect(node)
        captured_visuals = {captured_filter_or_text_effect(node)[0] for node in materials.get('effects', [])}
        check_filter_and_text_bindings(timeline)
    else:
        captured_visuals = set()  # Windows resources were independently checked by windows_vfx.
    allowed = {'videos', 'audios', 'texts', 'canvases', 'beats', 'material_animations',
               'placeholder_infos', 'speeds', 'sound_channel_mappings', 'material_colors',
               'loudnesses', 'vocal_separations', 'transitions', 'common_mask', 'drafts', 'video_effects', 'effects'}
    if validated_audio_fades:
        allowed.add('audio_fades')
    if validated_audio_processing:
        allowed.update({'realtime_denoises','audio_effects'})
    if validated_color:
        allowed.update(native_color.BUCKETS)
    if validated_adjustments:
        allowed.add('placeholders')
    unsupported = sorted(k for k, nodes in materials.items() if nodes and k not in allowed)
    j.require(not unsupported, 'Unverified native export material types: ' + ', '.join(unsupported))
    allowed_tracks={'video', 'text', 'audio', 'effect', 'filter'}|({'adjust'} if validated_adjustments else set())
    j.require(all(t.get('type') in allowed_tracks for t in timeline.get('tracks', [])),
              'Unverified native export track type')
    effect_ids = {node.get('id') for node in materials.get('video_effects', [])}
    for track in ([] if validated_windows_vfx else timeline.get('tracks', [])):
        if track.get('type') == 'effect':
            for segment in track.get('segments', []):
                j.require(segment.get('material_id') in effect_ids and segment.get('material_id') is not None,
                          'Effect track must bind the captured video effect')
                j.require(not segment.get('common_keyframes'), 'Video effect keyframes are not yet verified')
        else:
            for segment in track.get('segments', []):
                j.require(not effect_ids.intersection([segment.get('material_id')] + segment.get('extra_material_refs', [])),
                          'Captured video effect is only verified on an effect track')
    for node in materials.get('material_animations', []):
        j.require(not node.get('animations'), 'Text/clip animations are not yet verified for native headless export')
    for node in materials.get('speeds', []):
        j.require(validated_speed_curves or not node.get('curve_speed'), 'Curve speed export is not yet verified')
    if not validated_windows_vfx:
        for node in materials.get('transitions', []):
            j.require(node.get('effect_id') == '6724845717472416269', 'Only the captured dissolve transition is verified')
    for node in materials.get('canvases', []):
        j.require(node.get('type') == 'canvas_color', 'Only solid canvas backgrounds are verified')
    compound_ids = {node['id'] for node in materials.get('drafts', [])}
    compound_refs = {ref for track in timeline.get('tracks', []) for segment in track.get('segments', [])
                     if compound_ids.intersection(segment.get('extra_material_refs', []))
                     for ref in segment.get('extra_material_refs', [])}
    for node in materials.get('sound_channel_mappings', []):
        default_compound = node['id'] in compound_refs and node.get('type') == '' and not any(
            value for key, value in node.items() if key not in {'id', 'type'})
        j.require(node.get('type') == 'none' or default_compound, 'Custom audio channel mappings are not yet verified')
    warnings = []
    if materials.get('transitions') and not validated_windows_vfx:
        warnings.append({
            'code': 'native-dissolve-audio-overlap',
            'message': 'Dissolve video is verified, but source audio can sum across the overlap; '
                       'two same-phase source tones measured +6.03 dB. Review output audio; no gain correction is applied.',
            'native_ui_audio_comparison': 'matched on the same synthetic timeline; +6.019 dB UI vs +6.030 dB headless',
        })
    if materials.get('video_effects') and not validated_windows_vfx:
        warnings.append({'code': 'native-resource-use-limits',
                         'resource': 'effect/light-shake',
                         'message': 'Isolated rendering is verified on the captured non-member sample; '
                                    'this does not grant redistribution or establish commercial rights.'})
    for key in sorted(captured_visuals):
        usage = resources.definition(key)['usage']
        warnings.append({'code': 'native-resource-use-limits', 'resource': key, 'usage': usage,
                         'message': 'Technical rendering verified on the same-machine local sample after successful native UI export. '
                                    'This does not acquire or prove ongoing account entitlement, commercial rights, or redistribution rights. '
                                    'Use only within existing native authorization; account data is not read.'})
    return {'content_scope': 'local single-timeline video, text, audio, linear keyframes, captured dissolve, six static geometric masks and captured light-shake',
            'mask_export': 'six captured shapes verified on the synthetic sample; inspect each actual output',
            'visual_acceptance': 'requires viewing the exported output',
            'audio_acceptance': 'requires checking the exported audio; stream presence is not audio quality acceptance',
            'warnings': warnings}


def supported_features(timeline):
    # This feature-only helper also accepts partial noncompound fixtures. Full
    # structural validation remains mandatory in verified_build before export.
    rows = compound.validate(timeline, edit.basic_validation) if timeline.get('materials', {}).get('drafts') else [(None, timeline)]
    result = local_supported_features(timeline)
    for owner, child in rows[1:]:
        child_result = local_supported_features(child)
        result['warnings'].extend({**warning, 'timeline_id': child['id']} for warning in child_result['warnings'])
    result['nested_timelines'] = len(rows) - 1
    if len(rows) > 1:
        result['content_scope'] += '; captured editable local combination compounds, with every child checked'
    return result


def captured_audio_fades(timeline):
    """Validate only the local 11.4.7 official audio_fade shape observed in Lyra.

    This is a structural gate. A successful native render and an audio-envelope
    measurement are separate evidence; unknown fade types/fields remain blocked.
    """
    materials = timeline.get('materials', {})
    rows = materials.get('audio_fades', [])
    j.require(isinstance(rows, list), 'Audio fades must be a material list')
    fades = {}
    for node in rows:
        j.require(isinstance(node, dict) and set(node) == {
            'id', 'type', 'fade_type', 'fade_in_duration', 'fade_out_duration'},
            'Unverified audio fade fields')
        identity = node['id']
        j.require(isinstance(identity, str) and identity and identity not in fades,
                  'Audio fade material IDs must be nonempty and unique')
        j.require(node['type'] == 'audio_fade' and type(node['fade_type']) is int and node['fade_type'] == 4,
                  'Unverified audio fade type')
        for field in ('fade_in_duration', 'fade_out_duration'):
            j.require(type(node[field]) is int and 0 <= node[field] <= 43_200_000_000,
                      'Audio fade duration must be bounded nonnegative integer microseconds')
        fades[identity] = node
    used = set()
    audio_ids = {node.get('id') for node in materials.get('audios', [])}
    for track in timeline.get('tracks', []):
        for segment in track.get('segments', []):
            j.require(segment.get('material_id') not in fades, 'Audio fade cannot be a primary material')
            refs = segment.get('extra_material_refs') or []
            matching = [ref for ref in refs if ref in fades]
            if not matching:
                continue
            j.require(track.get('type') == 'audio' and segment.get('material_id') in audio_ids,
                      'Audio fade requires an audio segment binding')
            j.require(len(matching) == 1, 'An audio segment must bind exactly one fade material')
            span = segment.get('target_timerange', {}).get('duration')
            node = fades[matching[0]]
            j.require(type(span) is int and span > 0 and
                      node['fade_in_duration'] + node['fade_out_duration'] <= span,
                      'Audio fade durations must fit the target segment without overlap')
            used.update(matching)
    j.require(used == set(fades), 'Audio fade material has no valid segment reference')
    return len(fades)


def windows_supported_features(timeline, record, runtime=None):
    """仅放行当前已审核 Windows ABI 的基础成片范围。"""
    materials = timeline.get('materials', {})
    profile = (runtime or record.get('runtime') or {}).get('runtime_profile', record.get('runtime_profile'))
    extensions_reviewed = profile == WINDOWS_1147_PROFILE
    if not extensions_reviewed:
        for node in materials.get('effects', []):
            captured_filter_or_text_effect(node)
    blocked = ('drafts',) if extensions_reviewed else ('drafts', 'audio_effects')
    if not extensions_reviewed:
        blocked += ('video_effects', 'transitions', 'common_mask')
    present = [name for name in blocked if materials.get(name)]
    j.require(not present, 'Windows 原生导出尚未验收这些材料类型: ' + ', '.join(present))
    if runtime and record.get('runtime_profile'):
        j.require(record['runtime_profile'] == profile, 'Build runtime differs from the installed editor')
    if record.get('font_assets'):
        j.require(extensions_reviewed, 'Windows 自定义字体仅在精确 11.4.7 运行时验收')
    assets = fonts.recorded_assets(record)
    if assets:
        j.require(all(asset.get('format') in {'ttf', 'otf'} for asset in assets),
                  'Windows 字体导出需要已解析的静态 TTF/OTF 依赖清单')
    if materials.get('audio_fades'):
        j.require(extensions_reviewed, 'Windows 音频淡化仅在精确 11.4.7 运行时验收')
    fade_count = captured_audio_fades(timeline)
    animation_ids = {node.get('id') for node in materials.get('material_animations', [])}
    for track in timeline.get('tracks', []):
        if track.get('type') == 'text':
            j.require(all(not animation_ids.intersection(segment.get('extra_material_refs', []))
                          for segment in track.get('segments', [])),
                      'Windows 原生文字不支持动画材料引用（含空占位）；请重新构建普通文字草稿')
    vfx_result = windows_vfx.validate_timeline(timeline, runtime or {
        'runtime_profile': profile, 'app_build': '11.4.7.14462'}) if extensions_reviewed else None
    import native_speed_curves
    curve_result = native_speed_curves.validate(timeline) if extensions_reviewed else None
    import native_audio_processing
    audio_result = native_audio_processing.validate(timeline) if extensions_reviewed else None
    result = local_supported_features(timeline, validated_audio_fades=extensions_reviewed,
                                      validated_windows_vfx=extensions_reviewed,
                                      validated_speed_curves=extensions_reviewed,
                                      validated_audio_processing=extensions_reviewed,
                                      validated_color=extensions_reviewed,
                                      validated_adjustments=bool(vfx_result and vfx_result['adjustment_tracks']['tracks']))
    version = (runtime or record.get('runtime') or {}).get('app_version', 'reviewed runtime')
    result.update(content_scope='Windows ' + version + ' fixed-ABI local single-timeline video, basic text and audio',
                  mask_export='not enabled on Windows', nested_timelines=0,
                  static_local_fonts=extensions_reviewed, audio_fade_materials=fade_count)
    if extensions_reviewed:
        result['content_scope'] += '; parsed static local TTF/OTF fonts and bound native audio fades (type 4)'
        result['windows_vfx'] = vfx_result
        result['color_adjustments'] = vfx_result['native_color']
        result['speed_curves'] = curve_result
        result['audio_processing'] = audio_result
        result['mask_export'] = 'reviewed circle geometry and per-mask linear keyframes with builtin runtime'
        if vfx_result['masks']:
            from windows_mask_protocol import verify_builtin_runtime
            verify_builtin_runtime(runtime or record.get('runtime') or {})
    return result


def verified_build(path):
    path = Path(path).resolve(strict=True)
    record = j.read_json(path / 'build.json')
    if record.get('schema') == 'jy14-headless-build/v1':
        record = j.verify_build(path)
    elif record.get('schema') == edit.BUILD_SCHEMA:
        record = edit.verify_build(path)
    else:
        raise ValueError('Export requires a supported verified headless/edit build')
    j.require(record['runtime_profile'] in EXPORT_PROFILES, 'Export requires a reviewed build profile')
    timeline = j.nd.helper()._decrypt_metadata_in_memory(path / 'draft' / j.nd.TIMELINE_FILE)
    compound.validate(timeline, edit.basic_validation)
    j.require(timeline.get('duration', 0) > 0 and timeline.get('tracks'), 'Cannot export an empty timeline')
    return path, record, timeline


def source_in_build(raw, target, folder):
    """Map only draft-owned resources into the immutable build snapshot."""
    j.require(isinstance(raw, str) and raw, 'Missing export dependency path')
    resolved = j.native_media_path(raw, target)
    if not resolved.is_relative_to(target):
        import native_lut_candidates
        managed=native_lut_candidates.external_build_source(resolved,folder)
        if managed is not None:return managed
    j.require(resolved.is_relative_to(target), 'Export dependency is not draft-owned; materialize it first')
    relative = resolved.relative_to(target)
    j.require(relative.parts and relative.parts[0] == 'Resources', 'Export dependencies must be in Resources')
    source = folder / relative
    j.require(source.exists() and not source.is_symlink() and source.resolve().is_relative_to(folder),
              'Export dependency is missing, symlinked, or outside the build')
    return source, relative


def windows_build_supported_features(timeline, record, folder, runtime=None):
    """Inspect owned VFX bytes before the future homepage path exists.

    Only this capability-check copy is rebased. Build/publish identity and the
    dependency stager continue to use the original future draft-owned paths.
    """
    value = native_color.resolve_timeline_paths(timeline,Path(record['target']))
    for bucket in ('transitions', 'common_mask', 'video_effects', 'effects', 'audio_effects', 'realtime_denoises', *native_color.BUCKETS):
        for node in value.get('materials', {}).get(bucket, []):
            if node.get('path'):
                raw=str(native_color.resource_root(node)) if native_color.is_node(bucket,node) else node['path']
                source, _ = source_in_build(raw, Path(record['target']), Path(folder))
                if native_color.is_node(bucket,node):
                    extra={role:source_in_build(str(raw),Path(record['target']),Path(folder))[0]
                           for role,raw in native_color.lut_sources(node)}
                    native_color.rebase_node(node,source,dependency_destinations=extra)
                else:node['path'] = str(source)
    return windows_supported_features(value, record, runtime)


def _saved_vfx_source(raw, source):
    """Resolve saved spellings without resolving away a junction/traversal first."""
    j.require(isinstance(raw, str) and raw and '://' not in raw, 'Saved VFX requires a local resource path')
    if raw.startswith(j.DRAFT_PATH_TOKEN):
        relative = Path(raw[len(j.DRAFT_PATH_TOKEN):])
        j.require(not relative.is_absolute() and '..' not in relative.parts, 'Unsafe saved VFX resource traversal')
        candidate = Path(source) / relative
    else:
        candidate = Path(raw)
        j.require('..' not in candidate.parts, 'Unsafe saved VFX resource traversal')
        if not candidate.is_absolute():
            j.require(candidate.parts[:1] == ('Resources',), 'Saved VFX resource must be absolute or draft-owned')
            candidate = Path(source) / candidate
    return media_store.safe_path(candidate, directory=True)


def _saved_vfx_manifest(folder):
    """Strict read-only Unicode source inspection; renderer APIs stay ASCII-only."""
    folder = media_store.safe_path(folder, directory=True)
    files = {}
    for directory, names, filenames in os.walk(folder, followlinks=False):
        media_store.safe_path(directory, directory=True)
        for name in names:
            media_store.safe_path(Path(directory) / name, directory=True)
        for name in filenames:
            path = media_store.safe_path(Path(directory) / name, regular=True)
            info = path.stat()
            j.require(len(files) < 1024 and info.st_size <= 64 * 1024 * 1024,
                      'Saved VFX package exceeds the reviewed resource bounds')
            files[path.relative_to(folder).as_posix()] = {
                'size': info.st_size, 'sha256': media_store.verified_digest(path)}
    j.require(files, 'Saved VFX package is empty')
    return files


def _snapshot_saved_vfx(bucket, node, source, snapshot):
    """Copy exact source bytes into ASCII ownership, then use the usual verifier."""
    raw=str(native_color.resource_root(node)) if native_color.is_node(bucket,node) else node.get('path')
    original = _saved_vfx_source(raw, source)
    manifest = _saved_vfx_manifest(original)
    identity = windows_vfx.manifest_hash(manifest)
    relative = Path('Resources/native-export-vfx') / identity
    copied = media_store.safe_path(Path(snapshot) / relative, exists=False)
    j.require(str(copied).isascii(), 'Saved VFX dependency snapshot must be ASCII')
    if not copied.exists():
        copied.mkdir(parents=True, mode=0o700)
        for name, info in manifest.items():
            source_file = media_store.safe_path(original / name, regular=True)
            destination = copied / name
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            media_store.verified_digest(source_file, info['sha256'])
            with source_file.open('rb') as src, destination.open('xb') as dst:
                shutil.copyfileobj(src, dst)
                dst.flush()
                os.fsync(dst.fileno())
            media_store.verified_digest(destination, info['sha256'])
    # Full native shape, exact catalog identity and complete package hash remain
    # mandatory. No renderer or public VFX API receives the Unicode source path.
    if native_audio_processing.is_effect(bucket,node):
        entry=native_audio_processing.entry_for_node(bucket,node);native_audio_processing.verify_resource(copied,entry)
    elif native_color.is_node(bucket,node):
        entry=native_color.entry_for_node(bucket,node);native_color.verify_resource(copied,entry)
    else:
        entry = windows_vfx.entry_for_node(bucket, {**node, 'path': str(copied)})
        windows_vfx.verify_resource(copied, entry)
    j.require(manifest == entry['files'] and identity == entry['tree_sha256'] and
              _saved_vfx_manifest(original) == manifest,
              'Saved VFX source changed while creating its ASCII dependency snapshot')
    if native_color.is_node(bucket,node):
        entry=dict(entry,lut_dependencies=native_color.snapshot_lut_dependencies(node,copied))
    return original, relative, copied, entry


class SavedVfxSnapshots:
    """Reuse one verified copy per package in this operation only.

    Every node still receives full schema/binding validation. Recheck original
    bytes at the operation boundary; never persist a trusted hash cache.
    """
    def __init__(self,source,snapshot):
        self.source,self.snapshot=source,snapshot
        self.entries={}

    def get(self,bucket,node):
        raw=str(native_color.resource_root(node)) if native_color.is_node(bucket,node) else node.get('path')
        key=(bucket,node.get('type'),raw,node.get('path') if node.get('type')=='lut' else None)
        if key not in self.entries:
            self.entries[key]=(_snapshot_saved_vfx(bucket,node,self.source,self.snapshot),deepcopy(node))
        return self.entries[key][0]

    def verify_sources(self):
        checked=set()
        for (original,_,_,entry),node in self.entries.values():
            key=(str(original),entry['tree_sha256'])
            if key not in checked:
                j.require(_saved_vfx_manifest(original)==entry['files'],
                          'Saved VFX source changed during snapshot validation')
                checked.add(key)
            for extra in entry.get('lut_dependencies',[]):
                identity=(extra['role'],str(extra['source']),node['path'].split(';')[0] if extra['role']=='cube' else '')
                if identity not in checked:
                    j.require(native_color.verify_lut_dependency(extra['role'],extra['source'],node)==extra['files'],
                              'Saved LUT source changed during snapshot validation')
                    checked.add(identity)


def windows_saved_draft_supported_features(timeline, record, source, runtime):
    """Validate saved VFX through temporary verified ASCII copies, source read-only."""
    nodes = [(bucket, node) for bucket in ('transitions', 'common_mask', 'video_effects', 'effects', 'audio_effects', *native_color.BUCKETS)
             for node in timeline.get('materials', {}).get(bucket, [])]
    if not nodes:
        return windows_supported_features(timeline, record, runtime)
    value = native_color.resolve_timeline_paths(timeline,source)
    snapshots = []
    with tempfile.TemporaryDirectory(prefix='jy-saved-vfx-check-') as temporary:
        snapshot = media_store.safe_path(temporary, directory=True)
        j.require(str(snapshot).isascii(), 'Saved VFX validation requires an ASCII temporary directory')
        packages=SavedVfxSnapshots(source,snapshot)
        for bucket in ('transitions', 'common_mask', 'video_effects', 'effects', 'audio_effects', *native_color.BUCKETS):
            for node in value.get('materials', {}).get(bucket, []):
                original, _, copied, entry = packages.get(bucket,node)
                if native_color.is_node(bucket,node):native_color.rebase_node(node,copied)
                else:node['path'] = str(copied)
                snapshots.append({'source': str(original), 'preset': entry['key'],
                                  'tree_sha256': entry['tree_sha256'], 'source_verified_unchanged': True})
        packages.verify_sources()
        result = windows_supported_features(value, record, runtime)
    result['saved_vfx_source_policy'] = 'read-only source, exact-byte verified ASCII dependency snapshot'
    result['saved_vfx_source_checks'] = snapshots
    return result


def stage_timeline(timeline, record, folder, out, runtime=None):
    value = deepcopy(timeline)
    target = Path(record['target']).resolve()
    inactive_markers={}
    if j.nd.IS_WINDOWS and (runtime or {}).get('runtime_profile')==WINDOWS_1147_PROFILE:
        import native_adjustment_track
        inactive_markers=native_adjustment_track.inactive_feature_markers(value,target,
            resolve_resource=lambda path:source_in_build(str(path),target,folder)[0])
    files, mapping, canonical_mapping = {}, {}, {}
    sidecars = []
    media_materialization = []
    package_manifests={}
    lut_dependency_manifests={}

    def copy_file(relative, info, immutable_media=False):
        copied = out / relative
        source = folder / relative
        j.require(record['files'].get(str(relative)) == info, 'Export resource differs from the verified build manifest')
        if str(relative) in files:
            j.require(files[str(relative)] == info, 'Repeated dependency fingerprint differs')
            return
        if immutable_media and j.nd.IS_WINDOWS:
            media_materialization.append(media_store.materialize_immutable(source, copied, info['sha256']))
        elif not copied.exists():
            copied.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with source.open('rb') as src, copied.open('xb') as dst:
                shutil.copyfileobj(src, dst)
            os.chmod(copied, 0o600)
        j.require(j.nd.digest(copied) == info['sha256'] == j.nd.digest(source), 'Export dependency changed while copying')
        files[str(relative)] = info

    graph = list(compound.graph(value)) if value.get('materials', {}).get('drafts') else [(None, value)]
    nodes = [(bucket, node) for _, timeline_node in graph
             for bucket in ('videos', 'audios', 'common_mask', 'transitions', 'video_effects', 'audio_effects', 'effects', 'realtime_denoises', *native_color.BUCKETS)
             for node in timeline_node.get('materials', {}).get(bucket, [])]
    # Fonts are draft-owned dependencies outside the media-library buckets.
    font_assets = fonts.recorded_assets(record)
    if font_assets is not None:
        fonts.verify_assets(font_assets, value, target, folder)
    for asset in font_assets or ():
        if j.nd.IS_WINDOWS:
            j.require((runtime or {}).get('runtime_profile') == WINDOWS_1147_PROFILE,
                      'Windows local font staging requires the reviewed 11.4.7 runtime')
            parsed = fonts.inspect_font(folder / asset['relative'])
            j.require(parsed['sha256'] == asset['sha256'] and parsed['size'] == asset['size'] and
                      parsed['format'] == asset.get('format'), 'Staged static font differs from its parsed inventory')
        raw = str(target / asset['relative'])
        source, relative = source_in_build(raw, target, folder)
        copy_file(relative, {'sha256': asset['sha256'], 'size': asset['size']})
        mapping[raw] = str(out / relative)
        canonical_mapping[str(j.native_media_path(raw, target))] = str(out / relative)
    for bucket, node in nodes:
        raw = node.get('path')
        if not raw:
            continue
        resource_raw=str(native_color.resource_root(node)) if native_color.is_node(bucket,node) else raw
        source, relative = source_in_build(resource_raw, target, folder)
        destination = out / relative
        if source.is_dir():
            if str(source) not in package_manifests:
                package_manifests[str(source)]=resources.tree_manifest(source)
            manifest=package_manifests[str(source)]
            if native_audio_processing.is_effect(bucket,node):
                entry=native_audio_processing.entry_for_node(bucket,node);native_audio_processing.verify_resource(source,entry)
                j.require(manifest==entry['files'],'Native audio-effect resource bytes changed')
            elif native_color.is_node(bucket,node):
                # Build paths name the future live draft, not this immutable
                # snapshot. Resolve the complete material before choosing a
                # path-dependent resource identity, just as capability checks
                # do. Never attest bytes from a nonexistent virtual path.
                checked=deepcopy(node)
                extras={role:source_in_build(str(raw),target,folder)[0]
                        for role,raw in native_color.lut_sources(node)}
                native_color.rebase_node(checked,source,extras)
                entry=native_color.entry_for_node(bucket,checked)
                j.require(manifest==entry['files'],'Native color export resource bytes changed')
            elif j.nd.IS_WINDOWS and (runtime or {}).get('runtime_profile') == WINDOWS_1147_PROFILE:
                entry = windows_vfx.entry_for_node(bucket, {**node, 'path': str(source)})
                j.require(manifest == entry['files'], 'Windows VFX export resource bytes changed')
            elif bucket == 'common_mask':
                j.require(manifest == captured_mask(node)['files'],
                          'Mask export resource bytes differ from the captured native resource')
            elif bucket == 'video_effects':
                j.require(manifest == captured_video_effect(node)['files'],
                          'Video effect export resource bytes differ from the captured native resource')
            elif bucket == 'effects':
                j.require(manifest == captured_filter_or_text_effect(node)[1]['files'],
                          'Filter/text effect export resource bytes differ from the captured native resource')
            expected = {str(relative / name): info for name, info in manifest.items()}
        else:
            j.require(bucket not in {'common_mask', 'video_effects', 'effects', *native_color.BUCKETS},
                      'Native visual resources must be captured directories')
            expected = {str(relative): {'sha256': j.nd.digest(source), 'size': source.stat().st_size}}
        j.require(all(record['files'].get(name) == info for name, info in expected.items()),
                  'Export resource differs from the verified build manifest')
        for name, info in expected.items():
            copy_file(Path(name), info, immutable_media=bucket in {'videos', 'audios'})
        if native_color.is_node(bucket,node):
            for role,raw_dependency in native_color.lut_sources(node):
                dep_source,dep_relative=source_in_build(str(raw_dependency),target,folder)
                dep_key=(role,str(dep_source),node['path'].split(';')[0] if role=='cube' else '')
                if dep_key not in lut_dependency_manifests:
                    lut_dependency_manifests[dep_key]=native_color.verify_lut_dependency(role,dep_source,node)
                dep_files=lut_dependency_manifests[dep_key]
                dep_destination=native_color.lut_destination(node,destination,role)
                j.require(out/dep_relative==dep_destination,'LUT snapshot layout is not the reviewed owned dependency layout')
                for name,info in dep_files.items():
                    relative_file=dep_relative/name
                    j.require(record['files'].get(str(relative_file))==info,'LUT dependency differs from build manifest')
                    copy_file(relative_file,info)
        if native_color.is_node(bucket,node):mapping.update(native_color.rebased_paths(node,destination))
        else:mapping[raw] = str(destination)
        canonical_mapping[str(j.native_media_path(resource_raw, target))] = str(destination)
        if native_color.is_node(bucket,node) and node.get('lumi_hub_path'):
            lumi=node['lumi_hub_path'];mapped=str(destination/native_color.lumi_relative(node))
            mapping[lumi]=mapped;canonical_mapping[str(j.native_media_path(lumi,target))]=mapped

    for owner, child in graph:
        if owner is None:
            continue
        for key, source_path in compound.paths(owner, target).items():
            relative = source_path.relative_to(target)
            source = folder / relative
            j.require(source.is_file() and not source.is_symlink() and source.resolve().is_relative_to(folder.resolve()),
                      'Missing or unsafe compound export sidecar')
            info = {'sha256': j.nd.digest(source), 'size': source.stat().st_size}
            j.require(record['files'].get(str(relative)) == info, 'Compound sidecar differs from the verified build')
            mapping[owner[key]] = str(out / relative)
            canonical_mapping[str(source_path)] = str(out / relative)
            if key == 'draft_cover_path':
                copy_file(relative, info)
            else:
                sidecars.append((relative, j.read_json(source), info))

    def replace(item, key='', sidecar_base=None):
        if isinstance(item, dict):
            marker=inactive_markers.get(item.get('id'))
            if marker is not None:
                j.require(item.get('type')=='color_match' and
                          item.get('color_match_info')=={'source_feature_path':marker},
                          'Native inactive color-match marker changed while staging')
            result = {k: deepcopy(v) if marker is not None and k=='color_match_info'
                      else replace(v, k, sidecar_base) for k, v in item.items()}
            if item.get('type') == 'text' and isinstance(item.get('content'), str):
                content = j.nd.helper()._parse_strict_json(item['content'].encode('utf-8'), 'native text content')
                j.require(isinstance(content, dict) and isinstance(content.get('styles'), list),
                          'Unsupported native text content')
                # Native effectStyle/font paths are inside serialized JSON,
                # not direct material fields. Keep its literal text unchanged.
                result['content'] = json.dumps(replace(content, sidecar_base=sidecar_base),
                                               ensure_ascii=False, separators=(',', ':'))
            return result
        if isinstance(item, list):
            return [replace(v, key, sidecar_base) for v in item]
        if isinstance(item, str):
            if key == 'text':
                return item
            if item in mapping:
                return mapping[item]
            # Text itself can contain URLs; do not confuse it with a dependency.
            if key.endswith('path') and item:
                if item.startswith(compound.SUBDRAFT_TOKEN):
                    filename = item[len(compound.SUBDRAFT_TOKEN):]
                    j.require(sidecar_base is not None and filename in compound.SIDECARS.values(), 'Unsafe subdraft placeholder')
                    return str(sidecar_base / filename)
                if sidecar_base is not None and item in compound.SIDECARS.values():
                    return str(sidecar_base / item)
                canonical = str(j.native_media_path(item, target))
                if canonical in canonical_mapping:
                    return canonical_mapping[canonical]
                path = Path(item)
                if j.nd.IS_WINDOWS:
                    install = Path((runtime or {}).get('install_dir', ''))
                    mac_prefix = '/Applications/VideoFusion-macOS.app/Contents/Resources/'
                    if item.startswith(mac_prefix) and install.is_absolute():
                        translated = install / 'Resources' / item[len(mac_prefix):]
                        j.require(translated.is_file() and translated.resolve().is_relative_to(install.resolve()),
                                  'Windows 内置资源不存在: ' + key)
                        return str(translated)
                    j.require(install.is_absolute() and path.is_absolute() and
                              path.resolve().is_relative_to(install.resolve()) and path.is_file(),
                              'Unstaged/unsupported export resource path: ' + key)
                else:
                    j.require(path.is_absolute() and path.is_relative_to(j.nd.APP) and path.is_file(),
                              'Unstaged/unsupported export resource path: ' + key)
            if key.endswith('url') and item:
                raise ValueError('Online dependency is not supported by isolated export')
        return item

    for relative, sidecar, info in sidecars:
        destination = out / relative
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        j.write(destination, replace(sidecar, sidecar_base=destination.parent))
        files[str(relative)] = {'sha256': j.nd.digest(destination), 'size': destination.stat().st_size}
        j.require(j.nd.digest(folder / relative) == info['sha256'], 'Compound source sidecar changed while staging')
    if media_materialization:
        j.write(out / 'media-materialization.json', {'schema': media_store.SCHEMA,
                'contract': media_store.IMMUTABLE_CONTRACT, 'files': media_materialization})
    return replace(value), files


def settings_for(timeline, bitrate, timeout):
    width, height = (timeline['canvas_config'][key] for key in ('width', 'height'))
    fps = timeline.get('fps', 30)
    for dimension in (width, height):
        j.require(type(dimension) is int and 16 <= dimension <= 7680 and dimension % 2 == 0,
                  'Native H.264 export requires even canvas dimensions, 16..7680')
    j.number(fps, 'Export fps', 1, 120)
    j.require(type(bitrate) is int and 100_000 <= bitrate <= 200_000_000, 'Bitrate must be 100000..200000000')
    j.require(type(timeout) is int and 5 <= timeout <= 43200, 'Timeout must be 5..43200 seconds')
    return dict(width=width, height=height, fps=fps, bitrate=bitrate, timeout_seconds=timeout)


def sandbox_profile(out):
    literal = json.dumps(str(out))
    return ('(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n'
            '(deny file-read-data (subpath "/Users"))\n'
            '(deny file-read-data (subpath "/Library/Keychains"))\n'
            f'(allow file-read-data (subpath {literal}))\n'
            f'(allow file-write* (subpath {literal}))\n'
            '(allow file-write* (literal "/dev/null"))\n').encode()


def frame_count_bounds(duration_us, fps):
    """Preserve strict exact frames, accounting only for microsecond quantization.

    A 30fps boundary 875/30s rounds to 29166667us. The native writer can
    therefore emit ceil(875.00001)=876. This is distinct from a missing frame
    on an exactly representable boundary such as 33.2s (996 frames).
    """
    span = Fraction(duration_us, 1_000_000) * Fraction(str(fps))
    nearest = round(span)
    if span.denominator == 1:
        return nearest, nearest, nearest, 'exact-aligned'
    tolerance = Fraction(str(fps)) / 2_000_000
    if abs(span - nearest) <= tolerance:
        return nearest, max(nearest, math.ceil(span)), nearest, 'microsecond-quantized'
    return math.floor(span), math.ceil(span), nearest, 'adjacent-fractional'


def validate_probe(info, settings, duration_us, audio_expected):
    fmt = info.get('format', {})
    j.require(fmt.get('tags', {}).get('major_brand') in ('isom', 'mp41', 'mp42'),
              'Native output is not a standard MP4 container')
    video = [s for s in info.get('streams', []) if s.get('codec_type') == 'video']
    audio = [s for s in info.get('streams', []) if s.get('codec_type') == 'audio']
    j.require(len(video) == 1 and video[0].get('codec_name') == 'h264', 'Expected one H.264 stream')
    v = video[0]
    j.require((v.get('width'), v.get('height')) == (settings['width'], settings['height']), 'Export canvas changed')
    actual_fps = float(Fraction(v['r_frame_rate']))
    j.require(math.isclose(actual_fps, settings['fps'], abs_tol=0.001), 'Export frame rate changed')
    minimum_frames, maximum_frames, expected_frames, policy = frame_count_bounds(duration_us, settings['fps'])
    actual_frames = int(v.get('nb_frames', -999))
    j.require(minimum_frames <= actual_frames <= maximum_frames,
              f'Export frame count is incomplete or excessive: got {actual_frames}, '
              f'expected {minimum_frames}..{maximum_frames}; partial output is not a deliverable')
    actual_duration = float(fmt.get('duration', 0))
    j.require(math.isfinite(actual_duration) and abs(actual_duration - duration_us / 1_000_000) <=
              max(0.05, 1 / settings['fps']), 'Export duration changed')
    j.require(len(audio) <= 1 and (not audio_expected or len(audio) == 1), 'Expected native audio stream is missing')
    j.require(all(a.get('codec_name') == 'aac' for a in audio), 'Unexpected export audio codec')
    return {'duration_seconds': actual_duration, 'frames': int(v['nb_frames']),
            'expected_frames': expected_frames, 'frame_delta': int(v['nb_frames']) - expected_frames,
            'frame_count_policy': policy,
            'accepted_frame_range': [minimum_frames, maximum_frames],
            'duration_delta_seconds': round(actual_duration - duration_us / 1_000_000, 6),
            'width': v['width'], 'height': v['height'], 'fps': actual_fps,
            'video_codec': 'h264', 'audio_codec': 'aac' if audio else None,
            'major_brand': fmt['tags']['major_brand']}


def require_supported_platform():
    """仅允许已有精确运行时指纹和原生适配层的平台。"""
    j.require(sys.platform == 'darwin' or j.nd.IS_WINDOWS,
              '当前平台没有已审核的剪映原生导出适配层')


def run(build, out, bitrate=4_000_000, timeout=600):
    require_supported_platform()
    build, record, timeline = verified_build(build)
    # Reject unreviewed content before querying or starting a native runtime.
    windows_build_supported_features(timeline, record, build / 'draft') if j.nd.IS_WINDOWS else supported_features(timeline)
    settings_for(timeline, bitrate, timeout)
    runtime = j.nd.validate_runtime()
    validate_export_profiles(record['runtime_profile'], runtime['runtime_profile'])

    def verify_source():
        j.require(j.files_manifest(build / 'draft') == record['files'], 'Source build changed during export')

    return _run_export(build, out, timeline, record, runtime,
                       {'build': str(build), 'build_sha256': j.nd.digest(build / 'build.json')},
                       lambda job: stage_timeline(timeline, record, build / 'draft', job, runtime),
                       verify_source, 'source_build_unchanged', bitrate, timeout)


def read_draft(draft_dir, runtime):
    """Read one local timeline without synchronizing or modifying draft mirrors."""
    source = Path(draft_dir)
    j.require(source.is_absolute() and source.is_dir() and not source.is_symlink(),
              'Draft export requires an absolute regular draft directory')
    source = source.resolve(strict=True)
    before = j.files_manifest(source)
    project_path = source / 'Timelines/project.json'
    timeline_path = source / j.nd.TIMELINE_FILE
    if project_path.is_file():
        project = j.read_json(project_path)
        timeline_id = project.get('main_timeline_id')
        j.require(isinstance(timeline_id, str) and timeline_id and
                  Path(timeline_id).name == timeline_id and timeline_id not in ('.', '..') and
                  '/' not in timeline_id and '\\' not in timeline_id,
                  'Draft main timeline ID is invalid')
        active = [row for row in project.get('timelines', []) if not row.get('is_marked_delete')]
        j.require(len(active) == 1 and active[0].get('id') == timeline_id,
                  'Draft export currently requires one active timeline')
        nested = source / 'Timelines' / timeline_id / j.nd.TIMELINE_FILE
        if nested.is_file():
            timeline_path = nested
    else:
        candidates = list((source / 'Timelines').glob('*/' + j.nd.TIMELINE_FILE))
        j.require(len(candidates) <= 1, 'Draft main timeline is ambiguous')
        if candidates:
            timeline_path = candidates[0]
    j.require(timeline_path.is_file() and not timeline_path.is_symlink(), 'Draft timeline file is missing')
    timeline = j.nd.helper()._decrypt_metadata_in_memory(timeline_path)
    validate_timeline_schema(timeline, runtime['runtime_profile'])
    if project_path.is_file():
        j.require(timeline.get('id') == timeline_id, 'Draft main timeline identity differs')
    compound.validate(timeline, edit.basic_validation)
    j.require(timeline.get('duration', 0) > 0 and timeline.get('tracks'), 'Cannot export an empty timeline')
    j.require(j.files_manifest(source) == before, 'Source draft changed while reading')
    relative = str(timeline_path.relative_to(source))
    root_info = before.get(j.nd.TIMELINE_FILE)
    return source, before, timeline, {
        'source_draft': str(source), 'source_timeline': relative,
        'source_timeline_sha256': before[relative]['sha256'],
        'root_mirror_differs': bool(root_info and root_info != before[relative]),
        'timeline_selection': 'declared main timeline, then single timeline, then root',
    }


def stage_draft_timeline(timeline, source, out, runtime, dependencies):
    """Materialize local media, then use the verified-build dependency stager."""
    source, out = Path(source).resolve(strict=True), Path(out).resolve(strict=True)
    value = native_color.resolve_timeline_paths(timeline,source)
    snapshot = out / 'source-snapshot'
    snapshot.mkdir(mode=0o700)
    mapping = {}
    font_assets = {}
    media_materialization = []
    for bucket in ('videos', 'audios', 'realtime_denoises'):
        for node in value.get('materials', {}).get(bucket, []):
            raw = node.get('path')
            if not raw:
                continue
            if raw in mapping:
                continue
            j.require(isinstance(raw, str) and '://' not in raw, 'Draft export requires local media paths')
            original = j.regular_file(j.native_media_path(raw, source))
            info = {'sha256': j.nd.digest(original), 'size': original.stat().st_size}
            relative = Path('Resources/native-export-media') / (info['sha256'] + original.suffix.lower())
            copied = snapshot / relative
            if j.nd.IS_WINDOWS:
                media_materialization.append(media_store.materialize_immutable(
                    original, copied, info['sha256']))
            elif not copied.exists():
                copied.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with original.open('rb') as src, copied.open('xb') as dst:
                    shutil.copyfileobj(src, dst)
            j.require(j.nd.digest(copied) == info['sha256'] == j.nd.digest(original) and
                      original.stat().st_size == info['size'], 'Draft media changed while copying')
            dependencies[str(original)] = info
            mapping[raw] = str(source / relative)

    if media_materialization:
        j.write(out / 'source-media-materialization.json', {'schema': media_store.SCHEMA,
                'contract': media_store.IMMUTABLE_CONTRACT, 'files': media_materialization})

    # Explicitly captured Windows visual packages are frozen with the media.
    # Node fields alone cannot identify two LUTs with the same native shape.
    vfx_materialization = []
    packages=SavedVfxSnapshots(source,snapshot)
    for bucket in ('transitions', 'common_mask', 'video_effects', 'effects', 'audio_effects', *native_color.BUCKETS):
        for node in value.get('materials', {}).get(bucket, []):
            windows_vfx._profile(runtime)
            original, relative, copied, entry = packages.get(bucket,node)
            for name, info in entry['files'].items():
                dependencies[str(original / name)] = info
            for extra in entry.get('lut_dependencies',[]):
                for name,info in extra['files'].items():dependencies[str(extra['source']/name)]=info
            if native_color.is_node(bucket,node):mapping.update(native_color.rebased_paths(node,source/relative))
            else:mapping[node['path']] = str(source / relative)
            if native_color.is_node(bucket,node) and node.get('lumi_hub_path'):
                mapping[node['lumi_hub_path']]=str(source/relative/native_color.lumi_relative(node))
            vfx_materialization.append({'source': str(original), 'snapshot': str(copied),
                    'preset': entry['key'], 'tree_sha256': entry['tree_sha256'],
                    'source_verified_unchanged': True, 'files': len(entry['files'])})
    packages.verify_sources()
    if vfx_materialization:
        j.write(out / 'source-vfx-materialization.json', {'files': vfx_materialization,
                'policy': 'source read-only; exact-byte verified ASCII resource snapshots'})

    # Saved drafts can contain the same explicit local fonts as verified builds.
    # Snapshot each static font before rewriting either outer or rich-text paths.
    install = Path(runtime.get('install_dir', '')).resolve()
    for material in value.get('materials', {}).get('texts', []):
        content = fonts.content(material)
        paths = [material.get('font_path')] + [style['font'].get('path') for style in content.get('styles', [])
                                             if isinstance(style.get('font'), dict)]
        for raw in paths:
            if not isinstance(raw, str) or not raw or raw in mapping or raw.startswith('/Applications/'):
                continue
            original = j.native_media_path(raw, source)
            if original.is_relative_to(install):
                continue
            j.require(runtime.get('runtime_profile') == WINDOWS_1147_PROFILE,
                      'Saved local font export requires the reviewed 11.4.7 runtime')
            original = j.regular_file(original)
            asset = fonts.asset_for(original)
            relative = Path(asset['relative'])
            copied = snapshot / relative
            if not copied.exists():
                copied.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with original.open('rb') as src, copied.open('xb') as dst:
                    shutil.copyfileobj(src, dst)
            j.require(j.nd.digest(copied) == asset['sha256'] == j.nd.digest(original),
                      'Draft font changed while copying')
            dependencies[str(original)] = {'sha256': asset['sha256'], 'size': asset['size']}
            font_assets[asset['relative']] = asset
            mapping[raw] = str(source / relative)

    def replace(item, key=''):
        if isinstance(item, dict):
            result = {k: replace(v, k) for k, v in item.items()}
            if item.get('type') == 'text' and isinstance(item.get('content'), str):
                result['content'] = json.dumps(replace(fonts.content(item)), ensure_ascii=False, separators=(',', ':'))
            return result
        if isinstance(item, list):
            return [replace(v, key) for v in item]
        if isinstance(item, str) and key != 'text':
            return mapping.get(item, item)
        return item

    value = replace(value)
    record = {'target': str(source), 'files': j.files_manifest(snapshot), 'font_assets': list(font_assets.values())}
    return stage_timeline(value, record, snapshot, out, runtime)


def draft_export_canvas(timeline, width=None, height=None):
    """Resolve an implicit original canvas without changing the saved draft."""
    canvas = timeline.get('canvas_config') or {}
    j.require((width is None) == (height is None), 'Specify both --width and --height')
    if width is not None:
        dimensions, origin = (width, height), 'explicit export dimensions'
    elif 'width' in canvas and 'height' in canvas:
        return timeline, 'saved canvas'
    else:
        j.require(not any(key in canvas for key in ('width', 'height')) and
                  canvas.get('ratio', 'original') == 'original',
                  'Draft canvas is incomplete; specify --width and --height')
        used = {segment.get('material_id') for track in timeline.get('tracks', [])
                if track.get('type') == 'video' for segment in track.get('segments', [])}
        sizes = {(node.get('width'), node.get('height'))
                 for node in timeline.get('materials', {}).get('videos', []) if node.get('id') in used}
        j.require(len(sizes) == 1 and all(type(n) is int and n > 0 for n in next(iter(sizes), ())),
                  'Draft has no unambiguous original canvas; specify --width and --height')
        dimensions, origin = next(iter(sizes)), 'unique used video dimensions'
    value = deepcopy(timeline)
    value['canvas_config'] = {**canvas, 'width': dimensions[0], 'height': dimensions[1]}
    return value, origin


def run_draft(draft_dir, out, bitrate=4_000_000, timeout=600, fps=None, width=None, height=None):
    """Export an existing local draft using the same native renderer and checks."""
    require_supported_platform()
    j.require(j.nd.IS_WINDOWS, 'Direct draft export currently requires the reviewed Windows runtime')
    runtime = j.nd.validate_runtime()
    validate_export_profiles(runtime['runtime_profile'], runtime['runtime_profile'])
    source, before, timeline, evidence = read_draft(draft_dir, runtime)
    timeline, evidence['canvas_selection'] = draft_export_canvas(timeline, width, height)
    if fps is not None:
        j.number(fps, 'Export fps', 1, 120)
        timeline = deepcopy(timeline)
        timeline['fps'] = fps
    dependencies = {}

    def verify_source():
        j.require(j.files_manifest(source) == before, 'Source draft changed during export')
        j.require(all(Path(path).is_file() and Path(path).stat().st_size == info['size'] and
                      j.nd.digest(path) == info['sha256'] for path, info in dependencies.items()),
                  'Source draft media changed during export')

    record = {'runtime_profile': runtime['runtime_profile'], 'runtime': runtime}
    evidence['source_manifest'] = before
    return _run_export(source, out, timeline, record, runtime, evidence,
                       lambda job: stage_draft_timeline(timeline, source, job, runtime, dependencies),
                       verify_source, 'source_draft_unchanged', bitrate, timeout)


def _run_export(source_root, out, timeline, record, runtime, source_evidence,
                stage_source, verify_source, unchanged_key, bitrate, timeout):
    capabilities = (windows_build_supported_features(timeline, record, source_root / 'draft', runtime)
                    if j.nd.IS_WINDOWS and 'build' in source_evidence else
                    windows_saved_draft_supported_features(timeline, record, source_root, runtime) if j.nd.IS_WINDOWS else
                    supported_features(timeline))
    settings = settings_for(timeline, bitrate, timeout)
    job = Path(out)
    j.require(job.is_absolute() and not job.exists() and not job.is_symlink(), 'Export job must be a new absolute directory')
    j.require('work' in job.parts, 'Export jobs must be under the task work directory')
    j.require(not j.nd.IS_WINDOWS or str(job).isascii(),
              'Windows native export requires an ASCII output work path; the source checkout may use Unicode')
    j.require(not job.resolve().is_relative_to(source_root) and not job.resolve().is_relative_to(j.nd.DRAFT_ROOT),
              'Export job cannot be inside a build or live draft')
    job = j.nd.fresh_directory(job)
    started = time.monotonic()
    evidence = {'schema': SCHEMA, 'status': 'preparing', **source_evidence, 'runtime': runtime,
                'settings': settings, 'ui_used': False, 'network_allowed': False,
                'live_draft_written': False, 'external_ffmpeg_composition': False,
                'renderer': 'Jianying native ExportService', 'container_writer': 'native MP4 writer',
                'acceptance_boundaries': capabilities}
    try:
        staged, files = stage_source(job)
        verify_source()
        j.write(job / 'timeline.json', staged)
        timeline_hash = j.nd.digest(job / 'timeline.json')
        output = job / 'render.mp4'
        has_masks = any(child.get('materials', {}).get('common_mask') for _, child in compound.graph(timeline))
        compiler_tmp = job / 'compiler-tmp'
        compiler_tmp.mkdir(mode=0o700)
        if j.nd.IS_WINDOWS:
            builtin_snapshot = None
            if has_masks:
                from windows_mask_protocol import verify_builtin_runtime, runtime_manifest
                builtin_root = verify_builtin_runtime(runtime)
                builtin = runtime_manifest()
                builtin_snapshot = job / 'Resources/native-builtin-mask-runtime'
                shutil.copytree(builtin_root, builtin_snapshot, symlinks=False)
                j.require(resources.tree_manifest(builtin_snapshot) == builtin['builtin_files'],
                          'Copied native mask runtime differs from its exact captured files')
                for relative, info in builtin['builtin_files'].items():
                    files[str(builtin_snapshot.relative_to(job) / relative)] = info
                evidence['built_in_mask_runtime'] = {'root': str(builtin_root), 'snapshot': str(builtin_snapshot),
                    'tree_sha256': builtin['builtin_tree_sha256'], 'files': len(builtin['builtin_files']),
                    'adapter_string_offset': '0x9b8', 'native_protocol': 'is_old_version=false',
                    'from_reviewed_installation': True, 'object_memory_scanned': False}
            helper = job / 'native-export-helper.exe'
            source = HERE / 'native_export_windows.cpp'
            tools = str(HERE.parent / 'tools')
            if tools not in sys.path:
                sys.path.insert(0, tools)
            from windows_native_toolchain import compile_helper
            compile_result, toolchain = compile_helper(source, helper, compiler_tmp)
            env = dict(os.environ)
            env['JY_VIDEOEDITOR_DIR'] = runtime['install_dir']
            # 原生 FFmpeg writer 对含非 ASCII 的绝对输出路径会返回 EINVAL(-22)；
            # 子进程 cwd 已固定为 job，因此只传 ASCII 相对文件名。
            command = [str(helper), 'timeline.json', 'render.mp4',
                       str(settings['width']), str(settings['height']), str(settings['fps']),
                       str(bitrate), str(timeout)]
            if builtin_snapshot:
                command += ['--builtin-resource-root', str(builtin_snapshot)]
            evidence['windows_toolchain'] = toolchain
            evidence['network_sandbox_enforced'] = False
        else:
            j.write(job / 'export.sb', sandbox_profile(job))
            helper = job / 'native-export-helper'
            source = HERE / 'native_export.cpp'
            frameworks = j.nd.APP / 'Contents/Frameworks'
            compile_command = ['/usr/bin/xcrun', 'clang++', '-std=c++17', '-arch', 'arm64', '-O2',
                               '-Wno-deprecated-declarations', str(source), '-L' + str(frameworks),
                               '-lvideoeditor', '-Wl,-rpath,' + str(frameworks), '-o', str(helper)]
            env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'LC_ALL': 'C',
                   'TMPDIR': str(compiler_tmp) + '/',
                   'CLANG_MODULE_CACHE_PATH': str(compiler_tmp / 'modules')}
            compile_result = subprocess.run(compile_command, capture_output=True, timeout=120, env=env)
            command = ['/usr/bin/sandbox-exec', '-f', str(job / 'export.sb'), str(helper),
                       str(job / 'timeline.json'), str(output), str(settings['width']), str(settings['height']),
                       str(settings['fps']), str(bitrate), str(timeout), '1' if has_masks else '0']
            evidence['network_sandbox_enforced'] = True
            if has_masks:
                root = j.nd.APP / 'Contents/Resources/lumi_js_resources_video'
                evidence['built_in_mask_runtime'] = {
                    'root': str(root), 'from_signed_app_bundle': True, 'account_data_used': False,
                    'config_sha256': j.nd.digest(root / 'config.json'),
                    'javascript_sha256': j.nd.digest(root / 'js/video/video.js')}
        j.write(job / 'inputs.json', {'files': files, 'timeline_sha256': timeline_hash})
        j.write(job / 'compiler.stderr.log', compile_result.stderr)
        j.require(compile_result.returncode == 0, 'Native export helper compilation failed')
        os.chmod(helper, 0o700)
        evidence['helper_sha256'] = j.nd.digest(helper)
        evidence['adapter_source_sha256'] = j.nd.digest(source)
        with (job / 'native.stdout.log').open('xb') as stdout, (job / 'native.stderr.log').open('xb') as stderr:
            os.chmod(stdout.name, 0o600); os.chmod(stderr.name, 0o600)
            try:
                result = subprocess.run(command, cwd=job, stdout=stdout, stderr=stderr, env=env, timeout=timeout + 30)
            except subprocess.TimeoutExpired as error:
                raise ValueError('Native export timed out; partial output retained') from error
        evidence['native_returncode'] = result.returncode
        stdout_text = (job / 'native.stdout.log').read_text(encoding='utf-8', errors='replace')
        stderr_text = (job / 'native.stderr.log').read_text(encoding='utf-8', errors='replace')
        evidence['native_completion_event'] = ('JY_WINDOWS_NATIVE_EXPORT_DONE' in stdout_text if j.nd.IS_WINDOWS
                                               else 'JY_NATIVE_EXPORT_DONE' in stdout_text)
        evidence['native_restore_completion_event'] = ('JY_WINDOWS_NATIVE_RESTORE_DONE' in stdout_text if j.nd.IS_WINDOWS
                                                       else 'JY_NATIVE_RESTORE_DONE' in stderr_text)
        j.require(result.returncode == 0 and evidence['native_completion_event'] and evidence['native_restore_completion_event'],
                  'Native restoration/export did not complete successfully')
        if j.nd.IS_WINDOWS:
            evidence['native_visual_runtime']=native_color.validate_render_log(stdout_text+'\n'+stderr_text)
        if j.nd.IS_WINDOWS and any(child.get('materials',{}).get('audio_effects')
                                    for _,child in compound.graph(timeline)):
            evidence['native_audio_runtime']=native_audio_processing.validate_render_log(stdout_text+'\n'+stderr_text)
        if j.nd.IS_WINDOWS and has_masks:
            j.require('JY_WINDOWS_NATIVE_BUILTIN_RESOURCE_ROOT ' + str(builtin_snapshot) in stdout_text,
                      'Native mask runtime configuration was not acknowledged')
            verify_builtin_runtime(runtime)
        probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-show_format',
                                                    '-of', 'json', str(output)], timeout=60))
        j.write(job / 'ffprobe.json', probe)
        audio_expected = any(bool(child['materials'].get('audios')) or any(
            v.get('has_audio', True) for v in child['materials'].get('videos', [])
            if v.get('type') == 'video' and v.get('path')) for _, child in compound.graph(timeline))
        evidence['media'] = validate_probe(probe, settings, timeline['duration'], audio_expected)
        decoded = subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(output), '-f', 'null', '-'],
                                 capture_output=True, timeout=timeout)
        j.write(job / 'decode.stderr.log', decoded.stderr)
        j.require(decoded.returncode == 0, 'Native MP4 did not fully decode')
        evidence['full_decode_passed'] = True
        j.require(all(j.nd.digest(job / name) == item['sha256'] for name, item in files.items()),
                  'Native export modified an input resource')
        j.require(j.nd.digest(job / 'timeline.json') == timeline_hash, 'Native export modified its timeline input')
        verify_source()
        evidence.update(status='encoded-and-decoded', output=str(output), output_sha256=j.nd.digest(output),
                        output_bytes=output.stat().st_size,
                        visual_content_acceptance='requires viewing the actual output',
                        elapsed_seconds=round(time.monotonic() - started, 3))
        evidence[unchanged_key] = True
        os.chmod(output, 0o600)
        j.write(job / 'result.json', evidence)
        return evidence
    except Exception as error:
        evidence.update(status='failed', error=str(error), partial_artifacts_retained=True)
        j.write(job / 'result.json', evidence)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--build', help='Verified headless/edit build snapshot')
    inputs.add_argument('--draft-dir', help='Existing local draft; reads the declared main timeline without writing it')
    parser.add_argument('--out', required=True, help='New absolute work directory; output is render.mp4')
    parser.add_argument('--bitrate', type=int, default=4_000_000)
    parser.add_argument('--timeout', type=int, default=600)
    parser.add_argument('--fps', type=float, help='Direct draft export frame rate; otherwise use the draft value or 30')
    parser.add_argument('--width', type=int, help='Direct draft export width; pair with --height')
    parser.add_argument('--height', type=int, help='Direct draft export height; pair with --width')
    args = parser.parse_args()
    try:
        j.require(args.draft_dir or args.fps is None, '--fps only applies to --draft-dir')
        j.require(args.draft_dir or (args.width is None and args.height is None),
                  '--width and --height only apply to --draft-dir')
        result = (run_draft(args.draft_dir, args.out, args.bitrate, args.timeout, args.fps,
                            args.width, args.height) if args.draft_dir
                  else run(args.build, args.out, args.bitrate, args.timeout))
        print(json.dumps({k: result[k] for k in ('status', 'output', 'media', 'full_decode_passed',
                                                'source_build_unchanged', 'source_draft_unchanged', 'elapsed_seconds',
                                                'acceptance_boundaries') if k in result}, ensure_ascii=False))
    except Exception as error:
        print('Native export failed: ' + str(error), file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
