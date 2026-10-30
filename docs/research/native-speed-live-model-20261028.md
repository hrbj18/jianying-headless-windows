# Windows 11.4.7 曲线变速：当前编辑会话的原生 Qt 模型

日期：2026-10-28。本研究只读取本机精确安装包、旧元数据和当前进程。没有调用编辑方法，没有修改 engine、草稿或原生桥，没有 computer use。主线程正在进行的渲染与编辑验收不由本报告代替。

证据根：`D:\JianyingHeadless\integrations\speed-research-20261028\live-model`。
绑定 DLL：`VECreator.dll` SHA256 `769c33961ef9d7e471e583f03c975be975b0c35e849a767690d09e9f2fc45111`。下文 VA 均为 PE 静态首选基址 `0x180000000` 下的地址，实际使用须按已验证模块基址重定位。绝不缓存本报告里的运行时对象地址作为未来操作目标。

## 视频对象到速度模型的确切绑定

`MainTimeLineSegmentVideoViewModel`：Qt metadata `0x18a82ee30`，qt_static_metacall `0x1820831f0`。

- local property 64：`speedControlViewModel`，类型 `MainTimeLineSpeedControlViewModel*`。
- local method 150：无参 getter `speedControlViewModel()`。
- local method 151：`setSpeedControlViewModel(MainTimeLineSpeedControlViewModel* newSpeedControlViewModel)`。
- **`newSpeedControlViewModel` 只是 setter 的参数名，不是第二个属性或新版模型。**

getter `0x182539f00` 的只读路径证实：

1. `video+0x660` 是 QPointer 控制块；指针存在且 `int(control+4) != 0` 才读取对象。实际观察为 `-1`，不能改成 `>0`。
2. `video+0x668` 是实际速度 VM 指针。
3. 实际 vtable 必须等于 `VECreator base+0xac59560`。

setter `0x182535d10` 也只读／写这两处 QPointer 字段，进一步确认对应关系。不要为了得到 QObject* 返回值而把已有 Qt 桥的 bool/double 返回类型乱用成指针。

纯 Reader 观察的当前会话：pid 26164、birth 134375592292885847、active timeline `0x7165a6f0`，video `0xba3ad5d0` → VM `0x419e5620`，vtable 和 RTTI `MainTimeLineSpeedControlViewModel` 均匹配。读取前后以当前 video 的 `+0x298` timeline 和进程 birth 核对，不扫描任意对象后猜目标。完整记录：`current-speed-bindings-readonly.json`。

## 正常初始化入口

旧元数据已有精确 `MainTimeLineCanvasViewModel.activeSpeedControl(bool active,bool needSync)`：local method 125；local method 126 是单 bool 重载，其第二参数默认 true。

静态路径：

`Canvas Qt metacall 0x182071ee0 → local125 case 0x182072a4e → wrapper 0x182333b30 → canvas+0x1d8 的当前模型 → 0x182286860`。

实现遍历 canvas model 的已选择片段列表（`+0x6e0` / `+0x6f0`），按真实 Qt metadata cast 为视频模型，再调用 `0x18251bc80`。后者在原生 visible 由 false 进入 true 时，从该片段真实 speed 材料取得数据，调用 `0x1824b7100` 填充速度 VM 区间；随后按 needSync 同步检查器。

因此应先复用已有 `live_editor.v02.select(editor,obj)` 选中明确目标，再通过当前已绑定 `ctx['canvas']` 的 typed Qt 接口正常激活。**直接写 VM.visible 只改标记并发 notify，不能替代这条初始化路径。** 同样不要通过改磁盘文件、重开工程来冒充当前页同步。

本研究先观察到 VM.visible=false、items=0；主线程正常初始化后，再次纯 Reader 观察到 visible=true、speedMode=1、avgSpeed=1.5、items=2。此为观察结果，不是本研究偷偷执行了初始化。证据：`speed-native-data-readonly.json`、`speed-intervals-readonly.json`。

## 区间列表与 getter

根模型：`MainTimeLineSpeedControlViewModel`，vtable RVA `0xac59560`，metadata `0x18a8087f0`，metacall `0x182065d20`。

| 字段 | 已确认布局 |
|---|---|
| 当前区间 QList | `vm+0xa8` header，`+0xb0` data 指针，`+0xb8` count，三元组共 24 字节 |
| 当前列表元素 | `data+i*8` 是单项 VM 指针，stride 8 |
| 操作前基线 QList | `vm+0xc0` header，`+0xc8` data，`+0xd0` count；无编辑时可为空 |
| 单项 VM vtable | RVA `0xac59500`，类型 `MainTimeLineSpeedControlItemViewModel` |
| 单项 index | item `+0x10`，int |
| 单项 avgSpeedValue | item `+0x28`，double |
| 单项 startSpeedPoint | item `+0x30`，QPointF，连续两个 double x/y |
| 单项 endSpeedPoint | item `+0x40`，QPointF，连续两个 double x/y |
| 单项 gradient | item `+0x50`，double，Qt property 8，元数据类型 double |

当前只读实证：

| interval | start | end | avg | gradient |
|---|---|---|---|---|
| 0 | (0,1) | (.5,2) | 1.5 | +0.35714285714285715 |
| 1 | (.5,2) | (1,1) | 1.5 | -0.35714285714285715 |

读取 QList 需检查 count 合理、数据区可读、列表头前后不变、每项 vtable 正确及当前会话不变。字段仅适用于上述精确指纹，不要据此泛化其它构建。

## 原生区间斜率 API 的语义

