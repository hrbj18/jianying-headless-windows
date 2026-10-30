"""Rebuild explicit, byte-pinned local GeneralEffect compatibility resources.

This is an auditable package adapter, not a repair of the application's original
GeneralEffect routing. The exact official fragment shaders, fog masks and fog
effect curve run in the official engine through an AmazingFeature scene. No
application binary or original resource is modified. Resource admission remains
the responsibility of the exact-version Windows VFX catalog.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

from windows_vfx import manifest_hash, tree_manifest


WHITE_TREE = 'ea01778c35c6b0f7483ed31c6e588bb3948cc7749c4dd694a56dfb6267960396'
ORIGINAL_TREES = {
    'dissolve': '22a8d69e69c9850450a66a65da77d2d6f09412a9208f6bd6369af111df4dcca9',
    'fog': '50316ba093d43e353c0de0852779b469d1e01a49c7a69d4bb6dc5dc6720b75fa',
    'slide-left': 'd15207e0cfa472f07b4545713ef398a00bbdb6e3990c3ffa605329abc173b49c',
    'slide-right': 'b50a1f86c7367ddef8151607d1a8f71a47ab5214bb1bbf69be59de32d2936c1e',
}
ORIGINAL_IDS = {'dissolve': '6724845717472416269', 'fog': '7216171159589491259',
                'slide-left': '6726711499676455435', 'slide-right': '6726711296063967748'}
SIMPLE_SHADERS = {
    'dissolve': 'GESticker_Blend/generalEffect/resource1/shader/VerticalGlitch0.frag',
    'slide-left': 'GESticker_RightMove/generalEffect/resource1/shader/VerticalGlitch0.frag',
    'slide-right': 'GESticker_LeftMove/generalEffect/resource1/shader/VerticalGlitch0.frag',
}
ADAPTER_HASHES = {
    'dissolve': '158dea25e7e9c995bf6410e717e9aca2e6529c8f80281a800fbb057f161aff48',
    'fog': '04268a4e177b7ad16ba5f789ae4f5dbbcc1e60eb9dcfc7f16b0f1e0b04360966',
}
OUTPUT_TREES = {
    'dissolve': '4f598973aca0927bdaef47a05b3b67f198cd3931a3e57675435a7dec2d528cad',
    'fog': 'bf566be7726758682d7d3145d897586e9cf6c53e861199f15550bac6db510444',
    'slide-left': 'f57983f0f9fb6cb50755e0148fcf8cdcbc4fe17dfa24b65cb12fb0cea8356d5f',
    'slide-right': '8d212e26825b5de82ec68a01b07fa90b0b2ddaeec371b6fdf726b06d77d57530',
}
FOG_PASSES = [
    ('mixPass', 'xshader/mixImg'),
    ('NoisePass', 'effects/Grain/xshader/noise'),
    ('passMask', 'xshader/passMask'),
    ('PassHighlight', 'effects/Glow/xshader/passHighlight'),
    ('PassHorzBlur1', 'effects/Glow/xshader/passHorzBlur'),
    ('PassVertBlur1', 'effects/Glow/xshader/passVertBlur'),
    ('PassOutput', 'effects/Glow/xshader/passOutput'),
    ('passBlend', 'xshader/passBlend'),
]
# Only vertex-attribute names need adaptation between the two resource formats.
# The complete original vertex sources remain in original-ge/ for audit.
VERTEX_ADAPTERS = {
    'dissolve': ('precision highp float; attribute vec3 position; attribute vec2 texcoord0; '
                 'varying highp vec2 texCoord; void main(){gl_Position=vec4(position,1.0);'
                 'texCoord=texcoord0;}'),
    'fog': ('precision highp float; attribute vec3 position; attribute vec2 texcoord0; '
            'varying vec2 v_uv; void main(){gl_Position=vec4(position,1.0);v_uv=texcoord0;}'),
}


def _require(value, message):
    if not value:
        raise ValueError(message)


def build(kind, white_template, original_resource, out):
    """Build into a new absolute ASCII directory and return the complete manifest."""
    _require(kind in ORIGINAL_IDS, 'Unknown compatibility kind')
    white, original, out = map(Path, (white_template, original_resource, out))
    _require(out.is_absolute() and str(out).isascii() and '..' not in out.parts and
             not out.exists() and out.parent.is_dir() and out.parent.resolve() == out.parent,
             'Compatibility output must be a fresh canonical absolute ASCII directory')
    template_files, original_files = tree_manifest(white), tree_manifest(original)
    _require(manifest_hash(template_files) == WHITE_TREE and
             manifest_hash(original_files) == ORIGINAL_TREES[kind],
             'Original resource or scene template fingerprint differs')
    _require(not out.is_relative_to(white) and not out.is_relative_to(original),
             'Compatibility output must be outside both original packages')
    adapter_kind = 'fog' if kind == 'fog' else 'dissolve'
    adapter = Path(__file__).with_name('windows_transition_adapters') / (adapter_kind + '.lua')
    adapter_bytes = adapter.read_bytes()
    _require(hashlib.sha256(adapter_bytes).hexdigest() == ADAPTER_HASHES[adapter_kind],
             'Compatibility adapter fingerprint changed; review the Lua source')

    shutil.copytree(white, out)
    shutil.copytree(original, out / 'original-ge')
    scene = out / 'AmazingFeature'
    shaders = []

    def copy_shader(source, destination):
        shutil.copyfile(source, destination)
        _require(source.read_bytes() == destination.read_bytes(), 'Shader copy differs')
        shaders.append({'source': source.relative_to(original).as_posix(),
                        'runtime': destination.relative_to(out).as_posix(),
                        'sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                        'byte_equal': True})

    prefix_hash = None
    if kind in SIMPLE_SHADERS:
        copy_shader(original / SIMPLE_SHADERS[kind],
                    scene / 'xshader/passBlend3.frag')
    else:
        general = original / 'transition/generalEffect'
        shutil.copytree(general / 'res', scene / 'fogres')
        for _, stem in FOG_PASSES:
            copy_shader(general / 'gs3.frag', scene / (stem + '.frag'))
            (scene / (stem + '.vert')).write_bytes(VERTEX_ADAPTERS[kind].encode())
        copy_shader(general / 'blend.frag', scene / 'xshader/passBlend3.frag')
        full_event = (original / 'event.lua').read_bytes()
        divider = b'---------- TransitionEntry.lua ----------'
        _require(full_event.count(divider) == 1, 'Original fog event boundary changed')
        prefix = full_event.split(divider)[0]
        prefix_hash = hashlib.sha256(prefix).hexdigest()
        adapter_bytes = prefix + adapter_bytes

    (scene / 'xshader/passBlend3.vert').write_bytes(VERTEX_ADAPTERS[adapter_kind].encode())
    (scene / 'lua/SeekModeScript.lua').write_bytes(adapter_bytes)
    config = json.loads((out / 'config.json').read_text(encoding='utf-8'))
    revision = '_v3' if kind == 'fog' else '_v2' if kind == 'dissolve' else '_v1'
    config['name'] = 'Codex_Local_GE_Compat_' + ORIGINAL_IDS[kind] + revision
    (out / 'config.json').write_bytes((json.dumps(config, indent=2) + '\n').encode())
    _require(tree_manifest(original) == original_files and tree_manifest(white) == template_files,
             'An original resource changed during compatibility construction')

    provenance = {
        'schema': 'jy-windows-transition-compat-provenance/v1',
        'compatibility_adapter': True, 'official_general_effect_route_repaired': False,
        'kind': kind, 'original_resource_id': ORIGINAL_IDS[kind],
        'template_tree_sha256': WHITE_TREE, 'original_tree_sha256': ORIGINAL_TREES[kind],
        'original_files': original_files, 'shader_bindings': shaders,
        'adapter_sha256': ADAPTER_HASHES[adapter_kind], 'original_event_prefix_sha256': prefix_hash,
        'original_sources_unchanged': True,
        'file_manifest_excluding_provenance': tree_manifest(out),
    }
    (out / 'COMPATIBILITY-PROVENANCE.json').write_bytes(
        (json.dumps(provenance, ensure_ascii=False, indent=2) + '\n').encode())
    complete = tree_manifest(out)
    _require(manifest_hash(complete) == OUTPUT_TREES[kind],
             'Rebuilt compatibility bytes differ from the reviewed native-rendered package')
    return {'key': 'transition/' + kind + '-compat', 'path': str(out), 'files': complete,
            'tree_sha256': manifest_hash(complete), 'compatibility_adapter': True,
            'original_resource_id': ORIGINAL_IDS[kind], 'provenance': provenance}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind', choices=ORIGINAL_IDS, required=True)
    parser.add_argument('--white-template', required=True)
    parser.add_argument('--original-resource', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--manifest-out', required=True)
    args = parser.parse_args(argv)
    manifest = Path(args.manifest_out)
    _require(manifest.is_absolute() and not manifest.exists() and manifest.parent.is_dir() and
             manifest.parent.resolve() == manifest.parent,
             'Manifest output must be a new file in a canonical absolute directory')
    _require(all(not manifest.is_relative_to(Path(folder)) for folder in
                 (args.white_template, args.original_resource, args.out)),
             'Manifest output must be outside the original and compatibility packages')
    result = build(args.kind, args.white_template, args.original_resource, args.out)
    with manifest.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({key: result[key] for key in
                     ('key', 'path', 'tree_sha256', 'compatibility_adapter', 'original_resource_id')}))
    return result


if __name__ == '__main__':
    main()
