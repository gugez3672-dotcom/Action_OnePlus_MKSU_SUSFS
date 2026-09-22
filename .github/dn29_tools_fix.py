from pathlib import Path

p = Path("source/manager/app/src/main/java/com/resukisu/resukisu/ui/screen/main/ToolsPage.kt")
t = p.read_text()

# Persistent last directory.
if "import android.content.Context" not in t:
    t = t.replace(
        "import android.util.Base64\n",
        "import android.content.Context\nimport android.util.Base64\n",
        1,
    )
if "import androidx.compose.ui.platform.LocalContext" not in t:
    t = t.replace(
        "import androidx.compose.ui.input.pointer.pointerInput\n",
        "import androidx.compose.ui.input.pointer.pointerInput\nimport androidx.compose.ui.platform.LocalContext\n",
        1,
    )

old = '''    val ksuCli: KsuCliRepository = koinInject()
    val scope = rememberCoroutineScope()

    var tab by rememberSaveable { mutableIntStateOf(0) }

    var currentPath by rememberSaveable { mutableStateOf("/") }
'''
new = '''    val ksuCli: KsuCliRepository = koinInject()
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    val toolPrefs = remember(context) {
        context.getSharedPreferences("daily_notes_root_tools", Context.MODE_PRIVATE)
    }

    var tab by rememberSaveable { mutableIntStateOf(0) }

    var currentPath by rememberSaveable {
        mutableStateOf(toolPrefs.getString("last_file_path", "/") ?: "/")
    }
'''
if old not in t:
    raise SystemExit("state anchor missing")
t = t.replace(old, new, 1)

# Remember every successfully navigated location across app restarts.
anchor = '''    DisposableEffect(session) {
        onDispose { session.closeNow() }
    }

'''
insert = '''    DisposableEffect(session) {
        onDispose { session.closeNow() }
    }

    LaunchedEffect(currentPath) {
        toolPrefs.edit().putString("last_file_path", currentPath).apply()
    }

'''
if anchor not in t:
    raise SystemExit("session anchor missing")
t = t.replace(anchor, insert, 1)

# File tap is now safe: directory enters; every file opens actions. No SH auto-run.
old_tap = '''                                            onTap = {
                                                if (entry.directory) {
                                                    currentPath = fullPath
                                                } else if (isTextLike(entry.name)) {
                                                    loadEditor(fullPath)
                                                } else {
                                                    selectedEntry = entry
                                                    showProperties = true
                                                    scope.launch {
                                                        propertiesText = execRoot(
                                                            "/data/adb/ksu/bin/busybox stat " + shellQuote(fullPath)
                                                        ).out
                                                    }
                                                }
                                            },
'''
new_tap = '''                                            onTap = {
                                                if (entry.directory) {
                                                    currentPath = fullPath
                                                } else {
                                                    selectedEntry = entry
                                                    showActions = true
                                                }
                                            },
'''
if old_tap not in t:
    raise SystemExit("tap behavior anchor missing")
t = t.replace(old_tap, new_tap, 1)

# File button from terminal must return to the remembered path, not force "/".
old_file_button = '''                    FilledTonalButton(
                        onClick = {
                            currentPath = "/"
                            tab = 0
                        },
                    ) { Text("文件") }
'''
new_file_button = '''                    FilledTonalButton(
                        onClick = {
                            tab = 0
                        },
                    ) { Text("文件") }
'''
if old_file_button not in t:
    raise SystemExit("file button anchor missing")
t = t.replace(old_file_button, new_file_button, 1)

# Fallback to root only when a remembered directory no longer exists/is readable.
old_refresh = '''            runCatching { listRoot(currentPath) }
                .onSuccess { entries = it }
                .onFailure { fileError = it.message ?: "读取目录失败" }
            loading = false
'''
new_refresh = '''            runCatching { listRoot(currentPath) }
                .onSuccess { entries = it }
                .onFailure {
                    val failedPath = currentPath
                    if (failedPath != "/") {
                        currentPath = "/"
                        fileError = "上次目录不可访问，已返回根目录"
                    } else {
                        fileError = it.message ?: "读取目录失败"
                    }
                }
            loading = false
'''
if old_refresh not in t:
    raise SystemExit("refresh anchor missing")
t = t.replace(old_refresh, new_refresh, 1)

