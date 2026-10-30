# 完整亮度/RGB曲线点API：官方上层提交与当前GUI宿主边界

> 2026-10-28 后续状态：以下最初结论保留为阶段性研究记录。主线程现已通过真实个人预设 item 的普通 `importClicked()` 成功生成包含完整四通道几何的独立调节轨；它不是修改原视频片段。新增调节片段的原生 Inspector 绑定、默认算法节点及尚待验收的重置/历史链见第12节。不可将最初“未找到宿主”的状态误读为最新验证结果，也不可把这次预设应用称为任意锚点的直接 setter。

日期：2026-10-28；目标构建：剪映 `11.4.7.14462`。本轮只读官方发布的 CLI、JS SDK、Qt元数据和本机PE，不调用任何native接口、不执行CLI、不读写进程、不操作GUI、不修改engine/bridge/ABI/DLL/草稿。没有将重置、按x插点或发通知信号替代完整点编辑。

## 结论

**已找到完整四通道锚点和控制柄的官方参数API，但尚未找到满足当前限制、已闭合到当前GUI会话和原生undo的调用入口。**

官方JS SDK的 `colorCurvesParams` 支持 `luma/red/green/blue` 四个数组，每点有 `anchor/leftControl/rightControl`。它的 picture-adjust action 会构造 `segmentDelta`，不是只有一个预设名称。原生 `videoeditor.dll` 也导出相应参数JSON解析器和 `VideoClient::setPictureAdjust`。因此不能说剪映没有完整曲线数据API。

但JS SDK中查到的 `editor.commit` 属于它自己的renderer/sequence实例，另有JS history；没有查到它与当前Qt编辑页 `IDraftService`、当前draft/session或原生undo栈的绑定证据。原生导出的参数与request又是C++对象/`shared_ptr`，不是现桥可封送的QObject或QString槽。不能仅因为方法叫commit或数据能序列化，就宣布当前GUI已经能完整改点。

另找到真实 `CommandController.runCommand(QString cmd)` 接收 `tool_calls` JSON，可由现有typed桥封送。但是它把JSON交agent/clipflow工具执行器，并不直接调用JS SDK的picture-adjust API；尚缺完整曲线的tool schema和当前owner绑定，不能发送猜测payload来试。

证据均保存在：`D:\JianyingHeadless\integrations\native-curve-full-point-api-20261028`。

## 1. 官方JS完整数据契约

安装发布物：`Resources/canvas_agent/app/static/js`。关键文件和原始字节位置来自`发生位置与SHA`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/curve-js-occurrences.json`，未随源码分发），不是网上不同版本示例。

| 层 | 已确认接口 / 行为 | 证据 |
|---|---|---|
| 点参数工厂 | `createColorCurvesPointParamFromPlain`，内部函数e7；处理anchor、leftControl、rightControl，每个是{x,y} | `ai-creation~4.b708b52d.js`，char≈141933 |
| 曲线参数工厂 | `createMaterialColorCurvesParamFromPlain`，内部函数te；处理panel/resourceId/path和四通道数组 | 同文件，char≈142221 |
| snake_case适配 | `color_curves_params` → `colorCurvesParams`，`left_control/right_control` → camelCase坐标 | 同文件，char≈96799 |
| 完整picture-adjust action | module44437中MetaTypeColorCurves分支 → `updateColorCurvesParam(segment,material)`；生成colorCurves delta，再以track/segment ID和source delta构造mutation | `ai-creation~13.7a331c10.js`，char≈160559/164859 |
| render API包装 | module62123中 `.pictureAdjust.update(...)` 被包在 `.editor.commit(callback)` 中 | `ai-creation~10.f1164957.js`，char≈86560..86935 |

可复查：`精确参数片段`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/curve-sdk-full-param-contract.json`，未随源码分发）、`完整action模块44437`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/ai-creation~13.7a331c10-module-44437.js`，未随源码分发）、`包装模块62123`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/ai-creation~10.f1164957-module-62123.js`，未随源码分发）。这些文件只是保存的源片段，本轮没有执行JS。

该层的数据形状示意如下，**不是已确认可发给CommandController或当前GUI的请求包**：

```json
{
  "type": 57,
  "colorCurvesParams": {
    "panel": "<保留当前材料真实panel>",
    "resourceId": "<保留当前材料真实resourceId>",
    "path": "<保留当前材料真实资源路径>",
    "luma": [
      {"anchor":{"x":0,"y":0},"leftControl":{"x":0,"y":0},"rightControl":{"x":0.2,"y":0.12}},
      {"anchor":{"x":1,"y":1},"leftControl":{"x":0.8,"y":0.9},"rightControl":{"x":1,"y":1}}
    ],
    "red": [], "green": [], "blue": []
  }
}
```

同SDK `MetaTypeColorCurves` 数值枚举为57，持久化类型字符串为 `color_curves`。空数组如何处理应遵守具体调用语义，不能把示意空数组用于正式提交以意外清空其他通道。正式单通道修改应带回其他三个通道原值，材料标识和资源路径保留。

**额外差异：**上述`ColorCurvesPointParam`工厂没有 `syncDirectionControl` / `sync_direction_control`字段；持久化ColorCurvesPoint另有该字段。即使闭合此API，也要单独核验控制柄联动标记会保留、重算还是被默认化；不能因(x,y)完整就承诺与全部持久化字段无损往返。

## 2. editor.commit并非当前Qt会话的证明

`宿主源码片段`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/sdk-editor-instance-ownership.json`，未随源码分发）与`完整renderer模块80426`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/ai-creation~11.fe7840fa-module-80426.js`，未随源码分发）显示：

- 该render class构造参数有`wasm/config`，创建`new wasm.VESDKBind`，维护自己的`_editor/_editorSequence/_clipMap/_trackMap`；另一实现创建`new Sequence(uuid)`。
- module24053 的 `.editor.commit` 只是转发 `_render.editor.commit(callback)`。
- renderer commit 在最外层对自己的sequence调用begin/commit，再updateSetting/prepare；这是渲染事务，不是原生GUI保存的同义词。
- JS bundle同时含独立undoStack/redoStack与command执行层。它们存在不证明原生 `lyra::shell::IDraftService.sigDraftRedoUndoStatusChanged` 会变化。

没有在这一提交链看到当前Qt draft/session令牌核验、对现有main timeline的owner绑定或对原生历史服务的实际通知。**本结论不是说它必然只写磁盘，而是证据不足以把独立SDK/renderer事务当成当前GUI事务。**用它新建editor、修改副本、保存并重开当前草稿，不满足本轮实时编辑要求。

## 3. 原生SDK确有完整参数，但不是QObject接口

静态读取`videoeditor.dll` export table得到：`完整导出证据`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/native-full-curve-param-exports.json`，未随源码分发）。该构建SHA256为 `fa89997a94e96cf97c8ee436a56ab028ea5f87731214696ba43ff74c0fdc0fa0`。

| 导出RVA | 导出语义 |
|---|---|
| `0xdd640` | `lvve::from_json(const std::string&, ColorCurvesPointParam&)` |
| `0xe1870` | `lvve::from_json(const std::string&, MaterialColorCurvesParam&)` |
| `0x181de80` | `VideoClient::setPictureAdjust(std::shared_ptr<lyra::SetPictureAdjustReqStruct>, long)`，返回shared_ptr响应 |
| `0x174d6c0` | `PatchClient::applyPatch(shared_ptr<ApplyPatchReqStruct>, callback, bool, long)` |
| `0x146bfd0` | `lvve::HandleLVOPMethodCall(int64, const std::string&, const nlohmann::json&, callback...)`，通用native方法路由 |

这些符号证明原生有JSON→完整参数和正常请求层，但参数是MSVC `std::string`、nlohmann对象、C++引用、shared_ptr和回调。`ColorCurvesPointParam/MaterialColorCurvesParam/SetPictureAdjustReqStruct`不是Qt QObject。不能把它们假装成`QQuickItem*`传现有typed桥，也不能把正确RVA当成已确认调用ABI并直接跳转。本轮没有构造、调用或猜这些对象布局。

`setPictureAdjust`这一层的正确session/thread、record/command组合和当前GUI数据刷新还需正式契约；不能从名字推定自动记录UI undo。已有GUI曲线handler走原生请求链，可作为后续安全绑定的语义参照，但不因此产生一个现成QString invokable。

## 4. 新发现的真实Qt JSON入口

### CommandController

| 项目 | 精确证据 |
|---|---|
| 类及继承 | CommandController → QObject；vtable RVA`0xc31a748` |
| meta / metacall | `0xc2de940` / `0x3ac62e0` |
| 普通Qt槽 | `void runCommand(QString cmd)`，local method index3，flags2 |
| 实现 | metacall `0x3ac631d` → `0x3db74b0` |
| 结果signals | `jsonReady(QString)`、`runOk(QString)`、`runError(int,QString)` |
| 官方UI使用 | 发布QML标注输入为`tool_calls json`，按钮调用`controller.runCommand(input.text)` |

证据：`完整元数据`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/upper-api-qt-decoded-static.json`，未随源码分发）、`RTTI`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/command-controller-tool-rtti.json`，未随源码分发）、`dispatch`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/command-controller-metacall-static.txt`，未随源码分发）、`runCommand`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/command-controller-runCommand-static.txt`，未随源码分发）、`官方QML`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/adjust-qml-8eab9b8.qml`，未随源码分发）。

`runCommand`取得scene1的工具executor，把QString转UTF8，并带执行回调进入`agent::ToolExecutor`。该wrapper再交clipflow工具执行层；`clipflow_sdk.dll`的确有`ClipflowAgentToolsExecutor::processToolCallsJson`，没有证据表明这里会把任意JS SDK函数名直接执行。该槽**不是**`eval`、`setPictureAdjust(QString)`或原生SDKrequest的任意JSON透传。

现桥`typed_args.py`支持QString，单值UTF8最多4096字节；所以该签名本身可封送，完整payload也须满足现有上限。但调用前还缺两条硬证据：

1. **数据契约**：哪个真实tool name及参数schema接收完整colorCurvesParams？本轮未找到；不能把JS API数据形状直接塞进tool_calls。
2. **当前owner**：该controller是否已存在于当前会话，由哪个实际AgentToolsTestPanel/场景owner持有，scene1 executor是否对应目标当前draft？本轮不读进程、不创建面板，因此没有声明它已绑定。应只读验证实际QObject/private backlink、parent/scene、目标draft后再决定；不能临时new对象后冒充当前模型。

### JsonTemplateBuilderController和JSB

`JsonTemplateBuilderController.importCacheJson(QString)`、`runBuiltCommand()`也是真实普通Qt槽，但前者导入的是测试工具模板/缓存，不是当前曲线材料；不能把它的cache导入当作曲线更新成功。

`jsb::WebViewJsbWrapper.request(QVariantMap)`、`BaseJSBViewModel.request(QVariantMap)`及`InfiniteCanvasNativeBridgeController.handleJsCallback(QString,jsb::InvokeProtocolData)`可作后续原生Web路由研究线索；当前桥没有QVariantMap/InvokeProtocolData封送，不属于本轮可直接调用入口。更未确认其中哪个method映射完整曲线并保持当前native undo。

