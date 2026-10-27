# Daily Notes 2 移植与静态特征审计约束

状态：待内核审查通过并开始编译后推进；本文件不表示管理器已经实现、构建或验收。

版本 `D2.0.0/36200`，应用包名 `com.daily.notes`。官方管理器、ksud 与内核都固定 `inputs.lock.json` 的 KernelSU 提交；SUSFS 用户态执行端固定同一个 `519c86c`，不使用 fork 后端或 D91 固定二进制。

## 功能清单

| 部分 | 必须覆盖 |
|---|---|
| 官方管理功能 | 官方授权/应用配置、模块、WebUI、日志、设置及上游新增功能；检查官方默认值，不照搬 fork 的私有协议 |
| DN 工具页 | 双栏文件、批量操作、编辑/排序/打开、Root PTY/ATE、脚本后台执行、会话恢复与生命周期、字体/输入法/回车关闭等既有细节 |
| 授权 | 主空间默认显示、点标题展开其他空间、用户区分、批量控制、单应用控制 |
| 模块 | 默认隐藏、点标题显示；以真实模块标识打开 WebUI，核查旧修复是否由官方实现覆盖 |
| 设置 | 标题点按切换 0/11；长按清理 10/11 的无线与移动流量记录，覆盖卸载应用和已删除用户 |
| ADB | USB/网络/Root 开关，完整保留 D111 状态读取与保活同步解耦、错误独立提示和现有门控行为；不夹带暂缓的两开关拆分 |
| SUSFS | 保留 DN 设置入口；官方 ksu_susfs 执行；通用开机脚本目录而非额外模块；写入前按实机核对配置范围 |
| 外观与入口 | DN 应用名、图标切换、组件与命名空间；保留用户已确认的默认启动入口和界面行为 |

先把现有实际源码/配置整理成逐项移植清单，再分功能实现，不重新叠加旧 43 个锚点替换脚本。原 `代码/DailyNotes` 工作树只读提取，不 reset/clean、不全量 add、不覆盖其脏改动。

DN 功能输入以 Claude 当天最终交付 D1.1.1/36111 为准，已知最终 APK SHA256 为 `06b764651d8c14af8f79fe2fd00327023faa6d51119b2742241e6d2ba0083eb3`。正式移植前锁定其对应最终源码/资源/脚本与快照指纹；当前只核对了交付记录、APK 哈希和公开证书，不把源码全量对应关系写成已验证。

## 模块挂载与配置迁移（上机前门槛）

固定官方提交的 `website/docs/guide/metamodule.md` 明确：需要挂载 system 内容的模块依赖 metamodule，纯脚本模块不一定需要；同一时刻只能有一个。先根据实机模块清单与每个模块实际文件/脚本列出挂载、Zygisk、生命周期和依赖矩阵，再选择实现。官方 meta-overlayfs 是候选，不在本轮自动预装，也不据现有源码推断手机已经安装。

SukiSU 的 allowlist/app profile 与官方格式须逐项对照，不能直接覆盖导入。上机前备份整份 `/data/adb`、记录 shell(2000) 与各用户的授权/配置，明确迁移支持范围；准备新管理器重新授权 shell 和应用的操作步骤，以及远程 Root/ADB 不可用时的本地 USB 恢复路径。

D2 正式包、配套官方 ksud/ksu_susfs、初始化/授权及模块恢复方案未齐全时，不刷入新内核。现有 D1.1.1 会被包名/证书门槛识别，但这不证明旧后端兼容新协议。旧 init_boot 的 SukiSU LKM 是否会重复加载也必须在部署方案中解决，恢复原厂 init_boot 尚属待用户确定的设备操作。

## 静态特征清理

审计分源码和最终 APK 两层，不能只改显示名或 applicationId。

| 表面 | 检查内容 |
|---|---|
| Manifest / 包信息 | applicationId、namespace、组件全名、别名、authority、permission、action、进程名、zygote preload、元数据、label/icon |
| DEX | 自有包名/类名、BuildConfig/R 引用、反射/序列化类型名、硬编码上游身份、URL、日志与错误文字 |
| 资源与资产 | 自有资源键和文字、图标、HTML/JS/WebUI bridge、文件名、配置、SourceDebugExtension/源路径等编译残留 |
| JNI / 原生库 | Java 类与导出函数配套重命名；动态注册类路径、System.loadLibrary、ELF SONAME/依赖、可见符号、字符串和调试路径 |
| 后端包装 | 使用中性的包内库名；校验新的 ksud 字节和来源，不能仅改名后仍留旧载荷 |

现有 DN 身份映射作为移植参考：`RuntimeApplication`、`HomeActivity`、`DesktopEntry`、`StartupPreload`、`NativeApi`、`BootstrapService`、`BootReceiver`、`IDeviceCatalog`、`PackageCatalogService` 均在 `com.daily.notes` 下；后端与 JNI 库沿用中性命名 `libnote_runtime.so` / `libnote_bridge.so`。

必须保持的内核 ABI/IOCTL、root 数据目录/命令接口与第三方依赖另作精确例外记录。例外必须写到具体字符串、位置和用途，不能用“包含 ksu 都放行”一类宽泛规则。自有身份中的 `me.weishu.kernelsu`、`com.resukisu` 等残留直接阻断交付。第三方许可文本按原许可保留并单列审计范围。

最终静态报告需同时审计签名前与 finalize 后的 APK；JNI 启动、Root/Binder/PTY、跨用户授权、模块 WebUI 等功能验证不能被“扫描无残留”替代。

## 出包约束

CI 只出未签名 arm64 包；本机原证书 V2-only 签名。核对 APK 内 ksud / ksu_susfs 的输入提交、SHA256、版本和签名前后字节，禁止使用旧命令中的 `D91-preserved-backend.bin`。

已查看同一官方提交的 `repack_apk.py`：可参考其 ksud 注入与 zipalign 流程，但不能代替 DN 源码移植和静态身份清理。该版本会把密码以 pass: 参数传给签名工具，且按 libksud.so 搜索载荷；若复用，必须先适配本地 password-file、中性库名、固定证书/V2-only 和签名前后载荷核对，不能直接照用。

跨框架升级可能涉及 `/data/adb` 数据格式与模块兼容，实际迁移之前必须具备整包备份。刷写、安装、重启与用户验收分别记录。
