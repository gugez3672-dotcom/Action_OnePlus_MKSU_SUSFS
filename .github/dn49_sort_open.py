#!/usr/bin/env python3
"""DN49: independent per-directory sorting + invert select + safe read-only hex preview."""
from pathlib import Path
p=Path("source/manager/app/src/main/java/com/resukisu/resukisu/ui/screen/main/DnDualPane.kt")
s=p.read_text()
def rep(a,b):
    global s
    if s.count(a)!=1: raise SystemExit("DN49 drift "+a[:110]+" x "+str(s.count(a)))
    s=s.replace(a,b,1)
rep('''    var filter by mutableStateOf("")
    var selectedNames by mutableStateOf<Set<String>>(emptySet())
''',
'''    var filter by mutableStateOf("")
    var sortMode by mutableStateOf(prefs.getString("sort_" + path, "name") ?: "name")
    var reversed by mutableStateOf(prefs.getBoolean("reverse_" + path, false))
    fun visible(): List<DualEntry> {
        val subset = if (filter.isBlank()) files else files.filter { it.name.contains(filter, true) }
        val ordered = subset.sortedWith(Comparator { a, b ->
            if (a.folder != b.folder) return@Comparator if (a.folder) -1 else 1
            val result = when(sortMode) {
                "time" -> a.mtime.compareTo(b.mtime)
                "size" -> a.size.compareTo(b.size)
                "type" -> a.name.substringAfterLast('.', "").compareTo(b.name.substringAfterLast('.', ""), true)
                else -> a.name.compareTo(b.name, true)
            }
            val sign = if (reversed) -result else result
            if (sign != 0) sign else a.name.compareTo(b.name, true)
        })
        return ordered
    }
    fun sortBy(mode: String, descending: Boolean) {
        capture()
        sortMode = mode
        reversed = descending
        prefs.edit().putString("sort_" + path, mode)
            .putBoolean("reverse_" + path, descending).apply()
    }
    var selectedNames by mutableStateOf<Set<String>>(emptySet())
''')
rep('''        val index = files.indexOfFirst { it.name == entry.name }
''',
'''        val entries = visible()
        val index = entries.indexOfFirst { it.name == entry.name }
''')
rep('''            selectedNames = selectedNames + files.subList(low, high + 1).map { it.name }''',
'''            selectedNames = selectedNames + entries.subList(low, high + 1).map { it.name }''')
rep('''        val shown = if (filter.isBlank()) files else files.filter { it.name.contains(filter, true) }''',
'''        val shown = visible()''')
rep('''        filter = ""
        selectedNames = emptySet()''',
'''        filter = ""
        sortMode = prefs.getString("sort_" + path, "name") ?: "name"
        reversed = prefs.getBoolean("reverse_" + path, false)
        selectedNames = emptySet()''')
rep('''    var filterVisible by remember { mutableStateOf(false) }''',
'''    var filterVisible by remember { mutableStateOf(false) }
    var sortDialog by remember { mutableStateOf(false) }''')
rep('''                        DropdownMenuItem(
                            text = { Text("输入目录路径") },
''',
'''                        DropdownMenuItem(
                            text = { Text("目录排序") },
                            onClick = { expandedMenu = false; sortDialog = true },
                        )
                        DropdownMenuItem(
                            text = { Text("输入目录路径") },
''')
rep('''                    TextButton(onClick = {
                        current.selectedNames = current.files.map { it.name }.toSet()
                    }) { Text("全选", fontSize = 12.sp) }
''',
'''                    TextButton(onClick = {
                        current.selectedNames = current.visible().map { it.name }.toSet()
                    }) { Text("全选", fontSize = 12.sp) }
                    TextButton(onClick = {
                        current.selectedNames = current.visible().map { it.name }
                            .filterNot { it in current.selectedNames }.toSet()
                    }) { Text("反选", fontSize = 12.sp) }
''')
rep('''    if (batchMenu) {
''',
'''    if (sortDialog) {
        AlertDialog(
            onDismissRequest = { sortDialog = false },
            title = { Text("当前目录排序") },
            text = {
                Column {
                    listOf("name" to "名称", "time" to "修改时间",
                        "size" to "大小", "type" to "类型").forEach { (mode, title) ->
                        Row(Modifier.fillMaxWidth().clickable {
                            val name = current.visible().getOrNull(
                                (current.scroll.firstVisibleItemIndex - 1).coerceAtLeast(0))?.name
                            current.sortBy(mode, current.reversed)
                            scope.launch {
                                withFrameNanos { }
                                val index = current.visible().indexOfFirst { it.name == name }
                                if (index >= 0) current.scroll.scrollToItem(index + 1)
                            }
                            sortDialog = false
                        }, verticalAlignment = Alignment.CenterVertically) {
                            RadioButton(selected = current.sortMode == mode, onClick = {
                                current.sortBy(mode, current.reversed)
                                sortDialog = false
                            })
                            Text(title)
                        }
                    }
                    Row(Modifier.clickable {
                        current.sortBy(current.sortMode, !current.reversed)
                    }, verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(checked = current.reversed, onCheckedChange = {
                            current.sortBy(current.sortMode, it)
                        })
                        Text("降序")
                    }
                }
            },
            confirmButton = { TextButton(onClick = { sortDialog = false }) { Text("完成") } },
        )
    }
    if (batchMenu) {
''')
rep('''                    Row(Modifier.fillMaxWidth()) {
                        option("终端", Modifier.weight(1f)) { openTerminal(if (c.entry.folder) file else c.directory) }
''',
'''                    Row(Modifier.fillMaxWidth()) {
                        option("十六进制预览", Modifier.weight(1f)) {
                            properties = "读取中…"
                            scope.launch {
                                properties = cmd(cli,
                                    "/data/adb/ksu/bin/busybox hexdump -C -n 512 -- " + qs(file)).value
                            }
                        }
                        option("终端", Modifier.weight(1f)) { openTerminal(if (c.entry.folder) file else c.directory) }
''')
rep('''    val shown = if (pane.filter.isBlank()) pane.files else pane.files.filter { it.name.contains(pane.filter, true) }''',
'''    val shown = pane.visible()''')
p.write_text(s)
assert 'sort_" + path' in s and 'current.sortBy(' in s
assert '十六进制预览' in s and '反选' in s
assert 'val shown = pane.visible()' in s
print("DN49 per-folder sorting, invert selection, read-only 512-byte hex preview")