为减少仅按类名查找的遗漏，本轮一次性识别了本DLL中4072条符合已校验Qt6静态布局的metaobject，并筛选普通JSON/command/dispatch/preset候选；`候选表`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/all-json-dispatch-candidates.json`，未随源码分发）。这是静态生成元数据范围，不承诺涵盖运行时生成的动态metaobject。没有发现另一条已绑定的QString完整曲线提交槽。

## 5. 官方CLI与现有DraftEditing路由

本轮读取了本项目的 [draftediting_worker.mjs](../../engine/draftediting_worker.mjs) / [draftediting_runtime.py](../../engine/draftediting_runtime.py) 以及同版本官方`app-server.mjs`。现有worker通过官方sandbox bridge启动lyra-cli，显式指定cwd/read-only/read-write路径。它没有把当前 `LiveEditor` 的真实QObject或Qt session/token传给一个JS editor对象，不能自然推导两者共用历史。

本机CLI普通picture_adjust字段表含白平衡、亮度等基本项和HSL；未见完整curve point参数。二进制中CLI对应client不含`color_curves_params`/`colorCurvesParams`/相应参数类，而videoeditor.dll含这些字段/类型。`出现位置对照`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/curve-native-schema-occurrences.json`，未随源码分发）。字段字符串缺失只是静态线索，不能单独证明所有扩展语法绝不支持。

CLI有Blueprint Node Patch、ApplyPatch与selection mutation等正常路径；`帮助/错误字符串`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/cli-patch-help-static.json`，未随源码分发）显示它们有明确op/field白名单及external_sid上下文。尚未定位一条已发布的“完整curve JSON →当前已打开GUI的同一session →原生undo”的契约；也未将覆盖target_draft.xml、apply离线副本或重新打开当作闭合证据。

## 6. 什么证据齐全后才值得主线程实现/实际验收

当前最有价值的新线索是CommandController普通QString入口，而不是再次扫描curve VM。推进需要先补全工具注册/输入映射的静态契约，以及当前controller/executor的真实owner。若工具不暴露完整曲线，不能用这个入口执行一个只支持基本调色的操作来掩盖缺口。

如果后续找到原生正式JSON调用器，应先在独立草稿做一次**真正改变中间锚点和控制柄**的四通道提交：同draft/session、当前模型数据与保存材料吻合、原生undo/redo完整恢复、保存并导出产生预期像素差异，其他轨道/曲线变速/字幕/音轨及资源保持原状。`sync_direction_control`也要分别回读。不要用reset/enable/新增等值点充数。

本轮最终分级：**完整数据契约已找到；当前GUI可调用的完整点提交入口与原生历史闭环尚未找到。**未修改或试运行任何候选入口。

## 7. 补充审计：原生个人调色预设路径

后续窄范围静态检查发现了一条值得保留的正常产品路径，但截至本轮能力审计，**仍不能把它列为已支持的完整曲线实时编辑**。本节只记录已找到的发布物证据；没有调用候选槽，没有注册或应用自有预设，没有修改当前草稿、engine、bridge或ABI。

### 7.1 预设材料确实包含完整四通道曲线

同版本`videoeditor.dll`导出的`lvve::AdjustPreset::RegisterParams`（RVA`0xfa71d0`）注册了`color_curves`，并与`hsl`、`hsl_curves`、基础`adjust`、色轮、`filter`等其他调色部分并列。`lvve::preset::ColorCurvesInfo::RegisterParams`（RVA`0xfa8460`）含`enable`和`luma/red/green/blue`四通道；`ColorCurvesPointInfo::RegisterParams`（RVA`0xfa88d0`）含`anchor`、`left_control`、`right_control`。

证据：`导出表`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/adjust-preset-videoeditor-exports.json`，未随源码分发）、`AdjustPreset字段注册`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-videoeditor-0xfa71d0.txt`，未随源码分发）、`四通道注册`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-videoeditor-0xfa8460.txt`，未随源码分发）、`完整点字段注册`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-videoeditor-0xfa88d0.txt`，未随源码分发）。

`lvve::CreatePresetAdjust(const std::string&, AdjustPreset&)`（RVA`0xfa6330`）使用JSON解析器；这里的字符串是JSON文本，不能仅凭函数名宣称其为文件导入接口。尚未完整确认个人预设中点坐标的序列化形状、版本约束、所有必需字段，以及与草稿`color_curves_params`中`sync_direction_control`的往返关系。因此本报告不提供猜测的“可直接导入”预设JSON，也不把JS SDK的camelCase结构当成该预设文件格式。

### 7.2 官方预设索引与真实列表项存在

`VECreator.dll`的`AdjustPresetSaveManager`有正常本地存储路径与索引：字符串`/Lut/AdjustPreset/`、`/adjustPreset.webp`和`AdjustPresetCfg.json`。静态函数RVA`0x4fe11d0`构造索引/预设文件路径、读取文件并进入原生解析/注册链；`0x4fe5280`遍历管理器持有的预设集合并写JSON索引。没有证明“在目录放一个任意JSON文件”就会被当前面板自动发现，也没有执行这种写入。

证据：`预设字符串与原生符号`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/adjust-preset-native-strings.json`，未随源码分发）、`读取链`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/adjust-preset-static-0x4fe11d0.txt`，未随源码分发）、`索引写入链`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/adjust-preset-static-0x4fe5280.txt`，未随源码分发）。

真实发布Qt类包括：

| 类 | 可证实的普通入口/绑定 | 当前边界 |
|---|---|---|
| `PersonalAdjustPresetPanelViewModel` | `aboutToShow()`、`getCollectionControl()`；vtable RVA`0xb474938` | 有官方面板与集合初始化；未核验当前会话真实对象 |
| `PersonalAdjustPresetPanelDataProvider` | `onPresetListChanged()`；vtable RVA`0xb4746b8` | 有官方预设集合更新路径；不是任意JSON提交槽 |
| `PersonalAdjustPresetItemViewModel` | `importClicked()`、`itemClicked(int,int)`；vtable RVA`0xb4744c0` | 有真实列表项普通应用入口；尚未证明自有完整曲线可经它应用 |
| `AdjustPresetSaveManager` | `presetListChanged`、`saveToLocalFinished`等通知；vtable RVA`0xcb0a750` | 未找到一个已核验且可直接调用的`loadFile(QString)`普通槽 |

`getCollectionControl()`实现RVA`0x2d0a5a0`使用面板真实持有的QPointer，缓存头/指针位于`+0x18/+0x20`，必要时由原生创建collection及data provider。`importClicked()`的Qt metacall进入RVA`0x2d04260`，再到`0x2d042d0`；后者从真实item model构造数据并调用其owner链。它不是直接任意坐标setter，也不是允许传入伪造item的契约。

证据：`Qt方法和属性`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-api-qt-decoded-static.json`，未随源码分发）、`RTTI/vtable`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-api-rtti-vtables.json`，未随源码分发）、`真实集合getter`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-api-0x2d0a5a0.txt`，未随源码分发）、`应用槽dispatch`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/PersonalAdjustPresetItemViewModel-metacall-static.txt`，未随源码分发）、`应用函数`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-api-0x2d042d0.txt`，未随源码分发）。

### 7.3 面向本轮能力清单的结论

| 能力 | 审计结论 |
|---|---|
| 表达四通道锚点和左右控制柄 | **存在真实SDK/原生预设数据契约**，不能因此宣称当前GUI已支持 |
| 当前编辑页任意完整曲线点提交 | **尚未打通**；现有Qt曲线VM没有已确认的完整setter，其他路由尚未闭环 |
| 自有完整调色预设经真实列表项应用 | **有较强静态线索，未实际验证**；完整文件规范、正常注册、owner/selection、native undo/save与出片均未闭环 |
| `CommandController.runCommand(QString)`提交完整曲线 | **尚未打通**；普通QString入口真实存在，但实际tool name/schema、当前draft owner及完整曲线映射未证实 |
| 独立JS editor或离线草稿包含完整曲线 | 不能替代“当前剪映GUI实时可编辑”的验收；不得用覆盖文件后重开计作原生同步 |

后续若恢复实现，预设路线可以优先补齐：自有预设完整格式与正常注册 → 当前真实collection/item → 正常应用 → 当前draft/session参数回读 → 原生undo/redo → 保存与像素差异。不应通过构造假model、直接改缓存、调用未知C++ABI或覆盖当前草稿来补齐证据。本轮按照主线程最新要求停在只读能力审计，没有继续新的GUI接入或实验。

## 8. 续行：个人预设精确结构与正常加载链（只读）

本节在主线程恢复完整目标后补充。允许的运行时操作仅为Windows只读模块枚举与`ReadProcessMemory`；未连接GUI/pipe、未调用任何剪映方法、未创建面板或修改资源、进程、草稿、engine和ABI。读取前将PID`26164`的birth与`C:/JianyingAVQA/work/readonly-native-process-v15.json`核对，均为`134375592292885847`。这些地址只适用于本文指纹固定的11.4.7.14462构建和这个进程代际。

### 8.1 当前个人预设根目录及索引格式

原生全局QString位于`VECreator.dll + 0xe85efc0`，只读得到：

```text
C:\Users\Administrator\AppData\Local\JianyingPro\User Data\Presets/Adjust/
```

该目录当前存在但为空。此前字符串`/Lut/AdjustPreset/`用于构造`VEConfig::path::getResourcePath()`下的另一处加载目录，不能把它直接当成当前用户个人预设目录。

索引writer`0x4fe5280`明确写顶层QJsonArray，每个元素为对象，key精确为`name`，value来自item持有的`AdjustPreset.name`：

```json
[
  {"name": "自有预设名称"}
]
```

文件名是`AdjustPresetCfg.json`。该索引没有携带完整曲线；**本轮没有找到“更新索引便触发当前管理器重读”的契约**。正常目录扫描反而显式排除此文件，不能把索引写入当成注册完成或将它假定为扫描的唯一清单。

证据：`运行时只读调用槽与根目录`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-iat-readonly.json`，未随源码分发）、`原生索引writer`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/adjust-preset-static-0x4fe5280-annotated.txt`，未随源码分发）、`路径初始化`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-format-0x4fd8200.txt`，未随源码分发）。

### 8.2 预设JSON中完整曲线的精确结构

结构层级已从原生`RegisterParams`与构造/转换函数交叉确认：

```text
AdjustPreset
  name: string
  version: int
  image_path: string
  color_curves:
    enable: bool
    luma: ColorCurvesPointInfo[]
    red: ColorCurvesPointInfo[]
    green: ColorCurvesPointInfo[]
    blue: ColorCurvesPointInfo[]

ColorCurvesPointInfo
  anchor:        { x: double, y: double }
  left_control:  { x: double, y: double }
  right_control: { x: double, y: double }
```

