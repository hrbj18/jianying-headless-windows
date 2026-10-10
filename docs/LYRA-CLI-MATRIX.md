# lyra-cli 能力矩阵与实测状态

本表由 `tools/enumerate_all_commands.py`（经剪映官方 VMSDK 递归调用真实 `--help`，
通过发布门禁后产出 `engine/lyra_commands.json`）与 `tools/export_command_options.py`
（导出指定命令的参数说明）实测得出，不是文档推测。本轮稳定探测 241 个 help 节点，清单
登记 195 条叶命令，195 条均成功取得当前参数表，`discovery.failures` 为 0。官方 help 展示的
`draft algo mask-tracking-mattingTrack` 别名被官方自身以 `exitCode=2 / ExtrasError` 拒绝，已在
`discovery.unsupported` 留痕而不安装 wrapper；另有 13 条同样被明确拒绝的旧路径已从能力清单移除。

状态列含义：

- **✅ 实测**：本项目已真实执行过该命令并确认行为；
- **🔌 已封装**：`engine/lyra_cli.py` 有 typed 函数或走通用转发 `draft()`；
- **🔐 需登录**：命令依赖账号权益；
- **⏳ 未测**：已确认存在，但本项目尚未实跑。

## 顶层域

| 域 | 子命令 | 本项目状态 |
| --- | --- | --- |
| `auth` | login / relogin / qrcode / status / me / check / logout | ✅ 实测（分步链接登录）· 🔌 `auth_login_link` / `auth_login_complete` / `auth_status` |
| `draft` | 见下 | ✅ / 🔌 |
| `material` | search / download / query / topic / recommend / similar / motiongraph | 🔌 `material_search` / `material_download`（download 未实测） |
| `media` | aigc / transcode-image / crop-image / resize-image / compress / trim-video / trim-audio / change-video-speed / change-audio-speed / rotate / extract-frames / extract-audio / probe / loudness / measure-box / beats / object-matting-track / asr / vad / feature / translate / understand | 🔌 `media_asr`（未实测） |
| `lint` | command / media / algorithm-effect / draft / trace | 🔌 `lint_command` / `lint_draft`（未实测） |

## `draft` 子域

| 子域 | 子命令数 | 命令 | 本项目状态 |
| --- | --- | --- | --- |
| `lyrics` | 4 | add / animation(add,update,replace) / remove / recognize | ✅ **实测闭环**（识别 + 动效 + 渲染）· 🔌 `lyrics_recognize` / `lyrics_animation_add` / `lyrics_animation_update` / `lyrics_animation_remove` |
| `blueprint` | 4 | init / sync / apply / resource | ✅ 实测（本项目官方落地的核心通道）· 🔌 `draftediting_runtime` |
| `template` | 5 | add / publish / render / slots / replace | 🔌 `template_render`（未实测；要求 `--ref` 指向新工作区） |
| `subtitle` | 4 | add / template / remove / recognize | 🔌 `subtitle_add`（参数已核对，未实测） |
| `audio` | 5 | volume / fade / speed / add / remove | 🔌 `audio_add`（参数已核对，未实测） |
| `text` | 8 | translate / content / effect / wrap-width / add / remove / animation / style | 🔌 通用转发（`add` 的 help 需要草稿上下文，未硬编码参数） |
| `video` | 28 | crop / speed / stabilize / scale / rotate / translate / alpha / flip / layer / volume / freeze / add / remove / transition / filter / effect / mask / animation / beat / audio-effect / color / adjust / background / matting-stroke / mix-mode / face-beauty / extract-frames / extract-music | 🔌 通用转发 |
| `algo` | 21 | query / wait / quality-enhance / upscale-resolution / ai-frame-interpolation / ai-matting / ai-transition / custom-matting / chroma-color-matting / video-tracking / sound-separation / loudness-normalize / denoise / voice-enhance / video-stabilize / tts / subtitle-recognize / text-add-tone / music-beats / material-understand / subtitle-keywords | 🔐 多数需登录 · 🔌 `algo_tts` / `algo_sound_separation` / `algo_upscale_resolution`（参数已核对，未实测） |
| `keyframe` | 4 | add / update / remove / curve | 🔌 通用转发 |
| `effect` | 3 | add / remove / generate | 🔌 通用转发 |
| `sticker` / `filter` / `adjust` / `segment` / `timeline` / `compound-clip` / `deform` | — | 各自快捷方式 | 🔌 通用转发 |
| `edit` | — | 冻结的旧式 raw 兼容层 | ⏳ 不推荐新代码使用 |
| `project` / `cover` / `extract` / `history` / `config` | — | 工程管理、封面、结构导出、撤销重做、画布配置 | 🔌 通用转发 |

