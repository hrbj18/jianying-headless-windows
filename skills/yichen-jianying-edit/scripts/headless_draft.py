#!/usr/bin/env python3
"""Pinned Skill entrypoint for a separately checked-out Jianying Headless project."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys

def project_root():
    configured = os.environ.get('JIANYING_HEADLESS_ROOT')
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            raise SystemExit('JIANYING_HEADLESS_ROOT must be an absolute checkout path')
        candidates = [path.resolve()]
    else:
        candidates = list(Path(__file__).resolve().parents)
    for path in candidates:
        marker = path / 'project.json'
        if marker.is_file() and not marker.is_symlink():
            try:
                identity = json.loads(marker.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            if identity.get('id') == 'jianying-headless' and identity.get('schema') == 'jianying-headless-project/v1':
                return path
    raise SystemExit('Jianying Headless checkout unavailable. Clone the project with authorized GitHub access, '
                     'then set JIANYING_HEADLESS_ROOT to its absolute path. The Skill alone does not include the engine.')


PROJECT_ROOT = project_root()
BACKEND = PROJECT_ROOT / 'engine'
PINS = {
    'native_fonts.py': 'ddd7b4c1ecd55890bd645c14930f2c5f6687794691c2280daa32673e048da5e6',
    'runtime_profiles.py': 'db37d0286cbc137da2b73bf1b115774612efd653bec8de49c4fddda247c9ea8a',
    'jy14_headless.py': '44838b75f9f3dd55a8122b3d360964c38abf5f1a4e4c5177e9a423352722f66b',
    'native_motion.py': 'b8f9b174fff8bd1670ac568a59e6ee383db03eb4156301f1c3b73b64f165083c',
    'native_effects.py': 'c46b2fc9221dd613f220564b752e532f8f3753dd5595aaffc24f41d5236e4e97',
    'native_resources.py': '13d7f9648ee4694c02b403a370a2fe1338a46ec47045e628d5ed9dedb09e78ca',
    'native_visual_effects.py': '15df7e56cc7d575a552c180e72ec712f136c618d271b2f3ad2d32dd5929e844c',
    'native-resource-catalog.json': '97af2df27463a9183fb1aa8f2ef534b37a644cb196f340fe88fdc50b456abde9',
    'native_compound.py': 'eb9e7d5544e1726be291912c47a5cc917b80180a231242ca30b7b5aaf68f5bfc',
    'compound-blueprint.json': '9cba9435053280abf9072d5eaccb8586c841b11dac6854b32daf9cbdba76af8e',
    'native_edit.py': 'ac6f51a4d5934af64d966d8e9c361236f7baa145141d2b6431987313248a945d',
    'native_export.py': 'df8cd8a13433d27bf87ddb46ef14d8b5c3b10814f9eeb8e7bf87ef46740ec112',
    'native_export.cpp': 'c60da6c65f5bb7ac733b8f5b619401be3921f9254b953a55903d4e7566156379',
    'native_export_windows.cpp': '85efc1dbe363115fd70c6ccd7319ee627f14c7d189c1d4c2e46b2baaffb24fed',
    'headless_runtime.py': '93b749bde68c7dd7210b40dbe73b6071dfe3bf23e93f5dab6a51c067ce31fe43',
    'windows_runtime.py': 'ecedc4b91163c5f78ea556232be56021ec2da72a0a2cd378fe89a64840d3ee73',
    'blueprint.json': '91f7eddad5bff9af23eb88b53713c180e3e3d4054edd469140cfa9aa56bc1dc9',
    'local_config.py': '0248f511ad8bb02110938f441b156f34992bef267cf9fd0e8446d3550da8479f',
    'draftediting_runtime.py': '2afa12b075fdfd6ae40a1159a18c2b81112de449f3d2ae3534f000d3cec6eddb',
    'draftediting_worker.mjs': 'dcd32b49a7c3f14036b6f3e2b6526ded2e2273933fd55f0005fb8522a5d2287f',
    'windows_edit_actions.py': '19888352483a65a31cb6ea2d68e31e8327d0066f958cea515e6ab6ffac97dfe5',
    'windows_native_preview.py': '9e12c9ca829ecca4e30ab1e371438187c8d1ebc0df1e2625522d8ee2a373a98e',
    'windows_preview_client.mjs': '7850438a7bd6619468a62c66cfdbbd8f7a37e2a1410a4350033ad430ddc03e1f',
    'windows_vfx.py': 'b974ba55eff46c21eb633c4c2f73eafd0eb402d604806263b0852b1c6a27a5eb',
    'windows-vfx-catalog.json': 'f41e0e6677578b75444c4c4ed5bbf59df3034085a0f69086c5c7cfab46174d79',
    'windows_mask_protocol.py': '0269b2346d21e435c98ffda517560aec570751479322666aac9259db6acc86c7',
    'windows-mask-runtime.json': '62054d5e3b818cfe89519526d4d72ac94a39afc487d688578e88a3747dd71343',
    'windows_vfx_packaging.py': '9a16360e4604cae0b058e4e2fcee3308ad7426f7ec67cc5724dcc955a448f4c1',
    'windows_mask_controls.py': '20c6f9e50f9e03ebd10644ac1e75270eb665bf4a484c50ca4ec6c783052e233a',
    'windows_mask_keyframes.py': '730f2b189cedca104edf609c2102166fe55cbd7f08424e93907cf27b7da89c28',
    'windows_timeline_patch.py': '842e4153d39da6f23a403e9307f0a51d942783e95e00cf724d09b5779596390e',
    'windows_transition_compat.py': '403cff4476c271be6d583b044e20afc4dc16fa9e6ca3a46240431a8940e3ab3b',
    'windows_transition_adapters/dissolve.lua': '158dea25e7e9c995bf6410e717e9aca2e6529c8f80281a800fbb057f161aff48',
    'windows_transition_adapters/fog.lua': '04268a4e177b7ad16ba5f789ae4f5dbbcc1e60eb9dcfc7f16b0f1e0b04360966',
    'analysis_store.py': '8e6647da53b05545b291e4b54123f720a29324566ec656e5fbc6c15da897c688',
    'cloud_asr.py': '31f4df2c27e776adfb5aa7f4e397a5004dfb3baf358121c2c5fc61767207100a',
    'media_evidence.py': 'd35f3db29c6d4f77d6ce000d57c81be2a183f96beedc3355e4f9deda6bb6d0df',
    'material_analysis.py': '15c7e7a61b36bb081561f33cf9afe3a04b426fa6011cd87e1ec51760fd8edc61',
    'analysis_edit.py': 'ccc42fbf879feb76cfc89c869741dcb18857befe7c87bd312ba3bba8b3e14a3d',
    'editing_style.py': '134bdc8684bbe06c8d05b30093ef88babe5648879c2fda0823b6a0d4da95c310',
    'delivery_lifecycle.py': '2f45650b7cb5838918c91c943c2c42394939b82269b8b853cec88b3b877d529f',
    'media_store.py': 'd6b355184e940004f2bf081b3cd8b2ec238290547ab91f7e67cd52e4196de97b',
    'workspace_cleanup.py': 'c8fcecb1bb3d069bf68b077714ef79e2a1dc03ac5a13b9c69d67f3a6ed31317b',
    'story_edit.py': '8ebddefe7c3ffda75be98ea43685dc40faa079f67419e0cc4df76455722ed61f',
    'agent_drafts.py': '32bd1cc7d2183b1bca44df58773cf643ea285b7aaae68547cd957f48775a46fb',
    'agent_entry.py': 'fada03cf8afd6610e9347f00ff2b4bb3d726520feecf2d7d2ed3182446e93946',
    'agent_environment.py': '933c06fa254d2ed932f77ac64c91e6a8b345914c7a8a5515fbe21c30c2d9d074',
    'agent_segments.py': '74ff332395bb74e0a4ff7c07be092aef430fcbf044be85094021b5b8d8247bc8',
    'live_editor/__init__.py': 'd89ebaceff7ea8bf638a036cc469150149d07818b779285a28d68c92123b6c7c',
    'live_editor/client.py': 'db4074fe3b05566dbd8c55c9ec4e0188796702e119fde42700a558ad96eb8170',
    'live_editor/drafts.py': '5d8f7d304383fcaebd82da45b2a79659ed640f04a6a404dacd26c8899d2204b6',
    'live_editor/errors.py': '81846f8e68bc47856d4a8c5149513d22e570aceef6667974682cfb713fefae0e',
    'live_editor/native_client.py': 'eadb9ff0e7f5f95a4807e7e3350127653f7492403815ce407aea5a37aeb35025',
    'live_editor/operations.py': '0291ffeb98d3777efd230a146e0a199fdd056a3dcb5a728451d135f4089fe3c5',
    'live_editor/paths.py': '1dcebdb7f7662fc2d14826823197b6b778aea45b9cc8f508b3c7230433bd7401',
    'live_editor/pipe_transport.py': '44817d99a596b8c4308aa77bd857074cb087cec1abe8c7eebe93c82d1776c60b',
    'live_editor/profile.py': '3ad5f33a1e8938a4965a40551071c0a1f182c6829ddce39773c74319befdae50',
    'live_editor/typed_args.py': '279e92a2826165e8bd84de78ba65920c0a9e90a8dfdf6d7b9f792781e94d68ca',
    'live_editor/v02.py': 'cd2a514732c76ad56a0eff2dc3ecaad5c7a8031a68b13090c422a51d783613b4',
    'live_editor/window_state.py': 'f526c25f73d9f530a30d90ecaf6e700c7950ecb705d576d045a2a11152e5bb1f',
    'live_editor/windows.py': 'd5fba8d87d8d83892f386587f66933787018bee33fe48aa96e61e92ab4d07c84',
    'live_editor/winprocess.py': '447262791ab0970a3447c3089960c13fd1fa4ad06f5117b06726d748586b7b17',
}

for name, expected in PINS.items():
    path = BACKEND / name
    if not path.is_file() or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise SystemExit('Headless component changed or unavailable; reverify before updating the pin: ' + name)

sys.path[:0] = [str(BACKEND), str(PROJECT_ROOT / 'tools')]
from local_config import configure_environment

configure_environment()
entrypoint = 'jy14_headless.py'
if len(sys.argv) > 1 and sys.argv[1] == 'agent':
    entrypoint = 'agent_entry.py'
    del sys.argv[1]
elif len(sys.argv) > 1 and sys.argv[1] == 'edit':
    entrypoint = 'native_edit.py'
    del sys.argv[1]
elif len(sys.argv) > 1 and sys.argv[1] in ('export', 'export-draft'):
    if sys.argv[1] == 'export-draft' and '--build' in sys.argv[2:]:
        raise SystemExit('export-draft accepts --draft-dir; use export for --build')
    entrypoint = 'native_export.py'
    del sys.argv[1]
elif len(sys.argv) > 1 and sys.argv[1] in ('edit-actions', 'preview'):
    entrypoint = {'edit-actions': 'windows_edit_actions.py', 'preview': 'windows_native_preview.py'}[sys.argv[1]]
    del sys.argv[1]
elif len(sys.argv) > 1 and sys.argv[1] == 'vfx':
    del sys.argv[1]
    if len(sys.argv) > 1 and sys.argv[1] == 'build-compat':
        entrypoint = 'windows_transition_compat.py'
        del sys.argv[1]
    elif len(sys.argv) > 1 and sys.argv[1] == 'freeze-draft':
        entrypoint = 'windows_vfx_packaging.py'
        del sys.argv[1]
    else:
        entrypoint = 'windows_vfx.py'
elif len(sys.argv) > 1 and sys.argv[1] == 'lyra':
    entrypoint = 'draftediting_runtime.py'
    del sys.argv[1]
    if len(sys.argv) > 1 and sys.argv[1] in {'init', 'create', 'project-create', 'resource-import', 'sync', 'apply', 'run'}:
        if '--help' not in sys.argv[2:] and '-h' not in sys.argv[2:] and '--start-editor' not in sys.argv[2:]:
            sys.argv.insert(2, '--start-editor')
runpy.run_path(str(BACKEND / entrypoint), run_name='__main__')
