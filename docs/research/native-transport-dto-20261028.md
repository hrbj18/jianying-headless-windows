# 剪映 11.4.7 原生传输 DTO 静态研究

范围：仅阅读本机发布物、研究任务资源与静态反汇编。不执行 mutator，不连接活跃剪映，不使用 computer use，不读取凭据。

本轮发现：Web JavaScript 参数模型与 Windows native addon 的真正 DTO **不同**。addon 会递归补 snake_case 别名，因而 `audioAdjustParams`、`segId` 等 camelCase 名称本身通常可以传入；但不会把 `audioAdjustParam` 子对象展平，也不会把 Web 的 `materials` 数组拆成 native `material` 单对象。**真正危险的是本机数值枚举与 Web 字符串/旧数值枚举不同。**

## 发布物与证据

- `videoeditor_addon.node`（根目录与 `Resources/agent_runtime/runtime` 两份相同）：3,789,312 字节，SHA256 `d9997bc0421a9da9ecafba4835bb8b4c1363de7a8c50e46be81b081766300be9`。
- `videoeditor.dll`：70,998,296 字节，SHA256 `fa89997a94e96cf97c8ee436a56ab028ea5f87731214696ba43ff74c0fdc0fa0`。
- 安装根：`D:\刘宇钊\软件\剪映\JianyingPro\11.4.7.14462`。
- 研究目录：`D:\JianyingHeadless\work\native-av-upgrade-20261028-004610-32bec1\research-native-audio`。

addon 使用 REA/Ghidra 分析，原始证据保留为 `rea-addon-dto-evidence.json` 与 `rea-addon-dto.snapshot.json`；后续参数标准化研究另存 `rea-addon-normalization-evidence.json`。DLL 使用 PE 导出表、异常目录的函数边界、限定地址范围的 LLVM 反汇编，不加载 DLL。

## 真实 transport 映射

| edit operation | 原生服务/方法 | addon 处理函数 |
|---|---|---|
| audio.setVoiceEffect | AudioService / audioChangeVoice | 0x18005c0e0 → 0x180035380 |
| audio.setVoiceEffectParams | AudioService / audioChangeVoiceAdjust | 0x18005c0e0 → 0x180034450 |
| video.setBasicColor | VideoService / setPictureAdjust | 0x180192230 → 0x180150280 |

addon 将用户参数包成正式请求的 `params` 后调用 DLL `lyra::ServiceApiMapping::makeReq`。真实字段来自 DLL 注册表关联的生成解析函数；addon 自身只额外补少数字段（声音 segment_id/name），不能用 addon 内没有出现 audio_adjust_params 字符串推断它不支持。

### addon 不会过滤音效参数数组

REA 新恢复函数 **0x180084460**（Evidence `ev_86fc5642bdb06f1cfcdbb2555785e5a15daa83c021d1c794830e430ed06c0a9a`）：

- 对对象逐键递归复制，保留原键，并用 0x1800852c0 为其生成 snake_case 别名。
- 对数组逐项递归复制并 push_back，不会按字段白名单丢弃 `audio_adjust_params`。
- 补 `segId/seg_id/segmentId→segment_id`，再补 `segment_id→seg_id/fix_segment_id`；还补片段 ID 数组及部分时间字段别名。
- 仅对特定 64 位整数字段将字符串转为整数；不将普通 enum 字符串转换为数值。
- 最外层剥离 draftSnapshot/actionType 等控制字段后，0x180082580 将结果作为正式请求 params，并设 commit_immediately。

主线程实际实验确认：移除错误 `audio_effect_type:"audio_effect"` 与 `vc_type:"none"` 后，原生正确保存 audio_adjust_params 的 .5，再以扁平调参保存 .25；category 也正确保留。此前字段缺失符合中途 enum 解析异常的结果，不是数组被 addon 删掉。证据是主任务 `voice-effect-session-native-v3-noenums/voice-effect-response.json` 与 `voice-effect-modified-response.json`。