准确拼写使用snake_case，`enable`不是`enabled`；坐标不是`[x,y]`数组。`ColorPointInfo::RegisterParams`在RVA`0xfa9290`把`x/y`注册到native对象`+0x28/+0x30`的double；`ColorCurvesPointInfo`的三个ColorPointInfo分别位于`+0x28/+0x60/+0x98`，步长`0xd0`。四通道容器位于ColorCurvesInfo `+0x30/+0x48/+0x60/+0x78`。

`AdjustPreset`还注册了`hsl`、`hsl_curves`、`primary_color_wheels`、`log_color_wheels`、`adjust`、`filter`、`smart_color_adjust`、`color_correct`、`color_match`、`extra_info`。若目标只是改变曲线，后续应基于正式导出的完整自有grade保留这些部分；本轮没有创建一个省略其他grade的“完整预设”冒充其等价物。

`version`是32位整数字段（AdjustPreset `+0x68`），默认构造函数RVA`0xfa2c60`初始化为0。**默认值0不等于已验证的本版本导入/输出版本号**；当前个人目录与真实manager都无样例，未捕获一次正常保存的preset，不能编造一个已通过加载的版本或声称所有整数版本都兼容。

在这套preset point DTO中未找到`sync_direction_control`字段注册；其往返保留性仍未证明。`anchor/left_control/right_control`的显式形状可完整表达四通道Bezier几何，但不得顺带承诺额外的GUI控制柄联动状态。

证据：`顶层字段`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-videoeditor-0xfa71d0.txt`，未随源码分发）、`ColorPointInfo x/y注册`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-schema-0xfa9290.txt`，未随源码分发）、`point构造与真实字段偏移`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-schema-0xfa3480.txt`，未随源码分发）、`version默认值`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-schema-0xfa2c60.txt`，未随源码分发）。这些偏移只用于只读解释，不是新增C++ABI调用方案。

### 8.3 完整控制柄的正常渲染转换；绝对坐标范围仍需实测

续查caller已确认：RVA`0x4fd7240`是**保存预设时的封面离屏渲染任务**，不能把它仅按内部set调用命名为当前GUI的preset apply。它复制ColorCurvesInfo，检查`enable`且至少一条通道非空后，调用`0x4fd8b00`构造曲线请求，再交现有渲染服务方法（该处vtable `+0xe0`）。`0x4fd8b00`对四通道分别调用`0x4fd8fe0`。后者把点转换成一维double数组：

- 首点：`anchor.x/y`，再`right_control.x/y`；
- 中间点：`left_control.x/y`、`anchor.x/y`、`right_control.x/y`；
- 末点：`left_control.x/y`、`anchor.x/y`。

对至少2个点的通道，输出长度为`6*N - 4`个double。首点左控制柄和末点右控制柄不会参与这条实际Bezier请求；不能用它们单独改变作为“曲线生效”证明。

这个转换只逐double复制，**没有乘除255、像素尺寸换算、归一化或范围夹取**。可以确认preset坐标沿用该原生曲线请求的单位；仅凭这段转换还不能把UI的0–255显示值、SDK的归一化坐标或超界控制柄直接视为等价。合法绝对范围、插值端点约束、超界控制柄与UI回读应通过正式保存/应用fixture对照确认，当前不提供未经验证的范围常量。

证据：`完整曲线的封面渲染分支`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-caller-0x4fd7240-annotated.txt`，未随源码分发）、`四通道请求构造`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-curve-to-request-0x4fd8b00.txt`，未随源码分发）、`精确控制柄展开`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-curve-to-request-0x4fd8fe0.txt`，未随源码分发）。这证明预设完整几何进入正常原生渲染转换，**没有证明当前GUI apply、undo/redo和保存已通过**；第10节给出caller闭环。

### 8.4 文件到genuine collection/item的原生路径

已定位正常个人加载链：

```text
AdjustPresetSaveManager singleton
  getter 0x4fdfe00 -> 静态真实对象 VECreator+0xef3aec0
  ctor 0x4fd47c0
    -> init user root 0x4fd8200
    -> scan(root, source=1) 0x4fe1b60
       -> QDir::entryInfoList("*.json", filters=0x12, sort=1)
       -> load(QFileInfo,...,source=1) 0x4fe11d0
          -> 排除 AdjustPresetCfg.json
          -> QFile::readAll / QByteArray::toStdString
          -> helper 0x4fdd290
          -> videoeditor!lvve::CreatePresetAdjust(JSON text, AdjustPreset&)
          -> genuine AdjustPresetItem ctor 0x4fd46d0
          -> 正常去重检查 0x4fdb330
          -> manager+0x18 的 shared_ptr item vector
```

`0x4fe11d0`同时接受`json/zip`后缀；`0x4fe6a00`检查的精确后缀是`zip`（不是json），处理解包资源。普通JSON直接读取后进入parser。加载source1的外部路径时，原生还可能正常保存到个人根并移除原来的临时输入，因此不能把这个非Qt内部函数作为无副作用只读接口；本轮只做静态研究。

集合侧：`PersonalAdjustPresetPanelViewModel.aboutToShow()`→真实collection中的provider→`0x2d095a0/0x2d097f0`→manager的`0x4fe3040(source=1, team="")`→真实item列表。此处是从内存manager取列表，没有重新遍历文件目录。provider订阅了manager的真实变更通知，但手工发signal不会产生已加载的preset材料，不能当成注册。

对PID26164已只读验证singleton vtable=`VECreator+0xcb0a750`，manager列表当前0项，待保存的grade上下文`+0x40`也是null。没有现成真实item可供本轮读取版本和坐标样例。证据：`只读manager快照`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-manager-readonly-snapshot.json`，未随源码分发）、`待保存上下文快照`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-manager-context-readonly.json`，未随源码分发）。

唯一已发现的直接load-file wrapper`0x4fe0ef0`的正常caller是旧资源项链`0x299e1f0`，以source3调用；不是个人source1入口，不能把其资源下载回调当成任意个人导入。已补查现成Import/Material/CommonEffect等相关Qt元数据，没有找到一个可用现桥调用的个人`loadPreset(QString path)`或`reloadFromDisk()`槽。**“正常启动时会加载自有文件”与“当前会话能即时正式注册新文件”是不同能力；后者尚缺可调用上层入口。**

证据：`singleton/ctor`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-follow-0x4fdfe00.txt`，未随源码分发）、`ctor扫描`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/adjust-preset-static-0x4fd47c0-annotated.txt`，未随源码分发）、`正常文件扫描`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-caller-0x4fe1b60-annotated.txt`，未随源码分发）、`文件解析与真实注册`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-caller-0x4fe11d0-annotated.txt`，未随源码分发）、`正常caller关系`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-loader-normal-callers.json`，未随源码分发）、`补充相关Qt元数据`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-loader-extra-qt-decoded-static.json`，未随源码分发）、`个人面板官方QML`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-qml-873d7ce.qml`，未随源码分发）。

### 8.5 最短补证路径与当前未确定项

现成普通槽`AdjustPresetSaveViewModel.save(QString name)`已确认：meta RVA`0xcae5b10`、metacall `0x4e7bec0`、local index5→实现`0x512ce80`→genuine manager→`0x4fe4bd0`。官方QML确实在确认按钮调用它。**续查修正：当前`AdjustSettingHandleViewModel.save()`直接采集并自动命名保存，不会先创建这个保存对话框；见第9节。**因此制作正式样例无需寻找或构造saveVM；不能new一个假saveVM或直接改manager上下文来模拟正常保存。

主线程若已有该正常绑定，可先从独立测试工程正式保存一次完整自有preset，读取实际文件作为基底，核对版本、四通道单位及其他grade字段。研究侧本轮没有执行这个mutation。待补项仍为：当前会话的正式自有文件注册入口、完整preset输出样例、坐标合法范围、sync状态往返，以及应用后的当前模型/原生undo/redo/保存/出片闭环。

证据：`save槽dispatch`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/AdjustPresetSaveViewModel-metacall-static.txt`，未随源码分发）、`save实现`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-caller-0x512ce80.txt`，未随源码分发）、`manager保存前提`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-save-name-0x4fe4bd0.txt`，未随源码分发）、`官方保存对话QML`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-qml-8e64c2d.qml`，未随源码分发）。

## 9. 正式样例的真实保存绑定，以及正常重启注册的边界

本节仍只读，不调用保存、打开窗口、注册资源、关闭或重启剪映。它修正第8节对saveVM初始化顺序的推断，并给主线程一个比寻找对话框更短的现成入口。

### 9.1 当前调色面板本身有完整的普通保存槽

| 项目 | 固定版本证据 |
|---|---|
| 类 | `AdjustSettingHandleViewModel`，使用现有live color已经绑定的真实当前handle |
| meta / metacall RVA | `0xbf40960` / `0x30f9390` |
| 普通方法 | `void save()`，local method index55，flags2 |
| dispatch | jump table `0x30fb93c[55]`→`0x30f996d`→实现`0x37a7000` |
| 选中数据 | handle `+0x1b8/+0x1c0`的真实SegmentHolder vector；取首个实际选中片段 |
| 采集 | SegmentHolder→真实Segment shared_ptr→`AdjustPresetSaveManager`→`0x4fe0bf0` |
| 保存 | `manager.save(empty QString)`→`0x4fe4bd0`，由原生生成默认名称，直接进入保存链 |

`save()`先依据handle当前选择/模式做检查，存在提示后定时重试的原生分支，所以一次Qt调用返回不等于落盘完成。应先核验正确独立QA工程和单一选中目标，保持其他mutation停止，调用后核对真实结果；本轮没有触发该分支或方法。

`0x4fe0bf0`在选中segment非空时创建真实AdjustPreset，将其保存在manager `+0x40/+0x48` shared_ptr，使用SegmentHolder进入采集器`0x6a19080`，然后**RVA`0x4fe0d28`明确设置`preparedPreset+0x68 = 3`**。因此本版本正常采集保存的version是3；第8节所述默认构造值0只是未采集时默认值，不能作为正式输出版本。

这条路径读取真实选中片段；不是reset、不是只读GUI显示值、不是改缓存，也不需要先打开`AdjustPresetSaveViewModel`。它能为后续全grade保留提供原生输出基底，但本轮未做实际保存，仍需主线程核对完整输出。

证据：`handle完整Qt元数据`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-loader-extra-qt-decoded-static.json`，未随源码分发）、`handle dispatch`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/AdjustSettingHandleViewModel-metacall-save-static.txt`，未随源码分发）、`自动保存实现`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-handle-action-0x37a7000.txt`，未随源码分发）、`采集与version3`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-save-prepare-0x4fe0bf0.txt`，未随源码分发）。

### 9.2 返回值、完成通知与文件名映射

普通Qt `save()`和保存对话框的`save(QString)`均为void。内部manager `0x4fe4bd0`返回int：

- 0：已进入正常保存安排；在调用`0x4fdd450`后设置为0，不代表异步文件写入必然完成；
- 1：没有prepared grade等不满足保存前提的分支；
- 2：空名自动编号分支超过原生99检查的分支。

