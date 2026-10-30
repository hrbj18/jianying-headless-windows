// Included after Job. Bounded typed arguments; owned QString storage on GUI thread.
struct TypedArg {uint32_t kind,size,offset;char type[52];};
struct TypedHeader {uint32_t version,count;uint64_t selection,selectionVtable;char segmentId[40];TypedArg args[8];};
static_assert(sizeof(TypedArg)==64&&sizeof(TypedHeader)==576);
using ConstructUtf8=void(*)(void*,const char*);
static uintptr_t panelPointer(uintptr_t p,size_t offset=0) {
    if(!readable(reinterpret_cast<void*>(p+offset),8))throw std::runtime_error("Panel pointer expired");
    return *reinterpret_cast<uintptr_t*>(p+offset);
}
static std::string panelUuid(uintptr_t p) {
    auto n=panelPointer(p,16),capacity=panelPointer(p,24);
    if(n!=36||capacity<n)throw std::runtime_error("Panel UUID invalid");
    auto chars=capacity<16?p:panelPointer(p);if(!readable(reinterpret_cast<void*>(chars),n))throw std::runtime_error("Panel UUID expired");
    return std::string(reinterpret_cast<char*>(chars),n);
}
#include "transition_guard.cpp"
static void guardVideoPanel(Job& j,void* selected,const char* segmentId) {
    auto b=reinterpret_cast<uintptr_t>(GetModuleHandleW(L"VECreator.dll"));auto vm=reinterpret_cast<uintptr_t>(j.object);
    auto vt=panelPointer(vm);
    if(vt!=b+0xbfa32e8&&vt!=b+0xb4ae418)throw std::runtime_error("Wrong video panel type");
    auto model=panelPointer(vm,0xa8),mc=panelPointer(vm,0xb0);
    if(!readable(reinterpret_cast<void*>(model),0x30)||!readable(reinterpret_cast<void*>(mc),16)||*reinterpret_cast<int32_t*>(mc+8)<=0)throw std::runtime_error("Video panel model expired");
    auto ids=panelPointer(model,8),idsEnd=panelPointer(model,0x10);
    if(idsEnd<ids||idsEnd-ids!=32||panelUuid(ids)!=segmentId)throw std::runtime_error("Video panel selection changed");
    auto native=panelPointer(model,0x20),nativeEnd=panelPointer(model,0x28);
    if(nativeEnd<native||nativeEnd-native!=16)throw std::runtime_error("Multiple native video selection");
    auto target=panelPointer(native),control=panelPointer(native,8);
    if(!readable(reinterpret_cast<void*>(control),16)||*reinterpret_cast<int32_t*>(control+8)<=0||panelUuid(target+8)!=segmentId)throw std::runtime_error("Native video panel selection expired");
    auto clip=reinterpret_cast<uintptr_t>(selected),tc=panelPointer(clip,0x258),trackVM=panelPointer(clip,0x260);
    if(!readable(reinterpret_cast<void*>(tc),8)||!*reinterpret_cast<int32_t*>(tc+4))throw std::runtime_error("Video track expired");
    auto tm=panelPointer(trackVM,0x120),tmc=panelPointer(trackVM,0x128);
    if(!readable(reinterpret_cast<void*>(tmc),16)||*reinterpret_cast<int32_t*>(tmc+8)<=0)throw std::runtime_error("Video track model expired");
    auto track=panelPointer(tm,0x20),array=panelPointer(track,0x40),first=panelPointer(array,0x38),last=panelPointer(array,0x40);
    if(last<first||(last-first)%16||last-first>65536)throw std::runtime_error("Invalid native track segments");
    bool found=false;for(auto p=first;p<last;p+=16)if(panelPointer(p)==target){found=true;break;}
    if(!found)throw std::runtime_error("Video panel belongs to another draft");
    using Scene=int32_t(*)();if(reinterpret_cast<Scene>(b+0x69508a0)()!=1)throw std::runtime_error("Not the main editing scene");
}
static void callTyped(Job& j) {
    if(j.payloadSize<sizeof(TypedHeader)||j.payloadSize>8192)throw std::runtime_error("Invalid typed payload");
    TypedHeader header{};std::memcpy(&header,j.payload,sizeof(header));
    if(header.version!=1||header.count>8)throw std::runtime_error("Typed protocol mismatch");
    if(!std::strcmp(j.name,"updateDuration")&&!header.selection)throw std::runtime_error("Transition selection required");
    if(header.selection) {
        auto selection=reinterpret_cast<void*>(header.selection);
        if(!readable(selection,0x2a0)||*reinterpret_cast<uint64_t*>(selection)!=header.selectionVtable)throw std::runtime_error("Selection expired");
        if(j.timeline&&*reinterpret_cast<void**>(static_cast<unsigned char*>(selection)+0x298)!=j.timeline)throw std::runtime_error("Selected clip detached");
        Result id{},selected{};call(selection,"getSegmentId",3,0,nullptr,id);get(selection,"selected",selected);
        if(!selected.number)throw std::runtime_error("Selection changed");
        header.segmentId[39]=0;
        for(size_t i=0;;i++){if(id.text[i]!=static_cast<unsigned char>(header.segmentId[i]))throw std::runtime_error("Selected segment changed");if(!header.segmentId[i])break;}
        if(!std::strcmp(j.name,"correctContent")) {
            if(!readable(j.object,0x20))throw std::runtime_error("Text panel expired");
            auto helper=*reinterpret_cast<unsigned char**>(static_cast<unsigned char*>(j.object)+0x18);
            if(!readable(helper,0x18))throw std::runtime_error("Text helper expired");
            auto begin=*reinterpret_cast<uintptr_t*>(helper+8),end=*reinterpret_cast<uintptr_t*>(helper+0x10);
            if(end<begin||end-begin!=32)throw std::runtime_error("Multiple text selection");
            Result current{};call(j.object,"contentID",3,0,nullptr,current);
            for(size_t i=0;;i++){if(current.text[i]!=static_cast<unsigned char>(header.segmentId[i]))throw std::runtime_error("Text panel selection changed");if(!header.segmentId[i])break;}
        }
        if(!std::strcmp(j.name,"acceptFilterValue")||!std::strcmp(j.name,"removeFilterBtnClicked")||!std::strcmp(j.name,"removeEffect"))guardVideoPanel(j,selection,header.segmentId);
        if(!std::strcmp(j.name,"updateDuration"))guardTransitionPanel(j,selection,header.segmentId);
    }
    auto ctor=reinterpret_cast<ConstructUtf8>(GetProcAddress(GetModuleHandleW(L"Qt6Core.dll"),"??0QString@@QEAA@PEBD@Z"));
    if(!ctor)throw std::runtime_error("QString constructor unavailable");
    alignas(8) unsigned char storage[8][64]={};bool strings[8]={};Generic args[10]={};
    alignas(8) unsigned char returned[64]={};
    const char* rt=j.returnType==1?"bool":j.returnType==3?"QString":j.returnType==4?"int64_t":j.returnType==5?"int":j.returnType==6?"double":nullptr;
    Generic ret{rt?returned:nullptr,rt};
    try {
        for(uint32_t i=0;i<header.count;i++) {
            auto& a=header.args[i];a.type[51]=0;
            if(a.offset<sizeof(header)||a.offset>j.payloadSize||a.size>j.payloadSize-a.offset)throw std::runtime_error("Argument outside payload");
            const auto data=j.payload+a.offset;
            const char* type=nullptr;size_t size=0;
            switch(a.kind){case 1:type="bool";size=1;break;case 2:type="int";size=4;break;case 3:type="int64_t";size=8;break;case 4:type="double";size=8;break;case 5:type="float";size=4;break;case 6:type="QString";break;case 7:type="QQuickItem*";size=8;break;default:throw std::runtime_error("Unsupported argument type");}
            if(a.kind==6) {
                if(!a.size||a.size>4097||data[a.size-1]!=0||std::memchr(data,0,a.size-1))throw std::runtime_error("Invalid UTF8 argument");
                ctor(storage[i],reinterpret_cast<const char*>(data));strings[i]=true;
            }else {
                if(size!=a.size)throw std::runtime_error("Argument size mismatch");
                std::memcpy(storage[i],data,size);
                // Enum arguments share int storage, but Qt requires their exact type name.
                if(a.type[0]){if(a.kind!=2&&a.kind!=7)throw std::runtime_error("Unsupported type override");type=a.type;}
            }
            args[i]={storage[i],type};
        }
        if(!std::strcmp(j.name,"removeEffect")) {
            if(header.count!=2||header.args[0].kind!=2||header.args[1].kind!=6||*reinterpret_cast<int32_t*>(storage[0])!=0||*reinterpret_cast<int64_t*>(static_cast<unsigned char*>(j.object)+0xe0)!=1)throw std::runtime_error("Only one named effect is supported");
            Result requested{},actual{};copyString(storage[1],requested);get(j.object,"effectName",actual);
            if(std::memcmp(requested.text,actual.text,sizeof requested.text))throw std::runtime_error("Video effect name changed");
        }
        if(!std::strcmp(j.name,"updateDuration")) {
            if(header.count!=1||header.args[0].kind!=5)throw std::runtime_error("Transition duration requires one float");
            float requested=*reinterpret_cast<float*>(storage[0]);Result low{},high{};get(j.object,"minDuration",low);get(j.object,"maxDuration",high);
            if(!std::isfinite(requested)||!std::isfinite(low.number)||!std::isfinite(high.number)||!(low.number>0&&low.number<=high.number&&requested>=low.number&&requested<=high.number))throw std::runtime_error("Transition duration outside current panel limits");
        }
        if(!invoke(j.object,j.name,1,&ret,&args[0],&args[1],&args[2],&args[3],&args[4],&args[5],&args[6],&args[7],&args[8],&args[9]))throw std::runtime_error("Typed invoke rejected");
        j.result->kind=j.returnType;
        if(j.returnType==1)j.result->number=returned[0]?1:0;
        if(j.returnType==3){try{copyString(returned,*j.result);}catch(...){destroyString(returned);throw;}destroyString(returned);}
        if(j.returnType==4){j.result->kind=2;j.result->number=static_cast<double>(*reinterpret_cast<int64_t*>(returned));}
        if(j.returnType==5){j.result->kind=2;j.result->number=*reinterpret_cast<int32_t*>(returned);}
        if(j.returnType==6){j.result->kind=2;j.result->number=*reinterpret_cast<double*>(returned);}
    }catch(...){for(uint32_t i=0;i<8;i++)if(strings[i])destroyString(storage[i]);throw;}
    for(uint32_t i=0;i<8;i++)if(strings[i])destroyString(storage[i]);
}
