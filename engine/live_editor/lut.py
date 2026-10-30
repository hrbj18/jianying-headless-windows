"""Normal native project LUT library and its real, owned selection items."""
from copy import deepcopy
import hashlib
from pathlib import Path
import struct,time,math
from . import v02
from .color import prepare_controls
from .errors import require
from .winprocess import Reader


def _text(r,p,wide=True):
    if wide:
        _,data,n=struct.unpack('<QQq',r.read(p,24))
        require(0<=n<=4096,'LUT_TEXT_INVALID','Native LUT text exceeds bounds')
        return r.read(data,n*2).decode('utf-16-le') if n else ''
    n,cap=struct.unpack('<QQ',r.read(p+16,16))
    require(0<=n<=4096 and cap>=n,'LUT_TEXT_INVALID','Native LUT key exceeds bounds')
    return r.read(p if cap<16 else r.pointer(p),n).decode('utf-8') if n else ''


def _children(r,model):
    data,count=struct.unpack('<Qq',r.read(model+0x90,16))
    require(0<=count<=256 and (data or not count),'LUT_ITEMS_INVALID','Invalid native LUT collection')
    result=[]
    for i in range(count):
        control,item=struct.unpack('<QQ',r.read(data+i*16,16))
        require(control and item and struct.unpack('<i',r.read(control+4,4))[0]!=0,
                'LUT_ITEM_EXPIRED','Native LUT collection item expired')
        private=r.pointer(item+8)
        require(private and r.pointer(private+8)==item,'LUT_ITEM_EXPIRED','Native LUT item is not a current QObject')
        result.append(item)
    return result


def prepare_library(editor,segment_id):
    token=editor.context()['token']
    handle,metadata=prepare_controls(editor,segment_id,load_resources=True)
    editor.invoke_typed(handle,'getVESpinComboBoxViewModel',[])
    base=editor.process['modules']['VECreator.dll']['base']
    with Reader(editor.process['pid']) as r:
        combo=r.pointer(handle+0x208)
        require(combo and r.pointer(combo)==base+0xbff1940 and r.pointer(combo+0x268)==handle,
                'LUT_LIBRARY_NOT_BOUND','Native LUT library does not belong to the current adjustment handler')
    # The published QML calls this loader. It builds genuine item objects,
    # rather than inventing a pointer or setting a cached current-index value.
    editor.invoke_typed(combo,'getData',[])
    end=time.monotonic()+15;items=[]
    while time.monotonic()<end:
        with Reader(editor.process['pid']) as r:
            control,root=struct.unpack('<QQ',r.read(combo+0x100,16))
            require(control and root and struct.unpack('<i',r.read(control+4,4))[0]!=0 and
                    r.pointer(root)==base+0xd34e990,'LUT_LIBRARY_NOT_BOUND','Native LUT root model expired')
            items=[]
            for group in _children(r,root):
                require(r.pointer(group)==base+0xa57eef0,'LUT_GROUP_INVALID','Unknown native LUT group')
                for item in _children(r,group):
                    require(r.pointer(item)==base+0xa581508 and r.pointer(item+0x288)==combo and
                            r.pointer(item+0x280),'LUT_ITEM_OWNER_INVALID','LUT item has a different owner')
                    path=_text(r,item+0x200,False);title=_text(r,item+0x3b0)
                    items.append((item,dict(path=path,title=title)))
        if items:break
        time.sleep(.2)
    require(items,'LUT_LIBRARY_EMPTY','Native LUT library has no current items')
    require(editor.context()['token']==token,'SESSION_CHANGED','Draft changed while binding native LUT items')
    return combo,items,dict(metadata,items=[x[1] for x in items],simulated_input=False)


def _material(doc,segment_id):
    track,segment=v02.segments(doc)[segment_id]
    require(track['type']=='video','LUT_REQUIRES_VIDEO','Select video')
    nodes=[n for n in doc['materials'].get('effects',[]) if n.get('type')=='lut' and n['id'] in segment.get('extra_material_refs',[])]
    require(len(nodes)==1,'LUT_NOT_BOUND','Initialize one reviewed LUT material in the plan first')
    return nodes[0]


def _cube_path(editor,node):
    from jy14_headless import native_media_path
    return native_media_path(node['path'].split(';')[0],Path(editor.context()['path']))


def _without_selected_lut(doc,segment_id):
    value=deepcopy(doc);node=_material(value,segment_id)
    value['materials']['effects']=[n for n in value['materials']['effects'] if n['id']!=node['id']]
    segment=v02.segments(value)[segment_id][1]
    segment['extra_material_refs']=[ref for ref in segment['extra_material_refs'] if ref!=node['id']]
    return value


def _require_native_edit_mode(doc,segment_id):
    refs=v02.segments(doc)[segment_id][1].get('extra_material_refs',[])
    red=[n for n in doc['materials'].get('hsl',[]) if n['id'] in refs and
         n.get('type')=='hsl' and n.get('hsl_color_type')==1 and
         n.get('custom_color')=='#FFE64444']
    require(len(red)==1 and red[0].get('interacting') is True,
            'LUT_NATIVE_EDIT_MODE_UNPREPARED',
            'Native LUT editing would also initialize red HSL mode; use an explicitly prepared new plan')


