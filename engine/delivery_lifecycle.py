"""Four-slot deliveries with explicit ownership and recoverable native revisions.

This module never discovers ownership from draft names. The caller supplies a
frozen manifest of exact draft IDs, paths and complete file hashes. Mutable
operations require the editor to be closed and use the native root lock/DACL
adapter. Revision directories stay outside the scan root; a pending index is
only a JSON file beside the original index, preserving its inherited DACL.
"""
from __future__ import annotations

from copy import deepcopy
import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import stat
import time
import uuid

import jy14_headless as j


SCHEMA = 'jy-delivery-lifecycle/v1'
ARCHIVE_SCHEMA = 'jy-delivery-archive/v1'
TRANSACTION_SCHEMA = 'jy-delivery-transaction/v1'


class LifecycleError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise LifecycleError(message)


def _packed(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + '\n').encode('utf-8')


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _ordinary(path):
    info = Path(path).lstat()
    require(not stat.S_ISLNK(info.st_mode) and
            not getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400),
            'Symlinks/reparse points are forbidden: ' + str(path))
    return info


def _path(value, *, exists=True, directory=None):
    require(isinstance(value, (str, Path)), 'An absolute path is required')
    path = Path(value)
    require(path.is_absolute() and '..' not in path.parts and
            not str(path).startswith(('\\\\?\\', '\\\\.\\')), 'Unsafe absolute path: ' + str(path))
    # Check ancestors before resolve, including junctions that Path.is_symlink
    # alone does not reject on Windows. Missing suffixes may be created later.
    for current in [*reversed(path.parents), path]:
        if current.exists() or current.is_symlink():
            _ordinary(current)
    resolved = path.resolve(strict=exists)
    if exists and directory is not None:
        mode = _ordinary(resolved).st_mode
        require(stat.S_ISDIR(mode) if directory else stat.S_ISREG(mode),
                'Unexpected path type: ' + str(path))
    return resolved


def _same(a, b):
    return j.same_native_path(a, b)


def _within(path, root):
    return path == root or path.is_relative_to(root)


def _relative(name):
    require(isinstance(name, str) and name and ':' not in name and '\x00' not in name,
            'Invalid manifest relative path')
    a, b = PurePosixPath(name.replace('\\', '/')), PureWindowsPath(name)
    require(not a.is_absolute() and not b.is_absolute() and '..' not in a.parts and
            '..' not in b.parts and not b.drive, 'Manifest path escapes its root')
    return a.as_posix()


def _file_map(value):
    require(isinstance(value, dict) and value, 'Complete nonempty file hashes are required')
    result = {}
    for name, info in value.items():
        name = _relative(name)
        require(name not in result and isinstance(info, dict) and
                re.fullmatch(r'[0-9a-f]{64}', str(info.get('sha256', ''))) and
                type(info.get('size')) is int and info['size'] >= 0,
                'Invalid or colliding file manifest entry')
        result[name] = {'sha256': info['sha256'], 'size': info['size']}
    return result


