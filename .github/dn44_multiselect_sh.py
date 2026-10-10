#!/usr/bin/env python3
"""DN44: MT-inspired swipe multiselect, batch opposite-pane operations, SH click dialog."""
from pathlib import Path
p=Path("source/manager/app/src/main/java/com/resukisu/resukisu/ui/screen/main/DnDualPane.kt")
s=p.read_text()
def swap(a,b):
    global s
    n=s.count(a)
    if n!=1: raise SystemExit("DN44 source drift: "+a[:110]+" x "+str(n))
    s=s.replace(a,b,1)

swap('import androidx.compose.foundation.gestures.detectTapGestures\n',
'''import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
''')
swap('''private data class DualOperation(val kind: String, val from: DualTarget)''',
'''private data class DualOperation(val kind: String, val from: DualTarget,
    val others: List<DualTarget> = emptyList())''')
swap('''    var filter by mutableStateOf("")
    var error by mutableStateOf("")''',
'''    var filter by mutableStateOf("")
    var selectedNames by mutableStateOf<Set<String>>(emptySet())
    var selectAnchor by mutableIntStateOf(-1)
    fun choose(entry: DualEntry, range: Boolean = false) {
        val index = files.indexOfFirst { it.name == entry.name }
        if (index < 0) return
        if (range && selectedNames.isNotEmpty() && selectAnchor >= 0) {
            val low = minOf(index, selectAnchor)
            val high = maxOf(index, selectAnchor)
            selectedNames = selectedNames + files.subList(low, high + 1).map { it.name }
        } else {
            selectedNames = if (entry.name in selectedNames) selectedNames - entry.name
                else selectedNames + entry.name
        }
        selectAnchor = index
    }
    var error by mutableStateOf("")''')
swap('''        filter = ""
        restoring = true''',
'''        filter = ""
        selectedNames = emptySet()
        selectAnchor = -1
        restoring = true''')
swap('''    var expandedMenu by remember { mutableStateOf(false) }''',
'''    var expandedMenu by remember { mutableStateOf(false) }
    var batchMenu by remember { mutableStateOf(false) }
    var scriptChoice by remember { mutableStateOf<String?>(null) }
    fun batchAction(kind: String) {
        val selected = current.files.filter { it.name in current.selectedNames }
            .map { DualTarget(state.active, current.path, it) }
        if (selected.isNotEmpty()) {
            operation = DualOperation(kind, selected.first(), selected.drop(1))
        }
        batchMenu = false
    }''')
