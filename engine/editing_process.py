"""Observable editing runs around the existing CLI; no new rendering backend."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid

PROJECT=Path(__file__).resolve().parents[1]
DEFAULT_ROOT=PROJECT/'.local/editing-process'
STAGES=('plan','selection','rough','refine','subtitle','sound','review','delivery')


def now():return datetime.now(timezone.utc).isoformat()
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(temp,path)
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def valid_id(value):
    if str(uuid.UUID(value))!=value:raise ValueError('Invalid process run ID')
    return value


class Store:
    def __init__(self,root=DEFAULT_ROOT):self.root=Path(root)
    def folder(self,run):
        p=self.root/valid_id(run)
        if p.is_symlink() or not (p/'run.json').is_file():raise ValueError('Unknown editing run')
        return p
    def create(self,title,objective):
        run=str(uuid.uuid4());folder=self.root/run;folder.mkdir(parents=True)
        write(folder/'run.json',dict(schema='jianying-editing-process/v1',id=run,title=title,
              objective=objective,createdAt=now(),projectRoot=str(PROJECT)))
        write(folder/'control.json',dict(paused=False,updatedAt=now()))
        self.event(run,'decision',title='本轮目标',text=objective,stage='plan')
        return run
    def event(self,run,kind,**fields):
        folder=self.folder(run)
        value=dict(id=str(uuid.uuid4()),at=now(),kind=kind,**fields)
        with (folder/'events.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(value,ensure_ascii=False)+'\n');f.flush()
        return value
    def events(self,run):
        file=self.folder(run)/'events.jsonl'
        return [json.loads(line) for line in file.read_text(encoding='utf-8').splitlines() if line.strip()]
    def inputs(self,run):
        folder=self.folder(run);file=folder/'inputs.jsonl';ack=folder/'acknowledged.json'
        seen=set(read(ack) if ack.exists() else [])
        return [json.loads(line) for line in file.read_text(encoding='utf-8').splitlines()
                if line.strip() and json.loads(line)['id'] not in seen] if file.exists() else []
    def artifact(self,run,path,label,role='after',time_us=None,expected_sha=None):
        path=Path(path).resolve(strict=True)
        mime={'.mp4':'video/mp4','.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg'}.get(path.suffix.lower())
        if not mime or not path.is_file():raise ValueError('Only real MP4/PNG/JPEG process media can be attached')
        sha=digest(path)
        if expected_sha and sha!=expected_sha:raise ValueError('Process artifact does not match its native evidence')
        return self.event(run,'artifact',artifactId=str(uuid.uuid4()),path=str(path),label=label,
                          role=role,mime=mime,size=path.stat().st_size,sha256=sha,timeUs=time_us)
    def import_result(self,run,path,role='after'):
        path=Path(path).resolve(strict=True);result=read(path)
        if result.get('status') not in ('encoded-and-decoded','native-frames-captured'):
            raise ValueError('Import requires a real successful native media result')
        self.event(run,'history',title='既有原生验收记录',text='历史回执；当时未记录的剪辑理由不作补写。',
                   stage='review',evidence=str(path),evidenceSha256=digest(path),
                   occurredAt=datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).isoformat(),
                   resultStatus=result['status'])
        self.collect(run,result,role)
    def collect(self,run,result,role='after'):
        if result.get('status')=='encoded-and-decoded':
            output=result.get('output')
            if output:self.artifact(run,output,'原生成片',role,expected_sha=result.get('output_sha256'))
        if result.get('status')=='native-frames-captured':
            for i,frame in enumerate(result.get('frames',[])):
                if frame.get('png'):
                    self.artifact(run,frame['png'],f'原生预览 {i+1}','preview',
                        frame.get('requested_us',frame.get('requested_position_us',frame.get('position_us'))),
                        expected_sha=frame.get('png_sha256'))


def execute(store,run,spec):
    folder=store.folder(run);action=valid_id(spec['id'])
    args=spec['args']
    if not isinstance(args,list) or not args or any(not isinstance(x,str) or '\0' in x for x in args):
        raise ValueError('Action args must be a string array')
    if args[0] not in {'build','verify-build','preview','export','export-draft','edit-actions','agent'}:
        raise ValueError('This process runner only wraps existing local editing commands')
    if spec.get('stage') not in STAGES:raise ValueError('Unknown editing stage')
    identity=hashlib.sha256(json.dumps(spec,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    # A separate lock spans the child. UI controls remain writable, but another
    # execution can never overlap or replay an uncertain native operation.
    lock=(folder/'execute.lock').open('a+b')
    if lock.seek(0,2)==0:lock.write(b'0');lock.flush()
    lock.seek(0)
    if os.name=='nt':
        import msvcrt
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:lock.close();raise ValueError('Another editing action is running')
    else:
        import fcntl
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    try:
        prior=[e for e in store.events(run) if e.get('actionId')==action]
        if prior:
            if any(e.get('specSha256')!=identity for e in prior):raise ValueError('Action ID belongs to another plan')
            if prior[-1].get('state') in ('executed','verified'):
                return dict(status='already-completed',dispatched=False,actionId=action)
            if any(e.get('state') in ('dispatching','running','failed') for e in prior):
                raise ValueError('Inspect the original action; it will never be replayed automatically')
        fields=dict(actionId=action,title=spec['title'],reason=spec.get('reason'),stage=spec['stage'],
                    changes=spec.get('changes',[]),args=args,specSha256=identity)
        if not prior:store.event(run,'action',state='planned',**fields)
        if read(folder/'control.json').get('paused') or store.inputs(run):
            return dict(status='waiting-user-input' if store.inputs(run) else 'paused',dispatched=False,
                        actionId=action,inputs=store.inputs(run))
        stdout=folder/(action+'.stdout.json');stderr=folder/(action+'.stderr.log')
        store.event(run,'action',state='dispatching',**fields)
        with stdout.open('wb') as out,stderr.open('wb') as err:
            child=subprocess.Popen([sys.executable,str(PROJECT/'jianying.py'),*args],cwd=PROJECT,
                stdout=out,stderr=err,env=dict(os.environ,PYTHONUTF8='1'),
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            store.event(run,'action',state='running',childPid=child.pid,**fields)
            while True:
                code=child.poll()
                write(folder/'heartbeat.json',dict(at=time.time(),actionId=action,childPid=child.pid))
                if code is not None:break
                time.sleep(.5)
        try:result=read(stdout)
        except (ValueError,OSError):result={}
        success=code==0 and result.get('status') in {'built','verified','confirmed','staged',
            'encoded-and-decoded','native-frames-captured','applied-and-read-back','ok','ready'}
        state=('verified' if result.get('status') in {'encoded-and-decoded','native-frames-captured','verified'}
               else 'executed') if success else 'failed'
        event=store.event(run,'action',state=state,exitCode=code,resultStatus=result.get('status'),
            evidence=str(stdout),evidenceSha256=digest(stdout),
            verification='原生输出与技术检查；审美判断另记' if state=='verified' else None,
            error=(result.get('error') or '执行未确认，请检查原回执，勿重复派发') if not success else None,**fields)
        if success:
            store.collect(run,result,spec.get('role','after'))
            if args[0]=='build' and '--out' in args:
                plan=Path(args[args.index('--out')+1])/'plan.json'
                if plan.is_file():
                    p=read(plan)
                    store.event(run,'timeline',title='已构建的时间线',tracks=[dict(type=t['type'],name=t.get('name'),
                        segments=[dict(startUs=s.get('start_us',0),durationUs=s.get('duration_us',0),
                            label=s.get('text') or Path(s.get('source','素材')).name,
                            sourceStartUs=s.get('source_start_us'),changes=s.get('keyframes',{})) for s in t['segments']])
                        for t in p['tracks']])
        return dict(status=state,actionId=action,dispatched=True,result=event)
    finally:
        if os.name=='nt':
            lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
        lock.close()


def main(arguments=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
    create=sub.add_parser('create');create.add_argument('--title',required=True);create.add_argument('--objective',required=True)
    window=sub.add_parser('window');window.add_argument('--run');window.add_argument('--close',action='store_true')
    mode=window.add_mutually_exclusive_group();mode.add_argument('--compact',dest='compact',action='store_const',const=True);mode.add_argument('--expand',dest='compact',action='store_const',const=False)
    sub.add_parser('window-status')
    for name in ('note','execute','attach','import-result','inspect','acknowledge'):
        p=sub.add_parser(name);p.add_argument('--run',required=True)
        if name=='note':
            p.add_argument('--title',required=True);p.add_argument('--text',required=True)
            p.add_argument('--stage',choices=STAGES,default='plan')
        if name=='execute':p.add_argument('--spec',type=Path,required=True)
        if name in ('attach','import-result'):p.add_argument('--path',type=Path,required=True);p.add_argument('--role',choices=('before','after','preview'),default='after')
        if name=='attach':p.add_argument('--label',required=True)
        if name=='acknowledge':p.add_argument('--note-id',required=True);p.add_argument('--summary',required=True)
    a=parser.parse_args(arguments);store=Store()
    if a.action in ('window','window-status'):
        from editing_overlay import launch_window,window_status
        result=window_status() if a.action=='window-status' else launch_window(a.run,a.compact,a.close)
    elif a.action=='create':result={'run':store.create(a.title,a.objective),'root':str(store.root)}
    elif a.action=='execute':result=execute(store,a.run,read(a.spec))
    elif a.action=='note':result=store.event(a.run,'decision',title=a.title,text=a.text,stage=a.stage)
    elif a.action=='attach':result=store.artifact(a.run,a.path,a.label,a.role)
    elif a.action=='import-result':store.import_result(a.run,a.path,a.role);result={'status':'imported-existing-result','no_task_replayed':True}
    elif a.action=='acknowledge':
        note=next((n for n in store.inputs(a.run) if n['id']==a.note_id),None)
        if not note:raise ValueError('Unknown pending user note')
        file=store.folder(a.run)/'acknowledged.json';seen=read(file) if file.exists() else []
        seen.append(note['id']);write(file,seen)
        result=store.event(a.run,'decision',stage='plan',title='已采纳调整指令',text=a.summary,inputId=note['id'])
    else:result={'run':read(store.folder(a.run)/'run.json'),'events':store.events(a.run),'inputs':store.inputs(a.run)}
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 2 if result.get('status') in {'failed','paused','waiting-user-input'} else 0


if __name__=='__main__':raise SystemExit(main())
