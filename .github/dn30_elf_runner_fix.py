from pathlib import Path

p = Path("source/manager/app/src/main/java/com/resukisu/resukisu/ui/screen/main/ToolsPage.kt")
t = p.read_text()

start = t.index("    fun runScriptInTerminal(path: String) {")
end = t.index("\n\n    fun sendTerminalLine()", start)

new = r'''    fun runScriptInTerminal(path: String) {
        ensureTerminalStarted()
        terminalRunning = true
        terminalHint = "正在识别文件类型…"
        tab = 1

        scope.launch {
            val parent = parentPath(path)
            val busybox = "/data/adb/ksu/bin/busybox"

            // Content magic wins over extension. Some root tools are native ELF
            // executables even when their filename ends in ".sh".
            val magic = execRoot(
                "$busybox hexdump -n 4 -e '4/1 \"%02x\"' " + shellQuote(path) + " 2>/dev/null"
            ).out.trim().lowercase(Locale.ROOT)

            if (magic == "7f454c46") {
                // Native ELF: never normalize it as text and never feed it to ash.
                // Shared storage is commonly noexec, so copy only there.
                var execPath = path
                var cleanupPath: String? = null
                val sharedStorage =
                    path.startsWith("/sdcard/") ||
                    path.startsWith("/storage/") ||
                    path.startsWith("/mnt/media_rw/")

                if (sharedStorage) {
                    val tempPath = "/data/adb/.dn_exec_" +
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

            // Only text/script candidates reach BOM/CRLF normalization.
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

            // Self-extracting shell scripts can append a raw gzip/zip payload.
            // Never run CR stripping across those bytes: it corrupts the archive.
            // NUL in either the first or last 128 KiB is a strong binary-payload signal.
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
                val tempPath = joinPath(parent, tempName)
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

t = t[:start] + new + t[end:]
p.write_text(t)

assert 'magic == "7f454c46"' in t
assert 'ELF 原生可执行文件' in t
assert '直接执行（不经 BusyBox ash）' in t
assert 'session.sendLine(shellQuote(execPath) + cleanup)' in t
assert '正在识别文件类型' in t
assert 'hasEmbeddedBinary' in t
assert 'shouldNormalizeCr = hasCr && !hasEmbeddedBinary' in t
assert '内嵌二进制数据，已保留原始字节' in t
