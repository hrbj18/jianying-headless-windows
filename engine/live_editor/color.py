"""Bind native color controls through the existing inspector model."""
import math,struct,time
from .errors import require
from .winprocess import Reader
from . import v02

HSL_COLORS=('red','orange','yellow','green','cyan','blue','purple','magenta')
HSL_ARGB=('#FFE64444','#FFE69444','#FFF2F224','#FF45E644',
          '#FF45E6E6','#FF4595E6','#FF9545E6','#FFE644E6')


def _qstring(reader,address):
    _,data,count=struct.unpack('<QQq',reader.read(address,24))
    require(0<=count<=128,'INVALID_COLOR_TAB','Invalid native tab ID')
    return reader.read(data,count*2).decode('utf-16-le') if count else ''


def _stdstring(reader,address):
    count,capacity=struct.unpack('<QQ',reader.read(address+16,16))
    require(0<=count<=128 and capacity>=count,'INVALID_COLOR_SELECTION','Invalid settings segment ID')
    data=address if capacity<16 else reader.pointer(address)
    return reader.read(data,count).decode('utf-8') if count else ''


def prepare_controls(editor,segment_id,load_resources=False):
    before=editor.status();token=before['snapshot']['token']
    timeline=editor.saved()['timeline'];track,segment=v02.segments(timeline)[segment_id]
    if track['type']=='adjust':return prepare_adjust_controls(editor,segment_id,load_resources)
    require(track['type']=='video','COLOR_REQUIRES_VIDEO','Select a video segment')
    video=v02.clip_object(editor,'video',segment_id);v02.select(editor,video)
    editor.refresh()
    ctx=editor.context();base=editor.process['modules']['VECreator.dll']['base']
    candidates=v02.objects(editor,'video_inspector');tabs=[]
    with Reader(editor.process['pid']) as reader:
        require(reader.birth()==editor.process['birth'],'PROCESS_CHANGED','Editor process was replaced')
        for inspector in candidates:
            private=reader.pointer(inspector+8)
            if not private or reader.pointer(private+8)!=inspector:continue
            header=reader.pointer(inspector+0x30)
            if not header or struct.unpack('<i',reader.read(header+4,4))[0]==0:continue
            control=reader.pointer(inspector+0x38)
            if not control or reader.pointer(control)!=base+0xbfbe988:continue
            model_header=reader.pointer(control+0x10)
            if not model_header or struct.unpack('<i',reader.read(model_header+4,4))[0]==0:continue
            model=reader.pointer(control+0x18)
            begin,end,capacity=struct.unpack('<QQQ',reader.read(model+0x28,24))
            require(begin<=end<=capacity and (end-begin)%16==0 and 0<(end-begin)//16<=32,
                    'INVALID_COLOR_TAB','Native inspector tabs are unavailable')
            names=[_qstring(reader,reader.pointer(begin+16*i)+0x58) for i in range((end-begin)//16)]
            if names.count('adjust')==1:tabs.append((inspector,names.index('adjust'),names))
    require(len(tabs)==1,'COLOR_INSPECTOR_NOT_BOUND','Expected one current video inspector')
    inspector,index,names=tabs[0]
    # The shipped QML connects this native signal to its tab control, which
    # performs the real onTabIndexChanged loader. onTabClicked only logs a click.
    editor.invoke_typed(inspector,'switchTab',[('int',index)],ctx=ctx)
    deadline=time.monotonic()+15;bound=[]
    while time.monotonic()<deadline:
        editor.refresh();bound=[]
        with Reader(editor.process['pid']) as reader:
            for outer in v02.objects(editor,'video_adjust'):
                settings=reader.pointer(outer+0x30);handle=reader.pointer(outer+0x40)
                if not settings or not handle or reader.pointer(handle)!=base+0xbfef5b0:continue
                if reader.pointer(handle+0x10)!=base+0xbfef610:continue
                begin,end,_=struct.unpack('<QQQ',reader.read(settings+8,24))
                if end-begin!=32:continue
                if _stdstring(reader,begin)==segment_id:bound.append(handle)
        if len(bound)==1:break
        require(len(bound)<=1,'COLOR_INSPECTOR_NOT_BOUND','Multiple color models claim the target')
        time.sleep(.25)
    require(len(bound)==1,'COLOR_CONTROLS_NOT_INITIALIZED','Native color page did not bind to this video')
    require(editor.context()['token']==token,'SESSION_CHANGED','Draft changed during color initialization')
    loaded=editor.get(bound[0],'isAdjustMergeResourceLoaded')
    requested=bool(load_resources and not loaded)
    if requested:
        # The installed QML LoadTipPanel uses this exact retry method. Request
        # it once, then only observe; never forge the resource-ready flag.
        editor.invoke_typed(bound[0],'loadSmartColorPanelData',[('int',0)])
        end=time.monotonic()+20
        while time.monotonic()<end and not loaded:
            time.sleep(.25)
            require(editor.context()['token']==token,'SESSION_CHANGED','Draft changed during resource load')
            loaded=editor.get(bound[0],'isAdjustMergeResourceLoaded')
    return bound[0],dict(route='PanelSettingCommonViewModel.switchTab',segment_id=segment_id,
                         tab_index=index,tab_id=names[index],selection_verified=True,
                         merge_resource_loaded=loaded,resource_load_requested=requested,simulated_input=False)


def prepare_adjust_controls(editor,segment_id,load_resources=False):
    token=editor.context()['token']
    obj=v02.clip_object(editor,'adjust',segment_id);v02.select(editor,obj)
    base=editor.process['modules']['VECreator.dll']['base'];deadline=time.monotonic()+15
    while True:
        editor.refresh();bound=[]
        with Reader(editor.process['pid']) as reader:
            for outer in v02.objects(editor,'adjust_base'):
                private=reader.pointer(outer+8)
                if not private or reader.pointer(private+8)!=outer:continue
                handle=reader.pointer(outer+0x28)
                if not handle or reader.pointer(handle)!=base+0xbfef5b0 or reader.pointer(handle+0x10)!=base+0xbfef610:continue
                begin,end,_=struct.unpack('<QQQ',reader.read(handle+0x1b8,24))
                if end-begin!=0x148:continue
                segment,control=struct.unpack('<QQ',reader.read(begin,16))
                if not segment or not control or struct.unpack('<i',reader.read(control+8,4))[0]<=0:continue
                if _stdstring(reader,segment+8)==segment_id:bound.append(handle)
        require(len(bound)<=1,'COLOR_CONTROLS_NOT_INITIALIZED','Multiple adjustment handlers claim this segment')
        if bound:break
        require(time.monotonic()<deadline,'COLOR_CONTROLS_NOT_INITIALIZED','Native adjustment inspector did not bind')
        time.sleep(.2)
    handle=bound[0]
    # Published navigation hook: the shipped QML sets the actual subtab index,
    # then onCurrentItemChanged calls onCurTabChanged and refreshes checkbox
    # state from the selected material. This is not a completion/state signal.
    if editor.get(handle,'curTabKey')!='curve':
        editor.invoke_typed(handle,'curTabTypeChanged',[('int',2)])
        deadline=time.monotonic()+10
        while editor.get(handle,'curTabKey')!='curve':
            require(time.monotonic()<deadline,'COLOR_CONTROLS_NOT_INITIALIZED','Normal curve subtab did not initialize')
            time.sleep(.2)
    loaded=editor.get(handle,'isAdjustMergeResourceLoaded')
    requested=bool(load_resources and not loaded)
    if requested:
        editor.invoke_typed(handle,'loadSmartColorPanelData',[('int',0)])
        deadline=time.monotonic()+20
        while not loaded and time.monotonic()<deadline:
            time.sleep(.2);loaded=editor.get(handle,'isAdjustMergeResourceLoaded')
    with Reader(editor.process['pid']) as reader:
        state=struct.unpack('<i',reader.read(handle+0xe4,4))[0]
        mode=struct.unpack('<i',reader.read(handle+0x124,4))[0]
    require(editor.context()['token']==token,'SESSION_CHANGED','Draft changed during adjustment binding')
    return handle,dict(route='DraftInspectorAdjustBaseViewModel.handler',segment_id=segment_id,
        selection_verified=True,merge_resource_loaded=loaded,resource_load_requested=requested,
        color_curves_enable_state=state,color_curves_checked=state==0,curve_mode=mode,
        active_subtab=editor.get(handle,'curTabKey'),
        curve_controls_visible=bool(loaded and mode in (2,3) and editor.get(handle,'curTabKey')=='curve'),
        can_edit_curves_in_native_ui=bool(loaded and mode in (2,3) and state==0 and
                                         editor.get(handle,'curTabKey')=='curve'),simulated_input=False)


def hsl(editor,segment_id,channel,property,value):
    import native_color
    require(channel in HSL_COLORS and property in ('hue','saturation','lightness') and
            type(value) is int and -100<=value<=100,'INVALID_HSL','Use an existing color and integer -100..100')
    color_type=HSL_COLORS.index(channel)+1
    def current(doc):
        track,segment=v02.segments(doc)[segment_id]
        require(track['type']=='video','COLOR_REQUIRES_VIDEO','HSL requires video')
        nodes=[n for n in doc['materials'].get('hsl',[]) if n['id'] in segment.get('extra_material_refs',[]) and
               n.get('hsl_color_type')==color_type]
        # The native GUI keys normal colors by both type and their ARGB swatch.
        # Legacy SDK nodes can have an empty custom_color; prefer the exact
        # GUI-keyed node after native migration instead of confusing the two.
        keyed=[n for n in nodes if n.get('custom_color')==HSL_ARGB[color_type-1]]
        if keyed:nodes=keyed
        require(len(nodes)==1,'HSL_CHANNEL_NOT_BOUND','Initialize this color channel in the native plan first')
        return nodes[0]
    old=editor.saved()['timeline'];native_color.validate(native_color.resolve_timeline_paths(old,editor.context()['path']));before=current(old)
    require(before.get(property,0)!=value,'HSL_UNCHANGED','Requested HSL value already matches')
    def change(report,doc):
        require(current(doc)==before,'REVISION_CHANGED','HSL material changed before editing')
        model,_=prepare_controls(editor,segment_id)
        editor.invoke_typed(model,'acceptHslColorType',[('int',color_type),('QString',HSL_ARGB[color_type-1])])
        method={'hue':'acceptHslHue','saturation':'acceptHslSaturation','lightness':'acceptHslLightness'}[property]
        editor.invoke_typed(model,method,[('int',value),('bool',True),('bool',False)])
        editor.refresh()
    def accepted(doc):
        node=current(doc)
        if node.get(property,0)!=value:return False
        native_color.validate(native_color.resolve_timeline_paths(doc,editor.context()['path']))
        return node['id']==before['id'] and node.get('path')==before.get('path')
    return v02.transaction(editor,'native-hsl-'+channel+'-'+property,change,accepted)


WHEEL_LAYOUT={
    'primary':{'lift':(0x28,0),'gamma':(0x30,1),'gain':(0x38,2),'offset':(0x40,3)},
    'log':{'shadow':(0x48,5),'midtone':(0x50,6),'highlight':(0x58,7),'offset':(0x60,8)},
}
WHEEL_FLAGS={'red':1,'green':4,'blue':2,'saturation':8}


def wheel_node(doc,segment_id,mode):
    track,segment=v02.segments(doc)[segment_id]
    require(track['type']=='video','COLOR_REQUIRES_VIDEO','Color wheels require video')
    nodes=[node for node in doc['materials'].get(mode+'_color_wheels',[])
           if node['id'] in segment.get('extra_material_refs',[])]
    require(len(nodes)==1,'COLOR_WHEEL_NOT_BOUND','Initialize this wheel mode in the native plan first')
    return nodes[0]


def prepare_wheel_controls(editor,segment_id,mode):
    require(mode in WHEEL_LAYOUT,'INVALID_COLOR_WHEEL','Use primary or log wheels')
    token=editor.context()['token']
    handle,metadata=prepare_controls(editor,segment_id,load_resources=True)
    # Official setter only persists a UI preference and refreshes these items.
    # It does not modify a material, but controls the next native action's mode.
    editor.invoke_typed(handle,'setColorWheelsTab',[('int',0 if mode=='primary' else 1)])
    base=editor.process['modules']['VECreator.dll']['base'];items={};controls={}
    doc=editor.saved()['timeline'];node=wheel_node(doc,segment_id,mode)
    with Reader(editor.process['pid']) as reader:
        data=reader.pointer(handle+0x128)
        require(data and reader.pointer(data)==base+0xb4a4298,'COLOR_WHEEL_DATA_NOT_BOUND',
                'Native wheel data does not belong to the current adjustment handler')
        require(struct.unpack('<i',reader.read(data+0x14,4))[0]==(0 if mode=='primary' else 1),
                'COLOR_WHEEL_MODE_MISMATCH','The native wheel mode did not settle')
        for group,(offset,kind) in WHEEL_LAYOUT[mode].items():
            item=reader.pointer(data+offset)
            require(item and reader.pointer(item)==base+0xb4a4238 and
                    struct.unpack('<i',reader.read(item+0x50,4))[0]==kind,
                    'COLOR_WHEEL_ITEM_NOT_BOUND','Native wheel group identity differs')
            private=reader.pointer(item+8)
            require(private and reader.pointer(private+8)==item,'COLOR_WHEEL_ITEM_NOT_BOUND',
                    'Native wheel item is no longer a live QObject')
            values=dict(zip(('red','green','blue','saturation'),struct.unpack('<dddd',reader.read(item+0x10,32))))
            mix=reader.read(item+0x30,4)
            require(not any(mix),'COLOR_WHEEL_MIXED','Mixed wheel controls are not editable by this command')
            saved=node.get(group,{})
            matches=all(math.isclose(value,saved.get(name,0),abs_tol=1e-6) for name,value in values.items())
            controls[group]=dict(values=values,saved_values=saved,matches_saved_value=matches)
            items[group]=item
    require(editor.context()['token']==token,'SESSION_CHANGED','Draft changed during wheel binding')
    return handle,items,dict(metadata,mode=mode,controls=controls,simulated_input=False)


def color_wheel(editor,segment_id,mode,group,component,value):
    import native_color
    require(mode in WHEEL_LAYOUT and group in WHEEL_LAYOUT[mode] and component in WHEEL_FLAGS and
            type(value) in (int,float) and math.isfinite(value) and -1<=value<=1,
            'INVALID_COLOR_WHEEL','Use an existing wheel group/component and a finite value in -1..1')
    doc=editor.saved()['timeline'];native_color.validate(native_color.resolve_timeline_paths(doc,editor.context()['path']));before=wheel_node(doc,segment_id,mode)
    require(not math.isclose(before.get(group,{}).get(component,0),value,abs_tol=1e-6),
            'COLOR_WHEEL_UNCHANGED','Requested native wheel value already matches')
    def change(report,doc):
        require(wheel_node(doc,segment_id,mode)==before,'REVISION_CHANGED','Color wheel changed before editing')
        handle,items,controls=prepare_wheel_controls(editor,segment_id,mode)
        require(controls['controls'][group]['matches_saved_value'],'COLOR_WHEEL_VALUE_MISMATCH',
                'Native wheel display differs from the saved material')
        values={name:0. for name in ('red','green','blue','saturation','luma')};values[component]=value
        args=[('QQuickItem*',items[group],'AdjustColorWheelItemData*'),
              ('int',WHEEL_FLAGS[component],'ColorWheelsParamFlag')]
        args += [('double',values[name]) for name in ('red','green','blue','saturation','luma')]
        args += [('bool',True)]
        editor.invoke_typed(handle,'setColorWheelValue',args)
        editor.refresh()
    def accepted(doc):
        node=wheel_node(doc,segment_id,mode)
        if not math.isclose(node.get(group,{}).get(component,0),value,abs_tol=1e-6):return False
        native_color.validate(native_color.resolve_timeline_paths(doc,editor.context()['path']))
        return node['id']==before['id'] and node['path']==before['path']
    return v02.transaction(editor,'native-wheel-'+mode+'-'+group+'-'+component,change,accepted)


def prepare_lut_controls(editor,segment_id):
    handle,metadata=prepare_controls(editor,segment_id,load_resources=True)
    doc=editor.saved()['timeline'];track,segment=v02.segments(doc)[segment_id]
    nodes=[node for node in doc['materials'].get('effects',[]) if node.get('type')=='lut'
           and node['id'] in segment.get('extra_material_refs',[])]
    require(len(nodes)==1,'LUT_NOT_BOUND','Initialize one native LUT on the selected video')
    base=editor.process['modules']['VECreator.dll']['base']
    with Reader(editor.process['pid']) as reader:
        data=reader.pointer(handle+0xa0)
        require(data and reader.pointer(data)==base+0xb4a4058,'LUT_DATA_NOT_BOUND','Unexpected native LUT data')
        item=reader.pointer(data+0x10)
        require(item and reader.pointer(item)==base+0xb4a3ed8 and
                struct.unpack('<i',reader.read(item+0x9c,4))[0]==14,
                'LUT_SLIDER_NOT_BOUND','Unexpected native LUT intensity slider')
        private=reader.pointer(item+8)
        require(private and reader.pointer(private+8)==item,'LUT_SLIDER_NOT_BOUND','LUT slider expired')
        ui,low_slider,high_slider,low_edit,high_edit=struct.unpack('<ddddd',reader.read(item+0x60,40))
        low_native,high_native=struct.unpack('<dd',reader.read(item+0xa0,16))
        require(all(math.isfinite(v) for v in (ui,low_edit,high_edit,low_native,high_native)) and high_edit>low_edit,
                'LUT_RANGE_INVALID','Native LUT slider ranges are invalid')
        native=low_native+(ui-low_edit)/(high_edit-low_edit)*(high_native-low_native)
        properties=dict(ui_value=ui,min_slider_ui=low_slider,max_slider_ui=high_slider,
            min_edit_ui=low_edit,max_edit_ui=high_edit,min_native=low_native,max_native=high_native,
            native_value=native,persisted_value=nodes[0].get('value',0),
            matches_saved_value=math.isclose(native,nodes[0].get('value',0),abs_tol=1e-6),
            property_type=_qstring(reader,item+0x28),constant_material_id=_qstring(reader,item+0x40),
            enabled=bool(reader.read(item+0x58,1)[0]),visible=bool(reader.read(item+0x59,1)[0]),
            mixed=bool(reader.read(item+0x5a,1)[0]),enable_state=struct.unpack('<i',reader.read(data+0x18,4))[0],
            selected_text=_qstring(reader,data+0x28),path_mixed=bool(reader.read(data+0x40,1)[0]))
    return handle,item,dict(metadata,lut=properties,material=nodes[0])
