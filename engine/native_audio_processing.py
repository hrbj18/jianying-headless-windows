"""Reviewed local SAMI denoise material and immutable model dependency."""
import math,hashlib,json
from pathlib import Path
import native_resources as resources

MODEL_SHA256='a20cbd66d4ae8d483fe0f1759fa76803f4355d96aece3b65902b6cf34ff14c1c'
MODEL_SIZE=264172
CATALOG=Path(__file__).with_name('windows-audio-resources.json')

def validate_render_log(text):
    failures=('load mdsp preset failed','cannot create graph from string, error:',
              'invalid json file, Unable to insert node:')
    found=[marker for marker in failures if marker.casefold() in text.casefold()]
    require(not found,'Native audio processing failed despite completed encoding: '+', '.join(found))
    return {'fatal_dsp_diagnostics':[]}


def is_effect(bucket,node):return bucket=='audio_effects'

def entry_for_node(bucket,node):
    require(is_effect(bucket,node),'Not an audio-effect material')
    entries=json.loads(CATALOG.read_text(encoding='utf-8'))['resources'].values()
    matches=[entry for entry in entries if node.get('resource_id')==entry['resource_id']]
    require(len(matches)==1,'Unreviewed native audio-effect resource identity')
    return matches[0]

def verify_resource(path,entry):
    path=Path(path)
    require(path.is_absolute() and path.is_dir() and not path.is_symlink(),'Native audio effect requires a local package directory')
    require(resources.tree_manifest(path)==entry['files'],'Native audio-effect package bytes changed')
    return entry

def validate_effects(timeline):
    materials=timeline.get('materials',{});nodes={}
    for node in materials.get('audio_effects',[]):
        require(isinstance(node,dict) and set(node)<= {'id','type','audio_adjust_params','category_id','category_name',
                'constant_material_id','is_ugc','is_vc_clone_tone','name','path','production_path','resource_id',
                'source_platform','speaker_id','sub_type','third_resource_id','time_range','vc_type'},'Unknown native audio-effect fields')
        entry=entry_for_node('audio_effects',node)
        require(node.get('type')=='audio_effect' and type(node.get('source_platform',0)) is int and
                node.get('source_platform',0)==entry['source_platform'] and type(node.get('sub_type',0)) is int and node.get('sub_type',0)==entry.get('sub_type',1) and
                node.get('vc_type','none')=='none' and node.get('is_ugc',False) is False and
                node.get('is_vc_clone_tone',False) is False and not node.get('production_path') and
                not node.get('speaker_id') and not node.get('third_resource_id'),'Unreviewed native audio-effect mode')
        time_range=node.get('time_range',{})
        require(isinstance(time_range,dict) and set(time_range)<= {'start','duration'} and
                all(type(time_range.get(k,0)) is int and time_range.get(k,0)==0 for k in ('start','duration')),
                'Partial audio-effect ranges require separate acceptance')
        params=node.get('audio_adjust_params',[])
        controls={(c['parameterIndex'],c['portIndex']):c for c in entry['controls']};seen=set()
        require(isinstance(params,list) and len(params)==len(controls),'Unreviewed native audio-effect parameters')
        for param in params:
            require(isinstance(param,dict) and set(param)<={'value','default_value','max_value','min_value','name',
                    'parameterIndex','portIndex'},'Unknown native audio-effect parameter fields')
            require(type(param.get('parameterIndex',0)) is int and type(param.get('portIndex',0)) is int,
                    'Native audio-effect indices must be integers')
            key=(param.get('parameterIndex',0),param.get('portIndex',0));control=controls.get(key)
            require(control is not None and key not in seen,'Unreviewed or duplicate native audio-effect control')
            seen.add(key)
            require(param.get('name')==control['name'] and all(type(param.get(k,control[k])) in (int,float) and
                    param.get(k,control[k])==control[k] for k in ('default_value','min_value','max_value')),
                    'Unreviewed native audio-effect parameter identity')
            require(type(param.get('value',0)) in (int,float) and math.isfinite(param.get('value',0)) and
                    0<=param.get('value',0)<=1,'Native audio-effect strength must be in 0..1')
        identity=node.get('id');require(isinstance(identity,str) and identity and identity not in nodes,'Duplicate audio-effect identity')
        verify_resource(node['path'],entry);nodes[identity]=node
    audio={node.get('id'):node for node in materials.get('audios',[])};used=set()
    for track in timeline.get('tracks',[]):
        for segment in track.get('segments',[]):
            require(segment.get('material_id') not in nodes,'Audio effect cannot be a primary material')
            bound=[ref for ref in segment.get('extra_material_refs',[]) if ref in nodes]
            if not bound:continue
            require(1<=len(bound)<=2 and track.get('type')=='audio' and segment.get('material_id') in audio,
                    'Audio effect requires independent audio bindings')
            require(len({nodes[ref].get('sub_type',0) for ref in bound})==len(bound),
                    'Repeated native audio-effect category')
            constants=[nodes[ref].get('constant_material_id') for ref in bound
                       if nodes[ref].get('constant_material_id')]
            require(all(isinstance(value,str) and '\0' not in value for value in constants) and
                    len(set(constants))==len(constants),'Repeated native audio-effect parameter identity')
            primary=audio[segment['material_id']]
            require(type(primary.get('check_flag')) is int and primary['check_flag']&3==3,
                    'Audio effect requires native BasicFlag and VoiceChangeFlag on its primary audio material')
            require(not segment.get('reverse') and segment.get('speed',1)==1,'Audio-effect time mapping requires separate acceptance')
            used.update(bound)
    require(used==set(nodes),'Orphan native audio effect')
    return len(nodes)

