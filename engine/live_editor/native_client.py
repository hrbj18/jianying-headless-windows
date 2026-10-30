"""Current editor identity + native Qt pipe connection, exact supported build."""
import struct
import threading
from .client import LiveEditor
from .errors import LiveEditError,require
from .pipe_transport import PipeTransport
from .pipe_transport import serialized
from .typed_args import arguments
from .winprocess import Reader,discover,scan_objects,validate_objects

class NativeEditor(LiveEditor):
    def __init__(self,config=None):
        super().__init__(config);self.pipe=None;self.context_data=None;self.lock=threading.RLock();self.rpc_lock=self.lock
    @serialized
    def connect(self):
        self.disconnect();self.process=discover(self.config);self.discovery=scan_objects(self.process)
        require(any(r['kind']=='video' for r in self.discovery['objects']),'NO_EDIT_DRAFT','No video editing page found')
        self.pipe=PipeTransport(self.process['pid'],self.process['birth'])
        try:self.pipe.start();self.trace('pipe-connected');self.context();return self
        except Exception:self.pipe.release();self.pipe=None;raise
    @serialized
    def disconnect(self):
        if self.pipe:self.pipe.release();self.pipe=None;self.trace('pipe-client-disconnected')
    @serialized
    def shutdown(self):
        require(self.pipe is not None,'DISCONNECTED','No current bridge')
        result=self.pipe.shutdown();self.pipe=None;self.trace('pipe-module-unloaded');return result
    @serialized
    def confirm_saved(self,*args,**kwargs):return super().confirm_saved(*args,**kwargs)
    def refresh(self,rescan=True):
        if rescan:self.discovery=scan_objects(self.process)
        return self.context()
    def context(self):
        process=self.process;base=process['modules']['VECreator.dll']['base']
        def one(rows,code):require(len(rows)==1,code,'Active editor binding is ambiguous or absent',{'count':len(rows)});return rows[0]
        with Reader(process['pid']) as r:
            require(r.birth()==process['birth'],'PROCESS_CHANGED','Editor was restarted')
            valid=validate_objects(r,base,self.discovery['objects'])
            def rows(kind):return [int(row['address'],16) for row in valid if row['kind']==kind]
            def at(p,o):return r.pointer(p+o)
            def safe_match(f,ps):
                result=[]
                for p in ps:
                    try:
                        if f(p):result.append(p)
                    except LiveEditError:pass
                return result
            def qstr(p):
                length=struct.unpack('<q',r.read(p+16,8))[0];require(0<=length<=2048,'INVALID_STRING','Invalid QString')
                return r.read(at(p,8),length*2).decode('utf-16-le') if length else ''
            def stdstr(p):
                n,cap=struct.unpack('<QQ',r.read(p+16,16));require(0<=n<32768 and cap>=n,'INVALID_DRAFT_PATH','Invalid native draft path')
                return r.read(p if cap<16 else at(p,0),n).decode('utf-8') if n else ''
            manager=one(safe_match(lambda p:at(at(p,0x120),0)==base+0xac355a8,rows('manager')),'NO_UNIQUE_ACTIVE_TIMELINE')
            timeline=at(manager,0x120);timeline_id=qstr(timeline+0x688)
            require(len(timeline_id)==36,'INVALID_TIMELINE_ID','Timeline ID unavailable')
            toolbar=one(safe_match(lambda p:at(at(p,0xe8),0x48)==manager and at(at(p,0xe8),0x58)==timeline,rows('toolbar')),'NO_BOUND_TOOLBAR')
            videos=safe_match(lambda p:at(p,0x298)==timeline,rows('video'))
            require(videos,'NO_ACTIVE_VIDEO_OBJECTS','Current timeline has no recognized video model')
            entrance=at(videos[0],0x180)
            require(at(entrance,0)==base+0xd3aaa68,'SESSION_INTERFACE_MISMATCH','Edit session interface mismatch')
            sid=struct.unpack('<i',r.read(at(entrance,0x28)+0x30,4))[0]
            require(sid>0,'NO_EDIT_SESSION','No current edit session')
            require(all(at(p,0x180)==entrance for p in videos),'MIXED_EDIT_SESSIONS','Video models belong to different sessions')
            draft_player=at(videos[0],0x170)
            player=one(safe_match(lambda p:at(at(p,0x1b0),0x1d8)==draft_player,rows('player')),'NO_BOUND_PREVIEW')
            control=one(safe_match(lambda p:at(p,0x108)==at(player,0x1d0),rows('player_control')),'NO_BOUND_PLAYER_CONTROL')
            canvas=one(safe_match(lambda p:at(at(p,0x1d8),0x68)==timeline and at(at(p,0x1d8),0x518)==entrance and at(at(p,0x1d8),0x528)==draft_player,rows('canvas')),'NO_BOUND_CANVAS')
            cursor=one(safe_match(lambda p:at(p,0x48)==at(canvas,0x1e8),rows('cursor')),'NO_BOUND_CURSOR')
            editor_base=process['modules']['videoeditor.dll']['base'];server=editor_base+0x423fe68
            sentinel=at(server,8);count=at(server,16);require(0<count<4096,'INVALID_ACTIVE_SESSION_MAP','Session map unavailable')
            node=at(sentinel,0);session=None
            for _ in range(count):
                if node==sentinel:break
                if struct.unpack('<i',r.read(node+16,4))[0]==sid:session=at(node,24);break
                node=at(node,0)
            require(session,'SESSION_NOT_ACTIVE','Session is not in the active map')
            wrapper=at(session,0x38);require(wrapper,'SESSION_ENGINE_NOT_READY','Edit engine not ready')
            config=at(wrapper,0xa0);require(config,'SESSION_CONFIG_NOT_READY','Edit engine config not ready')
            path=stdstr(config);global_path=stdstr(editor_base+0x3ed49c8)
            require(path and path.replace('\\','/').lower()==global_path.replace('\\','/').lower(),'DRAFT_SWITCH_IN_PROGRESS','Draft selection has not settled')
            token='|'.join(map(str,[f"{process['pid']}:{process['birth']}",hex(manager),hex(timeline),timeline_id,sid,path]))
            self.context_data=dict(manager=manager,timeline=timeline,timeline_id=timeline_id,toolbar=toolbar,videos=videos,sid=sid,player=player,control=control,canvas=canvas,cursor=cursor,path=path,token=token)
            return self.context_data
    def run(self,obj,op,name='',return_type=0,arg_type=0,value=b'',ctx=None):
        ctx=ctx or self.context_data
        with Reader(self.process['pid']) as r:vt=r.pointer(obj)
        result=self.pipe.call(op,object=obj,manager=ctx['manager'],timeline=ctx['timeline'],vtable=vt,name=name,return_type=return_type,arg_type=arg_type,value=value,timeline_id=ctx['timeline_id'])
        return result['text'] if result['kind']==3 else bool(result['number']) if result['kind']==1 else result['number'] if result['kind']==2 else None
    def get(self,obj,name):return self.run(obj,0,name)
    def invoke(self,obj,name,return_type=0,arg_type=0,value=b''):return self.run(obj,1,name,return_type,arg_type,value)
    @serialized
    def invoke_typed(self,obj,name,items=(),return_type=0,selection=0,segment_id='',ctx=None):
        ctx=ctx or self.context()
        require(self.context()['token']==ctx['token'],'SESSION_CHANGED','Draft changed before typed call')
        with Reader(self.process['pid']) as r:
            vt=r.pointer(obj);selection_vt=r.pointer(selection) if selection else 0
        data=arguments(items,selection,selection_vt,segment_id)
        result=self.pipe.call(6,object=obj,manager=ctx['manager'],timeline=ctx['timeline'],vtable=vt,
                             name=name,return_type=return_type,timeline_id=ctx['timeline_id'],payload=data)
        return result['text'] if result['kind']==3 else bool(result['number']) if result['kind']==1 else result['number'] if result['kind']==2 else None
    def revision(self,ctx):
        return sorted([[self.invoke(v,'getSegmentId',3),self.get(v,'x'),self.get(v,'width'),self.get(v,'pixelSize')] for v in ctx['videos']])
    def snapshot(self):
        ctx=self.context();clips=[]
        for v in ctx['videos']:
            x,width,pixel=[self.get(v,n) for n in ('x','width','pixelSize')]
            clip=dict(segmentID=self.invoke(v,'getSegmentId',3),x=x,width=width,pixelSize=pixel,durationUs=width/pixel)
            clip.update({n:self.get(v,n) for n in ('durationText','sDuration','isCuttingMode','isTrackLocked','selected')});clips.append(clip)
        with Reader(self.process['pid']) as r:
            model=r.pointer(ctx['toolbar']+0xe8);undo,redo=r.read(model+0x2bc,2)
        return dict(token=ctx['token'],timeline_id=ctx['timeline_id'],session_id=ctx['sid'],draft_path=ctx['path'],
            revision=sorted([[v['segmentID'],v['x'],v['width'],v['pixelSize']] for v in clips]),clips=clips,
            undo_enabled=bool(undo),redo_enabled=bool(redo),
            preview={key:self.get(ctx['control'],name) for key,name in [('total','totalProgress'),('current','currentProgress'),('playing','isPlaying'),('can_use','canUse')]},
            bindings={name:hex(ctx[name]) for name in ['manager','timeline','toolbar','player','control','canvas','cursor']})
    @serialized
    def inspect(self):
        require(self.pipe,'DISCONNECTED','Connect first')
        try:return self.snapshot()
        except LiveEditError as error:
            if error.code not in ('STALE_OBJECT','NO_UNIQUE_ACTIVE_TIMELINE','NO_BOUND_TOOLBAR','NO_ACTIVE_VIDEO_OBJECTS','NO_BOUND_PREVIEW','NO_BOUND_PLAYER_CONTROL'):raise
            self.refresh();return self.snapshot()
    def rpc(self,method,*args):
        with self.rpc_lock:
            if method=='inspect':return self.inspect()
            require(method in ('trim','history','split','delete','seek'),'UNKNOWN_OPERATION','Unsupported edit operation')
            expected,revision=args[1:3] if method=='history' else args[:2]
            ctx=self.context();require(ctx['token']==expected,'SESSION_CHANGED','Draft changed before edit')
            require(self.revision(ctx)==revision,'REVISION_CHANGED','Timeline changed before edit')
            require(not self.get(ctx['control'],'isPlaying'),'PAUSE_PLAYBACK_FIRST','Playback is active')
            if method=='trim':
                segment,duration=args[2:];candidates=[v for v in ctx['videos'] if self.invoke(v,'getSegmentId',3)==segment]
                require(len(candidates)==1,'SEGMENT_NOT_UNIQUE','Video clip must be unique')
                require(isinstance(duration,int) and duration>0,'INVALID_DURATION','Duration must be positive microseconds')
                old=next(r for r in revision if r[0]==segment)
                self.run(candidates[0],2,segment,0,2,struct.pack('<qdddQ',duration,*old[1:],ctx['control']),ctx=ctx)
            elif method=='history':
                action=args[0];require(action in ('undo','redo'),'INVALID_ACTION','Unsupported history action')
                shot=self.snapshot();require(shot['token']==expected and shot['revision']==revision,'SESSION_CHANGED','Editor changed before history action')
                require(shot[action+'_enabled'],'HISTORY_UNAVAILABLE','History action unavailable')
                self.run(ctx['toolbar'],1,action+'Clicked',ctx=ctx)
                self.refresh()
            else:
                if method=='seek':obj=ctx['cursor'];segment='';position=args[2]
                else:
                    segment=args[2];position=args[3] if method=='split' else 0
                    candidates=[v for v in ctx['videos'] if self.invoke(v,'getSegmentId',3)==segment]
                    require(len(candidates)==1,'SEGMENT_NOT_UNIQUE','Video clip must be unique');obj=candidates[0]
                data=struct.pack('<qQQQQ',position,ctx['canvas'],ctx['cursor'],ctx['toolbar'],ctx['control'])
                self.run(obj,{'split':3,'delete':4,'seek':5}[method],segment,value=data,ctx=ctx)
                if method in ('split','delete'):self.refresh()
            return self.snapshot()