## 通用转发

未做 typed 封装的命令一律走：

```python
import lyra_cli

lyra_cli.draft(["video", "speed"], draft_root, "local://demo",
               {"--seg-id": "v1", "--speed": "2.0", "--wait": True})
```

`None` 的参数会被跳过，`True` 表示只加开关。这条通道覆盖全部 `draft` 子命令，
不需要为每个命令硬编码参数。

## 逐条真实功能测试（`tools/functional_test.py`）

在剪映官方 VMSDK 沙箱里对 195 条命令各真实执行一次（**已登录 VIP 账号**），并在一个全新
工程上跑完整剪辑链路。结果按官方语义归类，失败不等于缺陷：

| 归类 | 条数 | 含义 |
| --- | --- | --- |
| ✅ 成功 | 102 | 官方返回 `err_code=0`，命令真实跑通 |
| ➡️ 需真实前置产物 | 31 | 需要工程里先有对应类型片段（`segment_text`/`segment_video`）、真实 task id、模板槽位或线上资源 |
| ⚠️ 官方参数契约拒绝 | 27 | `RequiredError` / `ValidationError`：参数组合、互斥或取值域要求 |
| ⚠️ 官方业务拒绝 | 22 | 线上资源下载失败、模板包解析、算法服务报错等业务前置条件不满足 |
| ⏭️ 有意跳过 | 4 | `auth logout`（会真实登出）/ `auth login` / `relogin` / `qrcode`（需人工授权） |
| 🚧 官方未实现 | 4 | `command is not implemented yet`：`material recommend` / `material similar` / `upgrade` 等 |
| 🚧 仅内嵌库支持 | 3 | `draft history undo` / `redo` / `trace` 明确只在被当作库内嵌时可用 |
| 📦 本机缺模型 | 1 | `media vad` 报 AED 模型未安装 |
| 🔐 需要登录 | 1 | `material download` 资源池下载仍失败 |

未登录时同一套测试的成功数是 87、需要登录 31；**登录 VIP 账号后成功数升到 102**，
说明登录真实解锁了约 15 条账号权益命令（其余需登录命令随后暴露了更深的参数/资源要求）。

工作流层（16 步真实剪辑链路）成功 13 步：建工程 → 加主视频/画中画/文字/音频 → 导出结构取真实
`seg_id` → 变速/裁剪/调色 → 关键帧 → 加字幕 → 加滤镜 → 导出模板包 → 最终结构校验；2 步是官方
standalone 不支持的 `history undo/redo`，1 步是模板资源路径要求。

## 关键实测记录

