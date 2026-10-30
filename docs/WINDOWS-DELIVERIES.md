# 固定交付、归档与素材存储

同一任务的成片数量由交付清单约束。例如四条视频对应四个逻辑 `slot_id`；每个交付位只在
首页保留一个当前修订。内部候选、试剪、技术验证和历史修订在任务工作目录或归档中管理。
用户已有的其它项目不自动加入本任务的所有权范围。

## 交付清单

使用 `jy-delivery-lifecycle/v1` JSON，包含 `delivery_id`、原生 `draft_root`、同卷扫描范围外的
`archive_root`、`expected_index_sha256`、恰好四个 `slots` 和显式 `owned_drafts`。
每个 owned 项包含原生 `draft_id`、精确绝对目录和完整 `files` 映射（相对路径、SHA256、字节数）；
每个 slot 引用其中一个当前工程。初始清单从已保存状态捕获，不能凭名称或文件夹前缀推断所有权。

```powershell
.\jianying.ps1 delivery inspect --manifest C:\task\delivery.json
.\jianying.ps1 delivery reconcile --manifest C:\task\delivery.json --audit C:\task\reconcile-1
.\jianying.ps1 delivery promote --manifest C:\task\delivery.json --slot sisters `
  --build C:\task\approved-build --audit C:\task\promote-1
```

`reconcile` 归档显式 owned 中的非当前工程；`promote` 验证新构建并替换一个交付位，旧修订进入
可恢复归档。它们要求剪映关闭，使用原生目录锁、完整文件哈希、索引预期哈希和权限检查。
用户保存的变化与清单冲突时停止，重新捕获、审阅后再执行；避免用旧构建覆盖新保存内容。
事务逐阶段记录，提交前失败在快照未变化时回滚搬移；提交后失败保留下一清单与日志供核对。
原生 `draft_ids` 字段原值保留，不把它猜作当前草稿数量。

归档包含实际工程、原索引项、原路径、完整哈希和事务记录。恢复有两种用途：

```powershell
.\jianying.ps1 delivery restore --manifest C:\task\delivery.json `
  --archive-id REVISION_ID --out C:\task\restore-check --audit C:\task\restore-audit
.\jianying.ps1 delivery restore --manifest C:\task\delivery.json `
  --archive-id REVISION_ID --slot sisters --audit C:\task\restore-slot-audit
```

默认私有恢复只验证文件等价，不登记首页；原生绝对路径没有改写，不能直接声称私有恢复副本可播放。
明确指定 `--slot` 时回到归档原路径，替换当前交付位，首页仍保留四个本任务工程。
普通 `publish` 用于首次独立交付；已有清单的修订使用 `delivery promote`。
incoming 工程位于扫描范围外；索引临时 JSON 与工程暂存是不同对象。

## 不可变媒体

Windows 构建、预览、导出及交付复制把完整哈希相同的媒体放入目标卷的受管理素材池。
池拥有独立的原样拷贝，原素材只读访问；工作快照通过真正同卷硬链接复用池对象，媒体路径继续
位于工程内。C、D 卷分别拥有池，跨卷采用目标卷对象，不把跨卷复制宣称为硬链接节省。
硬链接不可变媒体使用只读属性；它用于阻止意外写入，不代替权限隔离。
编辑元数据与时间线镜像仍各自独立，禁止共享可写 JSON。需要改写媒体时先调用
`media_store.ensure_private_copy`，把该路径拆成独立可写拷贝。

```powershell
.\jianying.ps1 media-store scan --allow-root C:\task\work --min-bytes 1000000000 `
  --protect-root C:\originals --out C:\task\media-scan.json
.\jianying.ps1 media-store dedupe --manifest C:\task\media-scan.json `
  --allow-root C:\task\work --protect-root C:\originals `
  --log C:\task\dedupe.jsonl --out C:\task\dedupe-result.json
```

scan/apply 均核对完整 SHA256；apply 逐文件记录并支持中断后按同一清单续跑。同名、同尺寸不能
代替内容校验。原路径保留，实际 file ID 和分配空间分别统计；硬链接的各路径逻辑大小相加会
重复计算空间。只读媒体删除使用单链接删除 helper，避免 chmod 改变池中所有别名的保护属性。

## 缓存回收

完成的原生预览/导出依赖缓存由 `cache prepare` 产生完整指纹计划，`cache apply` 根据该计划执行。
保留可编辑构建、计划、原始输入、成片、字幕依据、预览帧和验收日志；清理对象限于经过成功任务
记录与保留构建验证的暂存依赖/编译缓存。目录叫 Resources 本身不构成可删除依据。
先审阅清单，再执行；禁止递归清理整棵用户素材目录。

```powershell
.\jianying.ps1 cache prepare --request C:\task\cache-request.json --out C:\task\cache-plan.json
.\jianying.ps1 cache apply --plan C:\task\cache-plan.json --audit C:\task\cache-audit
```

`jy-cache-cleanup-request/v1` 显式提供 `allowed_roots`、`protected_files`、
`regenerable_directories`、`reason` 与 `regenerable_from`。以命令校验返回的证据为准，
无法证明可再生或仍有引用的目录保留。清理共享链接不一定释放底层对象，最终报告应区分
逻辑字节、唯一分配空间和磁盘空闲变化。

## 完成边界

核对任务四个交付位、其它项目索引与目录不变、归档恢复哈希、当前工程完整媒体引用、原素材
哈希和元数据，以及去重后的原生预览/导出。列出已回收与仍保留的缓存，不用首页数量代替
存储检查，也不用磁盘逻辑大小代替实际分配空间。GUI 冷启动保存仍属于独立验收范围。
