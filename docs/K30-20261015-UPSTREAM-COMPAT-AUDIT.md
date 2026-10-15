# K30 上游对齐与兼容性审计（2026-10-15）

状态：**审核分支，仅准备；未修改 K29 内核实现、未启动 K30 编译、未刷机、未通过 K30 验收。**

## 0. 固定基线

- 设备 PLK110 / Stock A67 `PLK110_16.0.8.302(CN01)` / Android 16 / Linux 6.12.23。
- K29 冻结提交 `5a880cb223906bf2d84fcb4e4f574ba6f49dbdb8`，原成功运行 [#29](https://github.com/gugez3672-dotcom/Action_OnePlus_MKSU_SUSFS/actions/runs/38126080166)。
- ReSukiSU 源码 `6ec8d9a8a8be30878c388504cacf8ae7849c757b`（目前上游后续更名 BakaSU；K30 禁止自动切换到 main）。
- cctv18/susfs4oki `8dce4337bcd15807c5449bbeff6e02a967138db0`。
- 官方 KernelSU **已发布稳定版** v3.3.1 / `0c0fdb960178fa12d80d6cbcfdcb6ad8be6a865d` 仅为选择性 backport 的参考版本；不是替换 ReSukiSU 的直接基础。
- 比对的 cctv18 最新 `oki-android16-6.12`: `5f236a7b573c5a21ad0e5871ee96b63b89486596`。
- OnePlus manifest/common/SoC/modules、Clang、KMI/ABI、stock scheduler 与 PGuard 行为保持 K29 一致。

## 1. 已有的上游补丁：禁止重复回灌

| 语义修复 | K29 来源/实现 | cctv18 当前 | 操作 |
|---|---|---|---|
| SELinux 时间侧信道 #3877 | `scripts/port_ksu_3877_selinux_hide.py`，KSU `a85dcbc`，保留 ReSukiSU+SUSFS 兼容接口和原厂权限流 | 改动 SELinux 路径 | 不叠两套 Hook |
| SELinux 策略 RCU #3746 | `scripts/apply_plk110_selinux_correctness.py` | 随 KSU 同步 | 不重复 |
| AVTAB/XPERMS | 同上，KSU `0ff54fab` | 随 KSU 同步 | 不重复 |
| SUS_MOUNT clone_mnt race | `scripts/apply_susfs_post230_fixes.py` | 已包含 | 新基线须移除同一修复后处理 |
| SUS_KSTAT statfs f_flags/wrapper | 同上 | 已包含 | 新基线须移除同一修复后处理 |
| `is_statically` bool | 同上 | 已包含 | 新基线须移除同一修复后处理 |
| `backup_sepolicy` 生命周期 | `scripts/apply_plk110_selinux_correctness.py`，K29 内置持续保留 | 上游 SELinux 结构变化 | 明确生命周期和同步，禁止重复释放/悬挂引用 |

## 2. cctv18 最新的**不兼容**接口变化

1. K29 cctv 基础提供 `my_setprocattr()` 挂接原厂 SELinux `setprocattr`；K29 的 #3877 脚本查找并替换此函数。
2. 最新 cctv18 `50_add_susfs_in_gki-android16-6.12.patch` 改在 `selinux_lsm_setattr(u64 attr,...)` 内做备份策略检查。
3. 原有 `security_context_to_sid_with_policy` 以及部分双策略 helper 在 cctv18 KSU 接入补丁中重构为 `my_security_context_to_sid` 等接口。
4. `sel_open_handle_status` 从分支中的 `my_sel_open_handle_status` 包装方式向原函数嵌入检查调整，且从 `ksu_selinux_hide_enabled` 更正为 `ksu_selinux_hide_running`。
5. 所以将 cctv18 SHA 直接替换为 `5f236a7b` 后照旧运行 `port_ksu_3877_selinux_hide.py` / `apply_susfs_post230_fixes.py` 会失配；不得盲目 fallback 或继续构建。

## 3. K30 双候选路径与选择条件

**A（推荐优先）：K29 最小改动兼容路径**
- K29 固定 ReSukiSU + 固定 cctv 基础不变；已移植的 #3877 / RCU / AVTAB / SUS_MOUNT / SUS_KSTAT 不再重复。
- 独立移植并验证 SELinux status 根据 running 而不是 enabled 判定的行为；连同 fake_status 初始化/内存/锁顺序审计，不能仅修改布尔量。
- 已确认 #3871（Package Observer 延迟处理）在 K29 固定源码中缺失，列为第一项实质 backport 候选；#3865 的核心规避方式（iterate_dir() 后再打开文件）K29 已具有，不重复引入；#3873 的 SIDTAB 全局同步语义需与 K29 从 #3877 移植的双策略 SID 同步实现等价性确认，防止二次同步。
- OnePlus A67 固定 common `b2a876903b49` 的 `security/selinux/ss/services.c` 未定义 `context_add_hash`；BakaSU #623 以该函数存在为条件，当前不移植。BakaSU #597 `execve`/ksud 存在性修复只用于异常缺失 ksud 的路径，首轮不改变 D 系列管理器 SU 行为。
- 不加入实验性内核模块黑名单、不默认启用 shell SU 限制、不合并管理器/ksud 全量更新。
- 编译前用脚本断言每一项修复最终只存在一个实现。

**B（隔离实验）：cctv18 新一代集成路径**
- 从 K29 固定源码派生另一实验分支，升级 cctv18 到 `5f236a7b`，彻底重写 SELinux 适配：切换至其原生 `selinux_lsm_setattr` 入口、对接对应的 `my_security_*` ABI，移除不适用的 `my_setprocattr` 二次修改和已上游化 SUSFS 后处理。
- 确保适配的是 **ReSukiSU** 固定源码，而不是误将官方 KernelSU KSU patch 的内核源码覆盖 ReSukiSU。
- 校验 A67 原厂 `hooks.c` 是否具有此新入口，先 dry-run；失败即停止 B 路线，不进行脆弱偏移补丁。
- 审计假状态与权限错误返回的语义一致性、生命周期、SELinux 原厂许可路径、结构体 ABI。
- B 仅在完全通过 A 路线同等或更严格的验证，且显示实际价值时才替代 A 成为发布 K30。否则 K30 走 A，B 留实验分支。

## 4. 官方主线对比边界

- 官方正式发布 v3.3.1 约束 **稳定源码参考**，其后 main 的新特性（包括 2026-10-15 模块热安装）不在 K30 默认移植范围。
- #3877、#3746、AVTAB/XPERMS 已在 K29 移植：不得重复。
- #3882 shell_su_adb_only：可选安全策略，不是静态隐藏提升；保持 K29 提权路径默认兼容，且不能在没有完整 ksud/管理器协议适配时引入。
- #3881 module_blacklist / #3878 ksu_config：新行为与模块启动时序相关，K30 第一轮排除。
- BakaSU 最新 main 相比固定 `6ec8d9a8` 领先 75 commits，包含不同项目重构/更名：禁止整个替换。

## 5. K30 编译放行标准（全部必须通过）

1. **固定身份**：stock manifest/common/SoC/modules & config SHA、Clang build 14043575、PGuard boot 开放、原厂调度/ABI 均与 K29 相同。
2. **源码**：KSU 官方稳定版参考 tag 固定；cctv 每个所用补丁固定 SHA；清楚记录变更文件、原因和旧实现移除位置；`git diff --check`，所有预期函数、Hook、CONFIG 有且仅有一次；没有双重函数/旧新 ABI 混搭。
3. **编译**：patch dry-run + 静态语义检查 + 构建成功 + `System.map`/Image/ABI/KMI 与 stock 门禁 + AK3 校验和；构建成功并不代表可刷。
4. **启动**：真实用户数据环境正常启动、解锁后稳定、无循环重启，保留可回退 K29；绝不让自动化绕过保护分区/解锁条件。
5. **SU**：管理器身份、普通应用无法意外提权；D 系列管理器 Root 终端、脚本、中断/停止和被授权应用原行为保持。
6. **SUSFS**：非 Root 与 Root 双视角的 SUS_PATH Loop、SUS_KSTAT stat/statx/statfs/fdinfo、SUS_MOUNT/mountinfo/mnt_id 及跨用户 0/10/11 的一致性；启动早期与开机稳定后的差分。
7. **SELinux**：公开 status/context/access、真实/伪装策略、许可/拒绝返回码、时序及开关生命周期；无内存泄漏/悬挂引用/异常状态页。
8. **发布**：旧 #29 不修改，新候选单独编号、日志、SHA256、回退包；未完成编译和真机验收前一律称为 K30 候选而非发布版。

## 6. 当前状态与下一步

本分支只包含此审计清单（尚无 K30 代码修改）。先实施 A 路线的逐提交语义对照与最小 backport；B 路线只作为独立验证。完成静态审核后才能触发新构建，切勿把此审计分支视作编译产物。

## 7. 直接读取 A67 和 K29 上游源码后的精确补充

- A67 原厂 `security/selinux/hooks.c` 同时具有 `selinux_lsm_setattr(u64 attr,...)`（约 6390 行）和委托给它的 `selinux_setprocattr`（约 6588 行）。所以最新版 cctv18 的新入口本身存在；还须做实际补丁适配、完整语义审查，不能假设新旧接口可混用。
- A67 `security/selinux/ss/services.c` 存在 `sidtab_context_to_sid`，但没有 `context_add_hash` 的函数定义。BakaSU #623 有版本/能力判断，不应为本机移入不存在的哈希辅助调用。
- 固定 ReSukiSU `6ec8d9a8` 的 `kernel/manager/throne_tracker.c` 已注明在 `iterate_dir` 后延迟 file opens，和 KSU #3865 的核心策略重叠，**不应再叠加 #3865**。
- 固定 ReSukiSU `6ec8d9a8` 的 `kernel/manager/pkg_observer.c` 在 fsnotify 路径直接 `track_throne(0)`；官方 [#3871](https://github.com/tiann/KernelSU/commit/ab23091edfeddc774e1e880b0919b211808a193e) 改为 `task_work_add(..., TWA_RESUME)` 延迟扫描，可避免持有锁期间对 /data/app 扫描；K30 优先以此为单独可回退补丁，但需适配 ReSukiSU 的 `track_throne` API 和任务退出分支。
- 官方 [#3873](https://github.com/tiann/KernelSU/commit/a810677b847ba564c5f9d3fa0fbabe54794b8eef) 在备份策略解析成功后同步真实 sidtab；K29 #3877 双策略辅助函数已有 real/orig sid 同步路径，必须审查覆盖关系，**不能直接补一次额外的 sync**。
- 最新 cctv18 SELinux status 从 `enabled` 改为 `running`，且在原始 `sel_open_handle_status` 中写入；A 路线只移植具实证收益的状态同步修复，并审计 `fake_status` 生命周期；B 路线则须独立验证新的属性设置流、原始权限与错误返回。
- K30 优先级结论：**#3871 进第一轮补丁候选；status running 一致性进第一轮审计/候选；已包含的 KSTAT/MOUNT/#3865 不再移植；#623/#597 暂不加入；其余官方功能不改变默认运行行为**。
