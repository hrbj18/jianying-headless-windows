"""Current native audio-base checkbox, preserving its normal entitlement path.

The shipped GUI exposes a bool, not a rate slider. A toggle may replace the
SDK's mode/rate with native mode 1/global defaults; never hide that migration.
"""
from copy import deepcopy
import struct
import time
import native_audio_processing as audio
from . import v02
from .color import _qstring, _stdstring
from .errors import require
from .winprocess import Reader


def material(doc, segment_id):
    track, segment = v02.segments(doc)[segment_id]
    require(track['type'] == 'audio', 'DENOISE_REQUIRES_AUDIO', 'Select independent audio')
    nodes = [n for n in doc['materials'].get('realtime_denoises', [])
             if n['id'] in segment.get('extra_material_refs', [])]
    require(len(nodes) == 1, 'DENOISE_NOT_BOUND', 'Initialize one reviewed denoise material first')
    return nodes[0]


def prepare_controls(editor, segment_id):
    doc = editor.saved()['timeline']; audio.validate(doc)
    node = material(doc, segment_id)
    token = editor.context()['token']
    clip = v02.clip_object(editor, 'audio', segment_id)
    v02.select(editor, clip); editor.refresh()
    base = editor.process['modules']['VECreator.dll']['base']
    roots = []
    with Reader(editor.process['pid']) as r:
        for root in v02.objects(editor, 'audio_inspector'):
            private = r.pointer(root + 8)
            if not private or r.pointer(private + 8) != root: continue
            control = r.pointer(root + 0x38)
            if not control or r.pointer(control) != base + 0xbfbe988: continue
            tabs = r.pointer(control + 0x18)
            if not tabs: continue
            begin, end, cap = struct.unpack('<QQQ', r.read(tabs + 0x28, 24))
            require(begin <= end <= cap and (end-begin) % 16 == 0 and 0 < end-begin <= 512,
                    'DENOISE_TABS_INVALID', 'Invalid current audio tab vector')
            names = [_qstring(r, r.pointer(begin + 16*i) + 0x58)
                     for i in range((end-begin)//16)]
            if names.count('audio_basic') == 1:
                roots.append((root, names.index('audio_basic')))
    require(len(roots) == 1, 'DENOISE_INSPECTOR_NOT_BOUND', 'Expected one current audio inspector')
    root, index = roots[0]
    editor.invoke_typed(root, 'switchTab', [('int', index)])
    deadline = time.monotonic() + 15; matches = []
    while time.monotonic() < deadline:
        editor.refresh(); matches = []
        with Reader(editor.process['pid']) as r:
            require(r.birth() == editor.process['birth'], 'PROCESS_CHANGED', 'Editor process changed')
            model, shared = r.pointer(root + 0x50), r.pointer(root + 0x58)
            if model and shared:
                begin, end, _ = struct.unpack('<QQQ', r.read(model + 0x50, 24))
                selected = end-begin == 32 and _stdstring(r, begin) == segment_id
                wrapper, owner = r.pointer(model + 0xa8), r.pointer(model + 0xb0)
                if selected and wrapper and owner and r.pointer(wrapper) == base + 0xbf8cee8:
                    begin, end, _ = struct.unpack('<QQQ', r.read(wrapper + 8, 24))
                    selected = end-begin == 32 and _stdstring(r, begin) == segment_id
                    for page in v02.objects(editor, 'audio_base_page') if selected else []:
                        private = r.pointer(page + 8)
                        if not private or r.pointer(private + 8) != page: continue
                        if r.pointer(page + 0x10) != model or r.pointer(page + 0x18) != shared: continue
                        handler = r.pointer(page + 0x20)
                        if (not handler or r.pointer(handler) != base + 0xbf94378 or
                            r.pointer(handler + 0x38) != base + 0xbf946d0 or
                            r.pointer(handler + 0x1f8) != base + 0xbf946f8 or
                            r.pointer(handler + 0x388) != wrapper or
                            r.pointer(handler + 0x390) != owner): continue
                        private = r.pointer(handler + 8)
                        if private and r.pointer(private + 8) == handler: matches.append(handler)
        require(len(matches) <= 1, 'DENOISE_CONTROLS_AMBIGUOUS', 'Multiple current denoise owners')
        if matches: break
        time.sleep(.25)
    require(len(matches) == 1, 'DENOISE_CONTROLS_NOT_BOUND', 'Current audio base page is not bound')
    handler = matches[0]
    enabled = bool(editor.get(handler, 'denoiseSwitch'))
    available = bool(editor.get(handler, 'denoiseSwitchEnabled'))
    mixed = editor.invoke(handler, 'isDenoiseSwitchMixed', 1)
    require(editor.context()['token'] == token and editor.get(clip, 'selected'),
            'SESSION_CHANGED', 'Selected audio changed during denoise initialization')
    return handler, dict(segment_id=segment_id, enabled=enabled, available=available, mixed=mixed,
        matches_saved_value=enabled == node.get('is_denoise',False), material=deepcopy(node),
        effective_native_settings=dict(enabled=node.get('is_denoise',False),
            mode=node.get('denoise_mode',1),rate=node.get('denoise_rate',1)),
        route='DraftInspectorAudioBaseViewModel.SoundEditSettingHandler',
        rate_control=False, simulated_input=False)


def toggle(editor, segment_id, enabled):
    require(type(enabled) is bool, 'INVALID_DENOISE_SWITCH', 'Denoise switch must be bool')
    doc = editor.saved()['timeline']; audio.validate(doc)
    before = deepcopy(material(doc, segment_id))
    require(before.get('is_denoise',False) != enabled, 'DENOISE_UNCHANGED', 'Denoise switch already matches')
    def change(report, current):
        require(material(current, segment_id) == before, 'REVISION_CHANGED', 'Denoise material changed')
        handler, controls = prepare_controls(editor, segment_id)
        require(controls['matches_saved_value'] and not controls['mixed'],
                'DENOISE_VALUE_MISMATCH', 'Native checkbox differs from the selected saved material')
        require(controls['available'], 'DENOISE_NOT_AVAILABLE', 'Native denoise control is disabled')
        # Same public callback as the shipped checkbox; no private wrapper,
        # global-rate edit, permission override, or synthetic input.
        editor.invoke_typed(handler, 'onDenoiseSwitchClick', [('bool', enabled)])
        editor.refresh()
    def accepted(current):
        node = material(current, segment_id)
        if node.get('is_denoise',False) != enabled: return False
        audio.validate(current)
        return node['id'] == before['id']
    return v02.transaction(editor, 'native-denoise-switch', change, accepted)
