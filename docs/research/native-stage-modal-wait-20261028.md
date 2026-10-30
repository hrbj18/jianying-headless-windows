# 原生新草稿打开等待：磁盘空间确认框

2026-10-28。只读研究：读取现有 PSS/unwind 证据、安装 DLL 的 PE/Qt metadata 和原生 QRC 资源；未使用 computer use，未附加/写入目标进程，未调用 getter、setter、edit、close 或其它 mutator，未改 bridge、engine 或官方 DLL。

## 结论

**本次打开请求卡在剪映正常的“磁盘空间不足”模态确认中，打开调用还没有返回。** 这不是仅根据 `QEventLoop::exec` 猜测：实际 unwind 返回地址、上层检查函数的源日志、原生文案键与官方 `LVAlertDialog.qml` 资源已闭环。

可读的现有对话对象位于 VECreator 全局弱引用的对象字段 RVA **`0xee94ce8`**，旁边 `0xee94ce0` 是引用控制块。应由主线程既有只读 Reader 先验证 PID/birth、模块基址、对象存活及实际 Qt metadata，再读 `mainText`、`subText`、`confirmBtnText`、`cancelBtnText`、`confirmedClose`、`deleteOnClose`、`visible`、`showable` 等属性。

**原生正常取消入口是对这个已确认的 alert Window 执行正常 `close()`，让 `onClosing` 发出既有 cancel 回调；不应只退出内部 QEventLoop 或伪造完成信号。** 本报告只定位，不执行。普通 pipe worker 已同步等待打开时，不能重发打开或把另一次请求超时当作未执行；当前尚未找到可绕开该占用、已经验证的官方外部 dialog 回应接口。

腾出空间可以消除下一次检查的根因，**不能据此声称当前提示会自动消失**。本次检查先同步比较一次空间，随后进入独立 alert 的事件循环；其真实 QML 没有磁盘监听或空间复检 Timer。主线程报告 D 盘约124MB、C盘约28GB，与提示相容；此磁盘余量不是本子研究实测。

## 实际栈与身份

主线程提供的证据：`stage-timeout-unwound-stacks.json`（历史本机证据：`D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1/stage-timeout-unwound-stacks.json`，未随源码分发）。目标 PID `26164`，birth `134375592292885847`；主线程 TID `26480`。PSS 快照后通过 dbghelp 真 unwind 得到：

```text
QEventLoop::exec
  VECreator return RVA 1da957a
  19030d5 → 1903a3e → 55eba76 → 55fe300
  Qt signal activation
  4e9328a → 535c9d8 → 4efa876 → 4e75203
  QMetaMethod::invoke → existing bridge
```

DLL 没有完整私有符号，dbghelp 的最近公开 symbol 名及很大的 displacement 不能当真实函数名。例如栈中 `CCFilter::getCoveringRelation + 0x18b82a` 不说明滤镜在阻塞；本报告按精确 RVA 和 PE `.pdata` 函数边界解释。

目标：`D:\刘宇钊\软件\剪映\JianyingPro\11.4.7.14462\VECreator.dll`，275,234,072字节，SHA-256 `769c33961ef9d7e471e583f03c975be975b0c35e849a767690d09e9f2fc45111`。下文 VECreator 地址均为 RVA；preferred base `0x180000000` 不能代替运行时基址。

