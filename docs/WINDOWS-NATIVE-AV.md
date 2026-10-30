# Windows 高级画面与声音：实际验收状态

更新于 2026-10-28。本轮目标仍未整体完成。所有试样通过现有项目、同一 .venv 与本机剪映
11.4.7.14462 制作；没有 computer use，没有修改原生 ABI、桥 DLL、官方 DLL 或其既有指纹。
原用户 R4 未被这些独立验收草稿覆盖。

## 已验证与尚待验证

| 能力 | 原生实际效果 | 原生编辑页继续修改 |
|---|---|---|
| 自定义速度曲线 | 同平均速度对照中120帧有112帧源时刻不同，最大差10源帧。 | 已修改斜率、撤销、重做、保存并再次出片。范围0.1..8x、目标时间归一化控制点、静态片段变换；光流和曲线叠加片段动画不在本次通过范围。 |
| HSL | 八色饱和度-100实际出片严格灰度。 | 红色饱和度已原生修改、撤销/重做、保存并重导；实际画面有差异。 |
| 色温、色调 | 30秒实拍中两个独立片段的实际native值.1/-.03；原生未编码取帧MAD1.553/.293。 | 正常双滑杆修改、原生完整历史、保存与重导通过。亮度/RGB Bezier计划可出片；任意锚点/柄实时setter仍未接通。 |
| Primary色轮 | 独立lift.red=.25与无调色对照MAD13.237。 | .25→.08原生修改、undo/redo完整语义指纹、两状态保存重导已通过；两状态像素MAD9.183，已查看实际画面。 |
| Log色轮 | 独立shadow.red=.25对照MAD3.619。 | .25→.05原生修改、undo/redo完整语义指纹、两状态保存重导已通过；像素MAD3.500，已查看实际画面。 |
| EQ、压缩、限制器五参数 | 每项独立改变解码PCM，五项差异RMS依次约.01931/.01511/.02776/.00806/.01391。 | 五项分别修改保存出片；连续5次undo和5次redo恢复完整时间线指纹，追加限制器测试也通过history。重做后PCM差异0。 |
| 实时降噪 | 同一真实语音/已知噪声样例，rate .35的静音底噪降低3.442dB、语音SI-SNR提高.899dB、语音增益变化-.308dB；延迟23.229ms。 | 已正常关闭/开启、完整时间线undo/redo、保存和五状态原生出片。重做前后对应状态的解码双声道PCM逐样本相同。GUI只有开关，切换会变成mode1/全局rate（本机.85）；校准的mode0/.35通过正常undo恢复，不能声称GUI存在rate滑块。 |
| LUT | 原生库/依赖路径/导出复合路径已修复。诊断CUBE的0/.4/1强度，120帧全部有实际变化；自制SDR CUBE的0/1像素MAD6.714。 | 诊断包和自制包均已通过正常强度修改、完整时间线undo/redo、保存和重新出片。自制包实际.55→.6。仅接33³、默认domain、有限SDR值；**不承诺与标准CUBE采样完全等价**，见下文。 |
| 标准LUT33兼容滤镜（实验） | 两组固定来源CUBE保留全部33³节点；144色块对独立FFmpeg浮点参考的full最大误差.862/255。实拍高频边缘仍存在最大46.53/255残差，不能声称整片标准等价。 | 命名版v41已通过正式原生卡片显示/启用条件、.55→.6、完整undo/redo、保存和120帧原生出片；实际raw帧随强度变化。此为独立兼容滤镜，不是原生LUT下拉框，也不是任意CUBE通用导入。 |
| 立体声/瞬态边界 | 原生独立双声道导出、强平台衰减约2.604dB、左右marker延迟均308/44100秒；未折叠为单声道。 | 同源native bypass对照和最终AAC实际测量。-3限制档实测-2.78dBTP，存在0.22dB真峰值超出；这组结果不能当作任意信号的硬真峰值保证。 |

## 公共入口与数据

既有 build plan 的视频段可声明：

```json
"grade": {
  "version": 2,
  "wheels": {"mode": "primary", "lift": {"red": 0.04}}
}
```

