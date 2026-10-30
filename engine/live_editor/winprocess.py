"""Read-only process discovery and aligned vtable scanning. No UI operations."""
import ctypes as c
import ctypes.wintypes as w
import hashlib
from pathlib import Path
import struct
import time

from .errors import require, LiveEditError
from .profile import HASHES, OBJECTS

class ProcessEntry(c.Structure):
    _fields_=[('dwSize',w.DWORD),('cntUsage',w.DWORD),('th32ProcessID',w.DWORD),
              ('th32DefaultHeapID',c.c_void_p),('th32ModuleID',w.DWORD),('cntThreads',w.DWORD),
              ('th32ParentProcessID',w.DWORD),('pcPriClassBase',w.LONG),('dwFlags',w.DWORD),('szExeFile',w.WCHAR*260)]

class ModuleEntry(c.Structure):
    _fields_=[('dwSize',w.DWORD),('th32ModuleID',w.DWORD),('th32ProcessID',w.DWORD),
              ('GlblcntUsage',w.DWORD),('ProccntUsage',w.DWORD),('modBaseAddr',c.c_void_p),
              ('modBaseSize',w.DWORD),('hModule',w.HMODULE),('szModule',w.WCHAR*256),('szExePath',w.WCHAR*260)]

class MBI(c.Structure):
    _fields_=[('BaseAddress',c.c_void_p),('AllocationBase',c.c_void_p),('AllocationProtect',w.DWORD),
              ('PartitionId',w.WORD),('RegionSize',c.c_size_t),('State',w.DWORD),('Protect',w.DWORD),('Type',w.DWORD)]

k=c.WinDLL('kernel32',use_last_error=True)
k.CreateToolhelp32Snapshot.argtypes=[w.DWORD,w.DWORD]; k.CreateToolhelp32Snapshot.restype=w.HANDLE
k.CloseHandle.argtypes=[w.HANDLE]
k.Process32FirstW.argtypes=[w.HANDLE,c.POINTER(ProcessEntry)];k.Process32NextW.argtypes=k.Process32FirstW.argtypes
k.Module32FirstW.argtypes=[w.HANDLE,c.POINTER(ModuleEntry)];k.Module32NextW.argtypes=k.Module32FirstW.argtypes
k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];k.OpenProcess.restype=w.HANDLE
k.ReadProcessMemory.argtypes=[w.HANDLE,c.c_void_p,c.c_void_p,c.c_size_t,c.POINTER(c.c_size_t)];k.ReadProcessMemory.restype=w.BOOL
k.VirtualQueryEx.argtypes=[w.HANDLE,c.c_void_p,c.POINTER(MBI),c.c_size_t];k.VirtualQueryEx.restype=c.c_size_t
k.GetProcessTimes.argtypes=[w.HANDLE,c.POINTER(w.FILETIME),c.POINTER(w.FILETIME),c.POINTER(w.FILETIME),c.POINTER(w.FILETIME)]

def _rows(flags, pid, cls, first, next_):
    h=k.CreateToolhelp32Snapshot(flags,pid)
    require(h not in (0,c.c_void_p(-1).value),'PROCESS_QUERY_FAILED','Cannot enumerate process or module')
    try:
        item=cls();item.dwSize=c.sizeof(item)
        ok=first(h,c.byref(item))
        while ok:
            yield cls.from_buffer_copy(item)
            ok=next_(h,c.byref(item))
    finally:k.CloseHandle(h)

def modules(pid):
    return {m.szModule:{'base':m.modBaseAddr,'size':m.modBaseSize,'path':m.szExePath}
            for m in _rows(0x8|0x10,pid,ModuleEntry,k.Module32FirstW,k.Module32NextW)}

