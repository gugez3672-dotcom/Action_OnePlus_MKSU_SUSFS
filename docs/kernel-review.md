# 编译前审查：官方 KernelSU + SUSFS 519

本轮边界：**源码与构建定义准备完成；没有内核/管理器编译，没有提交、推送、Actions 触发、手机连接或刷写。**

当前为 Claude 首轮审查 B1/R1/R2 修正版，修复后再次停等复核。用户要求审查无异议后才开始编译；本轮没有编译。

## 审查顺序

1. 看 `inputs.lock.json`：官方 KernelSU `75e179d3` / 32705、SUSFS `519c86c`、一加 A67 四组源码与 clang 固定提交。
2. 看 `review/LOCAL_OFFICIAL_OVERLAY.patch`：官方 SUSFS 之后仅额外改 Kbuild 的可复现版本/官方管理器参数、管理器 fd 两处权限门槛、三个信息 ioctl、负 fd 失败回收及 common 的 root fragment。
3. 看 `patches/PLK110_A67_SUSFS_519_compat.patch`、`scripts/susfs_patch_policy.py` 与 `review/OFFICIAL_SUSFS_INTEGRATION.json`：六个不兼容块由独立 A67 适配替代，其余官方原文保留；全部使用 git apply 严格上下文，禁止 fuzz。
4. 看 `scripts/link_official_driver.py`、`prepare_stock_build.py`、`prepare_stock_trust.py`、`prepare_stock_ikconfig.py`：driver 链接、两处原厂构建适配、模块证书信任、原厂公开配置。
5. 看 `verify_official_sources.py`、`verify_gki.py`、`verify_official_image.py` 和 workflow：检查是否能在错误输入、ABI/证书/完整 banner 漂移时阻断，并且打包前没有绕过检查。
6. 看 `docs/D2-port-contract.md`：管理器功能与静态身份审计范围。本轮未开始管理器移植。

不直接复用旧 K30/K32 修复脚本、SELinux 实验移植、fork 专属选项和 PGuard。它们已经被移出新主线流程，不能因文件名相似又接回去。

## 具体实现边界

- `KSU_PACKAGE_NAME/KSU_EXPECTED_SIZE/KSU_EXPECTED_HASH` 使用官方 Kbuild 参数，签名解析代码未修改；证书长度 890，SHA256 与现有 D1.1.1 一致。
- `ksu_install_fd()` 在实际安装管理器 fd 时检查 `manager_or_root`，异步入口 `ksu_supercall_reboot_handler()` 在分配任务前再次检查，未识别调用返回 -EPERM，使 common reboot 回到原厂校验路径。`ksu_install_su_fd()` 及官方 SU-session 权限例外保持。
- `GET_INFO`、`GET_INFO_LEGACY`、`CHECK_SAFEMODE` 均为 `manager_or_root`，不允许 SU-session 绕过。K32 的 `GET_FULL_VERSION` 在此官方提交没有对应 ioctl，不添加私有协议。
- Kbuild 在进入 Bazel 前冻结官方版本表达式 `30000 + git_count`；固定包名/证书使用原有编译定义通路。没有新增版本名、K 后缀或精确 APK 哈希门槛。
- 官方 519 的 UID filter worker 修复与两处 RCU 同步均保留。官方新增 susfs.c/.h 等逐字节核对；额外 A67 include/声明与旧 smaps 循环适配见 `docs/A67-SUSFS-519-adaptation.md`，另有已知空白规范化。
- preinit 编译后要求 ksu_preinit_init / ksu_preinit_handle_post_execveat 及非空 runner blob 符号；Image 禁止 KSU_NO_PREINIT 回退字符串，preflight/build 日志出现 preinit disabled 即失败。此门槛已有单元测试，本版真实编译结果尚未产生。
- 完整 banner、公开 IKCONFIG、模块 CRC、调度器/厂商 tracepoint 和原厂模块证书信任均为编译后门槛。
- 为保持 stock SCM stamping，先导出完整 diff 和 203 项源码指纹，再在 CI 临时 common 工作树标记已有受控改动为 assume-unchanged；编译前后复核实际字节。官方 UAPI 目录链接及其目标头文件也包含在指纹中。
- 内核 workflow 保留旧文件名，改成仅手动触发，`review_ack` 必须等于 `reviewed`；没有 push、pull_request 或 workflow_run 自动触发。
- 打包沿用固定 AnyKernel 提交，只替换 boot 内核；禁用 vbmeta 修补，不附带 ZIP/APK/IMG、模块或其他分区载荷。

## 已实际检查

- 使用固定提交的 33 个原厂文件建立独立副本，完整运行 driver 链接、原厂适配、证书、两侧官方补丁、加固与配置步骤，全部通过。
- 官方 KSU、保留的 common 官方块、独立 A67 适配全部严格 git apply --check/apply 通过；没有 fuzz/拒绝，记录见 `OFFICIAL_COMMON_PATCH.log`。
- 17 项单元测试通过（6 配置、4 补丁/函数守卫、7 preinit）；12 项真实源码破坏反向测试全部被拦截，之后已恢复原始字节。CI 同样运行源码反向检查。
- 203 项适配源码及链接/UAPI 目标指纹一致；Python AST、全部 workflow Bash 片段和 shell 脚本语法通过。
- `review/` 保存上述实际结果、实际 overlay 和实际输入下载哈希。`SOURCE_STATE.json` 的 review_fixture=true 表示精确源文件子集，不冒充完整 OnePlus checkout。
- 新 smaps 守卫已实际拒绝首轮错误源码；结果见 `CLAUDE_B1_REGRESSION.json`。原厂参考 run 34980659033 仍可读，stock-gki job 为 completed/success；提交/路径仍由 CI 原有前置步骤核对。

## 尚未验证，编译/验收时必须继续

完整 repo sync、Kleaf/Bazel 沙箱与新官方 preinit runner/UAPI 构建依赖、编译结果的实际 config、完整 banner、厂商模块 CRC 和证书表、AnyKernel 完整包门槛都尚未在本版本运行。源文件子集检查不能证明这些已经通过。

手机未连接，本次不刷新 K32/D1.1.1 的设备记录。后续启动、Root、模块、SUSFS/SELinux、检测软件、ADB 门控和长时间稳定性均需另行验收；本版没有 PGuard，B 槽不作可靠回退槽。

## 提交审查意见

请报告文件/行号、具体问题、触发条件、建议修改，并明确区分阻断项和可选项。未获得用户转达的无异议结论前，不运行任何构建/触发命令。修复审查问题后重新运行相关源码检查；收到用户转达的审查无异议结论后，按已有授权开始编译，不重复申请同一范围的授权。