非空名称经原生保存入口写入`AdjustPreset.name`，新建source1的genuine item并放入manager列表；封面/保存callback继续执行。文件writer `0x4fe5610`精确构造：

```text
个人preset根目录 / (真实 item.name + ".json")
```

完成callback `0x4fd5a70`依次执行真实JSON writer `0x4fe5610`、索引writer `0x4fe5280`，再调用`presetListChanged(source, team_id)`（signal实现RVA`0x4e94080`）。因此后续验收至少应核对：唯一新增文件可完整解析、其`name/version/color_curves`与目标一致、真实manager/item已更新、该文件内容稳定。不能因为manager先插入item、toast出现或void方法返回就记录“保存通过”。封面路径应取正式输出`image_path`，不猜测它必为某个固定PNG/JPEG文件。

证据：`内部manager保存与结果`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-save-name-0x4fe4bd0.txt`，未随源码分发）、`实际文件映射`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-caller-0x4fe5610-annotated.txt`，未随源码分发）、`写文件后通知`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/adjust-preset-static-0x4fd5a70.txt`，未随源码分发）、`封面与后续安排`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-save-prepare-0x4fdd450.txt`，未随源码分发）。

### 9.3 保存对话框的真实对象边界

`AdjustPresetSaveViewModel`本体vtable RVA`0xd0f3868`，QML包装类vtable RVA`0xb4a7fa0`，继承`VEDialogViewModel→QObject`。本体构造RVA`0x512ca80`将真实parent传入基类，并使用自己的官方QML；QML中的`saveViewModel`来自注入的`viewModel`，不是由当前handle的某个已发现getter返回。QML完成时调用`setRootWindow(root)`、`setContentItem(content_area)`。

本轮没有证明当前会话存在这个对话框，也没有找到从当前handle取得它的可靠getter/backlink。**不能凭vtable创建一个对象，也不能随意拿其他对话的viewModel。**由于第9.1节直接保存槽已经满足样例生成需要，不应为取得这个非必要对象扩展bridge或猜owner布局。

证据：`真实继承及vtable`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-savevm-rtti.json`，未随源码分发）、`构造`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-savevm-ctor-0x512ca80.txt`，未随源码分发）、`QML包装构造`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-savevm-ctor-0x3048e20.txt`，未随源码分发）、`官方QML注入关系`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-qml-8e64c2d.qml`，未随源码分发）。

### 9.4 “独立QA真实保存→另一个自有文件→正常重启加载→真实item应用”评估

**这是与当前静态产品证据相容的正常资源生命周期，值得主线程做独立QA验证；尚未实际验收，不能提前列为完成。**新资源在正常启动时由原生loader读取，生成真实item，再由真实面板应用，和离线改当前draft文件后重开冒充编辑是不同路径。要满足本轮目标，必须保留最后的当前GUI应用与原生历史/保存/渲染环节；正常重启只解决资源发现。

完整前置与验收顺序：

1. 独立QA工程保持单一目标片段选中，先保存工程，记录原生轨道、全部grade与其他多轨效果基线；确认无导出、异步保存或其他mutation在进行。
2. 使用真实handle的普通`save()`，等待正式preset落盘并核验version3、完整grade和`image_path`。这一步提供坐标与默认字段的真实样例，不拿付费/第三方预设充作自有资源。
3. 在另一个唯一名称的新自有preset文件中，只改变目标四通道几何并正确设置`color_curves.enable`；保留其余grade与有效自有资源引用，不覆盖原始preset、索引中的他人项或任何draft。若保存样例无法说明控制柄单位/范围，先核对后再构造，不能凭UI0–255显示值猜。
4. 通过已有正规的保存、关闭、启动入口完成剪映生命周期；不强杀、不丢弃未保存编辑，不在导出时退出，也不使用CU。若现有工程没有可靠的正常退出入口，这一步仍是未解决前提，不能用进程终止替代。
5. 重启后PID/birth、ASLR基址、全部QObject地址和live session/token均重新核验。旧pointer和session一律不能复用。由正常constructor扫描生成genuine个人item，并确认它持有的新预设名与完整曲线参数，不能构造假item或只发通知。
6. 打开/保持独立QA工程基线，正常绑定真实当前选择，通过真实item `importClicked()`/正常应用入口应用。此时才是新的当前GUI编辑，不能把资源载入或文件内容本身算修改成功。
7. 回读当前模型与保存材料，验证四通道中间锚点和**实际参与Bezier的左右控制柄**均改变，验证原生undo恢复、redo重现，保存并原生导出产生对应像素差异；其余轨道/字幕/音轨/速度与非目标grade不受无意改写。

风险与边界：正常重启会结束旧会话，旧的内存undo历史不能据此承诺跨重启保留；验收的undo/redo应属于重启后真实apply操作。预设应用可能覆盖它包含的其他grade，因此必须使用完整基底并核对非曲线字段。第一点左柄/最后一点右柄不参与当前转换，不能只改它们。`sync_direction_control`在preset DTO中的保留仍未知。当前会话即时reload文件的普通Qt入口仍未找到；正常重启路线不能被描述为已经补齐即时reload。

## 10. 一次真实保存仅生成JPEG：只读定位到死线程队列中的writer事件

### 10.1 已发生的真实尝试与研究边界

主线程已通过公共`agent live color-preset-save`调用真实handle `save()`一次，request=`85985638-93cc-4cc0-a9bd-bfa035f3c658`，源为原30秒工程的片段`67D8D40A-A953-4858-B663-36DCE098D576`。30秒确认超时后没有重放。输出仅为`Presets/Adjust/预设调色1.jpeg`，大小82991字节；没有同名JSON或cfg。源工程随后已正常保存关闭，后续主线程已切换其他QA工程；本节只读的是全局预设保存对象与它捕获的旧保存事件，**没有把该item当成当前QA选择或对旧segment重新发操作**。

本节未调用GUI/pipe/native方法、未消费队列、未移动线程、未改任何进程/草稿/资源/engine/bridge状态。只读前再次核对PID26164/birth134375592292885847。

主线程证据：`一次尝试的独立确认`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/native-preset-save-independent-inspection-v27.json`，未随源码分发）。该文件记录其采集时的旧工程，不能将其`current`字段误认为本节研究时的当前工程。

### 10.2 manager/item的实际中间状态

只读snapshot确认真实source1 item已存在：

| 字段 | 实测值 |
|---|---|
| name | `预设调色1` |
| version | 3 |
| 四通道点数 | luma/red/green/blue各2点 |
| item.file_path | 空 |
| AdjustPreset.image_path | 空 |
| manager封面工作队列指针`+0x50` | 非空；这是普通C++工作队列，首字节为状态，不是QObject vtable |

这与“已创建item、封面任务已生成JPEG，但保存writer未执行”相符。`0x4fd5a70`若执行，会在调用JSON writer前将回调的封面路径写到preset.image_path；目前该字段仍空。因此没有依据先归因于上传限制、JSON字段校验或另一个写入根目录。

证据：`真实中间状态与完整已采集曲线`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/pending-preset-after-real-save-readonly.json`，未随源码分发）、`普通封面队列只读快照`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/pending-preset-cover-task-readonly.json`，未随源码分发）。内存中完整grade不是一次成功落盘的JSON，不能混称“正式预设文件已生成”。

### 10.3 封面完成后的确切派发链

本轮把此前未知的functor caller接通：

```text
manager.save 0x4fe4bd0
  -> cover arrangement 0x4fdd450
     -> ordinary C++ worker queue
     -> functor vtable 0xcb0aae0, DoCall 0x4fdb260
     -> cover/offscreen render task 0x4fd7240
        -> save JPEG
        -> original completion functor vtable 0xcb0ab18
        -> DoCall 0x4fdb230 -> dispatch wrapper 0x4fd4160
           -> QMetaObject::invokeMethodImpl(manager, writerSlot, AutoConnection, null)
           -> writerSlot.impl 0x4fe0750
              -> call operation1 -> 0x4fd5a70
                 -> set preset.image_path
                 -> write JSON 0x4fe5610
                 -> write cfg 0x4fe5280
                 -> presetListChanged
