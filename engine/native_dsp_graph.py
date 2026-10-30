"""Original local SAMI graph; processing stays in Jianying's native engine.

The package contains only configuration authored for this project. Processor
indices and mappings are pinned to the reviewed 11.4.7 audioeffect.dll.
"""
import json
import math
from pathlib import Path

RESOURCE_ID = 'local-studio-dsp-v2'
EQ_RESOURCE_ID = 'local-studio-eq-v1'
DYNAMICS_RESOURCE_ID = 'local-studio-dynamics-v1'
VERSION = '14.0.5'


def normalize(kind, value):
    bounds = {'gain': (-20, 20, 1), 'threshold': (-70, 0, .5),
              'ratio': (1, 40, 2.5), 'ceiling': (-24, 0, .75)}
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('DSP controls must be finite numbers')
    if kind == 'frequency':
        if not 20 <= value <= 20000:
            raise ValueError('EQ frequency must be in 20..20000 Hz')
        return math.log(value / 20) / math.log(1000)
    low, high, exponent = bounds[kind]
    if not low <= value <= high:
        raise ValueError('DSP control is outside its native range')
    return ((value - low) / (high - low)) ** (1 / exponent)


CONTROLS = [
    dict(name='EQ增益（-20至20dB）', parameterIndex=4, portIndex=0,
         kind='gain', default_physical=0),
    dict(name='EQ频率（20至20000Hz）', parameterIndex=2, portIndex=0,
         kind='frequency', default_physical=1000),
    dict(name='压缩阈值（-70至0dB）', parameterIndex=2, portIndex=1,
         kind='threshold', default_physical=-18),
    dict(name='压缩比例（1至40）', parameterIndex=1, portIndex=1,
         kind='ratio', default_physical=3),
    dict(name='限制上限（-24至0dB）', parameterIndex=2, portIndex=2,
         kind='ceiling', default_physical=-2),
]
for control in CONTROLS:
    control.update(min_value=0, max_value=1,
                   default_value=normalize(control['kind'], control['default_physical']))


def parameters(values=None):
    values = values or {}
    if set(values) - {item['kind'] for item in CONTROLS}:
        raise ValueError('Unknown studio DSP control')
    return [{**{k: item[k] for k in ('name', 'parameterIndex', 'portIndex',
                                    'min_value', 'max_value', 'default_value')},
             'value': normalize(item['kind'], values.get(item['kind'], item['default_physical']))}
            for item in CONTROLS]


def bundle_files():
    stereo = dict(audio_channels_layout='Stereo', is_active=True)
    def processor(identity, name, params):
        return dict(node_id=identity, node_type='processor_node', processor_name=name,
                    processor_audio_buses_configuration=dict(inputs=[stereo], outputs=[stereo]),
                    processor_state=dict(parameters=params, version=VERSION), version=VERSION)
    eq = {'Gain dB': 0}
    for band in range(1, 9):
        eq.update({f'Filter {band} Bypass': band != 1,
                   f'Filter {band} Mode': 'Bell', f'Filter {band} Freq': 1000,
                   f'Filter {band} Gain dB': 0, f'Filter {band} Q': 1})
    nodes = [
        processor('studio_compressor', 'Compressor', {
            'Bypass': False, 'Ratio': 3, 'Threshold dB': -18,
            'Attack': 10, 'Release': 120, 'Knee dB': 6, 'Lookahead': 0,
            'Auto Makeup Gain': False, 'Output Gain dB': 0,
            'Sidechain Audition': False, 'Sidechain Filter Enabled': False,
            'Sidechain Filter Cutoff Frequency': 1000,
            'Sidechain Filter Mode': 'LowPass', 'Sidechain Filter Resonance': 1,
            'Use External Sidechain': False}),
        processor('studio_equaliser', 'Equaliser', eq),
        processor('studio_limiter', 'Limiter', {
            'Bypass': False, 'Audition Unity Gain': False, 'Input Gain dB': 0,
            'Ceiling dB': -2, 'Lookahead': 7, 'Release': 100}),
    ]
    # Compressor declares a second, inactive sidechain bus even when external
    # sidechain is disabled. Omitting it makes NodeFactory reject the graph.
    nodes[0]['processor_audio_buses_configuration']['inputs'].append(
        dict(audio_channels_layout='Stereo', is_active=False))
    def port(node, direction, kind, index=0):
        return dict(internal_node_id=node, internal_node_port_index=0,
                    port_direction=direction, port_index=index, port_type=kind)
    connections = [dict(upstream_node_id=a, upstream_port_index=0,
                        downstream_node_id=b, downstream_port_index=0, port_type='audio')
                   for a, b in [('studio_compressor', 'studio_equaliser'),
                                ('studio_equaliser', 'studio_limiter')]]
    graph = dict(node_id='studio_graph', node_type='graph_container_node',
                 version=VERSION, nodes=nodes, connections=connections,
                 ports=[port('studio_compressor', 'input', 'audio'),
                        port('studio_limiter', 'output', 'audio'),
                        port('studio_equaliser', 'input', 'parameter_change', 0),
                        port('studio_compressor', 'input', 'parameter_change', 1),
                        port('studio_limiter', 'input', 'parameter_change', 2)])
    extra = {'setting': {'audio_effect_parameters_change': [
        dict(parameterIndex=c['parameterIndex'], portIndex=c['portIndex'], sliderName=c['name'],
             minValue=0, maxValue=1, defaultValue=c['default_value']) for c in CONTROLS]}}
    def encode(value):
        return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    return {'config.json': encode({'effect': {'Link': [{'type': 'SAMIAudioEffect'}]},
                                   'version': '10.5.0'}),
            'extra.json': encode(extra), 'mdsp_preset.json': encode(graph),
            'preset3.yaml': b'- effect: music_dsp_effect\n  chunk:\n    mdsp_preset: mdsp_preset.json\n'}


