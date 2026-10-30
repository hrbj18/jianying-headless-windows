"""Original built-in HSL, RGB/luma curves and white-balance resource bindings.

Only exact local package bytes and their native material schemas are accepted.
This module does not replace pixels or bake a color transform into the media.
"""
from pathlib import Path
from copy import deepcopy
import json,math
import native_resources as resources
import native_lut_dependencies as lut_dependencies

CATALOG=Path(__file__).with_name('windows-color-resources.json')
BUCKETS=('hsl','color_curves','primary_color_wheels','log_color_wheels','hsl_curves')
WHEEL_COMPONENTS=('red','green','blue','luma','saturation')
WHEEL_GROUPS={'primary':('lift','gamma','gain','offset'),
              'log':('shadow','midtone','highlight','offset')}
LUT_CONFIG=Path('AmazingFilter_lut/config.json')
LUT_CUBE=Path('AmazingFilter_lut/Alexa LogC to Rec709.cube')


def resolve_timeline_paths(timeline,draft_root):
    """Resolve the native draft token on a validation/export copy only."""
    from jy14_headless import native_media_path
    value=deepcopy(timeline)
    for bucket in (*BUCKETS,'effects'):
        for node in value.get('materials',{}).get(bucket,[]):
            if not is_node(bucket,node):continue
            for field in ('path','lumi_hub_path'):
                raw=node.get(field)
                if not raw:continue
                parts=raw.split(';') if field=='path' and node.get('type')=='lut' else [raw]
                mapped=[native_media_path(p,Path(draft_root)).as_posix()
                        if p.startswith('##_draftpath_placeholder_') else p for p in parts]
                node[field]=';'.join(mapped)
    return value


def validate_render_log(text):
    failures=('Cannot load filter scene with ',
              'Loading feature with no config.json or json is error with path ')
    found=[marker for marker in failures if marker.casefold() in text.casefold()]
    if any('addLutEnableStatus' in line and 'parse json error' in line.casefold() for line in text.splitlines()):
        found.append('native LUT merged-parameter JSON parse failure')
    require(not found,'Native visual processing failed despite completed encoding: '+', '.join(found))
    return {'fatal_visual_diagnostics':[]}

def require(value,message):
    if not value:raise ValueError(message)

def is_node(bucket,node):
    return bucket in BUCKETS or (bucket=='effects' and node.get('type') in {
        'temperature','tone','lut','smart_color_adjust','color_match','color_correct'})


def resource_root(node):
    if node.get('type')!='lut':return Path(node['path'])
    parts=node.get('path','').split(';')
    require(len(parts)==2 and all(parts),'LUT requires two explicit local paths')
    lumi=Path(node.get('lumi_hub_path',''))
    require(lumi.name=='lumi_hub_path','LUT requires the reviewed merged Lumi package')
    root=lumi.parent
    lut_dependencies.source_dependencies(node,root,LUT_CUBE,LUT_CONFIG.parent)
    return root

def key_for(bucket,node):
    candidate=experimental_entry(node)
    if candidate is not None:return candidate['key']
    if node.get('type')=='lut':
        resource_root(node)
        return 'color/native-collection-7416258989467374091'
    if node.get('path') and node.get('lumi_hub_path') and Path(node['lumi_hub_path'])==Path(node['path'])/'lumi_hub_path':
        return 'color/native-collection-7416258989467374091'
    # Actual export proves that this build requires the merged resource.
    # Standalone vec3/scalar HSL packages encoded successfully but had no effect.
    return 'color/merge' if bucket=='hsl' or node.get('lumi_hub_path') else 'color/curves' if bucket=='color_curves' else 'color/temperature-tone'


def lut_sources(node):
    if node.get('type')!='lut':return []
    return lut_dependencies.source_dependencies(node,resource_root(node),LUT_CUBE,LUT_CONFIG.parent)