```

Qt调用槽`VECreator` IAT`0x187f26558`已解析为本机Qt6Core的`QMetaObject::invokeMethodImpl`（RVA`0xa7b00`）。wrapper把connection参数设置为0/Auto，并以真实全局manager作receiver。离屏任务`0x4fd7240`的身份也由此确定；它能生成完整曲线封面，但这条链不是当前GUI的正常预设应用入口，已修正第8.3节。

证据：`两层functor vtable`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-callback-vtable-slots.json`，未随源码分发）、`完成派发wrapper`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-callback-dispatch-0x4fd4160.txt`，未随源码分发）、`真正writer slot`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-save-writer-slot-0x4fe0750.txt`，未随源码分发）、`本机Qt invokeMethodImpl`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-qt-invokeMethodImpl-static.txt`，未随源码分发）。

### 10.4 硬证据：manager绑定已退出线程，writer仍在该线程队列

没有调用QObject::thread。先静态读取本机Qt6Core该getter（RVA`0xe23e0`），确认为`QObject+8 → private+0x58 → QThreadData+0x58 → QThread*`；再按本机invokeMethodImpl的真实指令，读取`QThread+8 → private+0xb0 → threadData+0x60`得到Windows线程ID。结果：

| 对象 | QThread* | Windows线程ID | 当前Windows线程列表 |
|---|---|---:|---|
| 真实AdjustPresetSaveManager | `0x372e75f0` | 29264 | **不存在** |
| 真实QCoreApplication | `0x470210` | 26480 | 存在 |
| 常驻bridge工作线程 | 不据本节Qt getter推断 | 24504 | 存在 |

manager所属QThreadData=`0x5a7be020`，其eventDispatcher（`+0x68`）为null。按本机Qt postEvent与QMetaCallEvent构造函数的真实布局进行只读核对，该线程postEvent列表中恰有1项，receiver就是manager：

```text
QMetaCallEvent type = 43 (0x2b)
posted = true
slot.impl = VECreator+0x4fe0750
slot.saved_manager = 0x7ffbb977aec0
slot.saved_item = 0xd0d687c0
slot.cover_path = %USERPROFILE%/AppData/Local/JianyingPro/User Data/Presets/Adjust/预设调色1.jpeg
```

这不是泛化的“某个回调可能慢”：**本次JPEG的确切正常JSON writer事件仍排在已退出线程的队列上，且没有event dispatcher处理它。**当前主GUI线程是否继续工作不改变该receiver的线程归属。本轮没有处理、取出、重新派发或复制此事件。

证据：`QObject线程getter静态证据`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-qt-thread-getter-0xe23e0.txt`，未随源码分发）、`被动线程归属`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/pending-preset-thread-affinity-readonly.json`，未随源码分发）、`Windows线程存在性`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/pending-preset-windows-thread-existence.json`，未随源码分发）、`捕获本次writer的精确队列快照`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/pending-preset-postevent-queue-readonly.json`，未随源码分发）、`Qt postEvent静态布局`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-qt-postevent-0x9cf10.txt`，未随源码分发）、`QMetaCallEvent构造`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-qt-postevent-0xd5ec0.txt`，未随源码分发）。

### 10.5 结论与下一步的安全边界

本次失败已定位为**全局manager的既有错误线程归属，导致正常writer投递到已退出线程**。没有证据表明是上传、root解析或曲线JSON schema阻止写入。当前bridge源码通过QCoreApplication的BlockingQueued分发，再在该接收线程执行Direct调用；不能仅凭manager当前坏affinity，断言是这次正式save采用了错误派发方式。manager首次构造于29264的具体历史操作未在本轮追溯，不猜责任来源。

不能把JPEG列为“预设保存成功”，不能延长等待后无证据宣布完成，也不能重放同一save。研究侧不建议直接改threadData、伪造回调、手动写manager缓存、任意调用内部writer或将它们当成正常产品修复。已退出owner线程的既有事件如何处置，应由主线程在保留这次needs-inspection证据后决定。

若后续走正常关闭/重启生命周期建立新QA会话，应在任何新预设任务之前验证新manager的QObject affinity确实为QCoreApplication主线程；旧PID/birth、对象与pending事件不再复用。正常产品生命周期重建全局对象与再次执行旧任务是不同决策，本节没有执行其中任何一步，也没有授权把本次失败任务自动重试。

### 10.6 现有公共正常退出能力的源码核对

按主线程要求停止进一步队列读取与派发后，仅检查本项目源码，结果是：**已有正常关闭已保存编辑页并回首页，尚无已验证的“在首页正常退出整个剪映进程”公共命令**。

- [agent_window_lifecycle.py](../../engine/agent_window_lifecycle.py:10) 的`close_saved_editor`要求已保存并读回、播放暂停、文件SHA稳定及同一session，使用可取消的`QWindow.close`关闭当前编辑窗；确认结果是`home-without-edit-draft`并明确`process_terminated=False`。它不是整个应用quit。
- [window_state.py](../../engine/live_editor/window_state.py:7) 的`current_main_window`先调用`editor.context()`，只接受`objectName=MainWindow`和`title=剪映专业版`，以focus/transient chain或Qt allWindows列表查找且检查session。无edit draft的首页不能直接复用这项上下文约束。仓库没有`engine/agent_window_discovery.py`；同名的是[test_agent_window_discovery.py](../../tests/test_agent_window_discovery.py)，实际实现为window_state.py。
- [agent_modal_recovery.py](../../engine/agent_modal_recovery.py:101) 的`cancel_low_disk`只绑定精确低磁盘原生alert，核对文本/visible/confirmedClose后正常close；不能用它给普通首页窗口发quit。其`ModalChannel`能使用现有同指纹桥在无edit context的情况下服务真实Qt对象，是底层可复用运输能力；现成公开恢复wrapper仍明确限于低磁盘alert，并不构成已经实现、验证过的首页正常退出功能。
- [agent_entry.py](../../engine/agent_entry.py:145) 的`agent live close`调用上述编辑页关闭函数；[生命周期测试](../../tests/test_agent_window_lifecycle.py)也只验收回首页、保存取消和session竞态，没有验收进程正常退出。

本轮没有调用这些函数、连接恢复pipe、关闭窗口或重启进程。若主线程新增一个有明确对象身份/首页无编辑检查的正常退出包装，应单独验证它确实走原生可取消退出，不能把force kill、bridge worker退出或编辑页回首页混称“剪映已正常退出”。

### 10.7 新`quit-home`包装可复用的真实Qt实例与普通槽证据

按主线程后续要求，仅在内存中静态解析本机Qt6Core导出表、metaobject和指令，未调用退出、未连接pipe、未改任何进程状态。本次未新增研究脚本/产物文件，只追加本报告。目标Qt6Core.dll SHA256：`85725ddb9c5c68a276000ec8e235eeeb35374eb910a729700b988a2da670d0ee`。

| 项目 | 精确导出/元数据 | RVA |
|---|---|---|
| 应用实例静态指针slot | `?self@QCoreApplication@@0PEAV1@EA` | `0x4d7580` |
| instance叶getter | `?instance@QCoreApplication@@SAPEAV1@XZ` | `0xddd0` |
| QCoreApplication staticMetaObject | `?staticMetaObject@QCoreApplication@@2UQMetaObject@@B` | `0x339570` |
| meta字符串表 / data | 本机revision10元数据 | `0x339180` / `0x339320` |
| static metacall | 普通Qt方法分发 | `0x95d90` |
| quit导出 | `?quit@QCoreApplication@@SAXXZ` | `0x9df60` |

`instance()`在本机发布物中的有效叶指令明确为：

```text
Qt6Core+0xddd0  mov rax, qword ptr [Qt6Core+0x4d7580]
Qt6Core+0xddd7  ret
```

因此可以只读`module_base+0x4d7580`取得真实应用QObject，无须执行instance函数或猜单例地址。先前PID26164/birth134375592292885847的被动值为`0x3de4f30`，它只是那一代进程的证据，不能硬编码到新进程。主线程QThread静态slot是另一个导出`?theMainThread@QCoreApplicationPrivate@@2V?$QBasicAtomicPointer@VQThread@@@@A`，RVA`0x4d7588`，勿与self混用。

metaobject实际方法表确认：local method index7为`quit`，参数数量0、return type code43/void、flags=`0x0a`（public slot）；method row为`[9,0,81,2,10,13]`。对应metacall在RVA`0x95e55`调整栈后直接跳转RVA`0x9df60`。这是一条真实的普通无参Qt槽，可以通过现有QMetaObject typed调用按名称`quit`派发；不是需要扩展ABI的私有C++入口，也不能为了省事直接跳导出地址。

本机quit函数先检查真实self存在及应用的相应运行状态，再进入应用private的正常虚调用；其void返回本身不保证退出完成。主线程计划新增的公开包装仍应单独实现并验证：首页无编辑守卫、固定进程代际和真实application身份、保存前提、正常原生退出、实际进程终止确认。现成证据只确认“槽真实存在且能用现桥封送”，没有把尚未执行的退出记为通过，也不将旧preset writer排队任务记为完成。

### 10.8 保存前的最小被动affinity guard与未构造状态

此处只复核发布物与已有只读证据，不执行quit/save、不调用单例getter。精确固定版本布局：

```text
manager_object = vecBase + 0xef3aec0          # 对象本身，不是指针slot
expected_vtable = vecBase + 0xcb0a750
expected_secondary_vtable_at_object_10 = vecBase + 0xcb0a7b0
init_guard = signed_int32(vecBase + 0xef3af58)

app_object = read_pointer(qtCoreBase + 0x4d7580)
QObjectThread(object) = read_pointer(
    read_pointer(read_pointer(object + 8) + 0x58) + 0x58)
```

`0x4fdfe00`的最终`lea rax,[VECreator+0xef3aec0]`证明manager是静态对象本体；不要再读其第一个qword当成manager地址，那是vtable。构造函数也把该对象地址直接交给QObject基类，并写主/次vtable。主vtable和`VENotifyListener`次对象`+0x10`一起核对，可避免把zero-fill或构造中的对象当成有效QObject。

`QObjectThread()`恰为本机Qt6Core `QObject::thread()`（RVA`0xe23e0`）的三次只读解引用。因此，**manager与真实app各自取得的非空QThread指针可直接比较相等**，不必走QThreadPrivate/Windows TID深链；相等表示Qt线程归属相同。这里的app已通过真实self与当前代际校验，勿把空指针相等或两个过期对象相等算通过。可额外与`qtCoreBase+0x4d7588`中的真实main QThread核对，但不必借助线程ID实现最小guard。

单例的静态初始化标记为MSVC线程安全static guard，不能按“正数=初始化成功”解释。本机getter进入header RVA`0x7379e6c`，header检测0后置-1；构造完成进入footer RVA`0x7379e0c`，其递增全局epoch并存回guard。实际完成epoch通常是负数。

| 被动观察 | 判定/处置建议 |
|---|---|
| guard=0，且主vtable、次vtable、QObject private指针均为0 | 干净的未构造状态；没有QObject可做affinity比较，不能解引用或声称“已同线程” |
| guard=-1 | 正在构造；本次派发前拒绝/报告需检查，不自行等待重放或调用getter |
| guard为稳定完成epoch，且主/次vtable正确、private/threadData/QThread均有效 | 比较manager/app QThread指针；相同才算已构造状态下线程守卫通过 |
| guard在两次读取间改变，或guard/对象vtable矛盾、链不可读 | 构造竞态或异常状态；拒绝派发 |
| 已构造，但manager QThread与app QThread不同 | 直接拒绝保存；尤其不能再向已退出owner追加另一个保存事件 |

manager对象和guard位于PE`.data`的zero-fill虚拟尾部：该节virtual_size=`0x779748`、raw_size=`0x60e400`；对象与guard相对节起点分别`0x6e7ec0/0x6e7f58`，均没有文件raw内容，加载初始为0。此事实与header的0/-1状态分支交叉支持干净未构造判别，而不是靠“读取异常就当未初始化”。

建议读取guard→对象主/次vtable及必要链→再次guard与关键指针，要求前后一致，并核对进程birth和固定DLL指纹。纯被动检查不是锁，不能替代现有串行mutation与GUI dispatcher保证。对干净未构造状态可以明确返回`uninitialized`，由原来那次正常GUI槽的首次使用完成原生初始化；**不要为了通过guard额外调用getInstance或手写QObject**。若策略要求派发前必须完成affinity核验，则该状态应明确拒绝、等待一次现有正常产品初始化路径，而非伪造“已通过”。正常槽执行后还应被动复核新对象affinity；不能把未构造分支当成绕过死线程检查的长期豁免。

依据：`singleton getter静态指令`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-follow-0x4fdfe00.txt`，未随源码分发）、`真实QObject线程getter`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-qt-thread-getter-0xe23e0.txt`，未随源码分发）、`ctor主/次vtable`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/adjust-preset-static-0x4fd47c0-annotated.txt`，未随源码分发）。本机Microsoft工具链的`thread_safe_statics.cpp`（历史本机证据：`C:/BuildTools/VC/Tools/MSVC/14.44.35207/crt/src/vcruntime/thread_safe_statics.cpp:194`，未随源码分发）也给出0/-1/epoch契约；本报告已独立核对剪映发布物中header/footer的相同指令语义，不把工具链文件版本当成目标DLL实现的替代证据。


## 11. 当前主标签到真实个人预设项：普通入口与只读 owner 绑定

本节只读固定发布物，并被动核验 PID `44364` / birth `134376337160720464`。没有调用 GUI/pipe/native、没有创建面板，没有修改 engine、桥接器或草稿。该次窄扫描未发现已构造的 `AdjustInspectorViewModel` / 个人面板 / 个人项，故以下是**静态已闭合的绑定契约**，不是当前会话已绑定成功的声明；主线程后续正常打开 QA / 切换标签后必须重新发现，不能沿用本节进程地址。