### 本机真正的数值枚举

DLL **TransferLVVEMetaTypeToString** 导出 RVA **0xddd580**，根据参数数值读取 RVA **0xdde958** 的 127 项 RVA 跳表。以下值通过跳表定位到对应返回字符串的实际指令分支确认，不能用 Web 旧版 MetaType 或渲染 filter ID 替换：

| native material.type | 返回字符串 | 分支 RVA |
|---:|---|---|
| 13 | filter | 0xddd8c8 |
| 14 | lut | 0xddd8f7 |
| 20 | brightness | 0xddd9e2 |
| 21 | contrast | 0xddda11 |
| 22 | saturation | 0xddda40 |
| 23 | natural_saturation | 0xddda6f |
| 24 | sharpen | 0xddda9e |
| 25 | highlight | 0xdddacd |
| 26 | shadow | 0xdddafc |
| 27 | white | 0xdddb89 |
| 28 | black | 0xdddbb8 |
| 29 | clear | 0xdddbe7 |
| **30** | **temperature** | **0xdddb2b** |
| **31** | **tone** | **0xdddb5a** |
| 32 | fade | 0xdddc16 |
| 33 | light_sensation | 0xdddc45 |
| 34 | vignetting | 0xdddc74 |
| 35 | particle | 0xdddca3 |
| 46 | audio_effect | 0xdddd8e |
| **69** | **hsl** | **0xdde1f6** |
| **70** | **color_curves** | **0xdde254** |
| 71 | audio_balance | 0xdde225 |
| 76 | primary_color_wheels | 0xdde33f |
| 77 | log_color_wheels | 0xdde36e |

例如 Web `ai-creation~10` 模块 58740 与 `ai-creation~5` 模块 27840 的旧 native 镜像枚举是 HSL=56、curves=57、temperature=24、tone=25；另一套渲染 filter ID 为 HSL=24、curves=26、temperature=16、tone=17、LUT=23。它们均不是本机上述 native DTO 的准确 material.type。更不能把持久化字符串 `"hsl"` 直接传入。

数值解析器 DLL RVA **0xc4000** 仅接受 JSON number（整数/无符号/浮点后取整数），对 string 抛 `type must be number, but is ...`，没有字符串 enum 查表。`TransferStringToLVVEMetaType` 虽然是另一个导出函数，当前请求解析链没有调用它。

audio_effect_type 是另一种枚举，**不是** material.type=46。发布 JS `ai-creation~5` 模块 74893 导出 tV 给出 Normal=0、SoundEffects=1、VCVoiceChange=2、SpeechToSong=3、VocalSeparation=4；本机 `TransferInt32TToLVVEAudioEffectType` / 反向同址 RVA 0xddb160 对 0..4 保持值，其余回落 0。资源的 tone/scene 分类并没有因此变成两个相应的 AudioEffectType；本轮没有找到这种一一映射，不臆造。

vc_type 由本机 **TransferLVVEVCCloneTypeToString** RVA **0xddf6d0** 精确确认：0=none、1=speech、2=sing；未知值同样退 none。收音机使用默认正常音效可不传这两个可选枚举。

枚举证据：`native-enum-parser.txt`、`native-enum-to-string.txt`、`native-meta-enum-jump-table.jsonl`、`native-meta-enum-recovered.json`。后者同时保存选中值、分支 RVA 和其文字/指令片段。

DLL service registry：`ServiceApiMapping` 构造 RVA 0x1830d10；AudioService registry RVA 0x183c5e0；VideoService registry RVA 0x19315e0。makeReq RVA 0x1832020 经注册对象 vtable +8 调入相应请求构造器。

## audio.setVoiceEffect

调用路径：请求构造器 RVA 0x1852f10 → 请求 envelope 解析 RVA 0x183e400 → 参数解析 RVA **0x1845580**。

