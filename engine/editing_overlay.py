"""Native text companion owned by Jianying; no browser, input simulation or capture."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import ctypes as c
from ctypes import wintypes as w
import json
import os
import subprocess
import sys
import time
import uuid

from editing_process import DEFAULT_ROOT, PROJECT, Store, read, valid_id, write

STATE_ROOT = PROJECT / '.local/editing-overlay'
STATE_FILE = STATE_ROOT / 'status.json'
COMMAND_FILE = STATE_ROOT / 'command.json'
LABELS = {'planned':'计划', 'dispatching':'提交中', 'running':'执行中',
          'executed':'完成', 'verified':'核验通过', 'failed':'失败，待核对'}


def journal_lines(path):
    """Ignore only a concurrent unfinished final append, never fabricate a result."""
    try:
        if path.stat().st_size > 16 * 1024 * 1024:
            raise ValueError('过程记录过大，请归档后重新打开')
        data = path.read_text(encoding='utf-8')
    except FileNotFoundError:
        return []
    return [json.loads(line) for line in data[:data.rfind('\n')+1].splitlines() if line.strip()]


def select_run(root=DEFAULT_ROOT, selected=None):
    store = Store(root)
    if selected:
        return store.folder(selected)
    folders = []
    for p in Path(root).glob('*'):
        try:
            if p.is_dir() and not p.is_symlink():
                valid_id(p.name)
                value = read(p/'run.json')
                if value.get('id') == p.name and value.get('schema') == 'jianying-editing-process/v1':
                    folders.append((value['createdAt'],p))
        except (OSError, ValueError, KeyError):
            continue
    return max(folders,key=lambda item:item[0])[1] if folders else None


def snapshot(folder, clock=None):
    if folder is None:
        return dict(run=None, title='尚无剪辑记录', state='idle', status='待命',
                    text='收到新的剪辑指令后，这里显示具体操作和执行结果。', paused=False)
    now = time.time() if clock is None else clock
    run = read(folder/'run.json')
    events = journal_lines(folder/'events.jsonl')
    actions = {}
    for e in events:
        if e.get('kind') == 'action': actions[e['actionId']] = e
    last = list(actions.values())[-1] if actions else None
    state, status = 'idle', '待命'
    if last and last['state'] in ('dispatching','running'):
        try: heartbeat = read(folder/'heartbeat.json')
        except FileNotFoundError: heartbeat = {}
        at = heartbeat.get('at',0) if heartbeat.get('actionId') == last['actionId'] else datetime.fromisoformat(last['at']).timestamp()
        state = 'uncertain' if now-at > 15 else 'running'
        status = '回执待核对 · 不会重复执行' if state == 'uncertain' else '正在执行'
    elif last and last['state'] == 'failed':
        state,status = 'failed','执行失败 · 请核对原回执'
    elif last:
        status = '待命 · 上一步'+LABELS.get(last['state'],last['state'])
    control = read(folder/'control.json')
    ack = read(folder/'acknowledged.json') if (folder/'acknowledged.json').exists() else []
    inputs = [e for e in journal_lines(folder/'inputs.jsonl') if e['id'] not in ack]
    if inputs: status += f' · {len(inputs)} 条意见待处理'
    if control.get('paused'): status += ' · 后续已暂停'
    lines = [('当前：'+last['title']) if state == 'running' else '当前：没有正在执行的已记录操作']
    if state in ('uncertain','failed'): lines[0] = '待核对：'+last['title']
    if last and state == 'running' and last.get('reason'): lines += ['依据：'+last['reason']]
    lines += ['', '最近记录（按实际回执）']
    for a in list(actions.values())[-4:]:
        stamp = datetime.fromisoformat(a['at']).astimezone().strftime('%H:%M:%S')
        lines.append(f"{stamp}  {LABELS.get(a['state'],a['state'])} · {a['title']}")
        for change in a.get('changes',[]):
            lines.append(f"  {change.get('label','参数')}：{change.get('before','—')} → {change.get('after','—')}")
        if a.get('error'): lines.append('  '+str(a['error']))
    decisions = [e for e in events if e.get('kind') == 'decision']
    if decisions:
        lines += ['', '最近剪辑依据', decisions[-1].get('text','')]
    if not actions: lines += [run.get('objective','')]
    return dict(run=run['id'], title=run['title'], state=state, status=status,
                text='\n'.join(lines), paused=bool(control.get('paused')), pendingInputs=len(inputs))


def dock_rect(owner, work, size, offset=(0,0)):
    left,top,right,bottom = owner
    wl,wt,wr,wb = work
    width,height = size
    x = max(wl,min(right-width-18+offset[0],wr-width))
    y = max(wt,min(top+90+offset[1],wb-height))
    return int(x),int(y),width,height


def hidden_reason(owner, minimized, foreground_pid, editor_pid, own_pid):
    if not owner:return 'waiting-editor-window'
    if minimized:return 'editor-minimized'
    if foreground_pid not in (editor_pid,own_pid):return 'editor-in-background'
    return None


class NativeHost:
    """Reads only the editor's window metadata; all writes target our own window."""
    def __init__(self):
        self.u = c.WinDLL('user32',use_last_error=True)
        self.k = c.WinDLL('kernel32',use_last_error=True)
        for name,args,result in [
            ('IsWindow',[w.HWND],w.BOOL),('IsWindowVisible',[w.HWND],w.BOOL),
            ('IsIconic',[w.HWND],w.BOOL),('GetWindowRect',[w.HWND,c.POINTER(w.RECT)],w.BOOL),
            ('GetWindowThreadProcessId',[w.HWND,c.POINTER(w.DWORD)],w.DWORD),
            ('GetAncestor',[w.HWND,w.UINT],w.HWND),('GetWindow',[w.HWND,w.UINT],w.HWND),
            ('GetForegroundWindow',[],w.HWND),('SetWindowLongPtrW',[w.HWND,c.c_int,c.c_ssize_t],c.c_ssize_t),
            ('GetWindowLongPtrW',[w.HWND,c.c_int],c.c_ssize_t),
            ('SetWindowPos',[w.HWND,w.HWND,c.c_int,c.c_int,c.c_int,c.c_int,w.UINT],w.BOOL),
            ('MonitorFromWindow',[w.HWND,w.DWORD],w.HANDLE),
            ('GetMonitorInfoW',[w.HANDLE,c.c_void_p],w.BOOL)]:
            fn = getattr(self.u,name); fn.argtypes=args; fn.restype=result
        self.k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];self.k.OpenProcess.restype=w.HANDLE
        self.k.GetProcessTimes.argtypes=[w.HANDLE,*([c.POINTER(w.FILETIME)]*4)]
        self.k.CloseHandle.argtypes=[w.HANDLE]
    def birth(self,pid):
        h=self.k.OpenProcess(0x1000,False,pid)
        if not h:return None
        try:
            times=[w.FILETIME() for _ in range(4)]
            if not self.k.GetProcessTimes(h,*[c.byref(t) for t in times]):return None
            return times[0].dwHighDateTime<<32|times[0].dwLowDateTime
        finally:self.k.CloseHandle(h)
    def pid(self,hwnd):
        pid=w.DWORD();self.u.GetWindowThreadProcessId(hwnd,c.byref(pid));return pid.value
    def rect(self,hwnd):
        r=w.RECT()
        if not self.u.GetWindowRect(hwnd,c.byref(r)):raise OSError('Cannot read window geometry')
        return r.left,r.top,r.right,r.bottom
    def work(self,hwnd):
        class MonitorInfo(c.Structure):
            _fields_=[('cbSize',w.DWORD),('rcMonitor',w.RECT),('rcWork',w.RECT),('dwFlags',w.DWORD)]
        m=MonitorInfo();m.cbSize=c.sizeof(m)
        if not self.u.GetMonitorInfoW(self.u.MonitorFromWindow(hwnd,2),c.byref(m)):
            raise OSError('Cannot read monitor work area')
        r=m.rcWork;return r.left,r.top,r.right,r.bottom
    def attach(self,own,owner):
        if self.pid(own)!=os.getpid():raise ValueError('Refusing to modify another application window')
        c.set_last_error(0);self.u.SetWindowLongPtrW(own,-8,owner)
        if self.u.GetWindow(own,4)!=owner:raise OSError('Native window ownership was not established')
        # Tool window; display without stealing keyboard focus. No global topmost flag.
        style=self.u.GetWindowLongPtrW(own,-20)
        self.u.SetWindowLongPtrW(own,-20,(style|0x80|0x08000000)&~0x40000)
    def place(self,own,rect):
        if self.pid(own)!=os.getpid():raise ValueError('Refusing to move another application window')
        # Only our overlay moves; NOACTIVATE. Ownership keeps it above its editor.
        if not self.u.SetWindowPos(own,0,*rect,0x0010|0x0040):raise OSError('Cannot position companion window')


