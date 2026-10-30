"""Audited main-timeline writes using the reviewed official EncryptUtils.

Callers construct a narrow, validated change. This helper preserves ciphertext,
checks every source file before replacement, and verifies the saved main. It is
one file replacement, not a transaction or an exclusion lock against the GUI.
"""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import uuid

from runtime_profiles import WINDOWS_1147_PROFILE


def commit(source, audit_prefix, runtime, label, mutate):
    import native_export as native
    require = native.j.require
    require(runtime.get('runtime_profile') == WINDOWS_1147_PROFILE and
            runtime.get('app_build') == '11.4.7.14462',
            'Saved-timeline compatibility requires exact Windows 11.4.7.14462')
    require(label in {'mask-controls', 'mask-keyframes', 'transition-scene'},
            'Unknown saved-timeline compatibility operation')
    source, before, timeline, evidence = native.read_draft(source, runtime)
    prefix = Path(audit_prefix)
    require(prefix.is_absolute() and prefix.parent.is_dir() and
            not prefix.resolve().is_relative_to(source), 'Timeline audit must be outside the source draft')
    def audit_file(suffix):
        return prefix.parent / (prefix.name + '.' + label + '.' + suffix)
    report_path = audit_file('json')
    require(not report_path.exists(), 'Saved-timeline compatibility audit already exists')
    main = source / evidence['source_timeline']
    require(main.is_file() and not main.is_symlink() and main.resolve().is_relative_to(source),
            'Declared main timeline must be a regular draft-owned file')
    relative = str(main.relative_to(source))
    report = {'schema': 'jy-windows-timeline-patch/v1', 'status': 'preparing',
              'operation': label, 'source': str(source), 'main_timeline': str(main),
              'before_sha256': before[relative]['sha256'], 'only_declared_main_written': True,
              'native_encryption': 'official EncryptUtils', 'atomic_batch': False}
    try:
        updated = deepcopy(timeline)
        report['patch'] = mutate(updated, source)
        if updated == timeline:
            require(native.j.files_manifest(source) == before, 'Draft changed during compatibility readback')
            report.update(status='already-compatible', after_sha256=report['before_sha256'],
                          source_other_files_unchanged=True)
            return report
        previous = audit_file('before.enc')
        with main.open('rb') as src, previous.open('xb') as dst:
            shutil.copyfileobj(src, dst)
        require(native.j.nd.digest(previous) == before[relative]['sha256'],
                'Main timeline changed during compatibility snapshot')
        report['recovery_path'] = str(previous)
        encrypted = audit_file('after.enc')
        helper = native.j.nd.helper()
        helper._encrypt_metadata_from_memory(native.j.nd.packed(updated), encrypted)
        require(helper._decrypt_metadata_in_memory(encrypted) == updated,
                'Official encryption failed saved-timeline readback')
        pending = main.with_name('.jy-' + label + '-' + uuid.uuid4().hex + '.tmp')
        report['temporary_path'] = str(pending)
        with encrypted.open('rb') as src, pending.open('xb') as dst:
            shutil.copyfileobj(src, dst)
        require(native.j.nd.digest(pending) == native.j.nd.digest(encrypted),
                'Saved-timeline ciphertext copy changed')
        current = native.j.files_manifest(source)
        current.pop(str(pending.relative_to(source)), None)
        require(current == before, 'Draft changed concurrently; refusing compatibility replacement')
        os.replace(pending, main)
        _, after_files, after, selected = native.read_draft(source, runtime)
        require(selected['source_timeline'] == evidence['source_timeline'] and after == updated,
                'Saved main timeline differs from the validated compatibility change')
        expected = dict(before)
        expected[relative] = {'sha256': native.j.nd.digest(encrypted), 'size': encrypted.stat().st_size}
        require(after_files == expected, 'Files outside the declared main timeline changed')
        report.update(status='patched-and-read-back', after_sha256=expected[relative]['sha256'],
                      source_other_files_unchanged=True)
        return report
    except Exception as error:
        report.update(status='failed-or-unverified', error=str(error),
                      recovery='Inspect retained ciphertext and source; no automatic rollback was attempted.')
        raise
    finally:
        with report_path.open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
