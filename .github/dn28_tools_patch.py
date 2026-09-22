from pathlib import Path

tool_page = Path("source/manager/app/src/main/java/com/resukisu/resukisu/ui/screen/main/ToolsPage.kt")
tool_page.write_text(r'''package com.resukisu.resukisu.ui.screen.main

import android.util.Base64
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
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.resukisu.resukisu.data.shell.KsuCliRepository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.koin.compose.koinInject
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

private class RootInteractiveSession(private val command: List<String>) {
    private var process: Process? = null
    private var writer: BufferedWriter? = null
    private var readJob: Job? = null

    val isAlive: Boolean
        get() = process?.isAlive == true

    fun start(
        scope: CoroutineScope,
        onOutput: (String) -> Unit,
        onExit: (Int) -> Unit,
    ) {
        if (isAlive) return
        val p = ProcessBuilder(command).redirectErrorStream(true).start()
        process = p
        writer = BufferedWriter(OutputStreamWriter(p.outputStream, StandardCharsets.UTF_8))
        readJob = scope.launch(Dispatchers.IO) {
            val input = p.inputStream
            val buffer = ByteArray(2048)
            try {
                while (true) {
                    val count = input.read(buffer)
                    if (count <= 0) break
                    val chunk = String(buffer, 0, count, StandardCharsets.UTF_8)
                    withContext(Dispatchers.Main.immediate) { onOutput(chunk) }
                }
            } finally {
                val code = runCatching { p.waitFor() }.getOrDefault(-1)
                withContext(Dispatchers.Main.immediate) { onExit(code) }
            }
        }
    }

    fun sendLine(text: String) {
        val w = writer ?: return
        w.write(text)
        w.newLine()
        w.flush()
    }

    fun sendRaw(text: String) {
        val w = writer ?: return
        w.write(text)
        w.flush()
    }

    suspend fun stop() = withContext(Dispatchers.IO) {
        val p = process ?: return@withContext
        runCatching { writer?.close() }
        runCatching { p.destroy() }
        delay(250)
        if (p.isAlive) runCatching { p.destroyForcibly() }
        process = null
        writer = null
        readJob?.cancel()
        readJob = null
    }

    fun closeNow() {
        runCatching { writer?.close() }
        runCatching { process?.destroyForcibly() }
        process = null
        writer = null
        readJob?.cancel()
        readJob = null
    }
}

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
    val ksuCli: KsuCliRepository = koinInject()
    val scope = rememberCoroutineScope()

    var tab by rememberSaveable { mutableIntStateOf(0) }

    var currentPath by rememberSaveable { mutableStateOf("/") }
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
    var showDeleteConfirm by remember { mutableStateOf(false) }

    var terminalOutput by remember { mutableStateOf("Root Shell\n") }
    var terminalInput by rememberSaveable { mutableStateOf("") }
    var terminalRunning by remember { mutableStateOf(false) }
    var terminalHint by remember { mutableStateOf("未启动") }

    val session = remember {
        RootInteractiveSession(listOf(ksuCli.getKsuDaemonPath(), "debug", "su", "-g"))
    }

    DisposableEffect(session) {
        onDispose { session.closeNow() }
    }

    suspend fun execRoot(command: String): CommandResult =
        withContext(Dispatchers.IO) {
            val stdout = ArrayList<String>()
            val stderr = ArrayList<String>()
            val result = ksuCli.withNewRootShell(globalMnt = true) {
                newJob().add(command).to(stdout, stderr).exec()
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
                .onFailure { fileError = it.message ?: "读取目录失败" }
            loading = false
        }
    }

    fun ensureTerminalStarted() {
        if (session.isAlive) return
        terminalHint = "启动中"
        session.start(
            scope = scope,
            onOutput = { chunk ->
                val clean = stripAnsi(chunk)
                if (clean.isNotEmpty()) terminalOutput = (terminalOutput + clean).takeLast(180_000)
            },
            onExit = { code ->
                terminalRunning = false
                terminalHint = "已结束 · $code"
                terminalOutput = (terminalOutput + "\n[会话结束，退出码 $code]\n").takeLast(180_000)
            },
        )
        terminalHint = "Root"
        session.sendLine("cd /")
        session.sendLine("id")
    }

    fun openTerminalAt(path: String) {
        ensureTerminalStarted()
        session.sendLine("cd " + shellQuote(path))
        terminalHint = "Root · $path"
        tab = 1
    }

    fun runScriptInTerminal(path: String) {
        ensureTerminalStarted()
        val parent = parentPath(path)
        session.sendLine("cd " + shellQuote(parent))
        terminalOutput = (terminalOutput + "\n# /system/bin/sh " + shellQuote(path) + "\n").takeLast(180_000)
        session.sendLine("/system/bin/sh " + shellQuote(path))
        terminalRunning = true
        terminalHint = "脚本运行中"
        tab = 1
    }

    fun sendTerminalLine() {
        val line = terminalInput
        if (line.isEmpty()) return
        ensureTerminalStarted()
        terminalOutput = (terminalOutput + line + "\n").takeLast(180_000)
        session.sendLine(line)
        terminalInput = ""
    }

    fun loadEditor(path: String) {
        editorPath = path
        editorBusy = true
        showEditor = true
        scope.launch {
            val result = execRoot("/data/adb/ksu/bin/busybox head -c 262144 " + shellQuote(path))
            editorText = result.out
            editorBusy = false
        }
    }

    fun saveEditor() {
        editorBusy = true
        scope.launch {
            val encoded = Base64.encodeToString(editorText.toByteArray(), Base64.NO_WRAP)
            val cmd = "printf %s " + shellQuote(encoded) +
                " | /data/adb/ksu/bin/busybox base64 -d > " + shellQuote(editorPath)
            val result = execRoot(cmd)
            if (result.success) {
                showEditor = false
                refreshFiles()
            } else {
                fileError = result.out.ifBlank { "保存失败" }
            }
            editorBusy = false
        }
    }

    LaunchedEffect(tab, currentPath) {
        if (tab == 0) refreshFiles()
    }

    Scaffold(containerColor = Color.Transparent) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(top = innerPadding.calculateTopPadding())
                .padding(horizontal = 16.dp)
                .padding(bottom = bottomPadding + 8.dp),
        ) {
            Text(
                text = "工具",
                style = MaterialTheme.typography.headlineLarge,
                modifier = Modifier.padding(top = 10.dp, bottom = 10.dp),
            )

            TabRow(selectedTabIndex = tab) {
                Tab(selected = tab == 0, onClick = { tab = 0 }, text = { Text("文件") })
                Tab(
                    selected = tab == 1,
                    onClick = {
                        ensureTerminalStarted()
                        tab = 1
                    },
                    text = { Text("终端") },
                )
            }

            Spacer(Modifier.height(10.dp))

            if (tab == 0) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Row(
                        modifier = Modifier
                            .weight(1f)
                            .horizontalScroll(rememberScrollState()),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        val parts = currentPath.split('/').filter { it.isNotBlank() }
                        TextButton(onClick = { currentPath = "/" }) { Text("/") }
                        var acc = ""
                        parts.forEach { segment ->
                            acc += "/$segment"
                            Text("›", color = MaterialTheme.colorScheme.onSurfaceVariant)
                            val target = acc
                            TextButton(onClick = { currentPath = target }) {
                                Text(segment, maxLines = 1)
                            }
                        }
                    }

                    IconButton(
                        onClick = { currentPath = parentPath(currentPath) },
                        enabled = currentPath != "/",
                    ) {
                        Icon(Icons.TwoTone.ArrowUpward, contentDescription = "上级")
                    }
                    IconButton(onClick = { refreshFiles() }) {
                        Icon(Icons.TwoTone.Refresh, contentDescription = "刷新")
                    }
                    IconButton(onClick = { showSearch = !showSearch }) {
                        Icon(Icons.TwoTone.Search, contentDescription = "搜索")
                    }
                    IconButton(onClick = { openTerminalAt(currentPath) }) {
                        Icon(Icons.TwoTone.Terminal, contentDescription = "在终端打开")
                    }
                }

                if (showSearch) {
                    OutlinedTextField(
                        value = query,
                        onValueChange = { query = it },
                        modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp),
                        singleLine = true,
                        label = { Text("筛选当前目录") },
                        leadingIcon = { Icon(Icons.TwoTone.Search, null) },
                    )
                }

                pendingSource?.let { source ->
                    Surface(
                        modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp),
                        tonalElevation = 2.dp,
                        shape = MaterialTheme.shapes.medium,
                    ) {
                        Row(
                            modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Icon(
                                if (pendingMove) Icons.TwoTone.DriveFileMove else Icons.TwoTone.ContentCopy,
                                contentDescription = null,
                            )
                            Spacer(Modifier.width(8.dp))
                            Text(
                                text = source.substringAfterLast('/'),
                                modifier = Modifier.weight(1f),
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                            )
                            TextButton(
                                onClick = {
                                    scope.launch {
                                        val dest = joinPath(currentPath, source.substringAfterLast('/'))
                                        val cmd = if (pendingMove) {
                                            "mv " + shellQuote(source) + " " + shellQuote(dest)
                                        } else {
                                            "cp -a " + shellQuote(source) + " " + shellQuote(dest)
                                        }
                                        val result = execRoot(cmd)
                                        if (!result.success) fileError = result.out
                                        pendingSource = null
                                        pendingMove = false
                                        refreshFiles()
                                    }
                                },
                            ) { Text("粘贴") }
                            TextButton(
                                onClick = {
                                    pendingSource = null
                                    pendingMove = false
                                },
                            ) { Text("取消") }
                        }
                    }
                }

                if (fileError.isNotEmpty()) {
                    Text(
                        text = fileError,
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodySmall,
                        modifier = Modifier.padding(bottom = 6.dp),
                    )
                }

                if (loading) {
                    Box(
                        modifier = Modifier.fillMaxWidth().padding(24.dp),
                        contentAlignment = Alignment.Center,
                    ) {
                        CircularProgressIndicator(modifier = Modifier.size(28.dp))
                    }
                } else {
                    val filtered = entries.filter {
                        query.isBlank() || it.name.contains(query, ignoreCase = true)
                    }

                    LazyColumn(modifier = Modifier.fillMaxSize()) {
                        items(
                            items = filtered,
                            key = { (if (it.directory) "D:" else "F:") + it.name },
                        ) { entry ->
                            val fullPath = joinPath(currentPath, entry.name)
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .pointerInput(fullPath) {
                                        detectTapGestures(
                                            onTap = {
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
                                            onLongPress = {
                                                selectedEntry = entry
                                                showActions = true
                                            },
                                        )
                                    }
                                    .padding(vertical = 11.dp),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                val icon = when {
                                    entry.directory -> Icons.TwoTone.Folder
                                    entry.name.endsWith(".sh", ignoreCase = true) -> Icons.TwoTone.Terminal
                                    isTextLike(entry.name) -> Icons.TwoTone.Description
                                    else -> Icons.TwoTone.InsertDriveFile
                                }
                                Icon(
                                    imageVector = icon,
                                    contentDescription = null,
                                    modifier = Modifier.size(34.dp),
                                    tint = if (entry.directory) {
                                        MaterialTheme.colorScheme.primary
                                    } else {
                                        MaterialTheme.colorScheme.onSurfaceVariant
                                    },
                                )
                                Spacer(Modifier.width(14.dp))
                                Column(modifier = Modifier.weight(1f)) {
                                    Text(
                                        text = entry.name,
                                        style = MaterialTheme.typography.bodyLarge,
                                        maxLines = 1,
                                        overflow = TextOverflow.Ellipsis,
                                    )
                                    Spacer(Modifier.height(2.dp))
                                    val detail = buildString {
                                        if (entry.directory) append("文件夹")
                                        else if (entry.symlink) append("链接")
                                        else append(formatSize(entry.size))
                                        if (entry.mode.isNotBlank()) {
                                            append(" · ")
                                            append(entry.mode)
                                        }
                                        val time = formatTime(entry.modified)
                                        if (time.isNotBlank()) {
                                            append(" · ")
                                            append(time)
                                        }
                                    }
                                    Text(
                                        text = detail,
                                        style = MaterialTheme.typography.bodySmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                        maxLines = 1,
                                        overflow = TextOverflow.Ellipsis,
                                    )
                                }
                                IconButton(
                                    onClick = {
                                        selectedEntry = entry
                                        showActions = true
                                    },
                                ) {
                                    Icon(Icons.TwoTone.MoreVert, contentDescription = "更多")
                                }
                            }
                            HorizontalDivider()
                        }
                    }
                }
            } else {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Icon(Icons.TwoTone.Terminal, contentDescription = null)
                    Spacer(Modifier.width(8.dp))
                    Column(modifier = Modifier.weight(1f)) {
                        Text("Root 终端", style = MaterialTheme.typography.titleMedium)
                        Text(
                            terminalHint,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    TextButton(
                        onClick = {
                            scope.launch {
                                session.stop()
                                terminalRunning = false
                                terminalHint = "已停止"
                                terminalOutput += "\n[已停止]\n"
                            }
                        },
                        enabled = session.isAlive,
                    ) { Text("停止") }
                    TextButton(onClick = { terminalOutput = "" }) { Text("清屏") }
                }

                Surface(
                    modifier = Modifier.fillMaxWidth().weight(1f).padding(top = 8.dp),
                    color = MaterialTheme.colorScheme.surfaceContainerLowest,
                    shape = MaterialTheme.shapes.medium,
                ) {
                    LazyColumn(modifier = Modifier.fillMaxSize().padding(12.dp)) {
                        item {
                            Text(
                                text = terminalOutput,
                                fontFamily = FontFamily.Monospace,
                                style = MaterialTheme.typography.bodyMedium,
                            )
                        }
                    }
                }

                OutlinedTextField(
                    value = terminalInput,
                    onValueChange = { terminalInput = it },
                    modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                    singleLine = true,
                    label = { Text(if (terminalRunning) "脚本输入 / 命令" else "Root 命令") },
                    textStyle = MaterialTheme.typography.bodyMedium.copy(fontFamily = FontFamily.Monospace),
                )
                Row(
                    modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Button(
                        onClick = { sendTerminalLine() },
                        enabled = terminalInput.isNotEmpty(),
                    ) { Text("发送") }
                    OutlinedButton(
                        onClick = {
                            ensureTerminalStarted()
                            session.sendRaw("\u0003")
                        },
                        enabled = session.isAlive,
                    ) { Text("Ctrl+C") }
                    FilledTonalButton(
                        onClick = {
                            currentPath = "/"
                            tab = 0
                        },
                    ) { Text("文件") }
                }
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
                                    Text("Root 执行并进入终端")
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
        AlertDialog(
            onDismissRequest = { if (!editorBusy) showEditor = false },
            title = {
                Text(
                    editorPath.substringAfterLast('/'),
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            },
            text = {
                if (editorBusy) {
                    Box(
                        modifier = Modifier.fillMaxWidth().padding(24.dp),
                        contentAlignment = Alignment.Center,
                    ) { CircularProgressIndicator() }
                } else {
                    OutlinedTextField(
                        value = editorText,
                        onValueChange = { editorText = it },
                        modifier = Modifier.fillMaxWidth().height(360.dp),
                        textStyle = MaterialTheme.typography.bodySmall.copy(
                            fontFamily = FontFamily.Monospace
                        ),
                    )
                }
            },
            confirmButton = {
                TextButton(onClick = { saveEditor() }, enabled = !editorBusy) { Text("保存") }
            },
            dismissButton = {
                TextButton(onClick = { showEditor = false }, enabled = !editorBusy) { Text("取消") }
            },
        )
    }
}
''')

assert 'Text("文件")' in tool_page.read_text()
assert 'Text("终端")' in tool_page.read_text()
assert 'Root 执行并进入终端' in tool_page.read_text()
assert 'RootInteractiveSession' in tool_page.read_text()
