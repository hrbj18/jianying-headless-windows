#include <cmath>
#include <map>
#include <set>
#include "move_candidate.cpp"
struct MoveWire {uint32_t version,count;int64_t targetUs;int32_t targetIndex,sid;char segment[40],sourceTrack[40],targetTrack[40];uint64_t canvas,entrance;};
struct MoveRow {uint64_t object,vtable;double x,width,pixel;char segment[40],track[40];};
static_assert(sizeof(MoveWire)==160&&sizeof(MoveRow)==120);
static uintptr_t movePtr(uintptr_t p,size_t o=0) {if(!readable(reinterpret_cast<void*>(p+o),8))throw std::runtime_error("Move pointer expired");return *reinterpret_cast<uintptr_t*>(p+o);}
static int32_t moveInt(uintptr_t p) {if(!readable(reinterpret_cast<void*>(p),4))throw std::runtime_error("Move field expired");return *reinterpret_cast<int32_t*>(p);}
static std::string moveString(uintptr_t p) {
    auto size=movePtr(p,16),capacity=movePtr(p,24);if(size!=36||capacity<size)throw std::runtime_error("Move native UUID invalid");
    auto data=capacity<16?p:movePtr(p);if(!readable(reinterpret_cast<void*>(data),size))throw std::runtime_error("Move native UUID expired");
    return std::string(reinterpret_cast<char*>(data),size);
}
struct MoveContext {Job* job;MoveWire* wire;std::vector<MoveRow>* rows;};
static bool moveIdentity(void* data,const live_move_candidate::Request&) {return importIdentity(static_cast<MoveContext*>(data)->job);}
static bool moveState(void* data,const live_move_candidate::Request& q,void*,int,int) {
    auto& c=*static_cast<MoveContext*>(data);auto b=reinterpret_cast<uintptr_t>(GetModuleHandleW(L"VECreator.dll"));
    std::map<std::string,std::set<std::string>> wanted;std::map<std::string,uintptr_t> nativeTracks;
    bool source=false,destination=false;
    for(auto& row:*c.rows) {
        auto p=reinterpret_cast<void*>(row.object);
        if(!readable(p,0x2b0)||movePtr(row.object)!=row.vtable||movePtr(row.object,0x298)!=q.timeline||movePtr(row.object,0x180)!=q.entrance)throw std::runtime_error("Move clip binding changed");
        Result id{},x{},width{},pixel{},locked{},cutting{};call(p,"getSegmentId",3,0,nullptr,id);
        std::string actual;for(size_t i=0;id.text[i]&&i<40;i++)actual.push_back(static_cast<char>(id.text[i]));
        if(actual!=row.segment)throw std::runtime_error("Move clip UUID changed");
        get(p,"x",x);get(p,"width",width);get(p,"pixelSize",pixel);get(p,"isTrackLocked",locked);get(p,"isCuttingMode",cutting);
        if(x.number!=row.x||width.number!=row.width||pixel.number!=row.pixel||pixel.number<=0||cutting.number)throw std::runtime_error("Move clip revision changed");
        auto control=movePtr(row.object,0x258),trackVM=movePtr(row.object,0x260);
        if(!control||!moveInt(control+4)||!readable(reinterpret_cast<void*>(trackVM),0x130))throw std::runtime_error("Move track expired");
        auto model=movePtr(trackVM,0x120),mc=movePtr(trackVM,0x128);
        if(!model||!mc||moveInt(mc+8)<=0)throw std::runtime_error("Move track model expired");
        auto vt=movePtr(model);if(vt!=b+0xac2fa70&&vt!=b+0xac815c0)throw std::runtime_error("Move track model type changed");
        auto track=movePtr(model,0x20);auto trackId=moveString(track+8);
        if(trackId!=row.track||moveInt(track+0x38)!=1)throw std::runtime_error("Move track identity changed");
        wanted[trackId].insert(actual);nativeTracks[trackId]=track;
        if(trackId==q.sourceTrackId||trackId==q.targetTrackId) {
            Result trackLocked{};get(reinterpret_cast<void*>(trackVM),"isLocked",trackLocked);
            if(trackLocked.number||locked.number||moveInt(track+0x50)==0)throw std::runtime_error("Move main or locked track");
        }
        if(actual==q.segmentId)source=trackId==q.sourceTrackId&&std::abs(row.x/row.pixel-q.expectedStartUs)<2&&std::abs(row.width/row.pixel-q.expectedDurationUs)<2;
        if(trackId==q.targetTrackId) {
            destination=true;
            if(actual!=q.segmentId&&row.x/row.pixel<q.targetStartUs+q.expectedDurationUs-1&&q.targetStartUs<(row.x+row.width)/row.pixel-1)throw std::runtime_error("Move destination overlaps");
        }
    }
    for(auto& pair:nativeTracks) {
        auto array=movePtr(pair.second,0x40),first=movePtr(array,0x38),last=movePtr(array,0x40);
        if(last<first||(last-first)%16||(last-first)/16!=wanted[pair.first].size())throw std::runtime_error("Move track segment set changed");
        std::set<std::string> actual;for(auto at=first;at<last;at+=16)actual.insert(moveString(movePtr(at)+8));
        if(actual!=wanted[pair.first])throw std::runtime_error("Move native segment coverage changed");
    }
    return source&&destination;
}
static void moveNative(Job& j) {
    // The retired partial probe remains read-only; unknown modes must not edit.
    const bool readonlyProbe=std::strcmp(j.name,"probe")==0||std::strcmp(j.name,"probe-draft")==0;
    if(j.name[0]&&!readonlyProbe)throw std::runtime_error("Unknown move operation");
    if(j.payloadSize<sizeof(MoveWire))throw std::runtime_error("Move payload absent");MoveWire h{};std::memcpy(&h,j.payload,sizeof h);
    if(h.version!=1||!h.count||h.count>60||j.payloadSize!=sizeof h+h.count*sizeof(MoveRow))throw std::runtime_error("Move payload invalid");
    h.segment[39]=h.sourceTrack[39]=h.targetTrack[39]=0;
    std::vector<MoveRow> rows(h.count);std::memcpy(rows.data(),j.payload+sizeof h,rows.size()*sizeof(MoveRow));
    for(auto& row:rows){row.segment[39]=row.track[39]=0;}
    live_move_candidate::Request q{};q.targetTrackIndex=h.targetIndex;q.targetStartUs=h.targetUs;q.expectedSid=h.sid;
    std::memcpy(q.segmentId,h.segment,40);std::memcpy(q.sourceTrackId,h.sourceTrack,40);std::memcpy(q.targetTrackId,h.targetTrack,40);
    q.manager=reinterpret_cast<uintptr_t>(j.manager);q.managerVtable=movePtr(q.manager);q.timeline=reinterpret_cast<uintptr_t>(j.timeline);q.timelineVtable=movePtr(q.timeline);
    q.canvasModel=h.canvas;q.canvasModelVtable=movePtr(h.canvas);q.entrance=h.entrance;q.entranceVtable=movePtr(h.entrance);q.clip=reinterpret_cast<uintptr_t>(j.object);q.clipVtable=movePtr(q.clip);
    bool found=false;for(auto& row:rows)if(row.object==q.clip&&std::strcmp(row.segment,q.segmentId)==0&&row.pixel>0){q.expectedStartUs=static_cast<int64_t>(std::llround(row.x/row.pixel));q.expectedDurationUs=static_cast<int64_t>(std::llround(row.width/row.pixel));found=true;}
    if(!found)throw std::runtime_error("Move source absent");
    Result playing{};get(*reinterpret_cast<void**>(j.value),"isPlaying",playing);if(playing.number)throw std::runtime_error("Playback active");
    MoveContext context{&j,&h,&rows};live_move_candidate::Runtime runtime{};
    runtime.veCreatorBase=reinterpret_cast<uintptr_t>(GetModuleHandleW(L"VECreator.dll"));runtime.videoEditorBase=reinterpret_cast<uintptr_t>(GetModuleHandleW(L"videoeditor.dll"));
    runtime.guiOwnerThreadId=GetCurrentThreadId();runtime.exactBuildVerified=true;runtime.identityStillMatches=moveIdentity;runtime.liveMoveStateAccepts=moveState;runtime.context=&context;
    runtime.probeOnly=readonlyProbe;
    auto result=live_move_candidate::submitOnGuiThread(runtime,q);
    if(result.status!=live_move_candidate::Status::Dispatched)throw std::runtime_error(("Move status "+std::to_string(static_cast<unsigned>(result.status))).c_str());
    j.result->kind=2;j.result->number=result.targetIndex;
}
