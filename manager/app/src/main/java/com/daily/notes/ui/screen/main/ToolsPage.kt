package com.daily.notes.ui.screen.main

import android.content.Context
import android.util.Base64
import android.widget.Toast
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.twotone.ArrowUpward
import androidx.compose.material.icons.twotone.ContentCopy
import androidx.compose.material.icons.twotone.Delete
import androidx.compose.material.icons.twotone.Description
import androidx.compose.material.icons.twotone.DriveFileMove
import androidx.compose.material.icons.twotone.Edit
import androidx.compose.material.icons.twotone.Folder
import androidx.compose.material.icons.twotone.Info
import androidx.compose.material.icons.twotone.InsertDriveFile
import androidx.compose.material.icons.twotone.Lock
import androidx.compose.material.icons.twotone.MoreVert
import androidx.compose.material.icons.twotone.Refresh
import androidx.compose.material.icons.twotone.Search
import androidx.compose.material.icons.twotone.Terminal
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.compose.material3.Surface
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.daily.notes.data.shell.BackendCliRepository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.BufferedWriter
import java.io.OutputStreamWriter
import java.nio.charset.StandardCharsets
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

private data class RootEntry(
    val name: String,
    val directory: Boolean,
    val symlink: Boolean,
    val size: Long,
    val modified: Long,
    val mode: String,
)

private data class CommandResult(val out: String, val success: Boolean)

private fun shellQuote(value: String): String =
    "'" + value.replace("'", "'\"'\"'") + "'"

private fun joinPath(base: String, name: String): String =
    if (base == "/") "/$name" else "$base/$name"

private fun parentPath(path: String): String {
    if (path == "/") return "/"
    val clean = path.trimEnd('/')
    val cut = clean.lastIndexOf('/')
    return if (cut <= 0) "/" else clean.substring(0, cut)
}

private fun formatSize(bytes: Long): String = when {
    bytes < 1024L -> "$bytes B"
    bytes < 1024L * 1024 -> String.format(Locale.US, "%.1f KB", bytes / 1024.0)
    bytes < 1024L * 1024 * 1024 -> String.format(Locale.US, "%.1f MB", bytes / (1024.0 * 1024.0))
    else -> String.format(Locale.US, "%.2f GB", bytes / (1024.0 * 1024.0 * 1024.0))
}

private fun formatTime(epochSeconds: Long): String {
    if (epochSeconds <= 0L) return ""
    return SimpleDateFormat("MM-dd HH:mm", Locale.getDefault()).format(Date(epochSeconds * 1000))
}

private fun stripAnsi(text: String): String =
    text.replace(Regex("\\u001B\\[[;\\d?]*[ -/]*[@-~]"), "").replace("\r", "")

private fun isTextLike(name: String): Boolean {
    val lower = name.lowercase(Locale.ROOT)
    return lower.endsWith(".txt") ||
        lower.endsWith(".sh") ||
        lower.endsWith(".conf") ||
        lower.endsWith(".json") ||
        lower.endsWith(".xml") ||
        lower.endsWith(".prop") ||
        lower.endsWith(".log") ||
        lower.endsWith(".md") ||
        lower.endsWith(".ini") ||
        lower.endsWith(".yaml") ||
        lower.endsWith(".yml")
}

