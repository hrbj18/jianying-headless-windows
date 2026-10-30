"""Small native Qt transport; no instrumentation VM, hooks, or UI inputs.

Closing a client leaves the worker resident. shutdown() explicitly drains and
unloads the DLL. The two lifecycle operations are tested and reported separately.
"""
import ctypes as c
import hashlib
import ctypes.wintypes as w
import json
import secrets
import struct
import time
import threading
from functools import wraps
from pathlib import Path
from .winprocess import modules, Reader, k, MBI
from .errors import require, LiveEditError

from .paths import STATE_ROOT as ROOT
DLL=Path(__file__).resolve().parents[2]/'bridge/live-editor/live-qt-pipe-v02.dll'
REQ=struct.Struct('<IIQQQQQii40s128s32s40s')
QUARANTINED_IO=[]
INVALID=c.c_void_p(-1).value

class Overlapped(c.Structure):
    _fields_=[('Internal',c.c_size_t),('InternalHigh',c.c_size_t),('Offset',w.DWORD),('OffsetHigh',w.DWORD),('hEvent',w.HANDLE)]

def api(name,restype,args):
    fn=getattr(k,name);fn.restype=restype;fn.argtypes=args;return fn

api('VirtualAllocEx',c.c_void_p,[w.HANDLE,c.c_void_p,c.c_size_t,w.DWORD,w.DWORD])
api('VirtualFreeEx',w.BOOL,[w.HANDLE,c.c_void_p,c.c_size_t,w.DWORD])
api('WriteProcessMemory',w.BOOL,[w.HANDLE,c.c_void_p,c.c_void_p,c.c_size_t,c.POINTER(c.c_size_t)])
api('CreateRemoteThread',w.HANDLE,[w.HANDLE,c.c_void_p,c.c_size_t,c.c_void_p,c.c_void_p,w.DWORD,c.POINTER(w.DWORD)])
api('WaitForSingleObject',w.DWORD,[w.HANDLE,w.DWORD])
api('GetExitCodeThread',w.BOOL,[w.HANDLE,c.POINTER(w.DWORD)])
api('GetExitCodeProcess',w.BOOL,[w.HANDLE,c.POINTER(w.DWORD)])
api('LoadLibraryW',w.HMODULE,[w.LPCWSTR])
api('FreeLibrary',w.BOOL,[w.HMODULE])
api('GetModuleHandleW',w.HMODULE,[w.LPCWSTR])
api('GetProcAddress',c.c_void_p,[w.HMODULE,c.c_char_p])
api('VirtualQuery',c.c_size_t,[c.c_void_p,c.POINTER(MBI),c.c_size_t])
api('GetModuleFileNameW',w.DWORD,[w.HMODULE,w.LPWSTR,w.DWORD])
api('CreateFileW',w.HANDLE,[w.LPCWSTR,w.DWORD,w.DWORD,c.c_void_p,w.DWORD,w.DWORD,w.HANDLE])
api('WaitNamedPipeW',w.BOOL,[w.LPCWSTR,w.DWORD])
api('CreateEventW',w.HANDLE,[c.c_void_p,w.BOOL,w.BOOL,w.LPCWSTR])
api('ReadFile',w.BOOL,[w.HANDLE,c.c_void_p,w.DWORD,c.POINTER(w.DWORD),c.POINTER(Overlapped)])
api('WriteFile',w.BOOL,[w.HANDLE,c.c_void_p,w.DWORD,c.POINTER(w.DWORD),c.POINTER(Overlapped)])
api('GetOverlappedResult',w.BOOL,[w.HANDLE,c.POINTER(Overlapped),c.POINTER(w.DWORD),w.BOOL])
api('CancelIoEx',w.BOOL,[w.HANDLE,c.POINTER(Overlapped)])
api('CreateMutexW',w.HANDLE,[c.c_void_p,w.BOOL,w.LPCWSTR])
api('ReleaseMutex',w.BOOL,[w.HANDLE])

def serialized(fn):
    @wraps(fn)
    def wrapped(self,*args,**kwargs):
        with self.lock:return fn(self,*args,**kwargs)
    return wrapped

def lifecycle_locked(fn):
    @wraps(fn)
    def wrapped(self,*args,**kwargs):
        mutex=checked(k.CreateMutexW(None,False,f'Local\\JianyingLive-{self.pid}-{self.birth}'),'Create lifecycle mutex')
        acquired=False
        try:
            acquired=k.WaitForSingleObject(mutex,15000) in (0,0x80)
            require(acquired,'CONNECTION_BUSY','Another controller is changing native bridge lifecycle')
            return fn(self,*args,**kwargs)
        finally:
            if acquired:k.ReleaseMutex(mutex)
            k.CloseHandle(mutex)
    return wrapped

def checked(value,what):
    require(bool(value),'WIN32_ERROR',what,{'winerror':c.get_last_error()})
    return value

def module_named(pid,name):
    return next((v for n,v in modules(pid).items() if n.lower()==name.lower()),None)

