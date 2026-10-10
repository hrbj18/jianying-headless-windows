// 剪映 Windows 引擎：加载草稿并初始化时间线（原生导出桥接 · 第二阶段）
//
// 目标：把一份草稿 JSON 交给剪映自己的引擎，建立可导出的时间线会话。
// 全程不打开剪映界面、不抢前台焦点。
//
// 与 macOS 版 jianying-headless 的关系：调用序列同构，但**结构体布局不能照抄**——
// macOS 用 libc++（std::string 24 字节），Windows 用 MSVC STL（32 字节）。
// 这里只写字段顺序，具体偏移交给编译器算。
//
// 用法:
//   jy_export.exe <draft.json> [输出目录]

#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include <cstdarg>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <functional>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

// ---------------------------------------------------------------- 引擎类型
namespace lvve {
struct VEGlobalConfig;
struct Draft;
struct PersistentDraft;
namespace adapter {
struct VEAdapterConfig;
}  // namespace adapter
}  // namespace lvve

namespace lyra {
struct RespStruct;
// 只声明要用到的方法，签名用于让编译器生成正确的成员函数调用。
struct Session {
  std::shared_ptr<void> draftTransaction(
      const std::function<void(std::shared_ptr<void>)>&, long);
  std::shared_ptr<void> getVeWrapper();
};
namespace wrapper {
class VeWrapper;
}  // namespace wrapper

// 请求基类。macOS 版源码里它有一个虚析构 + 两个字符串 + 若干标量，
// 这里保持同样的字段顺序，偏移由编译器按 MSVC 规则重算。
struct ReqStruct {
  virtual ~ReqStruct() = default;
  std::string service;
  std::string api;
  long tid = -1;
  bool async = false;
  int flags = 0;
};

// ProjectService/init 的请求体（对应 macOS 版的 InitReqStruct）
struct InitReqStruct : ReqStruct {
  std::string project_id;
  int main_config = -1;
  bool render_track = true;
  bool mixed_track = false;
  bool float_render = false;
  bool reserved = false;
  std::string timeline_name;
  std::shared_ptr<void> draft;
  InitReqStruct() {
    service = "ProjectService";
    api = "init";
  }
};

// DraftService/draftInit 的请求体
struct DraftInitReqStruct : ReqStruct {
  int input_kind = 2;
  std::string json;
  std::shared_ptr<void> draft;
  bool option_a = false;
  bool option_b = true;
  DraftInitReqStruct() {
    service = "DraftService";
    api = "draftInit";
  }
};

// ExportService/exportStart 的请求体。
//
// macOS 版是调用 DLL 里那个「未导出」的 ExportConfig 构造函数（硬编码偏移），
// 再往固定偏移里塞字段。这里换个思路：自己按字段顺序定义结构，让 MSVC 规则
// 去算偏移——std::string 的正确初始化由 C++ 运行时保证，不必依赖那个构造函数。
//
// 关键换算：macOS 的 ReqStruct 是 72 字节、Windows 是 88 字节（std::string
// 32 vs 24）。macOS 里输出路径紧跟在 ReqStruct 之后（+0x48），配置块在 +0x60，
// 因此 Windows 对应为输出路径 +0x58、配置块 +0x78，配置块内部相对偏移不变。
struct ExportStartReqStruct : ReqStruct {
  std::string output_path;  // 0x58（紧跟 ReqStruct）
  // 配置块从 0x78 开始；macOS 那块从 0x60 起、整体 0x3d8，这里留足余量。
  char config[0x3d8];
  ExportStartReqStruct() {
    std::memset(config, 0, sizeof(config));
    service = "ExportService";
    api = "exportStart";
  }
};

class Server {
 public:
  static Server& instance();
  void startup(const lvve::VEGlobalConfig*,
               const std::function<void(const std::function<void()>&)>&);
  void startup(const lvve::VEGlobalConfig*);
  long openSession(const lvve::adapter::VEAdapterConfig*, const std::string&);
  std::shared_ptr<Session> getSession(long);
  std::shared_ptr<RespStruct> invoke(std::shared_ptr<ReqStruct>, long);
  bool pumpOnce();
  void closeSession(long, std::function<void()>);
  void shutdown();
};
}  // namespace lyra

// 非静态的成员函数如果返回非平凡类型，必须用成员函数指针来调用：
// 编译器才会按 MSVC 的规则把 this 放在第一个参数位、返回缓冲排在第二位。
// 若误写成普通函数指针（把返回缓冲放最前），会直接访问违例。
using InvokeMemFn =
    std::shared_ptr<lyra::RespStruct> (lyra::Server::*)(std::shared_ptr<lyra::ReqStruct>, long);

// Session::draftTransaction(const std::function<void(std::shared_ptr<Draft>)>&, long)
// 也是「成员函数 + 返回非平凡类型」，同样必须走成员函数指针。
using DraftTransactionMemFn =
    std::shared_ptr<void> (lyra::Session::*)(
        const std::function<void(std::shared_ptr<void>)>&, long);

namespace lvve {
class Logger {
 public:
  static Logger& getLogger();
  void setLogLevel(const std::string&);
  void setAlogFunction(void (*)(const char*, const char*, int, const char*, int,
                                const char*, ...),
                       void (*)(char, char));
};
class Deserializer {
 public:
  static std::shared_ptr<void> deserialize_persistent_draft(const std::string&);
};
}  // namespace lvve

class ProjectClient {
 public:
  static std::shared_ptr<void> init(std::shared_ptr<lyra::InitReqStruct>, long);
};

namespace lvve {
std::shared_ptr<void> GetDraftFromJson(const std::string&);
}  // namespace lvve

