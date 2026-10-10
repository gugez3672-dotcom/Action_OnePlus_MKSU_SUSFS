#!/usr/bin/env python3
from pathlib import Path

base = Path("source/manager/app/src/main/java/com/resukisu/resukisu/ui/screen/main")
ui = base / "DnDualPane.kt"
if ui.exists():
    raise SystemExit("duplicate DN40")
ui.write_text(r'''package com.resukisu.resukisu.ui.screen.main

import android.content.Context
import android.util.Base64
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.twotone.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import com.resukisu.resukisu.data.shell.KsuCliRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import org.koin.compose.koinInject
import java.util.Locale

private val dark = Color(0xFF292929)
private val grey = Color(0xFF777777)
private val white = Color.White
private val pale = Color(0xFFF6F6F6)
private val divider = Color(0xFFE4E4E4)

internal data class DualEntry(val name: String, val folder: Boolean, val size: Long, val mtime: Long)
private data class DualAnchor(val name: String?, val index: Int, val offset: Int)
private data class DualTarget(val side: Int, val directory: String, val entry: DualEntry)
private data class DualOperation(val kind: String, val from: DualTarget)
private data class DualResult(val value: String, val ok: Boolean)
private fun qs(v: String) = "'" + v.replace("'", "'\"'\"'") + "'"
private fun joined(d: String, n: String) = if (d == "/") "/" + n else d + "/" + n
private fun parentDir(d: String) = if (d == "/") "/" else d.trimEnd('/').substringBeforeLast('/', "").ifEmpty { "/" }
private fun textFile(n: String) = listOf(".txt",".sh",".prop",".conf",".json",".xml",".log",".rc",".md",".ini",".yml")
    .any { n.endsWith(it, true) }
private fun dateText(n: Long): String = if (n <= 0L) "" else
    java.text.SimpleDateFormat("yy-MM-dd HH:mm", Locale.getDefault()).format(java.util.Date(n * 1000L))
private fun sizeText(n: Long): String = when {
    n < 1024L -> n.toString() + "B"
    n < 1048576L -> "%.1fK".format(Locale.US, n / 1024.0)
    n < 1073741824L -> "%.1fM".format(Locale.US, n / 1048576.0)
    else -> "%.1fG".format(Locale.US, n / 1073741824.0)
}

internal class DnFileWindow(val side: Int, ctx: Context, initial: String) {
    private val prefs = ctx.getSharedPreferences("daily_notes_dual_files", Context.MODE_PRIVATE)
    var path by mutableStateOf(prefs.getString("path_" + side, initial) ?: initial)
    var files by mutableStateOf<List<DualEntry>>(emptyList())
    var filter by mutableStateOf("")
    var error by mutableStateOf("")
    var loading by mutableStateOf(false)
    var refreshId by mutableIntStateOf(0)
    var restoring = true
    var back by mutableStateOf<List<String>>(emptyList())
    var forward by mutableStateOf<List<String>>(emptyList())
    val scroll = LazyListState()
    private val anchors = mutableMapOf<String, DualAnchor>()
    private fun key(p: String) = "pos_" + side + "_" +
        Base64.encodeToString(p.toByteArray(Charsets.UTF_8), Base64.NO_WRAP or Base64.URL_SAFE)
    fun capture() {
        if (restoring) return
        val i = scroll.firstVisibleItemIndex
        val anchor = DualAnchor(files.getOrNull(i - 1)?.name, i, scroll.firstVisibleItemScrollOffset)
        anchors[path] = anchor
        prefs.edit().putString(key(path), JSONObject().put("name", anchor.name)
            .put("index", i).put("offset", anchor.offset).toString()).apply()
    }
    fun saved(): DualAnchor? {
        anchors[path]?.let { return it }
        return runCatching {
            val o = JSONObject(prefs.getString(key(path), "") ?: "")
            DualAnchor(if (o.isNull("name")) null else o.optString("name"),
                o.optInt("index"), o.optInt("offset"))
        }.getOrNull()
    }
    fun navigate(destination: String, push: Boolean = true) {
        val d = destination.trim().replace(Regex("/+"), "/").trimEnd('/').ifEmpty { "/" }
        if (!d.startsWith("/")) return
        if (d == path) { refresh(); return }
        capture()
        if (push) { back = (back + path).takeLast(48); forward = emptyList() }
        path = d
        prefs.edit().putString("path_" + side, path).apply()
        filter = ""
        restoring = true
        files = emptyList()
        refreshId++
    }
    fun backwards() {
        val p = back.lastOrNull() ?: return
        back = back.dropLast(1)
        forward = (forward + path).takeLast(48)
        navigate(p, false)
    }
    fun forwards() {
        val p = forward.lastOrNull() ?: return
        forward = forward.dropLast(1)
        back = (back + path).takeLast(48)
        navigate(p, false)
    }
    fun refresh() { refreshId++ }
}
internal class DnDualWindows(ctx: Context) {
    val windows = listOf(DnFileWindow(0, ctx, "/data/adb"), DnFileWindow(1, ctx, "/storage/emulated/0"))
    var active by mutableIntStateOf(0)
    fun activate(index: Int) {
        if (index != active) { windows[active].capture(); active = index }
    }
}
private suspend fun cmd(cli: KsuCliRepository, command: String): DualResult = withContext(Dispatchers.IO) {
    val output = arrayListOf<String>()
    val errors = arrayListOf<String>()
    val r = cli.withNewRootShell(globalMnt = true) {
        newJob().add(command).to(output, errors).exec()
    }
    DualResult((output + errors).joinToString("\n"), r.isSuccess)
}
private suspend fun readDirectory(cli: KsuCliRepository, path: String): DualResult {
    val d = '$'
    val bb = "/data/adb/ksu/bin/busybox"
    val script = "P=" + qs(path) + "\n" +
        "if [ ! -d \"" + d + "P\" ]; then echo '目录无法访问'; exit 2; fi\n" +
        "for f in \"" + d + "P\"/* \"" + d + "P\"/.[!.]* \"" + d + "P\"/..?*; do\n" +
        "  [ -e \"" + d + "f\" ] || [ -L \"" + d + "f\" ] || continue\n" +
        "  if [ -d \"" + d + "f\" ]; then t=D; else t=F; fi\n" +
        "  s=$(" + bb + " stat -c '%s' \"" + d + "f\" 2>/dev/null || echo 0)\n" +
        "  m=$(" + bb + " stat -c '%Y' \"" + d + "f\" 2>/dev/null || echo 0)\n" +
        "  n=$(" + bb + " basename \"" + d + "f\")\n" +
        "  printf '%s\\t%s\\t%s\\t%s\\n' \"" + d + "t\" \"" + d + "s\" \"" + d + "m\" \"" + d + "n\"\n" +
        "done"
    return cmd(cli, script)
}
private fun parseEntries(s: String): List<DualEntry> =
    s.lineSequence().mapNotNull { line ->
        val parts = line.split('\t', limit = 4)
        if (parts.size != 4 || parts[0] !in listOf("D", "F")) null
        else DualEntry(parts[3], parts[0] == "D", parts[1].toLongOrNull() ?: 0L,
            parts[2].toLongOrNull() ?: 0L)
    }.distinctBy { it.name }.sortedWith(compareBy<DualEntry>({ !it.folder }, { it.name.lowercase(Locale.ROOT) }))

@Composable
internal fun DnDualFiles(
    state: DnDualWindows,
    openTerminal: (String) -> Unit,
    runScript: (String) -> Unit,
    openEditor: (String) -> Unit,
) {
    val cli: KsuCliRepository = koinInject()
    val scope = rememberCoroutineScope()
    val current = state.windows[state.active]
    var choice by remember { mutableStateOf<DualTarget?>(null) }
    var operation by remember { mutableStateOf<DualOperation?>(null) }
    var rename by remember { mutableStateOf<DualTarget?>(null) }
    var renameText by remember { mutableStateOf(TextFieldValue("")) }
    var properties by remember { mutableStateOf<String?>(null) }
    var addressDialog by remember { mutableStateOf(false) }
    var address by remember { mutableStateOf("") }
    var newDialog by remember { mutableStateOf(false) }
    var newName by remember { mutableStateOf("") }
    var filterVisible by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("") }

    fun doOperation(o: DualOperation) {
        val source = joined(o.from.directory, o.from.entry.name)
        val opposite = state.windows[1 - o.from.side]
        val destination = joined(opposite.path, o.from.entry.name)
        if (o.kind != "delete" && (source == destination ||
            (o.from.entry.folder && destination.startsWith(source + "/")))) {
            operation = null; message = "目标路径无效"; return
        }
        val action = when (o.kind) {
            "delete" -> "rm -rf -- " + qs(source)
            "copy" -> "cp -a -- " + qs(source) + " " + qs(destination)
            "move" -> "mv -- " + qs(source) + " " + qs(destination)
            else -> return
        }
        val command = if (o.kind == "delete") action else
            "if [ -e " + qs(destination) + " ] || [ -L " + qs(destination) +
                " ]; then echo '对侧存在同名文件，未覆盖'; exit 73; fi; " + action
        operation = null
        scope.launch {
            val r = cmd(cli, command)
            message = if (r.ok) "操作完成" else r.value.ifBlank { "操作失败" }
            state.windows[o.from.side].refresh()
            if (o.kind != "delete") opposite.refresh()
        }
    }
    BackHandler(current.back.isNotEmpty()) { current.backwards() }
    Column(Modifier.fillMaxSize()) {
        Surface(color = dark) {
            Column(Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 1.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(current.path,
                        Modifier.weight(1f).clickable { address = current.path; addressDialog = true }
                            .padding(start = 7.dp, top = 2.dp, bottom = 2.dp),
                        color = white, fontSize = 16.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    IconButton(onClick = { filterVisible = !filterVisible }, modifier = Modifier.size(34.dp)) {
                        Icon(Icons.TwoTone.Description, "筛选", tint = white)
                    }
                    IconButton(onClick = { current.refresh() }, modifier = Modifier.size(34.dp)) {
                        Icon(Icons.TwoTone.Refresh, "刷新", tint = white)
                    }
                    IconButton(onClick = { openTerminal(current.path) }, modifier = Modifier.size(34.dp)) {
                        Icon(Icons.TwoTone.Terminal, "终端", tint = white)
                    }
                }
                Text("文件夹: " + current.files.count { it.folder } +
                    "  文件: " + current.files.count { !it.folder } +
                    (if (state.active == 0) "  左窗口" else "  右窗口"),
                    modifier = Modifier.padding(start = 7.dp), fontSize = 11.sp, color = Color.LightGray)
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceEvenly) {
                    TextButton(onClick = { current.backwards() }, enabled = current.back.isNotEmpty(),
                        modifier = Modifier.height(30.dp)) { Text("←", fontSize = 12.sp) }
                    TextButton(onClick = { current.forwards() }, enabled = current.forward.isNotEmpty(),
                        modifier = Modifier.height(30.dp)) { Text("→", fontSize = 12.sp) }
                    TextButton(onClick = { current.navigate(parentDir(current.path)) },
                        enabled = current.path != "/", modifier = Modifier.height(30.dp)) { Text("↑", fontSize = 12.sp) }
                    TextButton(onClick = { state.windows[1 - state.active].navigate(current.path) },
                        modifier = Modifier.height(30.dp)) { Text("同步", fontSize = 12.sp) }
                    TextButton(onClick = { newName = ""; newDialog = true },
                        modifier = Modifier.height(30.dp)) { Text("新建", fontSize = 12.sp) }
                }
                if (filterVisible) {
                    OutlinedTextField(value = current.filter, onValueChange = { current.filter = it },
                        modifier = Modifier.fillMaxWidth(), singleLine = true,
                        label = { Text("筛选当前窗口", color = white) },
                        textStyle = androidx.compose.ui.text.TextStyle(color = white, fontSize = 13.sp))
                }
            }
        }
        if (message.isNotEmpty()) {
            Text(message, fontSize = 12.sp, color = MaterialTheme.colorScheme.error,
                modifier = Modifier.fillMaxWidth().clickable { message = "" }.padding(4.dp))
        }
        Row(Modifier.fillMaxSize()) {
            state.windows.forEachIndexed { index, pane ->
                DnFileList(pane, cli, state.active == index, Modifier.weight(1f).fillMaxHeight(),
                    onTap = { e ->
                        state.activate(index)
                        if (e.folder) pane.navigate(joined(pane.path, e.name))
                        else if (textFile(e.name)) openEditor(joined(pane.path, e.name))
                        else choice = DualTarget(index, pane.path, e)
                    },
                    onMenu = { e -> state.activate(index); choice = DualTarget(index, pane.path, e) },
                    onActivate = { state.activate(index) })
                if (index == 0) Box(Modifier.width(1.dp).fillMaxHeight().background(Color.LightGray))
            }
        }
    }
    choice?.let { c ->
        val file = joined(c.directory, c.entry.name)
        Dialog(onDismissRequest = { choice = null }) {
            Surface(shape = RoundedCornerShape(8.dp)) {
                Column(Modifier.padding(8.dp)) {
                    Text(c.entry.name, fontSize = 13.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.padding(8.dp))
                    @Composable fun option(title: String, action: () -> Unit) {
                        Box(Modifier.weight(1f).height(48.dp).clickable {
                            choice = null
                            action()
                        }.padding(start = 12.dp), contentAlignment = Alignment.CenterStart) {
                            Text(title, fontSize = 14.sp)
                        }
                    }
                    Row(Modifier.fillMaxWidth()) {
                        option("复制 →") { operation = DualOperation("copy", c) }
                        option("移动 →") { operation = DualOperation("move", c) }
                    }
                    Row(Modifier.fillMaxWidth()) {
                        option("删除") { operation = DualOperation("delete", c) }
                        option("重命名") {
                            rename = c
                            val n = c.entry.name
                            renameText = TextFieldValue(n, selection = TextRange(0,
                                n.lastIndexOf('.').takeIf { it > 0 } ?: n.length))
                        }
                    }
                    Row(Modifier.fillMaxWidth()) {
                        option("编辑") { openEditor(file) }
                        option("属性") {
                            properties = "读取中…"
                            scope.launch { properties = cmd(cli,
                                "/data/adb/ksu/bin/busybox stat -- " + qs(file) +
                                "; ls -ldZ " + qs(file)).value }
                        }
                    }
                    Row(Modifier.fillMaxWidth()) {
                        option("终端") { openTerminal(if (c.entry.folder) file else c.directory) }
                        option(if (c.entry.name.endsWith(".sh", true)) "运行脚本" else "打开") {
                            if (c.entry.name.endsWith(".sh", true)) runScript(file)
                            else if (c.entry.folder) state.windows[c.side].navigate(file)
                            else openEditor(file)
                        }
                    }
                }
            }
        }
    }
    operation?.let { o ->
        val source = joined(o.from.directory, o.from.entry.name)
        val dest = joined(state.windows[1 - o.from.side].path, o.from.entry.name)
        AlertDialog(onDismissRequest = { operation = null },
            title = { Text(when(o.kind) { "copy" -> "复制至对侧窗口"; "move" -> "移动至对侧窗口"; else -> "确认删除" }) },
            text = { Text(if (o.kind == "delete") source + "\n删除后无法恢复。"
                else "源：" + source + "\n目标：" + dest + "\n若目标存在则取消操作。") },
            confirmButton = { TextButton(onClick = { doOperation(o) }) { Text("确定") } },
            dismissButton = { TextButton(onClick = { operation = null }) { Text("取消") } })
    }
    rename?.let { c ->
        AlertDialog(onDismissRequest = { rename = null }, title = { Text("重命名") },
            text = { OutlinedTextField(value = renameText, onValueChange = { renameText = it }, singleLine = true) },
            confirmButton = { TextButton(onClick = {
                val name = renameText.text.trim()
                if (name.isNotBlank() && name != "." && name != ".." && '/' !in name) {
                    val old = joined(c.directory, c.entry.name)
                    val new = joined(c.directory, name)
                    scope.launch {
                        val result = cmd(cli, "if [ -e " + qs(new) + " ]; then exit 73; fi; mv -- " +
                            qs(old) + " " + qs(new))
                        message = if (result.ok) "重命名完成" else result.value.ifBlank { "失败" }
                        state.windows[c.side].refresh()
                    }
                } else message = "无效文件名"
                rename = null
            }) { Text("确定") } },
            dismissButton = { TextButton(onClick = { rename = null }) { Text("取消") } })
    }
    if (addressDialog) {
        AlertDialog(onDismissRequest = { addressDialog = false }, title = { Text("路径跳转") },
            text = { OutlinedTextField(value = address, onValueChange = { address = it }, singleLine = true) },
            confirmButton = { TextButton(onClick = {
                if (address.startsWith("/")) current.navigate(address) else message = "请输入绝对路径"
                addressDialog = false
            }) { Text("跳转") } },
            dismissButton = { TextButton(onClick = { addressDialog = false }) { Text("取消") } })
    }
    if (newDialog) {
        AlertDialog(onDismissRequest = { newDialog = false }, title = { Text("新建文件或文件夹") },
            text = { OutlinedTextField(value = newName, onValueChange = { newName = it }, singleLine = true) },
            confirmButton = {
                Row {
                    listOf("文件", "文件夹").forEach { type ->
                        TextButton(onClick = {
                            val name = newName.trim()
                            if (name.isNotBlank() && name != "." && name != ".." && '/' !in name) {
                                val path = joined(current.path, name)
                                scope.launch {
                                    val r = cmd(cli, if (type == "文件")
                                        "if [ -e " + qs(path) + " ]; then exit 73; fi; : > " + qs(path)
                                        else "mkdir -- " + qs(path))
                                    message = if (r.ok) "创建完成" else r.value.ifBlank { "失败" }
                                    current.refresh()
                                }
                            } else message = "无效文件名"
                            newDialog = false
                        }) { Text(type) }
                    }
                }
            },
            dismissButton = { TextButton(onClick = { newDialog = false }) { Text("取消") } })
    }
    properties?.let { p ->
        AlertDialog(onDismissRequest = { properties = null }, title = { Text("文件属性") },
            text = { Text(p, fontSize = 12.sp) },
            confirmButton = { TextButton(onClick = { properties = null }) { Text("关闭") } })
    }
}

@Composable
private fun DnFileList(
    pane: DnFileWindow, cli: KsuCliRepository, active: Boolean, modifier: Modifier,
    onTap: (DualEntry) -> Unit, onMenu: (DualEntry) -> Unit, onActivate: () -> Unit
) {
    LaunchedEffect(pane.path, pane.refreshId) {
        val path = pane.path
        val id = pane.refreshId
        pane.loading = true
        pane.error = ""
        try {
            val r = readDirectory(cli, path)
            if (id != pane.refreshId || path != pane.path) return@LaunchedEffect
            if (!r.ok) pane.error = r.value.ifBlank { "无法访问目录" }
            else {
                val files = parseEntries(r.value)
                pane.files = files
                if (pane.restoring) {
                    val mark = pane.saved()
                    withFrameNanos { }
                    if (mark != null) {
                        val idx = mark.name?.let { n -> files.indexOfFirst { it.name == n }.takeIf { it >= 0 }?.plus(1) }
                            ?: mark.index
                        pane.scroll.scrollToItem(idx.coerceIn(0, files.size), mark.offset.coerceAtLeast(0))
                    } else pane.scroll.scrollToItem(0)
                    pane.restoring = false
                }
            }
        } catch (e: Exception) {
            if (id == pane.refreshId) pane.error = e.message ?: "读取失败"
        } finally {
            if (id == pane.refreshId) pane.loading = false
        }
    }
    LaunchedEffect(pane) {
        snapshotFlow { pane.scroll.firstVisibleItemIndex to pane.scroll.firstVisibleItemScrollOffset }
            .collectLatest {
                delay(300)
                pane.capture()
            }
    }
    DisposableEffect(pane) { onDispose { pane.capture() } }
    val shown = if (pane.filter.isBlank()) pane.files else pane.files.filter { it.name.contains(pane.filter, true) }
    Column(modifier.background(if (active) white else pale)) {
        if (pane.error.isNotBlank()) Text(pane.error, color = Color.Red, fontSize = 11.sp, maxLines = 2)
        if (pane.loading) HorizontalDivider(thickness = 2.dp, color = Color(0xFF357ADF))
        LazyColumn(state = pane.scroll, modifier = Modifier.fillMaxSize()) {
            item(key = "parent_" + pane.path) {
                Row(Modifier.fillMaxWidth().height(40.dp).clickable {
                    onActivate()
                    pane.navigate(parentDir(pane.path))
                }.padding(horizontal = 3.dp), verticalAlignment = Alignment.CenterVertically) {
                    FolderGlyph()
                    Spacer(Modifier.width(3.dp))
                    Text("..", fontSize = 14.sp)
                }
            }
            items(shown, key = { pane.path + ":" + it.name }) { item ->
                Row(Modifier.fillMaxWidth().heightIn(min = 40.dp)
                    .pointerInput(item.name, pane.path) {
                        detectTapGestures(
                            onTap = { onTap(item) },
                            onLongPress = { onMenu(item) },
                        )
                    }.padding(horizontal = 3.dp, vertical = 4.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    if (item.folder) FolderGlyph() else
                        Icon(if (textFile(item.name)) Icons.TwoTone.Description else Icons.TwoTone.InsertDriveFile,
                            contentDescription = null, modifier = Modifier.size(32.dp),
                            tint = if (textFile(item.name)) Color(0xFF427CB0) else grey)
                    Spacer(Modifier.width(3.dp))
                    Column(Modifier.weight(1f)) {
                        Text(item.name, fontSize = 14.sp, lineHeight = 15.sp, color = dark,
                            maxLines = 2, overflow = TextOverflow.Ellipsis)
                        Text(dateText(item.mtime) + (if (item.folder) "" else "  " + sizeText(item.size)),
                            fontSize = 11.sp, lineHeight = 12.sp, color = grey,
                            maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                }
                HorizontalDivider(thickness = 0.3.dp, color = divider)
            }
        }
    }
}
@Composable
private fun FolderGlyph() {
    Box(Modifier.size(32.dp).background(dark, RoundedCornerShape(5.dp)),
        contentAlignment = Alignment.Center) {
        Icon(Icons.TwoTone.Folder, null, modifier = Modifier.size(20.dp), tint = white)
    }
}
''', encoding="utf-8")

