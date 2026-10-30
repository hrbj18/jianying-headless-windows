# 剪映 11.4.7：色温/色调与亮度/RGB曲线的原生普通Qt入口

研究日期：2026-10-28。范围是本机 `11.4.7.14462` 发布物的静态 QML、Qt metadata、RTTI 和 LLVM 反汇编。没有调用原生方法、修改当前进程、模拟输入、改 engine/bridge/ABI 或写剪映文件。静态证据统一保存在 `D:\JianyingHeadless\integrations\native-color-param-controls-20261028`。

## 结论

**色温与色调可以沿用已接通的通用调色滑杆提交链。**当前 handler 的 `tintAdjustList[0]` / `[1]` 是蓝黄 / 绿紫两项；普通槽 `onValueChanged(ParamSettingSliderData*,double,bool withShift,bool bRecord)` 可用现有 pointer+primitive typed bridge 封送。输入是 UI 值，原生内部负责映射和实际参数提交，`bRecord=true` 对应官方 QML 的 accepted 分支。不能通过写 `curValueUI` 属性代替它。

**任意曲线锚点和控制柄坐标，当前普通Qt接口没有找到可调用 setter。**新旧 curve ViewModel 均只直接继承 QObject，完整 metadata 里没有被遗漏的基类点编辑槽；new model 只有通知/插点信号和 hover 方法。实际画面点操作在派生 QQuickPaintedItem 的 C++ 实现中。已有普通Qt入口可以切换曲线通道、开关、重置和按 x 插点，但不能把这些等价成任意 `(anchor,left_control,right_control)` setter。无 ABI 扩展、无输入事件的本轮边界下，应明确保留该限制。

可以做受限而真实的曲线往返：在已有非恒等曲线的独立草稿中，正常选择单通道，调用 `resetColorCurve(AdjustColorCurvesData*)`，再做保存、undo/redo 和实际出片；这证明“原生重置/历史链可工作”，不证明完整点编辑能力。

## 版本与证据入口

- 安装文件：`D:\刘宇钊\软件\剪映\JianyingPro\11.4.7.14462\VECreator.dll`；SHA256 `769c33961ef9d7e471e583f03c975be975b0c35e849a767690d09e9f2fc45111`。下面代码地址均为 **RVA**，PE优选基址 `0x180000000`，不能当作当前进程绝对地址。
- `曲线完整Qt metadata`（历史本机证据：`D:/JianyingHeadless/integrations/native-color-param-controls-20261028/color-param-qt-decoded-static.json`，未随源码分发）、`metadata位置`（历史本机证据：`D:/JianyingHeadless/integrations/native-color-param-controls-20261028/color-param-qt-meta-locations.json`，未随源码分发）。静态 decoder 从已经检查的旧脚本复制到独立目录，不执行 DLL。
- `新旧模型RTTI/vtable`（历史本机证据：`D:/JianyingHeadless/integrations/native-color-param-controls-20261028/curve-rtti-vtables-static.json`，未随源码分发）、`真实派生视图RTTI/vtable`（历史本机证据：`D:/JianyingHeadless/integrations/native-color-param-controls-20261028/curve-derived-rtti-vtables-static.json`，未随源码分发）。
- `handler列表字段getter`（历史本机证据：`D:/JianyingHeadless/integrations/native-color-param-controls-20261028/adjust-list-bindings-static.json`，未随源码分发）、`普通曲线槽dispatch`（历史本机证据：`D:/JianyingHeadless/integrations/native-color-param-controls-20261028/curve-public-handler-dispatch.json`，未随源码分发）。
- handler 既有完整metadata和通用槽：`hsl-qt-decoded-static.json`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/hsl-qt-decoded-static.json`，未随源码分发）、`hsl-qt-handlers-static.json`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/hsl-qt-handlers-static.json`，未随源码分发）。
- 新提取资源清单：`adjust-qml-extracted.json`（历史本机证据：`D:/JianyingHeadless/integrations/native-color-param-controls-20261028/adjust-qml-extracted.json`，未随源码分发）。来自磁盘 qCompress/raw Qt资源，没有窗口检查或UI树自动化。

## 当前 owner / selection 必须沿用现有绑定

复用 [engine/live_editor/color.py](../../engine/live_editor/color.py) 的 `prepare_controls`：当前 video segment →真实选中对象→当前 inspector 的 `adjust` tab→`VideoAdjustSettingViewModel`→实际 `AdjustSettingHandleViewModel`。不要全进程找到相同类就选第一项。

静态指纹和既有绑定条件：

