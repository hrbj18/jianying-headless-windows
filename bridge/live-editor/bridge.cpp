// Qt 6.2.2 exact-build compatibility shim. No hooks or JS callbacks retained.
// Slot layout and ownership verified against the installed Qt6Core.dll.
#include <cstdint>
#include <cstring>
#include <atomic>
#include <stdexcept>
#include <string>
#include <windows.h>

struct Generic {void* data; const char* type;};
struct Result {int32_t executed;int32_t kind;double number;char16_t text[2049];};
static_assert(sizeof(Result)==4120);
static_assert(offsetof(Result,text)==16);
struct Slot;
using Impl=void(*)(int,Slot*,void*,void**,bool*);
struct Slot {std::atomic<int32_t> references{1};Impl impl;void* job;};
static_assert(offsetof(Slot,impl)==8);
using Invoke=bool(*)(void*,const char*,int,Generic*,Generic*,Generic*,Generic*,Generic*,Generic*,Generic*,Generic*,Generic*,Generic*,Generic*);
using Dispatch=bool(*)(void*,Slot*,int,void*);
using Property=void*(*)(void*,void*,const char*);
using TypeName=const char*(*)(void*);
using Double=double(*)(void*,bool*);
using Bool=bool(*)(void*);
using String=void*(*)(void*,void*);
using Destructor=void(*)(void*);
static Invoke invoke;
static Dispatch dispatch;
static Property property;
static TypeName typeName;
static Double asDouble;
static Bool asBool;
static String asString;
static Destructor destroyString,destroyVariant;
static void* stableDispatcher=nullptr;
static void* expectedManagerVtable=nullptr;
static bool readable(void* address,size_t bytes) {
    MEMORY_BASIC_INFORMATION info{};
    if(!address||!VirtualQuery(address,&info,sizeof(info)))return false;
    auto protection=info.Protect&0xff;
    return info.State==MEM_COMMIT&&!(info.Protect&PAGE_GUARD)&&protection!=PAGE_NOACCESS&&
        reinterpret_cast<uintptr_t>(address)+bytes>=reinterpret_cast<uintptr_t>(address)&&
        reinterpret_cast<uintptr_t>(address)+bytes<=reinterpret_cast<uintptr_t>(info.BaseAddress)+info.RegionSize;
}

