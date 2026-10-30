"""Native fixed-parameter audio controls; no keyframe-slot substitution."""
import math,struct,time
import native_audio_processing as audio
import native_dsp_graph as dsp
from .errors import require
from .winprocess import Reader
from . import v02


def effect_for(doc,segment_id,parameter=None):
    track,segment=v02.segments(doc)[segment_id]
    require(track['type']=='audio','AUDIO_REQUIRES_AUDIO','Select an independent audio segment')
    nodes=[n for n in doc['materials'].get('audio_effects',[]) if n['id'] in segment.get('extra_material_refs',[])]
    if len(nodes)==1 and nodes[0].get('resource_id')==dsp.RESOURCE_ID:return nodes[0]
    pair={n.get('resource_id'):n for n in nodes}
    require(len(nodes)==2 and set(pair)=={dsp.EQ_RESOURCE_ID,dsp.DYNAMICS_RESOURCE_ID},
            'STUDIO_EFFECT_NOT_BOUND','Initialize the native studio chain in the plan first')
    require(parameter is not None,'STUDIO_PARAMETER_REQUIRED','Choose a studio chain parameter')
    return pair[dsp.EQ_RESOURCE_ID if parameter in ('gain','frequency') else dsp.DYNAMICS_RESOURCE_ID]


def _split_controls(editor,segment_id,doc,token):
    from .color import _stdstring, _qstring
    segment=v02.segments(doc)[segment_id][1]
    effects={n['resource_id']:n for n in doc['materials']['audio_effects'] if n['id'] in segment['extra_material_refs']}
    constants=[node.get('constant_material_id') for node in effects.values()]
    require(all(isinstance(value,str) and value for value in constants) and len(set(constants))==2,
            'AUDIO_PARAMETER_IDENTITY_MISSING','The native studio categories require distinct persistent parameter IDs')
    obj=v02.clip_object(editor,'audio',segment_id);v02.select(editor,obj);editor.refresh()
    # The current desktop layout uses lazy inspector tabs rather than the old
    # monolithic AudioSettingViewModel. Enter its real native effect page.
    tab_bindings=[]
    base=editor.process['modules']['VECreator.dll']['base']
    with Reader(editor.process['pid']) as reader:
        for inspector in v02.objects(editor,'audio_inspector'):
            private=reader.pointer(inspector+8)
            if not private or reader.pointer(private+8)!=inspector:continue
            control=reader.pointer(inspector+0x38)
            if not control or reader.pointer(control)!=base+0xbfbe988:continue
            model=reader.pointer(control+0x18)
            if not model:continue
            begin,end,capacity=struct.unpack('<QQQ',reader.read(model+0x28,24))
            require(begin<=end<=capacity and (end-begin)%16==0 and 0<end-begin<=512,
                    'AUDIO_CATEGORY_NOT_BOUND','Native audio tabs are unavailable')
            names=[_qstring(reader,reader.pointer(begin+16*i)+0x58) for i in range((end-begin)//16)]
            if names.count('audio_effects')==1:tab_bindings.append((inspector,names.index('audio_effects')))
    if tab_bindings:
        require(len(tab_bindings)==1,'AUDIO_CATEGORY_NOT_BOUND','Multiple audio inspectors claim selection')
        inspector,index=tab_bindings[0]
        editor.invoke_typed(inspector,'switchTab',[('int',index)])
        editor.refresh()
    base=editor.process['modules']['VECreator.dll']['base'];bindings=[]
    with Reader(editor.process['pid']) as reader:
        for page in v02.objects(editor,'audio_effect_page'):
            private=reader.pointer(page+8)
            if not private or reader.pointer(private+8)!=page:continue
            model=reader.pointer(page+0x10);sub=reader.pointer(page+0x20)
            if not model or not sub or reader.pointer(sub)!=base+0xbf9bfe0:continue
            # The desktop effect page is owned by the current audio inspector,
            # and its handlers share that inspector model's exact wrapper.
            if not tab_bindings or reader.pointer(tab_bindings[0][0]+0x50)!=model:continue
            wrapper=reader.pointer(model+0xa8);wrapper_shared=reader.pointer(model+0xb0)
            if not wrapper or not wrapper_shared:continue
            # The new inspector wrapper has a different class layout. Its
            # owning DraftInspectorAudioModel carries the selection vector.
            begin,end,_=struct.unpack('<QQQ',reader.read(model+0x50,24))
            if end-begin!=32 or _stdstring(reader,begin)!=segment_id:continue
            handlers=[]
            for offset,kind,rid,category in [(0x68,0,dsp.EQ_RESOURCE_ID,'tone'),
                                           (0x70,1,dsp.DYNAMICS_RESOURCE_ID,'sound_effect')]:
                handler=reader.pointer(sub+offset)
                if (not handler or reader.pointer(handler)!=base+0xbf95348 or
                    reader.pointer(handler+0x38)!=base+0xbf956b0 or reader.pointer(handler+0x1f8)!=base+0xbf956d8 or
                    reader.pointer(handler+0x388)!=wrapper or reader.pointer(handler+0x390)!=wrapper_shared or
                    struct.unpack('<i',reader.read(handler+0x380,4))[0]!=kind):break
                handlers.append((handler,rid,category))
            if len(handlers)==2:bindings.append(handlers)
        for vm in v02.objects(editor,'audio_setting'):
            private=reader.pointer(vm+8)
            if not private or reader.pointer(private+8)!=vm:continue
            settings=reader.pointer(vm+0x18);shared=reader.pointer(vm+0x20)
            wrapper=reader.pointer(vm+0x28);wrapper_shared=reader.pointer(vm+0x30)
            sub=reader.pointer(vm+0x40)
            if not all((settings,wrapper,sub)) or reader.pointer(sub)!=base+0xbf9bfe0:continue
            if reader.pointer(wrapper+8)!=settings or reader.pointer(wrapper+0x10)!=shared:continue
            begin,end,_=struct.unpack('<QQQ',reader.read(settings+8,24))
            if end-begin!=32 or _stdstring(reader,begin)!=segment_id:continue
            handlers=[]
            for offset,kind,rid,category in [(0x68,0,dsp.EQ_RESOURCE_ID,'tone'),
                                           (0x70,1,dsp.DYNAMICS_RESOURCE_ID,'sound_effect')]:
                handler=reader.pointer(sub+offset)
                if (not handler or reader.pointer(handler)!=base+0xbf95348 or
                    reader.pointer(handler+0x38)!=base+0xbf956b0 or reader.pointer(handler+0x1f8)!=base+0xbf956d8 or
                    reader.pointer(handler+0x388)!=wrapper or reader.pointer(handler+0x390)!=wrapper_shared or
                    struct.unpack('<i',reader.read(handler+0x380,4))[0]!=kind):break
                handlers.append((handler,rid,category))
            if len(handlers)==2:bindings.append(handlers)
    require(len(bindings)==1,'AUDIO_CATEGORY_NOT_BOUND','Expected one native tone/sound-effect model bound to this audio')
    values={}
    for handler,rid,category in bindings[0]:
        # The installed QML uses this notification to refresh the current
        # category. It ignores its int and does not replace any audio material.
        editor.invoke_typed(handler,'onVoiceChangeSelected',[('int',0)])
        entry=audio.entry_for_node('audio_effects',effects[rid])
        controls={(c['parameterIndex'],c['portIndex']):c for c in entry['controls']}
        with Reader(editor.process['pid']) as reader:
            data=reader.pointer(handler+0x2e8);count=struct.unpack('<q',reader.read(handler+0x2f0,8))[0]
            require(count==len(controls)<=3,'AUDIO_CATEGORY_CONTROLS','Native category control count differs')
            for i in range(count):
                item=reader.pointer(data+8*i)
                require(reader.pointer(item)==base+0xbff3ac0 and reader.pointer(item+0xd0)==handler,
                        'AUDIO_CATEGORY_CONTROLS','Slider does not belong to this native category')
                pi,port=[int(editor.get(item,k)) for k in ('parameterIndex','portIndex')]
                key=(pi,port);control=controls.get(key)
                require(control is not None,'AUDIO_CATEGORY_CONTROLS','Unknown native category parameter')
                fields={k:editor.get(item,k) for k in ('sliderName','value','defaultValue','minValue','maxValue','hide','isMix','categoryID')}
                require(fields['categoryID']==category and fields['sliderName']==control['name'] and
                    fields['minValue']==0 and fields['maxValue']==1 and not fields['hide'] and not fields['isMix'],
                    'AUDIO_CATEGORY_CONTROLS','Native category metadata differs from the selected effect')
                saved=next(p.get('value',0) for p in effects[rid]['audio_adjust_params'] if
                    (p.get('parameterIndex',0),p.get('portIndex',0))==key)
                fields.update(persisted_value=saved,matches_saved_value=math.isclose(fields['value'],saved,abs_tol=1e-6))
                require((rid,pi,port) not in values,'AUDIO_CATEGORY_CONTROLS','Duplicate native category parameter')
                values[(rid,pi,port)]=(item,fields)
    require(editor.context()['token']==token and editor.get(obj,'selected'),'SESSION_CHANGED','Selected audio changed')
    return values,dict(segment_id=segment_id,resources=list(effects),count=len(values),
        route='AudioEffectsSettingSubViewModel.timbreSettingHandler/soundSettingHandler',
        controls=[dict(resource_id=k[0],parameter_index=k[1],port_index=k[2],**v[1]) for k,v in values.items()],
        simulated_input=False,keyframe_automation=False)


def prepare_controls(editor,segment_id):
    before=editor.status();token=before['snapshot']['token'];doc=editor.saved()['timeline']
    audio.validate(doc);effect=effect_for(doc,segment_id,'gain')
    if effect['resource_id']==dsp.EQ_RESOURCE_ID:return _split_controls(editor,segment_id,doc,token)
    # Until the shared wrapper's multi-selection binding has separate evidence,
    # require the actual one-audio acceptance project rather than guess a target.
    require(sum(len(t['segments']) for t in doc['tracks'] if t['type']=='audio')==1,
            'AUDIO_CONTROL_SCOPE','Native studio live validation currently requires one audio segment')
    obj=v02.clip_object(editor,'audio',segment_id);v02.select(editor,obj)
    base=editor.process['modules']['VECreator.dll']['base'];deadline=time.monotonic()+15
    expected={(c['parameterIndex'],c['portIndex']):c for c in dsp.CONTROLS};matches=[]
    while time.monotonic()<deadline:
        editor.refresh();matches=[]
        with Reader(editor.process['pid']) as reader:
            for handler in v02.objects(editor,'audio_handler'):
                private=reader.pointer(handler+8)
                if not private or reader.pointer(private+8)!=handler:continue
                data=reader.pointer(handler+0x2e8);count=struct.unpack('<q',reader.read(handler+0x2f0,8))[0]
                if count!=len(expected):continue
                values={};valid=True
                for index in range(count):
                    item=reader.pointer(data+8*index)
                    if not item or reader.pointer(item)!=base+0xbff3ac0 or reader.pointer(item+0xd0)!=handler:
                        valid=False;break
                    pi,port=[editor.get(item,k) for k in ('parameterIndex','portIndex')]
                    if not all(type(n) in (int,float) and math.isfinite(n) and n==int(n) for n in (pi,port)):
                        valid=False;break
                    key=(int(pi),int(port));control=expected.get(key)
                    if control is None or key in values:valid=False;break
                    fields={k:editor.get(item,k) for k in ('sliderName','value','defaultValue','minValue','maxValue','hide','isMix','materialID')}
                    # materialID is a keyframe binding and is legitimately empty
                    # for fixed local effects. Match this unique selected audio's
                    # immutable effect metadata, owner and five controls instead.
                    if fields['sliderName']!=control['name'] or fields['hide'] or fields['isMix']:
                        valid=False;break
                    if fields['minValue']!=0 or fields['maxValue']!=1:valid=False;break
                    saved=next(p.get('value',0) for p in effect['audio_adjust_params'] if
                        (p.get('parameterIndex',0),p.get('portIndex',0))==key)
                    fields['persisted_value']=saved
                    fields['matches_saved_value']=math.isclose(fields['value'],saved,abs_tol=1e-6)
                    values[key]=(item,fields)
                if valid and len(values)==len(expected):matches.append(values)
        if len(matches)==1:break
        require(len(matches)<=1,'AUDIO_CONTROLS_AMBIGUOUS','Multiple handlers claim the studio controls')
        time.sleep(.25)
    require(len(matches)==1,'AUDIO_CONTROLS_NOT_INITIALIZED','Native audio controls did not bind to the selected studio effect')
    require(editor.context()['token']==token and editor.get(obj,'selected'),
            'SESSION_CHANGED','Audio selection changed during control initialization')
    values={(dsp.RESOURCE_ID,*k):v for k,v in matches[0].items()}
    return values,dict(segment_id=segment_id,resource_id=dsp.RESOURCE_ID,count=len(values),
        controls=[dict(resource_id=k[0],parameter_index=k[1],port_index=k[2],**v[1]) for k,v in values.items()],
        simulated_input=False,keyframe_automation=False)


def adjust(editor,segment_id,parameter,physical):
    normalized=dsp.normalize(parameter,physical)
    before=effect_for(editor.saved()['timeline'],segment_id,parameter)
    entry=audio.entry_for_node('audio_effects',before)
    control=next(c for c in entry['controls'] if c['kind']==parameter)
    key=(before['resource_id'],control['parameterIndex'],control['portIndex'])
    def value(node):
        return next(p.get('value',0) for p in node['audio_adjust_params'] if
                    (p.get('parameterIndex',0),p.get('portIndex',0))==key[1:])
    require(not math.isclose(value(before),normalized,abs_tol=1e-6),
            'AUDIO_DSP_UNCHANGED','Requested studio value already matches')
    def change(report,doc):
        require(effect_for(doc,segment_id,parameter)==before,'REVISION_CHANGED','Audio effect changed before editing')
        values,_=prepare_controls(editor,segment_id)
        require(values[key][1]['matches_saved_value'],'AUDIO_SLIDER_VALUE_MISMATCH',
                'Native slider and saved parameter disagree; inspect this control before editing')
        editor.invoke_typed(values[key][0],'acceptVoiceChangeAdjustParams',[('double',normalized),('bool',False)])
        editor.refresh()
    def accepted(doc):
        node=effect_for(doc,segment_id,parameter)
        if not math.isclose(value(node),normalized,abs_tol=1e-6):return False
        audio.validate(doc)
        return node['path']==before['path']
    return v02.transaction(editor,'native-studio-'+parameter,change,accepted)
