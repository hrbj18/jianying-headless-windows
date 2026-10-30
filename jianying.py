#!/usr/bin/env python3
"""Normal Windows entrypoint for the installed local Jianying toolchain."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]


def print_json(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def invoke(module, arguments):
    sys.argv = [str(ROOT / 'engine' / (module + '.py'))] + list(arguments)
    runpy.run_module(module, run_name='__main__')
    return 0


def doctor():
    import windows_runtime
    import draftediting_runtime
    from windows_native_toolchain import _toolchain
    from local_config import config_path, workspace_root
    runtime = windows_runtime.validate_runtime()
    editing = draftediting_runtime.doctor()
    if not editing['official_worker_files_present']:
        raise ValueError('The installed editor is missing official Lyra/Bun/VMSDK worker files')
    vcvars, clang = _toolchain()
    return {**runtime, 'status': 'ready', 'python': sys.executable,
            'local_config': str(config_path()), 'workspace_root': str(workspace_root()),
            'ffmpeg': shutil.which('ffmpeg'), 'ffprobe': shutil.which('ffprobe'),
            'official_editing_runtime': editing,
            'native_compiler': {'vcvars64': str(vcvars), 'clang_cl': str(clang)},
            'editing_entry': 'lyra', 'export_entry': 'export-draft'}


def new_workspace(arguments):
    from local_config import workspace_root
    parser = argparse.ArgumentParser(prog='jianying workspace', description='Create an isolated editing job')
    parser.add_argument('--name', default='session')
    parser.add_argument('--root', type=Path, default=workspace_root())
    args = parser.parse_args(arguments)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', args.name):
        raise ValueError('--name must contain ASCII letters, digits, underscore or hyphen')
    parent = args.root.resolve()
    if not str(parent).isascii():
        raise ValueError('The official Lyra workspace needs an ASCII path; configure workspace_root')
    job = parent / (args.name + '-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6])
    job.mkdir(parents=True, exist_ok=False)
    draft_root = job / 'drafts'
    draft_root.mkdir()
    print_json({'status': 'workspace-created', 'job': str(job),
                'draft_root': str(draft_root), 'blueprint': str(job / 'blueprint'),
                'suggested_ref': 'local://' + job.name})
    return 0


def main(arguments=None):
    argv = list(sys.argv[1:] if arguments is None else arguments)
    from local_config import configure_environment
    configure_environment()
    if not argv or argv[0] in ('-h', '--help', 'help'):
        parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog='''Commands:
  doctor           Verify the reviewed editor, signature, media tools and compiler
  agent            Shared Codex/WorkBuddy preflight, staging and native live editing
  process          Record editing decisions, real actions, previews and cooperative pauses
  workspace        Create an isolated ASCII editing job
  lyra             Official workspace/create/import/sync/apply commands; see lyra --help
  edit-actions     Audited native edits: keyframes, speed, audio fades and reviewed VFX
  analyze          Cloud ASR, contact sheets, reviewed source intervals and native assembly
  style            Distill evidence-bound editing styles and reuse them on reviewed source cuts
  story            Compile reviewed story decisions into a clean original-audio rough cut
  delivery         Inspect, archive, restore and update fixed delivery slots
  media-store      Inspect and deduplicate managed immutable media
  cache            Prepare and remove explicitly authorized regenerable caches
  preview          Read actual frames from the native draft player, without desktop capture
  vfx              List byte-verified Windows filter/effect/transition/mask presets
  build            Build an editable draft from a local JSON plan
  verify-build     Verify the immutable build
  export           Export a verified build with Jianying's own engine
  export-draft     Export a saved disk draft after official Lyra edits
  publish          Register a built draft on the editor homepage
  verify           Verify a published draft
  config           Show machine-local paths

Examples:
  .\\jianying.ps1 doctor
  .\\jianying.ps1 workspace --name sample
  .\\jianying.ps1 lyra --help
  .\\jianying.ps1 export-draft --draft-dir C:\\...\\drafts\\sample --out C:\\...\\work\\render
''')
        parser.print_help()
        return 0
    command, rest = argv[0], argv[1:]
    if command == 'process':
        from editing_process import main as process_main
        return process_main(rest)
    if command == 'agent':
        from agent_entry import main as agent_main
        return agent_main(rest)
    if command == 'doctor':
        if rest:
            raise ValueError('doctor takes no arguments')
        print_json(doctor())
        return 0
    if command == 'config':
        from local_config import config_path, load_config
        print_json({'path': str(config_path()), 'settings': load_config()})
        return 0
    if command == 'workspace':
        return new_workspace(rest)
    if command == 'edit-actions':
        return invoke('windows_edit_actions', rest)
    if command == 'analyze':
        return invoke('material_analysis', rest)
    if command == 'style':
        return invoke('editing_style', rest)
    if command == 'story':
        return invoke('story_edit', rest)
    if command == 'delivery':
        return invoke('delivery_lifecycle', rest)
    if command == 'media-store':
        return invoke('media_store', rest)
    if command == 'cache':
        return invoke('workspace_cleanup', rest)
    if command == 'preview':
        return invoke('windows_native_preview', rest)
    if command == 'vfx':
        if rest and rest[0] == 'freeze-draft':
            return invoke('windows_vfx_packaging', rest[1:])
        if rest and rest[0] == 'build-compat':
            return invoke('windows_transition_compat', rest[1:])
        return invoke('windows_vfx', rest)
    if command == 'lyra':
        if rest and rest[0] in {'init', 'create', 'project-create', 'resource-import', 'sync', 'apply', 'run'}:
            if '--help' not in rest and '-h' not in rest and '--start-editor' not in rest:
                rest.insert(1, '--start-editor')
        return invoke('draftediting_runtime', rest)
    if command in {'build', 'verify-build', 'publish', 'resume-publish', 'verify', 'from-compiled'}:
        return invoke('jy14_headless', [command] + rest)
    if command == 'export':
        return invoke('native_export', rest)
    if command == 'export-draft':
        if '--build' in rest:
            raise ValueError('export-draft accepts --draft-dir; use export for --build')
        return invoke('native_export', rest)
    raise ValueError('Unknown command: ' + command + '; run --help')


if __name__ == '__main__':
    # Also make `python jianying.py ...` select the installed isolated runtime.
    python = ROOT / '.venv/Scripts/python.exe'
    if os.name == 'nt' and python.is_file() and Path(sys.prefix).resolve() != (ROOT / '.venv').resolve():
        raise SystemExit(subprocess.call([str(python), '-X', 'utf8', '-B', str(Path(__file__).resolve()), *sys.argv[1:]]))
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as error:
        print('Jianying command failed: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
