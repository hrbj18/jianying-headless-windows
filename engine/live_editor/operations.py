"""Guarded, journaled commands. No retry or rollback after ambiguous dispatch."""
import hashlib
import json
import math
import msvcrt
import os
from pathlib import Path
import time
import uuid
from .paths import STATE_ROOT as ROOT
from .drafts import assert_saved
from .errors import require,LiveEditError

def confirm_parameter_history(editor,token,before,timeout=20):
    """Observe saved content, since parameter undo can leave geometry intact."""
    def fingerprint(timeline):
        fields={key:timeline.get(key) for key in ('tracks','materials','duration','fps','canvas_config')}
        return hashlib.sha256(json.dumps(fields,sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()
    expected=fingerprint(before);deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        result=editor.confirm_saved(token)
        if fingerprint(editor.saved(result['snapshot'])['timeline'])!=expected:return result
        time.sleep(.2)
    raise LiveEditError('SAVE_TIMEOUT','History may be applied; saved content did not change; inspect before retrying')

def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    with temp.open('x',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
    os.replace(temp,path)

class CommandLock:
    def __enter__(self):
        ROOT.mkdir(parents=True,exist_ok=True)
        self.file=(ROOT/'command.lock').open('a+b')
        if os.fstat(self.file.fileno()).st_size==0:self.file.write(b'0');self.file.flush()
        self.file.seek(0)
        try:msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:
            self.file.close();raise LiveEditError('COMMAND_BUSY','Another live-edit command is running')
        return self
    def __exit__(self,*args):
        self.file.seek(0);msvcrt.locking(self.file.fileno(),msvcrt.LK_UNLCK,1);self.file.close()

def prepare(report,action,seconds=None,segment_id=None):
    require(action in ('trim','undo','redo','split','delete'),'INVALID_ACTION','Unknown operation')
    require(action not in ('trim','split') or (isinstance(seconds,(int,float)) and math.isfinite(seconds) and seconds>0),'INVALID_DURATION','Time must be positive seconds')
    if action in ('trim','split','delete'):
        clips=report['snapshot']['clips']
        require(segment_id or len(clips)==1,'SEGMENT_REQUIRED','Specify which video clip to edit')
        segment_id=segment_id or clips[0]['segmentID']
    return dict(schema='jianying-live-edit/plan-v0.1',operation_id=str(uuid.uuid4()),action=action,
                duration_us=round(seconds*1_000_000) if action=='trim' else None,
                position_us=round(seconds*1_000_000) if action=='split' else None,segment_id=segment_id,
                expected=report)

def check_expected(expected,current):
    require(current['draft_id']==expected['draft_id'],'WRONG_DRAFT','The active draft differs from the requested draft')
    require(current['snapshot']['token']==expected['snapshot']['token'],'SESSION_CHANGED','The edit session changed; prepare a fresh command')
    require(current['snapshot']['revision']==expected['snapshot']['revision'],'REVISION_CHANGED','The clip changed after command preparation')
    require(current['files'][1:]==expected['files'][1:],'SAVED_REVISION_CHANGED','Saved timeline changed after command preparation')

def apply(editor,plan):
    require(plan.get('schema')=='jianying-live-edit/plan-v0.1','INVALID_PLAN','Unknown plan format')
    operation_id=str(uuid.UUID(plan['operation_id']))
    folder=ROOT/'evidence'/'operations'/operation_id;record=folder/'result.json'
    with CommandLock():
        if record.exists():
            prior=json.loads(record.read_text(encoding='utf-8'))
            require(prior['plan']==plan,'OPERATION_ID_CONFLICT','Operation ID was used for another request')
            require(prior['state']=='confirmed','OPERATION_UNCERTAIN','Prior operation did not complete confirmation; inspect before preparing another command')
            return dict(prior['result'],replayed=False,already_completed=True)
        current=editor.status();check_expected(plan['expected'],current)
        shot=current['snapshot'];saved=editor.saved(shot);assert_saved(shot,saved)
        action=plan['action'];require(action in ('trim','undo','redo','split','delete'),'INVALID_ACTION','Unknown operation')
        if action=='trim':
            clips=shot['clips'];tracks=saved['timeline']['tracks']
            requested=plan.get('segment_id') or (clips[0]['segmentID'] if len(clips)==1 else None)
            matches=[(t,s) for t in tracks if t['type']=='video' for s in t['segments'] if s['id']==requested]
            require(len(matches)==1,'SEGMENT_NOT_UNIQUE','Specify the video clip to trim')
            track,segment=matches[0];source=segment['source_timerange'];target=segment['target_timerange']
            require(segment.get('speed',1)==1 and abs(source['duration']-target['duration'])<=1 and not segment.get('common_keyframes') and not segment.get('group_id'),'V01_SCOPE','Variable speed, animated or grouped clips require separate validation')
            simple=len(clips)==1 and len(tracks)==1 and len(track['segments'])==1
            overlay=len(track['segments'])==1 and target.get('start',0)>0 and segment.get('volume',1)==0
            require(simple or overlay,'V01_SCOPE','Trim is verified for a single video or an explicitly selected isolated muted overlay')
            duration=plan['duration_us'];fps=saved['timeline'].get('fps',30)
            require(isinstance(duration,int) and 0<duration<target['duration'],'INVALID_DURATION','Trim must shorten the clip')
            require(abs(duration*fps/1_000_000-round(duration*fps/1_000_000))<.00001,'FRAME_ALIGNMENT','Requested duration must land on a video frame')
        if action in ('split','delete'):
            tracks=saved['timeline']['tracks']
            require(len(tracks)==1 and tracks[0]['type']=='video','V01_SCOPE','Structural editing is verified for one normal-speed video track')
            segments=tracks[0]['segments'];target=next((s for s in segments if s['id']==plan['segment_id']),None)
            require(target is not None,'WRONG_SEGMENT','Requested clip is not on the active timeline')
            require(all(s.get('speed',1)==1 and not s.get('common_keyframes') and not s.get('group_id') for s in segments),'V01_SCOPE','Groups, animation and variable speed require separate validation')
            require(action!='delete' or len(segments)>1,'V01_SCOPE','Deleting the last video is outside the current discovery scope')
            if action=='split':
                pos=plan['position_us'];tr=target['target_timerange'];fps=saved['timeline'].get('fps',30)
                start=tr.get('start',0)
                require(isinstance(pos,int) and start<pos<start+tr['duration'],'INVALID_POSITION','Split must be inside the selected clip')
                require(abs(pos*fps/1_000_000-round(pos*fps/1_000_000))<.00001,'FRAME_ALIGNMENT','Split must land on a video frame')
        folder.mkdir(parents=True,exist_ok=True)
        for path,expected_hash in zip(saved['paths'],saved['hashes']):
            data=path.read_bytes()
            require(hashlib.sha256(data).hexdigest()==expected_hash,'REVISION_CHANGED','Saved file changed before backup')
            relative=path.relative_to(Path(shot['draft_path']))
            backup=folder/'before'/relative;backup.parent.mkdir(parents=True,exist_ok=True);backup.write_bytes(data)
        (folder/'before/Timelines/project.json').write_bytes(saved['project'].read_bytes())
        entry=dict(state='dispatching',plan=plan,started=time.time(),result=None)
        write_json(record,entry)
        try:
            if action=='trim':
                editor.rpc('trim',shot['token'],shot['revision'],requested,plan['duration_us'])
            elif action in ('undo','redo'):editor.rpc('history',action,shot['token'],shot['revision'])
            elif action=='split':editor.rpc('split',shot['token'],shot['revision'],plan['segment_id'],plan['position_us'])
            else:editor.rpc('delete',shot['token'],shot['revision'],plan['segment_id'])
            result=(confirm_parameter_history(editor,shot['token'],saved['timeline']) if action in ('undo','redo') else
                    editor.confirm_saved(shot['token'],expected_duration=plan['duration_us'] if action=='trim' else None,
                                         changed_revision=shot['revision'] if action!='trim' else None,
                                         segment_id=requested if action=='trim' else None))
            if action=='trim':require(any(c['segmentID']==requested and abs(c['durationUs']-plan['duration_us'])<2 for c in result['snapshot']['clips']),'RESULT_MISMATCH','Native trim produced a different duration')
            elif action not in ('undo','redo'):require(result['snapshot']['revision']!=shot['revision'],'RESULT_NOT_OBSERVED','No visible timeline change observed after history command')
            result.update(operation_id=operation_id,action=action)
            entry.update(state='confirmed',finished=time.time(),result=result)
            write_json(record,entry);return result
        except Exception as error:
            entry.update(state='needs-inspection',finished=time.time(),error=str(error))
            write_json(record,entry);raise
