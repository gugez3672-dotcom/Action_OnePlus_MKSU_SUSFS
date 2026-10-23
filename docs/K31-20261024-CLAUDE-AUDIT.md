# K31 只读代码审计报告（Claude，2026-10-24）

> 用途：整份交给 GPT 修 K31。本报告所有结论都标注了证据级别：**已写代码 / 已静态检查 / 已在真实源码 dry-run（replay）/ 已真实编译 / 已真机验证**。本轮**没有任何一项达到"已真实编译"或"已真机验证"**。

---

## 1. 确定结论

**K31 候选包（ZIP `96b3a5a7…`）现状不能进入编译前准备，存在 5 个 P0 阻断。** 在真实 K30 构建定义和真实固定源码上复现：

| 阶段 | K31 候选包现状 |
|---|---|
| 生成器 `prepare_k31_candidate.py` 跑真实 K30 | **直接报错退出**（P0-1） |
| 绕过 P0-1 后，真实源码重放 | `#3877 port` 失败、`K30 fixes` 失败、`K31 verify` 失败、Configure 步骤 PGuard 断言失败（P0-2～P0-5） |
| ZIP 自带 6 个单测 | 全部通过——但全是 mock，**没有一个能发现上面任何一个真实失败** |

**更重要的发现（决定 K31 路线）：**

1. cctv18 SUSFS `8dce4337 → 5f236a7b` 的**非 SELinux 内核代码与 K30 完全等价**：真实源码树逐文件对比，`fs/namespace.c`、`fs/stat.c`、`include/linux/susfs.h` 等全部字节相同；差异只有 `fs/exec.c` 删一个未使用的 extern、`fs/statfs.c` 括号换行、`fs/susfs.c` 多一个 `#include`。也就是说 **K30 手工回补的 5 项与上游逐字等价，升级 pin 在 SUSFS 功能上收益为零**（K30 树跑 K31 自己的 `k31_verify_susfs.py` 全部 OK 也印证这一点）。
2. 升级带来的**唯一实质变化是 SELinux 隐藏实现被换掉**，而新实现**倒退**：
   - `attr/current` 路径变成"先查备份策略、失败即提前返回，成功再查真实策略"——这正是 KernelSU **#3877 修掉的时间侧信道**；K30 用的是 #3877 的单次双策略并行解析 `ksu_security_context_to_sid_with_policy_ex`。
   - `selinuxfs` 隐藏路径只写备份 sidtab，**没有 #3873 的全局 sidtab 同步**（simonpunk 官方 10-19 的 `f4466db` 才补上；cctv18 `5f236a7b` 没有）。K30 的包装函数有该同步。
3. simonpunk 官方 GitLab `gki-android16-6.12` 在 10-15 之后又走了两步：`f4466db`（补 #3873）和 `1ac091c`（**删掉 SUSFS 自己的 SELinux 隐藏实现，改为 hooks.c 只转发给 KernelSU 的 `my_setprocattr`**）。这恰好就是 K30 现在的结构。cctv18 `5f236a7b` 只是一个已被上游自己淘汰的过渡版本。
4. Baka-SU（ReSukiSU 后继）在 `48fa4bb7`（10-10）**对 SUSFS 构建直接 `$(error Please wait susfs update.)`**，tip `dac2d186` 仍如此——**整体换 Baka-SU 不可能**，只能逐条 cherry-pick。
5. K30 的 #3871 移植**语义不等价**：任务回调里调用的是 `track_throne(0)`，在 ReSukiSU `6ec8d9a8` 中它会再把扫描丢给 init 进程（pid 1）的 task_work，扫描仍发生在 rename 返回之后——上游 #3871 注释明确说"扫描必须在 rename 返回前完成，否则管理器可能在加冕前被打开"。这与 Daily Notes 偶发"未安装/无内核通信"直接相关。

**推荐路线 A（已写代码 + 已在真实源码 replay 全部通过）：**
保持 K30 的 SUSFS pin `8dce4337` + 原五项回补 + #3877/#3746/AVTAB/K30 修复不变，K31 只新增 4 个经核实的 KernelSU 内核修复：

| # | 修复 | 来源 |
|---|---|---|
| 1 | #3871 任务回调同步扫描（`TRACK_THRONE_FORCE_SYNCHRONOUS`） | 上游 ab23091 / Baka 8450dd28 |
| 2 | #3733 扫描使用 `ksu_cred`、不触发 fsnotify / 不改 atime（#1 的前置） | 上游 6ebd714c / Baka a855ec67 |
| 3 | `get_managers` ioctl 不在 `rcu_read_lock` 内 `copy_to_user` | Baka 3d1185d8 |
| 4 | #3924 init.rc 按挂载路径识别 | 上游 469c4282 |

