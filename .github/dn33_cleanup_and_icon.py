from pathlib import Path
from textwrap import dedent

p = Path("source/manager/app/src/main/java/com/resukisu/resukisu/ui/screen/main/ToolsPage.kt")
t = p.read_text()

# 1) Interactive runner: keep temporary execution artifacts in one private directory.
start = t.index("    fun runScriptInTerminal(path: String) {")
end = t.index("\n\n    fun runScriptDetached(path: String)", start)

runner = r'''    fun runScriptInTerminal(path: String) {
        ensureTerminalStarted()
        terminalRunning = true
        terminalHint = "正在识别文件类型…"
        tab = 1

        scope.launch {
            val parent = parentPath(path)
            val busybox = "/data/adb/ksu/bin/busybox"
            val tempDir = "/data/adb/ksu/dn_tmp"

            // One private temp directory instead of scattering .dn_* files.
            // Normal completion removes the active temp immediately; this only
            // prunes abnormal leftovers older than one day.
            execRoot(
                "$busybox mkdir -p " + shellQuote(tempDir) + "; " +
                    "$busybox find " + shellQuote(tempDir) +
                    " -type f -mtime +0 -exec $busybox rm -f -- {} \\; 2>/dev/null || true; " +
                    "$busybox rm -f /data/adb/.dn_exec_* 2>/dev/null || true"
            )

            val magic = execRoot(
                "$busybox hexdump -n 4 -e '4/1 \"%02x\"' " + shellQuote(path) + " 2>/dev/null"
            ).out.trim().lowercase(Locale.ROOT)

            if (magic == "7f454c46") {
                var execPath = path
                var cleanupPath: String? = null
                val sharedStorage =
                    path.startsWith("/sdcard/") ||
                    path.startsWith("/storage/") ||
                    path.startsWith("/mnt/media_rw/")

                if (sharedStorage) {
                    val tempPath = tempDir + "/.dn_exec_" +
                        System.currentTimeMillis() + "_" + path.substringAfterLast('/')
                    val copied = execRoot(
                        "$busybox cp -f -- " + shellQuote(path) + " " + shellQuote(tempPath) +
                            " && chmod 700 " + shellQuote(tempPath)
                    )
                    if (!copied.success) {
                        terminalOutput = (
                            terminalOutput +
                                "\n[ELF 可执行文件复制失败]\n" +
                                copied.out + "\n"
                        ).takeLast(180_000)
                        terminalRunning = false
                        terminalHint = "ELF 准备失败"
                        return@launch
                    }
                    execPath = tempPath
                    cleanupPath = tempPath
                } else {
                    execRoot("chmod 700 " + shellQuote(path))
                }

                session.sendLine("cd " + shellQuote(parent))
                val displayPath = path.substringAfterLast('/')
                terminalOutput = (
                    terminalOutput +
                        "\n# Root 执行: " + displayPath +
                        "\n# 类型: ELF 原生可执行文件" +
                        "\n# 启动方式: 直接执行（不经 BusyBox ash）\n"
                ).takeLast(180_000)

                val cleanup = cleanupPath?.let {
                    "; __dn_ec=$?; rm -f -- " + shellQuote(it) +
                        "; printf '\n[程序结束，退出码 %s]\n' \"\$__dn_ec\""
                } ?: "; __dn_ec=$?; printf '\n[程序结束，退出码 %s]\n' \"\$__dn_ec\""

                session.sendLine(shellQuote(execPath) + cleanup)
                terminalHint = "程序运行中 · ELF 直接执行"
                return@launch
            }

            val firstLine = execRoot(
                "$busybox head -n 1 " + shellQuote(path)
            ).out.lineSequence().firstOrNull()
                ?.trimEnd('\r')
                ?.removePrefix("\uFEFF")
                .orEmpty()

            val shebang = if (firstLine.startsWith("#!")) {
                firstLine.removePrefix("#!").trim()
            } else {
                ""
            }

            val encodingProbe = execRoot(
                "HEX=$($busybox hexdump -n 3 -e '3/1 \"%02x\"' " + shellQuote(path) + " 2>/dev/null); " +
                    "if $busybox grep -q \"$(printf '\r')\" " + shellQuote(path) + "; then CR=1; else CR=0; fi; " +
                    "printf '%s %s' \"\$HEX\" \"\$CR\""
            ).out.trim()
            val probeParts = encodingProbe.split(' ', limit = 2)
            val hasBom = probeParts.firstOrNull()?.lowercase(Locale.ROOT)?.startsWith("efbbbf") == true
            val hasCr = probeParts.getOrNull(1) == "1"

            val headHasNul = execRoot(
                "$busybox head -c 131072 " + shellQuote(path) +
                    " 2>/dev/null | $busybox hexdump -v -e '1/1 \"%02x\\n\"' " +
                    "| $busybox grep -q '^00$'; printf '%s' $?"
            ).out.trim().endsWith("0")
            val tailHasNul = execRoot(
                "$busybox tail -c 131072 " + shellQuote(path) +
                    " 2>/dev/null | $busybox hexdump -v -e '1/1 \"%02x\\n\"' " +
                    "| $busybox grep -q '^00$'; printf '%s' $?"
            ).out.trim().endsWith("0")
            val hasEmbeddedBinary = headHasNul || tailHasNul

            var runPath = path
            var cleanupPath: String? = null
            val shouldNormalizeCr = hasCr && !hasEmbeddedBinary
            if (hasBom || shouldNormalizeCr) {
                val tempName = ".dn_run_" + System.currentTimeMillis() + "_" + path.substringAfterLast('/')
                val tempPath = tempDir + "/" + tempName
                val normalize = when {
                    hasBom && shouldNormalizeCr ->
                        "$busybox tail -c +4 " + shellQuote(path) +
                            " | $busybox tr -d '\r' > " + shellQuote(tempPath)
                    hasBom ->
                        "$busybox tail -c +4 " + shellQuote(path) +
                            " > " + shellQuote(tempPath)
                    else ->
                        "$busybox tr -d '\r' < " + shellQuote(path) +
                            " > " + shellQuote(tempPath)
                }
                val normalized = execRoot(normalize + "; chmod 700 " + shellQuote(tempPath))
                if (normalized.success) {
                    runPath = tempPath
                    cleanupPath = tempPath
                }
            }

            var interpreterLabel = "BusyBox ash"
            var interpreter = "$busybox ash"

            if (shebang.isNotBlank()) {
                when {
                    shebang.contains("bash") -> {
                        val bashPath = execRoot("command -v bash 2>/dev/null || true").out
                            .lineSequence().firstOrNull()?.trim().orEmpty()
                        if (bashPath.isNotBlank()) {
                            interpreter = shellQuote(bashPath)
                            interpreterLabel = "bash"
                        } else {
                            terminalOutput = (
                                terminalOutput +
                                    "\n[脚本要求 bash，但当前 Root 环境未找到 bash]\n" +
                                    "Shebang: " + shebang + "\n"
                            ).takeLast(180_000)
                            terminalRunning = false
                            terminalHint = "缺少 bash"
                            cleanupPath?.let { execRoot("rm -f -- " + shellQuote(it)) }
                            return@launch
                        }
                    }

                    shebang.contains("busybox") && (shebang.endsWith(" sh") || shebang.endsWith(" ash")) -> {
                        interpreter = "$busybox ash"
                        interpreterLabel = "BusyBox ash"
                    }

                    shebang.endsWith("/sh") || shebang == "sh" || shebang.endsWith(" ash") || shebang == "ash" -> {
                        interpreter = "$busybox ash"
                        interpreterLabel = "BusyBox ash"
                    }

                    shebang.startsWith("/") -> {
                        interpreter = shebang
                        interpreterLabel = shebang
                    }
                }
            }

            session.sendLine("cd " + shellQuote(parent))
            val displayPath = path.substringAfterLast('/')
            terminalOutput = (
                terminalOutput +
                    "\n# Root 执行: " + displayPath +
                    "\n# 解释器: " + interpreterLabel +
                    (if (hasBom || shouldNormalizeCr) "\n# 已临时规范化 BOM/CRLF" else "") +
                    (if (hasEmbeddedBinary && hasCr)
                        "\n# 检测到内嵌二进制数据，已保留原始字节（未清洗 CRLF）"
                     else "") +
                    "\n"
            ).takeLast(180_000)

            val cleanup = cleanupPath?.let {
                "; __dn_ec=$?; rm -f -- " + shellQuote(it) +
                    "; printf '\n[脚本结束，退出码 %s]\n' \"\$__dn_ec\""
            } ?: "; __dn_ec=$?; printf '\n[脚本结束，退出码 %s]\n' \"\$__dn_ec\""

            session.sendLine(interpreter + " " + shellQuote(runPath) + cleanup)
            terminalHint = "脚本运行中 · $interpreterLabel"
        }
    }'''

