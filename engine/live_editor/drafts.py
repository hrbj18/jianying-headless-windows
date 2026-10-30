"""Read-only saved-file confirmation. Live drafts are never written here."""
import hashlib
import json
import sys
from pathlib import Path
from .errors import require

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

class DraftReader:
    def __init__(self,config):
        self.roots=[Path(p).resolve() for p in config['draft_roots']]
        sys.path.insert(0,str(Path(config['headless_project'])/'engine'))
        from local_config import configure_environment
        configure_environment()
        import jy14_headless as j
        self.codec=j.nd.helper()
    def read(self,shot):
        folder=Path(shot['draft_path']).resolve()
        require(any(folder.is_relative_to(p) and folder!=p for p in self.roots),'DRAFT_OUTSIDE_ROOTS','Current draft is outside configured roots')
        project=folder/'Timelines/project.json'
        require(project.is_file(),'UNSUPPORTED_DRAFT_LAYOUT','A declared main timeline is required')
        project_before=digest(project)
        index=json.loads(project.read_text(encoding='utf-8-sig'))
        tid=shot['timeline_id']
        require(index.get('main_timeline_id')==tid,'TIMELINE_MISMATCH','Current timeline differs from saved main timeline')
        paths=[folder/'draft_meta_info.json',folder/'Timelines'/tid/'draft_content.json',folder/'draft_content.json']
        require(all(p.is_file() for p in paths),'DRAFT_FILES_MISSING','Saved draft files are incomplete')
        before=[digest(p) for p in paths]
        meta,main,root=[self.codec._decrypt_metadata_in_memory(p) for p in paths]
        after=[digest(p) for p in paths]
        require(before==after and digest(project)==project_before,'SAVE_IN_PROGRESS','Draft changed while it was read')
        require(main.get('id')==tid and root.get('id')==tid,'TIMELINE_MISMATCH','Saved timeline identity differs from active timeline')
        require(meta.get('draft_id'),'INVALID_DRAFT_ID','Draft has no stable identity')
        return dict(draft_id=meta['draft_id'],draft_name=meta.get('draft_name',folder.name),
                    timeline=main,root=root,paths=paths,hashes=after,project=project)

def assert_saved(shot,saved):
    for document in (saved['timeline'],saved['root']):
        videos={s['id']:s for t in document['tracks'] if t['type']=='video' for s in t['segments']}
        require(set(videos)=={c['segmentID'] for c in shot['clips']},'SAVE_PENDING','Visible video clips and saved clips differ')
        for clip in shot['clips']:
            segment=videos[clip['segmentID']]
            require(abs(segment['target_timerange']['duration']-clip['durationUs'])<2,'SAVE_PENDING','Clip duration has not been saved')
            require(abs(segment['target_timerange'].get('start',0)-clip['x']/clip['pixelSize'])<2,'SAVE_PENDING','Clip position has not been saved')
    require(saved['root']==saved['timeline'],'SAVE_PENDING','Main and root timeline mirrors differ')
    parts=shot['preview']['total'].split(':')
    require(len(parts)==4 and all(p.isdigit() for p in parts),'PREVIEW_UNREADABLE','Cannot interpret native preview duration')
    hours,minutes,seconds,frames=map(int,parts);fps=saved['timeline'].get('fps',30)
    preview_us=((hours*60+minutes)*60+seconds+frames/fps)*1_000_000
    require(abs(preview_us-saved['timeline']['duration'])<=1_000_000/fps,'SAVE_PENDING','Preview duration and saved timeline differ')
    return True
