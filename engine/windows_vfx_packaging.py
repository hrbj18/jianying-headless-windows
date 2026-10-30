"""Freeze reviewed native VFX dependencies inside one saved draft, with an audit.

Only material path fields in the declared main timeline are rewritten. Official
EncryptUtils produces the new ciphertext; root mirrors and all edit parameters
are preserved. This is a recoverable, non-atomic operation, with no UI actions.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import stat
import uuid

import native_export as native
import windows_vfx as vfx
from local_config import configure_environment

BUCKETS = ('video_effects', 'effects', 'transitions', 'common_mask')
SCHEMA = 'jy-windows-vfx-freeze-draft/v1'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _ordinary(path):
    info = Path(path).lstat()
    require(not Path(path).is_symlink() and
            not getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400),
            'Freeze-draft rejects symlinks and reparse points: ' + str(path))
    return info


def _directory(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts and path.is_dir(),
            'Freeze-draft requires an absolute existing directory')
    require(path.resolve(strict=True) == path, 'Freeze-draft directory is redirected through an alias')
    require(stat.S_ISDIR(_ordinary(path).st_mode), 'Freeze-draft path is not an ordinary directory')
    return path


def _manifest(folder):
    """Hash regular files including empty resource tags; never follow reparse dirs."""
    folder = _directory(folder)
    result = {}
    for current, dirs, files in os.walk(folder, topdown=True, followlinks=False):
        for name in dirs:
            require(stat.S_ISDIR(_ordinary(Path(current) / name).st_mode), 'Non-directory in draft tree')
        for name in files:
            path = Path(current) / name
            info = _ordinary(path)
            require(stat.S_ISREG(info.st_mode), 'Freeze-draft requires regular files')
            result[str(path.relative_to(folder))] = {'sha256': native.j.nd.digest(path), 'size': info.st_size}
    return result


def _save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n', encoding='utf-8')


def _copy_file(source, target):
    # Empty effect_platform_children.tag and similar package files are valid.
    require(stat.S_ISREG(_ordinary(source).st_mode), 'VFX source is not a regular file')
    with Path(source).open('rb') as src, Path(target).open('xb') as dst:
        shutil.copyfileobj(src, dst)


def _owned_parent(source, target):
    require(target.is_absolute() and target.is_relative_to(source) and target != source,
            'Owned VFX path escapes the draft')
    current = source
    for part in target.relative_to(source).parts:
        current = current / part
        if current.exists():
            require(stat.S_ISDIR(_ordinary(current).st_mode), 'VFX destination ancestor is not a directory')
        else:
            current.mkdir(mode=0o700)
        require(current.resolve() == current, 'VFX destination is redirected')


def _package_files(source, destination, entry):
    """Create one complete owned package or verify an existing exact copy."""
    origin = Path(source)
    vfx.verify_resource(origin, entry)
    if destination.exists():
        vfx.verify_resource(destination, entry)
        vfx.verify_resource(origin, entry)
        return False
    _owned_parent(destination.parents[2], destination.parent)
    destination.mkdir(mode=0o700)
    for relative in sorted(entry['files']):
        suffix = Path(relative)
        require(not suffix.is_absolute() and '..' not in suffix.parts, 'Invalid catalog package member')
        target = destination / suffix
        _owned_parent(destination, target.parent) if target.parent != destination else None
        _copy_file(origin / suffix, target)
    vfx.verify_resource(destination, entry)
    vfx.verify_resource(origin, entry)
    return True


def _plan(timeline, source):
    updated = deepcopy(timeline)
    packages = {}
    rewrites = []
    for bucket in BUCKETS:
        for node in updated.get('materials', {}).get(bucket, []):
            entry = vfx.entry_for_node(bucket, node)
            destination = source / 'Resources' / 'reviewed-vfx' / entry['tree_sha256']
            require(str(destination).isascii(), 'Draft-owned native VFX paths currently require an ASCII draft directory')
            identity = entry['tree_sha256']
            original = Path(node['path'])
            require(original == destination or (not destination.is_relative_to(original) and
                    not original.is_relative_to(destination)), 'VFX source and destination packages overlap')
            if identity not in packages:
                packages[identity] = {'origin': original, 'destination': destination, 'entry': entry}
            if original != destination:
                rewrites.append({'bucket': bucket, 'material_id': node['id'], 'before': node['path'],
                                 'after': destination.as_posix(), 'preset': entry['key']})
                node['path'] = destination.as_posix()
    return updated, packages, rewrites


def run(draft_dir, out):
    configure_environment()
    runtime = native.j.nd.validate_runtime()
    # Validate aliases/reparse entries before read_draft's generic manifest walk.
    source = _directory(Path(draft_dir))
    strict_before = _manifest(source)
    source, before, timeline, selection = native.read_draft(source, runtime)
    require(before == strict_before == _manifest(source), 'Draft changed during the freeze preflight')
    features = vfx.validate_timeline(timeline, runtime)
    updated, packages, rewrites = _plan(timeline, source)
    main_relative = selection['source_timeline']
    main = source / main_relative
    require(main.is_relative_to(source) and stat.S_ISREG(_ordinary(main).st_mode),
            'Declared main timeline must be a draft-owned regular file')
    audit = Path(out)
    require(audit.is_absolute() and str(audit).isascii() and '..' not in audit.parts and
            'work' in [part.lower() for part in audit.parts] and not audit.exists(),
            'Freeze audit must be a new absolute ASCII work directory')
    require(audit.resolve() == audit and not audit.is_relative_to(source) and not source.is_relative_to(audit),
            'Freeze audit and source must be separate canonical directories')
    audit = native.j.nd.fresh_directory(audit)
    report = {'schema': SCHEMA, 'status': 'preparing', 'atomic_batch': False, 'ui_used': False,
              'native_encryption': 'official EncryptUtils', 'source_draft': str(source),
              'source_timeline': main_relative, 'runtime': runtime, 'features': features,
              'before_manifest': before, 'path_rewrites': rewrites, 'packages': [],
              'root_mirrors_written': False, 'main_replaced': False,
              'recovery': str(audit / 'before'), 'network_requested': False}
    expected = dict(before)
    pending = None
    try:
        _save(audit / 'result.json', report)
        shutil.copytree(source, audit / 'before', symlinks=False)
        require(_manifest(audit / 'before') == before == _manifest(source),
                'Draft changed while copying the complete before snapshot')
        _copy_file(main, audit / 'before.enc')
        require(native.j.nd.digest(audit / 'before.enc') == before[main_relative]['sha256'],
                'Main timeline changed during ciphertext snapshot')
        _save(audit / 'before-timeline.json', timeline)
        for package in packages.values():
            require(_manifest(source) == expected, 'Concurrent draft change before VFX copy')
            entry, destination = package['entry'], package['destination']
            created = _package_files(package['origin'], destination, entry)
            for relative, info in entry['files'].items():
                owned_relative = str((destination / Path(relative)).relative_to(source))
                require(owned_relative not in expected or expected[owned_relative] == info,
                        'Existing owned VFX file differs from its reviewed bytes')
                expected[owned_relative] = info
            require(_manifest(source) == expected, 'Unexpected draft changes while copying VFX resources')
            report['packages'].append({'preset': entry['key'], 'tree_sha256': entry['tree_sha256'],
                                       'destination': str(destination), 'created': created,
                                       'file_count': len(entry['files'])})
            _save(audit / 'result.json', report)
        # Directory hashes, bindings and parameters must still validate at the new paths.
        vfx.validate_timeline(updated, runtime)
        require(_manifest(source) == expected, 'Concurrent draft change before timeline encryption')
        helper = native.j.nd.helper()
        if rewrites:
            pending = main.with_name('.jy-vfx-freeze-' + uuid.uuid4().hex + '.tmp')
            report['temporary_ciphertext'] = str(pending)
            helper._encrypt_metadata_from_memory(native.j.nd.packed(updated), pending)
            require(helper._decrypt_metadata_in_memory(pending) == updated,
                    'Official ciphertext did not preserve the expected path-only timeline')
            _copy_file(pending, audit / 'after.enc')
            require(native.j.nd.digest(pending) == native.j.nd.digest(audit / 'after.enc'),
                    'After-ciphertext audit copy changed')
            current = _manifest(source)
            current.pop(str(pending.relative_to(source)), None)
            require(current == expected, 'Concurrent draft change; refusing timeline replacement')
            os.replace(pending, main)
            report['main_replaced'] = True
            expected[main_relative] = {'sha256': native.j.nd.digest(audit / 'after.enc'),
                                       'size': (audit / 'after.enc').stat().st_size}
        else:
            _copy_file(main, audit / 'after.enc')
        _, after_files, after, selected = native.read_draft(source, runtime)
        require(selected['source_timeline'] == main_relative and after == updated,
                'Declared main timeline does not match the path-only freeze')
        require(after_files == expected == _manifest(source), 'Files outside the expected freeze changed')
        after_features = vfx.validate_timeline(after, runtime)
        require(after_features == features, 'Freeze changed the VFX capability or binding inventory')
        _save(audit / 'after-timeline.json', after)
        report.update(status='frozen-and-read-back' if rewrites else 'already-draft-owned',
                      after_manifest=after_files, source_other_files_unchanged=True,
                      added_files=sorted(set(after_files) - set(before)),
                      after_timeline_sha256=after_files[main_relative]['sha256'],
                      export_status='not-tested-by-this-command')
    except Exception as error:
        report.update(status='failed-or-unverified', error=str(error),
                      recovery_note='Inspect the complete before snapshot and retained ciphertext; no automatic rollback was attempted.')
        if pending is not None and pending.exists():
            report['retained_temporary_ciphertext'] = str(pending)
    _save(audit / 'result.json', report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--draft-dir', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    result = run(args.draft_dir, args.out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['status'] in {'frozen-and-read-back', 'already-draft-owned'} else 1


if __name__ == '__main__':
    raise SystemExit(main())