t = t[:start] + runner + t[end:]

# 2) Detached jobs: no persistent stdout log, fixed tiny diagnostic file only,
# and move CPU/cpuset out of top-app to foreground.
start = t.index("    fun runScriptDetached(path: String) {")
end = t.index("\n\n    fun sendTerminalLine()", start)

detached = r'''    fun runScriptDetached(path: String) {
        terminalHint = "正在启动独立后台…"

        scope.launch {
            val busybox = "/data/adb/ksu/bin/busybox"
            val parent = parentPath(path)
            val token = System.currentTimeMillis().toString()
            val jobDir = "/data/adb/ksu/dn_jobs"
            val cgroupPath = "$jobDir/last.cgroup"
            val readyPath = "$jobDir/.ready_$token"

            // Remove files produced by older builds. New detached jobs do not
            // persist stdout/stderr, so dn_jobs stays essentially constant-size.
            execRoot(
                "$busybox mkdir -p " + shellQuote(jobDir) + "; " +
                    "$busybox rm -f " + shellQuote(jobDir) +
                    "/job_*.log " + shellQuote(jobDir) +
                    "/job_*.cgroup " + shellQuote(jobDir) +
                    "/.ready_* 2>/dev/null || true"
            )

            val magic = execRoot(
                "$busybox hexdump -n 4 -e '4/1 \"%02x\"' " + shellQuote(path) + " 2>/dev/null"
            ).out.trim().lowercase(Locale.ROOT)
            val isElf = magic == "7f454c46"

            val execPart = if (isElf) {
                "chmod 700 " + shellQuote(path) + " 2>/dev/null || true; " +
                    "exec $busybox setsid " + shellQuote(path)
            } else {
                "exec $busybox setsid $busybox ash " + shellQuote(path)
            }

            val child = buildString {
                append("pid=\$\$; ")
                append("for cg in /acct /dev/cg2_bpf /sys/fs/cgroup /dev/memcg/apps; do ")
                append("f=\"\$cg/cgroup.procs\"; ")
                append("if [ -e \"\$f\" ]; then printf '%s' \"\$pid\" > \"\$f\" 2>/dev/null || true; fi; ")
                append("done; ")
                // Avoid inheriting top-app scheduling from the manager. Foreground
                // keeps responsiveness for long-running touch/network helpers
                // without granting top-app treatment.
                append("for f in /dev/cpuset/foreground/cgroup.procs /dev/cpuctl/foreground/cgroup.procs; do ")
                append("if [ -e \"\$f\" ]; then printf '%s' \"\$pid\" > \"\$f\" 2>/dev/null || true; fi; ")
                append("done; ")
                append("$busybox mkdir -p " + shellQuote(jobDir) + "; ")
                append("cat /proc/\$\$/cgroup > " + shellQuote(cgroupPath) + " 2>/dev/null || true; ")
                append(": > " + shellQuote(readyPath) + "; ")
                append("cd " + shellQuote(parent) + " || exit 127; ")
                append(execPart)
            }

            val launch = buildString {
                append("$busybox mkdir -p " + shellQuote(jobDir) + "; ")
                append("rm -f " + shellQuote(readyPath) + "; ")
                append("$busybox sh -c " + shellQuote(child))
                append(" </dev/null >/dev/null 2>&1 & ")
                append("launcher=\$!; ")
                append("ok=0; ")
                append("for i in 1 2 3 4 5; do ")
                append("if [ -f " + shellQuote(readyPath) + " ]; then ok=1; break; fi; ")
                append("$busybox sleep 1; ")
                append("done; ")
                append("rm -f " + shellQuote(readyPath) + "; ")
                append("if [ \"\$ok\" = 1 ]; then ")
                append("printf 'DETACHED_OK pid=%s cgroup=%s' \"\$launcher\" " + shellQuote(cgroupPath) + "; ")
                append("else printf 'DETACHED_FAIL pid=%s' \"\$launcher\"; exit 1; fi")
            }

            val result = execRoot(launch)
            if (result.success && result.out.contains("DETACHED_OK")) {
                terminalOutput = (
                    terminalOutput +
                        "\n# 独立后台已启动: " + path.substringAfterLast('/') +
                        "\n# 管理器/终端关闭后：此后台任务继续运行" +
                        "\n# 后台输出: 不持久记录" +
                        "\n# cgroup: " + cgroupPath + "\n"
                ).takeLast(180_000)
                terminalHint = "独立后台已启动"
            } else {
                terminalOutput = (
                    terminalOutput +
                        "\n[独立后台启动失败]\n" +
                        result.out + "\n"
                ).takeLast(180_000)
                terminalHint = "后台启动失败"
            }
            tab = 1
        }
    }'''

