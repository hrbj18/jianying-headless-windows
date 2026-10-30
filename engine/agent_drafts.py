"""Stage a new isolated build; the editor owns hot homepage discovery."""
import json, shutil, struct, time, uuid
from pathlib import Path
import jy14_headless as j


def copy_build_snapshot(source,destination,manifest,*,pool_root=None):
    """Share immutable media while keeping every editable file independent."""
    import media_store
    source=Path(source).resolve(strict=True);destination=Path(destination).resolve()
    media=[]
    def copy_file(raw_from,raw_to):
        original=Path(raw_from);copied=Path(raw_to)
        relative=original.relative_to(source)
        info=manifest[str(relative)]
        if original.suffix.lower() in media_store.MEDIA_SUFFIXES:
            row=media_store.materialize_immutable(original,copied,info['sha256'],pool_root=pool_root)
            media.append(dict(row,relative=str(relative)))
            return str(copied)
        return shutil.copy2(original,copied)
    shutil.copytree(source,destination,copy_function=copy_file)
    j.require(j.files_manifest(destination)==manifest,'Staged build checksum mismatch')
    return media

def existing_snapshot(target,record,reopen_saved=False):
    """An explicit saved reopen never copies build bytes over native edits."""
    j.require(target.is_dir() and not target.is_symlink(),'Saved draft must be an existing real directory')
    j.require((target/'draft_content.json').is_file(),'Saved draft has no native content file')
    actual=j.files_manifest(target)
    if not reopen_saved:j.require(actual==record['files'],'Existing draft differs; staging never overwrites a saved project')
    return actual


def stage(build, open_first=False,reopen_saved=False):
    from agent_entry import AgentLock, compact
    from live_editor.paths import runtime_config, STATE_ROOT
    from live_editor.winprocess import discover, Reader
    from live_editor.pipe_transport import PipeTransport
    from live_editor.typed_args import arguments
    from live_editor.native_client import NativeEditor
    from live_editor.operations import write_json
    from live_editor.errors import LiveEditError
    from live_editor.windows import minimize
    with AgentLock():
        build=build.resolve(strict=True);record=j.verify_build(build)
        target=Path(record['target']).resolve()
        j.require(target.parent==j.nd.DRAFT_ROOT.resolve(),'Build targets a different draft root; rebuild with the shared config')
        j.require(not reopen_saved or (open_first and target.is_dir()),'Reopen-saved requires --open and an existing target')
        process=None;active=None;config=runtime_config()
        try:process=discover(config)
        except LiveEditError as error:
            if error.code!='EDITOR_NOT_UNIQUE' or (error.details or {}).get('candidates'):raise
        if process:
            try:
                with NativeEditor(config) as e:active=e.status()
            except LiveEditError as error:
                if error.code!='NO_EDIT_DRAFT':raise
            if open_first and active and Path(active['snapshot']['draft_path']).resolve()!=target:
                raise ValueError('Another draft is editing; stage without --open, then explicitly select the new draft')
        media=[]
        if target.exists():
            saved_files=existing_snapshot(target,record,reopen_saved)
        else:
            temporary=target.parent/('.agent-staging-'+uuid.uuid4().hex)
            media=copy_build_snapshot(build/'draft',temporary,record['files'])
            temporary.rename(target)
        result=dict(status='staged',draft_path=str(target),draft_id=record['draft_id'],
                    home_index_directly_written=False,editor_discovery='pending',opened=False,
                    immutable_media_files=len(media))
        if reopen_saved:
            audit=STATE_ROOT/'staging'/(record['draft_id']+'-saved-reopen-'+uuid.uuid4().hex+'.json')
            write_json(audit,dict(target=str(target),files_before_native_open=saved_files,
                build_bytes_copied=False,policy='Open existing native edits; never overwrite from build'))
            result.update(saved_draft_preserved=True,saved_reopen_audit=str(audit),build_bytes_copied=False)
        if media:
            audit=STATE_ROOT/'staging'/(record['draft_id']+'-media.json')
            for row in media:row['final_destination']=str(target/row['relative'])
            write_json(audit,{'files':media,'policy':'immutable media shared; metadata copied independently'})
            result['media_materialization_audit']=str(audit)
        if process:
            base=process['modules']['VECreator.dll']['base'];manager=base+0xef39450
            with Reader(process['pid']) as r:
                j.require(r.pointer(manager)==base+0xcafa6e0 and r.pointer(manager+0x10)==base+0xcafa740,'Unrecognized project manager')
                home=r.pointer(base+0xef390d8)
                j.require(r.pointer(home)==base+0xcaf4748,'Unrecognized Home model')
            # Startup can still be loading the configured roots. Readiness
            # polling does not dispatch or retry an editing mutation.
            deadline=time.monotonic()+20
            while True:
                with Reader(process['pid']) as r:counts=struct.unpack('<ii',r.read(manager+0x1c8,8))
                if counts==(0,0):break
                if time.monotonic()>=deadline:raise RuntimeError('Editor discovery busy; draft placed, no open/edit dispatched')
                time.sleep(.2)
            pipe=PipeTransport(process['pid'],process['birth']).start()
            try:
                pipe.call(6,object=manager,vtable=base+0xcafa6e0,name='onDraftRootPathChanged',payload=arguments([]))
                deadline=time.monotonic()+20;time.sleep(1)
                while True:
                    with Reader(process['pid']) as r:counts=struct.unpack('<ii',r.read(manager+0x1c8,8))
                    if counts==(0,0):break
                    if time.monotonic()>=deadline:raise RuntimeError('Native draft discovery pending; inspect before retrying')
                    time.sleep(.2)
                result['editor_discovery']='normal-root-rescan-requested'
                if open_first and not active:
                    pipe.call(6,object=home,vtable=base+0xcaf4748,name='onOpenProjectBtnClicked',payload=arguments([('QString',str(target))]))
                    time.sleep(2)
            finally:pipe.release()
            if active or open_first:
                # Home open returns before the async edit page has constructed
                # its video models. Observe readiness without replaying open.
                deadline=time.monotonic()+30
                while True:
                    try:
                        with NativeEditor(config) as e:
                            after=e.status()
                            if active:j.require(after['snapshot']['token']==active['snapshot']['token'],'Active edit session changed during discovery')
                            else:
                                j.require(Path(after['snapshot']['draft_path']).resolve()==target,'First open did not bind the staged draft')
                                result.update(opened=True,draft_id=after['draft_id'],report=compact(after),window=minimize(e))
                        break
                    except LiveEditError as error:
                        constructing={'NO_EDIT_DRAFT','NO_BOUND_TOOLBAR','NO_ACTIVE_VIDEO_OBJECTS',
                                      'NO_BOUND_PREVIEW','NO_BOUND_PLAYER_CONTROL','NO_BOUND_CANVAS','NO_BOUND_CURSOR'}
                        if active or error.code not in constructing:raise
                        if time.monotonic()>=deadline:
                            raise LiveEditError('STAGE_OPEN_PENDING','Open returned but edit page is not ready; inspect without replay') from error
                        time.sleep(.25)
            else:
                pipe=PipeTransport(process['pid'],process['birth']).start()
                try:result['release']=pipe.shutdown()
                finally:pipe.release()
        write_json(STATE_ROOT/'staging'/f'{record["draft_id"]}.json',result)
        return result
