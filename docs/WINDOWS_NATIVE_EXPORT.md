# Windows 原生导出 ABI 证据

适用范围为下列两个精确构建，`videoeditor.dll` SHA-256 分别绑定：

| 构建 | SHA-256 |
| --- | --- |
| `11.4.7.14462` | `fa89997a94e96cf97c8ee436a56ab028ea5f87731214696ba43ff74c0fdc0fa0` |
| `11.5.0.14471` | `37cadef37daff82e2ecdcd65080b9cbd7f6f9436f5e56c1ffb90c52c408eb7fb` |

11.4.7 已完成静态核对、加解密回环、官方实际编辑和原生导出，并接入正常入口。
其它构建仍需重新核对 RTTI、`.pdata`、请求布局及真实成片，不能按版本前缀或只替换期望哈希。
调用方式见 [Windows 调用指南](WINDOWS-CLI.md)。

## restoreDraft 崩溃根因

`RVA 0x1e263d0` 不是 macOS 风格的 `void(sid, restore, tid)` 入口，而是 `DraftService` handler：

- `RCX=this`；函数从 `this+0x50` 等成员读取服务状态。
- `RDX=hidden sret`；成功与失败尾声均把返回 `shared_ptr` 的对象/控制块写到 `[RDX]`、`[RDX+8]`。
- `R8` 指向按值请求 `shared_ptr` 临时对象；入口读取其对象/控制块并增引用，尾声递减 strong/weak。
- handler 从请求对象 `+0xe0` 读取 restore 标志，因此旧的 88 字节伪请求必然越界；扩大并清零内存也无法构造 vftable、字符串和控制块。

直接把该地址声明成三参数普通函数会破坏寄存器分配和返回缓冲，返回时发生 `ACCESS_VIOLATION` 属于确定的 ABI 错误。

## 安全客户端封装

从 `.?AURestoreDraftReqStruct@lyra@@` 的 MSVC RTTI 得到以下结果。
两构建的数据区地址不同，但正式助手使用的客户端函数入口及布局一致：

| 项目 | 11.4.7.14462 RVA | 11.5.0.14471 RVA |
| --- | ---: | ---: |
| TypeDescriptor | `0x41032f0` | `0x4107350` |
| CompleteObjectLocator | `0x346bcf8` | `0x346f778` |
| request vftable | `0x3037650` | `0x303a650` |
| request 构造引用 | `0x11c4217` | `0x11c4217` |
| `.pdata` 函数范围 | `[0x11c41a0, 0x11c433c)` | `[0x11c41a0, 0x11c433c)` |

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

### 11.4.7.14462

静态 PE 检查确认 19 个原生助手导出符号及 3 个 `EncryptUtils` 符号齐全。
`0x11b3ac0` 是导出请求工厂的函数入口，分配 `0x478` 字节并设置 `ExportService/exportStart`；
请求的 tid、输出字符串和配置块分别位于 `+0x48`、`+0x58`、`+0x78`。
配置构造函数 `0x11b57a0` 把 `30.0` 写入 `config+0x52`，与正式助手一致。
这些证据先用于允许隔离样本测试，正式支持依据还包括以下实际结果：

- 合成 JSON 加密/解密回环逐字节一致。
- 原始原生助手分别经 MSVC 和 `clang-cl` 编译，完成三秒基础视频与源音频导出。
- 官方 Lyra 新建外部工程、导入素材、同步，并实际修改视频时长、音量和普通文字。
- 官方编辑后的 `187.0.0 / 360000` 时间线和基础构建的 `185.0.0 / 360000` 时间线均已渲染。
- 正常入口 `jianying.ps1 export-draft` 导出已保存的编辑工程，得到 1920×1080、30 fps、
  90 帧、3.000 秒 H.264 视频和 AAC 音频；完整解码通过，源草稿与素材哈希保持不变。
- 先前合成样本还用源素材参考帧检查缩放、截取和画面内容，并对 PCM 检查非静音及 440 Hz 主频。
  这类样本检查不等于对任意用户成片的主观视听验收。

正式配置同时保留两个精确 DLL 哈希；EXE 的真实 PE 文件版本必须与目录名一致，
并继续验证官方 Authenticode 发布者。没有修改官方 DLL，也没有为任意新哈希自动注册适配。

### 11.5.0.14471 历史验收

对 3 秒、1080×1920、30 fps、本地 H.264 + 音频草稿：

- `restoreDraft` 完成并安全返回。
- `VeExportImpl::startCompile, ret=0`（旧错误为 `-142`）。
- 收到 `VE_INFO_COMPILE_DONE` 和两个 Windows 完成标记。
- 输出含 1 路 H.264（1080×1920、30 fps、90 帧、3.000 秒）和 1 路 AAC（44.1 kHz、双声道）。
- `ffprobe` 解析成功，`ffmpeg -v error -xerror ... -f null -` 完整解码退出码为 0。

`-142` 的最后一个非 ABI 原因是测试时误把加密的 `draft_content.json` 当明文交给反序列化器，且明文仍引用不存在的 live 素材路径。正式流水线会解密并通过 `stage_timeline()` 把依赖复制、验哈希、重写到本次 job 后再调用原生助手。

