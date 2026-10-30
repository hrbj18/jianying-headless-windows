"""Native grade and audio processing in the existing editable plan format."""
from copy import deepcopy
from pathlib import Path
import json,shutil,uuid,os,hashlib
import native_cube
import native_lut_candidates as lut_candidates
import native_lut_dependencies as lut_deps
import native_color as color
import native_audio_processing as audio
import native_dsp_graph as dsp
import native_resources as resources
from runtime_profiles import WINDOWS_1147_PROFILE

COLORS=('red','orange','yellow','green','cyan','blue','purple','magenta')
ARGB=('#FFE64444','#FFE69444','#FFF2F224','#FF45E644',
      '#FF45E6E6','#FF4595E6','#FF9545E6','#FFE644E6')
CHANNELS=('luma','red','green','blue')
RELATIVE={'color/merge':'Resources/native-av/grade',
          'color/native-collection-7416258989467374091':'Resources/native-av/grade-v2',
          'audio/local-studio':'Resources/native-av/studio',
          'audio/local-eq':'Resources/native-av/eq',
          'audio/local-dynamics':'Resources/native-av/dynamics',
          'audio/denoise':'Resources/native-av/denoise/denoise.model'}


def require(value,message):
    if not value:raise ValueError(message)


def validate_spec(spec,kind):
    if 'grade' in spec:
        require(kind=='video','Native grade requires video')
        grade=spec['grade'];require(isinstance(grade,dict) and grade and
            set(grade)<= {'version','temperature','tint','hsl','curves','wheels','lut'},'Unknown or empty native grade')
        require(type(grade.get('version',1)) is int and grade.get('version',1) in (1,2),'Unknown native grade version')
        for key in ('temperature','tint'):
            if key in grade:color.finite(grade[key],-1,1,key)
        if 'hsl' in grade:
            hsl=grade['hsl'];require(isinstance(hsl,dict) and hsl and set(hsl)<=set(COLORS),'Unknown HSL channel')
            for values in hsl.values():
                require(isinstance(values,dict) and values and set(values)<= {'hue','saturation','lightness','interacting'},'Unknown HSL control')
                for key,value in values.items():
                    if key=='interacting':require(type(value) is bool,'Native HSL interaction flag must be boolean')
                    else:require(type(value) is int and -100<=value<=100,'HSL controls must be integers in -100..100')
        if 'curves' in grade:
            curves=grade['curves'];require(isinstance(curves,dict) and curves and set(curves)<=set(CHANNELS),'Unknown color curve channel')
            for points in curves.values():color.points(points)
        if 'wheels' in grade:
            wheels=grade['wheels'];mode=wheels.get('mode') if isinstance(wheels,dict) else None
            require(grade.get('version')==2 and mode in color.WHEEL_GROUPS,
                    'Color wheels require grade version 2 and explicit primary/log mode')
            groups=color.WHEEL_GROUPS[mode]
            require(set(wheels)<={'mode','intensity'}|set(groups),'Unknown color-wheel group')
            color.finite(wheels.get('intensity',1),0,1,'wheel intensity')
            for group in groups:
                values=wheels.get(group,{})
                require(isinstance(values,dict) and set(values)<=set(color.WHEEL_COMPONENTS),'Unknown color-wheel component')
                for value in values.values():color.finite(value,-1,1,'wheel component')
        if 'lut' in grade:
            lut=grade['lut']
            require(grade.get('version')==2 and isinstance(lut,dict) and
                    set(lut)<={'preset','file','value','sha256','source_sha256','title','native_package_version','resource_candidate','native_filter_name'} and
                    (('file' in lut) != ('preset' in lut)),'LUT requires grade2 and exactly one file or preset')
            require(type(lut.get('native_package_version',1)) is int and lut.get('native_package_version',1) in (1,2),
                    'Unknown native LUT package version')
            if 'preset' in lut:require(lut['preset']=='alexa-logc33','Unknown native LUT preset')
            else:
                require(isinstance(lut['file'],str) and Path(lut['file']).is_absolute(),'Custom LUT requires an absolute source file')
                for key in ('sha256','source_sha256'):
                    if key in lut:require(isinstance(lut[key],str) and len(lut[key])==64 and
                        all(c in '0123456789abcdef' for c in lut[key]),'Invalid custom LUT content identity')
            if 'title' in lut:require(isinstance(lut['title'],str) and 0<len(lut['title'])<=128 and '\0' not in lut['title'],'Invalid LUT title')
            if 'resource_candidate' in lut:
                require('file' in lut and isinstance(lut['resource_candidate'],str),
                        'Experimental LUT candidate requires an explicit custom Cube')
                lut_candidates.variant_key(lut['resource_candidate'])
            if 'native_filter_name' in lut:
                require(lut_candidates.is_filter(lut), 'Native filter name requires a compatibility filter candidate')
                entry=lut_candidates.by_key(lut_candidates.variant_key(lut['resource_candidate']))
                require(lut['native_filter_name']==entry.get('display_name') and
                        isinstance(lut['native_filter_name'],str) and bool(lut['native_filter_name']),
                        'Unreviewed native compatibility filter name')
            color.finite(lut.get('value',1),0,1,'LUT intensity')
    if 'audio_processing' in spec:
        require(kind=='audio' and spec.get('speed',1)==1,'Native audio processing requires independent 1x audio')
        value=spec['audio_processing'];require(isinstance(value,dict) and value and set(value)<= {'studio','studio_chain','denoise'},'Unknown audio processing')
        require(not ('studio' in value and 'studio_chain' in value),'Choose one native studio layout')
        if 'studio' in value:
            require(isinstance(value['studio'],dict),'Studio settings must be an object')
            dsp.parameters(value['studio'])
        if 'studio_chain' in value:
            require(isinstance(value['studio_chain'],dict),'Studio chain settings must be an object')
            dsp.parameters(value['studio_chain'])
        if 'denoise' in value:
            noise=value['denoise'];require(isinstance(noise,dict) and set(noise)<= {'enabled','rate'},'Unknown denoise control')
            require(type(noise.get('enabled',True)) is bool,'Denoise enable must be boolean')
            color.finite(noise.get('rate',.85),0,1,'denoise rate')