static void copyString(void* value,Result& out) {
    const auto bytes=static_cast<unsigned char*>(value);
    auto length=*reinterpret_cast<int64_t*>(bytes+16);
    auto data=*reinterpret_cast<char16_t**>(bytes+8);
    if(length<0||length>2048||(length&&!data))throw std::runtime_error("QString size");
    if(length)std::memcpy(out.text,data,static_cast<size_t>(length)*2);
    out.text[length]=0;out.kind=3;
}
static void get(void* obj,const char* name,Result& out) {
    alignas(8) unsigned char value[64]={};property(obj,value,name);
    try {
        const char* type=typeName(value);
        if(!type)throw std::runtime_error("Property absent");
        if(!std::strcmp(type,"QString")) {
            alignas(8) unsigned char s[64]={};asString(value,s);
            try {copyString(s,out);}catch(...){destroyString(s);throw;}
            destroyString(s);
        } else if(!std::strcmp(type,"bool")){out.kind=1;out.number=asBool(value)?1:0;}
        else if(std::strstr(type,"double")||std::strstr(type,"float")||std::strstr(type,"int")||std::strstr(type,"long")) {
            bool ok=false;out.number=asDouble(value,&ok);if(!ok)throw std::runtime_error("Numeric conversion");out.kind=2;
        } else throw std::runtime_error("Property type");
    }catch(...){destroyVariant(value);throw;}
    destroyVariant(value);
}
static void call(void* obj,const char* name,int returnType,int argType,void* value,Result& out) {
    alignas(8) unsigned char returned[64]={};
    const char* rt=returnType==1?"bool":returnType==3?"QString":returnType==4?"int64_t":nullptr;
    const char* at=argType==1?"QQuickItem*":argType==2?"int64_t":argType==3?"double":argType==4?"bool":nullptr;
    Generic ret{rt?returned:nullptr,rt},args[10]={};
    if(at)args[0]={value,at};
    // Already on the receiver thread: DirectConnection is mandatory here.
    if(!invoke(obj,name,1,&ret,&args[0],&args[1],&args[2],&args[3],&args[4],&args[5],&args[6],&args[7],&args[8],&args[9]))
        throw std::runtime_error("Invoke rejected");
    out.kind=returnType;
    if(returnType==1)out.number=returned[0]?1:0;
    if(returnType==4){out.kind=2;out.number=static_cast<double>(*reinterpret_cast<int64_t*>(returned));}
    if(returnType==3){try {copyString(returned,out);}catch(...){destroyString(returned);throw;}destroyString(returned);}
}
struct Job {
    void* object;int operation;const char* name;int returnType;int argType;
    void* value;Result* result;void* manager;void* timeline;void* vtable;const char* timelineId;
    const unsigned char* payload=nullptr;size_t payloadSize=0;
};
#include "typed_call.cpp"
#include "import_operation.cpp"
#include "move_operation.cpp"
static void execute(Job& j) {
    if(j.manager&&(!readable(j.manager,0x128)||(expectedManagerVtable&&*static_cast<void**>(j.manager)!=expectedManagerVtable)))
        throw std::runtime_error("Manager expired");
    if(j.manager&&*reinterpret_cast<void**>(static_cast<unsigned char*>(j.manager)+0x120)!=j.timeline)
        throw std::runtime_error("Session changed");
    if(j.timelineId&&j.timelineId[0]) {
        if(!readable(j.timeline,0x6a0))throw std::runtime_error("Timeline expired");
        Result id{};copyString(static_cast<unsigned char*>(j.timeline)+0x688,id);
        for(size_t i=0;;i++){if(id.text[i]!=static_cast<unsigned char>(j.timelineId[i]))throw std::runtime_error("Timeline identity changed");if(!j.timelineId[i])break;}
    }
    if(!readable(j.object,j.operation==2?0x2a0:8))throw std::runtime_error("Object expired");
    if(*static_cast<void**>(j.object)!=j.vtable)throw std::runtime_error("Object replaced");
    if(j.operation==0)get(j.object,j.name,*j.result);
    else if(j.operation==1) {
        if(!std::strcmp(j.name,"undoClicked")||!std::strcmp(j.name,"redoClicked")) {
            if(!readable(j.object,0xf0))throw std::runtime_error("Toolbar expired");
            auto model=*reinterpret_cast<unsigned char**>(static_cast<unsigned char*>(j.object)+0xe8);
            if(!readable(model,0x2be)||*reinterpret_cast<void**>(model+0x48)!=j.manager||*reinterpret_cast<void**>(model+0x58)!=j.timeline)
                throw std::runtime_error("Toolbar detached");
            if(!model[!std::strcmp(j.name,"undoClicked")?0x2bc:0x2bd])throw std::runtime_error("History unavailable");
        }
        call(j.object,j.name,j.returnType,j.argType,j.value,*j.result);
    }
    else if(j.operation==2) {
        if(*reinterpret_cast<void**>(static_cast<unsigned char*>(j.object)+0x298)!=j.timeline)throw std::runtime_error("Clip detached");
        Result id{};call(j.object,"getSegmentId",3,0,nullptr,id);
        for(size_t i=0;;i++){if(id.text[i]!=static_cast<unsigned char>(j.name[i]))throw std::runtime_error("Wrong segment");if(!j.name[i])break;}
        Result locked{},cutting{};get(j.object,"isTrackLocked",locked);get(j.object,"isCuttingMode",cutting);
        if(locked.number||cutting.number)throw std::runtime_error("Clip busy");
        Result x{},width{},pixel{},playing{};get(j.object,"x",x);get(j.object,"width",width);get(j.object,"pixelSize",pixel);
        auto input=static_cast<unsigned char*>(j.value);
        if(x.number!=*reinterpret_cast<double*>(input+8)||width.number!=*reinterpret_cast<double*>(input+16)||pixel.number!=*reinterpret_cast<double*>(input+24))throw std::runtime_error("Revision changed");
        get(*reinterpret_cast<void**>(input+32),"isPlaying",playing);
        if(playing.number)throw std::runtime_error("Playback active");
        double edge=x.number+width.number;
        void* slider=nullptr;Result started{};call(j.object,"cutRightStarted",1,1,&slider,started);
        if(!started.number)throw std::runtime_error("Trim rejected");
        bool finishAttempted=false;
        try {
            call(j.object,"cutRightPositionChanged",0,2,j.value,*j.result);
            get(j.object,"x",x);get(j.object,"width",width);edge=x.number+width.number;
            finishAttempted=true;call(j.object,"cutRightFinished",0,3,&edge,*j.result);
        } catch(...) {
            // Attempt to finish the already-started gesture once. This is not
            // a rollback and does not hide the original operation failure.
            if(!finishAttempted)try {call(j.object,"cutRightFinished",0,3,&edge,*j.result);}catch(...){j.result->kind=-2;}
            throw;
        }
    }else if(j.operation>=3&&j.operation<=5) {
        auto input=static_cast<unsigned char*>(j.value);
        auto position=*reinterpret_cast<int64_t*>(input);
        auto canvas=*reinterpret_cast<unsigned char**>(input+8);
        auto cursor=*reinterpret_cast<unsigned char**>(input+16);
        auto toolbar=*reinterpret_cast<unsigned char**>(input+24);
        auto control=*reinterpret_cast<void**>(input+32);
        if(!readable(canvas,0x1f0)||!readable(cursor,0x50))throw std::runtime_error("Canvas expired");
        auto model=*reinterpret_cast<unsigned char**>(canvas+0x1d8);
        if(!readable(model,0x530)||*reinterpret_cast<void**>(model+0x68)!=j.timeline||
           *reinterpret_cast<void**>(canvas+0x1e8)!=*reinterpret_cast<void**>(cursor+0x48))throw std::runtime_error("Canvas detached");
        Result playing{};get(control,"isPlaying",playing);if(playing.number)throw std::runtime_error("Playback active");
        if(j.operation==5) {
            if(j.object!=cursor)throw std::runtime_error("Cursor mismatch");
            call(cursor,"clickSeekByTime",0,2,&position,*j.result);
            call(canvas,"getCursorDuration",4,0,nullptr,*j.result);
            if(j.result->number!=position)throw std::runtime_error("Seek mismatch");
        }else {
            if(!readable(j.object,0x2a0)||*reinterpret_cast<void**>(static_cast<unsigned char*>(j.object)+0x298)!=j.timeline||
               *reinterpret_cast<void**>(static_cast<unsigned char*>(j.object)+0x180)!=*reinterpret_cast<void**>(model+0x518)||
               *reinterpret_cast<void**>(static_cast<unsigned char*>(j.object)+0x170)!=*reinterpret_cast<void**>(model+0x528))throw std::runtime_error("Segment detached");
            Result id{};call(j.object,"getSegmentId",3,0,nullptr,id);
            for(size_t i=0;;i++){if(id.text[i]!=static_cast<unsigned char>(j.name[i]))throw std::runtime_error("Wrong segment");if(!j.name[i])break;}
            Result locked{},cutting{},selected{};get(j.object,"isTrackLocked",locked);get(j.object,"isCuttingMode",cutting);
            if(locked.number||cutting.number)throw std::runtime_error("Clip busy");
            if(j.operation==3) {
                Result x{},width{},pixel{};get(j.object,"x",x);get(j.object,"width",width);get(j.object,"pixelSize",pixel);
                if(position<=x.number/pixel.number||position>=(x.number+width.number)/pixel.number)throw std::runtime_error("Split outside clip");
                if(!readable(toolbar,0xf0))throw std::runtime_error("Toolbar expired");
                auto tm=*reinterpret_cast<unsigned char**>(toolbar+0xe8);
                if(!readable(tm,0x60)||*reinterpret_cast<void**>(tm+0x48)!=j.manager||*reinterpret_cast<void**>(tm+0x58)!=j.timeline)throw std::runtime_error("Toolbar detached");
            }
            call(canvas,"unselectSegments",0,0,nullptr,*j.result);
            call(j.object,"selectedSegment",0,0,nullptr,*j.result);
            get(j.object,"selected",selected);if(!selected.number)throw std::runtime_error("Selection failed");
            bool shortcut=false;
            if(j.operation==3) {
                call(cursor,"clickSeekByTime",0,2,&position,*j.result);
                call(canvas,"getCursorDuration",4,0,nullptr,*j.result);
                if(j.result->number!=position)throw std::runtime_error("Seek mismatch");
                call(toolbar,"cutoffClicked",0,4,&shortcut,*j.result);
            }else call(canvas,"delSelecteds",0,4,&shortcut,*j.result);
        }
    }else if(j.operation==6)callTyped(j);
    else if(j.operation==7)importNative(j);
    else if(j.operation==10)moveNative(j);
    else if(j.operation==11)insertNative(j);
    else throw std::runtime_error("Unknown operation");
}
static void slotImpl(int which,Slot* slot,void*,void**,bool*) noexcept {
    if(which==0){delete slot;return;}
    if(which!=1)return;
    auto& job=*static_cast<Job*>(slot->job);
    try {execute(job);job.result->executed=1;}
    catch(const std::exception& error) {
        job.result->executed=-1;job.result->kind=-1;
        auto text=error.what();size_t i=0;for(;text[i]&&i<2048;i++)job.result->text[i]=static_cast<unsigned char>(text[i]);job.result->text[i]=0;
    }
    catch(...) {job.result->executed=-1;}
}
extern "C" __declspec(dllexport) int live_init(void** functions) noexcept {
    invoke=reinterpret_cast<Invoke>(functions[0]);dispatch=reinterpret_cast<Dispatch>(functions[1]);
    property=reinterpret_cast<Property>(functions[2]);typeName=reinterpret_cast<TypeName>(functions[3]);
    asDouble=reinterpret_cast<Double>(functions[4]);asBool=reinterpret_cast<Bool>(functions[5]);
    asString=reinterpret_cast<String>(functions[6]);destroyString=reinterpret_cast<Destructor>(functions[7]);
    destroyVariant=reinterpret_cast<Destructor>(functions[8]);return 1;
}
extern "C" __declspec(dllexport) int live_result_size() noexcept {return sizeof(Result);}
extern "C" __declspec(dllexport) void live_set_dispatcher(void* target,void* managerVtable) noexcept {stableDispatcher=target;expectedManagerVtable=managerVtable;}
extern "C" __declspec(dllexport) int live_call_guarded(void* object,int operation,const char* name,int returnType,int argType,
    void* value,Result* result,void* manager,void* timeline,void* vtable,const char* timelineId,const unsigned char* payload=nullptr,size_t payloadSize=0) noexcept {
    if(!dispatch||!object||!result)return -3;
    std::memset(result,0,sizeof(Result));
    Job job{object,operation,name,returnType,argType,value,result,manager,timeline,vtable,timelineId,payload,payloadSize};
    try {
        auto* slot=new Slot;slot->impl=slotImpl;slot->job=&job;
        // Qt owns the initial reference and destroys the slot after dispatch.
        if(!dispatch(stableDispatcher?stableDispatcher:object,slot,3,nullptr))return -2;
        // Receiver destruction can wake a blocked call without executing it.
        return result->executed;
    }catch(...){return -1;}
}
extern "C" __declspec(dllexport) int live_call(void* object,int operation,const char* name,int returnType,int argType,
    void* value,Result* result,void* manager,void* timeline,void* vtable) noexcept {
    return live_call_guarded(object,operation,name,returnType,argType,value,result,manager,timeline,vtable,nullptr);
}
