"""Normal Qt application quit, only after the editing page is already closed.

Uses the unchanged, pinned bridge and public QCoreApplication.quit() slot. An
exit request is never repeated or converted into process termination.
"""
import ctypes as c
import ctypes.wintypes as w
import json
import time

from live_editor.errors import LiveEditError,require
from live_editor.paths import STATE_ROOT,runtime_config
from live_editor.winprocess import discover,Reader,k
from live_editor.native_client import NativeEditor
from live_editor.pipe_transport import PipeTransport,checked
from live_editor.operations import write_json


def quit_home(pid,birth,request_id):
    from agent_entry import AgentLock
    request=dict(action='quit-home',pid=pid,birth=birth,request_id=str(request_id))
    journal=STATE_ROOT/'app-lifecycle'/str(request_id)/'result.json'
    with AgentLock():
        if journal.is_file():
            prior=json.loads(journal.read_text(encoding='utf-8'))
            require(prior['request']==request,'REQUEST_ID_CONFLICT','Different lifecycle request')
            require(prior['state']=='confirmed','APP_QUIT_UNCERTAIN',
                    'Inspect the existing quit request; never dispatch it again')
            return dict(prior['result'],already_completed=True,dispatched=False)
        config=runtime_config();process=discover(config)
        require((process['pid'],process['birth'])==(pid,birth),'PROCESS_CHANGED',
                'The explicitly selected process generation changed')
        # A successful connection is evidence that a draft is still open.
        # Do not turn arbitrary discovery/transport errors into a Home state.
        try:
            with NativeEditor(config) as editor:active=editor.status()
        except LiveEditError as error:
            require(error.code=='NO_EDIT_DRAFT','HOME_STATE_UNPROVEN',
                    'Cannot prove the editor is at Home; nothing will be closed')
        else:
            require(False,'ACTIVE_EDIT_DRAFT',
                    'Save and normally close the active editing page before quitting')
        with Reader(pid) as reader:
            require(reader.birth()==birth,'PROCESS_CHANGED','Process generation changed')
            core=process['modules']['Qt6Core.dll']['base']
            application=reader.pointer(core+0x4d7580)  # Exact-build exported QCoreApplication::self.
            require(application,'APPLICATION_NOT_BOUND','Native application singleton is absent')
            private=reader.pointer(application+8)
            require(private and reader.pointer(private+8)==application,'APPLICATION_NOT_BOUND',
                    'Native application singleton is not a current QObject')
            vtable=reader.pointer(application)
        record=dict(request=request,state='prepared',started=time.time(),home_verified=True,
                    application=hex(application),restart_executable=process['modules']['JianyingPro.exe']['path'])
        write_json(journal,record)
        handle=checked(k.OpenProcess(0x101000,False,pid),'Observe the exact selected application process')
        channel=PipeTransport(pid,birth)
        try:
            channel.start()
            record['state']='dispatching';write_json(journal,record)
            call_error=None
            try:
                channel.call(1,object=application,vtable=vtable,name='quit')
            except LiveEditError as error:
                # The normal shutdown may close its pipe before the reply.
                # Only the observed normal process exit can resolve that case.
                call_error=error.as_dict()
            code=w.DWORD();deadline=time.monotonic()+15
            while True:
                checked(k.GetExitCodeProcess(handle,c.byref(code)),'Observe native application exit')
                if code.value!=259:break
                require(time.monotonic()<deadline,'APP_QUIT_NOT_CONFIRMED',
                        'Normal quit may be pending or cancelled; no force termination or replay')
                time.sleep(.2)
            require(code.value==0,'APP_EXIT_ABNORMAL','Native application did not exit normally')
            result=dict(status='confirmed',action='quit-home',pid=pid,birth=birth,
                        request_id=str(request_id),audit=str(journal),home_verified=True,
                        route='QCoreApplication.quit public Qt slot',exit_code=code.value,
                        process_exited=True,force_termination=False,simulated_input=False,
                        dispatched=True,already_completed=False,call_error=call_error,
                        restart_executable=record['restart_executable'])
            record.update(state='confirmed',result=result,finished=time.time())
            write_json(journal,record)
            return result
        except Exception as error:
            record.update(state='needs-inspection',error=str(error),finished=time.time())
            write_json(journal,record)
            raise
        finally:
            channel.release()
            k.CloseHandle(handle)