### 11.1 左侧素材库与右侧视频 Inspector 是不同 owner

现有 [color.prepare_controls](../../engine/live_editor/color.py) 使用右侧 `DraftInspectorVideoViewModel`，切换它的 `adjust` 属性页。它没有到左侧个人预设列表的普通 C++ getter。

官方 `NewAdjustInspector QML`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-qml-873bf55.qml`，未随源码分发） 则属于左侧调节素材库，声明真实强类型属性：

```qml
property AdjustInspectorViewModel baseViewModel: AdjustInspectorViewModel {}
property PersonalAdjustPresetPanelViewModel personalAdjustPanelViewModel:
    PersonalAdjustPresetPanelViewModel {
        tabType: PersonalAdjustPresetPanelViewModel.OnlyPreset
    }
```

`AdjustInspectorViewModel` 的固定 Qt metadata RVA `0xaccd210`、metacall `0x279d610` 仅有 `tabModel` / `tabTitles` 属性及 `enablePersonalAdjustPresetRefactor()` 方法，没有 `getPersonalPanel()`。不能虚构一个右侧 Inspector 偏移或 getter。`OnlyPreset` 精确枚举值为 `1`，另两项 `OnlyCreate=0` / `CreateAndPreset=2`；见`已解码 Qt metadata`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-api-qt-decoded-static.json`，未随源码分发）。

### 11.2 正常主标签入口，不把类型值当界面索引

固定发布物的 `MainTabPanelViewModel`（metadata `0xacccc40`，metacall `0x279ce30`）有普通 Qt invokable：

```text
gotoTab(MainTabEnum::Type type) -> void   local method 18
```

`MainTabEnum` metadata `0xacb38f0` 明确 `Adjust=8`。dispatch table `0x279d26c[18]` → `0x279cf9a` → 正常实现 `0x2a97470`：先通过继承的 `datasource` getter `0xd9b5e0` 取 `*(main_tab+0x10)`，cast 到 `MainTabPanelDataSource`，再由 `0x2a93030` 在真实 type 列表中查找索引，最后调用正常 `setIndex` 虚方法。故 `8` 是标签**类型**，不能直接当作界面索引。

本项目现有 [typed_args.py](../../engine/live_editor/typed_args.py) 与 [typed_call.cpp](../../bridge/live-editor/typed_call.cpp) 已支持 `int` 存储加精确 Qt enum 类型名覆盖，静态相容的正常候选调用是：

```python
editor.invoke_typed(main_tab, 'gotoTab', [('int', 8, 'MainTabEnum::Type')])
```

此研究未执行该调用。实施时仍需同会话、主线程、真实 owner 和固定指纹守卫；不能因类型名相容就把尚未实际调用记作通过。

用于现有 `profile.py` 发现的固定 vtable：

| 类 | primary vtable RVA | 同对象次 vtable 守卫 |
|---|---|---|
| MainTabPanelViewModel | `0xb4567a0` | `+0x28=0xb456828`, `+0xa8=0xb456850` |
| QQmlElement MainTabPanelViewModel | `0xad07478` | `+0x28=0xad07500`, `+0xa8=0xad07528` |
| MainTabPanelDataSource | `0xb456208` | `+0x10=0xb456280` |
| AdjustInspectorViewModel / QQmlElement | `0xb473d50` / `0xad09598` | QObject private back-pointer / 线程核验 |
| PersonalAdjustPresetPanelViewModel / QQmlElement | `0xb474938` / `0xacfd718` | `tabType` 位于 `+0x10`，必须为 `1` |
| PersonalAdjustPresetItemViewModel / QQmlElement | `0xb4744c0` / `0xacfd778` | 必须继续验证 model 与 import service 归属 |

本节编写时 [现有 profile](../../engine/live_editor/profile.py) 尚未登记这些发现类型。`winprocess.scan_objects` 只识别 `OBJECTS` 中的 vtable，故已有通用扫描不会自动返回它们；Qt 方法确实存在，不等于项目已经实现该绑定。

### 11.3 从正常 datasource 缓存绑定真正 NewAdjustInspector root

`MainTabPanelDataSource.tabView(int index)`（Qt local method `2`，metacall `0x27a10f0`，vtable `+0x68` → `0x2a93430`）使用：

```text
creator = *(datasource+0x18)              expected vt 0xb489bf8
valid MainTabEnum array = *(datasource+0x48)
count = int64(datasource+0x50)
type = array[index]                      index 必须先验证范围
```

`creator` 的真实类是 `MainTabComponentCreator`，不属于 QObject；其内部 `0x2f68f80` 正常获取/必要时创建组件，不能把该私有虚函数地址当成新公开 ABI。其静态源码链 `0x2f68f80 → 0x2f68870 → 0x2f69d60` 将类型 `8` 映射到原生 QML URL（字符串 RVA `0xb498c80`）：`qrc:/MaterialPanel/new_panel/adjust/NewAdjustInspector.qml`。

可以**被动读取已由正常路径建立的缓存**来核验 root：

```text
map_data = *(creator+0x10)
header = *(map_data+0x08)
root_node = *(header+0x08)
node: left +0, parent +8, right +0x10, is_nil byte +0x19
node key int32 +0x20
node mapped QPointer: header +0x28, QObject* +0x30
```

该布局来自已发布函数 `0x2f68f80`、`0x2f68220` 与正常插入 `0x2f69c00`，不是猜测节点。只读遍历必须限定节点数量、检查 nil/header、循环、指针可读性和 key 唯一性，且 key `8` 的 QPointer 必须存活；缓存没有该项时停止读取，交由主线程正常 `gotoTab` 初始化，不能直接调用内部 factory 或构造虚假 QQuickItem。

通过该真实 root，可继续核验发现的 `AdjustInspectorViewModel` 和 `OnlyPreset PanelVM` 的 QObject parent 均属于它；Qt6Core 公开 `QObject::parent()` RVA `0xee50` 的实际布局是 `*(*(object+8)+0x10)`。若要读取 QML 强类型属性本身，必须按该 root 的真实动态 metadata 找到 `personalAdjustPanelViewModel`，不能硬编码它在另一层 QML 中的 property index。

现有 bridge 的 `get` 仅支持 QString/bool/number，无法回传该 `QObject*` 属性；见 [bridge.cpp](../../bridge/live-editor/bridge.cpp)。本机 Qt6Qml 导出 `QQmlVMEMetaObject::getForProperty(QObject*,int)` (`0x25b510`) 与 `readPropertyAsQObject(int)` (`0x25e2e0`) 提供一手普通 getter 语义，但本节未扩展桥、不调用它们，也未把它们包装成可用的 live API。后者真实读取 VME `+0x98` 的 member storage，本地 property 的 QV4 slot 为 `member_data+0x10+8*index`；还验证 QObjectWrapper vtable 继承链和 wrapper `+0x18/+0x20` 的存活 QPointer。不能只从相似数值认定某个 slot 是目标属性，也不能跳过动态 metadata / property owner 层选择。

### 11.4 真实 collection、provider 与 delegate 必须完整对上

沿同一个 `OnlyPreset PanelVM`：

```text
panel +0x18/+0x20 -> collection QPointer      vt 0xb439e98
collection +0x30/+0x38 -> provider QPointer  vt 0xb4746b8
provider +0x88..+0x90 -> shared_ptr<Model> vector, stride 16
```

正常 `getCollectionControl()` 实现 `0x2d0a5a0` 创建并绑定上述对象；`aboutToShow()` 的 `0x2d0a4c0` 用当前 panel 的 tabType 设置 provider，再走正常 `0x2d095a0` 载入 manager 的内存列表。它不是文件即时 reload。

provider 的真实 delegate 绑定函数 `0x2d09ed0` 读取 delegate QObject property `"baseViewModel"`（字面值 RVA `0xa0dd7a0`），dynamic_cast 正常 model，然后 `0x2d06e70` / `0x2d04ef0` 将该 shared_ptr 绑定到 ItemVM `+0x70/+0x78`。紧接着 `0x2d05350` 绑定当前 provider 的服务：

```text
ItemVM +0x90/+0x98 == provider +0x40/+0x48    MaterialImportService
ItemVM +0x80/+0x88 == provider +0x60/+0x68    PreviewService
ItemVM +0xa0/+0xa8 == provider +0x50/+0x58    Drag service
```

因此导入前必须核验 ItemVM 的 `+0x70` 等于该 provider vector 的一项，所有相关 shared_ptr 控制块存活、QObject 主线程与进程代际一致，并由真实 model/manager item 检查预设唯一名称、版本和资源身份。自有 JSON 文件名相同或 ItemVM.name 相同均不足以单独证明绑定；不要把另一个草稿的旧 delegate、预览模型或任意堆内存对象作为接收者。

自有资源身份还有一条精确指针归属链：`PersonalAdjustPresetItemModel` 的正常更新 `0x2f3ebf0` 把输入 `shared_ptr<lvve::AdjustPreset>` 保存到 model `+0xb8/+0xc0`。manager 的 `0x4fe3040` 从 manager `+0x18..+0x20` 的 `shared_ptr<AdjustPresetItem>` vector 筛选 source1，再返回各 item `+0x08/+0x10` 的 DTO shared_ptr。因此可被动要求 `*(model+0xb8)` 正好等于当前 manager 某个 `*(item)==1` 条目的 `*(item+8)`，再核对该 DTO `name` (`std::string +0x28`)、`version` (`int32 +0x68`) 和完整 `color_curves` (`+0xb8`) 与自有输入。model `+0xc8` 是另一 resource 对象，不能误当作这个 preset DTO。所有 shared_ptr 控制块的 strong reference 应大于0；QObject QPointer 存活条件则是非0，二者不能混淆。

通过这些守卫后，最小正式候选调用仍仅是：

```python
editor.invoke_typed(genuine_item_vm, 'importClicked', [], ctx=current_context)
```

