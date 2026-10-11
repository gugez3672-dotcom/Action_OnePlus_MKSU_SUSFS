#!/usr/bin/env python3
"""D74: restore format-aware terminal file execution after replacing fake shell
with PTY. Keep original files unchanged, run ELF directly, and accept
self-extracting Shell scripts containing an embedded binary payload."""
from pathlib import Path
p=Path("source/manager/app/src/main/java/com/resukisu/resukisu/ui/screen/main/ToolsPage.kt")
s=p.read_text(encoding="utf-8")
old='''    fun runScriptInTerminal(path: String) {
        pty.changeDirectory(parentPath(path))
        pty.sendLine("/system/bin/sh " + shellQuote(path))
        terminalHint = "Root PTY · 脚本"
        tab = 1
    }
'''
if s.count(old)!=1: raise SystemExit(f"D74 script runner drift: found {s.count(old)} old funcs")
new=r'''    fun runScriptInTerminal(path: String) {
        // Do not infer execution format from the .sh suffix: ELF programs can
        // legitimately carry this extension. The old D70 runner lost DN30's
        // magic probe and forced all content through /system/bin/sh.
        pty.ensure()
        tab = 1
        terminalHint = "Root PTY · 正在识别文件类型"
        scope.launch {
            val bb = "/data/adb/ksu/bin/busybox"
            val q = shellQuote(path)
            val parent = parentPath(path)
            val regular = execRoot("test -f " + q + " && test -r " + q)
            if (!regular.success) {
                pty.sendLine("printf '%s\\n' " + shellQuote("[执行失败：文件不存在、不可读或不是普通文件]"))
                terminalHint = "无法读取文件"
                return@launch
            }
            val result = execRoot(
                "$bb hexdump -n 4096 -v -e '1/1 \"%02x\"' -- " + q
            )
            val hex = result.out.trim().lowercase(Locale.ROOT)
            if (!result.success || hex.length < 2 || hex.length % 2 != 0 ||
                !hex.matches(Regex("[0-9a-f]+"))) {
                pty.sendLine("printf '%s\\n' " + shellQuote("[执行失败：无法读取文件头]"))
                terminalHint = "文件识别失败"
                return@launch
            }
            val nativeElf = hex.startsWith("7f454c46")
            val prefix = hex.chunked(2).map { it.toInt(16) }
            val isBinary = prefix.any { it == 0 || (it < 32 && it != 9 && it != 10 && it != 13) }
            val showStatus = { label: String ->
                pty.sendLine("printf '%s\\n' " + shellQuote(label))
            }
            if (nativeElf) {
                // Never modify the source permission bits. On noexec/shared
                // storage or a non-executable file, use a private transient copy
                // instead, then remove that copy once the process returns.
                val storage = path.startsWith("/sdcard/") ||
                    path.startsWith("/storage/") ||
                    path.startsWith("/mnt/media_rw/")
                val canExec = execRoot("test -x " + q).success
                var runPath = path
                var cleanup: String? = null
                if (storage || !canExec) {
                    val copy = "/data/adb/.dn_elf_" + System.currentTimeMillis() +
                        "_" + (0..999999).random().toString()
                    val setup = execRoot(
                        "$bb cp -f -- " + q + " " + shellQuote(copy) +
                            " && $bb chmod 700 -- " + shellQuote(copy)
                    )
                    if (!setup.success) {
                        showStatus("[ELF 临时副本失败，原文件未修改] " + setup.out.take(120))
                        terminalHint = "ELF 准备失败"
                        return@launch
                    }
                    runPath = copy
                    cleanup = copy
                }
                pty.changeDirectory(parent)
                showStatus("[文件类型：ELF 原生程序，直接执行，不通过 sh]")
                val after = cleanup?.let {
                    "; dn_exit_status=$?; $bb rm -f -- " + shellQuote(it) +
                        "; printf '\\n[执行结束，退出码 %s]\\n' \"$dn_exit_status\""
                } ?: "; dn_exit_status=$?; printf '\\n[执行结束，退出码 %s]\\n' \"$dn_exit_status\""
                pty.sendLine(shellQuote(runPath) + after)
                terminalHint = "Root PTY · ELF 执行"
                return@launch
            }
            // A self-extracting Shell script may contain compressed/binary payload
            // after a valid interpreter header. Validate the leading shebang
            // *before* treating control bytes in the payload as a bad format.
            val firstLine = execRoot("$bb head -n 1 -- " + q).out
                .lineSequence().firstOrNull().orEmpty().trimStart('\uFEFF').trimEnd('\r')
            val shebang = if (firstLine.startsWith("#!")) firstLine.drop(2).trim() else ""
            val shellPrograms = setOf("sh", "bash", "ash", "dash", "ksh", "zsh")
            val interpreter = shebang.substringBefore(' ').substringBefore('\t')
            val envArg = if (interpreter == "/usr/bin/env") {
                shebang.removePrefix("/usr/bin/env").trimStart()
                    .substringBefore(' ').substringBefore('\t')
            } else ""
            val isShellShebang = shebang.isNotEmpty() &&
                (interpreter.substringAfterLast('/') in shellPrograms ||
                    envArg in shellPrograms)
            if (isBinary && !isShellShebang) {
                showStatus("[拒绝执行：非 ELF、无可识别 Shell 文件头，且包含二进制控制字节。]")
                terminalHint = "文件格式不支持"
                return@launch
            }
            var runner = "/system/bin/sh"
            if (shebang.contains("bash")) {
                val bash = execRoot("command -v bash 2>/dev/null").out.trim()
                    .lineSequence().firstOrNull().orEmpty()
                if (bash.isBlank()) {
                    showStatus("[脚本要求 bash，设备当前未找到 bash；已停止执行]")
                    terminalHint = "缺少 bash"
                    return@launch
                }
                runner = shellQuote(bash)
            }
            pty.changeDirectory(parent)
            pty.sendLine(runner + " " + q)
            terminalHint = "Root PTY · Shell 脚本"
        }
    }
'''
# NOTE: Kotlin string interpolation in the generated code requires escaping
# the '$' before dn_exit_status, as it is a shell variable not Kotlin.
new=new.replace('$dn_exit_status', r'\$dn_exit_status')
s=s.replace(old,new,1)
p.write_text(s,encoding="utf-8")
assert 'hex.startsWith("7f454c46")' in s
assert 'if (isBinary && !isShellShebang)' in s
assert s.index('val isShellShebang') < s.index('if (isBinary && !isShellShebang)')
assert s.count('val firstLine = execRoot(') == 1
assert 'pty.sendLine(shellQuote(runPath) + after)' in s
assert 'pty.sendLine(runner + " " + q)' in s
assert 'DN30' in s
assert 'val destinationDir = opposite.path' not in s  # different source file
print("DN58 D80: native ELF direct PTY execution; allow self-extracting Shell scripts with valid shebang; reject unknown binary")