| 项目 | 固定构建字段 / 指纹 |
|---|---|
| 当前 outer model | `outer+0x30` 是 settings，`outer+0x40` 是 handle；现有实现核验 settings 选中segment ID与目标一致 |
| handler vtable | `VECreator base+0xbfef5b0`，其 `+0x10` VENotifyListener子对象为 `base+0xbfef610` |
| 色彩页加载 | `prepare_controls(...,load_resources=True)` 已有实际加载流程；曲线 QML 以 `isAdjustMergeResourceLoaded` 为正常显示门槛，不能伪造该 ready 属性 |
| 项目一致性 | 读取前后同 draft/session/token；任何native调用前刷新并重做绑定，不能沿用上一个草稿的pointer |
| QObject寿命 | 对所读 pointer核对 vtable、QObject private backlink；只有当前owner链中存在的对象可被当作typed参数 |

进入基础/曲线子页可按已发布 QML 的普通 `onCurTabChanged(QString key,QString reportName)`，分别为 `("base","基础")`、`("curve","曲线")`；这只是相应正常模式初始化/面板选择，不等于参数已修改。该槽本身不需要鼠标键盘。

## 色温、色调滑杆：精确布局、范围与提交

### 列表和数据布局

Qt6 `QList<T*>` 在该构建是三个8字节字段：`{ref_header,data_pointer,count}`，**不是std::vector的begin/end/capacity**。列表项 stride 8，`item_i=read_ptr(data_pointer+8*i)`。复制getter会给header加引用；只读Reader不应手动增减引用或调用它。

| handler字段 | 类型与用途 | 原生getter dispatch |
|---|---|---|
| `+0x58/+0x60/+0x68` | tintAdjustList 的header/data/count | `0x30fa8c0` |
| `+0x70/+0x78/+0x80` | lightnessAdjustList 的header/data/count | `0x30fa922` |

`官方基础页QML`（历史本机证据：`D:/JianyingHeadless/integrations/native-color-param-controls-20261028/adjust-qml-8e60aeb.qml:1042`，未随源码分发） 把 tintAdjustList[0] 设置为蓝→黄渐变，[1]为绿→紫渐变，均交给 `ParamSettingSliderViewEx`；[2]/[3]是其他项目，不能把整个 tint list 都视为白平衡。实际程序应同时核对 slider 的 propertyType/text，避免只凭位置猜参数。

`ParamSettingSliderData` vtable 为 `base+0xb4a3ed8`；完整`slider metadata及字段getter`（历史本机证据：`D:/JianyingHeadless/integrations/research-native-color-audio-20261028/local-color-evidence/lut-gui-binding-exact-static.json`，未随源码分发）已被现有LUT入口使用。

| item偏移 | 类型 | 含义 |
|---|---|---|
| `+0x10` | QString | text |
| `+0x28` | QString | propertyType（用于识别参数/关键帧类型） |
| `+0x40` | QString | constantMaterialId |
| `+0x58/+0x59/+0x5a` | bool×3 | enabled / visible / isMix |
| `+0x60` | double | curValueUI |
| `+0x68/+0x70` | double×2 | minSliderValueUI / maxSliderValueUI |
| `+0x78/+0x80` | double×2 | minEditValueUI / maxEditValueUI |
| `+0x9c` | int | 原生effect/meta type；**不是**可凭枚举名称随意推定的范围 |
| `+0xa0/+0xa8` | double×2 | 最小 / 最大native参数 |

**范围必须读当前已绑定item。**基础类构造器 `0x3071f80` 默认UI0..100/native0..1，但只是未配置的通用初值；不能把它称为色温/色调真实范围。`官方滑杆QML`（历史本机证据：`D:/JianyingHeadless/integrations/native-color-param-controls-20261028/adjust-qml-8e02822.qml:27`，未随源码分发）明确把每个item自己的slider/edit范围绑定给控件。色温不应直接当Kelvin，色调也不应直接当RGB增益。本轮仅静态研究，没有伪造当前实例的实际数值读回。

原生 `onValueChanged` 在 `0x379f6c4..0x379f7cc` 比较UI/native两端：近似相等时直接取UI值，否则作线性映射：

```text
native = minNative + (ui-minEditUI)/(maxEditUI-minEditUI)*(maxNative-minNative)
ui = minEditUI + (native-minNative)/(maxNative-minNative)*(maxEditUI-minEditUI)
```