def grade_resource_key(grade):
    candidate=grade.get('lut',{}).get('resource_candidate')
    if candidate and not lut_candidates.is_filter(grade['lut']):return lut_candidates.variant_key(candidate)
    return 'color/native-collection-7416258989467374091' if grade.get('version',1)==2 else 'color/merge'


def relative_for(key):
    if key.startswith(('color/experimental-standard-lut33-','filter/experimental-standard-lut33-')):
        return 'Resources/native-av/lq-'+lut_candidates.by_key(key)['tree_sha256'][:12]
    return RELATIVE[key]


def needed(plan):
    keys=set()
    for track in plan['tracks']:
        for spec in track['segments']:
            if 'grade' in spec:
                keys.add(grade_resource_key(spec['grade']))
                if lut_candidates.is_filter(spec['grade'].get('lut',{})):
                    keys.add(lut_candidates.variant_key(spec['grade']['lut']['resource_candidate']))
                elif spec['grade'].get('lut',{}).get('native_package_version',1)==2:
                    keys.add(lut_key(spec['grade']['lut']))
            value=spec.get('audio_processing',{})
            if 'studio' in value:keys.add('audio/local-studio')
            if 'studio_chain' in value:keys.update(('audio/local-eq','audio/local-dynamics'))
            if 'denoise' in value:keys.add('audio/denoise')
    return sorted(keys)


def bind_lut_sources(plan):
    """Bind only the in-memory plan; never rewrite the user's Cube or plan."""
    for track in plan['tracks']:
        for spec in track['segments']:
            lut=spec.get('grade',{}).get('lut',{})
            if lut:lut.setdefault('native_package_version',2)
            if lut and lut['native_package_version']==2 and not lut_candidates.is_filter(lut):
                # The normal LUT action initializes this red HSL mode. Keep
                # it explicit in new builds so later strength edits change
                # only the LUT; never override a caller's deliberate mode.
                red=spec['grade'].setdefault('hsl',{}).setdefault('red',{'saturation':0})
                red.setdefault('interacting',True)
            if 'file' not in lut:continue
            require(lut['native_package_version']==2,'Custom Cube requires native package version2')
            parsed=native_cube.read(lut['file'])
            if lut.get('resource_candidate'):
                entry=lut_candidates.by_key(lut_candidates.variant_key(lut['resource_candidate']))
                require(parsed.sha256==entry['marker']['canonical_cube_sha256'],
                        'Experimental LUT fixture does not match the requested Cube')
            for field,actual in [('source_sha256',parsed.source_sha256),('sha256',parsed.sha256)]:
                require(field not in lut or lut[field]==actual,'Custom LUT source differs from its bound hash')
                lut[field]=actual
            lut['file']=str(Path(lut['file']).resolve())
            lut.setdefault('title',parsed.title or Path(lut['file']).stem[:128])
    return plan