Log用mode=log和shadow/midtone/highlight/offset；Primary用lift/gamma/gain/offset。
组件为red/green/blue/luma/saturation，-1..1；intensity为0..1。八色HSL和四条曲线保留在同一grade
接口，具体组合仍须实际审片。版本2冻结已审核调色collection完整资源树。

音频段可声明：

```json
"audio_processing": {
  "studio_chain": {"gain": -2, "frequency": 300, "threshold": -18, "ratio": 3, "ceiling": -3},
  "denoise": {"enabled": true, "rate": 0.2}
}
```

上面只是合法参数例子，不能替代对实际声音的验收。两类别声音链由本项目原创文本配置串联本机
SAMI Compressor、Equaliser、Limiter；未复制付费广播音效内容或其资源ID。EQ两控件与动态三
控件分别属于两个现成原生类别，每节点都有唯一稳定constant_material_id。旧studio五滑杆包
仍可渲染，但其后三项普通UI刷新有槽位限制，不等于新studio_chain的GUI验收范围。

当前页在正常`agent live`入口提供color-controls/hsl、wheel-controls/color-wheel、
audio-controls/audio-dsp、speed-controls/curve-gradient。所有修改绑定真实draft/session/segment
和请求UUID，使用原生撤销/重做保存。没有通过写内存中的滑杆值伪造完成。

新增`lut-library/lut-controls/lut-select/lut-value`。新建LUT工程保留独立CUBE、原生config和
algorithmConfig、feature与Lumi依赖，并登记工程自己的materials/Lut/LutDraft.json。原生
强度动作会替换材质UUID，确认保护实际CUBE和全部其余时间线，而非错误要求旧UUID不变。
原生还可能初始化红色HSL interacting模式；A/B中该标志在非零HSL时产生约.804/255像素差，
因此不能忽略。新建package2计划明确预置此模式；显式false不被覆盖，旧工程未准备时修改前拒绝。

首次LUT调整可能在原生历史栈建立两条记录：资源路径迁移与强度修改。实测一次undo先恢复
强度，再一次undo恢复资源路径，两次后整个原始时间线指纹相等。此前把“第一次undo后路径
仍改变”解释成不可撤销是错误的；不能假设一次公共业务动作只对应一条原生历史记录。
白平衡修改在未完成LUT资源初始化时会在派发前拒绝，让资源迁移成为独立可见步骤。

自定义CUBE的独立参考验收仍未通过：严格identity33在native强度1和0之间MAD1.912；
归一化纹理采样模型的预测误差1.300，拟合斜率约1.03、偏移约-4/255。它与本机3D shader
直接按RGB取样的静态证据一致，但不是完整通用证明。源CUBE保持不变，没有偷偷预扭曲、
烘焙素材、替换shader或放宽此前颜色一致性门禁。自制look可原生继续编辑不等于任意外部LUT精准匹配。

新增独立实验路线使用已固定来源的`resource_candidate: filter-gentle8-v24`或
`filter-nonlinear8-v24`，并显式设置`native_filter_name: 标准 LUT33 兼容滤镜`。
`file`仍须绑定该资源真实原CUBE的SHA；未知名字、任意新包和不匹配CUBE均拒绝。旧计划不加
该字段，其原始材质形状和verify-build继续保持。兼容包使用原生现成采样函数及自有胶水，
不替换官方shader、DLL或默认调色bundle。完整资源同时保存在build内与正常允许的
`User Data/AgentResources/standard-lut33/<tree SHA>`，只允许精确受验包从此路径解析到构建副本。

v28未命名版虽然强度动作、history和出片成功，但真实`filterName=""`，正式QML会隐藏卡片；
不能将其算人工可见控件通过。v41新独立build通过正常材料name启用正式卡片条件，没有改
活动QObject属性、资源ID、草稿路径保护或GUI开关。`agent live filter-controls`只读回当前
单选、名称、enabled/checked及`can_edit_in_native_ui`；该结果不是桌面截图。
证据为`lut33-named-UI-proof-v41.json`、`lut33-filter-native-history-proof-v42.json`和
`lut33-filter-native-actual-pixel-proof-v43.json`。完整边界见
[标准LUT研究](research/native-standard-lut-compensation-20261028.md)。

