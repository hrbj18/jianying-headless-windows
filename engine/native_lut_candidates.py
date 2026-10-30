"""Explicit, pinned experimental LUT fixtures, separate from supported bundles.

No renderer fallback or general resource trust: only the exact candidate bytes
in this audit catalog can enter an isolated native verification job.
"""
from pathlib import Path
import hashlib
import json
import os

CATALOG = Path(__file__).with_name('windows-lut-candidates-v17.json')
CATALOG_SHA = 'f5f2862d6e2b4bfa917b69a6b4e8732d7adfb18d04765a80df3b93ca19db150d'
MARKER = 'native-standard-lut33.json'


def catalog():
    if hashlib.sha256(CATALOG.read_bytes()).hexdigest() != CATALOG_SHA:
        raise ValueError('Experimental LUT catalog changed without review')
    return json.loads(CATALOG.read_bytes())


def by_key(key):
    value = catalog()['resources'].get(key)
    if value is None:
        raise ValueError('Unknown experimental LUT resource key')
    return value


def variant_key(variant):
    matches = [e['key'] for e in catalog()['resources'].values()
               if e.get('fixture_variant') == variant]
    if len(matches) != 1:
        raise ValueError('Unknown experimental LUT fixture variant')
    return matches[0]


def is_filter(lut):
    variant = lut.get('resource_candidate')
    return bool(variant and by_key(variant_key(variant)).get('bucket') == 'effects')


def gui_root(resource):
    if resource.get('bucket') != 'effects':
        raise ValueError('Only standard LUT compatibility filters use a managed GUI resource')
    # Native draft_load_helper allows Home resources and rejects shader paths
    # under the draft store. Keep authored resources separate from official IDs.
    return (Path(os.environ['LOCALAPPDATA']) / 'JianyingPro/User Data/AgentResources' /
            'standard-lut33' / resource['tree_sha256'])


def prepare_gui_resource(source, resource):
    import native_lut_dependencies
    import native_resources
    target=gui_root(resource)
    native_lut_dependencies.copy_dependency(source,target,resource['files'])
    if native_resources.tree_manifest(target) != resource['files']:
        raise ValueError('Managed native LUT resource differs from its pinned bundle')
    return target


def external_build_source(path, folder):
    """Resolve only an exact managed resource to its complete build-owned copy."""
    import native_resources
    for resource in catalog()['resources'].values():
        if resource.get('bucket')!='effects' or Path(path)!=gui_root(resource):continue
        if native_resources.tree_manifest(path)!=resource['files']:
            raise ValueError('Managed standard LUT resource changed')
        relative=Path('Resources/native-av')/('lq-'+resource['tree_sha256'][:12])
        source=Path(folder)/relative
        if native_resources.tree_manifest(source)!=resource['files']:
            raise ValueError('Build-owned standard LUT resource changed')
        return source,relative
    return None


def filter_entry(bucket, node):
    if bucket != 'effects' or node.get('type') != 'filter' or not node.get('path'):
        return None
    root = Path(node['path'])
    resource = entry(root, node)
    if resource is None or resource.get('bucket') != 'effects':
        return None
    import native_cube
    cube = native_cube.read(root / 'source.cube')
    if cube.sha256 != resource['marker']['canonical_cube_sha256']:
        raise ValueError('Standard LUT filter does not bind its original Cube')
    return resource


def entry(root, node):
    root = Path(root)
    marker = root / MARKER
    # The saved-draft stager first builds virtual draft-owned paths, then
    # resolves their actual files under its verified source snapshot. Its
    # full-SHA directory can select an entry, never attest the file bytes.
    if not marker.exists() and root.is_dir():
        return None
    candidates = catalog()
    if not marker.exists():
        matches = [e for e in candidates['resources'].values()
                   if e['tree_sha256'] == root.name]
        return matches[0] if len(matches) == 1 else None
    if marker.is_symlink() or not marker.is_file():
        raise ValueError('Experimental LUT marker must be an owned regular file')
    identity = json.loads(marker.read_bytes())
    resource = candidates['resources'].get(identity.get('key'))
    if resource is None or identity != resource['marker']:
        raise ValueError('Unknown experimental LUT resource identity')
    if node.get('type') == 'lut':
        cube, feature = map(Path, node['path'].split(';'))
        if feature != root:
            raise ValueError('Experimental LUT migrated away from its sampler')
        import native_cube
        parsed = native_cube.read(cube)
        if parsed.sha256 != identity['canonical_cube_sha256']:
            raise ValueError('Experimental LUT atlas does not bind this exact Cube')
    return resource