// ---------------------------------------------------------------- 符号名
#define S_GET_LOGGER "?getLogger@Logger@lvve@@SAAEAV12@XZ"
#define S_SET_ALOG "?setAlogFunction@Logger@lvve@@QEAAXP6AXPEBD0H0H0ZZP6AXDD@Z@Z"
#define S_SET_LEVEL \
  "?setLogLevel@Logger@lvve@@QEAAXAEBV?$basic_string@DU?$char_traits@D@std@@V?$allocator@D@2@@std@@@Z"
#define S_INSTANCE "?instance@Server@lyra@@SAPEAU12@XZ"
#define S_STARTUP "?startup@Server@lyra@@QEAAXPEBUVEGlobalConfig@lvve@@@Z"
#define S_OPEN_SESSION \
  "?openSession@Server@lyra@@QEAAJPEBUVEAdapterConfig@adapter@lvve@@AEBV?$basic_string@DU?$char_traits@D@std@@V?$allocator@D@2@@std@@@Z"
#define S_GET_SESSION \
  "?getSession@Server@lyra@@QEAA?AV?$shared_ptr@USession@lyra@@@std@@J@Z"
#define S_PUMP_ONCE "?pumpOnce@Server@lyra@@QEAA_NXZ"
#define S_DESERIALIZE \
  "?deserialize_persistent_draft@Deserializer@lvve@@SA?AV?$shared_ptr@VPersistentDraft@lvve@@@std@@AEBV?$basic_string@DU?$char_traits@D@std@@V?$allocator@D@2@@4@@Z"
#define S_GET_DRAFT_JSON \
  "?GetDraftFromJson@lvve@@YA?AV?$shared_ptr@VDraft@lvve@@@std@@AEBV?$basic_string@DU?$char_traits@D@std@@V?$allocator@D@2@@3@@Z"
#define S_PROJECT_INIT \
  "?init@ProjectClient@@SA?AV?$shared_ptr@UInitRespStruct@lyra@@@std@@V?$shared_ptr@UInitReqStruct@lyra@@@3@J@Z"
#define S_SERVER_INVOKE \
  "?invoke@Server@lyra@@QEAA?AV?$shared_ptr@URespStruct@lyra@@@std@@V?$shared_ptr@UReqStruct@lyra@@@4@J@Z"
#define S_DRAFT_TRANSACTION \
  "?draftTransaction@Session@lyra@@QEAA?AV?$shared_ptr@VDraft@lvve@@@std@@AEBV?$function@$$A6AXV?$shared_ptr@VDraft@lvve@@@std@@@Z@4@J@Z"
#define S_GET_WRAPPER \
  "?getVeWrapper@Session@lyra@@QEAA?AV?$shared_ptr@UVeWrapper@wrapper@lyra@@@std@@XZ"
#define S_GET_ADAPTER_CONFIG \
  "?getVeAdapterConfig@VeWrapper@wrapper@lyra@@QEAA?AV?$shared_ptr@UVEAdapterConfig@adapter@lvve@@@std@@XZ"
#define S_JSON_FROM_DRAFT \
  "?GetJsonFromDraft@lvve@@YA?AV?$basic_string@DU?$char_traits@D@std@@V?$allocator@D@2@@std@@AEBV?$shared_ptr@VDraft@lvve@@@3@@Z"
#define S_INVOKE_SYNC \
  "?invokeSync@Server@lyra@@QEAAXV?$shared_ptr@UReqStruct@lyra@@@std@@AEBV?$function@$$A6AXV?$shared_ptr@URespStruct@lyra@@@std@@@Z@4@J@Z"
#define S_CLOSE_SESSION \
  "?closeSession@Server@lyra@@QEAAXJV?$function@$$A6AXXZ@std@@@Z"
#define S_SHUTDOWN "?shutdown@Server@lyra@@QEAAXXZ"

// 导出请求体的构造函数（非导出符号，靠特征串交叉引用定位，见 find_ctor.py）：
//   videoeditor.dll!0x11b3ac0  — 分配 0x478 字节并设置
//   service="ExportService", api="exportStart"
// macOS 版对应的是硬编码偏移 0x274b018 / 长度 0x3d8。
#define EXPORT_CTOR_RVA 0x11b3ac0ULL
#define EXPORT_REQUEST_SIZE 0x478

// restoreDraft 的三参数客户端封装（未导出符号）。
// 不能直接调用 RVA 0x1e263d0：那是 DraftService handler，Windows x64 ABI 为
//   shared_ptr<Resp> handler(this, hidden_sret, shared_ptr<Req> by-value-temp)
// R8 指向按值 shared_ptr 临时对象，callee 在尾声递减其 strong/weak；绝不是三参数入口。
//
// 正确入口通过 RestoreDraftReqStruct 的 MSVC RTTI 反推：
//   TypeDescriptor -> CompleteObjectLocator -> vftable -> 构造引用 0x11c4217
//   -> .pdata 所属函数入口 0x11c41a0。
// 该函数分配 0xf8 字节 make_shared 控制块（对象大小 0xe8），构造 service/api，
// 设置 object+0xe0 的 restore 标志、object+0x48 的 tid，再进入统一客户端层。
// 反汇编参数寄存器为 ecx=sid、dl=restore、r8d=tid，对应：
//   void(int sid, bool restore, int tid)
#define RESTORE_DRAFT_RVA 0x11c41a0ULL