def require(value,message):
    if not value:raise ValueError(message)

def model_identity(raw):
    require(isinstance(raw,str) and raw and '://' not in raw,'Denoise requires a local model path')
    path=Path(raw)
    require(path.is_absolute() and path.is_file() and not path.is_symlink() and path.stat().st_size==MODEL_SIZE,
            'Denoise model is absent, unsafe or has an unreviewed size')
    with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    require(digest==MODEL_SHA256,'Denoise model bytes differ from the reviewed installation')
    return {'path':str(path),'sha256':digest,'size':MODEL_SIZE}

def validate(timeline):
    materials=timeline.get('materials',{});nodes={};models=[]
    for node in materials.get('realtime_denoises',[]):
        require(isinstance(node,dict) and set(node)<= {'id','type','is_denoise','denoise_mode','denoise_rate',
                'path','sami_name','sami_version','sami_type','is_from_hd_sounds'},'Unknown denoise fields')
        require(node.get('type')=='realtime_denoise' and node.get('sami_name','denoise_v2')=='denoise_v2' and
                node.get('sami_version','1.0')=='1.0' and type(node.get('sami_type')) is int and node['sami_type']==2 and
                type(node.get('denoise_mode',1)) in (int,float) and node.get('denoise_mode',1) in (0,1),
                'Unreviewed native denoise algorithm or mode')
        rate=node.get('denoise_rate')
        require(type(rate) in (int,float) and math.isfinite(rate) and 0<=rate<=1,'Invalid denoise rate')
        # The current native checkbox save omits its false enable value.
        require(type(node.get('is_denoise',False)) is bool and node.get('is_from_hd_sounds',False) is False,
                'Denoise enable must be boolean; HD/cloud sound mode is not reviewed')
        identity=node.get('id');require(isinstance(identity,str) and identity and identity not in nodes,
                                      'Denoise material IDs must be unique')
        models.append(model_identity(node.get('path')));nodes[identity]=node
    audio={node.get('id') for node in materials.get('audios',[])};used=set()
    for track in timeline.get('tracks',[]):
        for segment in track.get('segments',[]):
            require(segment.get('material_id') not in nodes,'Denoise cannot be a primary material')
            refs=segment.get('extra_material_refs') or [];bound=[ref for ref in refs if ref in nodes]
            if not bound:continue
            require(len(bound)==1 and track.get('type')=='audio' and segment.get('material_id') in audio,
                    'Denoise requires exactly one audio-segment binding')
            require(not segment.get('reverse') and segment.get('speed',1)==1,
                    'Denoise reverse or speed mapping requires separate acceptance')
            used.add(bound[0])
    require(used==set(nodes),'Orphan denoise material')
    return {'denoise_materials':len(nodes),'enabled':sum(n.get('is_denoise',False) for n in nodes.values()),
            'audio_effects':validate_effects(timeline),'models':models,
            'scope':'local SAMI denoise_v2; reviewed radio resource and authored studio DSP graph; 1x independent audio'}