参数 key：

```text
segment_id            string
name                  string
resource_id           string
third_resource_id     string
source_platform       integer
resource_path         string
production_path       string
audio_effect_type     integer / enum
speaker_id            string
vc_type               integer / enum
is_vc_clone_tone      boolean
is_ugc                boolean
time_range            object (本轮未恢复子字段)
category_id           string
category_name         string
is_modify             boolean
audio_adjust_params   array<object>
```

音效参数数组元素由 RVA **0x1846080** 解析：

```json
{
  "value": 0.5,
  "default_value": 1,
  "parameterIndex": 0,
  "portIndex": 0,
  "name": "强度",
  "min_value": 0,
  "max_value": 1
}
```

value/default_value/min_value/max_value 为浮点数，两个 Index 为整数。这里的默认值及范围来自主线程已通过正常 material download 取得的收音机资源 `7418519267659747877` 的 `extra.json`，不是猜测 DSP 索引。该资源仅公开强度 parameterIndex=0、portIndex=0；不能将它宣称为暴露了 EQ 各频段、压缩 threshold/ratio 的独立编辑控件。

可供主线程独立试样验证的完整请求形状保存在 `research-native-audio/native-audio-radio-dto-example.json`，带真实合法资源路径及待替换片段 ID。没有在此子任务执行。

## audio.setVoiceEffectParams

调用路径：请求构造器 RVA 0x1852d90 → envelope RVA 0x183e330 → 参数解析 RVA **0x1844e80**。

**该接口是扁平参数，不接受 Web 的 audioAdjustParam 子对象：**

```json
{
  "segment_id": "真实音频片段 ID",
  "resource_id": "7418519267659747877",
  "paramIndex": 0,
  "parameterIndex": 0,
  "portIndex": 0,
  "effect_adjust_value": 0.75,
  "is_keyframe": false
}
```

另有可选 `keyframe_id:string`、`is_auto_fill_keyframe:boolean`、`flags:integer`、`is_clear_all_keyframes:boolean`。`effect_adjust_value` 通过 double 解析器读取；paramIndex/parameterIndex/portIndex 通过 int 解析器读取。paramIndex 与 parameterIndex 是不同结构偏移；本轮不推断它们一般情况的业务关系。对于资源唯一公开的首个旋钮，两个 0 是后续最小实验样例，仍须 authoritative draftSnapshot 与二次导出验证。

## video.setBasicColor / setPictureAdjust

调用路径：请求构造器 RVA 0x191e680 → envelope RVA 0x18a5d30 → 参数解析 RVA **0x18a6760**。

顶层真正使用 **seg_id** 与 **material 单对象**：

```text
seg_id                     string
material                   object
is_keyframe                boolean
keyframe_id                string
is_auto_fill_keyframe       boolean
is_unified_beauty_mode      boolean
preset_resource_id         string
```

material 参数解析 RVA **0x1898e00**，相关字段为：

```text
effect_id / res_id / third_res_id / name    string
type / sub_type / video_effect_sub_type    integer / enum
bind_audio_id / transparent_params         string
path / lumi_hub_path                       string
value                                     double
category_id / category_name                string
item_effect_type                          array (本轮未恢复元素业务含义)
platform / version                        string
source_platform                           integer
adjust_params                             array<object>
hsl_params                                object
formula_id                                string
enable_skin_tone_correction                boolean
color_curves_params                       object
color_wheels_param                        object
text_flower_params                        string
disable_effect_faces / exclusion_group     array (元素另解析)
algorithm_artifact_path / intensity_key    string
face_adjust_params                        子结构本轮未恢复
panel_id                                  string
bloom_action_params / color_match_info     object
request_id                                string
covering_relation_change                  integer / enum
beauty_face_auto_preset_id                 string
```

上表 enum 的合法值必须来自已经验证的正式资源/参数模型，不应拿持久化材料的 type 字符串代替。