@Composable
fun ToolsPage(bottomPadding: Dp) {
    val backendContext = LocalContext.current
    val ksuCli = remember(backendContext) { BackendCliRepository(backendContext) }
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    val toolPrefs = remember(context) {
        context.getSharedPreferences("daily_notes_root_tools", Context.MODE_PRIVATE)
    }
    val dualWindows = remember(context) { DnDualWindows(context) }

    var tab by rememberSaveable { mutableIntStateOf(0) }

    var currentPath by rememberSaveable {
        mutableStateOf(toolPrefs.getString("last_file_path", "/") ?: "/")
    }
    var entries by remember { mutableStateOf<List<RootEntry>>(emptyList()) }
    var loading by remember { mutableStateOf(false) }
    var fileError by remember { mutableStateOf("") }
    var query by rememberSaveable { mutableStateOf("") }
    var showSearch by rememberSaveable { mutableStateOf(false) }
    var selectedEntry by remember { mutableStateOf<RootEntry?>(null) }
    var showActions by remember { mutableStateOf(false) }
    var pendingSource by remember { mutableStateOf<String?>(null) }
    var pendingMove by remember { mutableStateOf(false) }

    var showRename by remember { mutableStateOf(false) }
    var renameValue by remember { mutableStateOf("") }
    var showChmod by remember { mutableStateOf(false) }
    var chmodValue by remember { mutableStateOf("0755") }
    var showProperties by remember { mutableStateOf(false) }
    var propertiesText by remember { mutableStateOf("") }
    var showEditor by remember { mutableStateOf(false) }
    var editorPath by remember { mutableStateOf("") }
    var editorText by remember { mutableStateOf("") }
    var editorBusy by remember { mutableStateOf(false) }
    var editorError by remember { mutableStateOf("") }
    var editorHash by remember { mutableStateOf("") }
    var editorOriginal by remember { mutableStateOf("") }
    val editorLimit = 192 * 1024
    var showDeleteConfirm by remember { mutableStateOf(false) }

    var terminalOutput by remember { mutableStateOf("Root Shell\n") }
    var terminalInput by rememberSaveable { mutableStateOf("") }
    val terminalScroll = rememberLazyListState()
    var followOutput by remember { mutableStateOf(true) }
    val outputLines = remember(terminalOutput) { terminalOutput.lineSequence().toList() }
    LaunchedEffect(terminalOutput, followOutput, tab) {
        if (tab == 1 && followOutput && outputLines.isNotEmpty()) {
            terminalScroll.scrollToItem(outputLines.lastIndex)
        }
    }
    var terminalRunning by remember { mutableStateOf(false) }
    var terminalHint by remember { mutableStateOf("未启动") }

    val terminalModel: DnTerminalViewModel = androidx.lifecycle.viewmodel.compose.viewModel(
        viewModelStoreOwner = context as androidx.activity.ComponentActivity)
    val pty = terminalModel.controller(context, ksuCli.getBackendPath())
    androidx.compose.runtime.SideEffect { terminalModel.showingTerminal = tab == 1 }
    DisposableEffect(terminalModel) { onDispose { terminalModel.showingTerminal = false } }

    suspend fun execRoot(command: String): CommandResult =
        withContext(Dispatchers.IO) {
            val stdout = ArrayList<String>()
            val stderr = ArrayList<String>()
            val result = ksuCli.withNewRootShell(globalMnt = true) {
                newJob().add("(\n" + command + "\n)").to(stdout, stderr).exec()
            }
            val text = buildString {
                if (stdout.isNotEmpty()) append(stdout.joinToString("\n"))
                if (stderr.isNotEmpty()) {
                    if (isNotEmpty()) append('\n')
                    append(stderr.joinToString("\n"))
                }
            }
            CommandResult(text, result.isSuccess)
        }

    suspend fun listRoot(path: String): List<RootEntry> =
        withContext(Dispatchers.IO) {
            val stdout = ArrayList<String>()
            val stderr = ArrayList<String>()
            val d = '$'
            val busybox = "/data/adb/ksu/bin/busybox"
            val cmd =
                "P=" + shellQuote(path) + "\n" +
                "for f in \"" + d + "P\"/* \"" + d + "P\"/.[!.]* \"" + d + "P\"/..?*; do\n" +
                "  [ -e \"" + d + "f\" ] || [ -L \"" + d + "f\" ] || continue\n" +
                "  if [ -d \"" + d + "f\" ]; then t=D; elif [ -L \"" + d + "f\" ]; then t=L; else t=F; fi\n" +
                "  s=$(" + busybox + " stat -c '%s' \"" + d + "f\" 2>/dev/null || echo 0)\n" +
                "  m=$(" + busybox + " stat -c '%Y' \"" + d + "f\" 2>/dev/null || echo 0)\n" +
                "  p=$(" + busybox + " stat -c '%A' \"" + d + "f\" 2>/dev/null || echo ---------)\n" +
                "  n=$(" + busybox + " basename \"" + d + "f\")\n" +
                "  printf '%s\\t%s\\t%s\\t%s\\t%s\\n' \"" + d + "t\" \"" + d + "s\" \"" + d + "m\" \"" + d + "p\" \"" + d + "n\"\n" +
                "done"
            ksuCli.withNewRootShell(globalMnt = true) {
                newJob().add(cmd).to(stdout, stderr).exec()
            }
            stdout.mapNotNull { line ->
                val parts = line.split('\t', limit = 5)
                if (parts.size != 5) null else RootEntry(
                    name = parts[4],
                    directory = parts[0] == "D",
                    symlink = parts[0] == "L",
                    size = parts[1].toLongOrNull() ?: 0L,
                    modified = parts[2].toLongOrNull() ?: 0L,
                    mode = parts[3],
                )
            }.distinctBy { it.name }
                .sortedWith(compareBy<RootEntry>({ !it.directory }, { it.name.lowercase(Locale.ROOT) }))
        }

    fun refreshFiles() {
        scope.launch {
            loading = true
            fileError = ""
            runCatching { listRoot(currentPath) }
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
        }
    }

    fun ensureTerminalStarted() { pty.ensure() }
    fun openTerminalAt(path: String) {
        pty.openAt(path)
        tab = 1
    }
    fun runScriptInTerminal(path: String) {
        pty.openScript(path)
        tab = 1
    }
    fun loadEditor(path: String) {
        editorPath = path
        editorBusy = true
        editorError = ""
        editorHash = ""
        editorText = ""
        editorOriginal = ""
        showEditor = true
        scope.launch {
            val probe = execRoot(
                "if [ -L " + shellQuote(path) + " ]; then echo LINK; " +
                "elif [ ! -f " + shellQuote(path) + " ]; then echo NOT_FILE; " +
                "else /data/adb/ksu/bin/busybox stat -c %s -- " + shellQuote(path) + "; fi"
            )
            val n = probe.out.trim().toLongOrNull()
            if (!probe.success || n == null || n < 0 || n > editorLimit) {
                editorError = when {
                    probe.out.trim() == "LINK" -> "符号链接不允许直接编辑，请打开实际目标"
                    probe.out.trim() == "NOT_FILE" -> "仅支持普通文件"
                    n != null && n > editorLimit -> "文件超过 192 KiB，拒绝截断读取"
                    else -> "读取大小失败: " + probe.out.take(120)
                }
                editorBusy = false
                return@launch
            }
            val raw = execRoot("/data/adb/ksu/bin/busybox base64 -- " + shellQuote(path))
            val bytes = runCatching { Base64.decode(raw.out, Base64.DEFAULT) }.getOrNull()
            if (!raw.success || bytes == null || bytes.size.toLong() != n) {
                editorError = "读取不完整，已禁止保存"
                editorBusy = false
                return@launch
            }
            val decoded = String(bytes, Charsets.UTF_8)
            if (bytes.contains(0.toByte()) ||
                !decoded.toByteArray(Charsets.UTF_8).contentEquals(bytes)) {
                editorError = "文件不是纯 UTF-8 文本，禁止覆盖保存"
                editorBusy = false
                return@launch
            }
            val sha = execRoot("/data/adb/ksu/bin/busybox sha256sum -- " + shellQuote(path))
            val hash = sha.out.trim().substringBefore(" ").lowercase(Locale.ROOT)
            if (!sha.success || !hash.matches(Regex("[a-f0-9]{64}"))) {
                editorError = "读取 SHA-256 失败，已禁止保存"
                editorBusy = false
                return@launch
            }
            val receivedHash = java.security.MessageDigest.getInstance("SHA-256")
                .digest(bytes).joinToString("") { "%02x".format(it.toInt() and 0xff) }
            if (receivedHash != hash) {
                editorError = "读取过程中原文件已改变，禁止编辑旧副本"
                editorBusy = false
                return@launch
            }
            editorText = decoded
            editorOriginal = decoded
            editorHash = hash
            editorBusy = false
        }
    }

    fun saveEditor() {
        if (editorBusy || editorHash.isBlank() || editorError.isNotBlank()) return
        if (editorText == editorOriginal) {
            showEditor = false
            return
        }
        val bytes = editorText.toByteArray(Charsets.UTF_8)
        if (bytes.size > editorLimit) {
            editorError = "保存内容超过 192 KiB，已阻止写入"
            return
        }
        val path = editorPath
        val expected = editorHash
        val encoded = Base64.encodeToString(bytes, Base64.NO_WRAP)
        val newHash = java.security.MessageDigest.getInstance("SHA-256")
            .digest(bytes).joinToString("") { "%02x".format(it.toInt() and 0xff) }
        editorBusy = true
        scope.launch {
            // Preserve mode, ownership and xattrs by copying the original file to
            // a same-dir temporary first. Verify actual bytes before replacement.
            val script = """
BB=/data/adb/ksu/bin/busybox
P=${shellQuote(path)}
EXPECTED=${shellQuote(expected)}
NEW_HASH=${shellQuote(newHash)}
if [ ! -f "${'$'}P" ] || [ -L "${'$'}P" ]; then echo '源文件已改变类型'; exit 70; fi
CURRENT=$(${'$'}BB sha256sum -- "${'$'}P" | ${'$'}BB cut -d ' ' -f1)
if [ "${'$'}CURRENT" != "${'$'}EXPECTED" ]; then echo '文件被外部修改，拒绝覆盖'; exit 71; fi
TMP="${'$'}P.dn-temp-${'$'}${'$'}"
BACKUP="${'$'}P.dn-bak-$(date +%s)-${'$'}${'$'}"
if ! ${'$'}BB cp -a -- "${'$'}P" "${'$'}TMP"; then echo '临时副本失败'; exit 72; fi
if ! printf '%s' ${shellQuote(encoded)} | ${'$'}BB base64 -d > "${'$'}TMP"; then
  ${'$'}BB rm -f -- "${'$'}TMP"; echo '临时文件写入失败'; exit 73
fi
GOT=$(${'$'}BB sha256sum -- "${'$'}TMP" | ${'$'}BB cut -d ' ' -f1)
if [ "${'$'}GOT" != "${'$'}NEW_HASH" ]; then
  ${'$'}BB rm -f -- "${'$'}TMP"; echo '新文件 SHA-256 不匹配'; exit 74
fi
CURRENT=$(${'$'}BB sha256sum -- "${'$'}P" | ${'$'}BB cut -d ' ' -f1)
if [ "${'$'}CURRENT" != "${'$'}EXPECTED" ]; then
  ${'$'}BB rm -f -- "${'$'}TMP"; echo '保存期间原文件已改变'; exit 75
fi
if ! ${'$'}BB cp -a -- "${'$'}P" "${'$'}BACKUP"; then
  ${'$'}BB rm -f -- "${'$'}TMP"; echo '备份失败，原文件未改动'; exit 76
fi
if ! ${'$'}BB mv -fT -- "${'$'}TMP" "${'$'}P"; then
  echo '替换失败，备份保留'; exit 77
fi
echo "保存成功，备份 ${'$'}BACKUP"
""".trimIndent()
            val result = execRoot(script)
            editorBusy = false
            if (result.success) {
                editorOriginal = editorText
                editorHash = newHash
                showEditor = false
                dualWindows.windows.forEach { pane ->
                    if (pane.path == parentPath(path)) pane.refresh()
                }
                fileError = result.out.ifBlank { "保存成功" }
            } else editorError = result.out.ifBlank { "保存失败，未确认替换" }
        }
    }


    Scaffold(containerColor = Color.Transparent) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(top = innerPadding.calculateTopPadding())
                .padding(bottom = if (tab == 1) 0.dp else bottomPadding + 2.dp),
        ) {
            if (tab == 0) {
                DnDualFiles(
                    state = dualWindows,
                    openTerminal = { openTerminalAt(it) },
                    runScript = { runScriptInTerminal(it) },
                    openEditor = { loadEditor(it) },
                )
            } else {
                DnPtyTerminalPanel(
                    controller = pty,
                    onFiles = { tab = 0 },
                )
            }
        }
    }

    if (showActions) {
        val entry = selectedEntry
        if (entry != null) {
            val fullPath = joinPath(currentPath, entry.name)
            AlertDialog(
                onDismissRequest = { showActions = false },
                title = {
                    Text(entry.name, maxLines = 1, overflow = TextOverflow.Ellipsis)
                },
                text = {
                    Column {
                        if (entry.directory) {
                            TextButton(
                                onClick = {
                                    currentPath = fullPath
                                    showActions = false
                                },
                            ) {
                                Icon(Icons.TwoTone.Folder, null)
                                Spacer(Modifier.width(10.dp))
                                Text("打开")
                            }
                            TextButton(
                                onClick = {
                                    showActions = false
                                    openTerminalAt(fullPath)
                                },
                            ) {
                                Icon(Icons.TwoTone.Terminal, null)
                                Spacer(Modifier.width(10.dp))
                                Text("在终端打开")
                            }
                        } else {
                            if (isTextLike(entry.name)) {
                                TextButton(
                                    onClick = {
                                        showActions = false
                                        loadEditor(fullPath)
                                    },
                                ) {
                                    Icon(Icons.TwoTone.Edit, null)
                                    Spacer(Modifier.width(10.dp))
                                    Text("打开 / 编辑")
                                }
                            }
                            if (entry.name.endsWith(".sh", ignoreCase = true)) {
                                TextButton(
                                    onClick = {
                                        showActions = false
                                        runScriptInTerminal(fullPath)
                                    },
                                ) {
                                    Icon(Icons.TwoTone.Terminal, null)
                                    Spacer(Modifier.width(10.dp))
                                    Text("运行脚本")
                                }
                            }
                            TextButton(
                                onClick = {
                                    showActions = false
                                    openTerminalAt(parentPath(fullPath))
                                },
                            ) {
                                Icon(Icons.TwoTone.Terminal, null)
                                Spacer(Modifier.width(10.dp))
                                Text("在终端打开所在目录")
                            }
                        }

                        HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))

                        TextButton(
                            onClick = {
                                pendingSource = fullPath
                                pendingMove = false
                                showActions = false
                            },
                        ) {
                            Icon(Icons.TwoTone.ContentCopy, null)
                            Spacer(Modifier.width(10.dp))
                            Text("复制")
                        }
                        TextButton(
                            onClick = {
                                pendingSource = fullPath
                                pendingMove = true
                                showActions = false
                            },
                        ) {
                            Icon(Icons.TwoTone.DriveFileMove, null)
                            Spacer(Modifier.width(10.dp))
                            Text("移动")
                        }
                        TextButton(
                            onClick = {
                                renameValue = entry.name
                                showActions = false
                                showRename = true
                            },
                        ) {
                            Icon(Icons.TwoTone.Edit, null)
                            Spacer(Modifier.width(10.dp))
                            Text("重命名")
                        }
                        TextButton(
                            onClick = {
                                chmodValue = if (entry.directory) "0755" else "0644"
                                showActions = false
                                showChmod = true
                            },
                        ) {
                            Icon(Icons.TwoTone.Lock, null)
                            Spacer(Modifier.width(10.dp))
                            Text("修改权限")
                        }
                        TextButton(
                            onClick = {
                                showActions = false
                                propertiesText = "读取中…"
                                showProperties = true
                                scope.launch {
                                    propertiesText = execRoot(
                                        "/data/adb/ksu/bin/busybox stat " + shellQuote(fullPath) +
                                            "; ls -ldZ " + shellQuote(fullPath)
                                    ).out
                                }
                            },
                        ) {
                            Icon(Icons.TwoTone.Info, null)
                            Spacer(Modifier.width(10.dp))
                            Text("属性")
                        }
                        TextButton(
                            onClick = {
                                showActions = false
                                showDeleteConfirm = true
                            },
                        ) {
                            Icon(Icons.TwoTone.Delete, null, tint = MaterialTheme.colorScheme.error)
                            Spacer(Modifier.width(10.dp))
                            Text("删除", color = MaterialTheme.colorScheme.error)
                        }
                    }
                },
                confirmButton = {
                    TextButton(onClick = { showActions = false }) { Text("关闭") }
                },
            )
        }
    }

    if (showRename) {
        val entry = selectedEntry
        if (entry != null) {
            val oldPath = joinPath(currentPath, entry.name)
            AlertDialog(
                onDismissRequest = { showRename = false },
                title = { Text("重命名") },
                text = {
                    OutlinedTextField(
                        value = renameValue,
                        onValueChange = { renameValue = it },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )
                },
                confirmButton = {
                    TextButton(
                        onClick = {
                            val newPath = joinPath(currentPath, renameValue)
                            showRename = false
                            scope.launch {
                                val result = execRoot(
                                    "mv " + shellQuote(oldPath) + " " + shellQuote(newPath)
                                )
                                if (!result.success) fileError = result.out
                                refreshFiles()
                            }
                        },
                        enabled = renameValue.isNotBlank() && renameValue != entry.name,
                    ) { Text("确定") }
                },
                dismissButton = {
                    TextButton(onClick = { showRename = false }) { Text("取消") }
                },
            )
        }
    }

    if (showChmod) {
        val entry = selectedEntry
        if (entry != null) {
            val fullPath = joinPath(currentPath, entry.name)
            AlertDialog(
                onDismissRequest = { showChmod = false },
                title = { Text("修改权限") },
                text = {
                    OutlinedTextField(
                        value = chmodValue,
                        onValueChange = { chmodValue = it },
                        singleLine = true,
                        label = { Text("例如 0755 / 0644") },
                    )
                },
                confirmButton = {
                    TextButton(
                        onClick = {
                            showChmod = false
                            scope.launch {
                                val result = execRoot(
                                    "chmod " + shellQuote(chmodValue) + " " + shellQuote(fullPath)
                                )
                                if (!result.success) fileError = result.out
                                refreshFiles()
                            }
                        },
                    ) { Text("应用") }
                },
                dismissButton = {
                    TextButton(onClick = { showChmod = false }) { Text("取消") }
                },
            )
        }
    }

    if (showDeleteConfirm) {
        val entry = selectedEntry
        if (entry != null) {
            val fullPath = joinPath(currentPath, entry.name)
            AlertDialog(
                onDismissRequest = { showDeleteConfirm = false },
                title = { Text("确认删除") },
                text = { Text(fullPath) },
                confirmButton = {
                    TextButton(
                        onClick = {
                            showDeleteConfirm = false
                            scope.launch {
                                val result = execRoot("rm -rf -- " + shellQuote(fullPath))
                                if (!result.success) fileError = result.out
                                refreshFiles()
                            }
                        },
                    ) { Text("删除", color = MaterialTheme.colorScheme.error) }
                },
                dismissButton = {
                    TextButton(onClick = { showDeleteConfirm = false }) { Text("取消") }
                },
            )
        }
    }

    if (showProperties) {
        AlertDialog(
            onDismissRequest = { showProperties = false },
            title = { Text("文件属性") },
            text = {
                Text(text = propertiesText, fontFamily = FontFamily.Monospace)
            },
            confirmButton = {
                TextButton(onClick = { showProperties = false }) { Text("关闭") }
            },
        )
    }

    if (showEditor) {
        Dialog(onDismissRequest = { if (!editorBusy && editorText == editorOriginal) showEditor = false },
            properties = DialogProperties(usePlatformDefaultWidth = false)) {
            Surface(modifier = Modifier.fillMaxSize().padding(5.dp),
                shape = MaterialTheme.shapes.medium) {
                Column(Modifier.fillMaxSize().padding(12.dp)) {
                    Text(editorPath.substringAfterLast('/'),
                        style = MaterialTheme.typography.titleMedium,
                        maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(editorPath, style = MaterialTheme.typography.labelSmall,
                        maxLines = 2, overflow = TextOverflow.Ellipsis,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                    if (editorError.isNotBlank())
                        Text(editorError, style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.error)
                    Spacer(Modifier.height(8.dp))
                    if (editorBusy) {
                        Box(Modifier.weight(1f).fillMaxWidth(),
                            contentAlignment = Alignment.Center) { CircularProgressIndicator() }
                    } else {
                        OutlinedTextField(
                            value = editorText, onValueChange = { editorText = it },
                            modifier = Modifier.weight(1f).fillMaxWidth(),
                            enabled = editorError.isBlank(),
                            textStyle = MaterialTheme.typography.bodySmall.copy(fontFamily = FontFamily.Monospace),
                        )
                    }
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                        TextButton(onClick = { showEditor = false }, enabled = !editorBusy) {
                            Text(if (editorText != editorOriginal) "放弃修改" else "关闭")
                        }
                        TextButton(onClick = { saveEditor() },
                            enabled = !editorBusy && editorError.isBlank() && editorHash.isNotBlank()) {
                            Text("保存并备份")
                        }
                    }
                }
            }
        }
    }
}