## 正常导出路径与范围

`jianying.ps1 export --build ...` 输入已验证的不可变 JSON 计划构建；
`jianying.ps1 export-draft --draft-dir ...` 输入已保存的磁盘工程，按声明的主时间线解析，
在新 job 中复制和校验素材后导出。后者不会把 GUI 中未保存的内存状态当作输入。
结果须为 `encoded-and-decoded`；保留的日志、流/时长/帧数、完整解码与源文件复核均用于验收。

11.4.7 的扩展范围还包括多轨、程序化关键帧、变速、解析过的静态本地 TTF/OTF 字体、
双边原生音频淡化（type 4）和独立原生帧预览。旧 `native_edit` 副本编辑流程仍未取得验证。
其它构建需各自证据，不会因地址布局相似而继承这些扩展。

正常 plan 的 `keyframes.<channel>[].at_us` 是片段局部时间。精确 Windows 11.4.7 的
正向 1 倍视频现支持非零 `source_start_us`：原生保存的 `time_offset` 必须是
`source_start_us + at_us`，构建读回采用相同映射。真实直播 5163 秒入点的 4 秒样本中，
直接把局部时间写入原生字段会编码成功却没有推镜；修正后 1→1.8→1 的缩放在播放器
与 120 帧完整导出中均可见。变速关键帧、裁切音频音量关键帧仍需单独验收并保持拒绝。

## 11.4.7 视觉资源与蒙版配置

`windows_vfx.py` / `windows-vfx-catalog.json` 按完整文件 SHA256、材质字段和真实片段绑定
识别 14 个冻结资源：四个滤镜、辉光/轻微抖动/模糊、白光快闪、四个命名兼容转场，以及旧 circle 与现代软边
circle 蒙版。尺寸、位置、羽化、本体关键帧、转场时长及源余量的准确契约统一见
[Windows 视觉效果](WINDOWS-VFX.md)。本节保留原生导出相关证据，不扩展到任意同类资源。

资源先通过官方 CLI 写入并解密读回，再以原生预览和导出逐帧确认实际效果。
早期反例中，叠化与雾化的查询、写入、编码都成功，但 GeneralEffect 原包缺少裸运行时所找的
`main.scene`，实际只是延迟硬切。这个反例说明 `encoded-and-decoded` 仅证明编码完整性，
不能单独证明效果生效。现在 `transition/dissolve-compat` 和 `transition/fog-compat` 通过
独立命名、本地冻结的 AmazingFeature 兼容包解决真实渲染：原始 fragment 在官方原生引擎
执行，雾化仍用原始多遍模糊、遮罩序列和曲线。四个离散时长均有两源混合/雾化像素、移位
资源和保存工程恢复再渲染证据；应用原本的 GeneralEffect 路由并未修改。

蒙版另有本机构建兼容边界：

- 项目使用官方 `EncryptUtils`，只对已核对的目标和绑定协调指定字段、旧协议标记及现代
  蒙版资源路径，保留前后密文和审计。正常具有 `Timelines/project.json` 的工程必须直接
  通过声明主时间线读回；少数历史草稿无该声明且根文件与嵌套布局不一致时，仅接纳经目标、
  素材和时序核对的官方结果字段或通道，不能以整份旧根时间线替代声明主时间线。
- 导出助手调用本机构建的 `getVeAdapterConfig`，使用真正的 `std::string` 对象设置
  适配配置 `+0x9b8` 的内建资源根。只在精确 11.4.7 指纹下启用，读取并复制已经审核的
  **48 文件**内建蒙版运行时，再用 `--builtin-resource-root` 显式传入快照路径。
  原生播放器也配置同一已校验资源根，不扫描未知内存或修改官方安装文件。
- 旧 circle 仅接受羽化 0。现代 `mask/circle-soft` 使用未修改的 27 文件官方原包，
  已验收静态软边和 `KFTypeCommonMaskFeather` 动画；两种资源的已审核几何通道控制
  蒙版本体，独立于片段整体位置/缩放。历史草稿中早期未读到动画的现象不能概括为官方
  CLI 普遍不能保存蒙版关键帧。精确参数、曲线和入点限制仍以视觉效果文档为准。

原有蒙版隔离样例完成 4 秒/120 帧完整解码，预览与导出前景重合率约 0.994。
新增几何、羽化与本体动画都有保存读回及原生像素验证。这些证据不代替 GUI 打开、保存和
冷重开验收；16:9 画布中宽高均 0.65 的轴归一化 circle 参数仍会形成椭圆。

预览/导出将媒体、字体、效果包及所需内建运行时复制到独立任务快照，重写本次内存副本路径，
结束后复核源工程和原依赖。动作批次及蒙版 CLI 写入后协调均非原子事务；审计记录完成步骤和
恢复密文，失败后不自动重放或回滚。官方资源解析可能使用网络，不能把 `edit-actions`
称为离线；Windows 预览/导出使用本地快照，但没有额外网络阻断沙箱。