实现内部还有浮点近似比较；项目侧应先读有限数、确认两范围非退化，并把请求UI值限制在当前有效edit范围。不可固定除100后再传UI槽，从而二次归一化。保存后的真实 `materials.effects` 中 `type=temperature/tone` 的 value 应与映射值相符，保持当前材料ID/refs/资源，不把UI对象改变当验收。`完整通用提交函数`（历史本机证据：`D:/JianyingHeadless/integrations/native-color-param-controls-20261028/color-static-0x379f650.txt`，未随源码分发）。

### 普通Qt槽与 record

```text
AdjustSettingHandleViewModel.onValueChanged(
  ParamSettingSliderData* commonSliderInfo,
  double value, bool withShift, bool bRecord)

同名5参数版本最后还有 QString action_type；4参数版本由Qt自动生成的默认参数克隆，内部构造空action_type后调用同一实现。
```

Qt metacall case `0x30f98ef` → 真实实现 `0x379f650`。现有typed桥可用与LUT完全相同的pointer exact-type方式，后接 `double ui, bool false, bool true`，4个参数，不扩ABI。不要改成向item的Qt property写数值。官方QML `onValueChanged`（连续调整）传 `bRecord=false`，`onAccepted`传 `bRecord=true`；最终一次直接提交可走accepted分支，不需要伪造拖动事件。`原始QML调用`（历史本机证据：`D:/JianyingHeadless/integrations/native-color-param-controls-20261028/adjust-qml-8e02822.qml:62`，未随源码分发）。

`0x379f650` 的UI回写之后还走真实效果提交；通用effect支路在 `0x379fd8d..0x379fe07` 组装effect数据并携带 bRecord 进入 `0x37ace50`。后者对已选片段/参数做处理，并在record分支建立提交/历史回调，不能跳过前面的参数转换只调用它。静态证据：`0x37ace50`（历史本机证据：`D:/JianyingHeadless/integrations/native-color-param-controls-20261028/color-static-0x37ace50.txt`，未随源码分发）。真正undo/redo/save/output仍需主线程实际验收。

## 曲线当前对象链和模式

| 字段 | 布局 / 含义 | 静态证据 |
|---|---|---|
| handler `+0xe4` | int colorCurvesEnableState；On=0/Off=1/Mix=2 | getter `0x30faa93`，基类enum metadata |
| handler `+0xe8/+0xf0/+0xf8` | QList<AdjustColorCurvesData*> header/data/count，stride8 | getter `0x30faaa0` |
| handler `+0x100` | int currentSelected | 已发布handler属性/通道选择链 |
| handler `+0x104` | bool allSelected | resetColorCurve的真实分支 |
| handler `+0x124` | ColorCurveEnableMode | getter `0x30fabac`：OldRgba=0、HueSat=1、NewRgba=2、HueSatAndNewRgba=3 |
| color data vtable | `base+0xb4a41d8` | RTTI与getter |
| color data `+0x10/+0x11` | bool chromaPicking/isColorCurvesMix | metadata getter `0x30f6902/0x30f690d` |
| color data `+0x18/+0x20` | 旧 AdjustColorCurveCoordinateViewModel* / 新 BezierCurveCoordinateViewModel* | getter `0x30f6918/0x30f6924` |
| color data `+0x40` | QString title | getter `0x30f695a` |
| color data `+0x68` | int channel type | 新旧数据初始化与reset读取 |
| new VM vtable / channel | `base+0xbfee320`；`+0x30`为构造器保存的channel | `构造器0x377ad40`（历史本机证据：`D:/JianyingHeadless/integrations/native-color-param-controls-20261028/curve-vm-constructor-0x377ad40.txt`，未随源码分发） |
| old VM vtable | `base+0xc014268` | 完整RTTI |

QML `新RGB页`（历史本机证据：`D:/JianyingHeadless/integrations/native-color-param-controls-20261028/adjust-qml-8e5ece3.qml:468`，未随源码分发）给定四个列表索引：0=亮度/master，1=R，2=G，3=B。每个视图从本列表项的 `bezierCurveCoordinateViewModel` 获取模型。正常编辑需要 list项channel、model channel、目标保存材料 `materials.color_curves` 对应；数据混合（isColorCurvesMix）或多选时不能按单视频方案处理。

下列是**现有普通Qt方法**，确切签名从metadata解码，方法地址从metacall dispatch而不是相似字符串推测：

| 方法 | 实现RVA | 实际作用 |
|---|---|---|
| `setColorCurvesViewIndex(bool allSelect,int currentIndex,bool updateStatus)` | `0x37aa0d0` | 当前曲线通道/显示状态选择；默认参数克隆2参数版本将updateStatus设false |
| `activateCurveByIndex(int index)` | `0x3794130` | 激活通道；保留当前allSelected状态，不保证切成单选 |
| `resetColorCurve(AdjustColorCurvesData* pData)` | `0x37a5f60` | 正常重置相应曲线；有“全部选择”转重置全部的分支 |
| `resetAllColorCurves()` | `0x37a5790` | 正常重置全部 |
| `setColorCurvesEnable(bool bEnable)` | `0x37a9b50` | 正常曲线开关，走普通提交，不直接改属性缓存 |

