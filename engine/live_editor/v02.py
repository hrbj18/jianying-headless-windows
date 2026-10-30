"""Standalone realtime operations; every mutation is journaled and read back."""
import copy,hashlib,json,math,time,uuid,struct
from pathlib import Path
from .paths import STATE_ROOT as ROOT
from .drafts import assert_saved
from .errors import require,LiveEditError
from .operations import CommandLock,check_expected,write_json
from .winprocess import Reader,validate_objects

def segments(doc):
    return {s['id']:(t,s) for t in doc['tracks'] for s in t['segments']}

def fingerprint(doc):
    # Metadata may change while saving; retain all actual tracks and materials.
    return hashlib.sha256(json.dumps({k:doc.get(k) for k in ('tracks','materials','duration','fps','canvas_config')},sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()

def objects(editor,kind):
    ctx=editor.context();base=editor.process['modules']['VECreator.dll']['base']
    with Reader(editor.process['pid']) as r:
        valid=validate_objects(r,base,editor.discovery['objects'])
        return [int(row['address'],16) for row in valid if row['kind']==kind and
                (kind not in ('video','audio','text','transition','adjust') or r.pointer(int(row['address'],16)+0x298)==ctx['timeline'])]

def clip_object(editor,kind,segment_id):
    found=[p for p in objects(editor,kind) if editor.invoke(p,'getSegmentId',3)==segment_id]
    require(len(found)==1,'SEGMENT_NOT_UNIQUE','Expected one current clip model',{'kind':kind,'segment_id':segment_id,'count':len(found)})
    obj=found[0];require(not editor.get(obj,'isTrackLocked'),'TRACK_LOCKED','Target track is locked');return obj

def select(editor,obj):
    ctx=editor.context();require(not editor.get(ctx['control'],'isPlaying'),'PAUSE_PLAYBACK_FIRST','Playback is active')
    editor.run(ctx['canvas'],1,'unselectSegments',ctx=ctx)
    editor.run(obj,1,'selectedSegment',ctx=ctx)
    require(editor.get(obj,'selected'),'SELECTION_FAILED','Native clip selection was rejected')

def confirm(editor,token,predicate,timeout=20):
    end=time.monotonic()+timeout;last=None
    while time.monotonic()<end:
        try:
            shot=editor.inspect();require(shot['token']==token,'SESSION_CHANGED','Draft changed during operation')
            saved=editor.saved(shot);assert_saved(shot,saved)
            require(predicate(saved['timeline']),'SAVE_PENDING','Waiting for requested native result')
            return editor.status(),saved['timeline']
        except LiveEditError as ex:
            if ex.code not in ('SAVE_PENDING','SAVE_IN_PROGRESS'):raise
            last=ex
        time.sleep(.2)
    raise LiveEditError('SAVE_TIMEOUT','Mutation may be applied; inspect before retrying',str(last))

def transaction(editor,label,dispatch,predicate,expected=None):
    """No retry on ambiguous dispatch; keep actual native undo history."""
    with CommandLock():
        report=editor.status()
        if expected:check_expected(expected,report)
        saved=editor.saved(report['snapshot']);assert_saved(report['snapshot'],saved)
        require(not report['snapshot']['preview']['playing'],'PAUSE_PLAYBACK_FIRST','Playback is active')
        oid=str(uuid.uuid4());folder=ROOT/'evidence/v02-operations'/oid;folder.mkdir(parents=True)
        for p,h in zip(saved['paths'],saved['hashes']):
            data=p.read_bytes();require(hashlib.sha256(data).hexdigest()==h,'REVISION_CHANGED','Draft changed during backup')
            target=folder/'before'/p.relative_to(Path(report['snapshot']['draft_path']));target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        entry=dict(id=oid,label=label,state='dispatching',started=time.time(),before=report)
        write_json(folder/'result.json',entry)
        try:
            dispatch(report,saved['timeline'])
            result,doc=confirm(editor,report['snapshot']['token'],predicate)
            entry.update(state='confirmed',finished=time.time(),after=result,content_sha256=fingerprint(doc));write_json(folder/'result.json',entry)
            return result,doc,oid
        except Exception as ex:
            entry.update(state='needs-inspection',finished=time.time(),error=ex.as_dict() if isinstance(ex,LiveEditError) else str(ex));write_json(folder/'result.json',entry);raise

def history(editor,action,predicate):
    require(action in ('undo','redo'),'INVALID_ACTION','Expected undo or redo')
    return transaction(editor,action,lambda r,d:editor.rpc('history',action,r['snapshot']['token'],r['snapshot']['revision']),predicate)

def audio_fade(editor,segment_id,edge,seconds):
    require(edge in ('in','out'),'INVALID_EDGE','Expected in or out')
    require(math.isfinite(seconds) and 0<=seconds<=10,'INVALID_DURATION','Fade must be 0..10 seconds')
    duration=round(seconds*1_000_000);obj=clip_object(editor,'audio',segment_id)
    def current(doc):
        segment=segments(doc)[segment_id][1]
        refs=segment.get('extra_material_refs',[])
        fades=[m for m in doc['materials'].get('audio_fades',[]) if m['id'] in refs]
        return (fades[0].get('fade_'+edge+'_duration',0) if fades else 0)
    def change(r,doc):
        target=segments(doc).get(segment_id);require(target is not None and target[0]['type']=='audio','WRONG_SEGMENT','Expected an audio clip')
        require(duration<=target[1]['target_timerange']['duration'],'INVALID_DURATION','Fade exceeds clip duration')
        select(editor,obj)
        editor.invoke_typed(obj,'setFade'+edge.title()+'Duration',[('double',float(duration)),('bool',True)],selection=obj,segment_id=segment_id)
    return transaction(editor,'audio-fade-'+edge,change,lambda d:current(d)==duration)

def text_content(doc,segment_id):
    segment=segments(doc)[segment_id][1]
    material=next(m for m in doc['materials']['texts'] if m['id']==segment['material_id'])
    return material,json.loads(material['content'])

def subtitle(editor,segment_id,text):
    require(isinstance(text,str) and 0<len(text)<=300 and '\0' not in text,'INVALID_TEXT','Expected 1..300 text characters')
    obj=clip_object(editor,'text',segment_id)
    def change(r,doc):
        require(segments(doc)[segment_id][0]['type']=='text','WRONG_SEGMENT','Expected a text clip')
        select(editor,obj);editor.refresh()
        panels=[p for p in objects(editor,'text_rich') if editor.invoke(p,'contentID',3)==segment_id]
        require(len(panels)==1,'TEXT_PANEL_NOT_BOUND','Cannot bind one current text panel')
        editor.invoke_typed(panels[0],'correctContent',[('QString',text)],selection=obj,segment_id=segment_id)
    return transaction(editor,'subtitle-content',change,lambda d:text_content(d,segment_id)[1]['text']==text)

def audio_keyframe(editor,segment_id,index,db):
    require(isinstance(index,int) and index>=0 and math.isfinite(db) and -60<=db<=6,'INVALID_VOLUME','Invalid volume keyframe or dB')
    obj=clip_object(editor,'audio',segment_id);linear=0 if db<=-60 else 10**(db/20)
    def values(doc):
        entries=[k for k in segments(doc)[segment_id][1].get('common_keyframes',[]) if k['property_type']=='KFTypeVolume']
        require(len(entries)==1 and index<len(entries[0]['keyframe_list']),'KEYFRAME_MISSING','Expected one existing audio keyframe curve')
        return entries[0]['keyframe_list']
    def change(r,doc):
        rows=values(doc);require(editor.get(obj,'volumeKeyFrameCount')==len(rows),'KEYFRAME_MISMATCH','Visible and saved audio keyframes differ')
        select(editor,obj)
        editor.invoke_typed(obj,'setKeyFrameVolume',[('int',index),('double',float(db)),('bool',True)],selection=obj,segment_id=segment_id)
    return transaction(editor,'audio-keyframe-volume',change,lambda d:abs(values(d)[index]['values'][0]-linear)<1e-5)

def media_binding(editor):
    with Reader(editor.process['pid']) as r:
        rows=[(p,r.pointer(p+0x150),r.pointer(p+0x160)) for p in objects(editor,'media_inspector') if r.pointer(p+0x160)]
    require(len(rows)==1,'MEDIA_GRID_NOT_UNIQUE','Expected one current normal local-media grid')
    return rows[0]

def media_items(editor,source=None):
    inspector,importer,grid=media_binding(editor);found=[]
    with Reader(editor.process['pid']) as r:
        candidates=[p for p in objects(editor,'media_item') if r.pointer(p+0x288)==grid]
    for p in candidates:
        file=editor.get(p,'filePath')
        if source is None or Path(file).resolve()==Path(source).resolve():
            found.append(dict(object=p,file_path=file,title=editor.get(p,'title'),ready=bool(editor.get(p,'importBtnEnabled')) and not editor.get(p,'isUnsupported') and not editor.get(p,'isPlaceHolderMaterial'),grid=grid))
    return found

def timeline_preview(editor):
    # Normal media-library preview teardown; does not activate a window.
    grid=media_binding(editor)[2]
    editor.run(grid,1,'endPreview')
    return editor.inspect()['preview']

def import_media(editor,source):
    source=Path(source).resolve();require(source.is_file(),'MEDIA_NOT_FOUND','Source media is absent')
    require(source.suffix.lower() in ('.jpg','.jpeg','.png','.mp4','.mov','.wav','.mp3'),'MEDIA_TYPE','Unsupported local test media extension')
    with CommandLock():
        timeline_preview(editor)
        report=editor.status();token=report['snapshot']['token'];before=fingerprint(editor.saved()['timeline'])
        previous=media_items(editor,source)
        if previous:
            require(len(previous)==1 and previous[0]['ready'],'MEDIA_NOT_READY','Existing material is not ready')
            return dict(status='already-imported',item=previous[0],report=report)
        inspector,importer,grid=media_binding(editor);oid=str(uuid.uuid4());record=ROOT/'evidence/v02-operations'/oid/'result.json'
        entry=dict(id=oid,label='import-media',state='dispatching',source=str(source),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),started=time.time(),before=report,before_content_sha256=before)
        write_json(record,entry)
        try:
            ctx=editor.context();require(ctx['token']==token,'SESSION_CHANGED','Draft changed before import')
            with Reader(editor.process['pid']) as r:vt=r.pointer(inspector)
            editor.pipe.call(7,object=inspector,manager=ctx['manager'],timeline=ctx['timeline'],vtable=vt,timeline_id=ctx['timeline_id'],value=struct.pack('<QQ',importer,grid),payload=str(source).encode('utf-8')+b'\0')
            deadline=time.monotonic()+45
            while time.monotonic()<deadline:
                editor.refresh();require(editor.context()['token']==token,'SESSION_CHANGED','Draft changed during asynchronous import')
                found=media_items(editor,source)
                if len(found)==1 and found[0]['ready']:break
                time.sleep(.3)
            else:raise LiveEditError('IMPORT_TIMEOUT','Import may have been submitted; inspect before retrying')
            timeline_preview(editor)
            after=editor.status();require(fingerprint(editor.saved()['timeline'])==before,'UNEXPECTED_TIMELINE_CHANGE','Library import unexpectedly changed the timeline')
            require(hashlib.sha256(source.read_bytes()).hexdigest()==entry['source_sha256'],'SOURCE_CHANGED','Input file changed')
            result=dict(status='imported-and-visible',item=found[0],operation_id=oid,report=after)
            entry.update(state='confirmed',finished=time.time(),after=result);write_json(record,entry);return result
        except Exception as ex:
            entry.update(state='needs-inspection',error=str(ex),finished=time.time());write_json(record,entry);raise

def insert_media(editor,source):
    found=media_items(editor,source);require(len(found)==1 and found[0]['ready'],'MEDIA_NOT_READY','Import exactly one ready local material first')
    item=found[0];prior=set(segments(editor.saved()['timeline']))
    def change(r,doc):
        require(set(segments(doc))==prior,'REVISION_CHANGED','Timeline changed before insertion')
        # Normal add inserts at a main-track boundary near the cursor. Explicitly
        # append at the end so existing captions/clips cannot be rippled forward.
        shot=editor.inspect();editor.rpc('seek',shot['token'],shot['revision'],doc['duration'])
        with Reader(editor.process['pid']) as reader:vt=reader.pointer(item['grid'])
        editor.run(item['object'],11,value=struct.pack('<QQ',item['grid'],vt))
        editor.refresh()
    return transaction(editor,'insert-local-media',change,lambda d:len(set(segments(d))-prior)==1)

def move_video(editor,segment_id,target_track_id,seconds,probe=False):
    require(math.isfinite(seconds) and seconds>=0,'INVALID_POSITION','Move requires a nonnegative time')
    target_us=round(seconds*1_000_000);obj=clip_object(editor,'video',segment_id)
    def change(report,doc):
        indexed=segments(doc);source_track,segment=indexed[segment_id]
        tracks=[t for t in doc['tracks'] if t['type']=='video'];target=next((t for t in tracks if t['id']==target_track_id),None)
        require(target is not None and tracks.index(target)>0 and tracks.index(source_track)>0,'V02_MOVE_SCOPE','Move is verified between existing secondary video tracks')
        require(segment.get('speed',1)==1 and not segment.get('group_id') and not segment.get('common_keyframes') and not segment.get('is_loop') and not segment.get('transition_id'),'V02_MOVE_SCOPE','Grouped, animated or variable-speed clips require separate validation')
        duration=segment['target_timerange']['duration'];fps=doc.get('fps',30)
        frame_time=round(round(target_us*fps/1_000_000)*1_000_000/fps)
        require(abs(target_us-frame_time)<=1,'FRAME_ALIGNMENT','Move must land on a video frame')
        require(target_us+duration<=doc['duration'],'V02_MOVE_SCOPE','Current test moves stay inside the existing film duration')
        require(all(s['id']==segment_id or s['target_timerange'].get('start',0)>=target_us+duration or s['target_timerange'].get('start',0)+s['target_timerange']['duration']<=target_us for s in target['segments']),'DESTINATION_OVERLAP','Destination interval is occupied')
        ctx=editor.context();rows=[]
        with Reader(editor.process['pid']) as r:
            canvas=r.pointer(ctx['canvas']+0x1d8);entrance=r.pointer(obj+0x180);vt=r.pointer(obj)
            for p in ctx['videos']:
                sid=editor.invoke(p,'getSegmentId',3);track=indexed[sid][0]['id']
                rows.append(struct.pack('<QQddd40s40s',p,r.pointer(p),*[editor.get(p,n) for n in ('x','width','pixelSize')],sid.encode('ascii'),track.encode('ascii')))
        data=struct.pack('<IIqii40s40s40sQQ',1,len(rows),target_us,tracks.index(target),ctx['sid'],segment_id.encode('ascii'),source_track['id'].encode('ascii'),target_track_id.encode('ascii'),canvas,entrance)+b''.join(rows)
        editor.pipe.call(10,object=obj,manager=ctx['manager'],timeline=ctx['timeline'],vtable=vt,timeline_id=ctx['timeline_id'],name=probe if isinstance(probe,str) else 'probe' if probe else '',value=struct.pack('<Q',ctx['control']),payload=data)
        editor.refresh()
    def result(doc):
        row=segments(doc)[segment_id]
        return True if probe else row[0]['id']==target_track_id and abs(row[1]['target_timerange'].get('start',0)-target_us)<=1
    return transaction(editor,'move-readonly-probe' if probe else 'move-video',change,result)

def insert_audio_at(editor,source,seconds):
    source=Path(source).resolve()
    require(source.suffix.lower() in ('.wav','.mp3') and math.isfinite(seconds) and seconds>=0,'INVALID_AUDIO','Expected a local WAV/MP3 and a nonnegative position')
    found=media_items(editor,source);require(len(found)==1 and found[0]['ready'],'MEDIA_NOT_READY','Import one ready audio material first')
    item=found[0];before=editor.saved()['timeline'];prior=segments(before);position=round(seconds*1_000_000)
    require(position<before['duration'],'INVALID_POSITION','Audio insertion must be inside this test timeline')
    def change(report,doc):
        require(segments(doc)==prior,'REVISION_CHANGED','Timeline changed before audio insertion')
        shot=editor.inspect();editor.rpc('seek',shot['token'],shot['revision'],position)
        with Reader(editor.process['pid']) as r:vt=r.pointer(item['grid'])
        editor.run(item['object'],11,value=struct.pack('<QQ',item['grid'],vt));editor.refresh();timeline_preview(editor)
    def result(doc):
        rows=segments(doc);new=set(rows)-set(prior)
        if len(new)!=1 or doc['duration']!=before['duration']:return False
        track,segment=rows[next(iter(new))]
        old_ids=[t['id'] for t in before['tracks']]
        if [t['id'] for t in doc['tracks'] if t['id'] in old_ids]!=old_ids:return False
        inserted_index=next(i for i,t in enumerate(doc['tracks']) if t['id']==track['id'])
        for k,(old_track,old_segment) in prior.items():
            if rows[k][0]['id']!=old_track['id']:return False
            expected=copy.deepcopy(old_segment)
            # A new audio track renumbers the subsequent native render rows.
            # Verify that one known shift; retain every timing/content field.
            if 'track_render_index' in expected and old_ids.index(old_track['id'])>=inserted_index:expected['track_render_index']+=1
            if rows[k][1]!=expected:return False
        material=next((m for m in doc['materials'].get('audios',[]) if m['id']==segment['material_id']),None)
        return track['type']=='audio' and abs(segment['target_timerange'].get('start',0)-position)<=1 and material is not None and Path(material['path']).resolve()==source
    return transaction(editor,'insert-audio-at',change,result)

def audio_volume(editor,segment_id,db):
    require(math.isfinite(db) and -60<=db<=6,'INVALID_VOLUME','Volume must be -60..6 dB')
    obj=clip_object(editor,'audio',segment_id);linear=0 if db<=-60 else 10**(db/20)
    def change(report,doc):
        s=segments(doc)[segment_id][1]
        require(not any(k['property_type']=='KFTypeVolume' for k in s.get('common_keyframes',[])) and editor.get(obj,'volumeKeyFrameCount')==0,'KEYFRAMED_VOLUME','Use explicit audio-keyframe adjustment for animated volume')
        select(editor,obj);editor.invoke_typed(obj,'setVolumeLine',[('int',-1),('int',-1),('double',float(db)),('double',float(db)),('bool',True)],selection=obj,segment_id=segment_id)
    return transaction(editor,'audio-volume-db',change,lambda d:abs(segments(d)[segment_id][1].get('volume',1)-linear)<1e-5)

def video_panel(editor,segment_id):
    obj=clip_object(editor,'video',segment_id);select(editor,obj);editor.refresh();found=[]
    with Reader(editor.process['pid']) as r:
        for p in objects(editor,'video_basic'):
            model=r.pointer(p+0xa8);start=r.pointer(model+8);end=r.pointer(model+16)
            if end-start!=32:continue
            n,cap=struct.unpack('<QQ',r.read(start+16,16))
            if n!=36:continue
            sid=r.read(start if cap<16 else r.pointer(start),n).decode('ascii')
            if sid==segment_id:found.append(p)
    require(len(found)==1,'VIDEO_PANEL_NOT_BOUND','Expected one single-selected current video panel')
    return obj,found[0]

def attached_materials(doc,segment_id,key):
    refs=segments(doc)[segment_id][1].get('extra_material_refs',[])
    return [m for m in doc['materials'].get(key,[]) if m['id'] in refs]

def filter_value(editor,segment_id,value):
    require(math.isfinite(value) and 0<=value<=1,'INVALID_FILTER_VALUE','Filter intensity must be 0..1')
    obj,panel=video_panel(editor,segment_id)
    def change(report,doc):
        filters=[m for m in attached_materials(doc,segment_id,'effects') if m['type']=='filter']
        require(len(filters)==1,'FILTER_REQUIRED','Expected one existing filter')
        editor.invoke_typed(panel,'acceptFilterValue',[('double',float(value*100)),('bool',False)],selection=obj,segment_id=segment_id)
    def result(doc):
        rows=[m for m in attached_materials(doc,segment_id,'effects') if m['type']=='filter']
        return len(rows)==1 and abs(rows[0].get('value',0)-value)<1e-5
    return transaction(editor,'filter-intensity',change,result)

def remove_filter(editor,segment_id):
    obj,panel=video_panel(editor,segment_id)
    def change(report,doc):
        require(any(m['type']=='filter' for m in attached_materials(doc,segment_id,'effects')),'FILTER_REQUIRED','Expected an existing filter')
        editor.invoke_typed(panel,'removeFilterBtnClicked',selection=obj,segment_id=segment_id)
    return transaction(editor,'filter-remove',change,lambda d:not any(m['type']=='filter' for m in attached_materials(d,segment_id,'effects')))

def remove_effect(editor,segment_id):
    obj,panel=video_panel(editor,segment_id)
    def change(report,doc):
        require(len(attached_materials(doc,segment_id,'video_effects'))==1,'SINGLE_EFFECT_REQUIRED','Current test removes one existing named effect')
        name=editor.get(panel,'effectName')
        editor.invoke_typed(panel,'removeEffect',[('int',0),('QString',name)],selection=obj,segment_id=segment_id)
    return transaction(editor,'video-effect-remove',change,lambda d:not attached_materials(d,segment_id,'video_effects'))

def transition_panel(editor,transition_id):
    obj=clip_object(editor,'transition',transition_id);select(editor,obj)
    end=time.monotonic()+10
    while True:
        editor.refresh();ctx=editor.context();found=[]
        with Reader(editor.process['pid']) as r:
            for p in objects(editor,'transition_panel'):
                start=p+0x58;n,cap=struct.unpack('<QQ',r.read(start+16,16))
                if n!=36:continue
                sid=r.read(start if cap<16 else r.pointer(start),n).decode('ascii')
                if sid==transition_id and r.pointer(p+0x108)==ctx['manager']:found.append(p)
        if len(found)==1:return obj,found[0]
        require(len(found)<2,'TRANSITION_PANEL_NOT_UNIQUE','Multiple transition panels are bound')
        if time.monotonic()>=end:raise LiveEditError('TRANSITION_PANEL_NOT_BOUND','No initialized transition panel belongs to the current edit session')
        time.sleep(.2)

def transition_duration(editor,transition_id,seconds):
    require(math.isfinite(seconds) and seconds>0,'INVALID_DURATION','Transition duration must be finite positive seconds')
    obj,panel=transition_panel(editor,transition_id);target_us=round(seconds*1_000_000)
    def change(report,doc):
        rows=[m for m in doc['materials'].get('transitions',[]) if m['id']==transition_id]
        require(len(rows)==1,'TRANSITION_REQUIRED','Expected one current transition material')
        require(not editor.get(panel,'isMultiSelect'),'MULTIPLE_TRANSITIONS','Select one transition')
        require(editor.get(panel,'minDuration')<=seconds<=editor.get(panel,'maxDuration'),'INVALID_DURATION','Transition duration exceeds the current native limits')
        editor.invoke_typed(panel,'updateDuration',[('float',seconds)],selection=obj,segment_id=transition_id)
    def result(doc):
        rows=[m for m in doc['materials'].get('transitions',[]) if m['id']==transition_id]
        return len(rows)==1 and abs(rows[0]['duration']-target_us)<=1
    return transaction(editor,'transition-duration',change,result)