def write_bundle(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=False)
    for name, data in bundle_files().items():
        (path / name).write_bytes(data)
    return path


def split_controls(part):
    if part=='eq':
        kinds=('gain','frequency');ports={'gain':0,'frequency':0}
    elif part=='dynamics':
        kinds=('threshold','ratio','ceiling');ports={'threshold':0,'ratio':0,'ceiling':1}
    else:raise ValueError('Unknown native audio stage')
    return [dict(c,portIndex=ports[c['kind']]) for c in CONTROLS if c['kind'] in kinds]


def split_parameters(part,values=None):
    values=values or {};controls=split_controls(part)
    if set(values)-{c['kind'] for c in controls}:raise ValueError('Unknown native audio stage control')
    return [{**{k:c[k] for k in ('name','parameterIndex','portIndex','min_value','max_value','default_value')},
             'value':normalize(c['kind'],values.get(c['kind'],c['default_physical']))} for c in controls]


def split_bundle_files(part):
    # Keep each native category within the app's three ordinary refresh slots,
    # while retaining all five physical controls across tone + sound_effect.
    files=bundle_files();graph=json.loads(files['mdsp_preset.json'])
    controls=split_controls(part)
    def port(node,direction,kind,index=0):
        return dict(internal_node_id=node,internal_node_port_index=0,
                    port_direction=direction,port_type=kind,port_index=index)
    if part=='eq':
        graph['nodes']=[n for n in graph['nodes'] if n['node_id']=='studio_equaliser']
        graph['connections']=[]
        graph['ports']=[port('studio_equaliser','input','audio'),port('studio_equaliser','output','audio'),
                        port('studio_equaliser','input','parameter_change')]
    else:
        graph['nodes']=[n for n in graph['nodes'] if n['node_id']!='studio_equaliser']
        graph['connections']=[dict(upstream_node_id='studio_compressor',upstream_port_index=0,
            downstream_node_id='studio_limiter',downstream_port_index=0,port_type='audio')]
        graph['ports']=[port('studio_compressor','input','audio'),port('studio_limiter','output','audio'),
                       port('studio_compressor','input','parameter_change'),
                       port('studio_limiter','input','parameter_change',1)]
    graph['node_id']='studio_'+part+'_graph'
    extra={'setting':{'audio_effect_parameters_change':[dict(parameterIndex=c['parameterIndex'],
        portIndex=c['portIndex'],sliderName=c['name'],minValue=0,maxValue=1,defaultValue=c['default_value']) for c in controls]}}
    for name,value in [('mdsp_preset.json',graph),('extra.json',extra)]:
        files[name]=(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    return files


def write_split_bundle(path,part):
    path=Path(path);path.mkdir(parents=True,exist_ok=False)
    for name,data in split_bundle_files(part).items():(path/name).write_bytes(data)
    return path