def lut_destination(node,primary,role):
    name=Path(node['path'].split(';')[0]).stem if node.get('type')=='lut' else ''
    key=name[:12] if role=='cube' and len(name)==64 and all(c in '0123456789abcdef' for c in name) else ''
    return lut_dependencies.destination(primary,role,key)


def verify_lut_dependency(role,folder,node=None):
    merge=json.loads(CATALOG.read_text(encoding='utf-8'))['resources']['color/merge']
    cube_name=Path(node['path'].split(';')[0]).name if node else lut_dependencies.CUBE
    return lut_dependencies.verify(role,folder,verify_resource,merge,cube_name)


def snapshot_lut_dependencies(node,destination,resolve=None):
    result=[]
    for role,raw in lut_sources(node):
        source=Path(resolve(raw) if resolve else raw)
        target=lut_destination(node,destination,role)
        files=verify_lut_dependency(role,source,node)
        lut_dependencies.copy_dependency(source,target,files)
        verify_lut_dependency(role,target,node)
        result.append(dict(role=role,source=source,destination=target,files=files))
    return result


def rebase_node(node,destination,dependency_destinations=None):
    original=resource_root(node);lumi=node.get('lumi_hub_path')
    if node.get('type')=='lut':
        overrides=dependency_destinations or {};parts=node['path'].split(';');mapped=[]
        for role,part in zip(('cube','feature'),parts):
            p=Path(part)
            if p.is_relative_to(original):mapped.append((Path(destination)/p.relative_to(original)).as_posix())
            else:
                folder=Path(overrides.get(role,lut_destination(node,destination,role)))
                mapped.append((folder/p.name if role=='cube' else folder).as_posix())
        node['path']=';'.join(mapped)
    else:node['path']=str(destination)
    if lumi:
        require(Path(lumi).is_relative_to(original),'Color Lumi path is outside its reviewed package')
        node['lumi_hub_path']=str(Path(destination)/Path(lumi).relative_to(original))


def rebased_paths(node,destination):
    value=deepcopy(node);rebase_node(value,destination)
    result={node['path']:value['path'],str(resource_root(node)):str(destination)}
    if node.get('lumi_hub_path'):result[node['lumi_hub_path']]=value['lumi_hub_path']
    for role,source in lut_sources(node):
        result[str(source)]=str(lut_destination(node,destination,role))
    return result


def lumi_relative(node):
    if not node.get('lumi_hub_path'):return None
    root=resource_root(node);lumi=Path(node['lumi_hub_path'])
    require(lumi.is_relative_to(root),'Color Lumi path is outside its reviewed package')
    relative=lumi.relative_to(root)
    require(relative in (Path('.'),Path('lumi_hub_path')),'Unreviewed color Lumi subpath')
    return relative

def entry_for_node(bucket,node):
    require(is_node(bucket,node),'Unknown native color material')
    candidate=experimental_entry(node)
    if candidate is not None:return candidate
    entry=json.loads(CATALOG.read_text(encoding='utf-8'))['resources'][key_for(bucket,node)]
    revisions=entry.get('native_builtin_revisions',[])
    root=resource_root(node)
    if revisions and root.is_dir():
        # A normal cold reopen may migrate the same material protocol to the
        # installed DefaultAdjustBundle. Accept only its complete captured
        # tree, including when copied into an ASCII export snapshot. A path
        # name or compatible-looking shader is never sufficient identity.
        actual=resources.tree_manifest(root)
        matches=[revision for revision in revisions if actual==revision['files'] and
                 resources.manifest_hash(actual)==revision['tree_sha256']]
        require(len(matches)<=1,'Ambiguous native built-in color revision')
        if matches:return {**entry,**matches[0]}
    return entry


def experimental_entry(node):
    import native_lut_candidates
    path=resource_root(node) if node.get('type')=='lut' else node.get('path')
    return native_lut_candidates.entry(path,node) if path else None