**只改一条时的范围陷阱：**`resetColorCurve` 发现allSelected=true且当前模式为new(2/3)会调用resetAllColorCurves。应先正常 `setColorCurvesViewIndex(false,index,true)` 并回读 `allSelected/currentSelected`，然后把当前列表项指针传reset；仅调用activate不够。重置内部修改真正曲线数据，再进入 `0x37a1860` 提交流程。完整`reset函数`（历史本机证据：`D:/JianyingHeadless/integrations/native-color-param-controls-20261028/color-static-0x37a5f60.txt`，未随源码分发）、`提交函数`（历史本机证据：`D:/JianyingHeadless/integrations/native-color-param-controls-20261028/color-static-0x37a1860.txt`，未随源码分发）。有记录入口不等于本轮已经实测历史成功。

## 为什么点/控制柄没有现成普通Qt setter

新 `BezierCurveCoordinateViewModel` 完整metadata只有7个方法：6个signals（curveHoveredChanged、insertBezierControlPointSignal、bezierControlPointChanged、flushBezierControlPointSignal、insertPresetColorPointSignal、resetBezier），外加普通 `updateHoverState(bool)`。唯一property是curveHovered。`bezierControlPointChanged(LVVEColorCurvesType,CurvePointControlType,bool record)` 是**通知**，不接收新坐标，真实实现 `0x31304b0`只是Qt activate。旧 model 完整metadata仅3个signals且无property。两者RTTI均直接继承QObject，因此不是漏掉某个含点setter的业务基类。

基类 `BezierCurveCoordinateView` 完整metadata存在private slot `onInsertControlPoint(double x)`，metacall `0x3109697` → `0x3535a40`，检查x在0..1后经真实派生view的vtable `+0x178` 插入。对应 `RgbaNewCurveCoordinateView` vtable为 `base+0xbfbb328`，该槽派发至 `0x3537f80` → `0x3533cb0`。**基类本身该vtable槽是占位，不能把基类地址/offset拿来猜调用ABI。**派生类复用基类Qt metadata，没有新增普通坐标setter。

`新派生插点函数`（历史本机证据：`D:/JianyingHeadless/integrations/native-color-param-controls-20261028/curve-derived-insert-RgbaNewCurveCoordinateView.txt`，未随源码分发）、`实际插点处理`（历史本机证据：`D:/JianyingHeadless/integrations/native-color-param-controls-20261028/color-static-0x3533cb0.txt`，未随源码分发）。插点只有x，没有(y,left,right)；它最多用于沿当前曲线增加点，不应称为完整曲线参数控制。仅发changed/flush通知也没有新坐标来源，不构成真实编辑。

`ColorCurveCoordinate QML`（历史本机证据：`D:/JianyingHeadless/integrations/native-color-param-controls-20261028/adjust-qml-8e6059d.qml`，未随源码分发）只装载绘制view并展示只读tips；未发现额外数值输入框调用一个隐藏的坐标setter。`tipX/tipY/tips`在metadata本身为只读派生显示属性，也不应被当成锚点编辑字段。

该结论限制为：**这些当前绑定的新旧模型、视图、handler已发布的普通Qt入口没有完整坐标setter。**不外推为整个剪映绝无内部编辑函数；内部绘制/鼠标处理函数确实存在，但本轮不改ABI、不构造输入事件，也不允许内存改坐标后发信号伪装编辑。

## 建议主线程的最小真实验收

1. 在独立测试草稿绑定当前video，读取白平衡两item的实际UI/native范围、type/text、混合状态，与保存temperature/tone值互相验证。保留目标native值及反算UI值，分别只改一项，accepted=true，保存/undo/redo/导出，固定其余调色。
2. 对曲线已有非恒等形状，先单选通道，再做普通resetColorCurve；验证保存仅目标通道变恒等，其他通道/素材/ID不变，完成undo/redo和输出差异。这只验收重置功能。
3. 任意锚点/柄保持“原生草稿可持久化和渲染，但当前普通Qt实时编辑未接通”的准确分级。不要用离线覆盖重开、直接属性缓存或发通知信号填补证据。

本轮交付的是精确静态绑定和安全调用条件，不包含新的native修改成功声明。
