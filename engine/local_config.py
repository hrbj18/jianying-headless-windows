"""Machine-local paths for the normal CLI; no accounts or runtime fingerprints."""
from __future__ import annotations

import json
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PATH_KEYS = ('jianying_install_dir', 'ffmpeg_bin', 'workspace_root', 'draft_root', 'draft_index_path')


def config_path():
    explicit = os.environ.get('JIANYING_CONFIG_FILE')
    path = Path(explicit).expanduser() if explicit else PROJECT_ROOT / 'local-settings.json'
    if not path.is_absolute():
        raise ValueError('JIANYING_CONFIG_FILE must be an absolute path')
    return path


def load_config():
    path = config_path()
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as error:
        raise ValueError('Cannot read local settings: ' + str(path)) from error
    if not isinstance(value, dict):
        raise ValueError('Local settings must be a JSON object')
    for key in PATH_KEYS:
        item = value.get(key)
        if item is not None and (not isinstance(item, str) or not item.strip()
                                 or not Path(item).is_absolute()):
            raise ValueError(key + ' must be an absolute path')
    return value


def configure_environment():
    """Configure only this process; persistent system PATH stays untouched."""
    settings = load_config()
    ffmpeg_bin = settings.get('ffmpeg_bin')
    if ffmpeg_bin:
        directory = Path(ffmpeg_bin)
        if not directory.is_dir():
            raise ValueError('Configured FFmpeg directory does not exist: ' + ffmpeg_bin)
        parts = os.environ.get('PATH', '').split(os.pathsep)
        normalized = os.path.normcase(str(directory))
        parts = [part for part in parts if os.path.normcase(part) != normalized]
        os.environ['PATH'] = os.pathsep.join([str(directory)] + parts)
    os.environ['JIANYING_HEADLESS_ROOT'] = str(PROJECT_ROOT)
    return settings


def workspace_root():
    settings = load_config()
    if settings.get('workspace_root'):
        return Path(settings['workspace_root'])
    base = Path(os.environ.get('LOCALAPPDATA', str(PROJECT_ROOT)))
    return base / 'JianyingHeadless' / 'work'


def draft_locations():
    """The homepage index may stay in AppData while drafts live on another drive."""
    settings = load_config()
    default = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local'))) / 'JianyingPro/User Data/Projects/com.lveditor.draft'
    index = Path(settings.get('draft_index_path', str(default / 'root_meta_info.json')))
    configured = settings.get('draft_root')
    if configured:
        return Path(configured), index, 'configured'
    # Read only the editor-owned index. Mixed roots need an explicit choice.
    parents = set()
    if index.is_file():
        value = json.loads(index.read_text(encoding='utf-8-sig'))
        for entry in value.get('all_draft_store', []):
            raw = entry.get('draft_fold_path')
            if isinstance(raw, str) and Path(raw).is_dir():
                parents.add(Path(raw).resolve().parent)
    if len(parents) == 1:
        return parents.pop(), index, 'editor-index'
    if len(parents) > 1:
        raise ValueError('Multiple draft roots in the editor index; configure draft_root explicitly')
    return default, index, 'default'