`agent live color-preset-save`已在新正常应用会话从真实当前片段保存version3个人调色预设，
亮度/R/G/B四通道所有锚点和柄与原生材质逐项相等，整条时间线未改变。该命令保护已有预设，
并检查原生preset manager归属主线程；不是手写文件冒充保存。**预设保存不等于完整曲线的
原生应用和任意点实时编辑已打通**，自有曲线输入的正常加载/应用闭环仍需另验。

`white-balance-controls/white-balance`新增正常色温/色调滑杆入口。实际控件范围UI-50..50、
native-1..1，分别type30/31；这些数值不是Kelvin。原生保存省略零value及平均速度1已按
原生默认解释，显式None/bool/越界仍拒绝。组合工程实际参数往返已通过，证据见combined-real-native-edit-proof-v10.json。

降噪开关使用同一公共入口：

```powershell
.\jianying.ps1 agent live denoise-controls --draft-id <ID> --session <SESSION> --segment-id <AUDIO_ID>
.\jianying.ps1 agent live denoise-switch --draft-id <ID> --session <SESSION> --segment-id <AUDIO_ID> --enabled false --request-id <UUID>
```

控件返回原始material及按正式Persistent parser解释的effective_native_settings；只调用原生
`onDenoiseSwitchClick(bool)`，保留正常权益/确认分支。compact保存省略false、mode1等默认值；
首轮关闭已提交，但旧验证索引缺失字段报错，原needs-inspection审计完整保留，没有重放。
后续独立回读、原生checkbox、历史和声音均验证了该次结果；修正后新的开启请求正常confirmed。
详细绑定及默认值依据见[降噪原生检查器](research/native-vocal-denoise-live-binding-20261028.md)。

## 已修复的真实根因

- SDK枚举必须是本机数值：HSL69、曲线70、色温30、色调31、LUT14、Primary76、Log77。
  字符串会造成解析中断/部分结果；数组本身没有被addon过滤。
- 声音主素材需要check_flag Basic1|VoiceChange2；只移植效果节点会编码出未处理原声。
- 声音参数查询以constant_material_id和三个槽号查找；两个空ID会使压缩读到EQ值。
  新build为每个效果生成稳定独立标识，原生五个读数已与保存值全部一致。
- 当前桌面声音页使用DraftInspectorAudioViewModel的延迟子页，不能用旧AudioSettingViewModel
  结构猜指针；新绑定核对当前inspector/model/wrapper/所选片段、category与参数owner。
- 调色/声音子页用正常switchTab及原生通知加载；onTabClicked只记录点击，不负责加载。
- HSL需要完整合并调色资源。GUI会迁移至已审核缓存collection并省略若干默认字段；验证保留
  完整包和嵌套lumi路径，允许已实际观察到的默认省略，仍拒绝显式关闭与未知包。
- 本地Compressor graph需第二个未启用的sidechain输入总线；缺失时引擎可能继续编码原声。
  导出现在检查已确认的MDSP加载失败和visual filter scene加载失败，不再仅接受编码结束。
- 打开草稿的异步模型准备现只轮询，不重复打开。已核对的低磁盘模态可走正常取消完整链，
  原请求返回与连接恢复都需确认；不会写确认标志或模拟输入。

## 峰值测量纠正

此前将原生双声道转为float单声道，测量引入约+3.0103dB；“设置-12、峰值-9.6所以超限”的
结论已撤回。按原通道和FFmpeg BS.1770测量，同一-12档整片真峰值为-12.59dBTP。
-24/-18/-6档整片分别为-26.16/-19.45/-6.13dBTP。没有为DSP加固定补偿。

新的真实语音限制器-18测试整片真峰值-18.52dBTP；这是激活/参数试验，-27.29LUFS的测试输出
不是生产响度目标。原-9档在压缩后未激活而PCM不变也保留为反例。静态实现是动态增益限制，
不据这些样例承诺任意高频/瞬态/AAC编码后的绝对真峰值保证。

