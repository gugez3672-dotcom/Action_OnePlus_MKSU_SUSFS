#!/usr/bin/env python3
"""DN40: compact MT-inspired dual-pane Root file manager.

Modifies only ToolsPage.kt after dn25/dn28...dn34 patches. Keeps manager
bottom navigation, root shell, detachable runner, and module privacy unchanged.
Each pane owns its path, directory listing, filters, scroll position and
persistent history; refreshing a directory never disposes the LazyColumn.
"""
from pathlib import Path

P = Path("source/manager/app/src/main/java/com/resukisu/resukisu/ui/screen/main/ToolsPage.kt")
t = P.read_text(encoding="utf-8")

def once(old: str, new: str) -> None:
    global t
    count = t.count(old)
    if count != 1:
        raise SystemExit(f"DN40: expected anchor exactly once ({count}): {old[:130]!r}")
    t = t.replace(old, new, 1)

def between(begin: str, end: str, new: str) -> None:
    global t
    n = t.count(begin)
    if n != 1:
        raise SystemExit(f"DN40 begin anchor {n}: {begin[:100]!r}")
    i = t.index(begin)
    j = t.index(end, i)
    t = t[:i] + new + t[j:]

once("import androidx.compose.foundation.gestures.detectTapGestures\n",
     "import androidx.compose.foundation.background\n"
     "import androidx.compose.foundation.gestures.detectTapGestures\n"
     "import androidx.compose.foundation.verticalScroll\n")
once("import androidx.compose.foundation.layout.height\n",
     "import androidx.compose.foundation.layout.height\n"
     "import androidx.compose.foundation.layout.heightIn\n")
once("import androidx.compose.foundation.lazy.LazyColumn\n",
     "import androidx.compose.foundation.lazy.LazyColumn\n"
     "import androidx.compose.foundation.lazy.LazyListState\n")
once("import androidx.compose.foundation.rememberScrollState\n",
     "import androidx.compose.foundation.rememberScrollState\n"
     "import androidx.compose.foundation.shape.RoundedCornerShape\n")
once("import androidx.compose.material3.AlertDialog\n",
     "import androidx.compose.foundation.text.KeyboardActions\n"
     "import androidx.compose.foundation.text.KeyboardOptions\n"
     "import androidx.compose.material3.AlertDialog\n")
once("import androidx.compose.runtime.rememberCoroutineScope\n",
     "import androidx.compose.runtime.rememberCoroutineScope\n"
     "import androidx.compose.runtime.snapshotFlow\n"
     "import androidx.compose.runtime.withFrameNanos\n")
once("import androidx.compose.ui.graphics.Color\n",
     "import androidx.compose.ui.graphics.Color\n"
     "import androidx.compose.ui.graphics.vector.ImageVector\n")
once("import androidx.compose.ui.text.style.TextOverflow\n",
     "import androidx.compose.ui.text.style.TextOverflow\n"
     "import androidx.compose.ui.text.input.ImeAction\n")
once("import kotlinx.coroutines.delay\n",
     "import kotlinx.coroutines.delay\n"
     "import kotlinx.coroutines.FlowPreview\n"
     "import kotlinx.coroutines.flow.debounce\n")
once("import java.util.Locale\n",
     "import java.util.Locale\n"
     "import kotlin.reflect.KProperty\n")

