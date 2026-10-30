"""Shared local Agent interface. Native live mutations use the owning Qt session."""
from __future__ import annotations
import argparse, contextlib, hashlib, json, math, os, sys, time, uuid
from pathlib import Path

WRITES={'trim','split','delete','undo','redo','subtitle','audio-fade','audio-volume','audio-keyframe','import','append','move','filter-value','remove-filter','remove-effect','transition-duration','curve-gradient','hsl','audio-dsp','color-wheel','denoise-switch','lut-select','lut-value','white-balance','color-preset-save','curve-preset-apply','curve-enable','curve-reset'}
LIFECYCLE_WRITES={'close'}


def parser():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--client',choices=('codex','workbuddy','other'),default='other',help='Audit label, not proof of host execution')
    s=p.add_subparsers(dest='command',required=True)
    s.add_parser('doctor');s.add_parser('capabilities')
    stage=s.add_parser('stage',help='Place a verified new build and request normal editor discovery')
    stage.add_argument('--build',type=Path,required=True)
    stage.add_argument('--open',action='store_true',help='First open from Home only; never replace an editing session')
    stage.add_argument('--reopen-saved',action='store_true',help='Explicitly open the already edited target from Home without copying build bytes')
    modal=s.add_parser('cancel-low-disk',help='Cancel the exact native low-disk alert; never replay the pending open')
    modal.add_argument('--pid',type=int,required=True)
    modal.add_argument('--birth',type=int,required=True)
    modal.add_argument('--request-id',type=uuid.UUID,required=True)
    quit_app=s.add_parser('quit-home',help='Normally quit the exact process from Home only; never force terminate')
    quit_app.add_argument('--pid',type=int,required=True)
    quit_app.add_argument('--birth',type=int,required=True)
    quit_app.add_argument('--request-id',type=uuid.UUID,required=True)
    live=s.add_parser('live');subs=live.add_subparsers(dest='action',required=True)
    for name in ['status','segments','save','seek','minimize','release','speed-controls','color-controls','wheel-controls','lut-controls','lut-library','audio-controls','denoise-controls','white-balance-controls','filter-controls','curve-preset-controls',*sorted(WRITES|LIFECYCLE_WRITES)]:
        a=subs.add_parser(name)
        a.add_argument('--draft-id',required=name not in ('status','segments'),help='Exact active draft ID from status')
        a.add_argument('--session',required=name in LIFECYCLE_WRITES|{'speed-controls','color-controls','wheel-controls','lut-controls','lut-library','lut-select','lut-value','audio-controls','denoise-controls','denoise-switch','white-balance-controls','white-balance','color-preset-save','filter-controls','curve-preset-controls','curve-preset-apply','curve-enable','curve-reset'},help='Session fingerprint from status; required for explicit close or native controls')
        if name in WRITES|LIFECYCLE_WRITES:a.add_argument('--request-id',required=True,type=uuid.UUID,help='Stable UUID; retrying it never dispatches twice')
        if name in {'trim','split','delete','subtitle','audio-fade','audio-volume','audio-keyframe','move','filter-value','remove-filter','remove-effect','transition-duration','curve-gradient','hsl','audio-dsp'}:a.add_argument('--segment-id',required=True)
        if name in {'speed-controls','color-controls','wheel-controls','lut-controls','lut-library','lut-select','lut-value','audio-controls','color-wheel','denoise-controls','denoise-switch','white-balance-controls','white-balance','color-preset-save','filter-controls','curve-preset-controls','curve-preset-apply','curve-enable','curve-reset'}:a.add_argument('--segment-id',required=True)
        if name in {'curve-preset-controls','curve-preset-apply'}:a.add_argument('--preset-file',type=Path,required=True)
        if name=='white-balance':
            a.add_argument('--parameter',choices=('temperature','tint'),required=True)
            a.add_argument('--value',type=float,required=True)
        if name=='lut-value':a.add_argument('--value',type=float,required=True)
        if name=='lut-select':a.add_argument('--path',type=Path,required=True)
        if name in {'denoise-switch','curve-enable'}:a.add_argument('--enabled',choices=('true','false'),required=True)
        if name in {'wheel-controls','color-wheel'}:a.add_argument('--mode',choices=('primary','log'),required=True)
        if name=='color-wheel':
            a.add_argument('--group',choices=('lift','gamma','gain','offset','shadow','midtone','highlight'),required=True)
            a.add_argument('--component',choices=('red','green','blue','saturation'),required=True)
            a.add_argument('--value',type=float,required=True)
        if name=='color-controls':a.add_argument('--load-resources',action='store_true',help='Request the normal native adjustment resource load once')
        if name in {'trim','split','seek','audio-fade','move','transition-duration'}:a.add_argument('--seconds',type=float,required=True)
        if name=='subtitle':a.add_argument('--text',required=True)
        if name in {'import','append'}:a.add_argument('--source',type=Path,required=True)
        if name=='audio-fade':a.add_argument('--edge',choices=('in','out'),required=True)
        if name in {'audio-volume','audio-keyframe'}:a.add_argument('--db',type=float,required=True)
        if name=='audio-keyframe':a.add_argument('--index',type=int,required=True)
        if name=='move':a.add_argument('--target-track-id',required=True)
        if name=='filter-value':a.add_argument('--value',type=float,required=True)
        if name=='audio-dsp':
            a.add_argument('--parameter',choices=('gain','frequency','threshold','ratio','ceiling'),required=True)
            a.add_argument('--value',type=float,required=True)
        if name=='hsl':
            a.add_argument('--channel',choices=('red','orange','yellow','green','cyan','blue','purple','magenta'),required=True)
            a.add_argument('--property',choices=('hue','saturation','lightness'),required=True)
            a.add_argument('--value',type=int,required=True)
        if name=='curve-gradient':
            a.add_argument('--index',type=int,required=True)
            a.add_argument('--gradient',type=float,required=True)
    return p


