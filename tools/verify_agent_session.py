"""End-to-end acceptance through the public entry on an isolated 8-second draft.

Run from each actual client. The client label alone is not host provenance.
No editing inputs, automatic draft switching or project reopening are used.
"""
import argparse, ctypes, json, os, subprocess, sys, time, uuid
from pathlib import Path

REPO=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--client',choices=('codex','workbuddy'),required=True)
    p.add_argument('--draft-id',required=True)
    p.add_argument('--seconds',type=int,choices=(4,6),required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    records=[]
    def save():
        (a.out/'acceptance.json').write_text(json.dumps(dict(status='running',client=a.client,records=records),ensure_ascii=False,indent=2),encoding='utf-8')
    def call(args,expected=0):
        command=[sys.executable,'-X','utf8','-B',str(REPO/'jianying.py'),*args]
        started=time.time_ns();r=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=240)
        try:value=json.loads(r.stdout)
        except ValueError:value={'raw_stdout':r.stdout[-2000:]}
        records.append(dict(command=args,pid=os.getpid(),started_ns=started,finished_ns=time.time_ns(),exit_code=r.returncode,result=value,stderr=r.stderr[-2000:]));save()
        if r.returncode!=expected:raise RuntimeError('Command failed: '+json.dumps(value,ensure_ascii=False))
        print(json.dumps({'command':args[3] if len(args)>3 else args[0],'status':value.get('status'),'exit_code':r.returncode}),flush=True)
        return value
    prefix=['agent','--client',a.client,'live']
    before=call(prefix+['status'])['report']
    assert before['draft_id']==a.draft_id and before['draft_name']=='AgentIntegration_1022' and before['duration_us']==8000000, before
    session=before['session'];binding=['--draft-id',a.draft_id,'--session',session]
    def status(duration):
        r=call(prefix+['status'])['report'];assert r['session']==session and r['duration_us']==duration,r
        return r
    table=call(prefix+['segments']);sid=table['segments'][0]['segment_id'];assert len(table['segments'])==1
    # Explicit wrong target must stop before any dispatch.
    rejected=call(prefix+['trim','--draft-id',str(uuid.uuid4()),'--segment-id',sid,'--seconds',str(a.seconds),'--request-id',str(uuid.uuid4())],expected=2)
    assert rejected['code']=='WRONG_DRAFT';status(8000000)
    rid=str(uuid.uuid4());trim=prefix+['trim',*binding,'--segment-id',sid,'--seconds',str(a.seconds),'--request-id',rid]
    cut=call(trim);assert cut['report']['duration_us']==a.seconds*1000000
    replay=call(trim);assert replay['already_completed'] and not replay['dispatched'];status(a.seconds*1000000)
    call(['export-draft','--draft-dir',before['draft_path'],'--out',str(a.out/'export'),'--bitrate','2000000','--timeout','180'])
    for action,duration in [('undo',8000000),('redo',a.seconds*1000000),('undo',8000000)]:
        call(prefix+[action,*binding,'--request-id',str(uuid.uuid4())]);status(duration)
    # Exercise real structural edits; restore via the editor's native history.
    call(prefix+['split',*binding,'--segment-id',sid,'--seconds','2','--request-id',str(uuid.uuid4())]);status(8000000)
    clips=call(prefix+['segments'])['segments'];assert len(clips)==2
    right=max(clips,key=lambda s:s['start_us'])
    call(prefix+['delete',*binding,'--segment-id',right['segment_id'],'--request-id',str(uuid.uuid4())]);status(2000000)
    call(prefix+['undo',*binding,'--request-id',str(uuid.uuid4())]);status(8000000)
    call(prefix+['undo',*binding,'--request-id',str(uuid.uuid4())]);status(8000000)
    call(prefix+['seek',*binding,'--seconds','1'])
    saved=call(prefix+['save',*binding]);assert saved['report']['duration_us']==8000000
    call(prefix+['minimize',*binding])
    released=call(prefix+['release',*binding]);assert released['release']['module_unloaded'] and released['release']['process_alive']
    final=status(8000000)
    # Process lineage is host evidence; filenames/labels are not substituted.
    sys.path.insert(0,str(REPO/'engine'))
    from live_editor.winprocess import _rows,ProcessEntry,k
    processes={x.th32ProcessID:dict(pid=x.th32ProcessID,parent=x.th32ParentProcessID,image=x.szExeFile) for x in _rows(2,0,ProcessEntry,k.Process32FirstW,k.Process32NextW)}
    lineage=[];pid=os.getpid()
    while pid in processes and len(lineage)<12:
        row=processes[pid];lineage.append(row);pid=row['parent']
    result=dict(status='passed',client=a.client,entry=str(REPO/'jianying.py'),python=sys.executable,
                host_lineage=lineage,started_session=session,final=final,records=records,
                source_draft_restored=True,editor_reopened_for_refresh=False,editing_input_simulated=False,
                export=str(a.out/'export/render.mp4'),host_label_alone_is_not_proof=True)
    (a.out/'acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(status='passed',client=a.client,report=str(a.out/'acceptance.json'),export=result['export']),ensure_ascii=False),flush=True)

if __name__=='__main__':main()