once(
    "private data class CommandResult(val out: String, val success: Boolean)\n",
    '''private data class CommandResult(val out: String, val success: Boolean)

/** The two file windows never share scroll, history, loading or search state. */
private class RootFilePane(initialPath: String) {
    var path by mutableStateOf(initialPath)
    var entries by mutableStateOf<List<RootEntry>>(emptyList())
    var loading by mutableStateOf(false)
    var error by mutableStateOf("")
    var query by mutableStateOf("")
    val listState = LazyListState()
    val positions = mutableMapOf<String, Pair<Int, Int>>()
    var needsRestore = true
    var loadedPath: String = ""

    fun navigate(target: String) {
        if (target == path) return
        if (loadedPath == path && !needsRestore) {
            positions[path] = listState.firstVisibleItemIndex to
                listState.firstVisibleItemScrollOffset
        }
        path = target
        entries = emptyList()
        loadedPath = ""
        needsRestore = true
        error = ""
    }
}

/** Existing dialogs and script actions operate on whichever pane is selected. */
private class ActivePaneText(
    val read: () -> String,
    val write: (String) -> Unit
) {
    operator fun getValue(thisRef: Any?, property: KProperty<*>): String = read()
    operator fun setValue(thisRef: Any?, property: KProperty<*>, value: String) = write(value)
}
'''
)

once("@Composable\nfun ToolsPage(bottomPadding: Dp) {",
     "@OptIn(FlowPreview::class)\n@Composable\nfun ToolsPage(bottomPadding: Dp) {")

between(
    "    var currentPath by rememberSaveable {",
    "    var showSearch by rememberSaveable",
    '''    // Keep the old last_file_path preference as the initial left-pane folder.
    val panes = remember(context) {
        val leftPath = toolPrefs.getString(
            "dual_left_path", toolPrefs.getString("last_file_path", "/data/adb")
        ) ?: "/data/adb"
        val rightPath = toolPrefs.getString("dual_right_path", "/storage/emulated/0")
            ?: "/storage/emulated/0"
        listOf(RootFilePane(leftPath), RootFilePane(rightPath)).also { pair ->
            pair.forEachIndexed { i, pane ->
                pane.positions[pane.path] =
                    (toolPrefs.getInt("dual_" + i + "_index", 0) to
                        toolPrefs.getInt("dual_" + i + "_offset", 0))
            }
        }
    }
    var activePane by rememberSaveable { mutableIntStateOf(0) }
    var currentPath by ActivePaneText(
        read = { panes[activePane].path },
        write = { panes[activePane].navigate(it) }
    )
    var fileError by ActivePaneText(
        read = { panes[activePane].error },
        write = { panes[activePane].error = it }
    )
    var query by ActivePaneText(
        read = { panes[activePane].query },
        write = { panes[activePane].query = it }
    )
'''
)

once(
    '''    LaunchedEffect(currentPath) {
        toolPrefs.edit().putString("last_file_path", currentPath).apply()
    }
''',
    '''    // Save both paths and current scroll offsets across manager launches.
    LaunchedEffect(panes[0].path, panes[1].path) {
        toolPrefs.edit()
            .putString("dual_left_path", panes[0].path)
            .putString("dual_right_path", panes[1].path)
            .putString("last_file_path", panes[activePane].path)
            .apply()
    }
    LaunchedEffect(panes) {
        panes.forEachIndexed { i, pane ->
            launch {
                snapshotFlow {
                    Triple(
                        pane.path,
                        pane.listState.firstVisibleItemIndex,
                        pane.listState.firstVisibleItemScrollOffset
                    )
                }.debounce(350).collect { (path, index, offset) ->
                    if (pane.loadedPath == path && !pane.needsRestore) {
                        pane.positions[path] = index to offset
                        toolPrefs.edit()
                            .putInt("dual_" + i + "_index", index)
                            .putInt("dual_" + i + "_offset", offset)
                            .apply()
                    }
                }
            }
        }
    }
'''
)

