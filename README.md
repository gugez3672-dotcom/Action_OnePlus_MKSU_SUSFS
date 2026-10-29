# OnePlus 15 A67: official KernelSU + official SUSFS

状态：**Claude 首轮审查 B1/R1/R2 已修复，等待复核；未编译、未推送、未安装。**

输入唯一来源为 `inputs.lock.json`。一加源码、编译器、模块 ABI 与签名信任沿用已验证 K32 基础；KernelSU 固定官方 `75e179d3`，SUSFS 固定官方 `519c86c`。两侧官方补丁均使用同一 SUSFS 提交。

本版本保留 K32 的管理器 fd / 信息接口访问限制，管理器门槛采用官方包名、证书长度和证书哈希构建参数。不包含 PGuard，不携带内嵌 K 编号；官方数字版本为 `30000 + 2705 = 32705`。原厂完整 Linux banner、公开 IKCONFIG、调度器、模块 CRC 和原厂模块证书信任均为强制门槛。

## 审查入口

先读 `docs/kernel-review.md`，再看 `review/LOCAL_OFFICIAL_OVERLAY.patch` 与相关脚本。`review/` 是本轮源码检查的具体证据；它不表示编译或设备验证通过。

工作分支 `codex/official-ksu-susfs` 基于原 `main` 的 `0024c872`。旧实验 workflow / 触发器 / 专属补丁从新主线工作树移除，历史与归档分支保留。K 号由手动触发时的 `k_number` 输入指定，与 Actions 运行流水号无关；仓库只保留 K36 起的记录。

## 构建流程

唯一内核入口 `.github/workflows/Build-ReSukiSU-StockSched.yml` 只允许手动触发；收到用户转达的 Claude 审查无异议结论后，按已有授权传入 `review_ack=reviewed` 才会运行。提交或推送代码不会触发编译。

流水线：固定原厂源码与工具链 → 原厂构建适配和证书信任 → 官方 KSU / SUSFS 严格上下文补丁与独立 A67 smaps 适配 → 管理器参数、访问加固与原厂公开配置 → 源码门槛/反向检查 → 配置预检 → 编译 → 完整 banner / ABI / 证书 / preinit / 源码指纹复核 → 只打包验证通过的 Image。

产物 ZIP 为 `PLK110_A67_K<k_number>_KernelSU_SUSFS.zip`；`BUILD_RECORD.json` 保存 K 号、构建定义提交、两侧上游提交与 Image SHA256。包只更新 boot 中的内核，不附带模块、DTB/DTBO 或其他分区镜像。编译成功仍需手机启动与模块兼容验收。

## 管理器后续

在审查通过并开始内核编译后推进 D2.0.0/36200，范围见 `docs/D2-port-contract.md`。内核与管理器/ksud 用同一官方 KernelSU 提交，`ksu_susfs` 用同一 SUSFS 提交。签名密钥只在本机；新后端不能被旧 finalize 参数替换回 D91 后端。

本轮未读取密钥或连接手机。实际刷机之前须另行核对实机与 K32 启动链、D1.1.1、`/data/adb` 回退材料，不能把 B 槽当作可靠回退槽。

管理器只在本地编译与签名，仓库不再有管理器 workflow，也不存放任何签名密钥。全部构建输入可用 `scripts/archive_build_inputs.py <SOURCE_MANIFEST.xml> <目录>` 按锁定提交归档到本地。原厂 A67 复现构建的运行记录保存在 `baselines/VERIFIED_STOCK_RUN.json`，构建时离线核对。
