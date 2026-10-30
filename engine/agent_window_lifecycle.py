"""Explicit saved-editor close through the existing Qt bridge; never force quit."""
import hashlib,shutil,time
from pathlib import Path
from live_editor.errors import LiveEditError,require
from live_editor.native_client import NativeEditor
from live_editor.window_state import current_main_window


def close_saved_editor(editor,before,audit):
    require(before['status']=='saved-and-read-back','SAVE_REQUIRED','Close requires confirmed saved state')
    require(not before['snapshot']['preview']['playing'],'PAUSE_PLAYBACK_FIRST','Playback must be paused')
    # Metadata backup only; media remains immutable in the saved draft.
    saved=audit/'saved-before-close';saved.mkdir(parents=True,exist_ok=False)
    for i,item in enumerate(before['files']):
        source=Path(item['path'])
        require(hashlib.sha256(source.read_bytes()).hexdigest()==item['sha256'],
                'SAVE_IN_PROGRESS','Saved draft changed before close')
        shutil.copy2(source,saved/f'{i:02d}-{source.name}')
    root,ctx=current_main_window(editor)
    require(ctx['token']==before['snapshot']['token'],'SESSION_CHANGED','Draft changed before close')
    # QWindow.close sends the normal cancellable close event. It neither invokes
    # proprietary realClose nor terminates a process or bypasses a save prompt.
    accepted=editor.run(root,1,'close',return_type=1,ctx=ctx)
    editor.disconnect()
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        try:
            with NativeEditor(editor.config) as probe:
                after=probe.status()
            require(after['snapshot']['token']==ctx['token'],'SESSION_CHANGED',
                    'Another draft became active after close; do not open a replacement automatically')
        except LiveEditError as error:
            if error.code=='NO_EDIT_DRAFT':
                return dict(window=dict(route='QWindow.close',accepted=accepted,simulated_input=False,
                                        process_terminated=False),editor_state='home-without-edit-draft')
            raise
        time.sleep(.25)
    raise LiveEditError('CLOSE_NOT_CONFIRMED','Close may be pending or cancelled; inspect before any new request')