def lut_key(lut):
    if 'preset' in lut:return 'lut/preset-alexa-logc33'
    require('sha256' in lut,'Custom Cube must be bound before resource preparation')
    if lut.get('resource_candidate'):
        lut_candidates.variant_key(lut['resource_candidate'])
        return 'lut/candidate/'+lut['resource_candidate']+'/'+lut['sha256']
    return 'lut/cube/'+lut['sha256']


def custom_lut_key(key):
    return key.startswith(('lut/cube/','lut/candidate/'))


def lut_relative(key):
    require(key=='lut/preset-alexa-logc33' or custom_lut_key(key),'Unknown LUT resource key')
    suffix=key.rsplit('/',1)[-1][:12] if custom_lut_key(key) else ''
    main=RELATIVE['color/native-collection-7416258989467374091']
    if key.startswith('lut/candidate/'):
        main=relative_for(lut_candidates.variant_key(key.split('/')[2]))
    return lut_deps.destination(Path(main),'cube',suffix).as_posix()


def lut_filename(key):
    return key.rsplit('/',1)[-1]+'.cube' if custom_lut_key(key) else lut_deps.CUBE


def _custom_lut(plan,key):
    found=[s['grade']['lut'] for t in plan['tracks'] for s in t['segments']
           if 'lut' in s.get('grade',{}) and lut_key(s['grade']['lut'])==key]
    require(found,'Custom LUT source is not bound to the plan')
    return found[0]


def _lut_source_record(plan,key):
    lut=_custom_lut(plan,key)
    return dict(path=lut['file'],source_sha256=lut['source_sha256'],canonical_sha256=lut['sha256'],
                normalization='size-and-RGB-rows only; no mathematical resampling')


def _entry(key,folder=None):
    if key.startswith(('color/experimental-standard-lut33-','filter/experimental-standard-lut33-')):return lut_candidates.by_key(key)
    if key.startswith('lut/'):
        require(folder is not None,'LUT resource verification requires its owned package')
        return {'files':lut_deps.verify_cube_package(Path(folder)/lut_relative(key),lut_filename(key))}
    if key.startswith('color/'):return json.loads(color.CATALOG.read_text(encoding='utf-8'))['resources'][key]
    if key.startswith('audio/local-'):
        return json.loads(audio.CATALOG.read_text(encoding='utf-8'))['resources'][key]
    return {'files':{Path(RELATIVE[key]).name:{'sha256':audio.MODEL_SHA256,'size':audio.MODEL_SIZE}}}


LUT_PROJECT_INDEX=Path('materials/Lut/LutDraft.json')


def lut_project_records(plan,target):
    """Native project-local index, not the user's global LUT configuration.

    The pinned ImportCenter reader/writer uses this exact array of four text
    fields. It verifies the cube exists when normally opening the project.
    Package bytes are independently checked by the resource manifest.
    """
    wanted=any('lut' in spec.get('grade',{}) for track in plan['tracks'] for spec in track['segments'])
    if not wanted:return []
    require(target is not None and Path(target).is_absolute(),'LUT index requires the explicit project target')
    result={}
    for track in plan['tracks']:
        for spec in track['segments']:
            lut=spec.get('grade',{}).get('lut')
            if not lut:continue
            if lut_candidates.is_filter(lut):continue
            if lut.get('native_package_version',1)==1:
                cube=str(Path(target)/RELATIVE['color/native-collection-7416258989467374091']/color.LUT_CUBE)
                result[cube]=dict(title=color.LUT_CUBE.stem,path=cube,originPath=cube,imagePath=str(Path(target)/'draft_cover.jpg'))
                continue
            key=lut_key(lut);cube=(Path(target)/lut_relative(key)/lut_filename(key)).as_posix()
            title=lut.get('title') or (Path(lut['file']).stem if 'file' in lut else color.LUT_CUBE.stem)
            result[cube]=dict(title=title,path=cube,originPath=cube,imagePath=(Path(target)/'draft_cover.jpg').as_posix())
    return list(result.values())