def verify_resource(path,entry):
    path=Path(path)
    require(path.is_absolute() and path.is_dir() and not path.is_symlink(),'Color package must be a local directory')
    require(resources.tree_manifest(path)==entry['files'],'Color package bytes differ from the original reviewed resource')
    return entry

def finite(v,low,high,name):
    require(type(v) in (int,float) and math.isfinite(v) and low<=v<=high,'Invalid color '+name)

def points(values):
    require(isinstance(values,list) and 2<=len(values)<=32,'Color curve requires 2..32 anchors per channel')
    previous=-1.
    for point in values:
        require(isinstance(point,dict) and {'anchor','left_control','right_control'}<=set(point) and
                set(point)<= {'anchor','left_control','right_control','sync_direction_control'},'Unknown color curve point fields')
        for kind in ['anchor','left_control','right_control']:
            value=point[kind];require(isinstance(value,dict) and set(value)=={'x','y'},'Invalid color curve control')
            for axis in ['x','y']:finite(value[axis],0,1,'curve '+kind+'.'+axis)
        x=point['anchor']['x'];require(x>previous,'Color curve anchors must be strictly increasing');previous=x
        if 'sync_direction_control' in point:require(type(point['sync_direction_control']) is bool,'Invalid curve control linkage')
    require(values[0]['anchor']['x']==0 and values[-1]['anchor']['x']==1,'Color curve must cover the full input domain')

