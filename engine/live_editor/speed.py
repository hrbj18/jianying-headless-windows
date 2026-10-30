"""Exact-build native curve controls; no pointer injection or input events."""
import struct
import math
from copy import deepcopy
from .errors import require
from .winprocess import Reader
from . import v02

def prepare_controls(editor,segment_id):
    before=editor.status();token=before['snapshot']['token']
    segment=v02.segments(editor.saved()['timeline'])[segment_id][1]
    require(not segment.get('common_keyframes'),'CURVE_MAPPING_SCOPE','Animated curve clips need separate acceptance')
    video=v02.clip_object(editor,'video',segment_id)
    v02.select(editor,video)
    ctx=editor.context()
    require(ctx['token']==token,'SESSION_CHANGED','Draft changed before curve initialization')
    # This existing canvas method initializes controls from the selected
    # segment's saved curve. Merely writing visible does not initialize them.
    editor.invoke_typed(ctx['canvas'],'activeSpeedControl',[('bool',True),('bool',True)],ctx=ctx)
    base=editor.process['modules']['VECreator.dll']['base']
    with Reader(editor.process['pid']) as reader:
        control=reader.pointer(video+0x660)
        require(control and struct.unpack('<i',reader.read(control+4,4))[0]!=0,
                'SPEED_CONTROL_NOT_BOUND','Video has no live speed-control QPointer')
        model=reader.pointer(video+0x668)
        require(model and reader.pointer(model)==base+0xac59560,
                'SPEED_CONTROL_NOT_BOUND','Speed model vtable differs from the reviewed build')
        count=struct.unpack('<q',reader.read(model+0xb8,8))[0]
        require(0<count<=256,'SPEED_CONTROLS_NOT_INITIALIZED','Native curve controls have no valid intervals')
    require(editor.context()['token']==token,'SESSION_CHANGED','Draft changed during curve initialization')
    # SpeedMode is a custom Qt enum; the bridge deliberately supports only
    # reviewed primitive QVariant conversions. Read mode from saved materials.
    details={}
    for key in ['visible','avgSpeedValue','isDraging','isDragingGradientPoint']:
        editor.trace('speed-controls-property',property=key,model=hex(model))
        details[key]=editor.get(model,key)
    require(not details['isDraging'] and not details['isDragingGradientPoint'],
            'SPEED_EDIT_IN_PROGRESS','A native speed operation is already in progress')
    return model,{'route':'MainTimeLineCanvasViewModel.activeSpeedControl',
                  'segment_id':segment_id,'interval_count':count,**details,'simulated_input':False}

def curve_gradient(editor,segment_id,index,gradient):
    import native_speed_curves
    require(type(index) is int and index>=0 and type(gradient) in (int,float) and
            math.isfinite(gradient) and -.95<=gradient<=.95,'INVALID_CURVE_GRADIENT','Use an existing interval and gradient -0.95..0.95')
    old=editor.saved()['timeline']
    native_speed_curves.validate(old)
    old_segment=v02.segments(old)[segment_id][1]
    speeds=old['materials'].get('speeds',[])
    before=next((n for n in speeds if n['id'] in old_segment.get('extra_material_refs',[]) and n.get('curve_speed')),None)
    require(before is not None,'NO_CUSTOM_CURVE','Initialize a native custom curve before editing its gradient')
    users=[s['id'] for t in old['tracks'] for s in t['segments']
           if before['id'] in s.get('extra_material_refs',[])]
    require(users==[segment_id],'CURVE_SHARED_MATERIAL','Selected curve is shared by other clips')
    multitrack=sum(len(t['segments']) for t in old['tracks'])>1
    require(not multitrack or old_segment.get('volume',1)==0,
            'CURVE_SOURCE_AUDIO_SYNC','Multitrack curve edits require muted source video and independently timed audio')
    def protected(doc):
        value=deepcopy(doc)
        segment=v02.segments(value)[segment_id][1]
        bound=[n for n in value['materials']['speeds'] if n['id'] in segment.get('extra_material_refs',[]) and n.get('curve_speed')]
        require(len(bound)==1,'CURVE_BINDING_CHANGED','Selected curve binding changed')
        # Native interpolation can quantize mean speed by a few ulps.
        # Preserve all timeline ranges and every other clip/material exactly.
        segment['speed']=0
        bound[0]['speed']=0
        bound[0]['curve_speed']['speed_points']=[]
        return v02.fingerprint(value)
    before_protected=protected(old)
    points=before['curve_speed']['speed_points']
    def change(report,doc):
        model,details=prepare_controls(editor,segment_id)
        require(index<details['interval_count'],'INVALID_CURVE_INTERVAL','Interval index is outside the native curve')
        with Reader(editor.process['pid']) as reader:
            data=reader.pointer(model+0xb0);item=reader.pointer(data+8*index)
            base=editor.process['modules']['VECreator.dll']['base']
            require(reader.pointer(item)==base+0xac59500,'CURVE_ITEM_NOT_BOUND','Native interval model differs')
            require(struct.unpack('<i',reader.read(item+0x10,4))[0]==index,'CURVE_ITEM_NOT_BOUND','Native interval index differs')
            previous=struct.unpack('<d',reader.read(item+0x50,8))[0]
        require(abs(previous-gradient)>1e-6,'CURVE_UNCHANGED','Requested gradient already matches the native interval')
        editor.invoke_typed(model,'dragGradientStarted',[('int',index),('double',previous)])
        editor.invoke_typed(model,'dragGradientChanged',[('int',index),('double',gradient)])
        editor.invoke_typed(model,'dragGradientFinished',[('int',index),('double',gradient)])
        editor.refresh()
    def accepted(doc):
        native_speed_curves.validate(doc)
        segment=v02.segments(doc)[segment_id][1]
        found=[n for n in doc['materials']['speeds'] if n['id'] in segment['extra_material_refs'] and n.get('curve_speed')]
        return (len(found)==1 and found[0]['curve_speed']['id']==native_speed_curves.CUSTOM_ID and
                found[0]['curve_speed']['speed_points']!=points and protected(doc)==before_protected and
                math.isclose(segment.get('speed',1),old_segment.get('speed',1),abs_tol=1e-5))
    return v02.transaction(editor,'native-speed-curve-gradient',change,accepted)
