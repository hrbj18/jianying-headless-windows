#!/usr/bin/env python3
"""Read-only source/pin checks; not a complete secret or legal audit."""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parent.parent
LOCAL_DIRS = {'.git', 'work', 'outputs', '.local', '__pycache__', '.pytest_cache', '.venv', 'venv'}
LOCAL_CODEC = 'bridge/jy14_codec_hardened_11_4'
SUFFIXES = {'.py', '.cpp', '.h', '.json', '.md', '.yaml', '.txt', '.mjs', '.ps1', '.lua', '.csv', '.ts'}
SPECIAL = {'.gitignore', '.gitattributes', 'NOTICE', 'LICENSE'}
OWN_LIVE_BRIDGE = 'bridge/live-editor/live-qt-pipe-v02.dll'
SKILL_WRAPPERS = (
    'skills/yichen-jianying-edit/scripts/headless_draft.py',
    'skills/yichen-jianying-edit-standalone/scripts/headless_draft.py',
)
REQUIRED_SKILL_PINS = {
    'native_fonts.py', 'runtime_profiles.py', 'jy14_headless.py', 'native_motion.py',
    'native_effects.py', 'native_resources.py', 'native_visual_effects.py',
    'native-resource-catalog.json', 'native_compound.py', 'compound-blueprint.json',
    'native_edit.py', 'native_export.py', 'native_export.cpp', 'native_export_windows.cpp',
    'headless_runtime.py', 'windows_runtime.py', 'blueprint.json',
    'local_config.py', 'draftediting_runtime.py', 'draftediting_worker.mjs',
    'windows_edit_actions.py', 'windows_native_preview.py', 'windows_preview_client.mjs',
    'windows_vfx.py', 'windows-vfx-catalog.json', 'windows_mask_protocol.py',
    'windows-mask-runtime.json', 'windows_vfx_packaging.py',
    'windows_mask_controls.py', 'windows_mask_keyframes.py', 'windows_timeline_patch.py',
    'windows_transition_compat.py', 'windows_transition_adapters/dissolve.lua',
    'windows_transition_adapters/fog.lua',
    'analysis_store.py', 'cloud_asr.py', 'media_evidence.py', 'material_analysis.py', 'analysis_edit.py',
    'editing_style.py',
    'delivery_lifecycle.py', 'media_store.py', 'workspace_cleanup.py', 'story_edit.py',
}
# User-approved public IG case derivatives. Never turn this into a general
# media extension allowance: exact bytes, size and path are release-reviewed.
PUBLIC_MEDIA = {
    'docs/media/hypit-original-frames.png': ('0e7b55e8e1a7a759d6500d29a5d57ec8e93ac89e509504c8e9ed0daadd06d2cf', 947936),
    'docs/media/jianying-import-frames.png': ('64d1a63d6bfaf2c3c2c75de1c58b2beab58ad36499752a6855add08aa43f81dd', 884490),
    'docs/media/hypit-original-preview.mp4': ('0ac79c184ce093a71e73e4ad72f49e44bdf01134154834c983fd52d656095b83', 4421052),
    'docs/media/jianying-import-preview.mp4': ('ccaf385b0683b9e6b155e3c3422c3e3b2d27a8bb82b2f196344f2baa64e586cc', 4223556),
}
PATTERNS = {
    'personal-home-path': re.compile(r'/(?:Users|home)/[A-Za-z0-9_.-]+/'),
    'private-key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'github-token': re.compile(r'\bgh[pousr]_[A-Za-z0-9]{30,}\b'),
    'signed-url': re.compile(r'https?://[^\s<>"\x27]+[?&](?:Signature|X-Amz-Signature|auth_key)=', re.I),
}


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_public_media(path, relative):
    require(relative in PUBLIC_MEDIA, 'Unapproved public media: ' + relative)
    expected_hash, expected_size = PUBLIC_MEDIA[relative]
    require(path.is_file() and not path.is_symlink(), 'Nonregular public media: ' + relative)
    require(path.stat().st_size == expected_size and digest(path) == expected_hash,
            'Public media bytes differ: ' + relative)
    return expected_hash


def literal(path, name):
    for node in ast.parse(path.read_text(encoding='utf-8')).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError('Missing literal: ' + name)


def source_files():
    selected = None
    if (ROOT / '.git').exists():
        result = subprocess.run(
            ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
            cwd=ROOT, check=True, capture_output=True,
        )
        selected = {name.decode('utf-8') for name in result.stdout.split(b'\x00') if name}
    files = []
    for folder, directories, names in os.walk(ROOT, followlinks=False):
        for name in directories:
            require(not (Path(folder) / name).is_symlink(), 'Symlinked directory: ' + name)
        directories[:] = [name for name in directories if name not in LOCAL_DIRS]
        for name in names:
            path = Path(folder) / name
            relative = path.relative_to(ROOT).as_posix()
            if selected is not None and relative not in selected:
                continue
            if relative == LOCAL_CODEC:
                continue
            if relative == 'local-settings.json':
                continue  # Machine-local paths are not distributable project source.
            require(path.is_file() and not path.is_symlink(), 'Nonregular source: ' + relative)
            require(path.suffix in SUFFIXES or name in SPECIAL or relative in PUBLIC_MEDIA or relative == OWN_LIVE_BRIDGE,
                    'Unexpected source type: ' + relative)
            files.append(path)
    return sorted(files)


