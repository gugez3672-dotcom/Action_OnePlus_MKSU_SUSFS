#!/usr/bin/env python3
"""DN42: unify top toolbar with MT-inspired compact header; retain DN bottom nav.

Applies AFTER dn40 and dn41. Remove the redundant Tools title/tab strip, keep
terminal reachable from path bar, and keep all existing two-pane file actions.
Only UI composition changes; Root file operations and backend are untouched.
"""
from pathlib import Path

base = Path("source/manager/app/src/main/java/com/resukisu/resukisu/ui/screen/main")
pane = base / "DnDualPane.kt"
tools = base / "ToolsPage.kt"

def replace_one(path: Path, old: str, new: str):
    s = path.read_text(encoding="utf-8")
    n = s.count(old)
    if n != 1:
        raise SystemExit(f"DN42 {path.name}: expected exactly one anchor, got {n}: {old[:100]!r}")
    path.write_text(s.replace(old, new, 1), encoding="utf-8")

s = pane.read_text(encoding="utf-8")
anchor = '    var message by remember { mutableStateOf("") }\n'
assert s.count(anchor) == 1
s = s.replace(anchor, anchor + '    var expandedMenu by remember { mutableStateOf(false) }\n', 1)
start = s.index('''        Surface(color = dark) {''', s.index("    BackHandler(current.back.isNotEmpty())"))
end = s.index('''        if (message.isNotEmpty()) {''', start)
header = r'''        // One continuous 56dp toolbar. The DN navigation bar stays at bottom.
        Surface(color = dark, modifier = Modifier.fillMaxWidth()) {
            Row(
                modifier = Modifier.fillMaxWidth().height(56.dp).padding(horizontal = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                IconButton(
                    onClick = { current.navigate(parentDir(current.path)) },
                    enabled = current.path != "/",
                    modifier = Modifier.size(40.dp),
                ) {
                    Icon(Icons.TwoTone.ArrowUpward, "返回上级",
                        tint = if (current.path != "/") white else Color.Gray)
                }
                Column(
                    modifier = Modifier.weight(1f)
                        .clickable { address = current.path; addressDialog = true }
                        .padding(start = 5.dp, end = 4.dp),
                    verticalArrangement = Arrangement.Center,
                ) {
                    Text(
                        text = current.path,
                        color = white,
                        fontSize = 18.sp,
                        lineHeight = 22.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(
                        text = "文件夹 " + current.files.count { it.folder } +
                            "  文件 " + current.files.count { !it.folder } +
                            if (state.active == 0) "  · 左" else "  · 右",
                        color = Color(0xFFCECECE),
                        fontSize = 11.sp,
                        lineHeight = 15.sp,
                        maxLines = 1,
                    )
                }
                IconButton(
                    onClick = { openTerminal(current.path) },
                    modifier = Modifier.size(40.dp),
                ) {
                    Icon(Icons.TwoTone.Terminal, "打开 Root 终端", tint = white)
                }
                Box {
                    IconButton(
                        onClick = { expandedMenu = true },
                        modifier = Modifier.size(40.dp),
                    ) {
                        Icon(Icons.TwoTone.MoreVert, "文件管理操作", tint = white)
                    }
                    DropdownMenu(
                        expanded = expandedMenu,
                        onDismissRequest = { expandedMenu = false },
                    ) {
                        DropdownMenuItem(
                            text = { Text("后退") },
                            enabled = current.back.isNotEmpty(),
                            onClick = { expandedMenu = false; current.backwards() },
                        )
                        DropdownMenuItem(
                            text = { Text("前进") },
                            enabled = current.forward.isNotEmpty(),
                            onClick = { expandedMenu = false; current.forwards() },
                        )
                        DropdownMenuItem(
                            text = { Text("刷新当前窗口") },
                            onClick = { expandedMenu = false; current.refresh() },
                        )
                        DropdownMenuItem(
                            text = { Text("同步到对侧窗口") },
                            onClick = {
                                expandedMenu = false
                                state.windows[1 - state.active].navigate(current.path)
                            },
                        )
                        DropdownMenuItem(
                            text = { Text("新建文件 / 文件夹") },
                            onClick = { expandedMenu = false; newName = ""; newDialog = true },
                        )
                        DropdownMenuItem(
                            text = { Text(if (filterVisible) "关闭筛选" else "筛选当前窗口") },
                            onClick = {
                                expandedMenu = false
                                filterVisible = !filterVisible
                                if (!filterVisible) current.filter = ""
                            },
                        )
                        DropdownMenuItem(
                            text = { Text("输入目录路径") },
                            onClick = {
                                expandedMenu = false
                                address = current.path
                                addressDialog = true
                            },
                        )
                    }
                }
            }
        }
        if (filterVisible) {
            Surface(modifier = Modifier.fillMaxWidth(),
                color = MaterialTheme.colorScheme.surface) {
                OutlinedTextField(
                    value = current.filter,
                    onValueChange = { current.filter = it },
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 3.dp),
                    singleLine = true,
                    label = { Text("筛选当前窗口") },
                )
            }
        }
'''
s = s[:start] + header + s[end:]
pane.write_text(s, encoding="utf-8")