between(
    "    fun refreshFiles() {",
    "\n    fun ensureTerminalStarted() {",
    '''    fun refreshFiles(index: Int = activePane) {
        val pane = panes[index]
        val path = pane.path
        scope.launch {
            pane.loading = true
            pane.error = ""
            val result = runCatching { listRoot(path) }
            if (pane.path != path) return@launch
            result.onSuccess { found ->
                // Same-directory refresh retains the existing LazyListState.
                pane.entries = found
                pane.loadedPath = path
                if (pane.needsRestore) {
                    val (position, offset) = pane.positions[path] ?: (0 to 0)
                    withFrameNanos { }
                    pane.listState.scrollToItem(
                        position.coerceIn(0, found.size), offset.coerceAtLeast(0)
                    )
                    pane.needsRestore = false
                }
            }.onFailure { error ->
                pane.error = error.message ?: "读取目录失败"
                pane.entries = emptyList()
                pane.loadedPath = path
                pane.needsRestore = false
            }
            pane.loading = false
        }
    }

    fun pasteTo(index: Int) {
        val source = pendingSource ?: return
        val targetPane = panes[index]
        val dest = joinPath(targetPane.path, source.substringAfterLast('/'))
        if (dest == source || dest.startsWith(source.trimEnd('/') + "/")) {
            targetPane.error = "目标不能是来源本身或其子目录"
            return
        }
        scope.launch {
            // No silent overwrite. Existing target must be resolved explicitly.
            val command = "if [ -e " + shellQuote(dest) + " ] || [ -L " +
                shellQuote(dest) + " ]; then echo '目标文件已存在'; exit 17; fi; " +
                (if (pendingMove) "mv " else "cp -a ") +
                shellQuote(source) + " " + shellQuote(dest)
            val result = execRoot(command)
            if (!result.success) {
                targetPane.error = result.out.ifBlank { "粘贴失败" }
                return@launch
            }
            pendingSource = null
            pendingMove = false
            refreshFiles(index)
            panes.forEachIndexed { i, other ->
                if (i != index && other.path == parentPath(source)) refreshFiles(i)
            }
        }
    }
'''
)
once(
    '''    LaunchedEffect(tab, currentPath) {
        if (tab == 0) refreshFiles()
    }
''',
    '''    LaunchedEffect(tab, panes[0].path) {
        if (tab == 0) refreshFiles(0)
    }
    LaunchedEffect(tab, panes[1].path) {
        if (tab == 0) refreshFiles(1)
    }
'''
)
# Replace the oversized screen header; the manager's bottom navigation is not touched.
once(
    '''            Text(
                text = "工具",
                style = MaterialTheme.typography.headlineLarge,
                modifier = Modifier.padding(top = 10.dp, bottom = 10.dp),
            )
''',
    '''            Text(
                text = if (tab == 0) panes[activePane].path else "Root 终端",
                style = MaterialTheme.typography.titleLarge,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.padding(top = 4.dp, bottom = 4.dp),
            )
'''
)
once(
    '''            Spacer(Modifier.height(10.dp))

            if (tab == 0) {
''',
    '''            Spacer(Modifier.height(3.dp))

            if (tab == 0) {
'''
)

