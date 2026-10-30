# 剪映 11.4.7 正式 GUI 导出的无 Computer Use 入口（只读研究）

本笔记依据本机固定发布物的 Qt 元数据、RTTI、正式 QML 和静态反汇编。研究者未调用任何 native/GUI 方法、未启动导出、未写进程、未改草稿、桥接 ABI、DLL、INI 或资源。以下地址均为 VECreator.dll 首选基址 `0x180000000` 下的静态 VA；RVA 不是当前 PID 的地址。运行时必须重新发现真实对象和所属会话。

源文件为 `D:/刘宇钊/软件/剪映/JianyingPro/11.4.7.14462/VECreator.dll`，本次 SHA-256 `769c33961ef9d7e471e583f03c975be975b0c35e849a767690d09e9f2fc45111`。

## 结论

**存在正式路线：当前编辑窗口标题栏 → 原生导出对话框 → 正式确认按钮 → 正常导出 job。** 打开与启动所需的核心 Qt 方法均使用既有桥支持的 QString 或零参数；不需要构造导出 owner、伪造 DTO、鼠标键盘或截图。不过本研究没有实际调用，不能宣布这条路线已经可运行或解决 latency compensation。

尤其要区分：正式 GUI 导出仍有 **Mojo 独立进程分支**。当前 GUI 进程中 cccreator 的补偿 flag 为 true（主线程提供的被动观测），不证明导出实际执行进程继承该值。应保持原分支和配置，通过真实导出日志、渲染进程及 PCM 对齐验收；不能把“从 GUI 发起”当作补偿已修复。

## 正常打开：标题栏 public invokable

正式主窗口 QML 在 `editor.export` 按钮中调用 `root.viewModel.openExportWindow("click")`，菜单传 `"menu"`，快捷键传 `"shortkey"`。快捷键还要求主窗口可见、没有 VEMask/OOBE 阻挡、非商业模板编辑且模板检查完成。研究路线应读取这些真实状态并保留已有阻挡。

| 项目 | 发布物证据 |
| --- | --- |
| 类型 | `MainWindowStyleTitleBarViewModel` |
| public invokable | `openExportWindow(QString from)`，Qt local method 47 |
| 默认克隆 | `openExportWindow()`，local 48，明确构造 QString `click` |
| Qt static metacall | `0x1855d74b0` |
| 真正实现 | `0x1856735c0` |
| 基类 vtable RVA | `0xd1ecf20` |
| 正常 QML 实例 vtable RVA | `0xd141368`（`QQmlElement<MainWindowStyleTitleBarViewModel>`） |

实现正常读取 QObject parent，经实际 QQuickItem 类型转换；缺 parent 会记录 `get parent_item failed!` 并返回。随后使用标题栏自己的已注入 export module（访问 `this+0xa8` 处的正常依赖包装），缺 module 也正常失败。它调用 module 的真实 vtable 槽 `+0x10`，并传 parent window、from、默认 options。**不要直接调用那个 vtable 或独立构造 module；从公开 invokable 进入，让现成流程建立导出 owner。**

主线程已有标题栏/toolbar 共享 ToolBarModel 的绑定研究：标题栏弱模型在 `+0x170/+0x178`，toolbar 在 `+0xe8/+0xf0`。打开前应与当前编辑 session/主时间线/草稿路径一起验证；不能从进程里随便挑一个同类对象。

证据：`正式标题栏 QML`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/gui-export-qml-98f6861-v34.qml`，未随源码分发）、`Qt metadata`（历史本机证据：`D:/JianyingHeadless/work/live-edit-v01/research/titlebar-meta.json`，未随源码分发）、`打开与确认实现`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/gui-export-titlebar-and-bottom.txt`，未随源码分发）、`现有会话绑定研究`（历史本机证据：`D:/JianyingHeadless/work/live-edit-v01/research/session-undo-save-binding.md`，未随源码分发）。

## 新导出窗口的真实 owner，不混用旧 ExportViewModel

正式模块路径为 `qrc:/Export/business/panel/ExportWindow.qml`。QML 自己声明 `ExportWindowViewModel {}`，正常完成时绑定 contentPage/rightPanelContainer，再加载左右面板和底部页。各新 ViewModel 均通过 `ModelBindFromSharedContext` 绑定已经建立的模型；默认构造后的模型字段为空，不能脱离对话框实例化后直接执行。