根模型 Qt 可调用方法：

| local index | 方法 | 实现 VA |
|---|---|---|
| 17 | `dragGradientStarted(int index,double gradient)` | `0x1824b07e0` |
| 18 | `dragGradientChanged(int index,double gradient)` | `0x1824b0240` |
| 19 | `dragGradientFinished(int index,double gradient)` | `0x1824b0630` |

这是原生数据模型的方法调用，不包含操作系统输入事件或屏幕坐标。若主线程将其封装为明确的 `curve-gradient(interval,value)`，仍须遵守当前会话、暂停、精确目标、命令日志、保存回读及不确定结果不重放等规则。

**gradient 为绝对目标值，不是增量，也不是直接速度。** `Changed` 从 Started 时的基线区间取平均速度 m，以已安装数据边界 0.1 和 10 计算可调幅度 `D=min(m-0.1,10-m)`，以传入 gradient 计算一侧速度 `m-D*gradient`，再调用原生 CurveSpeedUtils 计算另一侧。当前 m=1.5、start=1 的 `gradient=(1.5-1)/(1.5-.1)=0.357142857...` 与真实内存完全吻合。

因此输入 `0.2` 表示目标斜率 0.2，不要把原 gradient 再加上 0.2。公开封装应限制有限数值及 [-1,1]；本报告不声称原生函数替调用者完整验证了越界输入。开始／改变／结束必须属于同一明确请求，只有结束后保存验证通过才能报告完成。

`Started` 先校验区间索引、保存当前 index，设置原生编辑状态；`Changed` 要求索引与开始一致、current 与 baseline 列表都含该项，否则直接返回；`Finished` 清理选择与编辑状态、排空更新，再进入 `0x1824b2d70` 正常结束路径，报告标签为 segment_slope。该静态路径支持“正常模型提交”的预测，但 **undo/save 与最终 curve_speed 必须实测，不能靠这些名字推导成功**。

验收要求：保存后 mode 仍为 1、自定义 id 与点横坐标仍有效、至少有速度点改变，且原生导出实际帧序发生对应变化；再 undo/redo 核对恢复。若只改模型显示字段或 method 返回而主时间线没变，即判失败。

## 不宜用 updateAvgSpeed 代替曲线编辑

`updateAvgSpeed(double)` 是 local method 16，真实入口 `0x1824b6830`。它确有暂停外的速度／片长边界和正常 VIDEO_SPEED action 路径，但不能由名称推断其等比缩放曲线。

在当前视频路径，它经 `0x1824b4640` 分派到 `VideoSettingsData` 虚函数 `+0x68 = 0x183017460`，构造 VideoService.updateVideoSpeed。action 参数里 `+0x118` 被明确写 0、`+0x120` 为请求 speed，曲线 name/resourceid/points 为构造器默认空值。这与普通模式参数形状相符，存在清除曲线／回到普通速度的明确风险。主线程已决定不使用它作为曲线可编辑性证明。

另需区分：VM `+0x20` 是 UI speedMode；VM `+0xd8` 指向的内部 wrapper `+0x20` 区分 video/audio 分派，不是曲线模式。把二者混用会错误解释当前绑定。

## 独立源时间映射参考

曲线数据模型数学见前一报告，以下以独立的基本积分重新表达，未搬运整段私有函数：相邻速度点区间内，用归一化横坐标 `[0,.2049,.7951,1]` 和速度差比例 `[0,.1,.9,1]` 定义三段线性速度；每段积分用梯形面积加部分段二次面积即可。对 `(0,1),(.5,2),(1,1)`、4 秒目标／6 秒源：

| 目标秒 | 曲线对应源秒 | 恒定 1.5× 对应源秒 |
|---|---|---|
| 0 | 0 | 0 |
| .5 | .532267045 | .75 |
| 1 | 1.19755 | 1.5 |
| 1.5 | 2.032267045 | 2.25 |
| 2 | 3 | 3 |
| 2.5 | 3.967732955 | 3.75 |
| 3 | 4.80245 | 4.5 |
| 3.5 | 5.467732955 | 5.25 |
| 4（理论终点） | 6 | 6 |

独立数学程序 `source-map-reference.py` 与输出 JSON 在研究根。最终帧位置还涉及帧量化与解码帧选取，不能直接把浮点理论时刻当作精确像素 hash；可用带源帧编号的实际渲染对照验证，终点不作为越界 seek 请求。

## 保存的静态资料

- `speed-meta-locations.json`、`speed-meta-decoded.json`：元数据位置、方法参数、属性类型。
- `speed-vtables.json`：RTTI/COL 解析出的 vtable 与多继承 offset；不把后续非函数数据当 vtable 方法。
- `video-speed-getter-and-commit.txt`：视频 QPointer getter/setter 与结束路径。
- `active-speed-case.json`、`active-speed-wrapper.txt`、`active-speed-implementation.txt`、`video-activate-speed-control.txt`、`speed-control-data-initialize.txt`：正常初始化链。
- `speed-metacall-cases.json`、`speed-control-handlers.txt`、`gradient-save-helpers.txt`：区间斜率方法与元数据交叉核对。
- `average-speed-mutation-and-submit.txt`、`video-settings-update-speed.txt`、`video-speed-action-constructor.txt`：平均速度方法的模式风险。

所有反汇编均以已有只读 PE/LLVM 工具针对精确地址生成，没有调用目标函数或修改目标进程。公开的 Qt 方法签名、程序字段与静态调用路径仍需由主线程的实际保存／出片验收完成最终证明。