# Use a filled folder glyph like the reference, rather than the outlined one.
replace_one(pane, 'import androidx.compose.material.icons.Icons\n',
    'import androidx.compose.material.icons.Icons\nimport androidx.compose.material.icons.filled.Folder\n')
replace_one(pane,
    'Icon(Icons.TwoTone.Folder, null, modifier = Modifier.size(20.dp), tint = white)',
    'Icon(Icons.Filled.Folder, null, modifier = Modifier.size(20.dp), tint = white)')

s = tools.read_text(encoding="utf-8")
start = s.index('''            Text(
                text = "工具",
                style = MaterialTheme.typography.titleMedium,''',
    s.index('    Scaffold(containerColor = Color.Transparent)'))
end = s.index('''            if (tab == 0) {
                DnDualFiles(''', start)
removed = s[start:end]
assert 'TabRow(selectedTabIndex = tab)' in removed
assert 'Spacer(Modifier.height(10.dp))' in removed
s = s[:start] + s[end:]
tools.write_text(s, encoding="utf-8")

# Terminal has a compact "Files" back action in place of the deleted tab bar.
replace_one(
    tools,
    '''                    Icon(Icons.TwoTone.Terminal, contentDescription = null)
                    Spacer(Modifier.width(8.dp))
                    Column(modifier = Modifier.weight(1f)) {
                        Text("Root 终端", style = MaterialTheme.typography.titleMedium)
''',
    '''                    TextButton(onClick = { tab = 0 }) { Text("‹ 文件") }
                    Spacer(Modifier.width(4.dp))
                    Column(modifier = Modifier.weight(1f)) {
                        Text("Root 终端", style = MaterialTheme.typography.titleMedium)
''',
)

p = pane.read_text(encoding="utf-8")
t = tools.read_text(encoding="utf-8")
assert 'height(56.dp)' in p
assert 'DropdownMenu(' in p and 'DropdownMenuItem(' in p
assert 'current.navigate(parentDir(current.path))' in p
assert 'state.windows[1 - state.active].navigate(current.path)' in p
assert 'Icons.Filled.Folder' in p
assert 'DnDualFiles(' in t
assert 'TextButton(onClick = { tab = 0 }) { Text("‹ 文件") }' in t
assert 'TabRow(selectedTabIndex = tab)' not in t
assert 'text = "工具"' not in t
assert 'RootInteractiveSession(' in t
assert 'fun runScriptInTerminal(path: String)' in t
assert 'LazyColumn(state = pane.scroll' in p
assert 'val destination = joined(opposite.path, o.from.entry.name)' in p
print("DN42: compact single MT-inspired toolbar; manager bottom bar and dual-pane operations preserved.")
