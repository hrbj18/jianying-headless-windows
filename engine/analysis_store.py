"""Local analysis records, exact evidence identities and process-scoped locks."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile


def require(value, message):
    if not value:
        raise ValueError(message)


def number(value, low, high, label):
    require(type(value) in (int, float) and math.isfinite(value) and low <= value <= high,
            label + ' must be a finite number in ' + str((low, high)))
    return value


def digest_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def identity(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def read(path):
    def pairs(rows):
        result = {}
        for key, value in rows:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    return json.loads(Path(path).read_text('utf-8-sig'), object_pairs_hook=pairs,
                      parse_constant=lambda _: require(False, 'Non-finite JSON value'))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.analysis-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def regular(path):
    path = Path(path).expanduser()
    require(path.is_absolute() and path.is_file() and not path.is_symlink(),
            'Expected an absolute regular input file')
    return path.resolve(strict=True)


def file_record(path):
    path = regular(path)
    before = path.stat()
    digest = digest_file(path)
    after = path.stat()
    require((before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns),
            'Source changed while reading')
    return {'path': str(path), 'size': after.st_size, 'mtime_ns': after.st_mtime_ns, 'sha256': digest}


def verify_source(record, *, full=False):
    path = regular(record['path'])
    info = path.stat()
    require(info.st_size == record['size'] and info.st_mtime_ns == record['mtime_ns'],
            'Source changed; prepare a new analysis job')
    if full:
        require(digest_file(path) == record['sha256'], 'Source content changed')
    return path


def owned_file(root, relative, expected_hash=None):
    root = Path(root).resolve(strict=True)
    path = root / relative
    require(not Path(relative).is_absolute() and not path.is_symlink() and
            path.resolve().is_relative_to(root) and path.is_file(), 'Evidence must be job-owned')
    if expected_hash:
        require(digest_file(path) == expected_hash, 'Evidence bytes changed: ' + str(relative))
    return path


@contextmanager
def lock(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / '.analysis.lock').open('a+b') as stream:
        stream.seek(0, 2)
        if not stream.tell():
            stream.write(b'0'); stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ValueError('Analysis operation is already running') from error
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)
