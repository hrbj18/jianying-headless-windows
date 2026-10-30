"""Save one genuine native personal grade preset, preserving the whole timeline.

The fixed-version handle owns the selected segment. Its ordinary save() method
collects that segment and uses the application's own filename, writer and list.
No personal preset or current draft file is authored by this command.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import os
import time
import struct

from . import v02
from .color import prepare_controls
from .errors import require
from .winprocess import Reader


def owner_thread(editor, allow_unconstructed=False):
    """Reject an already constructed singleton attached to a dead/other thread."""
    base=editor.process['modules']['VECreator.dll']['base']
    core=editor.process['modules']['Qt6Core.dll']['base']
    manager=base+0xef3aec0
    with Reader(editor.process['pid']) as reader:
        require(reader.birth()==editor.process['birth'],'PROCESS_CHANGED','Editor process changed')
        guard=struct.unpack('<i',reader.read(base+0xef3af58,4))[0]
        vt,private,secondary=struct.unpack('<QQQ',reader.read(manager,24))
        if guard==0 and vt==private==secondary==0:
            require(allow_unconstructed,'PRESET_MANAGER_NOT_INITIALIZED',
                    'Native preset manager has not completed normal construction')
            return 'unconstructed'
        require(guard not in (0,-1) and vt==base+0xcb0a750 and secondary==base+0xcb0a7b0,
                'PRESET_MANAGER_NOT_READY','Native preset manager construction is uncertain')
        application=reader.pointer(core+0x4d7580)
        def thread(obj):
            data=reader.pointer(obj+8)
            require(data and reader.pointer(data+8)==obj,'PRESET_OWNER_INVALID','QObject owner is stale')
            td=reader.pointer(data+0x58)
            require(td,'PRESET_OWNER_INVALID','Native QObject thread data is absent')
            return reader.pointer(td+0x58)
        own,main=thread(manager),thread(application)
        require(reader.read(base+0xef3af58,4)==struct.pack('<i',guard),
                'PRESET_MANAGER_NOT_READY','Native preset manager changed during inspection')
        require(own and own==main,'PRESET_WRONG_OWNER_THREAD',
                'Native preset manager is not on the application thread; use normal saved-app restart, never replay or move it')
    return 'main-thread'


def save(editor, segment_id):
    owner_thread(editor,allow_unconstructed=True)
    root=Path(os.environ['LOCALAPPDATA'])/'JianyingPro/User Data/Presets/Adjust'
    require(root.is_dir() and not root.is_symlink(),'PRESET_ROOT_UNAVAILABLE',
            'Expected the verified fixed-version personal preset directory')
    original={p.name:p.read_bytes() for p in root.glob('*.json')}
    before=deepcopy(editor.saved()['timeline'])
    segment=v02.segments(before)[segment_id][1]
    curves=[n for n in before['materials'].get('color_curves',[])
            if n['id'] in segment.get('extra_material_refs',[])]
    require(len(curves)==1,'PRESET_CURVE_NOT_BOUND',
            'This verification command requires one actual bound complete color curve')
    result={}

    def change(report,doc):
        require(v02.fingerprint(doc)==v02.fingerprint(before),'REVISION_CHANGED',
                'Timeline changed before native grade collection')
        handle,metadata=prepare_controls(editor,segment_id,load_resources=True)
        require(metadata['merge_resource_loaded'],'COLOR_RESOURCE_NOT_READY',
                'Normal native grade resources must be ready before saving a preset')
        owner_thread(editor,allow_unconstructed=True)
        editor.invoke_typed(handle,'save',[])
        owner_thread(editor)
        end=time.monotonic()+30
        while time.monotonic()<end:
            files={p.name:p for p in root.glob('*.json')}
            require(all(name in files and files[name].read_bytes()==data
                        for name,data in original.items() if name!='AdjustPresetCfg.json'),
                    'PRESET_EXISTING_FILE_CHANGED','An existing personal preset changed')
            new=[p for name,p in files.items() if name not in original and name!='AdjustPresetCfg.json']
            require(len(new)<=1,'PRESET_RESULT_AMBIGUOUS','More than one personal preset appeared')
            if new:
                p=new[0]
                try:
                    data=p.read_bytes();preset=json.loads(data)
                except (OSError,ValueError):
                    time.sleep(.2);continue
                require(preset.get('version')==3 and preset.get('name') and
                        p.name==preset['name']+'.json','PRESET_FORMAT_UNEXPECTED',
                        'Saved preset differs from the verified normal version/name format')
                body=preset.get('color_curves',{})
                require(body.get('enable') is True,'PRESET_CURVE_DISABLED',
                        'Native saved preset did not enable the selected color curves')
                for channel in ('luma','red','green','blue'):
                    expected=curves[0][channel];actual=body.get(channel)
                    require(isinstance(actual,list) and len(actual)==len(expected),
                            'PRESET_POINTS_CHANGED','Native preset curve point count differs')
                    for a,b in zip(actual,expected):
                        for part in ('anchor','left_control','right_control'):
                            require(a.get(part)==b[part],'PRESET_POINTS_CHANGED',
                                    'Native preset curve control coordinates differ')
                time.sleep(.5)
                if p.read_bytes()!=data:continue
                result.update(path=str(p),name=preset['name'],version=preset['version'],
                              sha256=hashlib.sha256(data).hexdigest(),
                              curves_coordinates_equal=True,source_segment=segment_id,
                              native_auto_named=True,simulated_input=False,
                              native_owner_thread_verified=True,
                              scope='Native saved sample; arbitrary preset application not yet verified')
                return
            time.sleep(.2)
        require(False,'PRESET_SAVE_UNCERTAIN',
                'Native save was dispatched once but no complete matching preset was confirmed; inspect without replay')

    def accepted(doc):
        return bool(result) and v02.fingerprint(doc)==v02.fingerprint(before)

    after,doc,operation=v02.transaction(editor,'native-color-preset-save',change,accepted)
    after=deepcopy(after);after['preset_export']=result
    return after,doc,operation