| 真类型 | 基类 vtable RVA | 正常 QQmlElement vtable RVA |
| --- | --- | --- |
| ExportWindowViewModel | `0xc450880` | `0xc3685f0` |
| ExportHomeBottomViewModel | `0xc45a798` | `0xc368d60` |
| ExportFileSelectorPanelViewModel | `0xc456530` | `0xc3689e0` |
| ExportVideoOptionsPanelViewModel | `0xc457e48` | `0xc368b30` |
| ExportCompileBottomViewModel | `0xc458cf0` | `0xc368dd0` |
| ExportModelImpl | `0xc44a498` | 不应自行创建 |
| ExportWindowModel | `0xc449fc0` | 不应自行创建 |
| ExportHomeBottomModel | `0xc459840` | 不应自行创建 |

可读绑定证据：

- `ExportWindowViewModel+0x68` 为正常绑定的 ExportWindowModel；`uiStage` 的 getter 从该模型 `+0x178` 读取 int。元数据定义 HOME=0、COMPILING=1、FINISH=2。getter 的空模型分支也返回 0，故不能仅凭 HOME 判定初始化完成。
- `ExportHomeBottomViewModel::modelAttached` 实现 `0x1842fbb10`：把第一项 shared model 保存在 `+0x48/+0x50`，下一项保存在 `+0x58/+0x60`；`compileClick()` 从 `+0x48` 读取自己的正常 HomeBottomModel。所有 control block、RTTI、窗口所有权必须真实且存活。没有直接 native 访问就不能假定具体运行实例已经正确绑定。
- `ExportFileSelectorPanelViewModel+0x60` 为 FileSelectorPanelModel，读 `selectedExportPath` 调其正常 getter，读 title 位于模型 `+0x10`。这些模型可进一步与同一对话框的 QML owner、context 和只读时间线名称核对。
- `ExportModelImpl` 的 RTTI 显示 `export_ns::IExportModel` 与 QObject 均在 offset 0；这是新导出链上的模型，公开只读属性包含 preparing、isTryExporting、veCompiling、progress、inBgExportPending、exportTaskFailed、progressBlocked 等。旧 `ExportViewModel` 也仍在发布物中，但不能把它的 fileParams/videoParams 当作当前新窗口实例的配置入口，除非另有真实绑定证据。

证据：`正式导出窗口 QML`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/gui-export-qml-912b3a7-v34.qml`，未随源码分发）、`模块 qmldir`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/gui-export-qml-9124bf8-v34.qml`，未随源码分发）、`VM RTTI`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/gui-export-rtti-vtables-static.json`，未随源码分发）、`模型/QML RTTI`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/gui-export-model-rtti-static.json`，未随源码分发）、`正常 modelAttached`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/gui-export-model-attachment.txt`，未随源码分发）、`uiStage 读取`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/gui-export-ui-stage-read.txt`，未随源码分发）、`完整模型 Qt 元数据`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/gui-export-model-qt-decoded-static.json`，未随源码分发）。

## 正常确认与权益、任务语义

新 `ExportHomeBottomViewModel.compileClick()` 是 public invokable，local method 21，无参数。static metacall `0x18420bd80`，真正实现 `0x1842fba30`，其内部读取已绑定 HomeBottomModel 后调用 `0x1842f4280`。这不是通过构造一个简化 ExportService DTO 来绕过 UI。

正式 QML 确认按钮 `objectName="export.confirm"`，`Accessible.name="ExportOkBtn"`，定义零参动态 QML 方法 `triggerAutomationAction()`。其顺序为：

1. 调正常 `checkAlgoTask(QJSValue callback)`；若任务未准备好则显示现有任务面板。
2. 通过后正常 forceActiveFocus，调用 VM `compileClick()`。

因此如既有桥能够通过真实 QObject/QQuickItem owner 解析动态 QML 方法，**优先调用真实按钮的 `triggerAutomationAction()`**，先读按钮 enabled 与 ViewModel 状态；它保留这一层 QJS callback，本身不需要桥构造 QJSValue。现桥用 `QMetaObject::invokeMethod`，零参调用在类型协议上可表达，但**动态 QML 对象定位/元方法实际接受尚未运行验证**。

直接调用 VM `compileClick()` 是同一个 QML 中 Return/Enter 快捷键的官方路线，快捷键以 `ok.enabled` 为前提；它不会执行鼠标点击处理里的 checkAlgoTask。不能把两条入口的语义差异藏掉。`checkAlgoTask(QJSValue)` 本身超出现有 typed_args 支持，不伪造 QJSValue 内存。

确认按钮 enabled 原式要求 `!isTryExporting`、至少一项 video/gif/subtitle/audio 被选中，以及企业上传条件满足。QML 还读取 preparing、spaceEnough、VIP info ready/block/trial、版权信息。`compileClick()` 后由正常模型/导出 job 执行权益、导出准备和确认；研究不授权伪造成功信号、强开 disabled 控件、自动购买、忽略素材错误、覆盖已有文件或关闭策略检查。若需要额外确认，应观察并报告真实状态，不重放已经提交的确认动作。

证据：`正式确认按钮与任务检查 QML，650–720 行`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/gui-export-qml-913580e-v34.qml`，未随源码分发）、`完整 VM Qt 元数据`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/gui-export-qt-decoded-static.json`，未随源码分发）、`HomeBottomModel 正常执行链`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/gui-export-compile-start-manager.txt`，未随源码分发）。