def main():
    files = source_files()
    included_paths = {path.resolve() for path in files}
    inventory = {}
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        if relative == OWN_LIVE_BRIDGE:
            manifest = json.loads((path.parent / 'manifest.json').read_text(encoding='utf-8'))
            require(digest(path) == manifest['files'][path.name], 'Own live bridge bytes differ')
            inventory[relative] = digest(path)
            continue
        if relative in PUBLIC_MEDIA:
            inventory[relative] = verify_public_media(path, relative)
            continue
        raw = path.read_bytes()
        require(b'\x00' not in raw, 'Binary content in source: ' + relative)
        content = raw.decode('utf-8-sig')
        for label, pattern in PATTERNS.items():
            require(not pattern.search(content), label + ' in ' + relative)
        if path.suffix == '.py':
            ast.parse(content, filename=relative)
        elif path.suffix == '.json':
            json.loads(content)
        elif path.suffix == '.md':
            for target in re.findall(r'\[[^\]]*\]\(([^\s)]+)\)', content):
                if '://' in target or target.startswith('#'):
                    continue
                target = target.split('#', 1)[0]
                target = re.sub(r':\d+(?::\d+)?$', '', target)
                destination = path.parent / target
                require(destination.is_file() and destination.resolve() in included_paths,
                        'Broken or unpackaged relative link in ' + relative + ': ' + target)
        inventory[relative] = hashlib.sha256(raw).hexdigest()

    shared_pins = None
    for relative in SKILL_WRAPPERS:
        wrapper = ROOT / relative
        require(wrapper.is_file() and not wrapper.is_symlink(), 'Missing or nonregular Skill wrapper: ' + relative)
        pins = literal(wrapper, 'PINS')
        require(isinstance(pins, dict) and REQUIRED_SKILL_PINS <= set(pins),
                'Skill pin set omits required components: ' + relative)
        if shared_pins is None:
            shared_pins = pins
        else:
            require(pins == shared_pins, 'Skill wrapper pin sets or hashes differ: ' + relative)
        for name, expected in pins.items():
            path = ROOT / 'engine' / name
            nested_adapter = name in {'windows_transition_adapters/dissolve.lua', 'windows_transition_adapters/fog.lua'}
            nested_adapter = nested_adapter or (Path(name).parent == Path('live_editor') and Path(name).suffix == '.py')
            require((Path(name).name == name or nested_adapter) and isinstance(expected, str) and
                    bool(re.fullmatch(r'[0-9a-f]{64}', expected)),
                    'Invalid Skill pin: ' + relative + ': ' + name)
            require(path.is_file() and not path.is_symlink() and digest(path) == expected,
                    'Skill pin differs: ' + relative + ': ' + name)
    runtime = ROOT / 'engine/headless_runtime.py'
    manifest_path = ROOT / 'bridge/SOURCE_MANIFEST.json'
    require(digest(manifest_path) == literal(runtime, 'IO_MANIFEST_SHA'), 'IO manifest pin differs')
    manifest = json.loads(manifest_path.read_bytes())
    for name, expected in manifest['source_files'].items():
        require(Path(name).name == name and digest(ROOT / 'bridge' / name) == expected, 'Bridge source pin differs: ' + name)
    for name, expected in literal(runtime, 'PINS').items():
        if name == Path(LOCAL_CODEC).name and not (ROOT / LOCAL_CODEC).exists():
            continue
        require(digest(ROOT / 'bridge' / name) == expected, 'Runtime IO/codec pin differs: ' + name)
    require(digest(ROOT / 'engine/native-resource-catalog.json') ==
            literal(ROOT / 'engine/native_resources.py', 'CATALOG_SHA'), 'Resource catalog pin differs')

    if (ROOT / '.git').is_dir():
        tracked = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, check=True, capture_output=True).stdout
        names = {name.decode() for name in tracked.split(b'\x00') if name}
        require(names <= set(inventory), 'Git includes a file outside the checked source inventory')
    fingerprint = hashlib.sha256(json.dumps(inventory, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    print(json.dumps({'status': 'source-checks-passed', 'files': len(files), 'inventory_sha256': fingerprint,
                      'official_binaries_in_source_inventory': False, 'network_called': False,
                      'approved_public_media': len(set(inventory).intersection(PUBLIC_MEDIA)),
                      'skill_wrappers_verified': len(SKILL_WRAPPERS), 'skill_pinned_components': len(shared_pins),
                      'scope': 'syntax, known privacy patterns, relative links, source pins and tracked-file boundary'}))


if __name__ == '__main__':
    main()
