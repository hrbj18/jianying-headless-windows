// Resident native transport. No Frida, hooks, JavaScript VM or window actions.
// Each client disconnect closes a pipe. Shutdown drains the last synchronous
// Qt job before this DLL's worker releases its own LoadLibrary reference.
#define NOMINMAX
#include <windows.h>
#include <string>
#include <vector>
#include "bridge.cpp"

struct Bootstrap {wchar_t pipe[160];char token[32];};
struct Request {uint32_t magic,operation;uint64_t object,manager,timeline,vtable,reserved;int32_t returnType,argType;unsigned char value[40];char name[128];char token[32];char timelineId[40];};
static_assert(sizeof(Request)==296);
static HMODULE ownModule;
BOOL WINAPI DllMain(HINSTANCE module,DWORD reason,LPVOID){if(reason==DLL_PROCESS_ATTACH)ownModule=module;return TRUE;}
static void* findExport(HMODULE module,const char* prefix){
 auto base=reinterpret_cast<unsigned char*>(module);
 auto dos=reinterpret_cast<IMAGE_DOS_HEADER*>(base);
 auto nt=reinterpret_cast<IMAGE_NT_HEADERS64*>(base+dos->e_lfanew);
 auto dir=reinterpret_cast<IMAGE_EXPORT_DIRECTORY*>(base+nt->OptionalHeader.DataDirectory[0].VirtualAddress);
 auto names=reinterpret_cast<DWORD*>(base+dir->AddressOfNames);void* result=nullptr;
 for(DWORD i=0;i<dir->NumberOfNames;i++){
  const char* name=reinterpret_cast<char*>(base+names[i]);
  if(!std::strncmp(name,prefix,std::strlen(prefix))){if(result)throw std::runtime_error("Export ambiguous");result=reinterpret_cast<void*>(GetProcAddress(module,name));}
 }
 if(!result)throw std::runtime_error("Export missing");return result;
}
static void initializeCore(){
 auto core=GetModuleHandleW(L"Qt6Core.dll");if(!core)throw std::runtime_error("Qt absent");
 const char* names[]={"?invokeMethod@QMetaObject@@SA_NPEAVQObject@@PEBDW4ConnectionType@Qt@@VQGenericReturnArgument@@VQGenericArgument@@444444444@Z",
 "?invokeMethodImpl@QMetaObject@@CA_NPEAVQObject@@PEAVQSlotObjectBase@QtPrivate@@W4ConnectionType@Qt@@PEAX@Z",
 "?property@QObject@@","?typeName@QVariant@@","?toDouble@QVariant@@","?toBool@QVariant@@","?toString@QVariant@@","??1QString@@","??1QVariant@@"};
 void* functions[9];for(int i=0;i<9;i++)functions[i]=findExport(core,names[i]);live_init(functions);
 auto instance=reinterpret_cast<void*(*)()>(findExport(core,"?instance@QCoreApplication@@"));
 auto application=instance();if(!application)throw std::runtime_error("Application absent");
 auto ve=GetModuleHandleW(L"VECreator.dll");
 live_set_dispatcher(application,ve?reinterpret_cast<unsigned char*>(ve)+0xac45858:nullptr);
}
static bool readAll(HANDLE pipe,void* data,DWORD size){
 auto bytes=static_cast<unsigned char*>(data);DWORD done=0;
 while(done<size){DWORD n=0;if(!ReadFile(pipe,bytes+done,size-done,&n,nullptr)||!n)return false;done+=n;}return true;
}
static bool writeAll(HANDLE pipe,const void* data,DWORD size){
 auto bytes=static_cast<const unsigned char*>(data);DWORD done=0;
 while(done<size){DWORD n=0;if(!WriteFile(pipe,bytes+done,size-done,&n,nullptr)||!n)return false;done+=n;}return true;
}
static DWORD runServer(const Bootstrap& boot){
 initializeCore();
 HANDLE pipe=CreateNamedPipeW(boot.pipe,PIPE_ACCESS_DUPLEX|FILE_FLAG_FIRST_PIPE_INSTANCE,
   PIPE_TYPE_BYTE|PIPE_READMODE_BYTE|PIPE_WAIT|PIPE_REJECT_REMOTE_CLIENTS,1,16384,16384,0,nullptr);
 if(pipe==INVALID_HANDLE_VALUE)return GetLastError();
 bool stop=false;
 while(!stop){
  BOOL connected=ConnectNamedPipe(pipe,nullptr);if(!connected&&GetLastError()!=ERROR_PIPE_CONNECTED)break;
  Request req{};
  while(readAll(pipe,&req,sizeof(req))){
   Result result{};
   if(req.magic!=0x4c455631||std::memcmp(req.token,boot.token,32)!=0)break;
   if(req.reserved>8192||(req.reserved&&req.operation!=6&&req.operation!=7&&req.operation!=10))break;
   std::vector<unsigned char> payload(static_cast<size_t>(req.reserved));
   if(!payload.empty()&&!readAll(pipe,payload.data(),static_cast<DWORD>(payload.size())))break;
   req.name[127]=0;req.timelineId[39]=0;
   if(req.operation==8){result.executed=1;result.kind=2;result.number=GetCurrentProcessId();}
   else if(req.operation==9){result.executed=1;stop=true;}
   else if(req.operation<=7||req.operation==10||req.operation==11)live_call_guarded(reinterpret_cast<void*>(req.object),req.operation,req.name,req.returnType,req.argType,
      req.value,&result,reinterpret_cast<void*>(req.manager),reinterpret_cast<void*>(req.timeline),reinterpret_cast<void*>(req.vtable),req.timelineId,payload.data(),payload.size());
   else result.executed=-8;
   if(!writeAll(pipe,&result,sizeof(result)))break;
   if(stop){FlushFileBuffers(pipe);break;}
  }
  DisconnectNamedPipe(pipe);
 }
 CloseHandle(pipe);return 0;
}
extern "C" __declspec(dllexport) DWORD WINAPI bridge_run(void* parameter){
 Bootstrap boot=*static_cast<Bootstrap*>(parameter);DWORD result=0;
 try {result=runServer(boot);}catch(...){result=0xeeee;}
 // runServer's stack and every Qt-owned slot have been released before unload.
 FreeLibraryAndExitThread(ownModule,result);
}