class Overlay:
    def __init__(self,selected=None):
        import tkinter as tk
        from local_config import load_config
        from live_editor.winprocess import discover
        self.host=NativeHost()
        self.editor=discover({'install_dir':load_config()['jianying_install_dir']})
        self.pid=os.getpid();self.birth=self.host.birth(self.pid)
        self.selected=selected;self.owner=None;self.compact=False;self.offset=(0,0)
        self.command=None;self.last_text=None;self.last_rect=None;self.closed=False
        self.root=tk.Tk();self.root.withdraw();self.root.overrideredirect(True)
        self.root.title('剪映 · 剪辑过程');self.root.configure(bg='#384247')
        self.root.option_add('*Font',('Microsoft YaHei UI',10))
        self.frame=tk.Frame(self.root,bg='#23282c',highlightbackground='#48575e',highlightthickness=1)
        self.frame.pack(fill='both',expand=True)
        header=tk.Frame(self.frame,bg='#293438',height=36);header.pack(fill='x');header.pack_propagate(False)
        self.heading=tk.Label(header,text='●  剪辑助手',fg='#3bd2cd',bg='#293438',anchor='w',padx=12)
        self.heading.pack(side='left',fill='both',expand=True)
        def button(parent,text,command,width=3):
            return tk.Button(parent,text=text,command=command,width=width,bg='#293438',fg='#cad3d8',activebackground='#405158',activeforeground='white',bd=0,highlightthickness=0,takefocus=0,cursor='hand2')
        button(header,'×',self.close).pack(side='right')
        self.fold=button(header,'收起',self.toggle,5);self.fold.pack(side='right')
        self.body=tk.Frame(self.frame,bg='#23282c');self.body.pack(fill='both',expand=True)
        self.status=tk.StringVar(value='正在读取真实记录…')
        tk.Label(self.body,textvariable=self.status,fg='#65d6c8',bg='#23282c',anchor='w',padx=12,pady=8).pack(fill='x')
        self.task=tk.StringVar()
        tk.Label(self.body,textvariable=self.task,fg='#a9b9c5',bg='#23282c',anchor='w',padx=12,wraplength=332,justify='left',font=('Microsoft YaHei UI',9)).pack(fill='x')
        text_frame=tk.Frame(self.body,bg='#23282c');text_frame.pack(fill='both',expand=True)
        self.text=tk.Text(text_frame,bg='#23282c',fg='#e4e9ec',bd=0,padx=12,pady=10,wrap='word',width=34,height=9,cursor='arrow',font=('Microsoft YaHei UI',10),state='disabled',takefocus=0)
        scrollbar=tk.Scrollbar(text_frame,command=self.text.yview,width=9,bd=0,highlightthickness=0)
        scrollbar.pack(side='right',fill='y');self.text.configure(yscrollcommand=scrollbar.set)
        self.text.pack(fill='both',expand=True)
        footer=tk.Frame(self.body,bg='#293438',height=34);footer.pack(fill='x');footer.pack_propagate(False)
        tk.Label(footer,text='真实记录 · 仅收到指令才工作',fg='#8da0ad',bg='#293438',font=('Microsoft YaHei UI',8),padx=10).pack(side='left',fill='y')
        self.pause=button(footer,'暂停后续',self.toggle_pause,9);self.pause.pack(side='right',fill='y')
        self.value=snapshot(None)
        for widget in (header,self.heading):
            widget.bind('<ButtonPress-1>',self.drag_start)
            widget.bind('<B1-Motion>',self.drag)
        self.root.geometry('366x330');self.root.update_idletasks()
        self.hwnd=int(self.host.u.GetAncestor(self.root.winfo_id(),2))
        if not self.hwnd:raise ValueError('Native companion handle unavailable')
        self.root.protocol('WM_DELETE_WINDOW',self.close)
        self.root.after(10,self.tick)
    def toggle(self):
        self.compact=not self.compact;self.last_rect=None
        if self.compact:self.body.pack_forget()
        else:self.body.pack(fill='both',expand=True)
        self.fold.configure(text='展开' if self.compact else '收起')
        self.root.geometry('366x36' if self.compact else '366x330')
    def drag_start(self,event):self.drag_origin=(event.x_root,event.y_root,self.offset)
    def drag(self,event):
        x,y,offset=self.drag_origin;self.offset=(offset[0]+event.x_root-x,offset[1]+event.y_root-y);self.last_rect=None
    def toggle_pause(self):
        if not self.value.get('run'):return
        file=Store().folder(self.value['run'])/'control.json'
        write(file,dict(paused=not read(file).get('paused'),updatedAt=datetime.now(timezone.utc).isoformat(),id=str(uuid.uuid4())))
    def persist(self,reason=None):
        write(STATE_FILE,dict(schema='jianying-editing-overlay/v1',pid=self.pid,birth=self.birth,
            hwnd=self.hwnd,ownerHwnd=self.owner,editorPid=self.editor['pid'],editorBirth=self.editor['birth'],
            nativeOwner=int(self.host.u.GetWindow(self.hwnd,4) or 0),
            visible=bool(self.host.u.IsWindowVisible(self.hwnd)),compact=self.compact,
            geometry=list(self.host.rect(self.hwnd)),ownerGeometry=list(self.host.rect(self.owner)) if self.owner and self.host.u.IsWindow(self.owner) else None,
            updatedAt=time.time(),lastCommandId=self.command,closed=self.closed,reason=reason,
            display=self.value,backend='Tk/Win32-owned-window',simulatedInput=False,desktopCapture=False))
    def close(self):
        self.closed=True;self.root.withdraw();self.persist('closed-by-user');self.root.destroy()
    def tick(self):
        try:
            if COMMAND_FILE.exists():
                command=read(COMMAND_FILE)
                if command.get('id')!=self.command:
                    self.command=command['id']
                    if command.get('action')=='close':self.close();return
                    self.selected=command.get('run');self.offset=(0,0)
                    if command.get('compact') is not None and self.compact!=command['compact']:self.toggle()
                    self.last_rect=None
            if self.host.birth(self.editor['pid'])!=self.editor['birth']:
                self.root.withdraw();self.closed=True;self.persist('editor-exited');self.root.destroy();return
            from live_editor.windows import state
            owners=state(self.editor['pid'])
            usable=[r for r in owners if not r['minimized']]
            self.owner=max(usable or owners,key=lambda r:(self.host.rect(r['hwnd'])[2]-self.host.rect(r['hwnd'])[0])*(self.host.rect(r['hwnd'])[3]-self.host.rect(r['hwnd'])[1]))['hwnd'] if owners else None
            self.value=snapshot(select_run(selected=self.selected))
            self.status.set(self.value['status']);self.task.set(('当前任务：' if self.value['state']=='running' else '最近记录：')+self.value['title'])
            self.heading.configure(text='●  '+(self.value['status'][:16] if self.compact else '剪辑助手'))
            self.pause.configure(text='允许后续' if self.value['paused'] else '暂停后续',state='normal' if self.value['run'] else 'disabled')
            if self.value['text']!=self.last_text:
                self.text.configure(state='normal');self.text.delete('1.0','end');self.text.insert('1.0',self.value['text']);self.text.configure(state='disabled');self.last_text=self.value['text']
            reason=hidden_reason(self.owner,bool(self.owner and self.host.u.IsIconic(self.owner)),
                                 self.host.pid(self.host.u.GetForegroundWindow()),self.editor['pid'],self.pid)
            if self.owner:
                self.host.attach(self.hwnd,self.owner)
            if reason:
                self.root.withdraw();self.last_rect=None
            else:
                rect=dock_rect(self.host.rect(self.owner),self.host.work(self.owner),(366,36 if self.compact else 330),self.offset)
                # Tk treats negative positions as offsets from the screen's far
                # edge; Win32 placement below uses actual virtual-desktop pixels.
                self.root.geometry(f'{rect[2]}x{rect[3]}')
                if self.root.state()=='withdrawn':
                    self.root.deiconify();self.root.update_idletasks();self.host.attach(self.hwnd,self.owner);self.last_rect=None
                if rect!=self.last_rect:
                    self.host.place(self.hwnd,rect);self.last_rect=rect
            self.root.update_idletasks()
            self.persist(reason)
        except Exception as error:
            self.status.set('过程读取失败 · 不会重新执行任务')
            self.value=dict(self.value,state='error',status='过程读取失败 · 不会重新执行任务',error=str(error));self.persist('error: '+str(error))
        if not self.closed:self.root.after(350,self.tick)
    def run(self):self.root.mainloop()