replay 结果：**common 树与 K30 字节相同**（KMI/模块 CRC/公开 IKCONFIG 不应有任何变化，但仍须编译门禁确认），改动只落在 KernelSU 6 个文件，164 行统一 diff 见 `K31A_vs_K30_source.diff`。严格管理器、PGuard、SUSFS、#3877 全部静态门禁通过。

**证据级别总表**

| 项 | 已写代码 | 已静态检查 | 已真实源码 replay | 已编译 | 已真机 |
|---|---|---|---|---|---|
| ZIP 原 K31 候选 | 是 | 是 | **失败** | 否 | 否 |
| 路线 A（本报告附带） | 是 | 是 | **全部通过** | 否 | 否 |

---

## 2. 实际复现环境

- **K30**：`gugez3672-dotcom/Action_OnePlus_MKSU_SUSFS` 克隆到隔离 scratchpad，worktree 检出 `2fdd663bdae89179c1aad42dda72cb865f5bb92c`，`git rev-parse HEAD` 已核对；`baselines/PLK110_16.0.8.302_stock.config` SHA256 = `e239b50c…`（与工作流一致）。
- **K31 ZIP**：SHA256 `96b3a5a7d6555975b679a1d0dc072a758c8d1b8073fe7dd6d6094da3b4d258f1`（与交接一致）；`checksums.sha256` 9 个文件全部 OK；全部文件已逐行阅读。
- **固定源码（全部按 SHA 取得并核对）**：
  - OnePlus common `b2a876903b495c444a94b16f50d1463ffe953957`（`OnePlusOSS/android_kernel_common_oneplus_sm8850`，稀疏检出 fs/ include/ security/ block/ kernel/ mm/ 及 SUSFS 补丁涉及的全部 25 个文件）
  - ReSukiSU `6ec8d9a8`、Baka-SU tip `dac2d186`
  - cctv18 susfs4oki `8dce4337`、`5f236a7b`（= 分支 tip）
  - tiann/KernelSU `a85dcbc`（#3877）…`6d31a613`（main tip）
  - **simonpunk 官方 GitLab 可访问**：`gki-android16-6.12` tip `746b92a`、`-dev` tip `d4d1906`（GPT 端无法访问的部分本次已补齐）
- **replay 方法**：脚本 `scripts/audit_replay.sh` 逐条复现工作流中所有**修改源码**的步骤（vmlinux_oki、stock trust、ReSukiSU 接入、SUSFS 50 补丁 `-F0` 诊断 + `-F3` 实际、post230、#3877 port、SELinux correctness、K30 fixes、strict manager + PGuard 配置、stock IKCONFIG）。**未复现**：repo sync、Clang 下载、Kleaf `stamp.bzl`、Bazel 编译及之后所有产物门禁。
- **对照组**：先跑 K30 模式，全部步骤 rc=0，与 K30 Actions run 38756902685 一致，证明 harness 可信，再跑 K31。
- Windows 环境差异已消除：所有仓库 `core.autocrlf=false` 强制 LF；Python 写文件经 shim 强制 LF/UTF-8；`include/uapi/linux/netfilter/xt_*.h` 大小写冲突文件与本审计无关，已从 diff 检查排除。

---

## 3. 问题清单（按严重度）

### [P0-1] 生成器在真实 K30 工作流上必然崩溃
- **位置**：ZIP `scripts/prepare_k31_candidate.py:32`
- **代码**：`content = only_one(content, K30_SUSFS, K31_SUSFS, 'SUSFS pin')`
- **触发**：真实 K30 工作流里 `8dce4337…` 出现两次——第 42 行 `SUSFS4OKI_COMMIT:` 和第 336 行 post230 步骤 heredoc 里的 `base_okI=cctv18/susfs4oki@8dce4337…`。`only_one` 要求恰好一次。
- **实测**：`RuntimeError: SUSFS pin: expected one original and no preexisting replacement`
- **影响**：K31 审核工作流根本生成不出来；6 个 mock 单测的样例工作流只含一次 pin，所以测不出。
- **修复**：见第 6 节路线 A——不再改 SUSFS pin。若坚持路线 B，必须先删旧步骤再按 `SUSFS4OKI_COMMIT: ` 键锚定替换。
- **验证**：在真实 K30 checkout 上跑生成器（不是 mock）。

