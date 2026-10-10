#!/usr/bin/env python3
"""DN51: scroll-to-activate, visible per-pane paths, coherent menus/bookmarks and file utilities.

UI-only changes except explicit, verified chmod and copy-path. Root storage and
module code remain unchanged. Each pane retains its own scroll state.
"""
from pathlib import Path
p = Path("source/manager/app/src/main/java/com/resukisu/resukisu/ui/screen/main/DnDualPane.kt")
s = p.read_text(encoding="utf-8")
def rep(old, new):
    global s
    count = s.count(old)
    if count != 1:
        raise SystemExit("DN51 source drift: %r count=%d" % (old[:110], count))
    s = s.replace(old, new, 1)

rep("import androidx.compose.foundation.background\n",
'''import androidx.compose.foundation.background
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.text.selection.SelectionContainer
''')
rep("import androidx.compose.ui.input.pointer.pointerInput\n",
'''import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.input.nestedscroll.NestedScrollConnection
import androidx.compose.ui.input.nestedscroll.NestedScrollSource
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
''')
rep('''internal class DnDualWindows(ctx: Context) {
    val windows = listOf(DnFileWindow(0, ctx, "/data/adb"), DnFileWindow(1, ctx, "/storage/emulated/0"))
    var active by mutableIntStateOf(0)
''',
'''internal class DnDualWindows(ctx: Context) {
    private val prefs = ctx.getSharedPreferences("daily_notes_dual_files", Context.MODE_PRIVATE)
    val windows = listOf(DnFileWindow(0, ctx, "/data/adb"), DnFileWindow(1, ctx, "/storage/emulated/0"))
    var active by mutableIntStateOf(prefs.getInt("active_pane", 0).coerceIn(0, 1))
    var bookmarks by mutableStateOf(prefs.getStringSet("favorites", emptySet())?.toSet() ?: emptySet())
    fun toggleBookmark(path: String) {
        val newSet = if (path in bookmarks) bookmarks - path else bookmarks + path
        bookmarks = newSet
        prefs.edit().putStringSet("favorites", newSet.toSet()).apply()
    }
''')
rep('''        if (index != active) { windows[active].capture(); active = index }
''',
'''        if (index != active) {
            windows[active].capture()
            active = index
            prefs.edit().putInt("active_pane", index).apply()
        }
''')
rep('''    var sortDialog by remember { mutableStateOf(false) }
''',
'''    var sortDialog by remember { mutableStateOf(false) }
    var favoritesDialog by remember { mutableStateOf(false) }
    var chmodTarget by remember { mutableStateOf<DualTarget?>(null) }
    var chmodMode by remember { mutableStateOf("0644") }
    val clipboard = LocalClipboardManager.current
''')
# Bookmarks in existing right-side overflow.
rep('''                        DropdownMenuItem(
                            text = { Text("输入目录路径") },
''',
'''                        DropdownMenuItem(
                            text = {
                                Text(if (current.path in state.bookmarks) "取消收藏当前目录" else "收藏当前目录")
                            },
                            onClick = {
                                expandedMenu = false
                                state.toggleBookmark(current.path)
                            },
                        )
                        DropdownMenuItem(
                            text = { Text("快速访问 / 书签") },
                            onClick = { expandedMenu = false; favoritesDialog = true },
                        )
                        DropdownMenuItem(
                            text = { Text("输入目录路径") },
''')
# A 25dp slim path strip provides a stable reference for BOTH panes.
rep('''        if (current.selectedNames.isNotEmpty()) {
''',
'''        Row(Modifier.fillMaxWidth().height(25.dp)) {
            state.windows.forEachIndexed { index, window ->
                Column(
                    Modifier.weight(1f).fillMaxHeight()
                        .background(if (state.active == index)
                            MaterialTheme.colorScheme.surfaceVariant
                            else MaterialTheme.colorScheme.surface)
                        .clickable { state.activate(index) },
                ) {
                    Text(
                        text = (if (index == 0) "左  " else "右  ") + window.path,
                        modifier = Modifier.weight(1f).padding(start = 5.dp, end = 3.dp),
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        fontSize = 10.sp,
                        lineHeight = 15.sp,
                        fontWeight = if (state.active == index) FontWeight.SemiBold else FontWeight.Normal,
                        color = if (state.active == index)
                            MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Box(
                        Modifier.fillMaxWidth().height(2.dp)
                            .background(if (state.active == index)
                                MaterialTheme.colorScheme.primary else Color.Transparent)
                    )
                }
            }
        }
        if (current.selectedNames.isNotEmpty()) {
''')
# fix "scrolling the other pane doesn't activate" at the actual nested scroll boundary.
rep('''    Column(modifier.background(if (active) white else pale)) {
''',
'''    // Nested scroll pass-through: the user's vertical drag activates its pane,
    // but returns Offset.Zero so LazyColumn keeps the entire scroll gesture.
    val paneFocusConnection = remember(pane, onActivate) {
        object : NestedScrollConnection {
            override fun onPreScroll(available: Offset, source: NestedScrollSource): Offset {
                if (source == NestedScrollSource.UserInput && available.y != 0f) {
                    onActivate()
                }
                return Offset.Zero
            }
        }
    }
    Column(modifier.nestedScroll(paneFocusConnection)
        .background(if (active) white else pale)) {
''')
# Revamp the plain-text menu; keep same 2-column operation semantics.
rep('''        Dialog(onDismissRequest = { choice = null }) {
            Surface(shape = RoundedCornerShape(8.dp)) {
''',
'''        Dialog(onDismissRequest = { choice = null }) {
            Surface(
                shape = RoundedCornerShape(14.dp),
                color = MaterialTheme.colorScheme.surface,
                tonalElevation = 2.dp,
            ) {
''')
rep('''                    Text(c.entry.name, fontSize = 13.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.padding(8.dp))
''',
'''                    Text(c.entry.name, fontSize = 16.sp, fontWeight = FontWeight.SemiBold,
                        maxLines = 1, overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.padding(start = 10.dp, top = 8.dp, end = 10.dp))
                    Text(file, fontSize = 11.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(start = 10.dp, end = 10.dp, bottom = 5.dp))
                    HorizontalDivider()
''')
rep('''                    @Composable fun option(title: String, modifier: Modifier, action: () -> Unit) {
                        Box(modifier.height(48.dp).clickable {
                            choice = null
                            action()
                        }.padding(start = 12.dp), contentAlignment = Alignment.CenterStart) {
                            Text(title, fontSize = 14.sp)
                        }
                    }
''',
'''                    @Composable fun option(title: String, modifier: Modifier, action: () -> Unit) {
                        val img = when (title) {
                            "复制 →", "复制路径" -> Icons.TwoTone.ContentCopy
                            "移动 →" -> Icons.TwoTone.DriveFileMove
                            "删除" -> Icons.TwoTone.Delete
                            "重命名" -> Icons.TwoTone.Edit
                            "属性", "权限" -> Icons.TwoTone.Info
                            "终端", "运行脚本" -> Icons.TwoTone.Terminal
                            "加入选择" -> Icons.TwoTone.Folder
                            else -> Icons.TwoTone.Description
                        }
                        Row(
                            modifier.height(49.dp)
                                .clickable { choice = null; action() }
                                .padding(start = 9.dp, end = 2.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Icon(img, null, modifier = Modifier.size(21.dp),
                                tint = MaterialTheme.colorScheme.onSurfaceVariant)
                            Spacer(Modifier.width(7.dp))
                            Text(title, fontSize = 13.sp, maxLines = 1,
                                overflow = TextOverflow.Ellipsis)
                        }
                    }
''')
# insert menu entries after existing data rows, before Dialog menu Column closing,
# by anchoring specifically to existing '加入选择' and terminal actions.
rep('''                        option("加入选择", Modifier.weight(1f)) {
                            state.windows[c.side].choose(c.entry)
                        }
                    }
''',
'''                        option("加入选择", Modifier.weight(1f)) {
                            state.windows[c.side].choose(c.entry)
                        }
                    }
                    Row(Modifier.fillMaxWidth()) {
                        option("复制路径", Modifier.weight(1f)) {
                            clipboard.setText(AnnotatedString(file))
                            message = "已复制完整路径"
                        }
                        option("权限", Modifier.weight(1f)) {
                            chmodTarget = c
                            chmodMode = "0644"
                        }
                    }
''')
# Better secondary properties scroll and copyable text.
rep('''    properties?.let { p ->
        AlertDialog(onDismissRequest = { properties = null }, title = { Text("文件属性") },
            text = { Text(p, fontSize = 12.sp) },
            confirmButton = { TextButton(onClick = { properties = null }) { Text("关闭") } })
    }
''',
'''    properties?.let { data ->
        AlertDialog(
            onDismissRequest = { properties = null },
            title = { Text("文件详情") },
            text = {
                SelectionContainer {
                    Column(Modifier.heightIn(max = 360.dp).verticalScroll(rememberScrollState())) {
                        Text(data, style = MaterialTheme.typography.bodySmall.copy(
                            fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace))
                    }
                }
            },
            confirmButton = { TextButton(onClick = { properties = null }) { Text("完成") } },
        )
    }
    chmodTarget?.let { entry ->
        val full = joined(entry.directory, entry.entry.name)
        AlertDialog(
            onDismissRequest = { chmodTarget = null },
            title = { Text("修改文件权限") },
            text = {
                Column {
                    Text(full, style = MaterialTheme.typography.bodySmall,
                        maxLines = 2, overflow = TextOverflow.Ellipsis)
                    Spacer(Modifier.height(7.dp))
                    OutlinedTextField(
                        value = chmodMode, onValueChange = { chmodMode = it },
                        singleLine = true, label = { Text("八进制权限，例如 0644 / 0755") },
                    )
                    Text("仅修改选中文件；不递归修改子目录。",
                        style = MaterialTheme.typography.labelSmall)
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    val mode = chmodMode
                    if (!mode.matches(Regex("[0-7]{3,4}"))) {
                        message = "权限格式必须是 3～4 位八进制数字"
                    } else {
                        scope.launch {
                            val result = cmd(cli,
                                "if [ -L " + qs(full) + " ]; then echo '不支持修改符号链接权限'; exit 80; fi; " +
                                "/data/adb/ksu/bin/busybox chmod " + mode + " -- " + qs(full))
                            message = if (result.ok) "权限已修改" else
                                result.value.ifBlank { "修改失败" }
                            state.windows[entry.side].refresh()
                        }
                    }
                    chmodTarget = null
                }) { Text("确定") }
            },
            dismissButton = { TextButton(onClick = { chmodTarget = null }) { Text("取消") } },
        )
    }
    if (favoritesDialog) {
        AlertDialog(
            onDismissRequest = { favoritesDialog = false },
            title = { Text("目录书签") },
            text = {
                Column(Modifier.heightIn(max = 360.dp).verticalScroll(rememberScrollState())) {
                    if (state.bookmarks.isEmpty()) {
                        Text("暂无书签。在文件页右上角可收藏当前目录。")
                    }
                    state.bookmarks.sorted().forEach { saved ->
                        Row(Modifier.fillMaxWidth().heightIn(min = 44.dp)
                            .clickable {
                                current.navigate(saved)
                                favoritesDialog = false
                            }, verticalAlignment = Alignment.CenterVertically) {
                            Text(saved, modifier = Modifier.weight(1f), maxLines = 2,
                                style = MaterialTheme.typography.bodySmall)
                            IconButton(onClick = { state.toggleBookmark(saved) },
                                modifier = Modifier.size(36.dp)) {
                                Icon(Icons.TwoTone.Delete, "删除书签")
                            }
                        }
                    }
                }
            },
            confirmButton = { TextButton(onClick = { favoritesDialog = false }) { Text("关闭") } },
        )
    }
''')
p.write_text(s, encoding="utf-8")
assert "source == NestedScrollSource.UserInput" in s
assert "state.windows.forEachIndexed { index, window ->" in s
assert "快速访问 / 书签" in s and "复制路径" in s and "修改文件权限" in s
assert "fun doOperation(o: DualOperation)" in s
assert "val destinationDir = opposite.path" in s
assert "pane.scroll.scrollToItem" in s
print("DN51: active pane follows scroll, persistent dual path indicators, compact icon menu, bookmarks, chmod, path copy")