def validate(timeline):
    if any(t.get('type')=='adjust' for t in timeline.get('tracks',[])):
        import native_adjustment_track
        adjustment,projection=native_adjustment_track.project(timeline)
        result=validate(projection)
        result['materials']+=adjustment['materials']
        result['packages']=sorted(set(result['packages']+adjustment['packages']))
        result['adjustment_tracks']=adjustment
        return result
    materials=timeline.get('materials',{});nodes={};packages=[];verified=set()
    common={'id','type','path','lumi_hub_path','resource_id','source_platform','name','version','constant_material_id'}
    for bucket in (*BUCKETS,'effects'):
        for node in materials.get(bucket,[]):
            if not is_node(bucket,node):continue
            identity=node.get('id');require(isinstance(identity,str) and identity and identity not in nodes,'Invalid color material ID')
            if bucket=='hsl':
                require(node.get('type')=='hsl' and set(node)<=common|{'hsl_color_type','hue','saturation','lightness','custom_color','interacting'},'Unknown native HSL fields')
                require(type(node.get('hsl_color_type')) is int and 1<=node['hsl_color_type']<=8,'Unreviewed HSL color channel')
                require(str(node.get('version'))=='1','Unreviewed HSL protocol version')
                require(node.get('lumi_hub_path') and lumi_relative(node) is not None,
                        'HSL Lumi path must bind the exact reviewed merge package')
                require(type(node.get('interacting',False)) is bool,'Invalid HSL interaction state')
                for field in ['hue','saturation','lightness']:
                    require(type(node.get(field,0)) is int,'Native HSL requires integer controls')
                    finite(node.get(field,0),-100,100,'HSL '+field)
            elif bucket=='color_curves':
                require(node.get('type')=='color_curves' and set(node)<=common|{'panel','luma','red','green','blue'},'Unknown native color curve fields')
                for channel in ['luma','red','green','blue']:points(node.get(channel))
            elif bucket in ('primary_color_wheels','log_color_wheels'):
                mode='primary' if bucket=='primary_color_wheels' else 'log'
                groups=WHEEL_GROUPS[mode]
                require(node.get('type')==bucket and
                        set(node)<=common|set(groups)|{'panel','intensity'},'Unknown native color-wheel fields')
                require(node.get('panel','') in ('','adjust_collection'),'Unreviewed color-wheel panel')
                finite(node.get('intensity',1),0,1,'wheel intensity')
                for group in groups:
                    values=node.get(group,{})
                    require(isinstance(values,dict) and set(values)<=set(WHEEL_COMPONENTS),'Unknown color-wheel component')
                    for component in WHEEL_COMPONENTS:finite(values.get(component,0),-1,1,'wheel '+group+'.'+component)
                require(key_for(bucket,node)=='color/native-collection-7416258989467374091',
                        'Color wheels require the reviewed merged collection')
            elif node.get('type')=='lut':
                require(set(node)<=common|{'value','visible','platform','enable_skin_tone_correction',
                    'item_effect_type','effect_id','third_resource_id','adjust_params','face_adjust_params','exclusion_group',
                    'sub_type','color_match_info','multi_language_current','beauty_face_auto_retouch_info'},
                    'Unknown native LUT fields')
                finite(node.get('value',0),0,1,'LUT intensity')
                require(node.get('visible',True) is True and node.get('platform','all')=='all' and
                        node.get('enable_skin_tone_correction',False) is False and node.get('item_effect_type',0)==0 and
                        all(not node.get(field) for field in ('adjust_params','face_adjust_params','exclusion_group','third_resource_id')),
                        'Unreviewed native LUT mode')
                require(not node.get('color_match_info') and not node.get('beauty_face_auto_retouch_info'),
                        'Unreviewed LUT automatic adjustment')
            elif bucket=='hsl_curves' or node.get('type') in {'smart_color_adjust','color_match','color_correct'}:
                require(False,'Inactive preset metadata requires its verified native adjustment track')
            else:
                require(set(node)<=common|{'value','category_id','effect_id','sub_type','multi_language_current','beauty_face_auto_retouch_info','color_match_info'},'Unknown native white-balance fields')
                require(not node.get('color_match_info') and not node.get('beauty_face_auto_retouch_info'),
                        'Unreviewed white-balance automatic adjustment')
                # Native compact saves omit scalar zero; explicit None,
                # booleans and out-of-range values remain invalid.
                finite(node.get('value',0),-1,1,'white balance')
            lumi_relative(node)
            entry=entry_for_node(bucket,node);root=resource_root(node)
            package=('primary',str(root),entry['tree_sha256'])
            if package not in verified:
                verify_resource(root,entry);verified.add(package)
            for role,path in lut_sources(node):
                dependency=(role,str(path),node['path'].split(';')[0] if role=='cube' else '')
                if dependency not in verified:
                    verify_lut_dependency(role,path,node);verified.add(dependency)
            nodes[identity]=(bucket,node);packages.append(entry['key'])
    used=set()
    for track in timeline.get('tracks',[]):
        for segment in track.get('segments',[]):
            require(segment.get('material_id') not in nodes,'Color adjustments must be extra material references')
            refs=segment.get('extra_material_refs') or [];bound=[ref for ref in refs if ref in nodes]
            if not bound:continue
            require(track.get('type')=='video' and len(bound)==len(set(bound)),'Color requires distinct per-video bindings')
            for identity in bound:
                bucket,node=nodes[identity]
                # The native GUI omits these true constructor defaults.
                if bucket=='hsl':require(segment.get('enable_hsl',True) is True,'HSL binding is disabled')
                if bucket=='color_curves':require(segment.get('enable_color_curves',True) is True,'Color curve binding is disabled')
                if bucket in ('primary_color_wheels','log_color_wheels'):
                    require(segment.get('enable_color_wheels',True) is True,'Color wheels are disabled')
                if node.get('type')=='lut':require(segment.get('enable_lut',True) is True,'LUT is disabled')
                require(not any(g.get('material_id')==identity for g in segment.get('common_keyframes',[])),
                        'Color material keyframes require separate acceptance')
            used.update(bound)
    require(used==set(nodes),'Orphan color adjustment')
    return {'materials':len(nodes),'packages':sorted(set(packages)),
            'scope':'native HSL, luma/RGB curves, white balance and primary/log wheel schemas; actual pixel and GUI acceptance remain per-feature'}
