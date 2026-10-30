"""Minimize the current Qt editor without focus changes or input simulation."""
import struct
from .winprocess import Reader
from .errors import require

def current_main_window(editor):
    ctx=editor.context();base=editor.process['modules']['Qt6Gui.dll']['base']
    # Exact-build QGuiApplication::focusWindow() leaf loads this Qt global.
    # transientParent() uses a QPointer at private-data +0x138/+0x140.
    # Read-only evidence: research/qt_focus_export.json. No ownership is changed.
    with Reader(editor.process['pid']) as r:
        obj=r.pointer(base+0x6976d8);seen=set();root=None
        while obj and obj not in seen and len(seen)<5:
            seen.add(obj)
            if editor.get(obj,'objectName')=='MainWindow' and editor.get(obj,'title')=='剪映专业版':
                root=obj;break
            data=r.pointer(obj+8);control=r.pointer(data+0x138)
            obj=r.pointer(data+0x140) if control and struct.unpack('<i',r.read(control+4,4))[0] else 0
        if root is None:
            # A minimized/unfocused editor has no focusWindow. Exact-build
            # QGuiApplication::allWindows() copies this QList (header/data/size).
            # Static evidence: haike-omni-r4-20261027-172156-ad5a7c/analysis/
            # qt-all-windows-static.txt. discover() verifies Qt6Gui.dll's hash.
            address=base+0x697740;raw=r.read(address,24)
            _,data,count=struct.unpack('<QQq',raw)
            require(0<=count<=512,'EDITOR_WINDOW_LIST_INVALID','Qt window list size is invalid')
            pointers=r.read(data,count*8) if count else b''
            candidates=[]
            for candidate in struct.unpack('<'+'Q'*count,pointers):
                if editor.get(candidate,'objectName')=='MainWindow' and editor.get(candidate,'title')=='剪映专业版':
                    candidates.append(candidate)
            require(r.read(address,24)==raw and (r.read(data,count*8) if count else b'')==pointers,
                    'EDITOR_WINDOW_LIST_CHANGED','Qt windows changed during discovery')
            require(len(candidates)<=1,'EDITOR_WINDOW_NOT_UNIQUE','Multiple main editor windows found')
            if candidates:root=candidates[0]
    require(root is not None,'EDITOR_WINDOW_NOT_BOUND','No initialized current main editor Qt window was found')
    require(editor.context()['token']==ctx['token'],'SESSION_CHANGED','Draft changed before window operation')
    return root,ctx

def minimize_current_editor(editor):
    root,ctx=current_main_window(editor)
    editor.run(root,1,'showMinimized',ctx=ctx)
    return dict(route='QWindow.showMinimized',object=hex(root),activate=False,simulated_input=False)