### [P0-2] cctv18 `5f236a7b` 的 SELinux 契约变化导致 #3877 移植失败；若"绕过"则 #3877、#3873 双倒退
- **位置**：K30 `scripts/port_ksu_3877_selinux_hide.py:65` `assert "security_context_to_sid_with_policy" in hooks`
- **触发**：新 50 补丁把 `hooks.c`/`selinuxfs.c` 改为调用 common 自带的 `my_security_context_to_sid` / `my_security_sid_to_context` / `my_security_context_str_to_sid` / `my_security_compute_av_user`（定义在 `ss/services.c`），删掉了 `my_setprocattr`、`my_sel_open_handle_status`、`security_context_to_sid_with_policy` 引用。
- **实测**：replay `ksu3877_port rc=1 AssertionError`。
- **若 GPT 删掉 #3877 步骤强行编译**（链接可能能过，已核对所有 extern 都有定义）：
  1. `selinux_lsm_setattr` 新代码（K31 树 `hooks.c:6446`）：`my_security_context_to_sid(backup_sepolicy…)` 失败就 `return fake_error`，成功再 `security_context_to_sid(...)`——两种上下文耗时不同，就是 #3877 的时间侧信道原样回归。
  2. `selinuxfs.c:683` 只写备份 sidtab，无全局同步——#3873 回归（官方 `f4466db` 的提交说明原话就是"still missing … the global sidtab has to be synced"）。
- **影响**：Duck Detector 的 `attr/current` 时序探针正是这条路径；K30 的实现与上游 #3877 逐行一致（见第 5 节）。
- **修复**：路线 A 不升级 SUSFS SELinux 部分。
- **验证**：replay 中 `ksu3877_port` 必须 rc=0，且 `hooks.c` 必须含 `ksu_security_context_to_sid_with_policy_ex`。

### [P0-3] K30 补丁器的 K31 兼容改写永远走不到
- **位置**：生成后的 `scripts/apply_k30_upstream_fixes.py:94-95`（原文件同位置）
- **代码**：`if "static int my_sel_open_handle_status(" not in sel: raise RuntimeError("K29 SUSFS SELinux status hook missing")`
- **触发**：新 SUSFS 已把 `my_sel_open_handle_status` 并入原 `sel_open_handle_status`。ZIP 的 `rewrite_k30_upstream_patcher` 只改了后面的 `replace_once`，前置检查先抛异常。
- **实测**：replay `k30_upstream_fixes rc=1`，因此 #3871 也没有被打上（`k31_verify_kernel` 报 `K30 #3871 task-work deferral` 缺失）。
- **修复**：路线 A 下 K30 补丁器原样使用（K30 已验证）。

### [P0-4] 三处分支名门禁漏改，Configure 步骤必然失败
- **位置**：K30 工作流第 403 行（shell）、第 427 行（Python）、第 511 行（shell）；ZIP 生成器 `prepare_k31_candidate.py:52-55` 只替换了 `github.ref_name == '…'` 和 push 分支。
- **实测**（用真实生成的 PGuard 源码执行第 427 行逻辑）：
  - 分支 `k30-…`：`missing: []`
  - 分支 `k31-review-only`：**`missing: ['boot']` → `AssertionError: PGuard static partition coverage missing: ['boot']`**
- **影响**：第 403 行 boot 非 HARD 的 5 条断言被**静默跳过**；第 427 行 Configure 失败；第 511 行 SELinux 证据产物静默不归档。正是 K28 那类"分支条件静默跳过"的问题。
- **修复**：改为显式 profile（见附带 `prepare_k31_candidate.py` 与 `review/K31_workflow_vs_K30.diff`）：
  ```diff
  -          if [ "$GITHUB_REF_NAME" = "resukisu-pguard-v2-selinux-hardening-boot-open" ] || [ "$GITHUB_REF_NAME" = "k30-20261015-ksu-susfs-audit" ]; then
  +          if [ "$PLK110_PROFILE" = "k31" ]; then
  -          if __import__('os').environ.get('GITHUB_REF_NAME') in ('resukisu-pguard-v2-selinux-hardening-boot-open', 'k30-20261015-ksu-susfs-audit'):
  +          if __import__('os').environ['PLK110_PROFILE'] == 'k31':
  ```
  所有 `if: github.ref_name == …` 步骤条件删除（K31 工作流本身就是 profile，必需步骤无条件执行，失败即停）；生成器结束时断言工作流中**不再含** `k30-20261015`、`GITHUB_REF_NAME`、`github.ref_name ==`，且每个必需补丁步骤恰好出现一次、顺序正确。
- **验证**：路线 A replay 中 `configure_yaml rc=0`（执行的是从生成 YAML 中原样抽出的 run 块）。

### [P0-5] `k31_verify_kernel.py` 放在 Configure 之前
- **位置**：ZIP `prepare_k31_candidate.py:56-69`（插在 `Configure frozen kernel 11 baseline + Partition Guard v2` 之前）；`k31_verify_kernel.py:14,21` 读取 `Kbuild` 的 `KSU_MANAGER_PACKAGE` 与 `block/plk110_partition_guard.c`。
- **实测**：`FileNotFoundError: …block\plk110_partition_guard.c`；`KSU_MANAGER_PACKAGE`、固定证书也都是 Configure 才写入。
- **修复**：验证步骤移到 Configure 之后、`Publish exact A67 stock IKCONFIG` 之前（附带生成器已如此）。
- **验证**：路线 A replay `k31_verify_yaml rc=0`，14 项 OK。