between(
    '''            if (tab == 0) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                ) {''',
    '''            } else {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                ) {''',
    '''            if (tab == 0) {
                // Compact toolbar. The outer manager bottom navigation stays unchanged.
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    TextButton(onClick = {
                        currentPath = parentPath(currentPath)
                    }) { Text("上级") }
                    TextButton(onClick = { refreshFiles() }) { Text("刷新") }
                    TextButton(onClick = { showSearch = !showSearch }) { Text("查找") }
                    TextButton(onClick = { openTerminalAt(currentPath) }) { Text("终端") }
                }
                if (showSearch) {
                    OutlinedTextField(
                        value = query,
                        onValueChange = { query = it },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true,
                        label = { Text("筛选当前窗口") }
                    )
                }
                pendingSource?.let { source ->
                    Surface(
                        modifier = Modifier.fillMaxWidth(),
                        color = MaterialTheme.colorScheme.surfaceContainer,
                        shape = MaterialTheme.shapes.small,
                    ) {
                        Row(
                            modifier = Modifier.padding(horizontal = 6.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(
                                (if (pendingMove) "移动: " else "复制: ") +
                                    source.substringAfterLast('/'),
                                modifier = Modifier.weight(1f),
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                                style = MaterialTheme.typography.labelSmall,
                            )
                            TextButton(onClick = { pasteTo(activePane) }) { Text("粘贴到当前") }
                            TextButton(onClick = {
                                pendingSource = null
                                pendingMove = false
                            }) { Text("×") }
                        }
                    }
                }
                Row(modifier = Modifier.fillMaxSize()) {
                    panes.forEachIndexed { index, pane ->
                        if (index > 0) {
                            Box(
                                Modifier.width(2.dp).fillMaxSize()
                                    .background(MaterialTheme.colorScheme.outlineVariant)
                            )
                        }
                        Column(
                            modifier = Modifier.weight(1f).fillMaxSize()
                                .background(
                                    if (index == activePane)
                                        MaterialTheme.colorScheme.surfaceContainerLowest
                                    else MaterialTheme.colorScheme.surface
                                )
                        ) {
                            // Tapping a pane header selects it, without changing its scroll.
                            Row(
                                modifier = Modifier.fillMaxWidth()
                                    .pointerInput(index) {
                                        detectTapGestures(onTap = { activePane = index })
                                    }
                                    .padding(start = 5.dp, end = 4.dp, top = 3.dp, bottom = 3.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Column(Modifier.weight(1f)) {
                                    Text(
                                        if (index == activePane) "● 窗口 " + (index + 1)
                                        else "窗口 " + (index + 1),
                                        style = MaterialTheme.typography.labelSmall,
                                        color = MaterialTheme.colorScheme.primary,
                                    )
                                    Text(
                                        pane.path,
                                        style = MaterialTheme.typography.labelSmall,
                                        maxLines = 1,
                                        overflow = TextOverflow.Ellipsis,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    )
                                }
                                if (pane.loading) {
                                    CircularProgressIndicator(Modifier.size(13.dp), strokeWidth = 2.dp)
                                } else {
                                    Text(
                                        pane.entries.size.toString(),
                                        style = MaterialTheme.typography.labelSmall
                                    )
                                }
                            }
                            HorizontalDivider()
                            if (pane.error.isNotEmpty()) {
                                Text(
                                    pane.error,
                                    color = MaterialTheme.colorScheme.error,
                                    style = MaterialTheme.typography.labelSmall,
                                    modifier = Modifier.padding(horizontal = 5.dp)
                                )
                            }
                            val visible = pane.entries.filter {
                                pane.query.isBlank() ||
                                    it.name.contains(pane.query, ignoreCase = true)
                            }
                            LazyColumn(
                                state = pane.listState,
                                modifier = Modifier.fillMaxSize()
                            ) {
                                item(key = "parent") {
                                    Row(
                                        modifier = Modifier.fillMaxWidth()
                                            .pointerInput(index, pane.path) {
                                                detectTapGestures(onTap = {
                                                    activePane = index
                                                    currentPath = parentPath(pane.path)
                                                })
                                            }
                                            .heightIn(min = 46.dp)
                                            .padding(horizontal = 5.dp, vertical = 5.dp),
                                        verticalAlignment = Alignment.CenterVertically,
                                    ) {
                                        Icon(
                                            Icons.TwoTone.Folder,
                                            contentDescription = null,
                                            modifier = Modifier.size(28.dp),
                                        )
                                        Spacer(Modifier.width(5.dp))
                                        Text("..", style = MaterialTheme.typography.bodyMedium)
                                    }
                                }
                                items(
                                    items = visible,
                                    key = { (if (it.directory) "D:" else "F:") + it.name },
                                ) { entry ->
                                    val fullPath = joinPath(pane.path, entry.name)
                                    Row(
                                        modifier = Modifier.fillMaxWidth()
                                            .pointerInput(fullPath) {
                                                detectTapGestures(
                                                    onTap = {
                                                        activePane = index
                                                        if (entry.directory) {
                                                            currentPath = fullPath
                                                        } else {
                                                            selectedEntry = entry
                                                            showActions = true
                                                        }
                                                    },
                                                    onLongPress = {
                                                        activePane = index
                                                        selectedEntry = entry
                                                        showActions = true
                                                    },
                                                )
                                            }
                                            .heightIn(min = 53.dp)
                                            .padding(horizontal = 5.dp, vertical = 4.dp),
                                        verticalAlignment = Alignment.CenterVertically,
                                    ) {
                                        Box(
                                            Modifier.size(33.dp).background(
                                                Color(0xFF282828),
                                                RoundedCornerShape(6.dp)
                                            ),
                                            contentAlignment = Alignment.Center,
                                        ) {
                                            Icon(
                                                if (entry.directory) Icons.TwoTone.Folder
                                                else if (isTextLike(entry.name)) Icons.TwoTone.Description
                                                else Icons.TwoTone.InsertDriveFile,
                                                contentDescription = null,
                                                modifier = Modifier.size(21.dp),
                                                tint = Color.White,
                                            )
                                        }
                                        Spacer(Modifier.width(6.dp))
                                        Column(modifier = Modifier.weight(1f)) {
                                            Text(
                                                entry.name,
                                                style = MaterialTheme.typography.bodyMedium,
                                                maxLines = 1,
                                                overflow = TextOverflow.Ellipsis,
                                            )
                                            Text(
                                                if (entry.directory) formatTime(entry.modified)
                                                else formatSize(entry.size) + " · " +
                                                    formatTime(entry.modified),
                                                style = MaterialTheme.typography.labelSmall,
                                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                                maxLines = 1,
                                                overflow = TextOverflow.Ellipsis,
                                            )
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
'''
)