`QEventLoop::exec` 本身只是启动本地事件循环，需要上层证据才能证明模态含义。[Qt 官方说明](https://doc.qt.io/qt-6/qeventloop.html#exec)。

## 原因闭环与精确文案

| 原生位置 | 已读取的行为 |
| --- | --- |
| `0x55fded0`，栈返回 `0x55fe300` | `VEMainWindowController::showMainWindowOnOpenProject`；正常打开路径在 `0x55fe2fb` 调用 `0x55eb790` |
| `0x55eb790`，返回 `0x55eba76` | 对草稿路径做空间检查；不足时构造标题、正文、确认/取消文案，调用同步提示 helper `0x19031c0` |
| `0x55ec500` | 日志名 `VEMainWindowController::checkFreeSpaceByPath`，比较实际可用MB与 `controller[+0x300] * 1024` |
| `0x19031c0`，返回 `0x1903a3e` | 将 `mainText/subText/confirmBtnText/cancelBtnText/showable` 写入参数 map，调用 `0x1902bc0` |
| `0x1902bc0`，返回 `0x19030d5` | 源字面量 `showBlockingAlertDialog...`，构建真实原生 alert，设置 `deleteOnClose=false`，连接结束回调，进入局部 QEventLoop |

文案来自同一安装包 `Resources/po/zh-Hans.po`：

| 键 | 官方中文 |
| --- | --- |
| `pc_insufficient_disk_space` | 磁盘空间不足 |
| `pc_insufficient_disk_space_and_clear` | 磁盘空间不足，可能会出现数据丢失、播放卡顿、保存失败等问题，请尽快清理磁盘空间 |
| `main_still_continue_n` | 仍要继续 |
| `cancel` | 取消 |

四个键均直接在 `0x55eb790` 内加载，分别成为标题、正文和两个按钮，不是从附近无关字符串推测。

检查所需阈值来自当前 controller 的 double `+0x300`；构造函数先初始化为-1，之后配置可能覆盖。不能仅凭旧机器行为猜固定1GB。已经存在的 `VEMainWindowController*` 位于 singleton 槽 RVA **`0xef43a10`**。getter `0x55e6890` 在空时会创建 controller，不应为了发现对象调用它。当前阈值应由主线程只读核对，不能改阈值绕过正常检查。

`checkFreeSpaceByPath` 对无效路径或磁盘未准备好会记录另一条日志并返回 false；当前已实际走到不足确认分支，因此不是该无效路径返回分支。可用空间查询的单位在底层转换为MB，日志模板明确为 `required %lf MB, available %lf MB`。

## 真实资源与正常取消链

同步 helper 的工厂 `0x1900ef0` 使用路径 **`qrc:/FusionUI/src/window/LVAlertDialog.qml`**。资源属于独立 `FusionUI.dll`，不能用 VECreator 内同形状的其它 Alert QML 代替它。

FusionUI DLL：2,403,352字节，SHA-256 `f44c38192107ce355b6b16c264c3244186071a973cfaa06483112648ab4874f4`。其 RVA `0x1580` 调用 `qRegisterResourceData` version3，tree=`0x1f2050`、names=`0x1f0b50`、data=`0x15e540`。依据 [Qt 6.2.2 官方 QResource 实现](https://github.com/qt/qtbase/blob/v6.2.2/src/corelib/io/qresource.cpp) 按22字节 tree record 解析，node23 精确路径就是 `/FusionUI/src/window/LVAlertDialog.qml`，payload文件偏移 `0x16023d`。解压后6,087字节，SHA-256 `2cb5f41118bbccd0a511fb1f6ffd43f1199134958634213517dd5bd95a82f4db`。

层级为 `LVAlertDialog → LVModalDialog → LVWindow → QtQuick.Window`，Windows 的 `LVModalDialog.modality` 为 `Qt.WindowModal`。

已从这一个准确资源确认：

- `onClosing`：当 `confirmedClose=false` 时发 `cancelBtnClicked()`，然后恢复 `confirmedClose=false`。
- `onAttemptClose`：当未确认时设置 `confirmedClose=true` 并发同一个取消信号，用于正常关闭被拦截的情形。
- 取消按钮正常处理顺序：设置确认关闭标记，执行 `close()`，然后发取消信号。普通关闭事件则自动在 `onClosing` 走取消回调。
- 确认按钮有独立的关闭及确认信号路径。“仍要继续”是显式选择，不等于清理空间自动完成。
- 资源中无磁盘空间监听、Timer 或自动复检逻辑。

因此正常 `QWindow.close` 对这一个已验证、未完成确认的 alert，是取消其正常动作的入口。调用者不要先改 `confirmedClose`，也不要调用 `realClose()`、写 `visible=false`、直接析构或直接 `QEventLoop.quit()` 代替正常取消。

工厂 `0x1900ef0` 还证明了两个信号接线：

```text
root.confirmBtnClicked() → DialogEventListener.onConfirmBtnClicked()
root.cancelBtnClicked()  → DialogEventListener.onCancelBtnClicked()
```

`DialogEventListener` 是 QObject，其构造的 parent 为当前 alert root，可作为已知对象关系核对线索；本报告未扫描进程。其 metadata：

| 条目 | VECreator RVA |
| --- | --- |
| primary vtable | `0xa569680` |
| static Qt meta | `0xa178510` |
| static metacall | `0x1954b10` |
| local0 `onConfirmBtnClicked()` | `0x1a2b690` |
| local1 `onCancelBtnClicked()` | `0x1a2b530` |

取消槽只调用当前 listener 已绑定的 `std::function`（`+0x88`）；它本身不关闭窗口。因此直接调该槽不足以证明模态结束，完整正常关闭链更合适。local index 不等于包含 QObject 基类的全局 method index；不要猜 ABI 或直接用上表地址调用。

## Pipe 占用、外部 SDK 与恢复边界

主线程已知 bridge worker `24504` 同步等待 `onOpenProjectBtnClicked`，状态 `executed=0`。该字段表示桥尚未完成返回，**不表示打开没有进入原生代码**；真实 unwind 已经证明它在正常打开的同步提示里面。

本轮只读检查了现有 `engine/lyra_commands.json` 195项命令，未发现全局 alert answer、modal close 或普通应用窗口控制命令；`draft blueprint cancel` 只取消 blueprint apply，不能当作取消这个对话的入口。也未在已有 Python/桥公开入口中找到已验证的外部弹窗回应路由。这是有界搜索结果，不能声称剪映绝无内部 IPC。

如果当前 pipe 不再接受第二连接，不能靠重发同一或另一打开请求解除模态，也不能为此修改 bridge/DLL。主线程若另有已经验证、可投递到同一 GUI 线程的原生接口，应先读取准确 alert 对象与文本，再用正常 `close()` 取消；本报告没有建立这个独立投递渠道。

正常取消后应确认原打开调用终于返回、其原业务请求审计落定、该 alert 引用清除或不再显示，再读取当前会话。编辑模型暂缺、project manager counts为0/0都不能单独作为“操作已停止”的证据。清理空间后是否重新尝试，是主线程在明确前次终态后重新判断的下一步，不能在未明状态中重放。

## 保存的证据及未确定项

静态证据根目录：`D:\JianyingHeadless\integrations\native-stage-modal-research-20261028`。

- `stack-functions.json`：九个实际栈返回地址对应的 `.pdata` 边界。
- `VECreator-0x55eba76.txt`、`VECreator-0x55ec500.txt`、`prompt-strings.json`、`prompt-more-strings.json`：空间判断与文案。
- `VECreator-0x19030d5.txt`、`VECreator-0x1903a3e.txt`、`VECreator-0x1900ef0.txt`：同步提示、全局弱引用及信号接线。
- `FusionUI-0x1580.txt`、`read_fusion_resources.py`、`fusion-ui/resource-path-proof.json` 与该目录的 `LVAlertDialog.qml`、`LVModalDialog.qml`、`LVWindow.qml`：准确资源路径与正常关闭链。资源只解压到研究目录，未修改安装包。
- `DialogEventListener` metadata/vtable 和实现原始输出保留在同目录。

仍未由本子研究确定：当前进程中 alert 的确切地址和属性值、当前阈值、独立于被占用 pipe 的正式投递通道、正常取消后的真实业务终态。VECreator 的部分 IAT 由 gpShell 保护，未恢复的导入不能随意命名；本报告不把静态接线推断写成已观察运行。