### [P1-1] K30 #3871 移植语义与上游不一致：扫描仍在 rename 返回后才发生
- **位置**：K30 `scripts/apply_k30_upstream_fixes.py:52`（生成的 `pkg_observer.c` 任务回调中 `track_throne(0);`）
- **原因**：ReSukiSU `6ec8d9a8` 的 `track_throne(flags)` 在没有 `TRACK_THRONE_FORCE_SYNCHRONOUS` 时调用 `ksu_run_in_init_if_possible()`（`compat/kernel_compat.c:166`），把扫描再挂到 **init 进程的 TWA_RESUME task_work**；init 通常睡在 `epoll_wait`，下次返回用户态才执行。K30 的链路是 fsnotify → 渲染任务 task_work → **再排到 init** → 扫描，与移植前的延迟本质相同。
- **上游证据**：ab23091 注释"the scan must finish before the rename returns, or the manager can be opened before it is crowned"；Baka 8450dd28 回调为 `track_throne(TRACK_THRONE_FORCE_SYNCHRONOUS)`，另有 Baka f6513993 专门把 pkg_observer 改为同步。
- **影响**：管理器安装/重装后可能在加冕前被启动 → 该进程拿不到 `[ksu_driver]` fd，整个进程生命期显示"未安装"，与 Daily Notes 偶发"不能和内核通信"一致（另见 [[manager-kernel-fd-race]] 分析）。
- **修复**（已写代码）：任务回调改为同步；fsnotify 内的失败回退**保持** `track_throne(0)`（异步，不在持锁上下文做全盘扫描——比上游内联同步回退更安全）。
- **必须与 P1-2 一起合入**：同步后扫描在 system_server 上下文执行。

### [P1-2] 缺少 #3733：管理器扫描未切换凭据，且产生 fanotify/atime 副作用
- **位置**：K30 `KernelSU/kernel/manager/throne_tracker.c:193,299,422`、`manager/apk_sign.c:230-237`
- **原因**：`6ec8d9a8` 用 `filp_open()` 打开所有 `/data/app/*/base.apk` 后才置 `FMODE_NONOTIFY`（打开阶段的 fanotify 权限事件已发生），未带 `O_NOATIME`；`do_track_throne` 不切换凭据。上游 6ebd714c（Baka a855ec67）用 `dentry_open(… | __FMODE_NONOTIFY)` + `O_NOATIME`，并在 `do_track_throne` 内 `override_creds(ksu_cred)`。上游 #3871（10-08）依赖 #3733（09-20）。
- **核对**：`ksu_cred` 已在 `include/ksu.h:11` 导出、`core/init.c:229` 初始化；6.12 有 `__FMODE_NONOTIFY`（`include/linux/fs.h:3646`）与 `dentry_open(const struct path*, …)`；`do_track_throne` 两处提前 `return` 都在 `INIT_LIST_HEAD` 之前，所有 `goto out/prune` 都在其后，`override_creds` 放在 `INIT_LIST_HEAD` 之后能覆盖全部路径（脚本中有断言）。
- **修复**：只移植 GKI 6.12 需要的部分（helper + 3 处调用 + 凭据），不带 Baka 的非 GKI Kbuild/compat/lsm_hooks 改动。

### [P1-3] `get_managers` ioctl 在 RCU 读锁内 `copy_to_user`
- **位置**：K30 `KernelSU/kernel/manager/manager.c:163-189`（`ksu_handle_get_managers_cmd`）
- **原因**：`copy_to_user` 可能触发缺页睡眠，不允许在 `rcu_read_lock` 临界区。Baka 3d1185d8（#423）附有 `BUG: sleeping function called from invalid context` 调用栈。
- **触发**：Daily Notes `KernelRepository.getManagerRuntimeInfo()` → `NativeApi.getManagersList()` 每次刷新都会调用。
- **修复**：Baka 3d1185d8 在 K30 树 `git apply --check` 干净通过；ioctl 输出布局不变，**D 系列无需改动**。

### [P1-4] 测试不足以检测真实错误
- **位置**：ZIP `tests/test_candidate.py`（6 个 mock）
- **事实**：全部通过，但真实输入下 P0-1/2/3/4/5 一个都没测到。
- **修复**：测试必须以**真实 K30 工作流文件**和**真实 replay**为输入（附带 `audit_replay.sh` 可作为模板）；生成器自身在结尾做 fail-closed 审计（附带版本已实现：残留分支门禁、必需步骤缺失/重复、顺序错误均抛异常）。

### [P1-5] 生成器未校验 K30 SHA
- **位置**：ZIP `prepare_k31_candidate.py:93-112`
- **修复**：`git rev-parse HEAD == 2fdd663…` 且 `.github scripts baselines` 无本地修改（附带版本 `verify_k30_checkout()`）。