def verify_lut_project_index(plan,folder,target):
    expected=lut_project_records(plan,target)
    if not expected:return
    index=Path(folder)/LUT_PROJECT_INDEX
    legacy=all(s.get('grade',{}).get('lut',{}).get('native_package_version',1)==1
               for t in plan['tracks'] for s in t['segments'])
    if legacy and not index.exists():return
    require(index.is_file() and not index.is_symlink(),'Native project LUT index is missing')
    require(json.loads(index.read_text(encoding='utf-8'))==expected,'Native project LUT index differs from the plan')


def prepare(plan,folder,runtime,project_target=None):
    keys=needed(plan)
    require(not keys or runtime.get('runtime_profile')==WINDOWS_1147_PROFILE,
            'Native grade/audio processing requires the reviewed Windows 11.4.7 runtime')
    records=[];install=Path(runtime.get('install_dir',''))
    for key in keys:
        relative=lut_relative(key) if key.startswith('lut/') else relative_for(key)
        destination=Path(folder)/relative
        if key.startswith('lut/'):
            if custom_lut_key(key):
                lut=_custom_lut(plan,key);parsed=native_cube.read(lut['file'])
                require(parsed.sha256==lut['sha256'] and parsed.source_sha256==lut['source_sha256'],
                        'Custom Cube changed during build')
                data=parsed.canonical
            else:
                original=Path(folder)/RELATIVE['color/native-collection-7416258989467374091']/color.LUT_CUBE
                data=original.read_bytes()
            lut_deps.prepare_package(data,lut_filename(key),install/'Resources/lut',destination)
            entry=_entry(key,folder)
            if custom_lut_key(key):
                require(hashlib.sha256(Path(lut['file']).read_bytes()).hexdigest()==lut['source_sha256'],
                        'Custom Cube original changed while creating its canonical copy')
        else:entry=_entry(key)
        if key.startswith('lut/'):pass
        elif key.startswith(('color/experimental-standard-lut33-','filter/experimental-standard-lut33-')):
            source=Path(entry['fixture_root'])
            color.verify_resource(source,entry);shutil.copytree(source,destination)
            color.verify_resource(destination,entry)
            if entry.get('bucket')=='effects':lut_candidates.prepare_gui_resource(destination,entry)
        elif key.startswith('color/'):
            source=(install/entry['installed_relative'] if 'installed_relative' in entry else
                    Path(os.environ['LOCALAPPDATA'])/entry['cache_relative'])
            color.verify_resource(source,entry);shutil.copytree(source,destination)
            color.verify_resource(destination,entry)
        elif key=='audio/local-studio':
            dsp.write_bundle(destination);audio.verify_resource(destination,entry)
        elif key in ('audio/local-eq','audio/local-dynamics'):
            dsp.write_split_bundle(destination,key.removeprefix('audio/local-'));audio.verify_resource(destination,entry)
        else:
            original=install/'Resources/audiosami/unet_denoise_44k_music_model_v1.0.model'
            audio.model_identity(str(original));destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(original,destination);audio.model_identity(str(destination))
        row=dict(key=key,relative=relative,files=entry['files'])
        if custom_lut_key(key):row['source']=_lut_source_record(plan,key)
        records.append(row)
    lut_records=lut_project_records(plan,project_target)
    if lut_records:
        index=Path(folder)/LUT_PROJECT_INDEX
        require(not index.exists(),'LUT index creation never overwrites an existing file')
        index.parent.mkdir(parents=True,exist_ok=True)
        index.write_text(json.dumps(lut_records,ensure_ascii=False,indent=2),encoding='utf-8')
    return records


def verify_files(records,folder,plan,project_target=None):
    require(isinstance(records,list) and [r.get('key') for r in records]==needed(plan),
            'Native grade/audio resource records differ from the plan')
    for record in records:
        key=record['key'];custom=custom_lut_key(key)
        relative=lut_relative(key) if key.startswith('lut/') else relative_for(key)
        require(set(record)==({'key','relative','files','source'} if custom else {'key','relative','files'}) and
            record['relative']==relative and record['files']==_entry(key,folder)['files'],
            'Native grade/audio resource identity changed')
        if custom:require(record['source']==_lut_source_record(plan,key),'Custom LUT source provenance differs from plan')
        path=Path(folder)/record['relative']
        if key.startswith('lut/'):lut_deps.verify_cube_package(path,lut_filename(key))
        elif key=='audio/denoise':audio.model_identity(str(path))
        else:require(resources.tree_manifest(path)==record['files'],'Native grade/audio resource bytes changed')
        if key.startswith('filter/experimental-standard-lut33-'):
            require(resources.tree_manifest(lut_candidates.gui_root(_entry(key)))==record['files'],
                    'Managed standard LUT GUI resource bytes changed')
    verify_lut_project_index(plan,folder,project_target)


