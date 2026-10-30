// Included after panelPointer/panelUuid, inside the same serialized GUI job.
// Exact-build evidence: research/v02-effects/transition-panel-contract.md.
#include <cmath>
struct TransitionShared {void* object=nullptr;void* control=nullptr;};
struct TransitionOwned {
    TransitionShared value{};void(*release)(void*);
    explicit TransitionOwned(void(*r)(void*)):release(r){}
    TransitionOwned(const TransitionOwned&)=delete;
    ~TransitionOwned(){if(value.control)release(value.control);}
    bool live()const{return value.object&&readable(value.control,16)&&*reinterpret_cast<int32_t*>(static_cast<unsigned char*>(value.control)+8)>0;}
};
static void guardTransitionPanel(Job& j,void* selected,const char* transitionId) {
    auto b=reinterpret_cast<uintptr_t>(GetModuleHandleW(L"VECreator.dll"));
    auto ve=reinterpret_cast<uintptr_t>(GetModuleHandleW(L"videoeditor.dll"));
    auto vm=reinterpret_cast<uintptr_t>(j.object),clip=reinterpret_cast<uintptr_t>(selected);
    auto vt=panelPointer(vm),clipVt=panelPointer(clip);
    if(vt!=b+0xbfa2de0&&vt!=b+0xb4adc68)throw std::runtime_error("Wrong transition panel type");
    if(clipVt!=b+0xac5e230&&clipVt!=b+0xa841738)throw std::runtime_error("Wrong transition selection type");
    auto manager=panelPointer(vm,0x108),managerControl=panelPointer(vm,0x110);
    if(manager!=reinterpret_cast<uintptr_t>(j.manager)||!readable(reinterpret_cast<void*>(managerControl),16)||*reinterpret_cast<int32_t*>(managerControl+8)<=0)throw std::runtime_error("Transition panel belongs to another editor");
    if(panelUuid(vm+0x58)!=transitionId)throw std::runtime_error("Transition panel selection changed");
    auto tc=panelPointer(clip,0x258),trackVM=panelPointer(clip,0x260);
    if(!readable(reinterpret_cast<void*>(tc),8)||!*reinterpret_cast<int32_t*>(tc+4))throw std::runtime_error("Transition track expired");
    Result locked{},cutting{},multiple{};get(reinterpret_cast<void*>(trackVM),"isLocked",locked);get(selected,"isCuttingMode",cutting);get(j.object,"isMultiSelect",multiple);
    if(locked.number||cutting.number||multiple.number)throw std::runtime_error("Transition is locked, cutting or multiply selected");
    auto model=panelPointer(trackVM,0x120),control=panelPointer(trackVM,0x128);
    if(!readable(reinterpret_cast<void*>(control),16)||*reinterpret_cast<int32_t*>(control+8)<=0)throw std::runtime_error("Transition track model expired");
    auto modelVt=panelPointer(model);
    if(modelVt!=b+0xac2fa70&&modelVt!=b+0xac815c0)throw std::runtime_error("Wrong transition track model type");
    auto track=panelPointer(model,0x20),array=panelPointer(track,0x40),first=panelPointer(array,0x38),last=panelPointer(array,0x40);
    if(last<first||(last-first)%16||last-first>65536)throw std::runtime_error("Invalid transition track segments");
    unsigned matches=0;uintptr_t foundLeft=0;int64_t nativeDuration=0;
    for(auto p=first;p<last;p+=16) {
        auto segment=panelPointer(p);if(panelPointer(segment)!=ve+0x2fdb2a8)continue;
        auto transition=panelPointer(segment,0x310),owner=panelPointer(segment,0x318);if(!transition)continue;
        if(!readable(reinterpret_cast<void*>(owner),16)||*reinterpret_cast<int32_t*>(owner+8)<=0)throw std::runtime_error("Native transition expired");
        if(panelPointer(transition)!=ve+0x2fc8708)throw std::runtime_error("Wrong native transition type");
        if(panelUuid(transition+8)==transitionId) {
            if(!readable(reinterpret_cast<void*>(transition+0xe8),8)||*reinterpret_cast<int64_t*>(transition+0xe8)<=0)throw std::runtime_error("Native transition duration invalid");
            nativeDuration=*reinterpret_cast<int64_t*>(transition+0xe8);foundLeft=segment;
            ++matches;
        }
    }
    if(matches!=1)throw std::runtime_error("Transition not uniquely bound to the current track");
    // Match the actual native cross-track lookup used by updateDuration, rather
    // than assuming that uniqueness on the selected track implies global identity.
    auto release=reinterpret_cast<void(*)(void*)>(b+0xb00680);
    TransitionOwned query(release),resolved(release);
    using Getter=TransitionShared*(*)(void*,TransitionShared*);
    auto timelineVt=panelPointer(reinterpret_cast<uintptr_t>(j.timeline));
    reinterpret_cast<Getter>(panelPointer(timelineVt,0xa0))(j.timeline,&query.value);
    if(!query.live()||!readable(query.value.object,0x40)||panelPointer(reinterpret_cast<uintptr_t>(query.value.object))!=ve+0x30cdae8||!panelPointer(reinterpret_cast<uintptr_t>(query.value.object),0x38))throw std::runtime_error("Current query facade unavailable");
    using Lookup=TransitionShared*(*)(void*,TransitionShared*,const std::string*);
    const std::string id(transitionId);
    reinterpret_cast<Lookup>(ve+0x1095c00)(query.value.object,&resolved.value,&id);
    if(!resolved.live()||reinterpret_cast<uintptr_t>(resolved.value.object)!=foundLeft||panelPointer(foundLeft)!=ve+0x2fdb2a8)throw std::runtime_error("Native transition lookup resolved another segment");
    Result current{},low{},high{};get(j.object,"duration",current);get(j.object,"minDuration",low);get(j.object,"maxDuration",high);
    if(!std::isfinite(current.number)||!std::isfinite(low.number)||!std::isfinite(high.number)||low.number<=0||low.number>high.number||current.number<low.number-1e-5||current.number>high.number+1e-5||std::abs(current.number*1000000-nativeDuration)>2)throw std::runtime_error("Transition panel state differs from the native transition");
    using Scene=int32_t(*)();if(reinterpret_cast<Scene>(b+0x69508a0)()!=1)throw std::runtime_error("Not the main editing scene");
}
