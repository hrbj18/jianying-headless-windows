# Windows 原生帧预览

`jianying.ps1 preview` 通过剪映自带 `videoeditor-service` 的暂停播放器直接取得指定时间点的帧，
包括 `transition/fog-compat` 雾化。预览不调用 ExportService，不生成视频再取帧，
不截取桌面、不模拟鼠标键盘，也不需要 GUI 宿主运行。

```powershell
.\jianying.ps1 preview --build D:\JianyingHeadless\work\my-build `
  --out D:\JianyingHeadless\work\my-preview --at 1.5 10.5 26.5 --width 960

.\jianying.ps1 preview --draft-dir 'C:\完整路径\我的已保存草稿' `
  --out D:\JianyingHeadless\work\draft-preview --at 1 5 --width 960
```

`--build` 与 `--draft-dir` 二选一。读取已保存磁盘状态；GUI 尚未保存的改动不在该快照中。
源码目录、源草稿与原素材可以含中文；输出目录必须是新的绝对 ASCII 路径，包含独立
`work` 路径段，并且与源工程及实时草稿树分离。

`--at` 后给 1..16 个不同的秒数，范围从 0 到工程结束前；结束时间本身不属于可取帧范围。
宽度默认 960，省略 `--height` 时按原画布比例推算高度。当前限制长边不超过 1920、短边不超过
1080；可传更小宽度处理特殊长宽比。`--timeout` 默认 90 秒；播放器单条管道请求最多等待
15 秒，启动和就绪各最多 20 秒。timeout 最多 600 秒。输出工作目录宜短，
避免 Windows 旧组件的路径长度限制。

输出PNG尺寸与播放器内部帧尺寸是两个值。2026-10-20的912×1920竖屏工程中，
captureFrame输出912×1920，但preview.json各帧player_state.frameWidth/frameHeight仍为
304×640。此路径可验布局、内容与时序，不能据PNG尺寸声称已检查全幅清晰度；文字栅格
和纹理清晰度另以正常原生导出的原尺寸MP4帧检查。

## 默认播放器路径与证据

先使用与 `export` / `export-draft` 相同的草稿读取、能力检查、媒体/字体复制和依赖校验器，
把时间线及本地资源暂存在输出目录。原生服务只加载这一副本。

服务使用本机正版 `bun.exe` 后台启动，不创建终端窗口。每次请求建立新的独立命名管道连接，
依次完成 `system.health → player.create(kind:draft) → load → getState → seek → captureFrame`。
传给原生播放器的时间线使用紧凑 JSON 字符串，并保留全部原始字段及 schema；本机构建曾对
格式化 JSON 返回 `accepted` 却得到零时长空画布。正常入口额外核对 `getState.durationUs`
与真实草稿一致，不只检查 `accepted` 或 `status:ready`。
health 返回 PID 必须与本命令启动的进程一致。完成后 `player.destroy`，再用
`system.shutdown(expectedPid)` 请求退出；超时才终止本命令创建的进程对象，不遍历或终止其他
剪映进程。

成功状态为 `native-frames-captured`，输出包括：

- `preview.json`：真实运行时、组件指纹、源数据未变化检查、帧时间戳和清理结果。
- `frame-000.png` 等：原生 RGBA8 帧编码成 PNG。
- `frame-000-attempt-00.packet` 等：官方 VEF1 原始帧包，保留失败时间戳尝试以便定位。
- `ipc-NNN.json`：每条官方请求/响应的元数据；图片 base64 从客户端输出中移除，文件内容不入日志。
- `timeline.json`、`inputs.json`、复制的依赖及官方服务日志。

VEF1 必须满足版本 1、40 字节小端头、请求的准确宽高、RGBA8 像素格式、有效行跨度和精确负载
长度。帧时间戳与请求位置的误差最多一帧；异步 seek 尚未就绪时短暂重试，不能把旧帧当成目标帧。
PNG 使用 Python 标准库 `struct/zlib` 编码，不增加图片处理依赖。

## 雾化的暂停播放器修复