`官方卡片 QML`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-qml-873c88f.qml`，未随源码分发） 的加号按钮用此无参方法；方法 local `19` → `0x2d04260` → `0x2d042d0` → 当前 `MaterialImportService` (`vt 0xb473f48`) 的 `0x2cf9e30`。普通个人预设 model 在 `0x2d09d16` 被赋 type `0x10`，走常规素材导入分流。卡片单/双击调用的 `itemClicked(x,width)` 则计算 `x/width` 并更新预览，不能替代正式导入。

**确定语义**是正常加号的“添加到轨道”请求（QML 文案 key `pc_add_to_track`），不是下载按钮；**尚未证明的语义**是最终新增独立调节片段还是修改所选 clip，以及底层具体 undo handler。两者只能由主线程一次真实调用后的完整保存差异、GUI 模型回读、真实 undo/redo 和原生出片确认。不得由静态调用链预先宣称应用成功、覆盖选中片段成功或撤销已经通过。


### 11.5 当前 QA 的真实派生 datasource：基类守卫误拒绝的修正证据

主线程正常打开 `AV_FullCurves_QA_v39_20261028` 后，当前代际为 PID `26548` / birth `134376361343594314`。本轮独立被动 Reader 得到与主线程相同的唯一主标签对象：`main_tab=0x52542720`，主 vtable RVA `0xad07478`，真实 `datasource=*(main_tab+0x10)=0x4acd3090`。`QObjectPrivate.q_ptr` 回指正常；没有调用 GUI/pipe/native，没有修改 profile 或草稿。

该 datasource 的确切 RTTI 是 **EditorTabPanelDataSource**，不是 MainTabPanelDataSource 本体：

```text
primary vtable RVA 0xb4563f8
secondary vtable at +0x10: RVA 0xb456470
RTTI COL RVA 0xd7008b8 / type descriptor RVA 0xec714c0
base MainTabPanelDataSource offset 0
base ITabPanelDataSource offset 0
base QObject offset 0
VENotifyListener offset 0x10
```

因此 v47 inventory 在检查 primary `0xb456208` / secondary `0xb456280` 时把真实派生 datasource 过滤掉；`main_tab+0x10` getter没有读错，也不是另一种 MainTab QQml wrapper。适用的固定接受集合应只加入这一对已经证实的派生 vtable；不能放宽成接受任意 QObject。

派生类的 `tabView(int)` 是 vtable `+0x68` 的 RVA `0x2a93ca0`。关键指令 `0x2a93cd0` **原样调用已核验的 base `0x2a93430`**，随后对真实返回的 QQuickItem 设置 `editmode=0` 并返回同一个对象。由此确认 base 的 type vector / creator / 缓存契约在这个派生类上仍适用；绕开普通 Qt `tabView` 私自调用内部 creator 则会遗漏这段正常产品逻辑，不应这样实施。

本次被动实读：

```text
datasource +0x18 -> 0x52500860
creator RTTI MainTabComponentCreator
creator vtable RVA 0xb489bf8
valid type array: [1,2,3,4,5,6,11,13,7,8,9,12]
Adjust type 8 -> current list index 9
```

正常 `gotoTab` 仍应传 `('int',8,'MainTabEnum::Type')`，由 native 查当前 index；本次读到 index9不构成以后会话固定索引。所有本节绝对地址仅用于这一代际的证据，不允许在重启后复用。

此结论只修正候选过滤，不等于 `gotoTab` 或 `importClicked` 已执行。主线程收到此研究前未派发它们；真实 root/OnlyPreset/delegate、历史与出片仍须顺序验收。


### 11.6 正常父/子分类选择 API 与完整 DTO 的实际字段核验

主线程 v48 已通过普通 `gotoTab(Adjust)` 建立当前 root `0x873ebaa0`、OnlyPreset panel `0x545936e0`、AdjustInspectorVM `0x955fb760`，并确认完整时间线未变。本研究仍未调用 GUI/native，只在相同 PID `26548` / birth `134376361343594314` 中被动找到唯一属于该 root 的 `AdjustTreeViewModel`：

```text
object 0x45bdb1d0, QQml vtable RVA 0xad03f90
QObject parent chain:
0x45bdb1d0 → 0x54591250 → 0x873ebba0 → 0x873ebaa0 → null
```

该类普通 vtable 为 `0xb448048`，继承 `VETreeWithSearchViewModel → VETreeViewModel → QUITreeViewModel`。应核验真实 owner 链、QObject 存活与 GUI thread，不可把另一个素材库的树作为接收者。

**无需 QStringList 或猜平铺索引的现成普通 API**就在 `VETreeViewModel` metadata RVA `0xa16ca60`（metacall `0x194d860`）中，保留发布物原有拼写 `Catgory`：

```text
local16 bool isExistChildItem(QString parent_key, QString child_key)
local15 bool isExistParentItem(QString key)
local34 void selectItemByCatgory(QString parentKey, QString catgoryKey,
                               bool bCrossCatgory)
local35 void selectItemByCatgory(QString parentKey, QString catgoryKey)
```

local35 是默认参数克隆，dispatch `0x194df9f` 显式把 bool 设为 true。local34 dispatch `0x194df75` → 实现 `0x1a24d60`：确认真实树模型存活，按 parentKey 查找对应的父节点，再仅在其真实 children 中比较 catgoryKey。命中后 `0x1a2514a` 调用普通选择实现 `0x1a23ef0`，最后更新真实模型的选中项。静态相容、由主线程串行执行的候选调用是：

```python
# 主线程可先通过普通只读方法确认精确的父/子键存在。
editor.invoke_typed(tree, 'selectItemByCatgory', [
    ('QString', 'my_adjust'),
    ('QString', 'my_default'),
    ('bool', True),
], ctx=current_context)
```

此处键来自 `NewAdjustInspector 官方 QML`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/preset-qml-873bf55.qml`，未随源码分发） 的 `tabKeyMyAdjust` / `tabSubKeyMyCustomPreset`。不存在相应 child 时应停止，不造树节点、不改 QML visible/开关。

`selectItemByIndex(int parentIndex)`（local24）其实通过默认参数克隆设置 `childIndex=0, from_deep_link=false`，再进入 `selectItemByIndex(int parentIndex,int childIndex,bool)`（local22 / `0x1a25960`）；它不是整个展开树的平铺索引。需要索引时必须分别来自真实父、子层级，本任务有精确键 API，优先用键。

可用于被动回读的真实选择状态为 tree `+0x58` 的 `QList<QString>` 三元组 `(header,data,count)`，每个 QString 步长24字节；本次实际值为 `['new_adjust']`。正常 `0x1a23ef0` 会更新此列表并调用 `0x1966800`；后者是该 metadata 的 local signal0 `curSelectedItemKeys(QStringList)`，由原生 Qt signal activation 发布。官方 QML 收到对应变化后自然调用 `personalAdjustPanelViewModel.aboutToShow()`。因此主线程应回读 `['my_adjust','my_default']`，再核验真实 provider / delegate 与完整时间线，而不是手动写 QML 显隐属性。

完整预设 DTO 的被动实际校验同时已完成。原生 manager 中 source1 item `0x7c69e550` → DTO `0x8382a870` 的 name 为 `AgentCurveQA_v39_20261028`、version3。源文件为 `%USERPROFILE%/AppData/Local/JianyingPro/User Data/Presets/Adjust/AgentCurveQA_v39_20261028.json`，SHA256：

```text
4fbce592e0670e4cbb085b51cd88a9aaeee04957042c0b2afe3928279cacb719
```

实际内存布局和文件逐 double 比较如下：

| 内容 | 相对 AdjustPreset DTO 的偏移 |
|---|---|
| color_curves 对象 | `+0xb8` |
| enable bool | `+0xe0` |
| luma std::vector begin/end/cap | `+0xe8` |
| red std::vector begin/end/cap | `+0x100` |
| green std::vector begin/end/cap | `+0x118` |
| blue std::vector begin/end/cap | `+0x130` |

每个 vector 是连续的 point **值对象**，步长 `0xd0`，不是 shared_ptr 数组。每个 point 的 double 坐标为：`anchor.x/y +0x50/+0x58`，`left_control.x/y +0x88/+0x90`，`right_control.x/y +0xc0/+0xc8`。四通道均3点，所有锚点、左右控制柄及 enable 与该源 JSON **完全相等**。身份守卫应验证 begin≤end≤cap、字节差是0xd0的整数倍、合理点数、有限坐标、稳定源文件哈希及 shared_ptr 归属，再逐字段比较；不要把这些值误当0..255，也不要硬绑 JSON coder 派生 point 的单一 vtable。

此项实际证据证明正常 loader 已真实保留完整自定义四通道曲线；它还没有证明预设已应用到当前 clip、历史已记录或出片已改变，后者保留给主线程一次正常导入与 undo/redo/渲染验收。

## 12. 真实导入后的独立调节轨、普通曲线控件和禁用算法节点

本节固定为 `11.4.7.14462`。研究侧只解析发布物、已有主线程证据，以及使用 `PROCESS_VM_READ | PROCESS_QUERY_LIMITED_INFORMATION` 被动读取当前进程；未调用 GUI/native/pipe、未发输入事件、未改 engine、官方资源、草稿或进程内存。所有 RVA 都相对各自 DLL；绝对对象地址仅是本代际的证据，不可在重启后复用。

主线程实际请求 `afdf4c1b-522e-49a0-b136-83dae4b4a2ab` 已确认：普通 genuine `PersonalAdjustPresetItemViewModel.importClicked()` 新增一个3秒 `adjust` 轨，含曲线材料 `34DCF126-3A12-4ac5-9586-751A95AA4FE8` 的四通道3点锚点和完整左右控制柄。它**没有**就地改原视频。原始证据为 `v52完整时间线`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/native-full-curves-after-import-timeline-v52.json`，未随源码分发）。后续 undo/redo 和渲染由主线程串行验收；研究侧不以 method 返回代替真实结果。

### 12.1 新调节片段的真实 Inspector 绑定

当前代际：PID `26548`，birth `134376361343594314`，VECreator base `0x7ffb0f390000`。目标 segment 为 `77D29E0A-3E46-461d-B5F4-64DA78E08594`；timeline 为 `86CFB4DF-2D7B-4C4A-990C-64462111ED7A`，native timeline `0x43fa5ee0`。被动取得的对象链：

```text
MainTimeLineSegmentAdjustViewModel 0xa65e0bc0
  +0x298 -> timeline 0x43fa5ee0（timeline+0x688 QString 与目标timeline id相同）
  +0x288 -> MainTimeLineSegmentAdjustModel 0x8b4ba680
DraftInspectorAdjustViewModel 0x82cb8d80
  +0x30/+0x38 -> current tab-control QPointer(header,object)
DraftInspectorAdjustBaseViewModel 0x73611ad0
  ordinary handler() getter -> +0x28 -> AdjustSettingHandleViewModel 0xa6ab68f0