### [P2-1] SUSFS 50 补丁依赖 `-F 3` 模糊匹配（K30 已有，非新问题）
- **位置**：K30 工作流第 295-296 行。
- **实测**：`-F0` 下唯一失败为 `security/selinux/hooks.c` Hunk #1，`-F3` 下 "succeeded at 109 with fuzz 2"。原因是 A67 源码没有上游上下文中的 `ANDROID: selinux_state is part of the KMI…` 注释。落点核对正确（3 行 `extern` 声明紧跟 `struct selinux_state selinux_state;`）。K30/K31 相同。
- **建议**：保留 `-F3`，但把 dry-run 输出存档并断言"恰好且仅有 hooks.c Hunk #1 fuzz 2"，其它任何 fuzz 都失败：
  ```bash
  patch --dry-run -p1 -F 3 < 50_add_susfs.patch | tee "$GITHUB_WORKSPACE/artifacts/SUSFS_DRYRUN.txt"
  test "$(grep -c 'with fuzz' "$GITHUB_WORKSPACE/artifacts/SUSFS_DRYRUN.txt")" = 1
  grep -B1 'with fuzz 2' "$GITHUB_WORKSPACE/artifacts/SUSFS_DRYRUN.txt" | grep -q 'security/selinux/hooks.c'
  ```

### [P2-2] #3924 的代价与适用性
- ZIP `k31_ksu_compat.py` 在真实树上 `ported`，结果与上游 469c4282 等价，K30 的 `/init.rc`、`/system/etc/init/hw/init.rc` 两条路径保留。代价：init 读每个常规文件都要 `d_path`，直到 hook 停用，可忽略。A67 未必使用 bind mount 的 init.rc，收益在于健壮性。已并入附带 `apply_k31_kernel_fixes.py`；`k31_ksu_compat.py` 可删除，避免两份实现。

### [P2-3] 生成的审核工作流仍保留 push 触发
- ZIP 版本把 push 分支换成 `k31-review-only`，一旦被移入 `.github/workflows` 并推该分支就会编译。附带版本删除 push 触发，仅保留 `workflow_dispatch`，名称前缀 `REVIEW-ONLY`。

### [P2-4] 溯源记录
- ZIP 版 `K30_UPSTREAM_FIXSET.txt` 写 `susfs_selinux_status=cctv18@5f236a7b`，而该修复实际不再由 K30 补丁器完成；路线 A 下 K30 原文成立。附带版本把 K31 三个脚本也存入 artifacts，并写 `K31_KERNEL_FIXSET.txt`。

### [P3-1] `avtab_for_each` 宏尾多余分号（#3701）
- K30 `selinux/sepolicy.c:88`。宏**未被任何代码使用**，无运行影响；可不动，或随下次同步顺手修。

---

## 4. 提交级上游对照表

图例：**K30 有** / **K31A 新增**（本报告路线 A）/ **不移植**（原因）/ **N/A**（不适用）/ **D 系列**（需管理器/ksud 配套）

### 4.1 SUSFS（cctv18 `oki-android16-6.12` `8dce4337..5f236a7b`，10 commits，4 files）

| SHA | 日期 | 内容 | K30 | 决策 |
|---|---|---|---|---|
| d4f2339 | 09-17 | susfs.c `#include <linux/security.h>`（旧 GKI 编译） | 无 | N/A：6.12 K30 已能编译；可选，无行为变化 |
| 2697b9f | 09-18 | SUS_MOUNT clone_mnt 竞态 | **有**（post230 `c8f64e41`） | 字节等价，不重复 |
| fdf7077 | 09-23 | KernelSU 侧 sync（10_enable 补丁） | — | 不移植（ReSukiSU 自带集成） |
| fcdf613 | 09-24 | SUS_KSTAT statfs f_flags | **有**（`2528bdb0`） | 字节等价 |
| a3f44b6 | 09-25 | rename calculate_f_flags_wrapper | **有**（`889b537e`） | 字节等价 |
| ed5e805 | 09-25 | statfs_by_dentry wrapper | **有**（`ebbc112e`） | 等价（仅括号换行） |
| a767c28 | 09-26 | `is_statically` bool | **有**（`b213c541`） | 字节等价 |
| 7fa2e34 | 10-12 | 同步 KSU main（含 SELinux 重构） | — | 已被 f5194b7 回滚 |
| f5194b7 | 10-14 | revert | — | — |
| 5f236a7 | 10-15 | 同步 KSU main：SELinux 改 `selinux_lsm_setattr` 内联 + `my_security_*` | K30 用 #3877 双策略 | **不移植**：#3877 时间侧信道与 #3873 双倒退（P0-2） |

### 4.2 SUSFS 官方 simonpunk GitLab `gki-android16-6.12`（cctv18 未跟进部分）

