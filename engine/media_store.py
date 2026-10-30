"""Verified immutable media sharing and explicitly scoped, resumable deduplication.

Original sources are read only.  The store owns a byte-for-byte copy; only that
copy is made read-only and linked into a working snapshot.  A writer must call
``ensure_private_copy`` before opening a shared dependency for modification.
The read-only bit is an accident guard, not an ACL or protection from an admin.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import time
import uuid


SCHEMA = 'jy14-media-store/v1'
SCAN_SCHEMA = 'jy14-media-scan/v1'
MEDIA_SUFFIXES = frozenset({'.mp4', '.mov', '.mkv', '.m4v', '.avi', '.webm',
                            '.mts', '.m2ts', '.mp3', '.wav', '.m4a', '.aac',
                            '.flac', '.ogg', '.opus'})
DEFAULT_MIN_BYTES = 64 * 1024 * 1024
IMMUTABLE_CONTRACT = 'shared-read-only-media; isolate with ensure_private_copy before writing'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _absolute(path):
    path = Path(path)
    require(path.is_absolute(), 'An absolute path is required: ' + str(path))
    require('..' not in path.parts, 'Parent path traversal is not allowed: ' + str(path))
    return path


def _reparse(info):
    return bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def safe_path(path, *, exists=True, regular=False, directory=False):
    """Reject symlinks and Windows reparse points in every existing component."""
    path = _absolute(path)
    for component in reversed((path, *path.parents)):
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        require(not stat.S_ISLNK(info.st_mode) and not _reparse(info),
                'Symlink/reparse path is not allowed: ' + str(component))
    if exists:
        info = path.stat()
        require(not regular or stat.S_ISREG(info.st_mode), 'Expected a regular file: ' + str(path))
        require(not directory or stat.S_ISDIR(info.st_mode), 'Expected a directory: ' + str(path))
    return path.resolve(strict=exists)


def _stamp(path):
    info = path.stat()
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def _digest(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def verified_digest(path, expected=None):
    path = safe_path(path, regular=True)
    before = _stamp(path)
    actual = _digest(path)
    require(before == _stamp(path), 'Media changed during hashing: ' + str(path))
    if expected is not None:
        require(isinstance(expected, str) and re.fullmatch('[a-f0-9]{64}', expected), 'Invalid SHA-256')
        require(actual == expected, 'Media SHA-256 differs: ' + str(path))
    return actual


def _windows_allocation(path):
    """FILE_STANDARD_INFO reports allocation and links without admin access."""
    from ctypes import wintypes

    class StandardInfo(ctypes.Structure):
        _fields_ = [('AllocationSize', ctypes.c_longlong), ('EndOfFile', ctypes.c_longlong),
                    ('NumberOfLinks', wintypes.DWORD), ('DeletePending', ctypes.c_ubyte),
                    ('Directory', ctypes.c_ubyte)]

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    get = kernel.GetFileInformationByHandleEx
    get.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    get.restype = wintypes.BOOL
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL
    handle = create(str(path), 0x80, 7, None, 3, 0x00200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        result = StandardInfo()
        if not get(handle, 1, ctypes.byref(result), ctypes.sizeof(result)):
            raise ctypes.WinError(ctypes.get_last_error())
        return int(result.AllocationSize), int(result.NumberOfLinks)
    finally:
        close(handle)


def file_identity(path):
    path = safe_path(path, regular=True)
    info = path.stat()
    allocation, links = ((getattr(info, 'st_blocks', 0) * 512, info.st_nlink)
                         if os.name != 'nt' else _windows_allocation(path))
    return {'file_id': str(info.st_dev) + ':' + str(info.st_ino), 'volume_id': str(info.st_dev),
            'size': info.st_size, 'mtime_ns': info.st_mtime_ns, 'links': links,
            'allocated_bytes': allocation,
            'read_only': not bool(info.st_mode & stat.S_IWUSR)}


def _json(path, value, *, exclusive=False):
    path = safe_path(path, exists=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x' if exclusive else 'w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def default_pool(destination):
    destination = _absolute(destination)
    if os.name == 'nt':
        return Path(destination.anchor) / 'JianyingHeadless' / 'media-store'
    # Non-Windows callers normally pass an explicit same-volume pool in tests.
    return Path.home() / '.cache' / 'jianying-headless' / 'media-store'


def _pool(destination, root=None):
    destination = safe_path(destination, exists=False)
    destination.parent.mkdir(parents=True, exist_ok=True)
    safe_path(destination.parent, directory=True)
    root = safe_path(root or default_pool(destination), exists=False)
    require(root != Path(root.anchor), 'A media pool cannot be a volume root')
    root.mkdir(parents=True, exist_ok=True)
    safe_path(root, directory=True)
    require(root.stat().st_dev == destination.parent.stat().st_dev,
            'Media pool must be on the destination volume; choose a destination-volume pool')
    marker = root / 'store.json'
    if not marker.exists():
        try:
            _json(marker, {'schema': SCHEMA, 'contract': IMMUTABLE_CONTRACT}, exclusive=True)
        except FileExistsError:
            pass
    safe_path(marker, regular=True)
    require(json.loads(marker.read_text(encoding='utf-8')).get('schema') == SCHEMA,
            'Unrecognized media pool marker: ' + str(root))
    return root


def _copy_verified(source, destination, expected):
    before = _stamp(source)
    with source.open('rb') as src, destination.open('xb') as dst:
        shutil.copyfileobj(src, dst, 4 * 1024 * 1024)
        dst.flush()
        os.fsync(dst.fileno())
    require(before == _stamp(source), 'Source changed while copying: ' + str(source))
    verified_digest(destination, expected)
    verified_digest(source, expected)


def _pid_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return True  # Malformed owners are never treated as abandoned.
    if os.name != 'nt':
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        # Access denied is a live/inaccessible process, not evidence of death.
        return ctypes.get_last_error() != 87
    try:
        exit_code = wintypes.DWORD()
        return not kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code)) or exit_code.value == 259
    finally:
        kernel.CloseHandle(handle)


def _recover_stale_object_lock(lock, target):
    safe_path(lock, regular=True)
    payload = lock.read_bytes()
    try:
        owner = json.loads(payload)
    except (ValueError, UnicodeError):
        return False
    if _pid_alive(owner.get('pid')):
        return False
    temporary = safe_path(owner.get('temporary', str(target)), exists=False)
    require(temporary.parent == target.parent and
            re.fullmatch(re.escape(target.name) + r'\.tmp-[a-f0-9]{32}', temporary.name),
            'Abandoned pool lock has an unrecognized temporary path')
    require(lock.read_bytes() == payload, 'Pool lock owner changed during recovery')
    if temporary.exists():
        safe_path(temporary, regular=True)
        _unlink(temporary)
    lock.unlink()
    return True


def _ensure_object(source, root, expected):
    target = root / 'sha256' / expected[:2] / expected
    safe_path(target, exists=False)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        verified_digest(target, expected)
        require(file_identity(target)['read_only'], 'Pool object lost its read-only guard: ' + str(target))
        return target, False
    lock = target.with_suffix('.lock')
    if lock.exists():
        _recover_stale_object_lock(lock, target)
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError('Media object creation is in progress; retry after it completes: ' + str(lock))
    temporary = target.with_suffix('.tmp-' + uuid.uuid4().hex)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump({'pid': os.getpid(), 'created_ns': time.time_ns(), 'sha256': expected,
                       'temporary': str(temporary)}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        # Recheck after owning the lock; never overwrite an existing store object.
        if target.exists():
            verified_digest(target, expected)
            require(file_identity(target)['read_only'], 'Pool object lost its read-only guard')
            return target, False
        _copy_verified(source, temporary, expected)
        os.chmod(temporary, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        os.rename(temporary, target)
        verified_digest(target, expected)
        return target, True
    finally:
        if temporary.exists():
            _unlink(temporary)
        lock.unlink(missing_ok=True)


def _unlink(path):
    """Delete one owned name without chmod-ing all of its read-only hard links."""
    if os.name != 'nt' or not file_identity(path)['read_only']:
        Path(path).unlink()
        return
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    set_info = kernel.SetFileInformationByHandle
    set_info.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    set_info.restype = wintypes.BOOL
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL
    handle = create(str(path), 0x10000, 7, None, 3, 0x00200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        # FILE_DISPOSITION_DELETE | POSIX_SEMANTICS | IGNORE_READONLY_ATTRIBUTE.
        flags = wintypes.DWORD(0x13)
        if not set_info(handle, 21, ctypes.byref(flags), ctypes.sizeof(flags)):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        close(handle)


def _atomic_replace(temporary, destination):
    """Replace one name, including a read-only target, without touching its inode.

    Windows FILE_RENAME_INFO_EX can ignore the replaced name's read-only bit.
    Unlike chmod + replace, it leaves every other hard link and its guard intact.
    """
    if os.name != 'nt' or not file_identity(destination)['read_only']:
        os.replace(temporary, destination)
        return
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    set_info = kernel.SetFileInformationByHandle
    set_info.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    set_info.restype = wintypes.BOOL
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL
    name = str(destination)

    class RenameInfo(ctypes.Structure):
        _fields_ = [('Flags', wintypes.DWORD), ('RootDirectory', wintypes.HANDLE),
                    ('FileNameLength', wintypes.DWORD), ('FileName', wintypes.WCHAR * len(name))]

    info = RenameInfo()
    # REPLACE_IF_EXISTS | POSIX_SEMANTICS | IGNORE_READONLY_ATTRIBUTE.
    info.Flags = 0x43
    info.RootDirectory = None
    info.FileNameLength = len(name.encode('utf-16-le'))
    info.FileName = name
    handle = create(str(temporary), 0x10000, 7, None, 3, 0x00200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if not set_info(handle, 22, ctypes.byref(info), ctypes.sizeof(info)):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        close(handle)


def _roots(allowed_roots):
    require(allowed_roots, 'An explicit nonempty allowed-root list is required')
    roots = [safe_path(root, directory=True) for root in allowed_roots]
    require(all(root != Path(root.anchor) for root in roots), 'A volume root is too broad')
    return list(dict.fromkeys(roots))


def _owned(path, roots, protected_roots=()):
    path = safe_path(path, regular=True)
    require(any(path.is_relative_to(root) and path != root for root in roots),
            'File is outside the explicit allowed roots: ' + str(path))
    require(not any(path == root or path.is_relative_to(root) for root in protected_roots),
            'Protected source cannot be changed: ' + str(path))
    return path


def unlink_owned_file(path, allowed_roots, protected_roots=()):
    """Unlink an explicitly owned cache name; shared store bytes remain guarded."""
    path = _owned(path, _roots(allowed_roots), [safe_path(p) for p in protected_roots])
    before = file_identity(path)
    _unlink(path)
    return {'path': str(path), 'removed_file_id': before['file_id'],
            'released_allocation_bytes': before['allocated_bytes'] if before['links'] == 1 else 0}


def materialize_immutable(source, destination, expected_sha256, pool_root=None,
                          *, allow_copy_fallback=True):
    """Read/verify source, create a store-owned copy, and link it on the target volume.

    Existing targets must match and are never overwritten here.  Fallback copies
    remain read-only, are independently allocated, and are explicitly reported.
    """
    source = safe_path(source, regular=True)
    destination = safe_path(destination, exists=False)
    require(source != destination, 'Source and destination must differ')
    source_before = _stamp(source)
    verified_digest(source, expected_sha256)
    root = _pool(destination, pool_root)
    require(not destination.is_relative_to(root), 'A working destination cannot be inside the media pool')
    pooled, created = _ensure_object(source, root, expected_sha256)
    before = file_identity(source)
    fallback = None
    if destination.exists():
        verified_digest(destination, expected_sha256)
        mode = 'existing-hardlink' if os.path.samefile(pooled, destination) else 'existing-private-copy'
    else:
        try:
            os.link(pooled, destination)
            mode = 'hardlink'
        except OSError as error:
            if not allow_copy_fallback:
                raise
            # Failed links do not silently claim savings.  An existing/conflicting
            # destination is never replaced, including a racing creator.
            require(not destination.exists(), 'Destination appeared while linking')
            fallback = {'errno': error.errno, 'winerror': getattr(error, 'winerror', None),
                        'reason': str(error)}
            _copy_verified(pooled, destination, expected_sha256)
            os.chmod(destination, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
            mode = 'verified-copy-fallback'
    verified_digest(destination, expected_sha256)
    verified_digest(source, expected_sha256)
    require(source_before == _stamp(source), 'Source changed during materialization')
    after, object_info = file_identity(destination), file_identity(pooled)
    if mode in {'hardlink', 'existing-hardlink'}:
        require(after['file_id'] == object_info['file_id'] and after['read_only'],
                'Hard-link identity/read-only verification failed')
    return {'schema': SCHEMA, 'source': str(source), 'destination': str(destination),
            'sha256': expected_sha256, 'size': after['size'], 'method': mode,
            'pool_root': str(root), 'pool_object': str(pooled), 'pool_object_created': created,
            'pool_allocated_bytes_added': object_info['allocated_bytes'] if created else 0,
            'source_identity': before, 'destination_identity': after, 'pool_identity': object_info,
            'fallback': fallback, 'source_verified_unchanged': True, 'contract': IMMUTABLE_CONTRACT}


def ensure_private_copy(path, expected_sha256=None, *, allowed_roots):
    """Atomically replace one owned name with writable independently owned bytes."""
    path = _owned(path, _roots(allowed_roots))
    expected = verified_digest(path, expected_sha256)
    before = file_identity(path)
    temporary = path.with_name('.media-private-' + uuid.uuid4().hex + path.suffix)
    try:
        _copy_verified(path, temporary, expected)
        os.chmod(temporary, stat.S_IRUSR | stat.S_IWUSR)
        require(file_identity(temporary)['file_id'] != before['file_id'], 'Private copy still shares identity')
        require(file_identity(path)['file_id'] == before['file_id'], 'Target identity changed')
        verified_digest(path, expected)
        _atomic_replace(temporary, path)
        return {'path': str(path), 'sha256': expected, 'before': before,
                'after': file_identity(path), 'method': 'independent-writable-copy'}
    finally:
        if temporary.exists():
            _unlink(temporary)


def _summary(files):
    unique = {row['file_id']: row for row in files}
    by_hash = {}
    for row in files:
        by_hash.setdefault(row['sha256'], {})[row['file_id']] = row
    return {'paths': len(files), 'logical_bytes': sum(row['size'] for row in files),
            'unique_file_ids': len(unique),
            'unique_allocated_bytes': sum(row['allocated_bytes'] for row in unique.values()),
            'unique_content_hashes': len(by_hash),
            'duplicate_allocated_bytes': sum(sum(row['allocated_bytes'] for row in group.values()) -
                                             min(row['allocated_bytes'] for row in group.values())
                                             for group in by_hash.values())}


def scan_media(allowed_roots, *, min_bytes=DEFAULT_MIN_BYTES, protected_roots=()):
    roots = _roots(allowed_roots)
    protected = [safe_path(root) for root in protected_roots]
    require(type(min_bytes) is int and min_bytes > 0, 'min_bytes must be a positive integer')
    files, skipped, visited = [], [], set()
    for root in roots:
        for directory, names, filenames in os.walk(root, followlinks=False):
            safe_path(directory, directory=True)
            for name in list(names):
                path = Path(directory) / name
                if path.is_symlink() or _reparse(path.lstat()) or any(
                        path == p or path.is_relative_to(p) for p in protected):
                    names.remove(name)
                    skipped.append({'path': str(path), 'reason': 'reparse-or-protected-directory'})
            for name in filenames:
                path = Path(directory) / name
                if path.suffix.lower() not in MEDIA_SUFFIXES or str(path).casefold() in visited:
                    continue
                visited.add(str(path).casefold())
                info = path.lstat()
                if (not stat.S_ISREG(info.st_mode) or path.is_symlink() or _reparse(info) or
                        any(path == p or path.is_relative_to(p) for p in protected)):
                    skipped.append({'path': str(path), 'reason': 'unsafe-or-protected-file'})
                    continue
                if info.st_size < min_bytes:
                    continue
                path = _owned(path, roots, protected)
                digest = verified_digest(path)
                files.append({'path': str(path), 'sha256': digest, **file_identity(path)})
    files.sort(key=lambda row: row['path'].casefold())
    return {'schema': SCAN_SCHEMA, 'created_ns': time.time_ns(),
            'allowed_roots': [str(root) for root in roots],
            'protected_roots': [str(root) for root in protected],
            'min_bytes': min_bytes, 'suffixes': sorted(MEDIA_SUFFIXES),
            'files': files, 'skipped': skipped, 'summary': _summary(files),
            'mutation_performed': False, 'hash_policy': 'every included file fully hashed with stable stat'}


def _append_log(path, event):
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(event, ensure_ascii=False, separators=(',', ':')) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def _read_journal(path):
    payload = path.read_bytes()
    # fsync-ed complete records are retained; a torn final append can safely be
    # discarded because actual file identity, not the log, decides resume state.
    if payload and not payload.endswith(b'\n'):
        boundary = payload.rfind(b'\n') + 1
        require(boundary > 0, 'Journal header was interrupted; use a new journal')
        with path.open('r+b') as stream:
            stream.truncate(boundary)
            stream.flush()
            os.fsync(stream.fileno())
        payload = payload[:boundary]
    return [json.loads(line) for line in payload.decode('utf-8').splitlines() if line.strip()]


def _recover_temporary_links(events, roots, protected, manifest_paths):
    recovered = []
    for event in events:
        if event.get('event') != 'prepare':
            continue
        require(event.get('path') in manifest_paths, 'Journal recovery target is outside the scan')
        temporary = safe_path(event['temporary'], exists=False)
        require(temporary.name.startswith('.media-link-') and
                re.fullmatch(r'\.media-link-[a-f0-9]{32}\.[a-z0-9]+', temporary.name),
                'Unrecognized recovery temporary path')
        target = safe_path(event['path'], exists=False)
        require(temporary.parent == target.parent, 'Recovery temporary is not beside its target')
        if not temporary.exists():
            continue
        _owned(temporary, roots, protected)
        verified_digest(temporary, event['sha256'])
        pooled = safe_path(event['pool_object'], regular=True)
        require(os.path.samefile(temporary, pooled), 'Recovery temporary lost its pool identity')
        _unlink(temporary)
        recovered.append(str(temporary))
    return recovered


def dedupe_manifest(manifest, allowed_roots, log_path, *, protected_roots=(), pool_root=None):
    """Apply an explicitly approved scan; re-hash every path and journal per file.

    A crash after a committed replacement is idempotent: a retry detects the
    actual pool file ID.  No file is selected by matching name or size alone.
    """
    require(manifest.get('schema') == SCAN_SCHEMA, 'Unsupported media scan manifest')
    roots = _roots(allowed_roots)
    protected = [safe_path(root) for root in protected_roots]
    protected += [safe_path(root) for root in manifest.get('protected_roots', [])]
    allowed = {str(root).casefold() for root in roots}
    require(allowed == {str(safe_path(p, directory=True)).casefold() for p in manifest['allowed_roots']},
            'Allowed roots differ from the scan; rescan the explicit scope')
    fingerprint = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode('utf-8')).hexdigest()
    log_path = safe_path(log_path, exists=False)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    events = []
    if log_path.exists():
        events = _read_journal(log_path)
        require(events and events[0].get('manifest_sha256') == fingerprint,
                'Journal belongs to a different scan')
    else:
        _append_log(log_path, {'event': 'begin', 'schema': SCHEMA, 'manifest_sha256': fingerprint,
                               'allowed_roots': sorted(allowed), 'started_ns': time.time_ns()})
    recovered = _recover_temporary_links(events, roots, protected,
                                         {item['path'] for item in manifest['files']})
    if recovered:
        _append_log(log_path, {'event': 'recovered-temporary-links', 'paths': recovered})
    volume_roots = {str(root.stat().st_dev): root for root in roots}
    free_before = {volume: shutil.disk_usage(root).free for volume, root in volume_roots.items()}
    released, allocated, rows = 0, 0, []
    seen_paths = set()
    for item in manifest['files']:
        path = _owned(item['path'], roots, protected)
        require(str(path).casefold() not in seen_paths, 'Duplicate path in scan manifest')
        seen_paths.add(str(path).casefold())
        require(path.suffix.lower() in MEDIA_SUFFIXES and path.stat().st_size >= manifest['min_bytes'],
                'Manifest path is outside the declared large-media policy')
        require(path.stat().st_size == item['size'], 'Media size changed since scan: ' + str(path))
        verified_digest(path, item['sha256'])
        before = file_identity(path)
        root = _pool(path, pool_root)
        require(not path.is_relative_to(root), 'Refusing to deduplicate store-owned objects')
        pooled, created = _ensure_object(path, root, item['sha256'])
        object_info = file_identity(pooled)
        allocated += object_info['allocated_bytes'] if created else 0
        if os.path.samefile(path, pooled):
            row = {'path': str(path), 'sha256': item['sha256'], 'method': 'already-shared',
                   'before': before, 'after': before, 'released_allocation_bytes': 0,
                   'pool_object_created': created, 'pool_object': str(pooled)}
        else:
            temporary = path.with_name('.media-link-' + uuid.uuid4().hex + path.suffix)
            _append_log(log_path, {'event': 'prepare', 'path': str(path), 'sha256': item['sha256'],
                                   'before': before, 'temporary': str(temporary),
                                   'pool_object': str(pooled), 'pool_created': created})
            try:
                os.link(pooled, temporary)  # No fallback: dedupe must actually share identity.
                verified_digest(temporary, item['sha256'])
                require(file_identity(path)['file_id'] == before['file_id'], 'Target identity changed')
                verified_digest(path, item['sha256'])
                old_info = file_identity(path)
                _atomic_replace(temporary, path)
                require(os.path.samefile(path, pooled), 'Replacement did not share pool identity')
                verified_digest(path, item['sha256'])
                freed = old_info['allocated_bytes'] if old_info['links'] == 1 else 0
                released += freed
                row = {'path': str(path), 'sha256': item['sha256'], 'method': 'hardlink-replaced',
                       'before': before, 'after': file_identity(path),
                       'released_allocation_bytes': freed, 'pool_object_created': created,
                       'pool_object': str(pooled)}
            finally:
                if temporary.exists():
                    _unlink(temporary)
        rows.append(row)
        _append_log(log_path, {'event': 'committed', **row})
    actual = [{'path': item['path'], 'sha256': verified_digest(item['path'], item['sha256']),
               **file_identity(item['path'])} for item in manifest['files']]
    free_after = {volume: shutil.disk_usage(root).free for volume, root in volume_roots.items()}
    result = {'schema': SCHEMA, 'status': 'deduplicated-and-verified', 'journal': str(log_path),
              'manifest_sha256': fingerprint, 'files': rows, 'before': manifest['summary'],
              'after': _summary(actual), 'released_old_allocation_bytes': released,
              'pool_allocation_bytes_added': allocated,
              'verified_net_allocation_reduction_bytes': released - allocated,
              'disk_free_before': free_before, 'disk_free_after': free_after,
              'disk_free_delta_is_advisory': True, 'contract': IMMUTABLE_CONTRACT,
              'recovered_temporary_links': recovered,
              'source_paths_preserved': True, 'full_hash_verification': True}
    _append_log(log_path, {'event': 'complete', 'result': result})
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    scan = commands.add_parser('scan', help='Read-only full-hash inventory in explicit roots')
    scan.add_argument('--allow-root', action='append', required=True)
    scan.add_argument('--protect-root', action='append', default=[])
    scan.add_argument('--min-bytes', type=int, default=DEFAULT_MIN_BYTES)
    scan.add_argument('--out', required=True)
    dedupe = commands.add_parser('dedupe', help='Apply one explicit scan with a resumable journal')
    dedupe.add_argument('--manifest', required=True)
    dedupe.add_argument('--allow-root', action='append', required=True)
    dedupe.add_argument('--protect-root', action='append', default=[])
    dedupe.add_argument('--pool-root')
    dedupe.add_argument('--log', required=True)
    dedupe.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    if args.command == 'scan':
        value = scan_media(args.allow_root, min_bytes=args.min_bytes, protected_roots=args.protect_root)
    else:
        manifest = json.loads(safe_path(args.manifest, regular=True).read_text(encoding='utf-8'))
        value = dedupe_manifest(manifest, args.allow_root, args.log,
                                protected_roots=args.protect_root, pool_root=args.pool_root)
    _json(args.out, value, exclusive=True)
    print(json.dumps({'status': value.get('status', 'scanned'), 'out': args.out,
                      'summary': value.get('after', value.get('summary')),
                      'verified_net_allocation_reduction_bytes': value.get('verified_net_allocation_reduction_bytes')},
                     ensure_ascii=False))
    return value


if __name__ == '__main__':
    main()