def session_key(report):
    return hashlib.sha256(report['snapshot']['token'].encode()).hexdigest()


def compact(report):
    s=report['snapshot']
    return dict(draft_id=report['draft_id'],draft_name=report['draft_name'],draft_path=s['draft_path'],
                pid=report['pid'],timeline_id=report['timeline_id'],duration_us=report['duration_us'],
                session=session_key(report),preview=s['preview'],undo_available=s['undo_enabled'],redo_available=s['redo_enabled'])


def capabilities():
    return {'schema':'jianying-agent/v1','live_app_builds':['11.4.7.14462'],
            'entry':'jianying.ps1 agent', 'live_actions':sorted(WRITES|LIFECYCLE_WRITES|{'status','segments','save','seek','minimize','release','speed-controls','color-controls','wheel-controls','lut-controls','lut-library','audio-controls','denoise-controls','white-balance-controls','filter-controls','curve-preset-controls'}),
            'lifecycle_commands':['stage','cancel-low-disk','quit-home'],
            'offline_commands':['workspace','build','verify-build','preview','export','export-draft','analyze'],
            'constraints':{'live':'one current GUI session; explicit target; per-request journal; no automatic ambiguous replay',
                           'move':'existing unlocked secondary video track, 1x muted simple clips, frame-aligned nonoverlapping range',
                           'effects':'existing verified resources only; general effect addition is not supported',
                           'history':'native stack entries; first LUT adjustment can create separate resource and value entries',
                           'parallel':'one visible live draft plus independent background drafts; serialize writes to the same draft',
                           'window':'attach-only; close is explicit, saved-session guarded and journaled; no simulated input or process termination'}}


def check_args(a):
    for key in ('seconds','db','value','gradient'):
        v=getattr(a,key,None)
        if v is not None and not math.isfinite(v):raise ValueError(key+' must be finite')
    if hasattr(a,'seconds') and a.seconds<0:raise ValueError('seconds must be nonnegative')
    if getattr(a,'action',None)=='subtitle' and not (0<len(a.text)<=300 and '\0' not in a.text):raise ValueError('Subtitle must contain 1..300 characters, without NUL')