## 导出参数：哪些当前桥可做，哪些只是原生 API 存在

`ExportVideoOptionsPanelViewModel` 的现成 public invokable：

| 方法 | 精确签名 |
| --- | --- |
| 分辨率 | `setResolutionIndex(int index)` |
| 格式 | `setFormat(int index)` |
| 编码 | `setEncoderIndex(int index)` |
| 帧率 | `setFrameRate(int index)` |
| 码率档 | `setBitrate(int index)` |
| 自定义码率 | `setCustomBitrate(qlonglong value, bool record)`，另有缺省 record 克隆 |

必须从此实例的 resolutionStringList/formatList/formatEnableList/encoderList/frameRateList/bitrateList 查询实际选项，不猜 index、单位或会员可用性；完整元数据保留了这些 QStringList 属性。现桥的 scalar get 不支持 QStringList，应采用已有只读列表解析或进一步现成接口，不能把它当 JSON 字符串。`qlonglong` 在 typed_args 里为 int64 storage，但 Qt 需精确类型名，当前 override 仅允许 int/pointer；不要把 `int64_t` 名称当作必然可匹配 qlonglong。int 参数的上述方法没有此问题。

FileSelector QML 根 `objectName="export.file_selector"`，正常属性 `automationOutputPath`、`automationOutputTitle` 的 onChanged 赋值真实 `VM.selectedExportPath/title`；不需要系统文件选择器才能在产品结构上设置目录。其合成 `exportFullFileName` 可读取当前完整目标路径。VM 两个 QString 属性确实有 Qt WRITE，另有 `getTimelineName()`、`canShowTimeline()` public invokable。

**但现有 bridge.cpp 没有通用 QObject.setProperty / QMetaProperty.write 操作**，只有 property 读取和 invokeMethod。WRITE 属性不等于现桥能写；QML 的这两个 automation 属性也不是元方法 setter。FileSelectorVM 的 public methods 只有 saveExportPath/openFileDialog/openEnterprisePathSelect/getTimelineName 等，未见 QString 目录/标题 setter invokable。不能调用私有 setter 地址、篡改 metadata，或假装 `setSelectedExportPath()` 可 invoke。旧 `ExportFileViewModel.setExportFilePath(QString,bool,bool)` 存在，但未经新窗口 owner/同一 ExportParams 绑定证明，不推荐借用。

最小真实实验可以在正常窗口里**只读审查并采用现有默认目录、唯一新草稿名及合适参数**，确认目标文件不存在并维持正常 overwrite=false 流程；这不证明任意输出路径已接通。若任务必须指定新路径/标题而又无法使用默认值，则仍缺现桥可调用的正式写属性/现成自动化入口，不能报告完全接通。本研究没有修改 ABI 来补它。

证据：`文件选择面板正式自动化属性和完整路径合成`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/gui-export-qml-9130a8d-v34.qml`，未随源码分发）、`视频参数正式 QML`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/gui-export-qml-912d7e1-v34.qml`，未随源码分发）、`Qt VM 字段/方法`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/gui-export-qt-decoded-static.json`，未随源码分发）、`参数元调用映射`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/gui-export-new-model-property-mapping.txt`，未随源码分发）、`现桥读属性/调用实现`（历史本机证据：`D:/刘宇钊/codex_work/jianying-headless-windows/bridge/live-editor/bridge.cpp`，未随源码分发）、`现桥 typed 参数支持`（历史本机证据：`D:/刘宇钊/codex_work/jianying-headless-windows/bridge/live-editor/typed_call.cpp`，未随源码分发）。

