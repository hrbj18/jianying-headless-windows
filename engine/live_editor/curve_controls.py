"""Normal curve checkbox/reset actions on a genuine adjustment inspector."""
from copy import deepcopy
import math
import struct

from . import v02
from .color import prepare_adjust_controls
from .errors import require
from .winprocess import Reader


def curve_node(doc,segment_id):
    track,segment=v02.segments(doc)[segment_id]
    require(track['type']=='adjust','CURVES_REQUIRE_ADJUSTMENT','This entry edits an imported native adjustment segment')
    nodes=[n for n in doc['materials'].get('color_curves',[]) if n['id'] in segment.get('extra_material_refs',[])]
    require(len(nodes)==1,'CURVES_NOT_BOUND','Expected one complete bound native color curve')
    return nodes[0]


def _state(editor,handle):
    base=editor.process['modules']['VECreator.dll']['base']
    with Reader(editor.process['pid']) as r:
        require(r.birth()==editor.process['birth'] and r.pointer(handle)==base+0xbfef5b0 and
                r.pointer(handle+0x10)==base+0xbfef610,'CURVES_OWNER_CHANGED','Native curve handler changed')
        return struct.unpack('<i',r.read(handle+0xe4,4))[0]


def enable(editor,segment_id,enabled):
    require(type(enabled) is bool,'INVALID_CURVE_ENABLE','Expected a boolean curve checkbox value')
    before=deepcopy(editor.saved()['timeline']);old=curve_node(before,segment_id)
    handle,controls=prepare_adjust_controls(editor,segment_id)
    require(controls['curve_controls_visible'],'CURVES_NOT_VISIBLE','Normal native curve panel is not ready')
    require(controls['color_curves_checked']!=enabled,'CURVES_UNCHANGED','Native checkbox already matches')
    def change(report,doc):
        require(v02.fingerprint(doc)==v02.fingerprint(before),'REVISION_CHANGED','Timeline changed before checkbox action')
        editor.invoke_typed(handle,'setColorCurvesEnable',[('bool',enabled)])
    def accepted(doc):
        _,segment=v02.segments(doc)[segment_id]
        return segment.get('enable_color_curves',True) is enabled and _state(editor,handle)==(0 if enabled else 1)
    result,doc,oid=v02.transaction(editor,'native-curve-checkbox',change,accepted)
    require(all(curve_node(doc,segment_id)[c]==old[c] for c in ('luma','red','green','blue')),
            'CURVE_GEOMETRY_CHANGED','Checkbox action changed native curve geometry; inspect, never replay')
    return result,doc,oid


def identity(node):
    import native_color
    for channel in ('luma','red','green','blue'):
        points=node.get(channel)
        native_color.points(points)
        if not all(math.isclose(point[kind]['x'],point[kind]['y'],rel_tol=0,abs_tol=1e-12)
                   for point in points for kind in ('anchor','left_control','right_control')):return False
    return True


def reset(editor,segment_id):
    before=deepcopy(editor.saved()['timeline']);node=curve_node(before,segment_id)
    require(not identity(node),'CURVES_UNCHANGED','All four native curves are already identity')
    handle,controls=prepare_adjust_controls(editor,segment_id)
    require(controls['can_edit_curves_in_native_ui'],'CURVES_NOT_EDITABLE','Normal native curve controls must be visible and checked')
    def change(report,doc):
        require(v02.fingerprint(doc)==v02.fingerprint(before),'REVISION_CHANGED','Timeline changed before native curve reset')
        editor.invoke_typed(handle,'resetAllColorCurves',[])
    return v02.transaction(editor,'native-all-four-color-curves-reset',change,
                           lambda doc:identity(curve_node(doc,segment_id)) and v02.fingerprint(doc)!=v02.fingerprint(before))