| SHA | 日期 | 内容 | 决策 |
|---|---|---|---|
| acb92d4 | 10-15 | = cctv18 5f236a7（仅偏移不同，已比对：susfs.c/.h/def.h 哈希相同） | 同上，不移植 |
| bd27568 | 10-18 | 补丁重定位到 android16-**6.12.92** | N/A：本机 6.12.23 |
| f4466db | 10-19 | selinux_hide 补全全局 sidtab 同步（对应 KSU #3873） | K30 已有等价语义（`_ex` 中 `!orig_rc` 时同步） |
| 291d571 | 10-19 | exec.c 适配 module preinit（KSU #3907） | D 系列 + #3907，不移植 |
| 1ac091c | 10-19 | SUSFS 删除自身 SELinux 实现，hooks.c 转发 KSU `my_setprocattr` | 方向即 K30 现结构；完整采用需同步 KSU 侧，不在 K31 |
| 9c9f19d | 10-19 | KSU 侧 sync（#3924） | K31A 已移植 #3924 |
| 746b92a | 10-23 | README | — |

09-04～09-16 官方修复（cc99f24、131c1ef、4917550、2a764bb、b1c1dc6、ae2526c、df186fe 等）已在 cctv18 `8dce4337` 内；K31 的 `k31_verify_susfs.py` 对 K30 树全部 OK 佐证（KSTAT bit8、NULL 早返回等）。

### 4.3 KernelSU 官方（`a85dcbc..6d31a613`，30 commits；仅列触及 kernel/ 的 9 个 + 范围外相关）

| SHA | PR | 内容 | K30 | 决策 |
|---|---|---|---|---|
| 6e386044 | #3878 | ksu_config 强制功能值 | 无 | 不移植：需 ksud/boot-patch，D 系列 |
| f895b80a | #3881 | 启动期 module_blacklist | 无 | 不移植：模块启动时序 |
| 0a1f3ff7 | #3882 | shell_su_adb_only | 无 | 不移植：改变提权默认、需 ksud |
| 0faec0cc | #3907 | module preinit（71 文件 +8817） | 无 | 不移植：ksud/早期启动/SUSFS 备份策略一体 |
| 96770dfb | #3911 | Android 17 QPR3 | — | N/A |
| e9ef3540 | #3917 | Linux 6.19+ | — | N/A |
| 0f58f12c | #3916 | ksys_unshare → ksyscall | — | 不移植：依赖 ksyscall 基础设施（Baka e88c7eee/9be0f347），纯重构 |
| 605e4269 | #3920 | #3881 开发者开关 | — | 随 #3881 不移植 |
| 469c4282 | #3924 | init.rc 挂载路径 | 无 | **K31A 新增** |
| 200818ca | #3901 | 模块热安装 | — | D 系列（无内核改动） |
| 其余 19 个 | — | manager/ksud/文档/依赖 | — | D 系列或无关 |

范围外但与 ReSukiSU `6ec8d9a8`（09-17）之后相关的 KSU 内核提交：

| SHA | PR | 内容 | K30 | 决策 |
|---|---|---|---|---|
| 6ebd714c | #3733 | 扫描 APK 不触发 fsnotify/atime + ksu_cred | **无** | **K31A 新增**（#3871 前置） |
| 95b87145 | #3738 | syscall_hook_manager / patch_memory 编译错误 | — | N/A（K30 已能编译，SUSFS inline hook 路径） |
| 11f41511 | #3742 | ksyscall 接线 | — | 不移植（基础设施） |
| 87db8315 | #3701 | avtab 宏分号 | 有缺陷但宏未使用 | P3 可选 |
| bd82a853 | #3746 | RCU policy | **有**（K29 #26） | 不重复 |
| 623eba3e | #3750 | riscv64 | — | N/A |
| 0ff54fab | — | AVTAB/XPERMS | **有** | 不重复 |
| cd4af89c | #3800 | 避免重复触发 service 阶段 | 无 | 可选 P2：仅当设备 mount_all 两次；需日志确认再加 |
| 26c45e27 | #3865 | iterate_dir 死锁 | 等价已有 | 不重复 |
| 6b5f55bd | #3868 | 固定管理器包名 | K30 用 `KSU_MANAGER_PACKAGE` | 等价 |
| a810677b | #3873 | sidtab 同步 | **语义已有**（#3877 `_ex`） | 不重复 |
| a05b1d7f | #3874 | strrchr 重构 | 行为等价 | 不移植 |
| ab23091e | #3871 | task_work 延迟扫描 | **有但语义不全**（P1-1） | **K31A 修正** |
| df03912f | — | 保持原权限检查顺序 | 被 #3877 取代 | K30 = #3877 版本 |
| a85dcbcf | #3877 | 时间侧信道 | **有**，逐行一致 | 保持 |

### 4.4 Baka-SU（`6ec8d9a8..dac2d186`，82 commits，25 个触及 kernel/）

