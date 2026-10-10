#!/usr/bin/env python3
"""DN52: remove duplicate pane paths, restore batch long-press, compact menu."""
from pathlib import Path
p=Path("source/manager/app/src/main/java/com/resukisu/resukisu/ui/screen/main/DnDualPane.kt")
s=p.read_text()
def rep(a,b):
    global s
    n=s.count(a)
    if n!=1: raise SystemExit("DN52 anchor drift "+a[:90]+" "+str(n))
    s=s.replace(a,b,1)

start=s.index('        Row(Modifier.fillMaxWidth().height(25.dp)) {')
end=s.index('        if (current.selectedNames.isNotEmpty()) {',start)
if 'window.path' not in s[start:end]: raise SystemExit("Unexpected path row")
s=s[:start]+s[end:]

rep('                    onMenu = { e -> state.activate(index); choice = DualTarget(index, pane.path, e) },',
'''                    onMenu = { e ->
                        state.activate(index)
                        if (pane.selectedNames.isNotEmpty()) batchMenu = true
                        else choice = DualTarget(index, pane.path, e)
                    },''')
rep('''                            onLongPress = {
                                if (pane.selectedNames.isNotEmpty()) onSelect(item, true)
                                else onMenu(item)
                            },''',
'''                            onLongPress = { onMenu(item) },''')

start=s.index('    if (batchMenu) {\n        AlertDialog(')
end=s.index('    scriptChoice?.let { script ->',start)
if 'batchAction("copy")' not in s[start:end]:raise SystemExit("Batch menu missing")
menu = """    if (batchMenu && current.selectedNames.isNotEmpty()) {
        Dialog(onDismissRequest = { batchMenu = false }) {
            Surface(
                modifier = Modifier.fillMaxWidth(),
                color = MaterialTheme.colorScheme.surface,
                shape = RoundedCornerShape(16.dp),
                tonalElevation = 3.dp,
            ) {
                Column(Modifier.fillMaxWidth().padding(14.dp)) {
                    Text("已选 ${current.selectedNames.size} 项",
                        fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
                    Spacer(Modifier.height(5.dp))
                    Text(
                        "目标：${state.windows[1 - state.active].path}",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 2, overflow = TextOverflow.Ellipsis,
                    )
                    Spacer(Modifier.height(12.dp))
                    @Composable
                    fun actionButton(
                        name: String,
                        icon: androidx.compose.ui.graphics.vector.ImageVector,
                        modifier: Modifier,
                        danger: Boolean = false,
                        onClick: () -> Unit,
                    ) {
                        Row(
                            modifier.height(54.dp).clickable(onClick = onClick)
                                .padding(horizontal = 7.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Icon(icon, null, Modifier.size(22.dp),
                                tint = if (danger) MaterialTheme.colorScheme.error
                                    else MaterialTheme.colorScheme.onSurfaceVariant)
                            Spacer(Modifier.width(7.dp))
                            Text(name, fontSize = 13.sp, maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                                color = if (danger) MaterialTheme.colorScheme.error
                                    else MaterialTheme.colorScheme.onSurface)
                        }
                    }
                    Row(Modifier.fillMaxWidth()) {
                        actionButton("复制 →", Icons.TwoTone.ContentCopy,
                            Modifier.weight(1f), onClick = { batchAction("copy") })
                        actionButton("移动 →", Icons.TwoTone.DriveFileMove,
                            Modifier.weight(1f), onClick = { batchAction("move") })
                    }
                    Row(Modifier.fillMaxWidth()) {
                        actionButton("删除所选", Icons.TwoTone.Delete,
                            Modifier.weight(1f), danger = true,
                            onClick = { batchAction("delete") })
                        actionButton("取消选择", Icons.TwoTone.Close,
                            Modifier.weight(1f), onClick = {
                                current.selectedNames = emptySet()
                                current.selectAnchor = -1
                                batchMenu = false
                            })
                    }
                    HorizontalDivider()
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                        TextButton(onClick = { batchMenu = false }) { Text("关闭") }
                    }
                }
            }
        }
    }
"""
s=s[:start]+menu+s[end:]
p.write_text(s)
assert 'window.path' not in s
assert 'onLongPress = { onMenu(item) }' in s
assert 'val destinationDir = opposite.path' in s
assert 'batchAction("copy")' in s and 'batchAction("move")' in s
assert 'source == NestedScrollSource.UserInput' in s
print("DN52: single active path, long-press batch menu, compact two-column actions")
