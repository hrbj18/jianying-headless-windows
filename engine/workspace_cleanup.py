"""Remove completed native-job caches backed by retained verified builds.

Preparation proves regeneration from a complete build and binds exact hashes.
Application validates surviving inputs before deleting the first cache name.
An fsynced intent/deleted journal permits bounded recovery in the same audit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import time
import uuid

from media_store import safe_path, verified_digest, unlink_owned_file

FORBIDDEN_NAMES = frozenset({'render.mp4', 'plan.json', 'build.json', 'root_meta_info.json',
                             'preview.json', 'result.json', 'inputs.json', 'timeline.json'})
BUILD_SCHEMAS = frozenset({'jy14-headless-build/v1', 'jy14-edit-build/v1'})


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return verified_digest(Path(path).resolve(strict=True))


def save(path, value):
    path = safe_path(path, exists=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('.cleanup-save-' + uuid.uuid4().hex)
    try:
        with temporary.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read(path):
    return json.loads(safe_path(path, regular=True).read_text(encoding='utf-8-sig'))


def regular_path(path):
    return safe_path(path)  # lstat checks junctions and every existing parent.


def inventory(folder):
    folder = safe_path(folder, directory=True)
    result = {}
    for directory, names, filenames in os.walk(folder, followlinks=False):
        safe_path(directory, directory=True)
        for name in names:
            safe_path(Path(directory) / name, directory=True)
        for name in filenames:
            path = safe_path(Path(directory) / name, regular=True)
            result[path.relative_to(folder).as_posix()] = {'sha256': verified_digest(path),
                                                          'size': path.stat().st_size}
    return dict(sorted(result.items()))


def _relative(base, name):
    require(isinstance(name, str) and name, 'A relative dependency name is required')
    value = Path(name)
    require(not value.is_absolute() and not value.drive and '..' not in value.parts and ':' not in name,
            'Unsafe relative dependency name')
    return safe_path(base / value, exists=False)


def _file_map(value):
    require(isinstance(value, dict), 'A dependency manifest is required')
    result = {}
    for name, info in value.items():
        path = Path(name)
        require(isinstance(name, str) and not path.is_absolute() and not path.drive and
                '..' not in path.parts and ':' not in name, 'Unsafe dependency manifest path')
        require(isinstance(info, dict) and re.fullmatch(r'[a-f0-9]{64}', str(info.get('sha256', ''))) and
                type(info.get('size')) is int and info['size'] >= 0, 'Invalid dependency fingerprint')
        key = path.as_posix()
        require(key not in result, 'Duplicate dependency name')
        result[key] = {'sha256': info['sha256'], 'size': info['size']}
    return result


def _retain(retained, path, sha=None, size=None):
    path = safe_path(path, regular=True)
    actual = verified_digest(path, sha)
    require(size is None or path.stat().st_size == size, 'Retained input size differs: ' + str(path))
    info = {'sha256': actual, 'size': path.stat().st_size}
    require(str(path) not in retained or retained[str(path)] == info,
            'Conflicting retained input fingerprint: ' + str(path))
    retained[str(path)] = info
    return path


def _verify_build(build, expected_sha, retained):
    build = safe_path(build, directory=True)
    record_path = _retain(retained, build / 'build.json', expected_sha)
    record = read(record_path)
    require(record.get('schema') in BUILD_SCHEMAS, 'Cleanup requires a supported retained build')
    files = _file_map(record.get('files'))
    require(files, 'Retained build manifest must not be empty')
    snapshot = safe_path(build / 'draft', directory=True)
    require(inventory(snapshot) == files, 'Retained build snapshot differs from its full manifest')
    for name, info in files.items():
        retained[str(_relative(snapshot, name))] = info
    _retain(retained, build / 'plan.json', record.get('plan_sha256'))
    for asset in record.get('assets', []) + record.get('new_assets', []) + record.get('font_assets', []):
        if asset.get('source') and asset.get('sha256'):
            _retain(retained, asset['source'], asset['sha256'], asset.get('size'))
    return {'build': str(build), 'build_sha256': expected_sha, 'snapshot_files': len(files),
            'full_manifest_verified': True}


def _native_job(folder, retained, builds):
    job = safe_path(folder.parent, directory=True)
    require(folder.name in {'Resources', 'compiler-tmp'},
            'Only dependency Resources and completed-export compiler caches are accepted')
    require(job.name.casefold() != 'draft' and not (job / 'build.json').exists(),
            'Editable draft/Resources cannot be removed as a cache')
    marker, mode, evidence = None, None, None
    if (job / 'preview.json').is_file():
        marker = job / 'preview.json'
        evidence = read(marker)
        require(folder.name == 'Resources', 'A preview cannot authorize compiler cache cleanup')
        require(evidence.get('schema') == 'jy-windows-native-preview/v1' and
                evidence.get('status') == 'native-frames-captured' and evidence.get('source_unchanged') is True,
                'Cache requires a successful native preview with unchanged source')
        source, mode = evidence.get('source', {}), 'preview'
    elif (job / 'result.json').is_file():
        marker = job / 'result.json'
        evidence = read(marker)
        require(evidence.get('schema') == 'jy14-native-export/v1' and
                evidence.get('status') == 'encoded-and-decoded' and evidence.get('source_build_unchanged') is True,
                'Cache requires a completed native export with unchanged build')
        source, mode = evidence, 'export'
    require(marker is not None, 'Cache is not beneath a completed native preview/export job')
    require(source.get('build') and re.fullmatch(r'[a-f0-9]{64}', str(source.get('build_sha256', ''))),
            'Cache regeneration requires a retained build path and SHA-256')
    build = safe_path(source['build'], directory=True)
    if str(build) not in builds:
        builds[str(build)] = _verify_build(build, source['build_sha256'], retained)
    else:
        require(builds[str(build)]['build_sha256'] == source['build_sha256'], 'Conflicting source build evidence')
    _retain(retained, marker)
    inputs_path = _retain(retained, job / 'inputs.json')
    inputs = read(inputs_path)
    files = _file_map(inputs.get('files'))
    _retain(retained, job / 'timeline.json', inputs.get('timeline_sha256'))
    for name, info in files.items():
        path = _relative(job, name)
        if not path.is_relative_to(job / 'Resources'):
            _retain(retained, path, info['sha256'], info['size'])
    if mode == 'preview':
        require(isinstance(evidence.get('frames'), list) and evidence['frames'], 'Preview has no preserved frames')
        for frame in evidence['frames']:
            path = safe_path(frame['png'], regular=True)
            require(path.parent == job, 'Preview frame escaped its task directory')
            _retain(retained, path, frame.get('png_sha256'))
    else:
        output = safe_path(evidence.get('output', ''), regular=True)
        require(output.parent == job, 'Export output is outside its task directory')
        _retain(retained, output, evidence.get('output_sha256'), evidence.get('output_bytes'))
    if folder.name == 'Resources':
        expected = {Path(name).relative_to('Resources').as_posix(): info for name, info in files.items()
                    if Path(name).parts[:1] == ('Resources',)}
        require(inventory(folder) == expected, 'Resource cache differs from the native job inputs manifest')
    else:
        cwd = safe_path((evidence.get('windows_toolchain') or {}).get('compiler_cwd', ''), directory=True)
        require(cwd == folder or cwd.is_relative_to(folder), 'Compiler cache is not bound to this completed export')
    return {'job': str(job), 'kind': mode, 'marker': str(marker),
            'marker_sha256': retained[str(safe_path(marker))]['sha256'],
            'source_build': str(build), 'source_build_sha256': source['build_sha256']}


def _candidate_policy(path, allowed, protected):
    require(any(root in path.parents for root in allowed),
            'Candidate must be a strict child of an authorized task root')
    require(path.name in {'Resources', 'compiler-tmp'}, 'Only dependency/compiler cache directories are accepted')
    require(path.parent.name.casefold() != 'draft', 'Editable draft/Resources cannot be removed as a cache')
    require(not any(path == p or path in p.parents for p in protected),
            'Cache is still referenced by a protected input: ' + str(path))


def prepare(request_path, out):
    request_path = safe_path(request_path, regular=True)
    out = safe_path(out, exists=False)
    require(not out.exists(), 'Cleanup plan output must be a new file')
    request = read(request_path)
    require(request.get('schema') == 'jy-cache-cleanup-request/v1', 'Unsupported cleanup request')
    allowed = [safe_path(p, directory=True) for p in request['allowed_roots']]
    require(allowed and all(p != Path(p.anchor) for p in allowed), 'Explicit task roots are required')
    protected = [safe_path(p, regular=True) for p in request['protected_files']]
    require(protected, 'At least the user original must be explicitly protected')
    retained, builds, candidates, seen = {}, {}, [], []
    for path in protected:
        _retain(retained, path)
    _retain(retained, request_path)
    for raw in request['regenerable_directories']:
        path = safe_path(raw, directory=True)
        _candidate_policy(path, allowed, protected)
        require(not any(path == p or path in p.parents or p in path.parents for p in seen),
                'Overlapping cleanup candidates')
        files = inventory(path)
        require(not any(Path(name).name in FORBIDDEN_NAMES for name in files),
                'Delivery, build or index file found in cache candidate')
        proof = _native_job(path, retained, builds)
        seen.append(path)
        candidates.append({'path': str(path), 'files': files, 'regeneration': proof})
    require(candidates, 'No proven regenerable cache directories were requested')
    for item in candidates:
        path = Path(item['path'])
        require(not (out == path or out.is_relative_to(path)), 'Cleanup plan must stay outside deletion candidates')
        _candidate_policy(path, allowed, [Path(p) for p in retained])
        require(not any(path == Path(row['build']) or path in Path(row['build']).parents or
                        Path(row['build']) in path.parents for row in builds.values()),
                'Cache overlaps a retained editable build')
    value = {'schema': 'jy-cache-cleanup-plan/v1', 'request_path': str(request_path),
             'request_sha256': digest(request_path), 'allowed_roots': [str(p) for p in allowed],
             'protected_files': [str(p) for p in protected],
             'protected_hashes': {str(p): retained[str(p)]['sha256'] for p in protected},
             'retained_files': retained, 'source_builds': list(builds.values()), 'candidates': candidates,
             'logical_bytes': sum(v['size'] for c in candidates for v in c['files'].values()),
             'reason': request['reason'], 'regenerable_from': request.get('regenerable_from', []),
             'actual_regeneration_policy': 'retained complete build snapshot and original input hashes'}
    save(out, value)
    return {'status': 'cleanup-prepared', 'plan': str(out), 'directories': len(candidates),
            'logical_bytes': value['logical_bytes'], 'verified_source_builds': len(builds),
            'retained_files': len(retained)}


def _append(path, event):
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(event, ensure_ascii=False, separators=(',', ':')) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def _events(path):
    if not path.exists():
        return []
    safe_path(path, regular=True)
    payload = path.read_bytes()
    if payload and not payload.endswith(b'\n'):
        boundary = payload.rfind(b'\n') + 1
        with path.open('r+b') as stream:
            stream.truncate(boundary)
            stream.flush()
            os.fsync(stream.fileno())
        payload = payload[:boundary]
    return [json.loads(line) for line in payload.decode('utf-8').splitlines() if line.strip()]


def _verify_retained(plan):
    require(plan.get('retained_files') and plan.get('source_builds'),
            'Cleanup plan lacks complete retained-build evidence; prepare again')
    for raw, info in plan['retained_files'].items():
        path = safe_path(raw, regular=True)
        require(path.stat().st_size == info['size'], 'Retained input size changed after preparation: ' + raw)
        verified_digest(path, info['sha256'])
    for row in plan['source_builds']:
        record_path = safe_path(Path(row['build']) / 'build.json', regular=True)
        verified_digest(record_path, row['build_sha256'])
        record = read(record_path)
        files = _file_map(record['files'])
        snapshot = Path(row['build']) / 'draft'
        require(inventory(snapshot) == files,
                'Retained build full manifest changed after preparation')
        for name, info in files.items():
            path = str(_relative(snapshot, name))
            require(plan['retained_files'].get(path) == info,
                    'Cleanup plan omitted a retained build dependency: ' + path)
        plan_file = str(safe_path(Path(row['build']) / 'plan.json', regular=True))
        require(plan['retained_files'].get(plan_file, {}).get('sha256') == record.get('plan_sha256'),
                'Cleanup plan omitted the source editing plan')
        for asset in record.get('assets', []) + record.get('new_assets', []) + record.get('font_assets', []):
            if asset.get('source') and asset.get('sha256'):
                path = str(safe_path(asset['source'], regular=True))
                require(plan['retained_files'].get(path, {}).get('sha256') == asset['sha256'],
                        'Cleanup plan omitted an original build input: ' + path)
    for path in plan['protected_files']:
        require(plan['retained_files'].get(path, {}).get('sha256') == plan['protected_hashes'].get(path),
                'Explicit protected source is absent from the retained hash set')


def apply(plan_path, audit):
    from windows_runtime import _ensure_editor_closed
    _ensure_editor_closed(True)
    plan_path = safe_path(plan_path, regular=True)
    plan = read(plan_path)
    require(plan.get('schema') == 'jy-cache-cleanup-plan/v1', 'Unsupported cleanup plan')
    fingerprint = hashlib.sha256(json.dumps(plan, sort_keys=True).encode('utf-8')).hexdigest()
    audit = safe_path(audit, exists=False)
    for item in plan['candidates']:
        candidate = safe_path(item['path'], exists=False)
        require(not (audit == candidate or audit.is_relative_to(candidate) or candidate.is_relative_to(audit)),
                'Cleanup audit must be outside all deletion candidates')
    if audit.exists():
        require(read(audit / 'binding.json').get('plan_sha256') == fingerprint,
                'Existing cleanup audit belongs to another plan')
    else:
        audit.mkdir(parents=True)
        save(audit / 'binding.json', {'plan_sha256': fingerprint, 'created_ns': time.time_ns()})
        save(audit / 'plan.json', plan)
    journal = audit / 'deleted.jsonl'
    count = 0
    try:
        allowed = [safe_path(p, directory=True) for p in plan['allowed_roots']]
        _verify_retained(plan)
        expected_paths = {str(_relative(Path(item['path']), name)): info
                          for item in plan['candidates'] for name, info in _file_map(item['files']).items()}
        intents, deleted = set(), set()
        for event in _events(journal):
            path = event.get('path')
            if event.get('event') not in {'intent', 'deleted', 'recovered-deleted'}:
                continue
            require(path in expected_paths and all(event.get(k) == v for k, v in expected_paths[path].items()),
                    'Cleanup journal path/fingerprint is outside this plan')
            if event['event'] == 'intent':
                intents.add(path)
            else:
                require(path in intents, 'Cleanup journal deletion lacks a durable intent')
                deleted.add(path)
        for item in plan['candidates']:
            folder = safe_path(item['path'], exists=False)
            _candidate_policy(folder, allowed, [Path(p) for p in plan['retained_files']])
            require(not any(Path(name).name in FORBIDDEN_NAMES for name in item['files']),
                    'Delivery, build or index file in cleanup plan')
            expected_remaining = {}
            for relative, info in _file_map(item['files']).items():
                path = _relative(folder, relative)
                raw = str(path)
                if path.exists():
                    require(raw not in deleted, 'Previously deleted cache was recreated; prepare a new plan')
                    expected_remaining[relative] = info
                else:
                    require(raw in intents, 'Cache disappeared without a cleanup intent; inspect manually')
                    if raw not in deleted:
                        _append(journal, {'event': 'recovered-deleted', 'path': raw, **info,
                                          'allocation_statistics_known': False})
                        deleted.add(raw)
            actual = inventory(folder) if folder.exists() else {}
            require(actual == expected_remaining, 'Cache changed after cleanup preparation: ' + str(folder))
        for item in plan['candidates']:
            folder = safe_path(item['path'], exists=False)
            for relative, expected in _file_map(item['files']).items():
                path = _relative(folder, relative)
                raw = str(path)
                if raw in deleted:
                    continue
                safe_path(path, regular=True)
                verified_digest(path, expected['sha256'])
                _ensure_editor_closed(True)
                _append(journal, {'event': 'intent', 'path': raw, **expected})
                released = unlink_owned_file(path, allowed, plan['protected_files'])
                _append(journal, {'event': 'deleted', 'path': raw, **expected, **released})
                deleted.add(raw)
                count += 1
            if folder.exists():
                for directory, _, _ in os.walk(folder, topdown=False, followlinks=False):
                    safe_path(directory, directory=True).rmdir()
        _verify_retained(plan)
        events = _events(journal)
        result = {'status': 'regenerable-caches-removed', 'files_removed': len(deleted),
                  'files_removed_this_attempt': count, 'logical_bytes_removed': plan['logical_bytes'],
                  'known_released_allocation_bytes': sum(e.get('released_allocation_bytes', 0)
                                                       for e in events if e.get('event') == 'deleted'),
                  'allocation_statistics_complete': not any(e.get('event') == 'recovered-deleted' for e in events),
                  'actual_space_note': 'Shared hard links may retain bytes in the media pool.',
                  'protected_files_unchanged': True, 'retained_builds_verified': len(plan['source_builds']),
                  'journal': str(journal), 'finished_at': time.time()}
        save(audit / 'result.json', result)
        return result
    except BaseException as error:
        failure = {'status': 'cleanup-interrupted', 'error': str(error),
                   'files_removed_this_attempt': count, 'journal': str(journal),
                   'recovery': 'Resume the same plan and audit; remaining files and retained inputs are revalidated.',
                   'manual_inspection_required_if_inputs_changed': True, 'finished_at': time.time()}
        save(audit / ('failure-' + uuid.uuid4().hex + '.json'), failure)
        save(audit / 'failure.json', failure)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    plan = commands.add_parser('prepare')
    plan.add_argument('--request', type=Path, required=True)
    plan.add_argument('--out', type=Path, required=True)
    run = commands.add_parser('apply')
    run.add_argument('--plan', type=Path, required=True)
    run.add_argument('--audit', type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.request, args.out) if args.command == 'prepare' else apply(args.plan, args.audit)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
