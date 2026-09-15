# 一加 15 PLK110 A.67 内核构建

## 固定基线

- 设备：OnePlus 15 / `PLK110`
- 固件：`PLK110_16.0.8.302(CN01)`
- 内核：`6.12.23-android16-5-gb2a876903b49-ab14541642-4k`
- 目标功能：SukiSU builtin `4.2.0` + SUSFS `2.3.0`
- 2026-09-15 只读检查：手机仍使用原厂 boot，SukiSU LKM 位于 init_boot。

common、SoC、modules、manifest、SukiSU、SUSFS 和 AnyKernel 源码均固定到
工作流记录的完整提交号。`SOURCE_PINS.txt` 和 `SOURCE_MANIFEST.xml` 随产物保存。
编译器沿用固定一加源码配套工具链；与原厂编译器的构建号差异会在报告中保留，
不宣称与原厂镜像逐字节相同。

## 两阶段构建

1. `Build-Stock-A67.yml` 先构建不含 SukiSU/SUSFS 的 GKI。
2. 纯内核离线核验成功后，`Build-SukiSU.yml` 才允许开始功能构建。
   工作流会验证指定纯内核运行的提交号和成功状态。

二者使用同一套 `scripts/build_gki.sh`、产物收集和离线核验脚本。
支持手动运行，也分别支持修改 `.github/plk110-stock-trigger` 和
`.github/plk110-build-trigger` 后触发。

### 保留正常配置和 KMI 检查

- 使用源码自带的 `gki_defconfig`，不把手机的完整 `.config` 写成 defconfig。
- 直接构建官方 canoe perf 的 base_kernel 指向的 `//common:kernel_aarch64`。
- 保留 Bazel 的 minimized defconfig、KMI 严格检查和符号裁剪。
- 通过 Bazel 标准参数开启原厂已有的 ZSTD 调试信息压缩，覆盖 SoC rc 的关闭设置。
- 使用标准 post-defconfig fragments 加入原厂公开证书及第二阶段功能配置。
- 保留 `MODULE_SIG`、`MODULE_SIG_ALL`、`MODULE_SIG_PROTECT`、
  `TRIM_UNUSED_KSYMS`、`MODVERSIONS`、原厂 LTO/CFI 和调度配置。
- 固定源码只补齐构建脚本所需的 `vmlinux_oki` 复制步骤，并修正与原厂不一致的
  版本字符串 OKI 后缀；所有源码改动随产物导出。

### 核验实际 Image

配置预检在完整编译前完成。最终配置从 **Image 内嵌的 IKCONFIG** 提取，
并与同一个 GKI 目标的预检配置逐项核对。

`dist/out_dir/.config` 属于一加设备模块目标，不能当作 boot Image 的配置。
此前第 14 次功能产物的导出配置与实际 Image 存在 432 个配置值差异；
实际 Image 与原厂只有 13 个配置值差异。不能据错误的导出配置判断
该 Image 关闭了模块签名保护。

原厂模块基线覆盖 system_dlkm、vendor_dlkm 和原厂 vendor_boot：
1018 个文件记录包含跨分区副本，覆盖实时加载的全部 664 个原厂模块。
现有 SukiSU LKM 不属于原厂模块基线。核验会检查内核提供的符号 CRC，
并区分由原厂模块彼此提供的依赖符号。

全部 103 个带签名的原厂模块均已离线验证由同一个原厂证书签名。
构建将该**公开证书**加入内置信任表，最终用 System.map 定位 Image 内的
`system_certificate_list` 并检查证书内容。没有原厂私钥，也不需要原厂私钥。
详见 [证书来源](baselines/PLK110_A67_stock_module_signer.md)。

## 功能与产物

第二阶段仅允许基线文件列出的 SukiSU/SUSFS 功能差异。KPM、ADB root、
SukiSU debug 和 SUSFS 日志关闭。SukiSU 版本信息固定为
`v4.2.0-e2912817@builtin`，版本码采用官方 v4.2.0 发布的 `40900`，
构建期间不再查询最新版本或读取错误仓库的提交号。

产物包含 Image、vmlinux、System.map、Module.symvers、实际配置、预检配置、
VERDICT.json、模块 ABI 报告、源码改动和 SHA256SUMS.txt。
第二阶段核验成功后才生成仅替换 boot 内核的 AnyKernel3 包。

**离线核验通过不代表实机启动通过。** 本流程不刷写、不重启手机。
当前 init_boot 中的 SukiSU LKM 与将来的 builtin 切换需要独立的启动及恢复安排。
没有 pstore 或启动日志时，不将历史启动失败归结为已证明的单一原因。