def _identity_curve():
    return [dict(anchor=dict(x=0,y=0),left_control=dict(x=0,y=0),right_control=dict(x=1/3,y=1/3),sync_direction_control=True),
            dict(anchor=dict(x=1,y=1),left_control=dict(x=2/3,y=2/3),right_control=dict(x=0,y=0),sync_direction_control=True)]


def nodes_for(spec,target):
    nodes=[];grade=spec.get('grade')
    if grade:
        version=grade.get('version',1)
        resource_key=grade_resource_key(grade)
        path=str(Path(target)/relative_for(resource_key))
        lumi=str(Path(path)/'lumi_hub_path') if version==2 else path
        common=dict(path=path,lumi_hub_path=lumi,resource_id='7416258989467374091' if version==2 else '',
                    source_platform=1 if version==2 else 0,version='1')
        if grade.get('lut',{}).get('resource_candidate'):
            # Authored compatibility resources have no official marketplace
            # identity. Keep this explicit instead of impersonating the base.
            common.update(resource_id='',source_platform=0)
        for field,kind in [('temperature','temperature'),('tint','tone')]:
            if field in grade:nodes.append(('effects',dict(common,type=kind,value=grade[field])))
        for channel in COLORS:
            if channel not in grade.get('hsl',{}):continue
            values=grade['hsl'][channel]
            nodes.append(('hsl',dict(common,type='hsl',hsl_color_type=COLORS.index(channel)+1,
                hue=values.get('hue',0),saturation=values.get('saturation',0),lightness=values.get('lightness',0),
                interacting=values.get('interacting',False),constant_material_id='',custom_color=ARGB[COLORS.index(channel)] if version==2 else '')))
        if 'curves' in grade:
            curves={c:deepcopy(grade['curves'].get(c,_identity_curve())) for c in CHANNELS}
            nodes.append(('color_curves',dict(common,type='color_curves',panel='',**curves)))
        if 'wheels' in grade:
            wheels=grade['wheels'];mode=wheels['mode'];bucket=mode+'_color_wheels'
            groups={group:{component:wheels.get(group,{}).get(component,0.) for component in color.WHEEL_COMPONENTS}
                    for group in color.WHEEL_GROUPS[mode]}
            wheel_common={key:value for key,value in common.items() if key!='version'}
            nodes.append((bucket,dict(wheel_common,type=bucket,panel='',intensity=wheels.get('intensity',1.),**groups)))
        if 'lut' in grade:
            lut=grade['lut'];lut_common={key:value for key,value in common.items() if key not in ('path','version')}
            if lut_candidates.is_filter(lut):
                key=lut_candidates.variant_key(lut['resource_candidate'])
                entry=lut_candidates.by_key(key)
                node=dict(entry['material_template'],
                    path=lut_candidates.gui_root(entry).as_posix(),value=lut.get('value',1.))
                # Old audited builds intentionally retain their original shape.
                # A new explicit name enables the normal native filter card.
                if 'native_filter_name' in lut:node['name']=lut['native_filter_name']
                nodes.append(('effects',node))
            elif lut.get('native_package_version',1)==2:
                key=lut_key(lut);cube=Path(target)/lut_relative(key)/lut_filename(key)
                compound=cube.as_posix()+';'+Path(path).as_posix()
            else:compound=str(Path(path)/color.LUT_CUBE)+';'+str(Path(path)/color.LUT_CONFIG.parent)
            if not lut_candidates.is_filter(lut):
                nodes.append(('effects',dict(lut_common,type='lut',path=compound,value=lut.get('value',1.),
                    visible=True,platform='all',version='',enable_skin_tone_correction=False,item_effect_type=0,
                    effect_id='7416258989467374091' if lut.get('native_package_version',1)==2 and not lut.get('resource_candidate') else '',
                    third_resource_id='',adjust_params=[],face_adjust_params=[],exclusion_group=[])))
    processing=spec.get('audio_processing',{})
    if 'studio' in processing:
        nodes.append(('audio_effects',dict(type='audio_effect',resource_id=dsp.RESOURCE_ID,
             path=str(Path(target)/RELATIVE['audio/local-studio']),source_platform=0,sub_type=1,
             name='本地专业声音',vc_type='none',audio_adjust_params=dsp.parameters(processing['studio']),
             is_ugc=False,is_vc_clone_tone=False,time_range=dict(start=0,duration=0),
             production_path='',speaker_id='',third_resource_id='',category_id='',category_name='')))
    if 'studio_chain' in processing:
        values=processing['studio_chain']
        for part,rid,subtype,name in [('eq',dsp.EQ_RESOURCE_ID,0,'本地 EQ'),
                                    ('dynamics',dsp.DYNAMICS_RESOURCE_ID,1,'本地动态处理')]:
            fields={c['kind'] for c in dsp.split_controls(part)}
            nodes.append(('audio_effects',dict(type='audio_effect',resource_id=rid,
                path=str(Path(target)/RELATIVE['audio/local-'+part]),source_platform=0,sub_type=subtype,
                name=name,vc_type='none',audio_adjust_params=dsp.split_parameters(part,{k:v for k,v in values.items() if k in fields}),
                is_ugc=False,is_vc_clone_tone=False,time_range=dict(start=0,duration=0),
                production_path='',speaker_id='',third_resource_id='',category_id='',category_name='')))
    if 'denoise' in processing:
        noise=processing['denoise']
        nodes.append(('realtime_denoises',dict(type='realtime_denoise',is_denoise=noise.get('enabled',True),
            denoise_mode=0,denoise_rate=noise.get('rate',.85),path=str(Path(target)/RELATIVE['audio/denoise']),
            sami_name='denoise_v2',sami_version='1.0',sami_type=2,is_from_hd_sounds=False)))
    return nodes


