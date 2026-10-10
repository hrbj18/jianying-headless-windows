# lyra-cli 能力矩阵与实测状态

本表由 `work/enumerate_cli.py` 与 `work/export_command_options.py` 实际调用官方
`--help` 枚举得出，不是文档推测。状态列含义：

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

## 关键实测记录

| 命令 | 观察 |
| --- | --- |
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