class Reader:
    def __init__(self,pid):
        self.pid=pid;self.handle=k.OpenProcess(0x10|0x1000,False,pid)
        require(self.handle,'PROCESS_ACCESS_FAILED','Cannot read editor process')
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
    def close(self):
        if self.handle:k.CloseHandle(self.handle);self.handle=None
    def birth(self):
        times=[w.FILETIME() for _ in range(4)]
        require(k.GetProcessTimes(self.handle,*[c.byref(t) for t in times]),'PROCESS_EXITED','Cannot verify process generation')
        return (times[0].dwHighDateTime<<32)|times[0].dwLowDateTime
    def read(self,addr,n,partial=False):
        buf=c.create_string_buffer(n);done=c.c_size_t()
        ok=k.ReadProcessMemory(self.handle,addr,buf,n,c.byref(done))
        require(partial or (ok and done.value==n),'STALE_OBJECT','Memory object is no longer readable')
        return buf.raw[:done.value]
    def pointer(self,addr):return struct.unpack('<Q',self.read(addr,8))[0]

def discover(config):
    install=Path(config['install_dir']).resolve()
    candidates=[]
    for p in _rows(2,0,ProcessEntry,k.Process32FirstW,k.Process32NextW):
        if p.szExeFile.lower()!='jianyingpro.exe':continue
        try:
            mods=modules(p.th32ProcessID)
            if 'VECreator.dll' not in mods or 'Qt6Quick.dll' not in mods:continue
            if Path(mods['VECreator.dll']['path']).parent.resolve()!=install:continue
            with Reader(p.th32ProcessID) as reader:birth=reader.birth()
            candidates.append({'pid':p.th32ProcessID,'parent':p.th32ParentProcessID,'birth':birth,'modules':mods})
        except LiveEditError:continue
    # The native service children load the same DLLs. Only the root editor can
    # own an edit session; actual active models are verified after discovery.
    ids={p['pid'] for p in candidates}
    candidates=[p for p in candidates if p['parent'] not in ids]
    require(len(candidates)==1,'EDITOR_NOT_UNIQUE','Expected one running supported editor; nothing will be launched',{'candidates':[p['pid'] for p in candidates]})
    for name,expected in HASHES.items():
        path=install/name
        require(path.is_file(),'BUILD_MISMATCH','Required installed component missing: '+name)
        with path.open('rb') as source:actual=hashlib.file_digest(source,'sha256').hexdigest()
        require(actual==expected,'BUILD_MISMATCH','Unverified editor component: '+name)
    return candidates[0]

def validate_objects(reader,base,rows):
    definitions={base+vt:(kind,extra) for kind,layouts in OBJECTS.items() for vt,extra in layouts}
    result=[]
    for row in rows:
        try:
            addr=int(row['address'],16);vt=reader.pointer(addr)
            if vt not in definitions:continue
            kind,extra=definitions[vt]
            if all(reader.pointer(addr+offset)==base+target for offset,target in extra.items()):
                result.append({'kind':kind,'address':hex(addr)})
        except (LiveEditError,ValueError):continue
    return result

def scan_objects(process,timeout=60):
    import numpy as np
    base=process['modules']['VECreator.dll']['base']
    expected={base+vt:kind for kind,layouts in OBJECTS.items() for vt,_ in layouts}
    low,high=min(expected),max(expected);found=[];scanned=0;started=time.monotonic()
    with Reader(process['pid']) as reader:
        require(reader.birth()==process['birth'],'PROCESS_CHANGED','Editor process was replaced')
        at=0
        while at<0x7fffffffffff:
            require(time.monotonic()-started<timeout,'DISCOVERY_TIMEOUT','Object discovery incomplete; no editing allowed')
            m=MBI()
            if not k.VirtualQueryEx(reader.handle,at,c.byref(m),c.sizeof(m)):break
            begin=m.BaseAddress or 0;at=begin+m.RegionSize
            if m.State!=0x1000 or m.Type!=0x20000 or m.Protect&0x100 or m.Protect&0xff not in (4,8):continue
            for offset in range(0,m.RegionSize,16*1024*1024):
                chunk=reader.read(begin+offset,min(m.RegionSize-offset,16*1024*1024),partial=True)
                scanned+=len(chunk)
                values=np.frombuffer(chunk[:len(chunk)//8*8],dtype='<u8')
                for i in np.flatnonzero((values>=low)&(values<=high)):
                    value=int(values[i])
                    if value in expected:found.append({'kind':expected[value],'address':hex(begin+offset+int(i)*8)})
        verified=validate_objects(reader,base,found)
    return {'objects':verified,'seconds':round(time.monotonic()-started,3),'bytes_read':scanned}
