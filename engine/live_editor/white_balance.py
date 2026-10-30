"""Normal bound native temperature/tint sliders; no cached property writes."""
from copy import deepcopy
from pathlib import Path
import math,struct
from . import v02
from .color import prepare_controls,_qstring
from .errors import require
from .winprocess import Reader

KINDS={'temperature':(30,'temperature'),'tint':(31,'tone')}

def material(doc,segment_id,kind):
    track,segment=v02.segments(doc)[segment_id]
    require(track['type']=='video','WHITE_BALANCE_REQUIRES_VIDEO','Select video')
    nodes=[n for n in doc['materials'].get('effects',[]) if n.get('type')==KINDS[kind][1]
           and n['id'] in segment.get('extra_material_refs',[])]
    require(len(nodes)==1,'WHITE_BALANCE_NOT_BOUND','Initialize this native grade parameter in the plan')
    return nodes[0]

def prepare(editor,segment_id):
    token=editor.context()['token'];handle,metadata=prepare_controls(editor,segment_id,load_resources=True)
    editor.invoke_typed(handle,'onCurTabChanged',[('QString','base'),('QString','基础')])
    base=editor.process['modules']['VECreator.dll']['base'];doc=editor.saved()['timeline']
    controls={};items={}
    with Reader(editor.process['pid']) as reader:
        data,count=struct.unpack('<Qq',reader.read(handle+0x60,16))
        require(data and 2<=count<=16,'WHITE_BALANCE_LIST_INVALID','Native white-balance list is unavailable')
        for index in range(count):
            item=reader.pointer(data+index*8)
            require(item and reader.pointer(item)==base+0xb4a3ed8,
                    'WHITE_BALANCE_SLIDER_INVALID','Unknown native adjustment slider')
            private=reader.pointer(item+8)
            require(private and reader.pointer(private+8)==item,'WHITE_BALANCE_SLIDER_EXPIRED','Slider expired')
            kind=struct.unpack('<i',reader.read(item+0x9c,4))[0]
            names=[name for name,(native,_) in KINDS.items() if kind==native]
            if not names:continue
            name=names[0]
            require(name not in controls,'WHITE_BALANCE_DUPLICATED','Repeated native parameter kind')
            saved=material(doc,segment_id,name)
            ui,lo_s,hi_s,lo,hi=struct.unpack('<ddddd',reader.read(item+0x60,40))
            lo_n,hi_n=struct.unpack('<dd',reader.read(item+0xa0,16))
            require(all(math.isfinite(x) for x in (ui,lo_s,hi_s,lo,hi,lo_n,hi_n)) and hi>lo and hi_n>lo_n,
                    'WHITE_BALANCE_RANGE_INVALID','Invalid live parameter range')
            native=lo_n+(ui-lo)/(hi-lo)*(hi_n-lo_n)
            controls[name]={'kind':kind,'text':_qstring(reader,item+0x10),
                'property_type':_qstring(reader,item+0x28),'ui_value':ui,'native_value':native,
                'min_edit_ui':lo,'max_edit_ui':hi,'min_native':lo_n,'max_native':hi_n,
                'enabled':bool(reader.read(item+0x58,1)[0]),'mixed':bool(reader.read(item+0x5a,1)[0]),
                'persisted_value':saved.get('value',0),
                'matches_saved_value':math.isclose(native,saved.get('value',0),abs_tol=1e-6)}
            items[name]=item
    require(set(controls)==set(KINDS),'WHITE_BALANCE_MISSING','Native temperature/tint pair not found')
    require(editor.context()['token']==token,'SESSION_CHANGED','Draft changed while binding white balance')
    return handle,items,dict(metadata,white_balance=controls)

def adjust(editor,segment_id,kind,value):
    import native_color
    from .lut import _require_native_edit_mode
    require(kind in KINDS and type(value) in (int,float) and math.isfinite(value) and -1<=value<=1,
            'WHITE_BALANCE_VALUE_INVALID','Use temperature/tint and native -1..1')
    old=editor.saved()['timeline'];before=deepcopy(material(old,segment_id,kind))
    native_color.validate(native_color.resolve_timeline_paths(old,editor.context()['path']))
    _require_native_edit_mode(old,segment_id)
    resolved=native_color.resolve_timeline_paths(old,editor.context()['path'])
    refs=v02.segments(resolved)[segment_id][1].get('extra_material_refs',[])
    for node in resolved['materials'].get('effects',[]):
        if node.get('type')=='lut' and node['id'] in refs:
            require(Path(node['path'].split(';')[1])==native_color.resource_root(node),
                    'WHITE_BALANCE_LUT_MIGRATION_PENDING',
                    'Native white balance would also migrate LUT resources; validate a deliberate LUT adjustment first')
    require(not math.isclose(before.get('value',0),value,abs_tol=1e-6),'WHITE_BALANCE_UNCHANGED','Value already matches')
    def protected(doc):
        copy=deepcopy(doc);node=material(copy,segment_id,kind)
        copy['materials']['effects']=[n for n in copy['materials']['effects'] if n['id']!=node['id']]
        segment=v02.segments(copy)[segment_id][1]
        segment['extra_material_refs']=[x for x in segment['extra_material_refs'] if x!=node['id']]
        return v02.fingerprint(copy)
    protected_before=protected(old)
    def change(report,doc):
        require(material(doc,segment_id,kind)==before,'REVISION_CHANGED','White balance changed before editing')
        handle,items,metadata=prepare(editor,segment_id);c=metadata['white_balance'][kind]
        require(c['enabled'] and not c['mixed'] and c['matches_saved_value'],
                'WHITE_BALANCE_CONTROL_DISABLED','Native control is not enabled and bound to saved value')
        require(c['min_native']<=value<=c['max_native'],'WHITE_BALANCE_RANGE_INVALID','Value outside native range')
        editor.invoke_typed(handle,'acceptHslColorType',[('int',1),('QString','#FFE64444')])
        ui=c['min_edit_ui']+(value-c['min_native'])/(c['max_native']-c['min_native'])*(c['max_edit_ui']-c['min_edit_ui'])
        editor.invoke_typed(handle,'onValueChanged',[
            ('QQuickItem*',items[kind],'ParamSettingSliderData*'),('double',ui),('bool',False),('bool',True)])
        editor.refresh()
    def accepted(doc):
        node=material(doc,segment_id,kind)
        if not math.isclose(node.get('value',0),value,abs_tol=1e-6):return False
        native_color.validate(native_color.resolve_timeline_paths(doc,editor.context()['path']))
        return protected(doc)==protected_before
    return v02.transaction(editor,'native-white-balance-'+kind,change,accepted)