```

`handler()` 的 Qt metadata RVA `0xbf0a090`，metacall `0x30d2d00`，local method0，dispatch 进入 `0xdcc7c0` 直接读取 `this+0x28`。这是 **+0x28，不能套用其他 Inspector 的 +0x18**。

实际 handle 的 `+0x1b8/+0x1c0/+0x1c8` 为 `std::vector<SegmentHolder>` begin/end/cap，单项大小 `0x148`，不是 QString 或 shared_ptr 数组。实际 begin `0x98bf6720`，end/cap `0x98bf6868`；其第一项首部 shared_ptr 指向 native segment `0xc10b6990`，RTTI 为 `SegmentPictureAdjust@lvve`。native segment `+8` 的 std::string id 与目标 segment **逐字相等**。`SegmentPictureAdjust::get_material()`（videoeditor `0x1a8b50`）返回 `segment+0x158` 的真实 `MaterialPictureAdjust` shared_ptr，实际 material `0x3612a300`。这条链绑定当前新增调节片段，不能继续使用旧 video settings 的 owner 偏移。

固定 vtable / 次 vtable 如下，接入 profile 时仍需检查完整 QObject 存活、owner 链、同 GUI 线程、当前 draft/session/segment，而不是只接受相似类名：

| 类 | base vtable RVA | QQml wrapper vtable RVA | 次 vtable |
|---|---|---|---|
| MainTimeLineSegmentAdjustViewModel | `0xac59078` | `0xa83fde8` | base `+0x10=0xac59310,+0xa0=0xac59338`；wrapper `+0x10=0xa840080,+0xa0=0xa8400a8` |
| MainTimeLineSegmentAdjustModel | `0xac84ef8` | — | `+0x10=0xac84fd8,+0x18=0xac85180,+0x310=0xac851a0` |
| DraftInspectorAdjustViewModel | `0xbfc24a8` | `0xb4b3eb8` | 无额外次 vt |
| DraftInspectorAdjustBaseViewModel | `0xbfc2620` | `0xb4b3f90` | base `+0x10=0xbfc2680`；wrapper `+0x10=0xb4b3ff0` |
| DraftInspectorAdjustModel | `0xbff14b8` | — | QObject / DraftInspectorBaseModel |

继承的普通 `getSegmentId() -> QString` 也可用于主线程只读身份核对：MainTimeLineSegmentViewModel metadata `0xa805ea0`、metacall `0x2061360`、local82，dispatch case `0x2061b48` → `0x224c840`。该实现从 clip `+0x288` 取得 model 并走正常 model interface；研究侧没有调用它。

### 12.2 曲线显示、启用状态与普通重置 API

派生 handle metadata `0xbf40960` / metacall `0x30f9390` 的属性和 getter 分支：

| local property | 名称 | 真实布局 | getter RVA |
|---|---|---|---|
| 21 | colorCurvesEnableState | `+0xe4 int` | `0x30faa93` |
| 22 | colorCurvesData | `+0xe8/+0xf0/+0xf8` QList header/data/count，元素stride8 | `0x30faaa0` |
| 23 | currentSelected | `+0x100 int` | `0x30fab0b` |
| 24 | allSelected | `+0x104 bool` | `0x30fab18` |
| 25 | hideCurve | `+0x105 bool` | `0x30fab26` |
| 28 | enableNnewAdjustCurveMode | `+0x124 int` | `0x30fabac` |
| 31 | isAdjustMergeResourceLoaded | `+0x138 bool` | `0x30fabd7` |

启用枚举**已从真实 Qt enum 表验证，不能按常见 bool 推测**。基类 `AdjustSettingHandleViewModelBase` metadata `0xbf04950`、metacall `0xaf7120`：`CheckBoxOn=0, CheckBoxOff=1, CheckBoxMix=2`。`ColorCurveEnableMode` 为 `EnableOldRgbaCurve=0, EnableHueSatCurve=1, EnableNewRgbaCurve=2, EnableHueSatAndNewRgbaCurve=3`。原始解码在 `hsl-base-qt-decoded-static.json`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/hsl-base-qt-decoded-static.json`，未随源码分发），派生属性的 exact type 为 `AdjustSettingHandleViewModelBase::CheckBoxState`。

官方 `新 RGB 页 QML`（历史本机证据：`D:/JianyingHeadless/integrations/native-color-param-controls-20261028/adjust-qml-8e5ece3.qml:178`，未随源码分发） 约束为：

```text
new RGB group visible = isAdjustMergeResourceLoaded && mode in {2,3}
checked = colorCurvesEnableState === CheckBoxOn
inner curve controls enabled = group.checked
hideCurve = 只把非当前通道opacity降到0，不关闭实际曲线效果
channel index: 0=L/luma, 1=R, 2=G, 3=B
```

13:25:23 的 `被动读值`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/native-adjust-curve-enabled-passive-v54.json`，未随源码分发） 确认同一个 handle 的 SegmentHolder id 匹配目标 segment，四个 genuine `AdjustColorCurvesData*` 与新 Bezier VM 的 channel 都逐项匹配0..3、mix均false；resourceLoaded=true、mode=3、hideCurve=false、allSelected=true、currentSelected=0，**但 colorCurvesEnableState=1，即 Off**。同时先前被动读取的 native material 曲线 enable 为true；因此不能宣布当前 GUI checked/enabled 已通过，更不能把这两个状态强行等价。主线程应等正在运行的渲染结束后，用普通 get 和严格 selection/owner 链重新确认状态。研究侧没有为“修复”差异调用开关或刷新。

官方 QML 本身使用以下普通方法；不是 raw setProperty、伪造 QML 对象或直接发信号：

| Qt local method | 确切签名 | dispatch / 实现 RVA |
|---|---|---|
| 100 | `void resetAllColorCurves()` | `0x30f9c78 → 0x37a5790` |
| 98 | `void resetColorCurve(AdjustColorCurvesData* pData)` | `0x30f9c56 → 0x37a5f60` |
| 104 | `void setColorCurvesViewIndex(bool allSelect,int currentIndex,bool updateStatus)` | `0x30f9cae → 0x37aa0d0` |
| 105 | 同名2参数默认克隆 | 设置 updateStatus=false 后走相同实现 |
| 101 | `void setColorCurvesEnable(bool bEnable)` | `0x30f9c82 → 0x37a9b50` |

整个 RGB 组标题的重置按钮直接调用无参 `resetAllColorCurves()`。单通道按钮调用 `resetColorCurve(colorCurvesData[currentSelected])`；实现发现 allSelected=true 且 mode2/3 会升级为全通道重置。因此单通道需要先通过正常 `setColorCurvesViewIndex(false,index,true)` 并读回状态，不能仅依赖 `activateCurveByIndex`。

`resetAllColorCurves` 会遍历当前四个 genuine 数据项，构建正常 `ResetGlobalAdjustColorCurvesReqStruct` / `ResetPictureAdjustColorCurvesParam` 请求，经真实业务 client 提交；最后进入 `0x37a1860` 的普通提交/追踪链。它不是只改变 view 缓存。静态调用链为 `0x37a5790 → std::function callback 0x3790880 → 0x37a6050 → callback 0x3788980`，后者 RTTI 标明上述正式 request / param。主线程仍应实际核验 history、保存几何和输出，不能凭静态提交分支宣称 undo 已成功。`静态指令证据`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/curve-reset-static-v54.txt`，未随源码分发）。

几何预期的可信边界：原生导出 `ColorCurvesUtils::DefaultCurves()` 在 videoeditor `0xeacdb0 → 0xeacc20` 生成两个归一化端点 `(0,0),(1,1)`，左右控制柄都在同一对角线上；该 helper 的具体控制柄为首点 left(0,0)/right(.3,.3)，末点 left(.6,.6)/right(0,0)。这证明原生默认曲线是 identity；本次尚未独立追到 reset 的最终 consumer 与此 helper 的直接联系，**不能把 .3/.6 硬编码为唯一合法 reset 保存结果**，应检验真实 saved geometry 为 identity、四通道恢复、undo后原四通道锚点与控制柄逐值恢复。不同但共线的柄仍可表达同一 identity。证据：`默认几何函数`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/curve-default-geometry-static-v54.txt`，未随源码分发）。重置验收不代替任意锚点 setter 验收；完整自定义几何的来源是 genuine 预设应用。

### 12.3 三个算法 enable 省略时都是 false

新增 adjust 的 smart_color_adjust / color_match / color_correct 默认节点 `value=.8`，本身不代表效果启用。videoeditor 的 `PersistentSegment` rapidjson `from_json` 位于 `0xd9ffd0`，字段缺失分支为：

| 字段 | 字段字符串 RVA | 缺失赋值 | persistent 偏移 / 默认 |
|---|---|---|---|
| enable_smart_color_adjust | `0x2fc16d8` | `0xda0c5b` | `+0x190=false`（r15在0xda009f清零） |
| enable_color_match_adjust | `0x2fc1708` | `0xda0e76` | `+0x1f0=false` |
| enable_color_correct_adjust | `0x2fc1738` | `0xda0ec6` | `+0x1f1=false` |

rapidjson serializer `0xda2ca0` 的 skip-default 分支也以false为默认：smart `0xda446d`、match `0xda474c`、correct `0xda47c1`。因此保存省略这三个键与false相容；不应删除默认材料来适配导出，也不应按value .8推为开启。`parser/serializer原指令摘录`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/native-adjust-algorithm-persistent-defaults-static-v54.txt`，未随源码分发）。

先前被动 native `MaterialPictureAdjust` 的 `+0x218/+0x230/+0x248` 也均false。另一个观察差异须保留：native `+0x172` 当时读为 enable_hsl=true，而 v52 不可变 snapshot 的 enable_hsl=false。主线程报告 v52 后仅正常undo/redo；本研究未找到可把差异忽略的证据，不能把它改写为一致。它不影响本节对三个算法各自 false 默认的确定解析。

### 12.4 禁用 ColorMatch 的未物化 sentinel 路径如何处理

v52 原生保存的 `color_match` 材料 `27163FD8-59F9-4a75-9438-61108F6BF630` 包含以下源特征 sentinel；主线程确认目标目录没有实际 `.match` 文件：

```text
##_draftpath_placeholder_0E685133-18CE-45ED-8CB8-2904A212EC80_##/color_match/color_match_source_feature_1793163734724.match
```

静态渲染参数构建链已验证 `enable_color_match_adjust` 的 gate：

```text
videoeditor 0x1ec9750（调节参数构建）
  0x1ecb0aa -> get_enable_color_match_adjust (0x25c330 -> material+0x230)
  0x1ecb0af cmp byte ptr [rax],0
  0x1ecb0b2 je 0x1ecb1f6     # false跳过ColorMatch filter构建
  enabled branch:
    0x1ecb1cc -> 0x1ed62b0（正常filter参数构建）
      0x1ed6ff1 -> 0x277c840（ColorMatch参数转换）
        0x277c930 -> get_color_match_info (0x1d9c40)
        0x277c981 -> get_source_feature_path (0x105c90)
```

false分支仅维护 effect id/path 缓存和后续参数清理，不进入 source_feature_path 的转换链。原生资源收集也有独立一致证据：导出的 `DraftResourcesFetcher::get_segment_resources(SegmentPictureAdjust,...)`（`0x10f6d80`）在 `0x10f7d23` 检查同一 enable，`0x10f7d2b` 为false直接跳 `0x10f7f60`，跳过 ColorMatch 整段资源收集。`完整静态指令`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/color-match-disabled-gates-static-v54.txt`，未随源码分发），`固定指纹和关键链摘要`（历史本机证据：`D:/JianyingHeadless/integrations/native-curve-full-point-api-20261028/native-adjust-reset-and-disabled-gates-static-v54.json`，未随源码分发）。

这支持一个很窄的导出契约：仅对**已经严格验证、确实引用该原生禁用 ColorMatch 材料**的 adjust segment，原样保留其未物化 sentinel 字面量；不造文件、不删节点、不允许普通任意路径、不把 enable=true/不明绑定按相同方式放行。任何用户/其他草稿的未 staging 路径仍维持原拒绝。静态 gate 不等于本次已完成出片，真实 preview/export 结果由主线程另行保存。