## 真实证据与剩余工作

任务根：D:/JianyingHeadless/work/native-av-upgrade-20261028-004610-32bec1。

- curve-clock-proof.json、curve-native-edit-pixel-proof.json
- gui-native-hsl-audio-history-proof.json、gui-native-color-audio-render-proof.json
- primary-wheel-native-history-proof.json、primary-wheel-native-edit-pixel-proof.json
- log-wheel-native-history-proof.json、log-wheel-native-edit-pixel-proof.json
- native-five-audio-edit-proof.json、native-ceiling-range-activation-proof.json、native-five-audio-signal-proof.json
- limiter-stereo-true-peak-recheck-proof.json、denoise-rate-grid-native-renders-v2.json
- native-denoise-history-proof-v3.json、native-denoise-audio-proof-v3.json、vocal-denoise-fidelity-grid-proof-v2.json
- LUT失败证据lut-native-pixel-proof-v1.json、lut-native-pixel-proof-v2.json及对应原生日志。
- LUT后续通过证据lut-three-strength-native-pixel-proof-v7.json、lut-native-history-proof-v8.json、custom-cube-native-edit-history-proof-v2.json。
- 自定义颜色边界custom-cube-native-pixel-proof-v1.json、identity-cube-native-sampler-measurement-v2.json、hsl-interaction-native-pixel-proof-v1.json。
- 立体声/瞬态stereo-transient-source-manifest-v1.json、stereo-transient-native-proof-v1.json；输入48kHz，原生AAC输出44.1kHz，按实际采样率分析。
- 30秒组合combined-real-native-target-v4.json、combined-real-native-controls-v4.json，实际8视频/8音频/3字幕，已打开并实际修改。
- combined-real-native-edit-proof-v10.json：5个业务修改、6条原生历史记录，连续6undo/6redo每步完整原始时间线指纹相等；保存后再次原生出片，900帧、1080×1920、30fps、源工程字节未变。
- combined-real-native-actual-media-proof-v10.json：整片900帧及双声道PCM对照，成片-21.07LUFS、-2.98dBTP。实际前后对照图已查看；没有声称完成主观试听。
- combined-real-repeatability-proof-v11.json：同状态重导的后段图像MAD.940/255、平均有符号偏差约.001，双声道PCM完全相同。H264成片不保证像素确定性。
- combined-real-native-lossless-pair-proof-v12.json：原生player直接PNG，两状态采样时钟完全一致；4个未修改镜头RGBA逐字节相等，已调整色温/色调/LUT有实际像素变化。内部帧360×640、输出640×1138；不据放大PNG声称全分辨率清晰度。
- combined-real-native-curve-raw-frame-proof-v14.json：.5/.55/.8秒原生暂停帧随曲线变化，MAD49.52/17.78/16.69；1.1秒恰在积分不变端点，不能只用该帧判断曲线无效。
- combined-real-native-audio-null-control-proof-v13.json：仅修改前段数字静音素材的EQ，其余媒体/参数一致，两份原生输出整片PCM逐样本相同；该对照未见跨片段EQ串扰。
- combined-real-sound-latency-proof-v1.json：真实8段音频相对原R4，无降噪约7ms、有降噪约30ms。native-audio-editable-timecomp-proof-v1.json已在有安静余量的独立立体声样例中，以可编辑source_start_us=6984将308样本延迟补到0；真实语音及GUI入点往返仍待完成。

剩余：真实语音处理延迟的可编辑补偿和入点往返、自定义CUBE标准一致性、更复杂真实噪声和主观试听。
追加真实语音头尾试验`real-voice-handles-timing-proof-v15.json`：单纯提前source_start虽然
可对齐正文，却丢失开头约30ms的人声，故不采用该方案，也不能由安静开头样例推断人声已保全。
任意调色曲线锚点/控制柄的实时setter仍未接通，现有原生计划可保存Bezier参数。
单项参数生效与观感达到用户对标仍是不同验收项；此处未宣称大师级审美已实现。