def apply(segment,materials,spec,kind,target):
    for bucket,template in nodes_for(spec,target):
        node=dict(template,id=str(uuid.uuid4()).upper())
        materials.setdefault(bucket,[]).append(node);segment.setdefault('extra_material_refs',[]).append(node['id'])
        if bucket=='hsl':segment['enable_hsl']=True
        if bucket=='color_curves':segment['enable_color_curves']=True
        if bucket in ('primary_color_wheels','log_color_wheels'):segment['enable_color_wheels']=True
        if node['type']=='lut':segment['enable_lut']=True
        if 'grade' in spec:segment['enable_adjust']=True
        if bucket=='audio_effects':
            # Native control lookups include this persistent effect identity.
            # Empty IDs make different categories alias the same three slots.
            if 'studio_chain' in spec.get('audio_processing',{}):
                node['constant_material_id']=node['id']
            primary=next(m for m in materials['audios'] if m['id']==segment['material_id'])
            primary['check_flag']=primary.get('check_flag',0)|3


def verify(segment,index,spec,kind,target):
    validate_spec(spec,kind)
    expected=nodes_for(spec,target)
    found=[index[r] for r in segment.get('extra_material_refs',[]) if
           color.is_node(*index[r]) or index[r][0] in {'audio_effects','realtime_denoises'} or
           (lut_candidates.is_filter(spec.get('grade',{}).get('lut',{})) and
            index[r][0]=='effects' and index[r][1].get('type')=='filter')]
    require(len(found)==len(expected),'Native grade/audio processing bindings differ from the plan')
    def identity(pair):return pair[0],pair[1]['type'],pair[1].get('hsl_color_type',0)
    for (bucket,wanted),(actual_bucket,node) in zip(sorted(expected,key=identity),sorted(found,key=identity)):
        require(bucket==actual_bucket and all(node.get(k)==v for k,v in wanted.items()),
                'Native grade/audio parameter differs from the plan')
        if bucket=='hsl':require(segment.get('enable_hsl') is True,'Planned HSL is disabled')
        if bucket=='color_curves':require(segment.get('enable_color_curves') is True,'Planned color curves are disabled')
        if bucket in ('primary_color_wheels','log_color_wheels'):
            require(segment.get('enable_color_wheels') is True,'Planned color wheels are disabled')
        if node['type']=='lut':require(segment.get('enable_lut') is True,'Planned LUT is disabled')
        if bucket=='audio_effects':
            primary=index[segment['material_id']][1]
            require(type(primary.get('check_flag')) is int and primary['check_flag']&3==3,'Planned audio effect is not enabled')
    if 'grade' in spec:require(segment.get('enable_adjust') is True,'Planned native grade is disabled')