t = t[:start] + detached + t[end:]
p.write_text(t)

# 3) Launcher icon: light warm-neutral adaptive background + borderless ivory note.
# The old graphite background was visible around the note and looked like a black rim.
colors = Path("source/manager/app/src/main/res/values/colors.xml")
ct = colors.read_text()
ct = ct.replace(
    '<color name="ic_launcher_background">#1B1E23</color>',
    '<color name="ic_launcher_background">#F1F0EC</color>',
)
colors.write_text(ct)

icon = dedent("""\
<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="108dp"
    android:height="108dp"
    android:viewportWidth="108"
    android:viewportHeight="108">
    <path
        android:fillColor="#FCFBF8"
        android:pathData="M31,18 L68,18 Q72,18 75,21 L84,30 Q87,33 87,38 L87,78 Q87,89 76,89 L31,89 Q21,89 21,79 L21,28 Q21,18 31,18 Z" />
    <path
        android:fillColor="#C6A46A"
        android:pathData="M68,18 L87,37 L77,37 Q68,37 68,28 Z" />
    <path
        android:strokeColor="#747981"
        android:strokeWidth="2.6"
        android:strokeLineCap="round"
        android:pathData="M37,48 L72,48 M37,59 L72,59 M37,70 L62,70" />
</vector>
""")

