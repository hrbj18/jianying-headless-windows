"""Cancel the exact native low-disk alert without replaying its open request.

The ordinary resident worker can be synchronously waiting inside this alert.
A separately owned worker in the SAME pinned bridge services only this bounded
recovery, with its own LoadLibrary reference, token, pipe, and exit handle.
No bridge ABI, vendor bytes, window input, or confirmation flags are changed.
"""
import ctypes as c
import ctypes.wintypes as w
import hashlib
import json
from pathlib import Path
import secrets
import time

from live_editor.errors import require
from live_editor.paths import runtime_config, STATE_ROOT
from live_editor.winprocess import discover, Reader, k
from live_editor.pipe_transport import (PipeTransport, DLL, checked, module_named,
                                        remote_export, export_rva, lifecycle_locked)
from live_editor.operations import write_json

FUSION_SHA256='f44c38192107ce355b6b16c264c3244186071a973cfaa06483112648ab4874f4'
EXPECTED_TEXT={
    'mainText':'磁盘空间不足',
    'subText':'磁盘空间不足，可能会出现数据丢失、播放卡顿、保存失败等问题，请尽快清理磁盘空间',
    'confirmBtnText':'仍要继续',
    'cancelBtnText':'取消',
}


def validate_alert(properties):
    require(all(properties.get(k)==v for k,v in EXPECTED_TEXT.items()),
            'UNRECOGNIZED_MODAL','The current alert is not the verified low-disk prompt')
    require(properties.get('visible') is True and properties.get('confirmedClose') is False,
            'MODAL_NOT_PENDING','The native low-disk prompt is not awaiting a normal cancel')


class ModalChannel(PipeTransport):
    """A temporary reference; closing it must leave the pending worker loaded."""
    @lifecycle_locked
    def start_owned(self,request_id):
        self._verify()
        existing=module_named(self.pid,DLL.name)
        require(existing and Path(existing['path']).resolve()==DLL.resolve(),
                'NO_EXISTING_BRIDGE','Recovery requires the original resident bridge')
        manifest=json.loads((DLL.parent/'manifest.json').read_text(encoding='utf-8'))
        require(hashlib.sha256(DLL.read_bytes()).hexdigest()==manifest['files'][DLL.name],
                'BRIDGE_HASH_MISMATCH','Native bridge identity changed')
        require(self.state_path.is_file(),'NO_PRIMARY_CONNECTION','No original connection state')
        self.primary_state_path=self.state_path
        self.state_path=STATE_ROOT/'state'/f'modal-{self.pid}-{self.birth}-{request_id}.json'
        require(not self.state_path.exists(),'MODAL_CONNECTION_UNCERTAIN',
                'This recovery channel already exists; inspect it before another attempt')
        self.state={'pid':self.pid,'birth':self.birth,
                    'pipe':rf'\\.\pipe\jianying-modal-{self.pid}-{secrets.token_hex(12)}',
                    'token':secrets.token_hex(16),'dll':str(DLL),
                    'primary_state':str(self.primary_state_path)}
        write_json(self.state_path,self.state)
        process=checked(k.OpenProcess(0x43a,False,self.pid),'Open exact recovery process')
        remote_path=bootstrap=loader=None
        try:
            # Each bridge_run consumes precisely its own LoadLibrary reference.
            remote_path=self._allocate(process,(str(DLL)+'\0').encode('utf-16-le'))
            loader=checked(k.CreateRemoteThread(process,None,0,
                remote_export(self.pid,'kernel32.dll',b'LoadLibraryW'),remote_path,0,None),
                'Retain the pinned bridge for modal recovery')
            require(k.WaitForSingleObject(loader,12000)==0,'LOAD_TIMEOUT',
                    'Recovery loader is pending; no automatic retry or unload')
            code=w.DWORD();checked(k.GetExitCodeThread(loader,c.byref(code)),'Recovery loader result')
            require(code.value!=0,'DLL_LOAD_FAILED','Recovery bridge reference was not acquired')
            k.VirtualFreeEx(process,remote_path,0,0x8000);remote_path=None
            data=self.state['pipe'].encode('utf-16-le').ljust(320,b'\0')+self.state['token'].encode()
            bootstrap=self._allocate(process,data)
            self.worker=checked(k.CreateRemoteThread(process,None,0,
                existing['base']+export_rva(DLL,b'bridge_run'),bootstrap,0,None),
                'Start the owned modal recovery channel')
            self.connect()
            k.VirtualFreeEx(process,bootstrap,0,0x8000);bootstrap=None
            return self
        finally:
            if loader:k.CloseHandle(loader)
            k.CloseHandle(process)
            # Pending remote inputs stay allocated for the executing worker.

    def finish_owned(self):
        require(not self.uncertain and self.handle and self.worker,
                'MODAL_CONNECTION_UNCERTAIN','Cannot stop an uncertain recovery channel')
        self.call(9);self.close()
        require(k.WaitForSingleObject(self.worker,12000)==0,'WORKER_EXIT_PENDING',
                'Recovery worker is still running; do not replay or unload')
        code=w.DWORD();checked(k.GetExitCodeThread(self.worker,c.byref(code)),'Recovery exit code')
        require(code.value==0,'WORKER_FAILED','Recovery worker exited with an error')
        require(module_named(self.pid,DLL.name) is not None,'PRIMARY_BRIDGE_MISSING',
                'The original resident bridge reference was not preserved')
        k.CloseHandle(self.worker);self.worker=None
        self.state_path.unlink()
        return {'owned_worker_exited':True,'primary_bridge_preserved':True}