tools = base / "ToolsPage.kt"
s = tools.read_text()
start_tag = '''            if (tab == 0) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Row(
'''
end_tag = '''            } else {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Icon(Icons.TwoTone.Terminal, contentDescription = null)
'''
start = s.find(start_tag, s.index('    Scaffold(containerColor = Color.Transparent)'))
end = s.find(end_tag, start)
if start == -1 or end == -1 or end <= start:
    raise SystemExit("could not locate tools file-pane boundaries")
s = s[:start] + '''            if (tab == 0) {
                DnDualFiles(
                    state = dualWindows,
                    openTerminal = { openTerminalAt(it) },
                    runScript = { runScriptInTerminal(it) },
                    openEditor = { loadEditor(it) },
                )
''' + s[end:]
prefs_tag = '''    val toolPrefs = remember(context) {
        context.getSharedPreferences("daily_notes_root_tools", Context.MODE_PRIVATE)
    }
'''
if s.count(prefs_tag) != 1: raise SystemExit("preferences anchor missing")
s = s.replace(prefs_tag, prefs_tag + '    val dualWindows = remember(context) { DnDualWindows(context) }\n', 1)
old_header = '''            Text(
                text = "工具",
                style = MaterialTheme.typography.headlineLarge,
                modifier = Modifier.padding(top = 10.dp, bottom = 10.dp),
            )
'''
if s.count(old_header) != 1: raise SystemExit("header anchor missing")
s = s.replace(old_header, '''            Text(
                text = "工具",
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.padding(top = 2.dp, bottom = 2.dp),
            )
''', 1)
old_margin = '                .padding(horizontal = 16.dp)\n                .padding(bottom = bottomPadding + 8.dp),'
if s.count(old_margin) != 1: raise SystemExit("margins anchor missing")
s = s.replace(old_margin, '                .padding(bottom = bottomPadding + 2.dp),', 1)
tools.write_text(s)

t = ui.read_text()
assert 'val destination = joined(opposite.path, o.from.entry.name)' in t
assert '"复制至对侧窗口"' in t and '"移动至对侧窗口"' in t
assert 'pane.capture()' in t and 'pane.scroll.scrollToItem' in t
assert 'LazyColumn(state = pane.scroll' in t
assert 'heightIn(min = 40.dp)' in t and 'size(32.dp)' in t
assert 'RootInteractiveSession(' in s
assert 'fun runScriptInTerminal(path: String)' in s
assert 'openTerminal = { openTerminalAt(it) }' in s
print("DN40: MT-style compact dual-pane UI and actual opposite-pane copy/move applied.")