begin=s.index("    fun doOperation(o: DualOperation) {")
end=s.index("    BackHandler(current.back.isNotEmpty())",begin)
new=r'''    fun doOperation(o: DualOperation) {
        val sources = listOf(o.from) + o.others
        val opposite = state.windows[1 - o.from.side]
        val roots = setOf("/", "/data", "/system", "/vendor", "/product", "/metadata", "/dev", "/proc", "/sys")
        val pairs = sources.map { target ->
            joined(target.directory, target.entry.name) to joined(opposite.path, target.entry.name)
        }
        if (pairs.any { (src, dest) ->
                (o.kind == "delete" && src in roots) ||
                    (o.kind != "delete" &&
                        (src == dest || dest.startsWith(src + "/")))
            }) {
            operation = null
            message = "包含系统关键目录或无效目标路径，操作已取消"
            return
        }
        // Preflight EVERY target before touching any source. Never overwrite.
        val checks = if (o.kind == "delete") "" else pairs.joinToString("\n") { (_, dest) ->
            "if [ -e " + qs(dest) + " ] || [ -L " + qs(dest) +
                " ]; then echo '目标存在: " + dest.replace("'", "") + "'; exit 73; fi"
        }
        val commands = pairs.joinToString("\n") { (src, dest) ->
            when (o.kind) {
                "copy" -> "cp -a -- " + qs(src) + " " + qs(dest) + " || exit $?"
                "move" -> "mv -- " + qs(src) + " " + qs(dest) + " || exit $?"
                "delete" -> "rm -rf -- " + qs(src) + " || exit $?"
                else -> "exit 2"
            }
        }
        val command = checks + "\n" + commands
        operation = null
        scope.launch {
            val r = cmd(cli, command)
            message = if (r.ok) "已完成 " + sources.size + " 项" else r.value.ifBlank { "操作失败" }
            if (r.ok) {
                state.windows[o.from.side].selectedNames = emptySet()
                state.windows[o.from.side].selectAnchor = -1
            }
            state.windows[o.from.side].refresh()
            if (o.kind != "delete") opposite.refresh()
        }
    }
'''
s=s[:begin]+new+s[end:]
# UI above current file list, only when selection active.
anchor='''        if (message.isNotEmpty()) {
            Text(message, fontSize = 12.sp, color = MaterialTheme.colorScheme.error,
'''
insert=r'''        if (current.selectedNames.isNotEmpty()) {
            Surface(color = MaterialTheme.colorScheme.surfaceVariant) {
                Row(Modifier.fillMaxWidth().height(40.dp).padding(horizontal = 6.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    Text("已选 " + current.selectedNames.size, fontSize = 12.sp,
                        modifier = Modifier.weight(1f))
                    TextButton(onClick = {
                        current.selectedNames = current.files.map { it.name }.toSet()
                    }) { Text("全选", fontSize = 12.sp) }
                    TextButton(onClick = { batchMenu = true }) { Text("操作", fontSize = 12.sp) }
                    TextButton(onClick = {
                        current.selectedNames = emptySet()
                        current.selectAnchor = -1
                    }) { Text("取消", fontSize = 12.sp) }
                }
            }
        }
        if (message.isNotEmpty()) {
            Text(message, fontSize = 12.sp, color = MaterialTheme.colorScheme.error,
'''
swap(anchor,insert)
swap('''                        if (e.folder) pane.navigate(joined(pane.path, e.name))
                        else if (textFile(e.name)) openEditor(joined(pane.path, e.name))
                        else choice = DualTarget(index, pane.path, e)
''',
'''                        if (pane.selectedNames.isNotEmpty()) pane.choose(e)
                        else if (e.folder) pane.navigate(joined(pane.path, e.name))
                        else if (e.name.endsWith(".sh", ignoreCase = true)) {
                            scriptChoice = joined(pane.path, e.name)
                        } else if (textFile(e.name)) openEditor(joined(pane.path, e.name))
                        else choice = DualTarget(index, pane.path, e)
''')
swap('''                    onMenu = { e -> state.activate(index); choice = DualTarget(index, pane.path, e) },
                    onActivate = { state.activate(index) })
''',
'''                    onMenu = { e -> state.activate(index); choice = DualTarget(index, pane.path, e) },
                    onSelect = { e, range -> state.activate(index); pane.choose(e, range) },
                    onActivate = { state.activate(index) })
''')
swap('''    choice?.let { c ->
''',r'''    if (batchMenu) {
        AlertDialog(
            onDismissRequest = { batchMenu = false },
            title = { Text("已选文件操作") },
            text = { Text("已选择 " + current.selectedNames.size + " 项，复制、移动均以对侧窗口当前目录为目标。") },
            confirmButton = {
                Column {
                    TextButton(onClick = { batchAction("copy") }) { Text("复制到对侧窗口") }
                    TextButton(onClick = { batchAction("move") }) { Text("移动到对侧窗口") }
                    TextButton(onClick = { batchAction("delete") }) { Text("删除所选文件") }
                }
            },
            dismissButton = { TextButton(onClick = { batchMenu = false }) { Text("取消") } },
        )
    }
    scriptChoice?.let { script ->
        AlertDialog(
            onDismissRequest = { scriptChoice = null },
            title = { Text("SH 脚本") },
            text = { Text(script + "\n请选择 Root 执行或打开编辑。") },
            confirmButton = { TextButton(onClick = {
                scriptChoice = null
                runScript(script)
            }) { Text("Root 执行") } },
            dismissButton = {
                Row {
                    TextButton(onClick = {
                        scriptChoice = null
                        openEditor(script)
                    }) { Text("编辑") }
                    TextButton(onClick = { scriptChoice = null }) { Text("取消") }
                }
            },
        )
    }
    choice?.let { c ->
''')
swap('''    onTap: (DualEntry) -> Unit, onMenu: (DualEntry) -> Unit, onActivate: () -> Unit
''','''    onTap: (DualEntry) -> Unit, onMenu: (DualEntry) -> Unit,
    onSelect: (DualEntry, Boolean) -> Unit, onActivate: () -> Unit
''')
swap('''            items(shown, key = { pane.path + ":" + it.name }) { item ->
                Row(Modifier.fillMaxWidth().heightIn(min = 40.dp)
                    .pointerInput(item.name, pane.path) {
                        detectTapGestures(
                            onTap = { onTap(item) },
                            onLongPress = { onMenu(item) },
                        )
                    }.padding(horizontal = 3.dp, vertical = 4.dp),
''',
'''            items(shown, key = { pane.path + ":" + it.name }) { item ->
                var dragAmount = 0f
                Row(Modifier.fillMaxWidth().heightIn(min = 40.dp)
                    .background(if (item.name in pane.selectedNames) Color(0xFFDCE9FF) else Color.Transparent)
                    .pointerInput(item.name, pane.path) {
                        detectHorizontalDragGestures(
                            onHorizontalDrag = { change, delta ->
                                dragAmount += delta
                                change.consume()
                            },
                            onDragEnd = {
                                if (kotlin.math.abs(dragAmount) > 25f)
                                    onSelect(item, pane.selectedNames.isNotEmpty())
                                dragAmount = 0f
                            },
                            onDragCancel = { dragAmount = 0f },
                        )
                    }
                    .pointerInput(item.name, pane.path) {
                        detectTapGestures(
                            onTap = { onTap(item) },
                            onLongPress = {
                                if (pane.selectedNames.isNotEmpty()) onSelect(item, true)
                                else onMenu(item)
                            },
                        )
                    }.padding(horizontal = 3.dp, vertical = 4.dp),
''')
p.write_text(s)
assert "detectHorizontalDragGestures" in s
assert "pane.choose(e" in s
assert "scriptChoice?.let" in s
assert "已选文件操作" in s
assert "sources.map" in s and "pairs.joinToString" in s
print("DN44: swipe/range select, batch operations to opposite pane, script execute/edit choice")
