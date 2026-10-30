"""Strict native curve-preset adjustment track, retaining every saved node.

The returned projection is exclusively for checking the older per-video VFX
contract. Rendering, source snapshots and rebasing always use the full timeline.
"""
from copy import deepcopy
from pathlib import Path
import math
import re

import native_color as color

INACTIVE_TYPES={'smart_color_adjust','color_match','color_correct'}


def require(value,message):
    if not value:raise ValueError(message)


def project(timeline,resolve_resource=None):
    tracks=[t for t in timeline.get('tracks',[]) if t.get('type')=='adjust']
    if not tracks:return {'tracks':0,'materials':0,'packages':[]},timeline
    require(len(tracks)==1 and len(tracks[0].get('segments',[]))==1,
            'Only one independently imported curve-preset adjustment segment is reviewed')
    materials=timeline.get('materials',{})
    rows=[(bucket,n) for bucket,nodes in materials.items() for n in nodes]
    ids=[n.get('id') for _,n in rows if n.get('id')]
    require(len(ids)==len(set(ids)),'Native material IDs must be globally unique')
    index={n['id']:(bucket,n) for bucket,n in rows if n.get('id')}
    track=tracks[0];segment=track['segments'][0]
    require(set(track)<={'id','type','segments','is_default_name','name'} and
            set(segment)<={'id','target_timerange','render_timerange','material_id','extra_material_refs',
                'enable_lut','enable_adjust','enable_hsl','enable_hsl_curves','enable_color_curves',
                'enable_smart_color_adjust','enable_color_match_adjust','enable_color_correct_adjust',
                'track_render_index','responsive_layout','source'},'Unreviewed adjustment track/segment fields')
    span=segment.get('target_timerange',{})
    require(set(span)<={'start','duration'} and type(span.get('start',0)) is int and span.get('start',0)>=0 and
            type(span.get('duration')) is int and span['duration']>0 and
            span.get('start',0)+span['duration']<=timeline['duration'], 'Invalid adjustment target range')
    require(not segment.get('render_timerange') and not segment.get('responsive_layout') and
            segment.get('source')=='segmentsourcenormal' and type(segment.get('track_render_index')) is int,
            'Unreviewed adjustment segment mode')
    require(all(segment.get(k,False) is False for k in ('enable_lut','enable_adjust',
                'enable_hsl_curves','enable_smart_color_adjust','enable_color_match_adjust','enable_color_correct_adjust')) and
            segment.get('enable_color_curves',True) is True,
            'Only complete curves and neutral wheels are reviewed on the native adjustment track')
    primary=segment.get('material_id');refs=segment.get('extra_material_refs',[])
    require(isinstance(refs,list) and len(refs) in (7,8) and len(set(refs))==len(refs) and primary not in refs and
            all(ref in index for ref in [primary,*refs]),'Invalid native curve-preset material references')
    bucket,placeholder=index[primary]
    require(bucket=='placeholders' and set(placeholder)=={'id','name','type'} and
            placeholder['type']=='adjust' and isinstance(placeholder['name'],str) and placeholder['name'],
            'Adjustment track must bind its normal native placeholder')
    owned={primary,*refs}
    for identity in owned:
        owners=[s for t in timeline['tracks'] for s in t.get('segments',[]) if
                identity==s.get('material_id') or identity in s.get('extra_material_refs',[])]
        require(len(owners)==1 and owners[0] is segment,'Adjustment materials must not alias another segment')
    require({n['id'] for n in materials.get('placeholders',[])}=={primary},'Unreviewed placeholder material')
    grouped={}
    for identity in refs:
        bucket,node=index[identity];grouped.setdefault(bucket,[]).append(node)
    layout={k:len(v) for k,v in grouped.items()}
    expected={'color_curves':1,'hsl_curves':1,'primary_color_wheels':1,'log_color_wheels':1,'effects':3}
    if 'hsl' in grouped:expected['hsl']=1
    require(layout==expected,'Unexpected native curve-preset node layout')
    if 'hsl' in grouped:
        hsl=grouped['hsl'][0]
        require(set(hsl)<={'id','constant_material_id','hsl_color_type','interacting','version','path','type',
                    'lumi_hub_path','custom_color','resource_id','hue','saturation','lightness'} and
                hsl.get('type')=='hsl' and hsl.get('hsl_color_type')==1 and hsl.get('interacting') is True and
                hsl.get('version')=='1' and hsl.get('custom_color')=='#FFE64444' and hsl.get('resource_id')=='' and
                isinstance(hsl.get('constant_material_id'),str) and hsl['constant_material_id'] and
                all(type(hsl.get(k,0)) is int and hsl.get(k,0)==0 for k in ('hue','saturation','lightness')) and
                segment.get('enable_hsl',True) is True,
                'Only complete curves and the exact neutral native HSL initialization are reviewed')
    else:
        require(segment.get('enable_hsl',False) is False,
                'Only complete curves are reviewed without a neutral HSL initialization')
    common={'id','type','panel','resource_id','path','lumi_hub_path'}
    curves=grouped['color_curves'][0]
    require(set(curves)<=common|{'luma','red','green','blue'} and curves.get('type')=='color_curves' and
            curves.get('panel')=='curve-hsl' and curves.get('resource_id')=='7040008114145333791',
            'Unreviewed native adjustment curve material')
    for channel in ('luma','red','green','blue'):color.points(curves.get(channel))
    hsl=grouped['hsl_curves'][0]
    require(set(hsl)<=common and hsl.get('type')=='' and hsl.get('panel')=='curve-hsl' and
            hsl.get('resource_id')=='7040008114145333791','Unreviewed disabled HSL curve placeholder')
    for mode,rid in [('primary','7062543820910498341'),('log','7062543643705348622')]:
        bucket=mode+'_color_wheels';node=grouped[bucket][0];groups=color.WHEEL_GROUPS[mode]
        require(set(node)<=common|set(groups)|{'intensity'} and node.get('type')==bucket and
                node.get('panel')=='curve-hsl' and node.get('resource_id')==rid and node.get('intensity',1)==1,
                'Unreviewed neutral native adjustment wheels')
        for group in groups:
            values=node.get(group,{})
            require(isinstance(values,dict) and set(values)<=set(color.WHEEL_COMPONENTS) and
                    all(type(v) in (int,float) and math.isfinite(v) and v==0 for v in values.values()),
                    'Native curve-only preset contains nonneutral color wheels')
    effects=grouped['effects']
    require({n.get('type') for n in effects}==INACTIVE_TYPES,'Unexpected disabled native preset effects')
    for node in effects:
        require(set(node)<=common|{'sub_type','value','version','color_match_info','multi_language_current',
                                  'beauty_face_auto_retouch_info'} and not node.get('panel') and
                node.get('resource_id')=='' and node.get('sub_type')=='none' and node.get('value')==.8 and
                node.get('version')=='v3' and not node.get('multi_language_current') and
                not node.get('beauty_face_auto_retouch_info'),'Unreviewed inactive preset effect fields')
        info=node.get('color_match_info',{})
        if node['type']=='color_match':
            require(isinstance(info,dict) and set(info)<={'source_feature_path'} and
                    (not info or re.fullmatch(r'##_draftpath_placeholder_[0-9A-Fa-f-]{36}_##/color_match/color_match_source_feature_[0-9]+\.match',info['source_feature_path'])),
                    'Unreviewed disabled native color-match reference')
        else:require(info=={},'Inactive native preset effect has unexpected algorithm data')
    root=Path(curves['path'])
    require(all(Path(n.get('path',''))==root and Path(n.get('lumi_hub_path',''))==root/'lumi_hub_path'
                for nodes in grouped.values() for n in nodes),'Adjustment resources do not share one complete collection')
    checked=deepcopy(curves)
    if resolve_resource:
        color.rebase_node(checked,resolve_resource(root))
    actual=color.resource_root(checked)
    entry=color.entry_for_node('color_curves',checked);color.verify_resource(actual,entry)
    require(entry['key']=='color/native-collection-7416258989467374091',
            'Native curve-preset adjustment requires an exact reviewed native collection')
    value=deepcopy(timeline)
    value['tracks']=[t for t in value['tracks'] if t.get('type')!='adjust']
    for bucket,nodes in value['materials'].items():
        value['materials'][bucket]=[n for n in nodes if n.get('id') not in owned]
    return {'tracks':1,'materials':len(refs),'packages':[entry['key']],
            'resource_tree_sha256':entry['tree_sha256'], 'inactive_nodes_retained_in_render':True,
            'scope':'one native imported curve-only adjustment segment; full four-channel geometry; neutral wheels; inactive automatic effects'},value


def inactive_feature_markers(timeline,draft_root,resolve_resource=None):
    """Retain only the native unmaterialized marker of a disabled match node.

    No file is fabricated or removed. Materialized dependencies and every other
    path still require the ordinary exact-byte staging policy.
    """
    import jy14_headless as j
    result,projection=project(timeline,resolve_resource)
    if not result['tracks']:return {}
    root=Path(draft_root).resolve();markers={}
    remaining={n['id'] for n in projection['materials'].get('effects',[])}
    for node in timeline['materials'].get('effects',[]):
        if node['id'] in remaining or node.get('type')!='color_match':continue
        value=node.get('color_match_info',{}).get('source_feature_path')
        if not value:continue
        require(value.startswith(j.DRAFT_PATH_TOKEN),'Unknown native inactive color-match marker')
        path=j.native_media_path(value,root)
        require(path.is_relative_to(root) and not path.exists(),
                'Materialized color-match features require their own verified dependency stager')
        markers[node['id']]=value
    return markers
