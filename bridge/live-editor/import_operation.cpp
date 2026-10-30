#include "native_import.cpp"
static bool importIdentity(void* data) noexcept {
    auto& j=*static_cast<Job*>(data);
    if(!readable(j.manager,0x128)||*reinterpret_cast<void**>(static_cast<unsigned char*>(j.manager)+0x120)!=j.timeline)return false;
    if(!readable(j.timeline,0x6a0))return false;
    try {Result id{};copyString(static_cast<unsigned char*>(j.timeline)+0x688,id);
        for(size_t i=0;;i++){if(id.text[i]!=static_cast<unsigned char>(j.timelineId[i]))return false;if(!j.timelineId[i])return true;}
    }catch(...){return false;}
}
static void importNative(Job& j) {
    if(j.payloadSize<2||j.payloadSize>4097||j.payload[j.payloadSize-1])throw std::runtime_error("Invalid import path");
    live_import_candidate::Request q{};
    q.inspector=reinterpret_cast<uintptr_t>(j.object);
    auto input=static_cast<unsigned char*>(j.value);
    q.importer=*reinterpret_cast<uintptr_t*>(input);q.grid=*reinterpret_cast<uintptr_t*>(input+8);
    q.pathBytes=static_cast<uint32_t>(j.payloadSize-1);std::memcpy(q.pathUtf8,j.payload,j.payloadSize);
    live_import_candidate::Runtime r{};
    r.moduleBase=reinterpret_cast<uintptr_t>(GetModuleHandleW(L"VECreator.dll"));r.guiOwnerThreadId=GetCurrentThreadId();
    r.currentDraftStillMatches=importIdentity;r.identityContext=&j;
    auto result=live_import_candidate::submitOnGuiThread(r,q);
    if(result.status!=live_import_candidate::Status::Submitted)throw std::runtime_error(("Import status "+std::to_string(static_cast<uint32_t>(result.status))).c_str());
    j.result->kind=2;j.result->number=1;
}
static void insertNative(Job& j) {
    auto input=static_cast<unsigned char*>(j.value);auto grid=*reinterpret_cast<unsigned char**>(input);
    auto expectedGridVt=*reinterpret_cast<void**>(input+8);
    if(!readable(grid,0x160)||*reinterpret_cast<void**>(grid)!=expectedGridVt||!readable(j.object,0x290))throw std::runtime_error("Media binding expired");
    auto item=static_cast<unsigned char*>(j.object);auto control=*reinterpret_cast<unsigned char**>(item+0x280);
    if(*reinterpret_cast<void**>(item+0x288)!=grid||!readable(control,8)||!*reinterpret_cast<int*>(control+4))throw std::runtime_error("Media collection detached");
    Result enabled{},unsupported{},placeholder{};get(j.object,"importBtnEnabled",enabled);get(j.object,"isUnsupported",unsupported);get(j.object,"isPlaceHolderMaterial",placeholder);
    if(!enabled.number||unsupported.number||placeholder.number)throw std::runtime_error("Media not ready");
    call(grid,"cancelAllSelectedItem",0,0,nullptr,*j.result);
    if(*reinterpret_cast<int64_t*>(grid+0x158)!=0)throw std::runtime_error("Media multiselection remains");
    call(j.object,"importBtnClicked",0,0,nullptr,*j.result);
}
