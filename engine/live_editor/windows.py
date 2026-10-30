"""Read window state; minimize through the current Qt object, with no input."""
import ctypes as c
from ctypes import wintypes as w
from .window_state import minimize_current_editor

def state(pid):
    u=c.WinDLL('user32',use_last_error=True)
    u.IsWindowVisible.argtypes=[w.HWND];u.IsWindowVisible.restype=w.BOOL
    u.IsIconic.argtypes=[w.HWND];u.IsIconic.restype=w.BOOL
    u.GetWindowThreadProcessId.argtypes=[w.HWND,c.POINTER(w.DWORD)]
    u.GetWindowTextW.argtypes=[w.HWND,w.LPWSTR,c.c_int]
    callback=c.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM);rows=[]
    @callback
    def visit(hwnd,unused):
        owner=w.DWORD();u.GetWindowThreadProcessId(hwnd,c.byref(owner))
        if owner.value==pid and u.IsWindowVisible(hwnd):
            title=c.create_unicode_buffer(1024);u.GetWindowTextW(hwnd,title,len(title))
            if title.value=='剪映专业版':rows.append(dict(hwnd=int(hwnd),minimized=bool(u.IsIconic(hwnd))))
        return True
    u.EnumWindows.argtypes=[callback,w.LPARAM];u.EnumWindows.restype=w.BOOL
    if not u.EnumWindows(visit,0):raise OSError('Window enumeration failed')
    return rows

def minimize(editor):
    rows=state(editor.process['pid'])
    if not rows:raise ValueError('No current Jianying main window')
    route={'route':'already-minimized','activate':False,'simulated_input':False} if all(r['minimized'] for r in rows) else minimize_current_editor(editor)
    rows=state(editor.process['pid'])
    if not rows or not all(r['minimized'] for r in rows):raise ValueError('Minimize was not confirmed')
    return dict(route=route,windows=rows)