def cancel_low_disk(pid,birth,request_id):
    from agent_entry import AgentLock
    request={'pid':pid,'birth':birth,'request_id':str(request_id),'action':'cancel-low-disk'}
    journal=STATE_ROOT/'modal-recovery'/str(request_id)/'result.json'
    with AgentLock():
        if journal.is_file():
            prior=json.loads(journal.read_text(encoding='utf-8'))
            require(prior['request']==request,'REQUEST_ID_CONFLICT','Different modal request')
            require(prior['state']=='confirmed','MODAL_RECOVERY_UNCERTAIN',
                    'Inspect the previous recovery; no automatic replay')
            return dict(prior['result'],already_completed=True,dispatched=False)
        process=discover(runtime_config())
        require((process['pid'],process['birth'])==(pid,birth),'PROCESS_CHANGED',
                'The requested editor process generation is no longer current')
        fusion=Path(process['modules']['FusionUI.dll']['path'])
        require(hashlib.sha256(fusion.read_bytes()).hexdigest()==FUSION_SHA256,
                'BUILD_MISMATCH','Unverified native alert implementation')
        base=process['modules']['VECreator.dll']['base']
        def current():
            with Reader(pid) as reader:
                require(reader.birth()==birth,'PROCESS_CHANGED','Editor generation changed')
                obj=reader.pointer(base+0xee94ce8)
                require(obj,'NO_PENDING_ALERT','No native blocking alert is present')
                vt=reader.pointer(obj)
                require(vt==process['modules']['Qt6Quick.dll']['base']+0x368df0,
                        'ALERT_TYPE_MISMATCH','Unexpected native alert window class')
                return obj,vt
        obj,vt=current()
        record={'request':request,'state':'prepared','alert':hex(obj),'started':time.time()}
        write_json(journal,record)
        channel=ModalChannel(pid,birth)
        try:
            channel.start_owned(str(request_id))
            props={}
            for key in (*EXPECTED_TEXT,'visible','confirmedClose'):
                value=channel.call(0,object=obj,vtable=vt,name=key)
                props[key]=value['text'] if value['kind']==3 else bool(value['number'])
            record['properties']=props;write_json(journal,record)
            validate_alert(props)
            require(current()==(obj,vt),'MODAL_CHANGED','The pending alert changed')
            record['state']='dispatching';write_json(journal,record)
            closed=channel.call(1,object=obj,vtable=vt,name='close',return_type=1)
            require(closed['kind']==1 and bool(closed['number']),'MODAL_CLOSE_REJECTED',
                    'The native alert declined normal close')
            deadline=time.monotonic()+10
            while True:
                with Reader(pid) as reader:alert=reader.pointer(base+0xee94ce8)
                if alert!=obj:break
                require(time.monotonic()<deadline,'MODAL_CLOSE_PENDING',
                        'Original alert is still registered; inspect before continuing')
                time.sleep(.1)
            stopped=channel.finish_owned()
            primary=PipeTransport(pid,birth)
            primary.state=json.loads(primary.state_path.read_text(encoding='utf-8'))
            try:
                primary.connect()  # Sequential server health proves prior job drained.
            finally:primary.release()
            result={'status':'confirmed','action':'cancel-low-disk',
                    'request_id':str(request_id),'pid':pid,'birth':birth,
                    'alert_cancelled':True,'prior_native_job_drained':True,
                    'open_replayed':False,'simulated_input':False,'dispatched':True,
                    'already_completed':False,'audit':str(journal),**stopped}
            record.update(state='confirmed',result=result,finished=time.time())
            write_json(journal,record)
            return result
        except Exception as error:
            record.update(state='needs-inspection',error=str(error),finished=time.time())
            write_json(journal,record)
            if channel.handle and not channel.uncertain and channel.worker:
                # A refused, completed read can release only this owned worker.
                try:channel.finish_owned()
                except Exception:pass
            raise
        finally:channel.release()
