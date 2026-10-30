"""Reviewed 11.4.7 circle-mask protocol repair and built-in resource identity.

Lyra's typed add writes an old-protocol flag for this package. The native player
needs the new protocol. Repair only the declared main timeline, via the official
EncryptUtils, and retain the exact prior ciphertext for explicit recovery.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import uuid

import native_resources as resources
from runtime_profiles import WINDOWS_1147_PROFILE

CATALOG_PATH = Path(__file__).with_name('windows-mask-runtime.json')
CATALOG_SHA256 = '62054d5e3b818cfe89519526d4d72ac94a39afc487d688578e88a3747dd71343'


def _require(value, message):
    if not value:
        raise ValueError(message)


def runtime_manifest():
    data = CATALOG_PATH.read_bytes()
    _require(hashlib.sha256(data).hexdigest() == CATALOG_SHA256,
             'Windows mask runtime catalog changed; review capture provenance')
    value = json.loads(data)
    _require(value.get('schema') == 'jy-windows-mask-runtime/v1', 'Unsupported mask runtime catalog')
    return value


def _reviewed_runtime(runtime):
    _require(runtime.get('runtime_profile') == WINDOWS_1147_PROFILE and
             runtime.get('app_build') == '11.4.7.14462',
             'Native mask compatibility is reviewed only for exact Windows 11.4.7.14462')


def verify_builtin_runtime(runtime) -> Path:
    """Read and verify every byte of the signed-installation mask runtime tree."""
    _reviewed_runtime(runtime)
    catalog = runtime_manifest()
    install = Path(runtime['install_dir'])
    _require(install.is_absolute() and install.is_dir() and not install.is_symlink(),
             'Mask runtime requires the reviewed absolute installation directory')
    install = install.resolve(strict=True)
    root = install / catalog['builtin_relative']
    _require(root.is_dir() and not root.is_symlink() and root.resolve(strict=True) == root,
             'Built-in mask runtime is missing or redirected')
    actual = resources.tree_manifest(root)
    _require(actual == catalog['builtin_files'] and
             resources.manifest_hash(actual) == catalog['builtin_tree_sha256'],
             'Built-in mask runtime bytes differ from reviewed Windows 11.4.7')
    return root


def _circle_mask(action, source, timeline, catalog):
    targets = [segment for track in timeline.get('tracks', []) if track.get('type') == 'video'
               for segment in track.get('segments', []) if segment.get('id') == action.get('segment_id')]
    _require(len(targets) == 1, 'Mask protocol repair requires one exact video segment')
    masks = timeline.get('materials', {}).get('common_mask', [])
    ids = [node.get('id') for node in masks]
    _require(len(ids) == len(set(ids)), 'Mask material identity is ambiguous')
    refs = targets[0].get('extra_material_refs', [])
    bound = [node for node in masks if node.get('id') in refs]
    _require(len(bound) == 1 and refs.count(bound[0].get('id')) == 1,
             'Mask protocol repair requires one bound circle mask')
    mask = bound[0]
    captured = catalog['mask_circle']
    _require(all(mask.get(field) == captured[field] for field in
                 ('resource_id', 'resource_type', 'type', 'category', 'category_id', 'name')),
             'Mask protocol repair only accepts the reviewed REA-circle identity')
    _require(type(mask.get('is_old_version')) is bool, 'Mask protocol flag is missing or ambiguous')
    config = mask.get('config', {})
    fixed = {'width': .65, 'height': .65, 'centerX': 0, 'centerY': 0,
             'rotation': 0, 'feather': 0, 'roundCorner': 0, 'aspectRatio': 1, 'expansion': 0}
    _require(isinstance(config, dict) and not set(config) - (set(fixed) | {'invert'}),
             'Unreviewed circle mask geometry fields')
    for field, expected in fixed.items():
        value = config.get(field, expected if field not in {'width', 'height'} else None)
        _require(type(value) in (int, float) and math.isfinite(value) and
                 math.isclose(value, expected, abs_tol=1e-9, rel_tol=0),
                 'Circle mask protocol repair requires fixed reviewed geometry: ' + field)
    _require(type(config.get('invert', False)) is bool and not config.get('invert', False),
             'Circle mask inversion has not been admitted by this repair')
    raw = mask.get('path')
    _require(isinstance(raw, str) and raw and '://' not in raw,
             'Mask protocol repair requires a local captured resource directory')
    path = Path(raw)
    if not path.is_absolute():
        path = source / path
    _require(path.is_dir() and not path.is_symlink() and path.resolve(strict=True) == path,
             'Mask protocol resource is missing or redirected')
    actual = resources.tree_manifest(path)
    _require(actual == captured['files'] and resources.manifest_hash(actual) == captured['tree_sha256'],
             'Mask protocol resource bytes differ from the reviewed circle package')
    return mask, path


def repair_after_action(action, source, audit_prefix, runtime):
    """Repair only video.mask.set's saved, bound circle; retain an audit on failure.

    This follows a CLI commit and is not an atomic batch. Existing root mirrors
    are intentionally untouched: read_draft selects the declared main timeline.
    """
    if action.get('op') != 'video.mask.set':
        return None
    _reviewed_runtime(runtime)
    catalog = runtime_manifest()
    # Function-local import avoids native_export -> mask admission -> import cycles.
    import native_export as native
    source, before, timeline, evidence = native.read_draft(source, runtime)
    prefix = Path(audit_prefix)
    _require(prefix.is_absolute() and prefix.parent.is_dir() and
             not prefix.resolve().is_relative_to(source), 'Mask repair audit must be outside the source draft')
    def audit_file(suffix):
        return prefix.parent / (prefix.name + '.mask-protocol.' + suffix)
    report_path = audit_file('json')
    _require(not report_path.exists(), 'Mask protocol audit already exists')
    main = source / evidence['source_timeline']
    _require(main.is_file() and not main.is_symlink() and main.resolve().is_relative_to(source),
             'Declared main timeline is not a regular draft-owned file')
    mask, resource_path = _circle_mask(action, source, timeline, catalog)
    relative = str(main.relative_to(source))
    report = {'schema': 'jy-windows-mask-protocol-repair/v1', 'status': 'preparing',
              'source': str(source), 'main_timeline': str(main), 'segment_id': action['segment_id'],
              'mask_id': mask['id'], 'resource': str(resource_path),
              'before_sha256': before[relative]['sha256'], 'only_declared_main_written': True,
              'native_encryption': 'official EncryptUtils', 'atomic_batch': False,
              'patch': {'field': 'materials.common_mask[id=' + mask['id'] + '].is_old_version',
                        'before': mask['is_old_version'], 'after': False}}
    try:
        if mask['is_old_version'] is False:
            _require(native.j.files_manifest(source) == before, 'Draft changed during mask protocol readback')
            report.update(status='already-native-protocol', after_sha256=report['before_sha256'],
                          source_other_files_unchanged=True)
            return report
        previous = audit_file('before.enc')
        _require(not previous.exists(), 'Mask protocol recovery snapshot already exists')
        with main.open('rb') as src, previous.open('xb') as dst:
            shutil.copyfileobj(src, dst)
        _require(native.j.nd.digest(previous) == before[relative]['sha256'],
                 'Main timeline changed during mask repair snapshot')
        report['recovery_path'] = str(previous)
        updated = deepcopy(timeline)
        changed = next(node for node in updated['materials']['common_mask'] if node['id'] == mask['id'])
        changed['is_old_version'] = False
        encrypted = audit_file('after.enc')
        helper = native.j.nd.helper()
        helper._encrypt_metadata_from_memory(native.j.nd.packed(updated), encrypted)
        _require(helper._decrypt_metadata_in_memory(encrypted) == updated,
                 'Official encryption failed mask compatibility readback')
        pending = main.with_name('.jy-mask-protocol-' + uuid.uuid4().hex + '.tmp')
        report['temporary_path'] = str(pending)
        with encrypted.open('rb') as src, pending.open('xb') as dst:
            shutil.copyfileobj(src, dst)
        _require(native.j.nd.digest(pending) == native.j.nd.digest(encrypted), 'Mask repair ciphertext copy changed')
        current = native.j.files_manifest(source)
        current.pop(str(pending.relative_to(source)), None)
        _require(current == before, 'Draft changed concurrently; refusing the mask compatibility replacement')
        os.replace(pending, main)
        _, after_files, after, selected = native.read_draft(source, runtime)
        _require(selected['source_timeline'] == evidence['source_timeline'] and after == updated,
                 'Saved main timeline does not match the mask compatibility repair')
        expected = dict(before)
        expected[relative] = {'sha256': native.j.nd.digest(encrypted), 'size': encrypted.stat().st_size}
        _require(after_files == expected, 'Files outside the declared main timeline changed during mask repair')
        _circle_mask(action, source, after, catalog)
        report.update(status='repaired-and-read-back', after_sha256=expected[relative]['sha256'],
                      source_other_files_unchanged=True)
        return report
    except Exception as error:
        report.update(status='failed-or-unverified', error=str(error),
                      recovery='Inspect retained ciphertext and concurrent edits; no automatic rollback was attempted.')
        raise
    finally:
        with report_path.open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