def files_manifest(folder):
    """Hash every regular file; reject aliases before descending or reading."""
    folder = _path(folder, directory=True)
    result = {}
    def traversal_error(error):
        raise error
    for current, dirs, files in os.walk(folder, topdown=True, followlinks=False, onerror=traversal_error):
        for name in dirs:
            require(stat.S_ISDIR(_ordinary(Path(current) / name).st_mode), 'Non-directory in draft tree')
        for name in files:
            path = Path(current) / name
            before = _ordinary(path)
            require(stat.S_ISREG(before.st_mode), 'Draft trees require regular files')
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(block)
            after = _ordinary(path)
            require((before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                    (after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'File changed while hashing')
            result[path.relative_to(folder).as_posix()] = {'sha256': digest.hexdigest(), 'size': after.st_size}
    return result


def _verify_tree(path, expected):
    require(files_manifest(path) == expected, 'Draft file hash conflict: ' + str(path))


@dataclass(frozen=True)
class Snapshot:
    path: Path
    content: bytes
    sha256: str
    mode: int
    fingerprint: tuple


def _snapshot(path):
    path = _path(path, directory=False)
    before = _ordinary(path)
    content = path.read_bytes()
    after = _ordinary(path)
    fingerprint = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    require(fingerprint(before) == fingerprint(after), 'File changed during snapshot: ' + str(path))
    return Snapshot(path, content, _sha(content), stat.S_IMODE(after.st_mode), fingerprint(after))


def _unchanged(snapshot):
    current = _snapshot(snapshot.path)
    require((current.sha256, current.fingerprint) == (snapshot.sha256, snapshot.fingerprint),
            'Snapshot conflict: ' + str(snapshot.path))


def _json(raw):
    def pairs(rows):
        value = {}
        for key, item in rows:
            require(key not in value, 'Duplicate JSON key')
            value[key] = item
        return value
    value = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=pairs,
                       parse_constant=lambda _: require(False, 'Nonfinite JSON value'))
    require(isinstance(value, dict), 'JSON object required')
    return value


def _id(value):
    require(isinstance(value, str) and value.strip() == value and 0 < len(value) <= 128,
            'Nonempty draft ID required')
    return value.casefold()


def _label(value):
    require(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', value),
            'Delivery/slot/archive IDs require simple ASCII labels')
    return value


def _nearest_existing(path):
    while not path.exists():
        path = path.parent
    return path


class NativeBackend:
    """Thin seam around the existing native closure, lock and ACL mechanisms."""
    def __init__(self):
        self.draft_root = j.nd.DRAFT_ROOT
        self.helper = j.nd.helper()

    def validate_runtime(self):
        return self.helper._validate_runtime_environment()

    def ensure_closed(self):
        return self.helper._ensure_editor_closed(True)

    def acquire(self, root):
        return self.helper._acquire_directory_transaction_lock(root, 'delivery root')[0]

    def release(self, token):
        self.helper._release_directory_transaction_lock(token)

    def attributes(self, path):
        return j.read_xattrs(path)

    def copy_attributes(self, attrs, destination, audit, source):
        return j.copy_xattrs(attrs, destination, audit, source)

    def verify_build(self, build):
        return j.verify_build(build)

    def metadata(self, path):
        return self.helper._decrypt_metadata_in_memory(path)

    def entry(self, metadata, target):
        return j.index_entry(metadata, target)

    def copy_draft(self, source, destination, record):
        native_record = dict(record, files={str(Path(_relative(name))): info
                                           for name, info in record['files'].items()})
        return j.copy_draft_dependencies(source, destination, native_record)

    def sync(self, token):
        os.fsync(token)


def _load(manifest_path, backend):
    frozen = _snapshot(manifest_path)
    manifest = _json(frozen.content)
    require(manifest.get('schema') == SCHEMA, 'Unsupported delivery manifest schema')
    _label(manifest.get('delivery_id'))
    root = _path(manifest.get('draft_root'), directory=True)
    require(_same(root, _path(backend.draft_root, directory=True)), 'Manifest is not bound to the native draft root')
    archive = _path(manifest.get('archive_root'), exists=False)
    require(not archive.exists() or archive.is_dir(), 'Archive root must be a directory')
    require(not _within(archive, root) and not _within(root, archive), 'Archive must be outside the scan root')
    require(_nearest_existing(archive).stat().st_dev == root.stat().st_dev and
            (not root.drive or archive.drive.casefold() == root.drive.casefold()), 'Archive root must be on the same volume')
    require(not _within(frozen.path, root), 'Manifest must be outside the live scan root')
    require(re.fullmatch(r'[0-9a-f]{64}', str(manifest.get('expected_index_sha256', ''))),
            'Manifest requires expected_index_sha256')
    owned = manifest.get('owned_drafts')
    require(isinstance(owned, list) and len(owned) >= 4, 'Explicit owned_drafts are required')
    ids, paths = set(), set()
    for row in owned:
        require(isinstance(row, dict), 'Owned draft object required')
        identity = _id(row.get('draft_id'))
        path = _path(row.get('path'), exists=False)
        require(path.parent == root and identity not in ids and str(path).casefold() not in paths,
                'Owned drafts must have unique exact direct-child paths and IDs')
        ids.add(identity); paths.add(str(path).casefold())
        row['path'], row['files'] = str(path), _file_map(row.get('files'))
    slots = manifest.get('slots')
    require(isinstance(slots, list) and len(slots) == 4, 'A delivery has exactly four logical slots')
    slot_ids, current = set(), set()
    for slot in slots:
        _label(slot.get('slot_id'))
        identity = _id(slot.get('draft_id'))
        path = _path(slot.get('path'), exists=False)
        matching = [r for r in owned if _id(r['draft_id']) == identity and _same(r['path'], path)]
        require(len(matching) == 1 and slot['slot_id'] not in slot_ids and identity not in current,
                'Each unique slot must reference one unique owned draft')
        slot_ids.add(slot['slot_id']); current.add(identity)
        slot['path'] = str(path)
    archives = manifest.setdefault('archives', [])
    require(isinstance(archives, list), 'archives must be a list')
    archive_ids, archived = set(), set()
    for row in archives:
        _label(row.get('archive_id'))
        identity = _id(row.get('draft_id'))
        path = _path(row.get('path'), exists=False)
        original = _path(row.get('original_path'), exists=False)
        require(identity in ids and original.parent == root and _within(path, archive) and path != archive and
                row['archive_id'] not in archive_ids and row.get('state', 'archived') in {'archived', 'restored'},
                'Archive record escapes exact authorized roots or collides')
        owner = next(r for r in owned if _id(r['draft_id']) == identity)
        require(_same(owner['path'], original) and _file_map(row.get('files')) == owner['files'],
                'Archive ownership or hash map differs')
        row['files'] = owner['files']
        row['path'], row['original_path'] = str(path), str(original)
        archive_ids.add(row['archive_id'])
        if row.get('state', 'archived') == 'archived':
            require(identity not in archived and identity not in current, 'An active archive cannot also be current')
            archived.add(identity)
    return frozen, manifest, root, archive


def _index(root, manifest):
    snap = _snapshot(root / 'root_meta_info.json')
    require(snap.sha256 == manifest['expected_index_sha256'], 'Home index hash conflict')
    value = _json(snap.content)
    require(_same(value.get('root_path'), root) and isinstance(value.get('all_draft_store'), list),
            'Home index root_path or entries differ')
    return snap, value


def _entry_for(index, row):
    found = [(i, e) for i, e in enumerate(index['all_draft_store'])
             if _id(e.get('draft_id')) == _id(row['draft_id']) or _same(e.get('draft_fold_path'), row['path'])]
    require(len(found) == 1 and _id(found[0][1].get('draft_id')) == _id(row['draft_id']) and
            _same(found[0][1].get('draft_fold_path'), row['path']), 'Owned home entry conflict: ' + row['draft_id'])
    return found[0]


def _live_owned(manifest, index, *, verify=True):
    archived = {_id(a['draft_id']) for a in manifest['archives'] if a.get('state', 'archived') == 'archived'}
    live = [r for r in manifest['owned_drafts'] if _id(r['draft_id']) not in archived]
    for row in live:
        _entry_for(index, row)
        if verify:
            _verify_tree(row['path'], row['files'])
    for identity in archived:
        require(not any(_id(e.get('draft_id')) == identity for e in index['all_draft_store']),
                'Archived draft remains registered')
    return live


def inspect(manifest_path, *, _backend=None):
    """Read-only ownership/hash inspection; never heals or rewrites an index."""
    backend = _backend or NativeBackend()
    frozen, manifest, root, archive = _load(manifest_path, backend)
    conflicts = []
    try:
        _, index = _index(root, manifest)
        live = _live_owned(manifest, index)
    except (ValueError, OSError) as error:
        conflicts.append(str(error)); live = []
    current = {_id(s['draft_id']) for s in manifest['slots']}
    return {'status': 'delivery-inspected' if not conflicts else 'delivery-conflict',
            'delivery_id': manifest['delivery_id'], 'manifest_sha256': frozen.sha256,
            'slots': deepcopy(manifest['slots']), 'task_visible_count': len(live),
            'archive_candidates': [deepcopy(r) for r in live if _id(r['draft_id']) not in current],
            'archive_root': str(archive), 'archives': deepcopy(manifest['archives']),
            'conflicts': conflicts, 'live_written': False}


def _write_new(path, content, mode=0o600):
    _path(path, exists=False)
    with Path(path).open('xb') as stream:
        os.chmod(path, mode)
        stream.write(content); stream.flush(); os.fsync(stream.fileno())


def _fresh_private(path, root):
    path = _path(path, exists=False)
    require(not _within(path, root) and not _within(root, path) and not path.exists(),
            'Output must be a fresh private directory outside the live scan root')
    path.mkdir(parents=True)
    return _path(path, directory=True)


def _move(source, destination, source_root, destination_root):
    source = _path(source, directory=True)
    destination = _path(destination, exists=False)
    require(source != source_root and destination != destination_root and
            _within(source, source_root) and _within(destination, destination_root) and
            not destination.exists(), 'Move escapes authorized roots or overwrites a directory')
    require(source.stat().st_dev == _nearest_existing(destination).stat().st_dev, 'Move must stay on one volume')
    destination.parent.mkdir(parents=True, exist_ok=True)
    _path(destination.parent, directory=True)
    j.exclusive_rename(source, destination)


class _Transaction:
    def __init__(self, manifest_path, audit, kind, backend, runtime):
        self.backend, self.kind = backend, kind
        self.runtime = runtime
        self.manifest_snapshot, self.manifest, self.root, self.archive_root = _load(manifest_path, backend)
        self.index_snapshot, self.original_index = _index(self.root, self.manifest)
        self.live = _live_owned(self.manifest, self.original_index)
        self.index_attrs = backend.attributes(self.index_snapshot.path)
        self.manifest_attrs = backend.attributes(self.manifest_snapshot.path)
        self.audit = _fresh_private(audit, self.root)
        self.txid = uuid.uuid4().hex
        self.private = self.archive_root / self.manifest['delivery_id'] / 'transactions' / self.txid
        self.private = _fresh_private(self.private, self.root)
        self.next = deepcopy(self.manifest)
        self.index = deepcopy(self.original_index)
        self.moves = []
        self.phase = 'preflight'
        self.index_committed = False
        self.manifest_committed = False
        _write_new(self.audit / 'index.original.json', self.index_snapshot.content)
        _write_new(self.audit / 'manifest.original.json', self.manifest_snapshot.content)
        self.event('prepared')

    def event(self, phase, **extra):
        self.phase = phase
        item = {'schema': TRANSACTION_SCHEMA, 'transaction_id': self.txid, 'operation': self.kind,
                'phase': phase, 'time_us': time.time_ns() // 1000,
                'manifest': str(self.manifest_snapshot.path), 'private': str(self.private),
                'index_committed': self.index_committed, 'manifest_committed': self.manifest_committed,
                **extra}
        with (self.audit / 'events.jsonl').open('ab') as stream:
            stream.write(_packed(item).replace(b'\n', b'') + b'\n'); stream.flush(); os.fsync(stream.fileno())
        temp = self.audit / ('.transaction-' + uuid.uuid4().hex + '.tmp')
        _write_new(temp, _packed(item))
        os.replace(temp, self.audit / 'transaction.json')

    def archive(self, row):
        _, entry = _entry_for(self.original_index, row)
        archive_id = uuid.uuid4().hex[:16]
        container = self.archive_root / self.manifest['delivery_id'] / 'objects' / archive_id
        require(not container.exists(), 'Archive ID collision')
        container.mkdir(parents=True)
        target = container / 'draft'
        record = {'schema': ARCHIVE_SCHEMA, 'archive_id': archive_id, 'transaction_id': self.txid,
                  'draft_id': row['draft_id'], 'original_path': row['path'], 'path': str(target),
                  'files': deepcopy(row['files']), 'entry': deepcopy(entry), 'state': 'archived',
                  'original_index_sha256': self.index_snapshot.sha256}
        _write_new(container / 'record.json', _packed(record))
        self.next['archives'].append(record)
        self.event('archive_intent', archive=record)
        self.backend.ensure_closed()
        _verify_tree(row['path'], row['files'])
        _unchanged(self.index_snapshot); _unchanged(self.manifest_snapshot)
        _move(row['path'], target, self.root, self.archive_root)
        self.moves.append((Path(row['path']), target, self.root, self.archive_root, row['files']))
        _verify_tree(target, row['files'])
        self.event('draft_archived', archive_id=archive_id)
        return record

    def place(self, source, target, expected):
        self.backend.ensure_closed()
        _verify_tree(source, expected)
        _unchanged(self.index_snapshot); _unchanged(self.manifest_snapshot)
        _move(source, target, self.archive_root, self.root)
        self.moves.append((Path(source), Path(target), self.archive_root, self.root, expected))
        _verify_tree(target, expected)
        self.event('incoming_placed', target=str(target))

    def commit(self):
        # Preserve the native counter verbatim: its semantics are not inferred
        # from the number of visible entries. Only exact owned entries change.
        require(self.index.get('draft_ids') == self.original_index.get('draft_ids'), 'Native draft_ids counter changed')
        new_live = _live_owned(self.next, self.index)
        require(len(new_live) == 4, 'Delivery must have exactly four visible owned drafts after commit')
        content = _packed(self.index)
        self.next['expected_index_sha256'] = _sha(content)
        self.next['last_transaction'] = {'transaction_id': self.txid, 'audit': str(self.audit), 'operation': self.kind}
        next_manifest = _packed(self.next)
        _write_new(self.audit / 'manifest.next.json', next_manifest)
        _write_new(self.audit / 'index.next.json', content)
        # A JSON file is not a draft directory. Keep only this pending index
        # beside its source so Windows resolves inherited ACEs against the
        # same parent; draft incoming trees still stay outside the scan root.
        # The existing adapter must preserve the complete source DACL exactly.
        prepared_index = self.index_snapshot.path.parent / ('.root_meta_info.delivery-' + self.txid + '.tmp')
        prepared_manifest = self.manifest_snapshot.path.parent / ('.delivery-manifest-' + self.txid + '.tmp')
        _write_new(prepared_index, content, self.index_snapshot.mode)
        _write_new(prepared_manifest, next_manifest, self.manifest_snapshot.mode)
        attrs_index, attrs_manifest = self.index_attrs, self.manifest_attrs
        require(self.backend.attributes(self.index_snapshot.path) == attrs_index and
                self.backend.attributes(self.manifest_snapshot.path) == attrs_manifest,
                'Security attributes changed after preflight')
        for name, source, target, attrs in [
            ('index-security', self.index_snapshot.path, prepared_index, attrs_index),
            ('manifest-security', self.manifest_snapshot.path, prepared_manifest, attrs_manifest),
        ]:
            security_audit = self.audit / name; security_audit.mkdir()
            copied, _ = self.backend.copy_attributes(attrs, target, security_audit, source)
            require(copied == attrs and self.backend.attributes(target) == attrs,
                    'Security attributes differ before commit')
        self.event('commit_prepared', prepared_index=str(prepared_index), prepared_manifest=str(prepared_manifest))
        self.backend.ensure_closed()
        _unchanged(self.index_snapshot); _unchanged(self.manifest_snapshot)
        require(self.backend.attributes(self.index_snapshot.path) == attrs_index and
                self.backend.attributes(self.manifest_snapshot.path) == attrs_manifest, 'Security attributes changed')
        require(prepared_index.read_bytes() == content and prepared_manifest.read_bytes() == next_manifest,
                'Prepared transaction bytes changed')
        os.replace(prepared_index, self.index_snapshot.path)
        self.index_committed = True
        self.event('index_committed')
        require(self.index_snapshot.path.read_bytes() == content and
                self.backend.attributes(self.index_snapshot.path) == attrs_index, 'Committed index differs')
        _unchanged(self.manifest_snapshot)
        os.replace(prepared_manifest, self.manifest_snapshot.path)
        self.manifest_committed = True
        require(self.manifest_snapshot.path.read_bytes() == next_manifest and
                self.backend.attributes(self.manifest_snapshot.path) == attrs_manifest, 'Committed manifest differs')
        self.event('complete', task_visible_count=4)
        result = {'status': 'delivery-' + self.kind + '-complete', 'delivery_id': self.manifest['delivery_id'],
                  'transaction_id': self.txid, 'audit': str(self.audit), 'task_visible_count': 4,
                  'slots': deepcopy(self.next['slots']), 'manifest_sha256': _sha(next_manifest),
                  'index_sha256': _sha(content), 'draft_ids_policy': 'preserved-uninterpreted-counter',
                  'archives': deepcopy(self.next['archives']), 'security_attributes_preserved': True}
        _write_new(self.audit / 'result.json', _packed(result))
        return result

    def failed(self, error):
        # Roll back only before the index commit, only while every protected
        # snapshot and moved file still has its expected bytes. Otherwise retain
        # the journal/next manifest; never overwrite a newly edited directory.
        rolled_back, rollback_error = False, None
        if not self.index_committed:
            try:
                self.backend.ensure_closed()
                _unchanged(self.index_snapshot); _unchanged(self.manifest_snapshot)
                for source, target, source_root, target_root, expected in reversed(self.moves):
                    _verify_tree(target, expected)
                    _move(target, source, target_root, source_root)
                rolled_back = True
            except Exception as recovery:
                rollback_error = str(recovery)
        try:
            self.event('failed', error=str(error), failed_phase=self.phase,
                       precommit_moves_rolled_back=rolled_back, rollback_error=rollback_error,
                       recovery='Use retained manifest.next.json only after inspecting transaction phase and current hashes')
        except OSError:
            pass


def _execute(manifest_path, audit, operation, action, backend):
    runtime = backend.validate_runtime()
    backend.ensure_closed()
    _, _, root, _ = _load(manifest_path, backend)
    token = backend.acquire(root)
    transaction = None
    try:
        transaction = _Transaction(manifest_path, audit, operation, backend, runtime)
        result = action(transaction)
        return result
    except Exception as error:
        if transaction is not None:
            transaction.failed(error)
        else:
            try:
                failure_audit = _fresh_private(audit, root)
                _write_new(failure_audit / 'failure.json', _packed({
                    'status': 'failed', 'phase': 'preflight', 'error': str(error),
                    'live_written': False, 'manifest': str(manifest_path)}))
            except (OSError, ValueError):
                pass
        raise LifecycleError(str(error) + '; retained transaction audit: ' + str(audit)) from error
    finally:
        backend.release(token)


def reconcile(manifest_path, audit, *, _backend=None):
    """Archive only explicitly owned noncurrent drafts; keep four exact slots."""
    backend = _backend or NativeBackend()
    def action(tx):
        current = {_id(s['draft_id']) for s in tx.manifest['slots']}
        retired = [r for r in tx.live if _id(r['draft_id']) not in current]
        for row in retired:
            tx.archive(row)
        retired_ids = {_id(r['draft_id']) for r in retired}
        tx.index['all_draft_store'] = [e for e in tx.index['all_draft_store'] if _id(e.get('draft_id')) not in retired_ids]
        return tx.commit()
    return _execute(manifest_path, audit, 'reconcile', action, backend)


def promote(manifest_path, slot_id, build, audit, *, _backend=None):
    """Promote a verified fresh build into one stable slot, archiving its prior revision."""
    backend = _backend or NativeBackend()
    _label(slot_id)
    build = _path(build, directory=True)
    def action(tx):
        require(len(tx.live) == 4, 'Reconcile owned revisions before promoting')
        slot = next((s for s in tx.manifest['slots'] if s['slot_id'] == slot_id), None)
        require(slot is not None, 'Unknown delivery slot')
        require(not _within(build, tx.root), 'Build must be outside the live scan root')
        frozen_build = _snapshot(build / 'build.json')
        frozen_plan = _snapshot(build / 'plan.json')
        incoming_files = files_manifest(build / 'draft')
        record = backend.verify_build(build)
        require(record.get('runtime_profile') == tx.runtime.get('runtime_profile'),
                'Incoming build runtime differs from the validated native runtime')
        target = _path(record['target'], exists=False)
        expected = _file_map(record['files'])
        require(incoming_files == expected, 'Incoming files differ from the verified build')
        require(target.parent == tx.root and not target.exists() and
                not any(_same(r['path'], target) or _id(r['draft_id']) == _id(record['draft_id'])
                        for r in tx.manifest['owned_drafts']), 'Incoming target/ID is not a fresh owned revision')
        require(not any(_same(e.get('draft_fold_path'), target) or _id(e.get('draft_id')) == _id(record['draft_id'])
                        for e in tx.index['all_draft_store']), 'Incoming home entry collides')
        _verify_tree(build / 'draft', expected)
        metadata = backend.metadata(build / 'draft' / 'draft_meta_info.json')
        require(_id(metadata.get('draft_id')) == _id(record['draft_id']) and
                _same(metadata.get('draft_fold_path'), target), 'Verified build metadata identity differs')
        entry = backend.entry(metadata, target)
        incoming = tx.private / 'incoming'
        tx.event('incoming_copy_intent', build=str(build), target=str(target), build_sha256=frozen_build.sha256)
        materialized = (backend.copy_draft(build / 'draft', incoming, record)
                        if hasattr(backend, 'copy_draft') else
                        shutil.copytree(build / 'draft', incoming, copy_function=shutil.copy2))
        _write_new(tx.audit / 'incoming-media.json', _packed({
            'build': str(build), 'materialization': materialized if isinstance(materialized, list) else []}))
        _verify_tree(incoming, expected); _verify_tree(build / 'draft', expected)
        _unchanged(frozen_build); _unchanged(frozen_plan)
        old = next(r for r in tx.live if _id(r['draft_id']) == _id(slot['draft_id']))
        position, _ = _entry_for(tx.index, old)
        tx.archive(old)
        tx.place(incoming, target, expected)
        new_row = {'draft_id': record['draft_id'], 'path': str(target), 'files': expected,
                   'build': str(build), 'build_sha256': frozen_build.sha256}
        tx.next['owned_drafts'].append(new_row)
        new_slot = next(s for s in tx.next['slots'] if s['slot_id'] == slot_id)
        new_slot.update(draft_id=record['draft_id'], path=str(target))
        tx.index['all_draft_store'][position] = entry
        _unchanged(frozen_build); _unchanged(frozen_plan)
        return tx.commit()
    return _execute(manifest_path, audit, 'promote', action, backend)


def restore(manifest_path, archive_id, audit, out=None, slot_id=None, *, _backend=None):
    """Default to a private byte-identical validation copy; explicit slot replaces one revision.

    Private copies retain the recorded native absolute bindings and are not
    registered or claimed playable. A slot restore uses the exact original
    live path so its saved native bindings remain valid.
    """
    backend = _backend or NativeBackend()
    _label(archive_id)
    require(not (slot_id is not None and out is not None), 'Choose a private restore or an explicit slot replacement')
    if slot_id is not None:
        _label(slot_id)
    def action(tx):
        saved = next((a for a in tx.manifest['archives'] if a['archive_id'] == archive_id and
                      a.get('state', 'archived') == 'archived'), None)
        require(saved is not None, 'Unknown active archive')
        _verify_tree(saved['path'], saved['files'])
        if slot_id is None:
            destination = _path(out, exists=False) if out is not None else tx.audit / 'restored-private'
            require(not _within(destination, tx.archive_root) and not destination.exists(),
                    'Private verification output must not overwrite archives')
            require(not _within(destination, tx.root) and not _within(tx.root, destination),
                    'Private restore output must be outside the live scan root')
            materialized = (backend.copy_draft(saved['path'], destination, {'files': saved['files']})
                            if hasattr(backend, 'copy_draft') else
                            shutil.copytree(saved['path'], destination, copy_function=shutil.copy2))
            _write_new(tx.audit / 'restore-media.json', _packed({
                'archive_id': archive_id,
                'materialization': materialized if isinstance(materialized, list) else []}))
            _verify_tree(destination, saved['files']); _verify_tree(saved['path'], saved['files'])
            _unchanged(tx.index_snapshot); _unchanged(tx.manifest_snapshot)
            tx.event('complete_private_restore', destination=str(destination))
            result = {'status': 'delivery-restored-private', 'audit': str(tx.audit), 'transaction_id': tx.txid,
                      'out': str(destination), 'archive_id': archive_id, 'original_path': saved['original_path'],
                      'native_bindings_rebased': False, 'registered': False, 'index_written': False,
                      'files_verified': True}
            _write_new(tx.audit / 'result.json', _packed(result))
            return result
        require(len(tx.live) == 4, 'Reconcile before restoring a slot')
        slot = next((s for s in tx.manifest['slots'] if s['slot_id'] == slot_id), None)
        require(slot is not None, 'Unknown delivery slot')
        target = _path(saved['original_path'], exists=False)
        require(not target.exists(), 'Archive original live path is occupied')
        metadata = backend.metadata(Path(saved['path']) / 'draft_meta_info.json')
        require(_id(metadata.get('draft_id')) == _id(saved['draft_id']) and
                _same(metadata.get('draft_fold_path'), target), 'Archived metadata identity/bindings differ')
        old = next(r for r in tx.live if _id(r['draft_id']) == _id(slot['draft_id']))
        position, _ = _entry_for(tx.index, old)
        tx.archive(old)
        tx.place(saved['path'], target, saved['files'])
        selected = next(a for a in tx.next['archives'] if a['archive_id'] == archive_id)
        selected.update(state='restored', restored_transaction_id=tx.txid)
        next_slot = next(s for s in tx.next['slots'] if s['slot_id'] == slot_id)
        next_slot.update(draft_id=saved['draft_id'], path=str(target))
        tx.index['all_draft_store'][position] = deepcopy(saved['entry'])
        return tx.commit()
    return _execute(manifest_path, audit, 'restore', action, backend)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('inspect', 'reconcile', 'promote', 'restore'):
        command = commands.add_parser(name)
        command.add_argument('--manifest', required=True)
        if name != 'inspect':
            command.add_argument('--audit', required=True)
        if name == 'promote':
            command.add_argument('--slot', required=True)
            command.add_argument('--build', required=True)
        if name == 'restore':
            command.add_argument('--archive-id', required=True)
            output = command.add_mutually_exclusive_group()
            output.add_argument('--out')
            output.add_argument('--slot')
    args = parser.parse_args(argv)
    if args.command == 'inspect':
        result = inspect(args.manifest)
    elif args.command == 'reconcile':
        result = reconcile(args.manifest, args.audit)
    elif args.command == 'promote':
        result = promote(args.manifest, args.slot, args.build, args.audit)
    else:
        result = restore(args.manifest, args.archive_id, args.audit, args.out, args.slot)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get('status') != 'delivery-conflict' else 2


if __name__ == '__main__':
    raise SystemExit(main())