# Replace the hard-coded /system/bin/sh runner with interpreter/encoding detection.
old_runner = '''    fun runScriptInTerminal(path: String) {
        ensureTerminalStarted()
        val parent = parentPath(path)
        session.sendLine("cd " + shellQuote(parent))
        terminalOutput = (terminalOutput + "\\n# /system/bin/sh " + shellQuote(path) + "\\n").takeLast(180_000)
        session.sendLine("/system/bin/sh " + shellQuote(path))
        terminalRunning = true
        terminalHint = "脚本运行中"
        tab = 1
    }
'''
new_runner = r'''    fun runScriptInTerminal(path: String) {
        ensureTerminalStarted()
        terminalRunning = true
        terminalHint = "正在识别脚本…"
        tab = 1

        scope.launch {
            val parent = parentPath(path)
            val busybox = "/data/adb/ksu/bin/busybox"

            // Read shebang without forcing an interpreter first.
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

            // Detect CRLF/BOM. Only then create a temporary normalized sibling copy.
            val encodingProbe = execRoot(
                "HEX=$($busybox hexdump -n 3 -e '3/1 \"%02x\"' " + shellQuote(path) + " 2>/dev/null); " +
                    "if $busybox grep -q \"$(printf '\\r')\" " + shellQuote(path) + "; then CR=1; else CR=0; fi; " +
                    "printf '%s %s' \"$HEX\" \"$CR\""
            ).out.trim()
            val probeParts = encodingProbe.split(' ', limit = 2)
            val hasBom = probeParts.firstOrNull()?.lowercase(Locale.ROOT)?.startsWith("efbbbf") == true
            val hasCr = probeParts.getOrNull(1) == "1"

            var runPath = path
            var cleanupPath: String? = null
            if (hasBom || hasCr) {
                val tempName = ".dn_run_" + System.currentTimeMillis() + "_" + path.substringAfterLast('/')
                val tempPath = joinPath(parent, tempName)
                val normalize = if (hasBom) {
                    "$busybox tail -c +4 " + shellQuote(path) +
                        " | $busybox tr -d '\\r' > " + shellQuote(tempPath)
                } else {
                    "$busybox tr -d '\\r' < " + shellQuote(path) +
                        " > " + shellQuote(tempPath)
                }
                val normalized = execRoot(normalize + "; chmod 700 " + shellQuote(tempPath))
                if (normalized.success) {
                    runPath = tempPath
                    cleanupPath = tempPath
                }
            }

            // Respect explicit shebangs. Generic sh/ash defaults prefer BusyBox ash.
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
                                    "\\n[脚本要求 bash，但当前 Root 环境未找到 bash]\\n" +
                                    "Shebang: " + shebang + "\\n"
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
                        // Keep an explicit absolute interpreter + optional arguments.
                        interpreter = shebang
                        interpreterLabel = shebang
                    }
                }
            }

            session.sendLine("cd " + shellQuote(parent))
            val displayPath = path.substringAfterLast('/')
            terminalOutput = (
                terminalOutput +
                    "\\n# Root 执行: " + displayPath +
                    "\\n# 解释器: " + interpreterLabel +
                    (if (hasBom || hasCr) "\\n# 已临时规范化 BOM/CRLF" else "") +
                    "\\n"
            ).takeLast(180_000)

            val cleanup = cleanupPath?.let {
                "; __dn_ec=$?; rm -f -- " + shellQuote(it) +
                    "; printf '\\n[脚本结束，退出码 %s]\\n' \"$__dn_ec\""
            } ?: "; __dn_ec=$?; printf '\\n[脚本结束，退出码 %s]\\n' \"$__dn_ec\""

            session.sendLine(
                interpreter + " " + shellQuote(runPath) + cleanup
            )
            terminalHint = "脚本运行中 · $interpreterLabel"
        }
    }
'''
if old_runner not in t:
    raise SystemExit("script runner anchor missing")
t = t.replace(old_runner, new_runner, 1)

# Menu language makes it clear that execution is never implicit.
t = t.replace(
    'Text("Root 执行并进入终端")',
    'Text("Root 执行 → 终端")',
    1,
)

p.write_text(t)

assert 'getSharedPreferences("daily_notes_root_tools"' in t
assert 'toolPrefs.edit().putString("last_file_path"' in t
assert 'selectedEntry = entry\\n                                                    showActions = true' in t
assert '正在识别脚本' in t
assert 'BusyBox ash' in t
assert '/system/bin/sh " + shellQuote(path)' not in t