mono = dedent("""\
<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="108dp"
    android:height="108dp"
    android:viewportWidth="108"
    android:viewportHeight="108">
    <path
        android:fillColor="#000000"
        android:pathData="M31,18 L68,18 L87,37 L87,78 Q87,89 76,89 L31,89 Q21,89 21,79 L21,28 Q21,18 31,18 Z M37,46 L72,46 L72,50 L37,50 Z M37,57 L72,57 L72,61 L37,61 Z M37,68 L62,68 L62,72 L37,72 Z" />
</vector>
""")

for rel in (
    "source/manager/app/src/main/res/drawable/ic_launcher_foreground.xml",
    "source/manager/app/src/main/res/drawable/ic_launcher_foreground_alt.xml",
):
    Path(rel).write_text(icon)

for rel in (
    "source/manager/app/src/main/res/drawable/ic_launcher_monochrome.xml",
    "source/manager/app/src/main/res/drawable/ic_launcher_monochrome_alt.xml",
):
    Path(rel).write_text(mono)

out = p.read_text()
assert "/data/adb/ksu/dn_tmp" in out
assert "last.cgroup" in out
assert "后台输出: 不持久记录" in out
assert "/dev/cpuset/foreground/cgroup.procs" in out
assert "/dev/cpuctl/foreground/cgroup.procs" in out
assert ">/dev/null 2>&1 &" in out
assert "#F1F0EC" in colors.read_text()
assert "#FCFBF8" in Path("source/manager/app/src/main/res/drawable/ic_launcher_foreground.xml").read_text()