def window_status():
    if not STATE_FILE.exists():return dict(status='not-running')
    value=read(STATE_FILE)
    alive=not value.get('closed') and time.time()-value['updatedAt']<5
    if os.name=='nt' and alive:
        host=NativeHost();alive=host.birth(value['pid'])==value['birth'] and bool(host.u.IsWindow(value['hwnd']))
        if alive:
            value['visible']=bool(host.u.IsWindowVisible(value['hwnd']))
            value['nativeOwner']=int(host.u.GetWindow(value['hwnd'],4) or 0)
    return dict(status='running' if alive else 'stopped',window=value)


def launch_window(selected=None,compact=None,close=False):
    if os.name!='nt':raise ValueError('Native companion requires Windows')
    if selected:Store().folder(selected)
    STATE_ROOT.mkdir(parents=True,exist_ok=True)
    request=str(uuid.uuid4())
    write(COMMAND_FILE,dict(id=request,action='close' if close else 'show',run=selected,compact=compact))
    previous=window_status()
    if previous['status']!='running':
        if close:return dict(status='not-running')
        python=Path(sys.executable).with_name('pythonw.exe')
        if not python.is_file():raise ValueError('The project Python GUI runtime is unavailable')
        with (STATE_ROOT/'stderr.log').open('ab') as err:
            subprocess.Popen([str(python),'-B',str(Path(__file__).resolve())],cwd=PROJECT,
                stdin=subprocess.DEVNULL,stdout=err,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
    deadline=time.monotonic()+8
    while time.monotonic()<deadline:
        value=window_status()
        if value.get('window',{}).get('lastCommandId')==request:return value
        time.sleep(.15)
    raise ValueError('Companion startup not confirmed; inspect .local/editing-overlay/stderr.log before retrying')


def main():
    STATE_ROOT.mkdir(parents=True,exist_ok=True)
    lock=(STATE_ROOT/'instance.lock').open('a+b')
    if lock.seek(0,2)==0:lock.write(b'0');lock.flush()
    lock.seek(0)
    import msvcrt
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:return 0
    try:
        # Physical pixels for both editor geometry and this window, across monitors.
        try:c.WinDLL('user32').SetProcessDpiAwarenessContext(c.c_void_p(-4))
        except (OSError,AttributeError):pass
        Overlay().run()
    finally:lock.close()
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception:
        import traceback
        with (STATE_ROOT/'stderr.log').open('a',encoding='utf-8') as error:traceback.print_exc(file=error)
        raise
