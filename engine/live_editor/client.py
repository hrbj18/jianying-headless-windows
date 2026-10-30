"""Saved-state support for the native Qt transport; no instrumentation runtime."""
import json,time,threading
from .errors import require,LiveEditError
from .profile import BUILD
from .drafts import DraftReader,assert_saved
from .paths import STATE_ROOT as ROOT, runtime_config

class LiveEditor:
    def __init__(self,config=None):
        self.config=config or runtime_config()
        self.process=None;self.reader=None;self.rpc_lock=threading.Lock()
    def __enter__(self):self.connect();return self
    def __exit__(self,*args):self.disconnect()
    def trace(self,phase,**extra):
        path=ROOT/'evidence/lifecycle.jsonl';path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('a',encoding='utf-8') as f:f.write(json.dumps(dict(time=time.time(),phase=phase,pid=self.process['pid'] if self.process else None,**extra),ensure_ascii=False)+'\n')
    def saved(self,shot=None):
        if self.reader is None:self.reader=DraftReader(self.config)
        return self.reader.read(shot or self.inspect())
    def confirm_saved(self,expected_token=None,expected_duration=None,changed_revision=None,segment_id=None):
        deadline=time.monotonic()+self.config.get('save_timeout_seconds',15);last=None
        while time.monotonic()<deadline:
            try:
                shot=self.inspect()
                if expected_token:require(shot['token']==expected_token,'SESSION_CHANGED','Draft changed during save confirmation')
                if expected_duration is not None:
                    clip=next((c for c in shot['clips'] if c['segmentID']==segment_id),None) if segment_id else shot['clips'][0]
                    require(clip is not None and abs(clip['durationUs']-expected_duration)<2,'SAVE_PENDING','Waiting for trim result')
                if changed_revision is not None:require(shot['revision']!=changed_revision,'SAVE_PENDING','Waiting for history result')
                saved=self.saved(shot);assert_saved(shot,saved)
                after=self.inspect()
                require(after['token']==shot['token'] and after['revision']==shot['revision'],'SAVE_IN_PROGRESS','Editor changed during save confirmation')
                return dict(status='saved-and-read-back',draft_id=saved['draft_id'],draft_name=saved['draft_name'],
                  timeline_id=shot['timeline_id'],duration_us=saved['timeline']['duration'],
                  files=[dict(path=str(p),sha256=h) for p,h in zip(saved['paths'],saved['hashes'])],snapshot=after)
            except LiveEditError as error:
                if error.code not in ('SAVE_PENDING','SAVE_IN_PROGRESS'):raise
                last=error
            time.sleep(.25)
        raise LiveEditError('SAVE_TIMEOUT','Native result may already be applied; do not replay automatically',last.as_dict() if last else None)
    def status(self):
        report=self.confirm_saved()
        report.update(build=BUILD,pid=self.process['pid'],discovery_seconds=self.discovery['seconds'])
        return report