adjust_params 先要求 JSON array（RVA 0x18945d0），数组元素的真正解析函数为 RVA **0xca1e0**：

```json
{
  "adjust_key": "真实基础调色 key",
  "adjust_value": 0.25,
  "default_value": 0,
  "flags": -1
}
```

adjust_value/default_value 是 double；flags 是 64 位整数。key 应从资源或正式现成映射取得；上例只表达结构，未验证 flags=-1 的业务效果。

### HSL 是单个整数参数对象

hsl_params 的参数解析 RVA **0x189a560**：

```text
hsl_color_type       integer
hue                  integer
saturation           integer
lightness            integer
interacting          boolean
path                 string
visible              boolean
custom_color         string
constant_material_id string
resource_id          string
source_platform      integer
```

前三项的单位/合法范围本轮没有仅凭字段猜测。它们通过 int 解析器而不是 double 解析器读取，且 hsl_params 不是 8 项数组。此前持久化 `hsl` 形状、Web hslParams 数组或浮点值能否互换，必须通过正确 DTO 的 native-save/export diff 另验。

本机构建的 HSL 最小实验请求（资源路径与片段 ID 由独立试样填入）：

```json
{
  "domain": "edit",
  "operation": "video.setBasicColor",
  "targetId": "独立试样 sessionId",
  "params": {
    "seg_id": "真实视频片段 ID",
    "is_keyframe": false,
    "material": {
      "type": 69,
      "hsl_params": {
        "hsl_color_type": 1,
        "hue": 30,
        "saturation": -35,
        "lightness": 10,
        "path": "复制到任务目录的真实 Resources/DefaultAdjustBundle/hsl",
        "resource_id": ""
      }
    }
  }
}
```

`hsl_color_type=1` 为发布 JS 模块 74893 的 Red；该模块还列 Unknown=0、Orange=2、Yellow=3、Green=4、Cyan=5、Blue=6、Purple=7、PurpleRed=8、End=9。这些颜色数字与 native material.type 的 69 属于两个不同字段；不能把 Unknown=0 当红色。上述30/-35/10是主线程当前独立试样取值，不在本子任务宣称经过范围或出片验证。

相同传输结构下，temperature 使用 `material:{type:30,value:0.25,path:<真实temperature_tone_v3资源>}`；tone 使用 type:31；LUT 使用 type:14 及正式合法LUT资源。color_curves 使用 type:70 与 color_curves_params 单对象，主线程现有试样使用真实 Curves 包及 anchor/left_control/right_control 控制点。`sub_type` 不必为了测试强填未知值，保持正式构造默认即可。

### 曲线与色轮

color_curves_params（RVA **0x18981c0**）：panel/resource_id/path:string，luma/red/green/blue:array，source_platform:int。数组元素完整结构本轮未恢复，已有主线程原生曲线实验证据可复用，不能直接把任意 `[x,y]` 列表当已支持。

color_wheels_param（RVA **0x18986b0**）：modified_type:integer/enum、modified_fields:array、red/green/blue/luma/saturation/intensity:double、panel/resource_id/path:string、source_platform:int。业务量程尚未恢复。

## 实验边界

本轮仅修正传输 DTO；`accepted`、参数成功序列化、资源含 DSP 字样，都不足以证明声音处理已生效。主线程仍需独立草稿 authoritative snapshot、实际导出差分、再次调整参数后二次导出，并按用户要求保持剪映内可继续编辑。

主要机器证据文件：`native-audio-DTO-parser.txt`、`native-color-array-parser.txt`、`native-color-material-audio-element.txt`、`native-control-element-parsers.txt`、`native-adjust-param-parser.txt`、`service-mapping-ctor-annotated.txt`、`audio-video-service-registry.txt`、`native-audio-request-builders.txt`。这些文件均保留限定函数边界与带文字注释的 RIP 引用，便于复核每个 key 的读取位置。