def remote_export(pid,module,name):
    address=checked(k.GetProcAddress(k.GetModuleHandleW(module),name),'GetProcAddress')
    mbi=MBI();checked(k.VirtualQuery(address,c.byref(mbi),c.sizeof(mbi)),'VirtualQuery')
    path=c.create_unicode_buffer(32768);checked(k.GetModuleFileNameW(mbi.AllocationBase,path,len(path)),'GetModuleFileName')
    remote=module_named(pid,Path(path.value).name)
    require(remote is not None,'REMOTE_MODULE_MISSING','Loader dependency not loaded')
    return remote['base']+address-mbi.AllocationBase

def export_rva(path,name):
    local=checked(k.LoadLibraryW(str(path)),'Load native bridge locally for export resolution')
    try:return checked(k.GetProcAddress(local,name),'Bridge export')-local
    finally:k.FreeLibrary(local)

class PipeTransport:
    def __init__(self,pid,birth=None):
        self.pid=pid
        with Reader(pid) as reader:self.birth=reader.birth()
        require(birth is None or birth==self.birth,'PROCESS_CHANGED','Process generation changed')
        self.state_path=ROOT/f'state/pipe-v02-{pid}-{self.birth}.json'
        self.handle=None;self.worker=None;self.uncertain=False;self.lock=threading.RLock()
    def _verify(self):
        with Reader(self.pid) as reader:
            require(reader.birth()==self.birth,'PROCESS_CHANGED','Process generation changed')
            code=w.DWORD();checked(k.GetExitCodeProcess(reader.handle,c.byref(code)),'Read process liveness')
            require(code.value==259,'PROCESS_EXITED','Editor process has exited',{'exit':code.value})
    def _allocate(self,process,data):
        address=checked(k.VirtualAllocEx(process,None,len(data),0x3000,4),'Allocate bridge bootstrap')
        n=c.c_size_t();checked(k.WriteProcessMemory(process,address,data,len(data),c.byref(n)),'Write bridge bootstrap')
        require(n.value==len(data),'PARTIAL_WRITE','Incomplete bridge bootstrap')
        return address
    @serialized
    @lifecycle_locked
    def start(self):
        manifest=json.loads((DLL.parent/'manifest.json').read_text(encoding='utf-8'))
        require(hashlib.sha256(DLL.read_bytes()).hexdigest()==manifest['files'][DLL.name],'BRIDGE_HASH_MISMATCH','Native bridge identity changed')
        self._verify();existing=module_named(self.pid,DLL.name)
        if existing:
            require(Path(existing['path']).resolve()==DLL.resolve(),'BRIDGE_PATH_MISMATCH','Unexpected native bridge')
            require(self.state_path.is_file(),'UNOWNED_BRIDGE','Resident bridge has no matching local state')
            self.state=json.loads(self.state_path.read_text(encoding='utf-8'))
            self.connect();return self
        require(not self.state_path.is_file(),'STALE_BRIDGE_STATE','Previous bridge disappeared without confirmed shutdown')
        self.state={'pid':self.pid,'birth':self.birth,'pipe':rf'\\.\pipe\jianying-live-{self.pid}-{secrets.token_hex(12)}','token':secrets.token_hex(16),'dll':str(DLL)}
        self.state_path.parent.mkdir(parents=True,exist_ok=True)
        self.state_path.write_text(json.dumps(self.state),encoding='utf-8')
        process=checked(k.OpenProcess(0x43a,False,self.pid),'Open exact selected process for native bridge')
        remote_path=None;bootstrap=None;loader=None
        try:
            remote_path=self._allocate(process,(str(DLL)+'\0').encode('utf-16-le'))
            loader=checked(k.CreateRemoteThread(process,None,0,remote_export(self.pid,'kernel32.dll',b'LoadLibraryW'),remote_path,0,None),'Load native bridge')
            require(k.WaitForSingleObject(loader,12000)==0,'LOAD_TIMEOUT','Native loader did not finish; no automatic retry')
            k.VirtualFreeEx(process,remote_path,0,0x8000);remote_path=None
            loaded=module_named(self.pid,DLL.name)
            require(loaded is not None,'DLL_LOAD_FAILED','Native bridge did not load')
            data=self.state['pipe'].encode('utf-16-le').ljust(320,b'\0')+self.state['token'].encode()
            bootstrap=self._allocate(process,data)
            self.worker=checked(k.CreateRemoteThread(process,None,0,loaded['base']+export_rva(DLL,b'bridge_run'),bootstrap,0,None),'Start native pipe worker')
            self.connect()
            k.VirtualFreeEx(process,bootstrap,0,0x8000);bootstrap=None
            return self
        finally:
            # Input memory remains allocated if a native call has not completed.
            if loader:k.CloseHandle(loader)
            k.CloseHandle(process)
    @serialized
    def connect(self):
        self._verify();self.close();deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            h=k.CreateFileW(self.state['pipe'],0xc0000000,0,None,3,0x40000000,None)
            if h not in (None,INVALID):self.handle=h;break
            error=c.get_last_error()
            if self.worker and k.WaitForSingleObject(self.worker,0)==0:
                code=w.DWORD();k.GetExitCodeThread(self.worker,c.byref(code))
                raise LiveEditError('BRIDGE_EXITED','Native server exited during startup',{'exit':code.value})
            require(error in (2,231),'PIPE_OPEN_FAILED','Cannot connect to native bridge',{'winerror':error})
            k.WaitNamedPipeW(self.state['pipe'],100);time.sleep(.03)
        require(self.handle,'PIPE_TIMEOUT','Native pipe did not become available')
        require(self.call(8)['number']==self.pid,'PIPE_IDENTITY_MISMATCH','Pipe is not bound to expected process')
        return self
    def _io(self,data_or_size,write=False):
        size=len(data_or_size) if write else data_or_size
        buf=c.create_string_buffer(data_or_size,size) if write else c.create_string_buffer(size)
        at=0;deadline=time.monotonic()+12
        while at<size:
            event=checked(k.CreateEventW(None,True,False,None),'Create IO event');ov=Overlapped();ov.hEvent=event;n=w.DWORD()
            retained=False
            try:
                ok=(k.WriteFile if write else k.ReadFile)(self.handle,c.byref(buf,at),size-at,c.byref(n),c.byref(ov))
                if not ok:
                    require(c.get_last_error()==997,'PIPE_IO_FAILED','Native pipe closed',{'winerror':c.get_last_error()})
                    status=k.WaitForSingleObject(event,max(1,int((deadline-time.monotonic())*1000)))
                    if status!=0:
                        self.uncertain=True;k.CancelIoEx(self.handle,c.byref(ov))
                        completed=k.WaitForSingleObject(event,1000)==0
                        if completed:
                            done=k.GetOverlappedResult(self.handle,c.byref(ov),c.byref(n),False)
                            completed=bool(done) or c.get_last_error()!=996
                        if not completed:
                            # Kernel may still reference these addresses. Never free
                            # them or close their event while completion is unknown.
                            QUARANTINED_IO.append((self.handle,ov,buf,event));retained=True
                        raise LiveEditError('NATIVE_TIMEOUT','Native job may be running; do not replay or unload automatically')
                    checked(k.GetOverlappedResult(self.handle,c.byref(ov),c.byref(n),False),'Complete native IO')
                require(n.value>0,'PIPE_EOF','Native pipe closed before result');at+=n.value
            finally:
                if not retained:k.CloseHandle(event)
        return buf.raw
    @serialized
    def call(self,operation,object=0,manager=0,timeline=0,vtable=0,name='',return_type=0,arg_type=0,value=b'',timeline_id='',payload=b''):
        require(self.handle and not self.uncertain,'PIPE_DISCONNECTED','Native bridge is disconnected or uncertain')
        self._verify();encoded=name.encode('utf-8');require(len(encoded)<128,'NAME_TOO_LONG','Native method name too long')
        require(len(value)<=40 and len(payload)<=8192 and (not payload or operation in (6,7,10)),'PAYLOAD_INVALID','Native request exceeds supported protocol')
        req=REQ.pack(0x4c455631,operation,object,manager,timeline,vtable,len(payload),return_type,arg_type,value.ljust(40,b'\0'),encoded,self.state['token'].encode(),timeline_id.encode('ascii'))+payload
        self._io(req,True);data=self._io(4120);executed,kind,number=struct.unpack_from('<iid',data)
        text=data[16:4114].decode('utf-16-le').split('\0',1)[0]
        require(executed==1,'NATIVE_JOB_FAILED','GUI-thread native job failed',{'executed':executed,'operation':operation,'name':name,'native_error':text})
        return {'kind':kind,'number':number,'text':text}
    @serialized
    def close(self):
        if self.handle:k.CloseHandle(self.handle);self.handle=None
    @serialized
    def release(self):
        self.close()
        if self.worker:k.CloseHandle(self.worker);self.worker=None
    @serialized
    @lifecycle_locked
    def shutdown(self):
        require(not self.uncertain,'CONNECTION_UNCERTAIN','Cannot unload while a job may be running')
        if not self.handle:self.connect()
        self.call(9);self.close();deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            if module_named(self.pid,DLL.name) is None:break
            time.sleep(.05)
        require(module_named(self.pid,DLL.name) is None,'UNLOAD_TIMEOUT','Native bridge has not unloaded')
        if self.worker:
            require(k.WaitForSingleObject(self.worker,1000)==0,'WORKER_EXIT_PENDING','Native worker did not exit')
            code=w.DWORD();checked(k.GetExitCodeThread(self.worker,c.byref(code)),'Get worker exit code')
            require(code.value==0,'WORKER_FAILED','Native worker exited with an error',{'exit':code.value})
            k.CloseHandle(self.worker);self.worker=None
        self._verify()
        self.state_path.unlink(missing_ok=True)
        return {'module_unloaded':True,'process_alive':True}
