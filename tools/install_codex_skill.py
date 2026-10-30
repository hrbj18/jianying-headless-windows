#!/usr/bin/env python3
"""Install this checkout's Windows skill with a local project binding."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]


def install(destination, rebind=False, skill_name='jianying-windows', profile=None):
    if skill_name not in {'jianying-windows', 'yuezai-editing-style'}:
        raise ValueError('Unknown project skill')
    source = ROOT / 'skills' / skill_name
    if not (source / 'SKILL.md').is_file():
        raise ValueError('Project skill source is unavailable: ' + skill_name)
    destination = Path(destination).expanduser()
    if destination.is_symlink():
        raise ValueError('Skill destination must be a real directory')
    destination = destination.resolve()
    binding = destination / 'references/local.json'
    frozen_profile = None
    if skill_name == 'yuezai-editing-style':
        candidate = Path(profile) if profile else destination / 'references/profile.json'
        sys.path.insert(0, str(ROOT / 'engine'))
        from editing_style import inspect
        frozen_profile = inspect(candidate)
    elif profile is not None:
        raise ValueError('A style profile is only valid for yuezai-editing-style')
    if destination.exists():
        if not binding.is_file():
            raise ValueError('Existing skill is not managed by this checkout: ' + str(destination))
        prior = json.loads(binding.read_text(encoding='utf-8-sig')).get('project_root')
        if not isinstance(prior, str) or not prior or not Path(prior).is_absolute():
            raise ValueError('Existing skill has no valid project binding: ' + str(destination))
        if Path(prior).resolve() != ROOT and not rebind:
            raise ValueError('Existing skill belongs to another checkout: ' + str(destination)
                             + '; use --rebind only when intentionally moving its project binding')
    shutil.copytree(source, destination, dirs_exist_ok=True)
    local = {'project_root': str(ROOT)}
    if frozen_profile:
        target = destination / 'references/profile.json'
        target.write_text(json.dumps(frozen_profile, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        local.update(style_profile=str(target), profile_id=frozen_profile['id'])
    binding.write_text(json.dumps(local, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return {'status': 'skill-installed', 'name': skill_name, 'skill': str(destination), 'project_root': str(ROOT)}


def main():
    home = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex')))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name', choices=['jianying-windows', 'yuezai-editing-style'], default='jianying-windows')
    parser.add_argument('--destination', type=Path)
    parser.add_argument('--profile', type=Path, help='Frozen style profile for installing the YueZai style skill')
    parser.add_argument('--rebind', action='store_true',
                        help='Explicitly replace a managed skill binding after moving the project')
    args = parser.parse_args()
    try:
        destination = args.destination or home / 'skills' / args.name
        print(json.dumps(install(destination, rebind=args.rebind, skill_name=args.name, profile=args.profile), ensure_ascii=False, indent=2))
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