| SHA | 内容 | 决策 |
|---|---|---|
| 3d1185d8 | get_managers 不在 RCU 内 copy_to_user（#423） | **K31A 新增** |
| a855ec67 | = KSU #3733 | **K31A 新增**（仅 GKI 6.12 部分） |
| f98b7a6d | 去掉 bitmap，packages.list 变化总是搜索管理器 | 暂不移植：改变管理器识别策略，留给"未安装"专项 |
| 8af210f8 / e88c7eee / 9be0f347 | 编译修复 / ksyscall | 不移植 |
| a93bc59c / 769f8d71 / f397410c | #3701 / #3746 / AVTAB | 后两项 K30 已有 |
| 379c761b / 48fa4bb7 | SUSFS 维护警告 / **SUSFS 构建直接报错** | 证明不能整体切换 Baka |
| 325265c5 | riscv64 | N/A |
| f6513993 | pkg_observer 同步 | 与 K31A #3871 修正同义 |
| c4bdcaae | 3.6- dentry_open | N/A |
| b0fa24df | init 读 allowlist 时提权（Android 17） | N/A（A16），如升 A17 需重评 |
| 8770c7e3 | = KSU #3800 | 可选 P2 |
| 97c102ba / 9dbce02e | 项目更名 BakaSU | **不移植**：会破坏工作流 `REPO_NAME := ReSukiSU` 断言与版本串门禁 |
| ba8cfa50 / 8450dd28 / fa12ffde | #3873 / #3871 / #3877 | 已有 / K31A 修正 / 已有 |
| 969de3d0 | 原权限检查顺序 | 被 #3877 取代 |
| 64814408 | ksud 不存在时不处理 su execve（#597） | 暂不移植（与 K30 审计一致，只影响 ksud 缺失路径） |
| d7260ca1 | context_add_hash（#623） | N/A：A67 `services.c` 无 `context_add_hash`（已 grep 确认） |
| 522081c5 | 32 位用户态兼容（#612，20 文件） | 不移植：arm64 64 位用户态，改动面大 |

---

## 5. K30 原有补丁回归风险清单（检查证据）

| 项 | 检查方法 | 结果 |
|---|---|---|
| #3877 | K30 树 `hooks.c` `my_setprocattr` 与上游 a85dcbc `selinux_hide.c:232` 逐段对比；`ksu_security_context_to_sid_with_policy_ex` 与上游 `security_context_to_sid_with_policy` 对比 | 逐行一致（含 SETCURRENT 先检、dual parse、`!orig_rc` 全局同步）。路线 A 不改 |
| #3873 | 上游 a810677 diff vs K30 包装函数 | selinuxfs 隐藏路径经 `security_context_to_sid_with_policy` → `_ex(..., NULL, NULL)`，`!orig_rc` 时同步全局 sidtab，语义覆盖 |
| #3746 / AVTAB | K30 replay 中 `selinux_correctness` 断言 | 通过；路线 A 不改 |
| #3871 | K30 `pkg_observer.c` vs 上游 ab23091 / Baka 8450dd28 | **不等价**（P1-1），K31A 修正 |
| SUSFS 五项 | K30 与 cctv18 5f236a7b 生成树逐文件 cmp | namespace.c / stat.c / susfs.h 等字节相同 |
| SELinux status running | K30 `selinuxfs.c:252` | 已为 `ksu_selinux_hide_running`；路线 A 不改 |
| 严格管理器 | 路线 A replay 执行生成 YAML 中原样 Configure 块；`k31_verify_kernel.py` | 包名、证书 `7b6fcd9e…`、无动态管理器、reboot 魔数门禁、4 个 info ioctl `manager_or_root` 全部 OK |
| PGuard | 同上；第 427 行 Python 覆盖检查 | boot 非 HARD、init_boot/vendor_boot/xbl HARD、GPT 范围全部 OK |
| 公开 IKCONFIG | replay `stock_ikconfig rc=0` | 与基线 SHA `e239b50c…` 一致 |
| common / KMI | `diff -rq` K30 vs K31A common 树 | **完全相同**；K31A 只改 KernelSU 内置代码，无导出符号变化。仍须编译后 `Module.symvers` CRC 门禁确认 |
| Clang / 源码 pin | K31A 工作流 diff | 未改动 |
| D 系列授权 | ioctl 布局 | 3d1185d8 输出布局不变；无 UAPI 变化 |
| Duck `attr/current` +104 ns | 代码对照 | K30 = 上游 #3877 原样实现；无同机原厂对照前**不能**归因，也**不应**为此改 SELinux 逻辑。建议真机测量：同一系统下关闭 selinux_hide（`ksu_selinux_hide_enabled`）测一次 A−B 基线，再开启测一次，差值才可归因 |

---

## 6. 给 GPT 的修复任务清单（按顺序）

