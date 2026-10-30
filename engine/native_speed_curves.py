"""Bound custom native speed curves, preserving their points and time mapping.

Schema follows the installed CurveSpeed model and real official CLI saved
output, not a substitute sequence of constant-speed cuts. Rendering and GUI
round-trip evidence are independent of these structural checks.
"""
import math
from copy import deepcopy

CUSTOM_ID='6768730851543880206'

def require(value,message):
    if not value:raise ValueError(message)

def finite(value,minimum,maximum,label):
    require(type(value) in (int,float) and math.isfinite(value) and minimum<=value<=maximum,
            'Invalid curve '+label)
    return value

def average(points):
    require(isinstance(points,list) and 2<=len(points)<=128,'Curve needs 2..128 points')
    prior=-1.;total=0.;last=None
    for point in points:
        require(isinstance(point,dict) and set(point)=={'x','y'},'Unknown curve point fields')
        x=finite(point['x'],0,1,'point x');y=finite(point['y'],.1,8,'point y')
        require(x>prior,'Curve point x must be strictly increasing')
        if last is not None:total+=(last['y']+y)*.5*(x-last['x'])
        prior=x;last=point
    require(points[0]['x']==0 and points[-1]['x']==1,'Curve endpoints must cover 0..1')
    return total

def validate_spec(spec,kind):
    if 'speed_curve' not in spec:return None
    curve=spec['speed_curve']
    require(kind=='video' and isinstance(curve,dict) and set(curve)=={'points'},
            'speed_curve requires video and explicit points')
    mean=average(curve['points'])
    require(math.isclose(spec.get('speed',1),mean,abs_tol=1e-6),
            'Planned speed must equal the curve average')
    require(not spec.get('keyframes'),'Curve keyframe time mapping needs separate acceptance')
    return mean

def from_spec(spec):
    return {'id':CUSTOM_ID,'name':'自定义','speed_points':deepcopy(spec['speed_curve']['points'])}

def verify_segment(segment,index,spec,kind):
    bound=[index[ref][1] for ref in segment.get('extra_material_refs',[]) if index[ref][0]=='speeds']
    if 'speed_curve' in spec:
        validate_spec(spec,kind)
        require(len(bound)==1 and bound[0].get('mode')==1 and bound[0].get('curve_speed')==from_spec(spec),
                'Planned native curve points did not round-trip')
    else:
        require(all(not node.get('curve_speed') for node in bound),'Unexpected curve in a constant-speed plan')

def validate(timeline):
    materials=timeline.get('materials',{});curves={}
    for node in materials.get('speeds',[]):
        curve=node.get('curve_speed')
        if not curve:continue
        require(set(node)<= {'id','type','mode','speed','curve_speed'},'Unknown speed material fields')
        require(node.get('type')=='speed' and type(node.get('mode')) is int and node['mode']==1,
                'Custom curve requires speed mode 1')
        require(isinstance(curve,dict) and set(curve)<= {'id','name','source_platform','speed_points'} and
                curve.get('id')==CUSTOM_ID and curve.get('source_platform',0)==0,
                'Unreviewed curve identity or fields')
        require(isinstance(node.get('id'),str) and node['id'] and node['id'] not in curves,
                'Curve material IDs must be unique')
        mean=average(curve.get('speed_points'))
        require(math.isclose(finite(node.get('speed',1),.1,8,'average'),mean,abs_tol=1e-6),
                'Curve average differs from saved speed')
        curves[node['id']]=(node,mean)
    used=set();videos={v.get('id'):v for v in materials.get('videos',[])}
    for track in timeline.get('tracks',[]):
        for segment in track.get('segments',[]):
            require(segment.get('material_id') not in curves,'Curve cannot be a primary material')
            refs=segment.get('extra_material_refs') or [];bound=[ref for ref in refs if ref in curves]
            if not bound:continue
            require(len(bound)==1 and refs.count(bound[0])==1,'Exactly one speed curve must bind a segment')
            material=videos.get(segment.get('material_id'),{})
            require(track.get('type')=='video' and material.get('type')=='video',
                    'Speed curve requires a video segment')
            require(not segment.get('common_keyframes'),'Curve keyframe time mapping needs separate acceptance')
            _,mean=curves[bound[0]]
            require(math.isclose(finite(segment.get('speed',1),.1,8,'segment average'),mean,abs_tol=1e-6),
                    'Segment speed differs from curve average')
            source=segment.get('source_timerange',{});target=segment.get('target_timerange',{})
            require(all(type(v) is int and v>=0 for v in [source.get('start',0),target.get('start',0)]) and
                    type(source.get('duration')) is int and source['duration']>0 and
                    type(target.get('duration')) is int and target['duration']>0,
                    'Invalid curve source or target duration')
            require(abs(source['duration']/mean-target['duration'])<=2,
                    'Curve source/target duration differs from average mapping')
            if material.get('duration') is not None:
                require(source.get('start',0)+source['duration']<=material['duration']+1,
                        'Curve source range exceeds the media')
            used.add(bound[0])
    require(used==set(curves),'Orphan speed curve has no video binding')
    return {'curves':len(curves),'points':sum(len(n['curve_speed']['speed_points']) for n,_ in curves.values()),
            'scope':'native custom curve points; normalized target-time x; 0.1..8x; static clip transforms'}