# Terminal: continuous console with auto-following output and keyboard Enter.
once(
    '''    var terminalHint by remember { mutableStateOf("未启动") }
''',
    '''    var terminalHint by remember { mutableStateOf("未启动") }
    val terminalScroll = rememberScrollState()
    LaunchedEffect(terminalOutput, tab) {
        if (tab == 1) terminalScroll.scrollTo(terminalScroll.maxValue)
    }
'''
)
once(
    '''                    LazyColumn(modifier = Modifier.fillMaxSize().padding(12.dp)) {
                        item {
                            Text(
                                text = terminalOutput,
                                fontFamily = FontFamily.Monospace,
                                style = MaterialTheme.typography.bodyMedium,
                            )
                        }
                    }
''',
    '''                    Column(
                        modifier = Modifier.fillMaxSize()
                            .verticalScroll(terminalScroll)
                            .padding(10.dp),
                    ) {
                        Text(
                            text = terminalOutput,
                            fontFamily = FontFamily.Monospace,
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
'''
)
once(
    '''                    textStyle = MaterialTheme.typography.bodyMedium.copy(fontFamily = FontFamily.Monospace),
''',
    '''                    textStyle = MaterialTheme.typography.bodyMedium.copy(fontFamily = FontFamily.Monospace),
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                    keyboardActions = KeyboardActions(onSend = { sendTerminalLine() }),
'''
)

# Postcondition: core module/terminal/file operations and manager navbar remain.
assert "RootInteractiveSession" in t and "fun runScriptInTerminal(path: String)" in t
assert "fun startDetached" in t or "独立后台" in t
assert "showActions = true" in t and "fun pasteTo(index: Int)" in t
assert "panes.forEachIndexed { index, pane ->" in t
assert "LazyColumn(" in t and "state = pane.listState" in t
assert "dual_left_path" in t and "dual_right_path" in t
assert "terminalScroll.scrollTo(terminalScroll.maxValue)" in t
assert "keyboardActions = KeyboardActions(onSend = { sendTerminalLine() })" in t
assert "if (showActions)" in t and "if (showEditor)" in t
P.write_text(t, encoding="utf-8")
print("DN40 MT-inspired compact dual-pane UI, sticky scroll, remembered paths and inline terminal input applied.")