1. **放弃 SUSFS pin 升级（路线 A）**：`SUSFS4OKI_COMMIT` 保持 `8dce4337`，`Backport audited SUSFS post-2.3.0 fixes` 步骤保留原样。在 K31 文档中写明证据：5f236a7b 非 SELinux 部分与 K30 字节等价（附 replay 方法），SELinux 部分导致 #3877/#3873 倒退。
2. **用附带的 `scripts/prepare_k31_candidate.py` 替换 ZIP 版生成器**：
   - 校验 K30 SHA 与工作区干净；
   - 删除 push 触发，加 `PLK110_PROFILE: k31`；
   - 删掉所有 `github.ref_name` 步骤条件，第 403/427/511 行改为 profile；
   - 插入 `K31 kernel fixes` 步骤（K30 fixes 之后、Configure 之前）与 `K31 static invariants` 步骤（Configure 之后）；
   - 结尾自审：残留分支门禁 / 必需步骤缺失或重复 / 顺序错误一律失败。
   生成结果与 K30 的差分见 `review/K31_workflow_vs_K30.diff`（113 行）。
3. **用附带的 `scripts/apply_k31_kernel_fixes.py` 替换 `k31_ksu_compat.py`**：内含 #3871 同步、#3733、get_managers RCU、#3924 四项，全部精确前像、写入前全部断言、重复执行即失败。源码效果见 `K31A_vs_K30_source.diff`（164 行，仅 KernelSU 6 个文件）。
4. 保留 ZIP 的 `k31_verify_susfs.py`、`k31_verify_kernel.py`（在真实树上通过），但只能作为辅助门禁，不能替代编译门禁。
5. **测试改为真实输入**：以 `scripts/audit_replay.sh` 为模板，CI 前在真实 K30 checkout + 固定源码上跑 `k30` 与 `k31a` 两种模式，必须全部 rc=0；mock 单测可保留但不作为放行依据。
6. （可选，P2）SUSFS dry-run 只允许 hooks.c Hunk #1 fuzz 2 的断言（见 P2-1）。
7. 用户授权"可以编译"后，编译门禁需额外核对：`System.map` 中 `ksu_filp_open_nonotify` 被内联或存在均可；`Module.symvers` CRC 与 K30 一致；Image 版本串仍为 `ReSukiSU-6ec8d9a8@PLK110-A67-PGuard`。
8. **真机验收重点**：
   - 安装/卸载/更新任意应用后立刻冷启动 Daily Notes，检查 `/proc/<pid>/fd` 中 `[ksu_driver]` 与 dmesg `Crowning manager`、`defer track_throne failed`；
   - 管理器反复刷新首页（getManagersList）无 `sleeping function called from invalid context`；
   - Root/SUSFS/PGuard/SELinux 回归同 K30。

---

## 7. 剩余不确定性 / 阻断

1. **未编译**：所有结论止于源码 replay。K31A 新增代码均是上游/Baka 已在 6.12 GKI 编译过的代码片段，但本组合未经 Kleaf + Clang 14043575 编译。
2. **#3871 同步扫描的耗时**：扫描发生在 PackageManager 的 rename 系统调用返回前（上游与 Baka 相同设计）。应用很多时安装可能略慢；需真机 dmesg 时间戳评估。
3. **#3733 在 system_server 上下文下的 SELinux**：`override_creds(ksu_cred)` 使扫描以 KSU 域执行（与 Baka/上游一致），需真机确认无 avc 拒绝。
4. **Duck 时序信号**：缺少同机同系统原厂对照，无法归因（见第 5 节建议的测量方法）。
5. **#3800**：是否需要取决于 A67 是否两次 mount_all，需开机 dmesg。
6. **`f98b7a6d`（去 bitmap）**：可能进一步改善管理器识别稳定性，但改变识别策略，建议与 Daily Notes "未安装"专项一并评估。
7. **ksud 源码**：本次未审 ksud；路线 A 无 UAPI 变化，不需要 ksud 配套。

---

## 附件（本目录）

| 文件 | 说明 |
|---|---|
| `scripts/prepare_k31_candidate.py` | 修正版生成器（路线 A） |
| `scripts/apply_k31_kernel_fixes.py` | K31 内核修复补丁器（4 项） |
| `scripts/audit_replay.sh` | 审计用 replay 脚本（Windows scratchpad 路径，GPT 可改为 Linux 路径复用） |
| `review/Build-ReSukiSU-K31-CANDIDATE.yml` | 生成的待审工作流（无 push 触发，不可自动运行） |
| `review/K31_workflow_vs_K30.diff` | 工作流相对 K30 的统一 diff |
| `K31A_vs_K30_source.diff` | 内核源码相对 K30 的统一 diff（真实 replay 产物） |

**我没有向任何仓库提交、没有触发 Actions、没有编译内核、没有刷机。**
（只在本机做了：克隆公开仓库到 scratchpad、在本地 DailyNotes 仓库 `git fetch` 了 3 个旧分支（只增加本地引用）、只读查询 GitHub API。）
