# Windows 原生导出 ABI 证据

适用范围仅限剪映专业版 Windows `11.5.0.14471`，`videoeditor.dll` SHA-256：

```text
37cadef37daff82e2ecdcd65080b9cbd7f6f9436f5e56c1ffb90c52c408eb7fb
```

其它构建必须重新完成 RTTI、`.pdata`、请求布局和真机成片验证，不能复用本文 RVA。

## restoreDraft 崩溃根因

`RVA 0x1e263d0` 不是 macOS 风格的 `void(sid, restore, tid)` 入口，而是 `DraftService` handler：

- `RCX=this`；函数从 `this+0x50` 等成员读取服务状态。
- `RDX=hidden sret`；成功与失败尾声均把返回 `shared_ptr` 的对象/控制块写到 `[RDX]`、`[RDX+8]`。
- `R8` 指向按值请求 `shared_ptr` 临时对象；入口读取其对象/控制块并增引用，尾声递减 strong/weak。
- handler 从请求对象 `+0xe0` 读取 restore 标志，因此旧的 88 字节伪请求必然越界；扩大并清零内存也无法构造 vftable、字符串和控制块。

直接把该地址声明成三参数普通函数会破坏寄存器分配和返回缓冲，返回时发生 `ACCESS_VIOLATION` 属于确定的 ABI 错误。

## 安全客户端封装

从 `.?AURestoreDraftReqStruct@lyra@@` 的 MSVC RTTI 得到：

| 项目 | RVA |
| --- | ---: |
| TypeDescriptor | `0x4107350` |
| CompleteObjectLocator | `0x346f778` |
| request vftable | `0x303a650` |
| request 构造引用 | `0x11c4217` |
| `.pdata` 函数范围 | `[0x11c41a0, 0x11c433c)` |

函数入口保存 `ECX` 为 sid、`DL` 为 restore、`R8D` 为 tid；随后分配 `0xf8` 字节
`make_shared` 控制块/对象，设置 `object+0xe0` 和 `object+0x48`，调用统一客户端层并自行释放请求和响应。
因此适配层使用：

```cpp
using RestoreDraftFn = void (*)(int sid, bool restore, int tid);
auto restore = reinterpret_cast<RestoreDraftFn>(base + 0x11c41a0);
restore(sid, true, tid);
```

调用后继续泵事件，直到固定版本日志事件
`DraftService::restoreDraft driverRun, callback !`，超时则不进入导出。

## 其它已修 ABI 问题

- Windows `long` 为 4 字节，导出配置 bitrate 槽为 8 字节；现使用 `std::int64_t`。
- `ProjectClient::init` 前 tid 保持默认 `-1`，响应的 Windows tid 位于 `+0x48`；不能扫描并误取 sid。
- 导出请求工厂 `RVA 0x11b3ac0` 通过真实 `std::shared_ptr<ReqStruct>` 返回类型调用，让 clang-cl 生成 hidden sret；不再把两个裸指针伪装成 `std::shared_ptr`。
- Windows `RespStruct+0x40` 是 `api.capacity`（常见值 15），不是 macOS 的 error code；导出终态使用固定版本的 `VE_INFO_COMPILE_DONE` / `VE_ERROR_COMPILE` 日志事件。
- `closeSession` 为异步操作；适配层等待其回调后才 `shutdown`。
- `videoeditor.dll` 在无 UI 宿主的 `DLL_PROCESS_DETACH` 路径会等待全局线程。隔离助手在 writer 关闭、会话关闭、Server shutdown 且刷新日志后用 `TerminateProcess` 结束自身；父 Python 进程继续执行 MP4 验证。

## 真机验收结果

对 3 秒、1080×1920、30 fps、本地 H.264 + 音频草稿：

- `restoreDraft` 完成并安全返回。
- `VeExportImpl::startCompile, ret=0`（旧错误为 `-142`）。
- 收到 `VE_INFO_COMPILE_DONE` 和两个 Windows 完成标记。
- 输出含 1 路 H.264（1080×1920、30 fps、90 帧、3.000 秒）和 1 路 AAC（44.1 kHz、双声道）。
- `ffprobe` 解析成功，`ffmpeg -v error -xerror ... -f null -` 完整解码退出码为 0。

`-142` 的最后一个非 ABI 原因是测试时误把加密的 `draft_content.json` 当明文交给反序列化器，且明文仍引用不存在的 live 素材路径。正式流水线会在内存解密并通过 `stage_timeline()` 把依赖复制、验哈希、重写到本次 job 后再调用原生助手。
