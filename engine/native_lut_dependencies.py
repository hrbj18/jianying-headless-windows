"""Exact native importer-generated diagnostic CUBE package dependencies.

The CUBE remains data consumed by Jianying, never a baked replacement video.
This pinned fixture is not a general arbitrary-CUBE compatibility claim.
"""
from pathlib import Path
import hashlib,shutil,os,re
import native_cube

CUBE='Alexa LogC to Rec709.cube'
FILES={
 CUBE:dict(size=564272,sha256='de533d358202c2dddbb7f32c6321d9cd2fcb98a46b9f09429539fcf434ac456c'),
 'algorithmConfig.json':dict(size=1020,sha256='f7c1da92217add03de0c7703e06ae6ee6a5cdbc77749ef3f8c8fff36eab80f0d'),
 'config.json':dict(size=379,sha256='eab533914cd7f1ee085e4f08b13615e3c6d10a3b33552762ef96c624758d3fd9')}


def require(ok,message):
    if not ok:raise ValueError(message)


def verify_cube_package(folder,cube_name=CUBE):
    folder=Path(folder)
    require(folder.is_absolute() and folder.is_dir() and not folder.is_symlink(),'LUT package must be an existing local directory')
    files={k:v for k,v in FILES.items() if k!=CUBE}
    if cube_name==CUBE:files[CUBE]=FILES[CUBE]
    else:
        require(re.fullmatch(r'[0-9a-f]{64}\.cube',cube_name) is not None,'Custom Cube must use its content-addressed filename')
        parsed=native_cube.read(folder/cube_name)
        require(parsed.sha256==Path(cube_name).stem and parsed.source_sha256==parsed.sha256,
                'Custom Cube bytes differ from the canonical content identity')
        files[cube_name]=dict(size=len(parsed.canonical),sha256=parsed.sha256)
    for name,info in files.items():
        path=folder/name
        require(path.is_file() and not path.is_symlink() and path.stat().st_size==info['size'] and
                hashlib.sha256(path.read_bytes()).hexdigest()==info['sha256'],
                'Native LUT cube/config bytes differ from the observed importer package')
    # Native importer adds a cover JPEG. It is not shader/config input and is
    # neither required nor copied into renderer snapshots.
    require(not set(p.name for p in folder.iterdir())-set(files)-{'draft_cover.jpg'},'Unknown native LUT package content')
    return files


def source_dependencies(node,primary_root,legacy_cube,legacy_feature):
    if node.get('type')!='lut':return []
    parts=node['path'].split(';');require(len(parts)==2,'LUT requires cube and feature paths')
    cube,feature=map(Path,parts);root=Path(primary_root);result=[]
    require(cube.is_absolute() and feature.is_absolute(),'LUT dependency paths must be absolute')
    if cube.is_relative_to(root):
        require(cube==root/legacy_cube,'Unreviewed embedded LUT cube identity')
    else:
        require(cube.name==CUBE or re.fullmatch(r'[0-9a-f]{64}\.cube',cube.name),
                'Unreviewed external LUT cube')
        result.append(('cube',cube.parent))
    if feature.is_relative_to(root):
        require(feature in (root,root/legacy_feature),'Unknown embedded LUT feature root')
    else:result.append(('feature',feature))
    return result


def destination(primary,role,cube_key=''):
    require(role in ('cube','feature'),'Unknown LUT dependency role')
    primary=Path(primary)
    # The full SHA remains in the manifest; a short directory avoids Windows
    # MAX_PATH failures for the default merge shader's nested filenames.
    require(not cube_key or re.fullmatch(r'[0-9a-f]{12}',cube_key),'Invalid Cube dependency identity')
    return primary.parent/(primary.name[:16]+'-lut-'+role+('-'+cube_key if role=='cube' and cube_key else ''))


def verify(role,folder,color_verify,merge_entry,cube_name=CUBE):
    if role=='cube':return verify_cube_package(folder,cube_name)
    require(role=='feature','Unknown LUT dependency role')
    color_verify(folder,merge_entry)
    return merge_entry['files']


def copy_dependency(source,target,files):
    source,target=Path(source),Path(target)
    require(source.resolve()!=target.resolve() or target.is_dir(),'Missing native LUT dependency')
    target.mkdir(parents=True,exist_ok=True)
    for name,info in files.items():
        src=source/name;dst=target/name
        require(src.is_file() and not src.is_symlink() and
                hashlib.sha256(src.read_bytes()).hexdigest()==info['sha256'],'LUT source changed before copying')
        if not dst.exists():
            dst.parent.mkdir(parents=True,exist_ok=True)
            # Match the existing exporter byte-copy route. Win32 CopyFile2
            # rejects some long nested shader paths despite successful open.
            with src.open('rb') as reader,dst.open('xb') as writer:
                shutil.copyfileobj(reader,writer)
                writer.flush();os.fsync(writer.fileno())
        require(dst.is_file() and not dst.is_symlink() and dst.stat().st_size==info['size'] and
                hashlib.sha256(dst.read_bytes()).hexdigest()==info['sha256'],'LUT snapshot bytes differ from source')


def prepare_package(data,cube_name,templates,destination):
    """Copy original installed runtime JSON and plain Cube data into ownership."""
    templates,destination=Path(templates),Path(destination)
    require(not destination.exists(),'Native LUT package creation never overwrites existing data')
    for name,info in FILES.items():
        if name==CUBE:continue
        path=templates/name
        require(path.is_file() and not path.is_symlink() and
                hashlib.sha256(path.read_bytes()).hexdigest()==info['sha256'],'Installed LUT template bytes changed')
    destination.mkdir(parents=True)
    for name in ('config.json','algorithmConfig.json'):shutil.copyfile(templates/name,destination/name)
    (destination/cube_name).write_bytes(data)
    return verify_cube_package(destination,cube_name)
