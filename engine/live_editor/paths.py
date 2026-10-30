"""One configuration and one lock/audit directory for every local Agent client."""
from pathlib import Path
from local_config import workspace_root, draft_locations

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATE_ROOT = workspace_root() / 'live-editor-state'


def runtime_config():
    from windows_runtime import validate_runtime
    runtime = validate_runtime()
    if runtime['app_build'] != '11.4.7.14462':
        raise ValueError('Live editing requires reviewed build 11.4.7.14462; offline export has a separate version scope')
    storage, index, _ = draft_locations()
    return dict(headless_project=str(PROJECT_ROOT), install_dir=runtime['install_dir'],
                draft_roots=list(dict.fromkeys(map(str,(storage,index.parent,workspace_root())))),
                save_timeout_seconds=20)
