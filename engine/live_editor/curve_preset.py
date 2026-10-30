"""Use the application's genuine personal curve preset and normal import service.

Fixed 11.4.7 layouts are read-only identity guards. All UI initialization and
the single import use existing ordinary Qt methods through the unchanged bridge.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import os
import struct
import time

from . import v02
from .errors import require
from .winprocess import Reader
from .color_preset import owner_thread

CHANNELS=('luma','red','green','blue')


def source(path):
    import native_color
    path=Path(path)
    root=Path(os.environ['LOCALAPPDATA'])/'JianyingPro/User Data/Presets/Adjust'
    require(path.is_absolute() and path.parent==root and path.suffix=='.json' and
            path.is_file() and not path.is_symlink() and path.stat().st_size<=262144,
            'PRESET_SOURCE_INVALID','Select an existing local personal preset JSON')
    raw=path.read_bytes();value=json.loads(raw)
    require(value.get('version')==3 and value.get('name')==path.stem,
            'PRESET_SOURCE_INVALID','Preset version/name does not match its native file')
    curves=value.get('color_curves',{})
    require(curves.get('enable') is True and set(curves)==set(CHANNELS)|{'enable'},
            'PRESET_SOURCE_INVALID','Expected a complete enabled four-channel curve preset')
    for channel in CHANNELS:native_color.points(curves[channel])
    # This new entry is specifically for a curve-only application. Other grade
    # algorithms retain their independently verified public entry points.
    for name in ('adjust','hsl','hsl_curves','filter','color_match','color_correct','smart_color_adjust'):
        require(value.get(name,{}).get('enable') is False,'PRESET_NOT_CURVE_ONLY',
                'Other preset adjustment sections must be disabled')
    for mode,groups in [('primary',('lift','gamma','gain','offset')),
                        ('log',('shadow','midtone','highlight','offset'))]:
        wheels=value.get(mode+'_color_wheels',{})
        require(all(v==0 for g in groups for v in wheels.get(g,{}).values()),
                'PRESET_NOT_CURVE_ONLY','Color wheels must be neutral in a curve-only preset')
    return path,raw,value


def _parent(r,obj):
    private=r.pointer(obj+8)
    require(private and r.pointer(private+8)==obj,'PRESET_OWNER_INVALID','Expected a live QObject')
    return r.pointer(private+0x10)


def _inside(r,obj,root):
    seen=set()
    while obj and obj not in seen and len(seen)<128:
        if obj==root:return True
        seen.add(obj);obj=_parent(r,obj)
    return False


def _thread(r,obj):
    _parent(r,obj)
    data=r.pointer(r.pointer(obj+8)+0x58)
    require(data,'PRESET_OWNER_INVALID','QObject thread data is absent')
    return r.pointer(data+0x58)


def _qpointer(r,obj,offset):
    control,value=struct.unpack('<QQ',r.read(obj+offset,16))
    require(control and value and struct.unpack('<i',r.read(control+4,4))[0]!=0,
            'PRESET_OWNER_INVALID','Native QPointer is no longer alive')
    return value


def _shared(r,obj,offset):
    value,control=struct.unpack('<QQ',r.read(obj+offset,16))
    require(value and control and struct.unpack('<i',r.read(control+8,4))[0]>0,
            'PRESET_OWNER_INVALID','Native shared owner is no longer alive')
    return value


def _vector(r,address,stride,limit=256):
    begin,end,capacity=struct.unpack('<QQQ',r.read(address,24))
    require(begin<=end<=capacity and (end-begin)%stride==0 and
            (end-begin)//stride<=limit,'PRESET_MODEL_INVALID','Invalid native preset vector')
    return [begin+i*stride for i in range((end-begin)//stride)]


def _string(r,address):
    count,capacity=struct.unpack('<QQ',r.read(address+16,16))
    require(0<=count<=1024 and capacity>=count,'PRESET_MODEL_INVALID','Invalid native preset name')
    return r.read(address if capacity<16 else r.pointer(address),count).decode('utf-8')


def _root(r,ds,base):
    creator=r.pointer(ds+0x18)
    require(r.pointer(creator)==base+0xb489bf8,'PRESET_OWNER_INVALID','Unexpected component creator')
    data=r.pointer(creator+0x10);header=r.pointer(data+8);stack=[r.pointer(header+8)]
    seen=set();roots=[]
    while stack:
        node=stack.pop()
        if not node or node==header:continue
        require(node not in seen and len(seen)<128,'PRESET_OWNER_INVALID','Invalid component cache')
        seen.add(node)
        if r.read(node+0x19,1)!=b'\0':continue
        if struct.unpack('<i',r.read(node+0x20,4))[0]==8:roots.append(_qpointer(r,node,0x28))
        stack.extend([r.pointer(node),r.pointer(node+0x10)])
    require(len(roots)<=1,'PRESET_OWNER_INVALID','Ambiguous adjustment root')
    return roots[0] if roots else None


def prepare(editor,path):
    path,raw,value=source(path)
    before=deepcopy(editor.saved()['timeline']);ctx=editor.context()
    base=editor.process['modules']['VECreator.dll']['base']
    tabs=[]
    with Reader(editor.process['pid']) as r:
        for obj in v02.objects(editor,'main_tab'):
            _parent(r,obj);ds=r.pointer(obj+0x10)
            if ds and (r.pointer(ds)-base,r.pointer(ds+0x10)-base) in {
                    (0xb456208,0xb456280),(0xb4563f8,0xb456470)}:
                data,count=struct.unpack('<Qq',r.read(ds+0x48,16))
                require(0<count<64,'PRESET_OWNER_INVALID','Invalid material tab types')
                if 8 in struct.unpack('<'+'i'*count,r.read(data,count*4)):tabs.append((obj,ds))
    require(len(tabs)==1,'PRESET_LIBRARY_NOT_BOUND','Expected one current material library')
    tab,ds=tabs[0]
    editor.invoke_typed(tab,'gotoTab',[('int',8,'MainTabEnum::Type')],ctx=ctx)
    deadline=time.monotonic()+15
    while True:
        editor.refresh()
        with Reader(editor.process['pid']) as r:
            root=_root(r,ds,base)
            panels=[o for o in v02.objects(editor,'personal_adjust_panel') if root and
                    _parent(r,o)==root and struct.unpack('<i',r.read(o+0x10,4))[0]==1]
            trees=[o for o in v02.objects(editor,'adjust_tree') if root and _inside(r,o,root)]
        if len(panels)==len(trees)==1:break
        require(time.monotonic()<deadline,'PRESET_LIBRARY_NOT_BOUND','Native personal preset library did not initialize')
        time.sleep(.2)
    tree=trees[0];panel=panels[0]
    require(editor.invoke_typed(tree,'isExistParentItem',[('QString','my_adjust')],return_type=1) and
            editor.invoke_typed(tree,'isExistChildItem',[('QString','my_adjust'),('QString','my_default')],return_type=1),
            'PRESET_LIBRARY_NOT_BOUND','Normal personal preset category is unavailable')
    editor.invoke_typed(tree,'selectItemByCatgory',[
        ('QString','my_adjust'),('QString','my_default'),('bool',True)],ctx=ctx)
    owner_thread(editor)
    deadline=time.monotonic()+15
    while True:
        editor.refresh();found=[]
        with Reader(editor.process['pid']) as r:
            require(r.birth()==editor.process['birth'],'PROCESS_CHANGED','Editor process changed')
            application=r.pointer(editor.process['modules']['Qt6Core.dll']['base']+0x4d7580)
            main_thread=_thread(r,application)
            require(main_thread and all(_thread(r,o)==main_thread for o in (tab,root,panel,tree)),
                    'PRESET_OWNER_INVALID','Preset library is not on the application thread')
            collection=_qpointer(r,panel,0x18);provider=_qpointer(r,collection,0x30)
            require(r.pointer(collection)==base+0xb439e98 and r.pointer(provider)==base+0xb4746b8,
                    'PRESET_OWNER_INVALID','Unexpected native preset collection/provider')
            models={_shared(r,p,0) for p in _vector(r,provider+0x88,16)}
            manager=base+0xef3aec0;dtos=set()
            for p in _vector(r,manager+0x18,16):
                item=_shared(r,p,0)
                if struct.unpack('<i',r.read(item,4))[0]==1:dtos.add(_shared(r,item,8))
            for obj in v02.objects(editor,'personal_adjust_item'):
                model=_shared(r,obj,0x70)
                if model not in models:continue
                dto=_shared(r,model,0xb8)
                if dto not in dtos or _string(r,dto+0x28)!=value['name']:continue
                require(struct.unpack('<i',r.read(dto+0x68,4))[0]==3 and r.read(dto+0xe0,1)==b'\1',
                        'PRESET_SOURCE_MISMATCH','Loaded native preset version/curve enable differs')
                require(all(r.read(obj+a,16)==r.read(provider+b,16) for a,b in
                            [(0x90,0x40),(0x80,0x60),(0xa0,0x50)]),
                        'PRESET_OWNER_INVALID','Preset delegate is bound to other services')
                for offset in (0x80,0x90,0xa0):_shared(r,obj,offset)
                require(_thread(r,obj)==main_thread and r.pointer(r.pointer(obj+0x90))==base+0xb473f48,
                        'PRESET_OWNER_INVALID','Preset import service/thread is not the current normal owner')
                for channel,offset in zip(CHANNELS,(0xe8,0x100,0x118,0x130)):
                    points=[]
                    for point in _vector(r,dto+offset,0xd0,32):
                        points.append({kind:dict(zip(('x','y'),struct.unpack('<dd',r.read(point+field,16))))
                                       for kind,field in [('anchor',0x50),('left_control',0x88),('right_control',0xc0)]})
                    require(points==value['color_curves'][channel],'PRESET_SOURCE_MISMATCH',
                            'Loaded native curve points differ from the source file')
                require(editor.get(obj,'name')==value['name'],
                        'PRESET_OWNER_INVALID','Preset delegate name is not current')
                found.append(obj)
        require(len(found)<=1,'PRESET_LIBRARY_NOT_BOUND','Duplicate source1 native preset')
        if found:break
        require(time.monotonic()<deadline,'PRESET_NOT_LOADED',
                'Preset is not loaded by the normal application lifecycle; do not forge or replay it')
        time.sleep(.2)
    require(path.read_bytes()==raw,'PRESET_SOURCE_CHANGED','Preset source changed while binding')
    require(editor.context()['token']==ctx['token'] and
            v02.fingerprint(editor.saved()['timeline'])==v02.fingerprint(before),
            'REVISION_CHANGED','Timeline changed during library initialization')
    return found[0],dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest(),name=value['name'],
                         version=3,four_channel_points_verified=True,normal_native_services_bound=True,
                         computer_use=False),value


def has_curves(doc,curves):
    if isinstance(doc,dict):
        if all(channel in doc and isinstance(doc[channel],list) and
               all(isinstance(p,dict) for p in doc[channel]) and
               [{key:p.get(key) for key in ('anchor','left_control','right_control')} for p in doc[channel]]==curves[channel]
               for channel in CHANNELS):return True
        return any(has_curves(v,curves) for v in doc.values())
    if isinstance(doc,list):return any(has_curves(v,curves) for v in doc)
    return False


def apply(editor,segment_id,path):
    before=deepcopy(editor.saved()['timeline'])
    require(v02.segments(before)[segment_id][0]['type']=='video','PRESET_REQUIRES_VIDEO','Select a real video segment')
    obj=v02.clip_object(editor,'video',segment_id);v02.select(editor,obj)
    item,metadata,value=prepare(editor,path);curves=value['color_curves']
    require(not has_curves(before,curves),'PRESET_UNCHANGED','Requested complete curve geometry already exists')
    def change(report,doc):
        require(v02.fingerprint(doc)==v02.fingerprint(before),'REVISION_CHANGED','Timeline changed before preset import')
        current,checked,_=prepare(editor,path)
        require(current==item and checked==metadata,'PRESET_OWNER_INVALID','Preset binding changed before import')
        editor.invoke_typed(current,'importClicked',[])
    result,doc,oid=v02.transaction(editor,'native-complete-curve-preset-import',change,
                                   lambda d:has_curves(d,curves) and v02.fingerprint(d)!=v02.fingerprint(before))
    result['curve_preset_import']={**metadata,'saved_curve_geometry_verified':True,
                                  'render_verified_by_this_command':False}
    return result,doc,oid
