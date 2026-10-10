#!/usr/bin/env python3
"""DN41: MT-style compact two-column file action sheet, preserving every action."""
from pathlib import Path

P = Path("source/manager/app/src/main/java/com/resukisu/resukisu/ui/screen/main/ToolsPage.kt")
t = P.read_text(encoding="utf-8")
anchor = "private data class CommandResult(val out: String, val success: Boolean)\n"
if t.count(anchor) != 1:
    raise SystemExit("DN41 cannot locate action component anchor")
t = t.replace(anchor, '''@Composable
private fun RootFileAction(
    text: String,
    icon: ImageVector,
    modifier: Modifier = Modifier,
    onClick: () -> Unit
) {
    TextButton(onClick = onClick, modifier = modifier.heightIn(min = 54.dp)) {
        Icon(icon, contentDescription = null, modifier = Modifier.size(22.dp))
        Spacer(Modifier.width(6.dp))
        Text(
            text,
            style = MaterialTheme.typography.bodyMedium,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis
        )
    }
}

''' + anchor, 1)

a = t.index("    if (showActions) {\n")
b = t.index("    if (showRename) {\n", a)
menu = '''    if (showActions) {
        val entry = selectedEntry
        if (entry != null) {
            val fullPath = joinPath(currentPath, entry.name)
            AlertDialog(
                onDismissRequest = { showActions = false },
                title = {
                    Text(entry.name, maxLines = 1, overflow = TextOverflow.Ellipsis)
                },
                text = {
                    Column(Modifier.fillMaxWidth()) {
                        Row(Modifier.fillMaxWidth()) {
                            RootFileAction("复制", Icons.TwoTone.ContentCopy, Modifier.weight(1f)) {
                                pendingSource = fullPath
                                pendingMove = false
                                showActions = false
                            }
                            RootFileAction("移动", Icons.TwoTone.DriveFileMove, Modifier.weight(1f)) {
                                pendingSource = fullPath
                                pendingMove = true
                                showActions = false
                            }
                        }
                        Row(Modifier.fillMaxWidth()) {
                            RootFileAction("删除", Icons.TwoTone.Delete, Modifier.weight(1f)) {
                                showActions = false
                                showDeleteConfirm = true
                            }
                            RootFileAction("重命名", Icons.TwoTone.Edit, Modifier.weight(1f)) {
                                renameValue = entry.name
                                showActions = false
                                showRename = true
                            }
                        }
                        Row(Modifier.fillMaxWidth()) {
                            RootFileAction("属性", Icons.TwoTone.Info, Modifier.weight(1f)) {
                                showActions = false
                                propertiesText = "读取中…"
                                showProperties = true
                                scope.launch {
                                    propertiesText = execRoot(
                                        "/data/adb/ksu/bin/busybox stat " + shellQuote(fullPath) +
                                            "; ls -ldZ " + shellQuote(fullPath)
                                    ).out
                                }
                            }
                            RootFileAction("权限", Icons.TwoTone.Lock, Modifier.weight(1f)) {
                                chmodValue = if (entry.directory) "0755" else "0644"
                                showActions = false
                                showChmod = true
                            }
                        }
                        Row(Modifier.fillMaxWidth()) {
                            if (entry.directory) {
                                RootFileAction("打开", Icons.TwoTone.Folder, Modifier.weight(1f)) {
                                    currentPath = fullPath
                                    showActions = false
                                }
                            } else if (isTextLike(entry.name)) {
                                RootFileAction("编辑", Icons.TwoTone.Edit, Modifier.weight(1f)) {
                                    showActions = false
                                    loadEditor(fullPath)
                                }
                            } else {
                                Spacer(Modifier.weight(1f))
                            }
                            RootFileAction("终端", Icons.TwoTone.Terminal, Modifier.weight(1f)) {
                                showActions = false
                                openTerminalAt(if (entry.directory) fullPath else parentPath(fullPath))
                            }
                        }
                        if (entry.name.endsWith(".sh", ignoreCase = true) && !entry.directory) {
                            Row(Modifier.fillMaxWidth()) {
                                RootFileAction(
                                    "Root 执行", Icons.TwoTone.Terminal, Modifier.weight(1f)
                                ) {
                                    showActions = false
                                    runScriptInTerminal(fullPath)
                                }
                                RootFileAction(
                                    "后台运行", Icons.TwoTone.Terminal, Modifier.weight(1f)
                                ) {
                                    showActions = false
                                    runScriptDetached(fullPath)
                                }
                            }
                        }
                    }
                },
                confirmButton = {
                    TextButton(onClick = { showActions = false }) { Text("关闭") }
                },
            )
        }
    }

'''
t = t[:a] + menu + t[b:]
assert "runScriptDetached(fullPath)" in t
assert "runScriptInTerminal(fullPath)" in t
assert "showDeleteConfirm = true" in t
assert 'RootFileAction("复制"' in t
assert 'RootFileAction("移动"' in t
assert 'RootFileAction("权限"' in t
assert "if (showEditor)" in t
P.write_text(t, encoding="utf-8")
print("DN41 file operations: MT-like two-column menu with copy, move, delete, rename, attributes, permissions and root scripts.")