def selection_projection(doc,segment_id,baseline):
    """Protect content while allowing the native LUT action's neutral red HSL.

    This exact helper material was observed in the first real selection. A
    nonzero, pre-existing or unknown-resource HSL is never discarded here.
    """
    import native_color
    value=_without_selected_lut(doc,segment_id)
    original_ids={n['id'] for n in baseline['materials'].get('hsl',[])}
    segment=v02.segments(value)[segment_id][1];ignored=set()
    for node in value['materials'].get('hsl',[]):
        if (node['id'] in original_ids or node['id'] not in segment['extra_material_refs'] or
            node.get('type')!='hsl' or node.get('hsl_color_type')!=1 or node.get('version')!='1' or
            node.get('custom_color')!='#FFE64444' or not node.get('interacting') or
            not node.get('constant_material_id') or
            any(type(node.get(k,0)) is not int or node.get(k,0)!=0 for k in ('hue','saturation','lightness'))):continue
        entry=native_color.entry_for_node('hsl',node)
        native_color.verify_resource(native_color.resource_root(node),entry)
        ignored.add(node['id'])
    if ignored:
        value['materials']['hsl']=[n for n in value['materials']['hsl'] if n['id'] not in ignored]
        if not value['materials']['hsl'] and 'hsl' not in baseline['materials']:value['materials'].pop('hsl')
        segment['extra_material_refs']=[x for x in segment['extra_material_refs'] if x not in ignored]
        old_segment=v02.segments(baseline)[segment_id][1]
        if 'enable_hsl' in old_segment:segment['enable_hsl']=old_segment['enable_hsl']
        else:segment.pop('enable_hsl',None)
    return v02.fingerprint(value)


def verify_diagnostic_package(cube):
    # This first integration proof uses the original native bundled CUBE and
    # the actual native importer-generated configuration, not arbitrary files.
    import native_lut_dependencies
    native_lut_dependencies.verify_cube_package(cube.parent,cube.name)


def select(editor,segment_id,path):
    path=Path(path).resolve(strict=True);verify_diagnostic_package(path)
    before_doc=editor.saved()['timeline'];before=deepcopy(_material(before_doc,segment_id))
    _require_native_edit_mode(before_doc,segment_id)
    require(_cube_path(editor,before)!=path,'LUT_UNCHANGED','Requested LUT is already selected')
    def change(report,doc):
        require(_material(doc,segment_id)==before,'REVISION_CHANGED','LUT changed before selection')
        combo,items,_=prepare_library(editor,segment_id)
        matches=[item for item,info in items if info['path'] and Path(info['path']).resolve()==path]
        require(len(matches)==1,'LUT_ITEM_NOT_UNIQUE','Requested LUT is not one genuine current native library item')
        editor.invoke_typed(combo,'onClickItem',
            [('QQuickItem*',matches[0],'VESpinComboBoxItemViewModel*'),('bool',False)])
        editor.refresh()
    def protected(doc):
        return v02.fingerprint(_without_selected_lut(doc,segment_id))
    before_protected=protected(before_doc)
    def accepted(doc):
        node=_material(doc,segment_id)
        # A normal LUT replacement creates a new material UUID. Protect the
        # rest of the timeline rather than falsely requiring the old UUID.
        return (_cube_path(editor,node)==path and
                protected(doc)==before_protected)
    return v02.transaction(editor,'native-lut-library-select',change,accepted)


def intensity(editor,segment_id,value):
    import native_color
    from .color import prepare_lut_controls
    require(type(value) in (int,float) and math.isfinite(value) and 0<=value<=1,
            'LUT_VALUE_INVALID','Native LUT strength must be finite in 0..1')
    doc=editor.saved()['timeline'];native_color.validate(native_color.resolve_timeline_paths(doc,editor.context()['path']))
    _require_native_edit_mode(doc,segment_id)
    before=deepcopy(_material(doc,segment_id))
    before_protected=v02.fingerprint(_without_selected_lut(doc,segment_id))
    require(not math.isclose(before.get('value',0),value,abs_tol=1e-6),
            'LUT_UNCHANGED','Native LUT strength already matches')
    def change(report,doc):
        require(_material(doc,segment_id)==before,'REVISION_CHANGED','LUT changed before editing')
        handle,item,controls=prepare_lut_controls(editor,segment_id)
        editor.invoke_typed(handle,'acceptHslColorType',[('int',1),('QString','#FFE64444')])
        c=controls['lut']
        require(c['enabled'] and not c['mixed'] and c['matches_saved_value'],
                'LUT_CONTROL_DISABLED','Native LUT slider is not enabled and bound to the saved value')
        low,high=c['min_native'],c['max_native']
        require(high>low and low<=value<=high,'LUT_RANGE_INVALID','Requested strength is outside native bounds')
        ui=c['min_edit_ui']+(value-low)/(high-low)*(c['max_edit_ui']-c['min_edit_ui'])
        editor.invoke_typed(handle,'onValueChanged',[
            ('QQuickItem*',item,'ParamSettingSliderData*'),('double',ui),('bool',False),('bool',True)])
        editor.refresh()
    def accepted(doc):
        node=_material(doc,segment_id)
        if not math.isclose(node.get('value',0),value,abs_tol=1e-6):return False
        native_color.validate(native_color.resolve_timeline_paths(doc,editor.context()['path']))
        # The normal generic action replaces the LUT UUID and can update the
        # verified feature root. Preserve the cube and all unrelated content.
        return (_cube_path(editor,node)==_cube_path(editor,before) and
                v02.fingerprint(_without_selected_lut(doc,segment_id))==before_protected)
    return v02.transaction(editor,'native-lut-strength',change,accepted)