| 命令 | 观察 |
| --- | --- |
| 所有命令 | 工程必须放在剪映草稿根（`%LOCALAPPDATA%\JianyingPro\User Data\Projects\com.lveditor.draft`）下；工作区/草稿路径必须纯 ASCII，否则命令静默以 `exitCode=9` 失败 |
| `draft project delete` | 会真实删除工程；之后任何命令报 `draft not found`，测试必须重建工程 |
| `draft video speed/crop/adjust` 等 | `--seg-id` 与 `--seg-type`/`--target-track`/`--seg-index` **互斥**，同时传会被 `ValidationError` 拒绝 |
| `draft video volume`、`draft text style`、`draft audio volume` | 参数名必须命中官方 handler 字段，否则报 `gen_patch --update has no registered handler for field(s)` |
| `media trim-video` / `extract-frames` / `loudness` | `--end` 与 `--duration` 互斥，且 `--end` 必须大于 `--start` |
| `media trim-audio` / `change-audio-speed` / `extract-audio` | `--output` 后缀必须是 `.aac`/`.m4a`/`.mp3` |
| `media transcode-image` / `crop-image` / `resize-image` | `--format` 必须与 `--output` 后缀一致，否则报 `format conflicts with output suffix` |
| `draft keyframe add/update/remove`、`curve set` | `--animated-property` 只接受 `position-x/position-y/scale/scale-x/scale-y/rotation/opacity/volume`；`--points` 必须带时间单位（`0s:0.2,1s:0.8`） |
| `lint command` / `lint draft` / `lint trace` | 用进程退出码表达"发现多少问题"（`result.automation_exit_code`），`err_code=0` 仍是成功；`lint command` 需要 lyra-cli 源码仓库 |
| `draft algo video-tracking` / `draft blueprint patch` | 官方进程以 `unhandled Windows exception 0xE06D7363` 崩溃（官方缺陷，非封装问题） |
| `draft algo query` / `wait` | 需要真实 video-tracking task id，无法伪造 |
| `auth logout` | 会真实清除登录态，让同批所有需要登录的命令立即失败；自动化测试必须跳过 |
| `draft video mask add`、`draft adjust add`、`draft text effect add`、`draft video audio-effect add` | 参数被接受后进入线上资源下载，失败为 `download failed, sub_code: 1006`（需要真实资源 id/权益） |
| `draft algo subtitle-recognize`、`draft subtitle/lyrics recognize` | 登录后可执行，但算法侧要求 talking-head 素材，测试素材不满足 |
| `draft template add` | 需要真实的官方模板包，喂普通 mp4 报 `unzip failed` |
| `media measure-box`（视频贴纸） | 报 `requires --allow-video-decode` |
| `auth login --require-jianying-app` | 本机剪映签名不被认可（`signature_not_official`），官方提示可用 `LYRA_CLI_ALLOW_DEV_JIANYING_APP=1` |
| `auth login --require-jianying-app` | 本机剪映签名不被认可（`signature_not_official`），官方提示可用 `LYRA_CLI_ALLOW_DEV_JIANYING_APP=1` |
| `auth login --link-url --no-wait` | 返回 `login_url`（300 秒有效）与 `device_code` / `user_code` / `session_handoff`，用户授权后补齐即可登录 |
| `draft lyrics recognize --language zh` | 需要登录；`--mode draft` 会按音视频来源重复识别（本工程 100 条 → 去重 10 句） |
| `draft lyrics animation update --seg-id` | 只接受普通文本段（`segment_text`）；一次调用即作用于整组歌词；会重建并展开段落，原 `seg_id` 失效 |
| `draft lyrics animation add` | 不接受 `--seg-id`；多组识别结果时报 `multiple lyrics recognize tasks found` |
| `draft template render` | 官方唯一渲染命令，但 `--ref` 必须指向尚未存在的工作区（从 `--config` 生成），不能渲染已有草稿 |
| `draft blueprint apply` | 只写 `Timelines/<id>/draft_content.json`，渲染读根文件，必须同步镜像（`sync_draft_mirrors`） |
| `draft video add` / `draft text add` 的 `--help` | 需要草稿上下文，直接调用会挂住 → 用通用转发，不硬编码参数 |

## 已知覆盖缺口

1. **渲染任意已有草稿**：官方只提供从新配置生成草稿的 `template render`；本项目用自编译的
   原生 ExportService 辅助程序补上这一环（`engine/native_export_windows.cpp`）。
2. **GUI 交互**：时间轴拖拽、预览播放、素材库可视化浏览不在 CLI 范围。
3. **权益外资源**：`material download` 与部分 `draft algo` 受账号权益限制，命令会失败，
   封装层只转发不代授权。