## 观察完成，不能注入完成

正式 `ExportCompileBottomViewModel` 提供 scalar `progress`、`inBgExportPending`、`exportTaskFailed`、`progressBlocked`，QML 显示 `min(progress,1)*100%`；任务挂起/失败时显示零。新 `ExportCompileRightPanelViewModel` 还提供 exportFail/exportPending/preparing/isCloudMaterialDownloading。ExportModelImpl 提供上述总体状态。`ExportWindowModel.uiStage` 的 FINISH=2 可辅助判断，但单独的 100% 或 FINISH 都不替代真实产物验收。

现桥的 get 仅认识 QString、bool 和 typeName 含 double/float/int/long 的标量；命名 enum `ExportWindowModel::ExportUIStage` 未必可以经过该分支。需要时只能由已验证绑定的 WindowVM+0x68 → WindowModel+0x178 做**只读** int 观察，而非改桥类型识别或写状态。该模型 getter `0x1819c1420` 的静态指令明确为 `mov ebx,dword ptr [rbx+0x178]`，见`精确 getter 证据`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/gui-export-ui-stage-getter-leaf.txt`，未随源码分发）。正常 Qt completion signals / `onJobFinished(QSharedPointer<...>)` 是观察来源，不是启动导出或强行完成的入口。

实际完成标准应结合：真实 job 完成/无失败、输出路径存在且稳定、ffprobe/完整解码得到目标音视频、源草稿不变、音频相对同源参考的 PCM 延迟/首尾帧；本任务未做这些实验。

证据：`正式进度 QML`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/gui-export-qml-9137713-v34.qml`，未随源码分发）、`服务与状态 Qt 元数据`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/gui-export-service-qt-decoded-static.json`，未随源码分发）、`ExportModelImpl 元数据`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/gui-export-model-qt-decoded-static.json`，未随源码分发）。

## 关键限制：GUI 发起也可能走独立 ExportServiceMojo

`export_ns::StageCompile::exportServicePrepare` 实现 `0x1844315b0` 从真实 job config 获取布尔值（getter `0x18437be80`）及 mode（`0x18437de40`）。布尔为 true 时，正常构造 `ExportServiceMojo`（constructor `0x184459680`）。随后记录权威日志：

```
[EXPORT-JOB] Compile with mojo : %d, mode : %d.
```

`ExportServiceMojo` vtable RVA `0xc4706d8`；`ExportServiceLocal` vtable RVA `0xc477848`；均实际存在。公开 Qt metadata 的 ExportServiceProxy 只有 onProgress/onFinished/onInformation/onBlocked/onDisconnected signals，未发现一个可用 QString/标量 DTO 直接启动完整本地导出的 public invokable；不能把 signal 当命令。

所以最合理的下一实验是保持原有 flags/策略，从正式标题栏与真实确认按钮进入，完整记录上面的实际日志分支、当前真实参数、导出执行进程和音频对齐。若依旧选择 Mojo，不能宣称 GUI 的 flag 已修复 helper 音频问题，也不应为过测试把分支强设 local。这里只交付入口和证据，不承诺其选用哪种运行时。

证据：`服务构造与 StageCompile 静态链`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/gui-export-service-construction.txt`，未随源码分发）、`构造引用`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/gui-export-service-construction-calls.json`，未随源码分发）、`服务 RTTI`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/gui-export-model-rtti-static.json`，未随源码分发）、`ExportServiceProxy signals`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/gui-export-service-qt-decoded-static.json`，未随源码分发）。

## 本次没有完成的验证

- 未枚举 PID 26548 的任何真实导出对象；未确认当前存在导出窗。
- 未验证当前 bridge 对真实 QML 动态 `triggerAutomationAction()` 的解析、对象定位和接受情况。
- 未通过当前桥设置输出目录或标题；不能用 Qt WRITE 说明替代该验证。
- 未发起任何导出，没有新 MP4 或音频补偿结果；没有修改任何策略开关。

以上缺项是后续实验范围，不能被入口静态分析或既有离线导出结果替代。