static int g_lines = 0;
static bool g_quiet = false;
// 日志可能来自引擎工作线程，用 Win32 原子量避免与主线程泵循环发生数据竞争。
static volatile LONG g_compile_done = 0;
static volatile LONG g_compile_error = 0;
static volatile LONG g_restore_done = 0;
static volatile LONG g_close_done = 0;
static bool g_stack_dumped = false;
static void* g_engine_base = nullptr;

// 在日志回调里做栈回溯：日志回调由引擎调用，此刻调用栈上完整保留了
// 「restoreDraft → ... → 日志系统 → 本回调」这条链。
// 这样就能直接拿到 restoreDraft 的返回地址，不必去外部调试器。
static void dump_engine_stack(const char* why) {
  if (g_stack_dumped) {
    return;
  }
  g_stack_dumped = true;
  using CaptureFn = unsigned short(__stdcall*)(unsigned long, unsigned long, void**,
                                               unsigned long*);
  static CaptureFn capture = nullptr;
  if (!capture) {
    HMODULE ntdll = GetModuleHandleW(L"ntdll.dll");
    if (ntdll) {
      capture = reinterpret_cast<CaptureFn>(
          GetProcAddress(ntdll, "RtlCaptureStackBackTrace"));
    }
  }
  if (!capture) {
    std::fprintf(stderr, "  [栈回溯] 取不到 RtlCaptureStackBackTrace\n");
    return;
  }
  void* frames[48] = {nullptr};
  unsigned short count = capture(0, 48, frames, nullptr);
  std::fprintf(stderr, "  [栈回溯] 触发点: %s，共 %u 帧\n", why, count);
  for (unsigned short i = 0; i < count; ++i) {
    unsigned long long addr = reinterpret_cast<unsigned long long>(frames[i]);
    const char* tag = "";
    if (g_engine_base) {
      unsigned long long base = reinterpret_cast<unsigned long long>(g_engine_base);
      if (addr >= base && addr < base + 0x4600000ULL) {
        tag = " <== videoeditor.dll";
      }
    }
    std::fprintf(stderr, "    #%02u  0x%llx%s\n", i, addr, tag);
  }
}

static void nativeLog(const char*, const char* file, int line, const char* function,
                      int level, const char* format, ...) {
  char rendered[8192];
  va_list args;
  va_start(args, format);
  vsnprintf(rendered, sizeof(rendered), format ? format : "", args);
  va_end(args);

  // 引擎自己用这两条事件表示「编译（导出）完成 / 出错」，比轮询文件可靠
  if (strstr(rendered, "export_callback: VE_INFO_COMPILE_DONE")) {
    InterlockedExchange(&g_compile_done, 1);
  }
  if (strstr(rendered, "export_callback: VE_ERROR_COMPILE") ||
      strstr(rendered, "compile_error_callback") ||
      strstr(rendered, "startCompile result=-")) {
    InterlockedExchange(&g_compile_error, 1);
  }
  // restoreDraft 的入口日志一出现就抓栈（此时帧最深，能看到调用者）。
  if (strstr(rendered, "dlxu, restoreDraft")) {
    dump_engine_stack("dlxu, restoreDraft");
  }
  // 与 macOS 版相同，以 driverRun 回调日志作为时间线恢复完成信号。
  if (strstr(rendered, "DraftService::restoreDraft driverRun, callback !")) {
    InterlockedExchange(&g_restore_done, 1);
  }

  ++g_lines;
  if (g_quiet && g_lines > 12) {
    return;
  }
  // 只关心导出/草稿相关的关键事件，其余压掉，避免刷屏
  bool interesting = strstr(rendered, "export") || strstr(rendered, "Export") ||
                     strstr(rendered, "draft") || strstr(rendered, "Draft") ||
                     strstr(rendered, "restore") || strstr(rendered, "ERROR") ||
                     strstr(rendered, "WARN");
  if (!interesting && g_lines > 12) {
    return;
  }
  std::fprintf(stderr, "  [%d] %s:%d %s\n", level, file ? file : "", line, rendered);
}

template <typename Fn>
static Fn sym(HMODULE dll, const char* name) {
  void* address = reinterpret_cast<void*>(GetProcAddress(dll, name));
  if (!address) {
    std::fprintf(stderr, "  [缺失导出符号] %s\n", name);
  }
  return reinterpret_cast<Fn>(address);
}

[[noreturn]] static void terminate_child(UINT code) {
  std::fflush(nullptr);
  TerminateProcess(GetCurrentProcess(), code);
  // 仅用于满足编译器的 noreturn 控制流分析；TerminateProcess 成功后不会执行。
  for (;;) {
    Sleep(INFINITE);
  }
}

static std::string readFile(const char* path, bool& ok) {
  std::ifstream in(path, std::ios::binary);
  if (!in) {
    ok = false;
    return {};
  }
  std::ostringstream buffer;
  buffer << in.rdbuf();
  ok = true;
  return buffer.str();
}

static void dumpObject(const std::shared_ptr<void>& object, const char* label) {
  if (!object) {
    std::printf("    %s = (空)\n", label);
    return;
  }
  std::printf("    %s = %p\n", label, object.get());
  const auto* bytes = reinterpret_cast<const unsigned char*>(object.get());
  std::printf("      前 128 字节: ");
  for (int i = 0; i < 128; ++i) {
    std::printf("%02x", bytes[i]);
    if (i % 16 == 15) {
      std::printf("\n                   ");
    }
  }
  std::printf("\n      按 8 字节整数解读（偏移: 值）:\n        ");
  for (int i = 0; i < 128; i += 8) {
    long value = 0;
    std::memcpy(&value, bytes + i, sizeof(long));
    if (value >= 0 && value < 100000) {
      std::printf("0x%02x:%ld  ", i, value);
    }
  }
  std::printf("\n");
}