旧 v2 兼容包动态创建相机和渲染纹理，暂停 `seek/captureFrame` 路径会丢失左源模糊结果。
单独复用相机或纹理仍会黑场；订阅并确认真实播放、再暂停重试也没有解决。
v3 复用已序列化场景中的 8 组相机/renderer，以已有的两个独立 RT 交替传递 8 遍结果，
关闭会重写这些相机/RT 的模板效果脚本，仅保留雾化控制器。原始 Gaussian/blend fragment、
AE 曲线和 120 张遮罩保持字节一致。该改动在独立兼容资源内，不修改剪映安装或官方缓存。
这是经对照验证的兼容场景修复；渲染图登记机制是运行证据支持的推断，并非已证明的引擎源码结论。

正常 `preview` 统一使用 `native-player-capture-frame`。每帧保留 VEF1 原包与 PNG，
取帧后校验 `getState.status` 为 `ready/paused` 并记录状态。`preview.json` 声明
`export_used:false`、`external_frame_decode_and_resize:false`；没有 H.264 中间视频。

新动作的 `transition/fog-compat` 绑定 v3。历史草稿只接受目录中完整摘要匹配的已审核 v2，
预览复制完依赖后，将副本的该资源替换为已核验 v3，并写入 `resource_upgrades`，列出两套
树摘要、材质 ID 及副本路径；原工程和原资源保持不变。未审核字节、未知材质或不支持时长
仍会停止。`export-draft` 使用草稿保存的原版本；预览副本升级不等于已经改写交付工程。
需要永久升级工程时，在独立副本更新资源绑定并完成官方加密读回，再 `vfx freeze-draft`
保存完整依赖；不要手工覆盖已冻结资源目录。

验收包含 400/600/800/1200ms 雾化、高频网格的真实模糊与非均匀遮罩、暂停乱序/重复取帧，
以及带叠化、文字和软蒙版动画的 12 秒混合工程。独立 ExportService 成片仅作离线参考，
预览 PNG 的来源始终是播放器。预览与编码成片允许正常尺寸和颜色差异，不声称逐像素等同。

## 审核范围

仅启用已审核的 **Windows 11.4.7.14462**；在已有 EXE 版本、DLL 指纹和官方签名校验之外，
还校验这四个组件的精确 SHA256：

| 组件 | SHA256 |
| --- | --- |
| `videoeditor_addon.node` | `d9997bc0421a9da9ecafba4835bb8b4c1363de7a8c50e46be81b081766300be9` |
| `bun.exe` | `27ad10bef00a8a296d66a2983072ed8e824f05e1910dc505dd72b912083689e0` |
| `Resources/canvas_agent/runtime/videoeditor-service.mjs` | `83a1b2515b3ebac99e6a0d83b8040c361f593cde29a437aa5b1c02e673b2e585` |
| `Resources/canvas_agent/runtime/agent-runtime-addon-preload.mjs` | `85106d290b0aeb3fe86d5b871a2daa4baa9a88a84e5493c728da87871b59d9e6` |

内容范围沿用当前 Windows 原生导出的明确能力门禁，包括已验收的本地媒体、基础文字、
静态本地 TTF/OTF 字体和绑定的原生音频 fade。不会为了预览静默删除未知效果或在线依赖。
这条命令读取画面帧，不负责音频试听，也不把少量预览帧当成整片画面、音频或完整导出的验收。
Windows 服务没有另加网络沙箱；本命令不请求网络功能，只接受已通过本地依赖检查的时间线。

## 11.4.7 正常入口实测

在剪映 GUI 关闭时，正常 `preview --build` 读取 28 秒、1920×1080 的展示工程，直接得到
960×540 原生帧。1.5、10.5、26.5 秒的 VEF1 时间戳均与请求完全一致，三帧均首次取帧成功。
源构建的 `new_version:185.0.0` 未被修改，媒体和本地字体经已有导出依赖 stager 复制后呈现正常。

同一正常入口又通过 `--draft-dir` 读取中文名称的已发布磁盘工程，在 10.5 秒成功取得原生帧，
源工程及外部媒体/字体清单保持不变。两次服务均完成 player destroy、带 expectedPid 的 shutdown，
以退出码 0 收尾。帧包和 PNG 成功不代表音频试听或整片导出验收。

最终官方编辑后的 `187.0.0` 已发布工程也通过三时点读取和原生导出。预览与成片的构图及
字形一致，但本机播放器内部报告 640×360，960×540 帧有放大软化；三个时点与成片的亮度
SSIM 约为 0.917 / 0.876 / 0.942。请求的输出宽高不代表内部全分辨率渲染，不应用预览帧
验收最终锐度、暗部颜色或精细调色；这些仍检查正式导出的 MP4。