class AgentLock:
    """Serialize complete client commands, including state binding before mutation."""
    def __enter__(self):
        import msvcrt
        from live_editor.paths import STATE_ROOT
        STATE_ROOT.mkdir(parents=True,exist_ok=True)
        self.f=(STATE_ROOT/'agent-command.lock').open('a+b')
        if self.f.seek(0,2)==0:self.f.write(b'0');self.f.flush()
        self.f.seek(0)
        try:msvcrt.locking(self.f.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:self.f.close();raise RuntimeError('AGENT_BUSY: another client command is in progress')
        return self
    def __exit__(self,*args):
        import msvcrt
        self.f.seek(0);msvcrt.locking(self.f.fileno(),msvcrt.LK_UNLCK,1);self.f.close()


def execute_live(a):
    from live_editor.native_client import NativeEditor
    from live_editor import v02 as api
    from live_editor import operations as ops
    from live_editor.errors import require
    from live_editor.paths import STATE_ROOT
    request={k:str(v) if isinstance(v,(Path,uuid.UUID)) else v for k,v in vars(a).items() if k!='client'}
    journal=STATE_ROOT/'requests'/str(a.request_id)/'result.json' if a.action in WRITES|LIFECYCLE_WRITES else None
    with AgentLock():
        if journal and journal.is_file():
            prior=json.loads(journal.read_text(encoding='utf-8'))
            require(prior['request']==request,'REQUEST_ID_CONFLICT','Request ID belongs to a different command')
            require(prior['state']=='confirmed','OPERATION_UNCERTAIN','Inspect the earlier result before issuing a new request')
            return dict(prior['result'],already_completed=True,dispatched=False)
        class BoundEditor(NativeEditor):
            def __init__(self):super().__init__();self.bound=None
            def context(self):
                ctx=super().context()
                if self.bound is not None:require(ctx['token']==self.bound,'SESSION_CHANGED','The current edit session changed')
                return ctx
            def status(self):
                r=super().status()
                if a.draft_id:require(r['draft_id']==a.draft_id,'WRONG_DRAFT','Explicit draft differs from the current editing page')
                if a.session:require(session_key(r)==a.session,'SESSION_CHANGED','Session fingerprint is stale')
                return r
        with BoundEditor() as e:
            before=e.status();e.bound=before['snapshot']['token']
            entry={'request':request,'client':a.client,'state':'prepared','started':time.time(),'before':compact(before)}
            if journal:ops.write_json(journal,entry)
            try:
                name=a.action; native_id=None
                if name=='close':
                    from agent_window_lifecycle import close_saved_editor
                    entry['state']='dispatching';ops.write_json(journal,entry)
                    value=close_saved_editor(e,before,journal.parent)
                    output=dict(status='confirmed',command=name,client=a.client,report=compact(before),
                                request_id=str(a.request_id),audit=str(journal),dispatched=True,
                                already_completed=False,**value)
                    entry.update(state='confirmed',result=output,finished=time.time());ops.write_json(journal,entry)
                    return output
                elif name in {'status','save'}:after=e.status()
                elif name=='speed-controls':
                    from live_editor.speed import prepare_controls
                    _,controls=prepare_controls(e,a.segment_id)
                    return dict(status='speed-controls-initialized',report=compact(e.status()),controls=controls)
                elif name=='color-controls':
                    from live_editor.color import prepare_controls
                    _,controls=prepare_controls(e,a.segment_id,a.load_resources)
                    return dict(status='color-controls-initialized',report=compact(e.status()),controls=controls)
                elif name=='curve-preset-controls':
                    from live_editor.curve_preset import prepare
                    _,controls,_=prepare(e,a.preset_file)
                    return dict(status='curve-preset-controls-initialized',report=compact(e.status()),controls=controls)
                elif name=='filter-controls':
                    _,panel=api.video_panel(e,a.segment_id)
                    controls={key:e.get(panel,key) for key in ('isMultiSelect','filterName','filterEnabled','filterGroupChecked')}
                    controls['can_edit_in_native_ui']=bool(not controls['isMultiSelect'] and controls['filterName'] and
                        controls['filterEnabled'] and controls['filterGroupChecked'])
                    return dict(status='filter-controls-initialized',report=compact(e.status()),controls=controls)
                elif name=='wheel-controls':
                    from live_editor.color import prepare_wheel_controls
                    _,_,controls=prepare_wheel_controls(e,a.segment_id,a.mode)
                    return dict(status='wheel-controls-initialized',report=compact(e.status()),controls=controls)
                elif name=='white-balance-controls':
                    from live_editor.white_balance import prepare
                    _,_,controls=prepare(e,a.segment_id)
                    return dict(status='white-balance-controls-initialized',report=compact(e.status()),controls=controls)
                elif name=='lut-library':
                    from live_editor.lut import prepare_library
                    _,_,controls=prepare_library(e,a.segment_id)
                    return dict(status='lut-library-initialized',report=compact(e.status()),controls=controls)
                elif name=='lut-controls':
                    from live_editor.color import prepare_lut_controls
                    _,_,controls=prepare_lut_controls(e,a.segment_id)
                    return dict(status='lut-controls-initialized',report=compact(e.status()),controls=controls)
                elif name=='denoise-controls':
                    from live_editor.denoise import prepare_controls
                    _,controls=prepare_controls(e,a.segment_id)
                    return dict(status='denoise-controls-initialized',report=compact(e.status()),controls=controls)
                elif name=='audio-controls':
                    from live_editor.audio_controls import prepare_controls
                    _,controls=prepare_controls(e,a.segment_id)
                    return dict(status='audio-controls-initialized',report=compact(e.status()),controls=controls)
                elif name=='segments':
                    from agent_segments import segment_table
                    after=e.status();return dict(status='ok',report=compact(after),**segment_table(e.saved()['timeline']))
                elif name=='seek':
                    e.rpc('seek',before['snapshot']['token'],before['snapshot']['revision'],round(a.seconds*1_000_000));after=e.status()
                elif name=='minimize':
                    from live_editor.windows import minimize
                    window=minimize(e);return dict(status='minimized',report=compact(e.status()),window=window)
                elif name=='release':return dict(status='released',report=compact(before),release=e.shutdown())
                else:
                    entry['state']='dispatching';ops.write_json(journal,entry)
                    if name in {'trim','split','delete','undo','redo'}:
                        plan=ops.prepare(before,name,getattr(a,'seconds',None),getattr(a,'segment_id',None))
                        applied=ops.apply(e,plan);native_id=applied.get('operation_id');after=e.status()
                    elif name in {'import','append'}:
                        value=(api.import_media if name=='import' else api.insert_media)(e,a.source.resolve())
                        if isinstance(value,dict):after=value['report'];native_id=value.get('operation_id')
                        else:after,_,native_id=value
                    else:
                        def change_curve():
                            from live_editor.speed import curve_gradient
                            return curve_gradient(e,a.segment_id,a.index,a.gradient)
                        def change_hsl():
                            from live_editor.color import hsl
                            return hsl(e,a.segment_id,a.channel,a.property,a.value)
                        def change_audio_dsp():
                            from live_editor.audio_controls import adjust
                            return adjust(e,a.segment_id,a.parameter,a.value)
                        def change_color_wheel():
                            from live_editor.color import color_wheel
                            return color_wheel(e,a.segment_id,a.mode,a.group,a.component,a.value)
                        def change_denoise():
                            from live_editor.denoise import toggle
                            return toggle(e,a.segment_id,a.enabled=='true')
                        def select_lut():
                            from live_editor.lut import select
                            return select(e,a.segment_id,a.path)
                        def change_lut_value():
                            from live_editor.lut import intensity
                            return intensity(e,a.segment_id,a.value)
                        def change_white_balance():
                            from live_editor.white_balance import adjust
                            return adjust(e,a.segment_id,a.parameter,a.value)
                        def save_color_preset():
                            from live_editor.color_preset import save
                            return save(e,a.segment_id)
                        def apply_curve_preset():
                            from live_editor.curve_preset import apply
                            return apply(e,a.segment_id,a.preset_file)
                        def change_curve_enable():
                            from live_editor.curve_controls import enable
                            return enable(e,a.segment_id,a.enabled=='true')
                        def reset_curves():
                            from live_editor.curve_controls import reset
                            return reset(e,a.segment_id)
                        calls={'subtitle':lambda:api.subtitle(e,a.segment_id,a.text),
                               'curve-gradient':change_curve,
                               'hsl':change_hsl,
                               'color-wheel':change_color_wheel,
                               'audio-dsp':change_audio_dsp,
                               'denoise-switch':change_denoise,
                               'lut-select':select_lut,
                               'lut-value':change_lut_value,
                               'white-balance':change_white_balance,
                               'color-preset-save':save_color_preset,
                               'curve-preset-apply':apply_curve_preset,
                               'curve-enable':change_curve_enable,
                               'curve-reset':reset_curves,
                               'audio-fade':lambda:api.audio_fade(e,a.segment_id,a.edge,a.seconds),
                               'audio-volume':lambda:api.audio_volume(e,a.segment_id,a.db),
                               'audio-keyframe':lambda:api.audio_keyframe(e,a.segment_id,a.index,a.db),
                               'move':lambda:api.move_video(e,a.segment_id,a.target_track_id,a.seconds),
                               'filter-value':lambda:api.filter_value(e,a.segment_id,a.value),
                               'remove-filter':lambda:api.remove_filter(e,a.segment_id),
                               'remove-effect':lambda:api.remove_effect(e,a.segment_id),
                               'transition-duration':lambda:api.transition_duration(e,a.segment_id,a.seconds)}
                        after,_,native_id=calls[name]()
                output=dict(status='confirmed' if journal else 'ok',command=name,client=a.client,report=compact(after),
                            request_id=str(a.request_id) if journal else None,audit=str(journal) if journal else None,
                            native_operation_id=native_id,dispatched=bool(journal),already_completed=False)
                if name=='color-preset-save':output['preset']=after['preset_export']
                if name=='curve-preset-apply':output['preset']=after['curve_preset_import']
                if journal:entry.update(state='confirmed',result=output,finished=time.time());ops.write_json(journal,entry)
                return output
            except Exception as error:
                if journal:
                    entry.update(state='needs-inspection',error=str(error),finished=time.time());ops.write_json(journal,entry)
                raise


def main(argv=None):
    a=parser().parse_args(argv)
    try:
        check_args(a)
        with contextlib.redirect_stdout(sys.stderr):
            if a.command=='capabilities':output=capabilities()
            elif a.command=='doctor':
                from agent_environment import doctor
                output=doctor()
            elif a.command=='stage':
                from agent_drafts import stage
                output=stage(a.build,a.open,a.reopen_saved)
            elif a.command=='cancel-low-disk':
                from agent_modal_recovery import cancel_low_disk
                output=cancel_low_disk(a.pid,a.birth,a.request_id)
            elif a.command=='quit-home':
                from agent_app_lifecycle import quit_home
                output=quit_home(a.pid,a.birth,a.request_id)
            else:output=execute_live(a)
        print(json.dumps(output,ensure_ascii=True));return 0
    except (ValueError,RuntimeError,OSError) as error:
        print(json.dumps(dict(status='refused-or-needs-inspection',code=getattr(error,'code','AGENT_ERROR'),error=str(error)[:1000],automatic_retry=False),ensure_ascii=True));return 2

if __name__=='__main__':raise SystemExit(main())