int main(int argc, char** argv) {
  // 崩溃时 stdout 缓冲会整块丢失，排查阶段先关掉缓冲
  std::setvbuf(stdout, nullptr, _IONBF, 0);
  if (argc < 8) {
    std::printf("用法: native-export-helper.exe <timeline.json> <output.mp4> "
                "<width> <height> <fps> <bitrate> <timeout-seconds>\n");
    return 2;
  }
  const int output_width = std::stoi(argv[3]);
  const int output_height = std::stoi(argv[4]);
  const double output_fps = std::stod(argv[5]);
  const std::int64_t output_bitrate = std::stoll(argv[6]);
  const int timeout_seconds = std::stoi(argv[7]);
  if (output_width < 16 || output_height < 16 || output_fps < 1.0 ||
      output_bitrate < 100000 || timeout_seconds < 5) {
    std::fprintf(stderr, "导出参数超出安全范围\n");
    return 2;
  }

  DWORD install_chars = GetEnvironmentVariableW(L"JY_VIDEOEDITOR_DIR", nullptr, 0);
  if (!install_chars) {
    std::fprintf(stderr, "缺少 JY_VIDEOEDITOR_DIR；父进程必须先完成 DLL 身份校验\n");
    return 2;
  }
  std::wstring install(install_chars, L'\0');
  DWORD copied = GetEnvironmentVariableW(L"JY_VIDEOEDITOR_DIR", install.data(), install_chars);
  if (!copied || copied >= install_chars) {
    std::fprintf(stderr, "读取 JY_VIDEOEDITOR_DIR 失败\n");
    return 2;
  }
  install.resize(copied);
  long tid_override = -1;
  bool tid_explicit = false;
  bool do_restore = true;

  bool ok = false;
  std::string draft_json = readFile(argv[1], ok);
  if (!ok || draft_json.empty()) {
    std::printf("读不到草稿 JSON: %s\n", argv[1]);
    return 1;
  }
  std::printf("[0] 草稿 JSON %zu 字节\n", draft_json.size());

  std::wstring dll_path = std::wstring(install) + L"\\videoeditor.dll";
  SetDllDirectoryW(install.c_str());
  HMODULE dll = LoadLibraryExW(dll_path.c_str(), nullptr,
                               LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR |
                                   LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
  if (!dll) {
    std::printf("[1] 加载失败 GetLastError=%lu\n", GetLastError());
    return 1;
  }
  g_engine_base = reinterpret_cast<void*>(dll);
  std::printf("[1] 引擎已加载\n");

  auto get_logger = sym<lvve::Logger& (*)()>(dll, S_GET_LOGGER);
  auto set_alog = sym<void (*)(lvve::Logger*, void*, void*)>(dll, S_SET_ALOG);
  auto set_level = sym<void (*)(lvve::Logger*, const std::string*)>(dll, S_SET_LEVEL);
  if (get_logger && set_alog && set_level) {
    lvve::Logger& logger = get_logger();
    set_alog(&logger, reinterpret_cast<void*>(&nativeLog), nullptr);
    std::string level = "debug";
    set_level(&logger, &level);
  }

  auto instance = sym<lyra::Server& (*)()>(dll, S_INSTANCE);
  auto startup = sym<void (*)(lyra::Server*, const void*)>(dll, S_STARTUP);
  auto open_session =
      sym<long (*)(lyra::Server*, const void*, const std::string*)>(dll, S_OPEN_SESSION);
  auto get_session = sym<void (*)(lyra::Server*, std::shared_ptr<lyra::Session>*, long)>(
      dll, S_GET_SESSION);
  auto pump_once = sym<bool (*)(lyra::Server*)>(dll, S_PUMP_ONCE);
  auto deserialize =
      sym<std::shared_ptr<void> (*)(const std::string*)>(dll, S_DESERIALIZE);
  auto get_draft_json =
      sym<std::shared_ptr<void> (*)(const std::string*)>(dll, S_GET_DRAFT_JSON);
  auto project_init = sym<std::shared_ptr<void> (*)(
      std::shared_ptr<lyra::InitReqStruct>, long)>(dll, S_PROJECT_INIT);
  void* invoke_raw = reinterpret_cast<void*>(GetProcAddress(dll, S_SERVER_INVOKE));
  if (!invoke_raw) {
    std::printf("    [缺失] Server::invoke\n");
  }
  if (!instance || !startup || !open_session || !get_session || !deserialize ||
      !project_init) {
    terminate_child(1);
  }
  // C++ 标准不允许 void* 直接 reinterpret_cast 成成员函数指针，
  // 但 MSVC/clang-cl 下非虚单一继承的成员函数指针就是 8 字节函数地址，
  // 用 memcpy 做位拷贝即可（先断言大小一致）。
  InvokeMemFn server_invoke = nullptr;
  static_assert(sizeof(InvokeMemFn) == sizeof(void*),
                "本平台成员函数指针不是单指针宽度，需要改用 thunk");
  std::memcpy(&server_invoke, &invoke_raw, sizeof(invoke_raw));

  std::printf("[2] 启动引擎\n");
  lyra::Server& server = instance();
  startup(&server, nullptr);
  std::string name = "codex-headless-export";
  long sid = open_session(&server, nullptr, &name);
  std::printf("    sid = %ld\n", sid);
  if (sid < 0) {
    terminate_child(1);
  }
  for (int i = 0; i < 30; ++i) {
    pump_once(&server);
    Sleep(16);
  }
  std::shared_ptr<lyra::Session> session;
  get_session(&server, &session, sid);
  std::printf("    session = %p\n", static_cast<void*>(session.get()));
  if (!session) {
    terminate_child(1);
  }

  std::printf("[3] 解析草稿 JSON -> PersistentDraft\n");
  std::shared_ptr<void> persistent = deserialize(&draft_json);
  std::printf("    persistent = %p\n", persistent.get());
  if (!persistent && get_draft_json) {
    std::printf("    · deserialize 返回空，改用 GetDraftFromJson 兜底\n");
  }

  std::printf("[4] 构造 InitReqStruct 并调用 ProjectClient::init\n");
  auto request = std::make_shared<lyra::InitReqStruct>();
  // 与已验证的 macOS 流程一致：ProjectClient::init 前 tid 保持默认 -1，
  // 由项目初始化分配时间线；把 sid 写入 tid 会错误地产生 timeline_id=1。
  request->project_id = "codex-headless-export";
  request->timeline_name = "codex-headless-export";
  request->draft = persistent;
  std::printf("    sizeof(ReqStruct)=%zu  sizeof(InitReqStruct)=%zu\n",
              sizeof(lyra::ReqStruct), sizeof(lyra::InitReqStruct));
  std::printf("    request 对象地址 = %p\n", static_cast<void*>(request.get()));
  std::shared_ptr<void> initialized = project_init(request, sid);
  dumpObject(initialized, "InitRespStruct");
  std::printf("    （若上面地址与 request 相同，说明返回值写回了请求体，ABI 需再核对）\n");

  for (int i = 0; i < 30; ++i) {
    pump_once(&server);
    Sleep(16);
  }

  // 从响应里取 tid。macOS 版读的是偏移 0x38，Windows 的响应体更大
  // （std::string 差 8 字节、结构也不同），实测这里在 0x48。
  long tid = 0;
  if (tid_explicit) {
    tid = tid_override;
    std::printf("    tid 由命令行指定 = %ld\n", tid);
  }
  if (!tid_explicit && initialized) {
    const auto* response_bytes =
        reinterpret_cast<const unsigned char*>(initialized.get());
    // macOS 响应偏移为 0x38；Windows 两个 MSVC string 各多 8 字节，故为 0x48。
    // 不能扫描并挑出 sid：sid=1 与本次实际 tid=0 是两个不同标识。
    std::memcpy(&tid, response_bytes + 0x48, sizeof(tid));
    std::printf("    按 InitRespStruct+0x48 读取 tid = %ld\n", tid);
  }

  std::printf("[5] 构造 DraftInitReqStruct 并调用 Server::invoke\n");
  // 请求对象必须活到进程结束：引擎会异步引用它。
  std::shared_ptr<lyra::DraftInitReqStruct> binding;
  if (get_draft_json) {
    binding = std::make_shared<lyra::DraftInitReqStruct>();
    binding->tid = tid;
    binding->draft = get_draft_json(&draft_json);
    std::printf("    binding.draft = %p  sizeof=%zu\n", binding->draft.get(),
                sizeof(lyra::DraftInitReqStruct));
    dumpObject(std::static_pointer_cast<void>(binding), "DraftInitReqStruct");
    std::printf("    期望: service='DraftService' api='draftInit' tid=%ld\n", tid);
    if (server_invoke && binding->draft) {
      std::shared_ptr<lyra::RespStruct> response =
          (server.*server_invoke)(binding, sid);
      std::printf("    DraftInitRespStruct = %p\n",
                  static_cast<void*>(response.get()));
      for (int i = 0; i < 40; ++i) {
        pump_once(&server);
        Sleep(16);
      }
    }
  }

  std::printf("[6] 从引擎回读运行时草稿（证明草稿真的进了时间线）\n");
  void* tx_raw = reinterpret_cast<void*>(GetProcAddress(dll, S_DRAFT_TRANSACTION));
  void* json_raw = reinterpret_cast<void*>(GetProcAddress(dll, S_JSON_FROM_DRAFT));
  if (tx_raw && json_raw && session) {
    DraftTransactionMemFn transaction = nullptr;
    static_assert(sizeof(DraftTransactionMemFn) == sizeof(void*),
                  "成员函数指针宽度不符");
    std::memcpy(&transaction, &tx_raw, sizeof(tx_raw));
    auto json_from_draft =
        reinterpret_cast<std::string (*)(const std::shared_ptr<void>*)>(json_raw);

    std::shared_ptr<void> runtime_draft;
    std::function<void(std::shared_ptr<void>)> visitor =
        [&](std::shared_ptr<void> draft) { runtime_draft = draft; };
    std::shared_ptr<void> result = (session.get()->*transaction)(visitor, tid);
    std::printf("    draftTransaction 返回 %p, 回调拿到 %p\n",
                result.get(), runtime_draft.get());
    if (runtime_draft) {
      std::string round_trip = json_from_draft(&runtime_draft);
      std::printf("    ★ 从引擎回读草稿 %zu 字节（原始 %zu 字节）\n",
                  round_trip.size(), draft_json.size());
      std::printf("    前 200 字符: %.200s\n", round_trip.c_str());
      // 保留引擎实际接收并规范化后的草稿，便于诊断模板、歌词等由
      // DraftService 二次编译的材料。失败不阻断导出。
      const std::string round_trip_path = std::string(argv[2]) + ".runtime.json";
      std::ofstream round_trip_file(round_trip_path, std::ios::binary);
      if (round_trip_file) {
        round_trip_file.write(round_trip.data(),
                              static_cast<std::streamsize>(round_trip.size()));
        round_trip_file.close();
        std::printf("    引擎回读草稿已写入: %s\n", round_trip_path.c_str());
      } else {
        std::printf("    · 无法写入引擎回读草稿: %s\n", round_trip_path.c_str());
      }
    }
  } else {
    std::printf("    · 缺少 draftTransaction / GetJsonFromDraft 导出\n");
  }

  std::printf("[7] 完成\n");
  // ---- 第八步：触发出片 ----
  std::string output = argv[2];
  void* sync_raw = reinterpret_cast<void*>(GetProcAddress(dll, S_INVOKE_SYNC));
  if (!sync_raw) {
    std::printf("    [缺失] Server::invokeSync\n");
    terminate_child(1);
  }
  using InvokeSyncMemFn =
      void (lyra::Server::*)(
          std::shared_ptr<lyra::ReqStruct>,
          const std::function<void(std::shared_ptr<lyra::RespStruct>)>&, long);
  InvokeSyncMemFn invoke_sync = nullptr;
  static_assert(sizeof(InvokeSyncMemFn) == sizeof(void*), "成员函数指针宽度不符");
  std::memcpy(&invoke_sync, &sync_raw, sizeof(sync_raw));

  // 导出前先让 DraftService 恢复时间线（macOS 版对应 restore_draft 调用）。
  auto* base = reinterpret_cast<char*>(dll);
#if 0  // 仅逆向诊断：不得在生产导出中扫描未知大小的 adapter 对象。
  // ---- 关键前置：设置渲染所需的素材资源根目录 ----
  // macOS 版会取 adapter 配置并把它内部那个「内置效果资源路径」字段从空填成
  // lumi_js_resources_video 的绝对路径；字段为空时加蒙版/特效的时间线无法编译，
  // 表现为 startCompile 直接失败。
  {
    void* gw_raw = reinterpret_cast<void*>(GetProcAddress(dll, S_GET_WRAPPER));
    if (gw_raw) {
      using GetWrapperMemFn = std::shared_ptr<void> (lyra::Session::*)();
      GetWrapperMemFn get_wrapper = nullptr;
      std::memcpy(&get_wrapper, &gw_raw, sizeof(gw_raw));
      std::shared_ptr<void> wrapper = (session.get()->*get_wrapper)();
      std::printf("[7.2] VeWrapper = %p\n", wrapper.get());
      if (wrapper) {
        void* ac_raw =
            reinterpret_cast<void*>(GetProcAddress(dll, S_GET_ADAPTER_CONFIG));
        std::printf("      getVeAdapterConfig 符号 = %p\n", ac_raw);
        if (ac_raw) {
          // 成员函数指针在 MSVC x64 下就是函数地址，用占位类声明即可。
          struct AdapterHolder {
            char dummy[0];
          };
          using GetAdapterMemFn =
              std::shared_ptr<void> (AdapterHolder::*)();
          GetAdapterMemFn get_adapter = nullptr;
          std::memcpy(&get_adapter, &ac_raw, sizeof(ac_raw));
          auto* holder = reinterpret_cast<AdapterHolder*>(wrapper.get());
          std::shared_ptr<void> adapter = (holder->*get_adapter)();
          std::printf("      adapter config = %p\n", adapter.get());
          if (adapter) {
            // 扫描前 0x1000 字节里「capacity==15 且 size==0」的 MSVC 空字符串，
            // 这些就是候选的待填资源路径字段。
            const char* base_bytes = reinterpret_cast<const char*>(adapter.get());
            int shown = 0;
            for (size_t off = 0; off + 32 <= 0x1000 && shown < 12; off += 1) {
              size_t size = 0, capacity = 0;
              std::memcpy(&size, base_bytes + off + 16, 8);
              std::memcpy(&capacity, base_bytes + off + 24, 8);
              if (size == 0 && capacity == 15) {
                std::printf("        空字符串候选: 偏移 0x%zx\n", off);
                ++shown;
              }
            }
            // 同时把非空字符串列出来，找出看起来像「资源根目录」的那个
            std::printf("      非空字符串字段:\n");
            int shown2 = 0;
            for (size_t off = 0; off + 32 <= 0x1000 && shown2 < 40; off += 1) {
              size_t size = 0, capacity = 0;
              std::memcpy(&size, base_bytes + off + 16, 8);
              std::memcpy(&capacity, base_bytes + off + 24, 8);
              if (size > 0 && size < 260 && capacity >= size && capacity < 4096) {
                const char* text = capacity < 16
                                       ? base_bytes + off
                                       : *reinterpret_cast<const char* const*>(base_bytes + off);
                std::string value;
                bool printable = text != nullptr;
                if (printable) {
                  for (size_t i = 0; i < size; ++i) {
                    unsigned char c = static_cast<unsigned char>(text[i]);
                    if (c < 32 || c > 126) {
                      printable = false;
                      break;
                    }
                    value.push_back(static_cast<char>(c));
                  }
                }
                if (printable && value.size() >= 3) {
                  std::printf("        0x%04zx size=%zu %s\n", off, size, value.c_str());
                  ++shown2;
                }
              }
            }
          }
        }
      }
    }
  }
#endif

  if (!do_restore) {
    std::printf("[7.5] 跳过 restoreDraft（--no-restore）\n");
  } else {
    // 调正确的客户端封装；它在 DLL 内构造真正的 0xe8 字节请求对象。
    // 绝不能调用 0x1e263d0 handler，也不能手工伪造/清零请求体。
    std::printf("[7.5] 调用 restoreDraft 客户端封装 (RVA 0x%llx)\n",
                static_cast<unsigned long long>(RESTORE_DRAFT_RVA));
    using RestoreDraftFn = void (*)(int, bool, int);
    auto restore_draft = reinterpret_cast<RestoreDraftFn>(
        reinterpret_cast<char*>(dll) + RESTORE_DRAFT_RVA);
    InterlockedExchange(&g_restore_done, 0);
    restore_draft(static_cast<int>(sid), true, static_cast<int>(tid));

    std::printf("    调用已返回，等待 driverRun 回调完成信号\n");
    const int kRestoreTimeoutMs = timeout_seconds * 1000;
    for (int elapsed = 0; elapsed < kRestoreTimeoutMs; elapsed += 20) {
      pump_once(&server);
      if (InterlockedCompareExchange(&g_restore_done, 0, 0)) {
        break;
      }
      Sleep(20);
    }
    if (!InterlockedCompareExchange(&g_restore_done, 0, 0)) {
      std::fprintf(stderr, "    × restoreDraft 在超时时间内未完成，拒绝进入导出\n");
      terminate_child(1);
    }
    std::printf("    ★ restoreDraft 完成且返回路径未崩溃\n");
  }

  std::printf("[8] 触发导出 -> %s\n", output.c_str());

  // 那个地址不是构造函数，而是「创建请求体并返回 shared_ptr」的工厂函数。
  // 用真实返回类型调用，让 clang-cl 按 MSVC x64 ABI 自动生成 hidden sret；不能把
  // 两个裸指针伪装成 std::shared_ptr，否则违反 C++ 对象生命周期与严格别名规则。
  using MakeExportRequestFn = std::shared_ptr<lyra::ReqStruct> (*)();
  auto make_export_request =
      reinterpret_cast<MakeExportRequestFn>(base + EXPORT_CTOR_RVA);
  std::shared_ptr<lyra::ReqStruct> export_req = make_export_request();
  void* storage = export_req.get();
  std::printf("    工厂函数返回: object=%p\n", storage);
  if (!storage) {
    std::printf("    × 工厂函数未返回对象\n");
    terminate_child(1);
  }

  // MSVC std::string：16 字节 SSO 缓冲 + size(8) + capacity(8)
  auto read_msvc_string = [](const char* at, size_t limit) -> std::string {
    size_t size = 0;
    size_t capacity = 0;
    std::memcpy(&size, at + 16, sizeof(size));
    std::memcpy(&capacity, at + 24, sizeof(capacity));
    if (size == 0 || size > limit) {
      return {};
    }
    const char* data = capacity < 16 ? at : nullptr;
    if (!data) {
      std::memcpy(&data, at, sizeof(data));
    }
    return data ? std::string(data, size) : std::string();
  };
  char* raw = static_cast<char*>(storage);
  std::printf("    构造后前 192 字节:\n      ");
  for (int i = 0; i < 192; ++i) {
    std::printf("%02x", static_cast<unsigned char>(raw[i]));
    if (i % 32 == 31) {
      std::printf("\n      ");
    }
  }
  std::printf("\n      可打印字符: ");
  for (int i = 0; i < 192; ++i) {
    unsigned char c = static_cast<unsigned char>(raw[i]);
    std::printf("%c", (c >= 32 && c < 127) ? c : '.');
  }
  std::printf("\n");
  std::printf("    构造后 service=%s api=%s\n",
              read_msvc_string(raw + 0x08, 64).c_str(),
              read_msvc_string(raw + 0x28, 64).c_str());

  // 注意：反汇编显示这里是 mov %ebx（32 位写入），tid 在 Windows 上是 4 字节。
  // 之前按 8 字节写，会把紧随其后的 async / flags 一起覆盖掉。
  int* tid_slot = reinterpret_cast<int*>(static_cast<char*>(storage) + 0x48);
  *tid_slot = static_cast<int>(tid);
  // 输出路径：macOS 在 0x48、Windows 因 ReqStruct 更大而在 0x58
  std::string* output_slot =
      reinterpret_cast<std::string*>(static_cast<char*>(storage) + 0x58);
  *output_slot = output;  // 工厂已正确构造，直接赋值即可
  char* config = static_cast<char*>(storage) + 0x78;

  int width = output_width, height = output_height;
  double fps = output_fps;
  // Windows 的 long 只有 4 字节；该配置槽是 8 字节，必须显式使用 int64_t。
  std::int64_t bitrate = output_bitrate;
  // 偏移全部 = macOS 版 + 8：Windows 的 config 内部多一个 std::string。
  // 验证依据：config 自己的构造函数把 fps 默认值 30.0 写在 +0x52
  // （macOS 版是 +0x4a，恰好差 8）。
  std::memcpy(config + 0x47, &width, sizeof(width));
  std::memcpy(config + 0x4b, &height, sizeof(height));
  config[0x4f] = 0;  // 硬件编码偏好，与 macOS 版同一语义
  std::memcpy(config + 0x52, &fps, sizeof(fps));
  std::memcpy(config + 0x66, &bitrate, sizeof(bitrate));
  config[0x281] = 1;  // 使用原生 FFmpeg MP4 writer

  // 回读关键字段，确认写入真的生效（偏移错了会静默失败）
  auto read_at = [](const char* at, size_t n) {
    std::string s("                    ");
    s.clear();
    for (size_t i = 0; i < n; ++i) {
      unsigned char c = static_cast<unsigned char>(at[i]);
      s.push_back((c >= 32 && c < 127) ? static_cast<char>(c) : '.');
    }
    return s;
  };
  int back_w = 0, back_h = 0;
  double back_fps = 0.0;
  std::int64_t back_bitrate = 0;
  std::memcpy(&back_w, config + 0x47, 4);
  std::memcpy(&back_h, config + 0x4b, 4);
  std::memcpy(&back_fps, config + 0x52, 8);
  std::memcpy(&back_bitrate, config + 0x66, 8);
  std::printf("    回读: width=%d height=%d fps=%.2f bitrate=%lld\n", back_w,
              back_h, back_fps, static_cast<long long>(back_bitrate));
  std::printf("    回读 output 槽位(0x58)=%s\n",
              read_msvc_string(raw + 0x58, 256).c_str());
  std::printf("    config[0x281]=%d\n", static_cast<int>(config[0x281]));

  // Windows RespStruct 的两个 std::string 比 macOS 各大 8 字节；macOS 的
  // error_code 偏移 0x40 在 Windows 恰好落在 api.capacity（值为 15）。
  // 因此回调只计数，不再把未确认的固定偏移当终态；完成/失败以引擎日志事件为准。
  volatile LONG callback_count = 0;
  volatile LONG null_callback_count = 0;
  std::function<void(std::shared_ptr<lyra::RespStruct>)> on_response =
      [&](std::shared_ptr<lyra::RespStruct> response) {
        InterlockedIncrement(&callback_count);
        if (!response) {
          InterlockedIncrement(&null_callback_count);
        }
      };

  InterlockedExchange(&g_compile_done, 0);
  InterlockedExchange(&g_compile_error, 0);
  (server.*invoke_sync)(export_req, on_response, sid);
  std::printf("    exportStart 已发出，等待编译完成…\n");

  const int kTimeoutSeconds = timeout_seconds;
  for (int i = 0; i < kTimeoutSeconds * 20; ++i) {
    pump_once(&server);
    if (InterlockedCompareExchange(&g_compile_done, 0, 0) ||
        InterlockedCompareExchange(&g_compile_error, 0, 0)) {
      break;
    }
    Sleep(50);
  }
  const LONG done = InterlockedCompareExchange(&g_compile_done, 0, 0);
  const LONG failed = InterlockedCompareExchange(&g_compile_error, 0, 0);
  const LONG callbacks = InterlockedCompareExchange(&callback_count, 0, 0);
  const LONG null_callbacks = InterlockedCompareExchange(&null_callback_count, 0, 0);
  std::printf("    compile_done=%ld compile_error=%ld callbacks=%ld null=%ld\n",
              done, failed, callbacks, null_callbacks);
  const bool export_ok = done && !failed;
  if (!export_ok) {
    std::fprintf(stderr, "    × 原生导出失败或等待超时；残留文件不是可交付成片\n");
  } else {
    // 排空原生完成回调与 writer close 任务，避免主进程提前退出留下无 moov 的 MP4。
    for (int i = 0; i < 40; ++i) {
      pump_once(&server);
      Sleep(50);
    }
    std::printf("    ★ 导出完成，原生 writer 已获得额外 2 秒收尾时间\n");
  }

  // 与 macOS 版相同，显式释放请求/会话并关闭 Server；否则引擎工作线程会让
  // 实验进程停在 main 返回后的静态析构阶段。
  void* close_raw = reinterpret_cast<void*>(GetProcAddress(dll, S_CLOSE_SESSION));
  void* shutdown_raw = reinterpret_cast<void*>(GetProcAddress(dll, S_SHUTDOWN));
  if (!close_raw || !shutdown_raw) {
    std::fprintf(stderr, "    × 缺少 closeSession/shutdown 导出符号\n");
    terminate_child(1);
  }
  using CloseSessionMemFn = void (lyra::Server::*)(long, std::function<void()>);
  using ShutdownMemFn = void (lyra::Server::*)();
  CloseSessionMemFn close_session = nullptr;
  ShutdownMemFn shutdown = nullptr;
  static_assert(sizeof(CloseSessionMemFn) == sizeof(void*) &&
                    sizeof(ShutdownMemFn) == sizeof(void*),
                "Server 清理成员函数指针宽度不符");
  std::memcpy(&close_session, &close_raw, sizeof(close_raw));
  std::memcpy(&shutdown, &shutdown_raw, sizeof(shutdown_raw));

  InterlockedExchange(&g_close_done, 0);
  (server.*close_session)(sid, [] { InterlockedExchange(&g_close_done, 1); });
  for (int elapsed = 0; elapsed < 10000; elapsed += 20) {
    pump_once(&server);
    if (InterlockedCompareExchange(&g_close_done, 0, 0)) {
      break;
    }
    Sleep(20);
  }
  const bool close_ok = InterlockedCompareExchange(&g_close_done, 0, 0) != 0;
  if (!close_ok) {
    std::fprintf(stderr, "    × closeSession 在 10 秒内未完成\n");
  }

  export_req.reset();
  binding.reset();
  request.reset();
  initialized.reset();
  persistent.reset();
  session.reset();
  (server.*shutdown)();
  if (close_ok && export_ok) {
    std::printf("JY_WINDOWS_NATIVE_RESTORE_DONE\n");
    std::printf("JY_WINDOWS_NATIVE_EXPORT_DONE\n");
  }
  std::printf("[9] 完成\n");
  // videoeditor.dll 的进程级静态析构在无 UI 宿主中会等待仍存活的全局线程。
  // 此程序必须作为隔离子进程运行；Server 已 shutdown、writer 已 close 后立即退出，
  // 避免再次进入不属于公开 ABI 的 DLL 全局析构路径。
  const UINT exit_code = (close_ok && export_ok) ? 0U : 1U;
  // _Exit 最终会走 ExitProcess 并通知 videoeditor.dll 做 DLL_PROCESS_DETACH，
  // 该无 UI 宿主路径仍会等待全局线程；terminate_child 不执行 DLL detach。
  terminate_child(exit_code);
}
