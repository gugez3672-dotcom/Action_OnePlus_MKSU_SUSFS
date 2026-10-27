# SUSFS 519 在一加 A67 上的严格上下文适配

官方 519 的 `50_add_susfs_in_gki-android16-6.12.patch` 原件保持不变并保存到审查材料。原来使用 fuzz=3，导致三个 SUS_MAP 块错误落入 `smaps_rollup_open()` / `pte_is_pinned()`，已废止该做法。

现在所有 common 补丁使用 `git apply --check` 后再 `git apply`，不使用 GNU patch 的 fuzz、忽略上下文或 unidiff-zero 模式。任何非零 fuzz 的成功日志也会被守卫拒绝。

## 六个被替换的官方块

`scripts/susfs_patch_policy.py` 精确列出以下文件/块号，并核对 show_smap/show_smaps_rollup 的 hunk 头。其余官方块原文保留；移除的六块由 `patches/PLK110_A67_SUSFS_519_compat.patch` 替代。

| 官方文件 | 官方块号 | A67 适配 |
|---|---|---|
| fs/exec.c | 1 | 同样的 SUSFS 头文件引入，以 A67 实际 include 列表严格定位 |
| fs/proc/base.c | 1 | 同样的 SUSFS 头文件引入，以 A67 实际 include 列表严格定位 |
| security/selinux/hooks.c | 1 | 同样的两个 extern 声明，以 A67 的 selinux_state 定义严格定位 |
| fs/proc/task_mmu.c | 4 | show_smap 在 vma_pages 判断前对隐藏 VMA 返回 0 |
| fs/proc/task_mmu.c | 5、6 | 在 A67 旧 do/for_each_vma 结构中的三条 gather 路径分别过滤隐藏 VMA，last_vma_end 始终更新 |

这里没有给 A67 加原本不存在的 dma-buf include，也没有把新内核的 rollup 循环结构搬回旧源码。两条 pagemap_read 官方块保留并通过严格上下文匹配。

## 语义与守卫

- show_smap 的隐藏判断位于该函数体内、统计和 pad 处理之前。
- show_smaps_rollup 的普通循环、锁竞争后 case 1/2、锁竞争后 case 4 三条路径，都只对可见 VMA 调用 smap_gather_stats；无论是否隐藏，均更新 last_vma_end，保持继续迭代/重获锁的既有行为。
- SUS_MAP 关闭时，预处理后的三条原厂统计调用和游标更新保持原有流程。
- `scripts/c_source_checks.py` 按具名 C 函数体检查，忽略注释/字符串中的括号；禁止 SUS_MAP 或 bypass_orig_flow 出现在 smaps_rollup_open / pte_is_pinned。
- 本地与 CI 都运行 12 项源码破坏反向检查，结束后核对原始字节恢复；包括两个错误函数落点、遗漏 rollup 过滤、破坏游标更新和魔数返回成功等回归。

源码文件副本检查通过仍不代表内核已编译或运行；内存统计、锁竞争场景和实际隐藏效果留待后续编译/实机验收。
