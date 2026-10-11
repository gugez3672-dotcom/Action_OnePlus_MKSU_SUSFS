#!/usr/bin/env python3
"""D70a: first swipe multi-select must not reflow the LazyColumn / jump scroll."""
from pathlib import Path
p=Path("source/manager/app/src/main/java/com/resukisu/resukisu/ui/screen/main/DnDualPane.kt")
s=p.read_text(encoding="utf-8")
# Delete inserted 40dp selection row above file lists. The selection controls
# instead live in the existing compact batch long-press sheet. This guarantees
# that first selection does not change file-list viewport height or anchor.
start=s.index('''        if (current.selectedNames.isNotEmpty()) {
            Surface(color = MaterialTheme.colorScheme.surfaceVariant) {
''')
end=s.index('''        if (message.isNotEmpty()) {''', start)
removed=s[start:end]
assert 'Text("全选"' in removed and 'Text("反选"' in removed and 'Text("操作"' in removed
s=s[:start]+s[end:]
# Selection count in already-existing top metadata (no extra height).
old='''                    Text(
                        text = "文件夹 " + current.files.count { it.folder } +
                            "  文件 " + current.files.count { !it.folder } +
                            if (state.active == 0) "  · 左" else "  · 右",
'''
new='''                    Text(
                        text = "文件夹 " + current.files.count { it.folder } +
                            "  文件 " + current.files.count { !it.folder } +
                            (if (state.active == 0) "  · 左" else "  · 右") +
                            (if (current.selectedNames.isNotEmpty())
                                "  · 已选 " + current.selectedNames.size else ""),
'''
if s.count(old)!=1:raise SystemExit("D70a header drift")
s=s.replace(old,new,1)
# Batch actions: add select-all and invert options in a third row (modal only).
old='''                    HorizontalDivider()
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                        TextButton(onClick = { batchMenu = false }) { Text("关闭") }
                    }
'''
new='''                    HorizontalDivider()
                    Row(Modifier.fillMaxWidth()) {
                        actionButton("全选", Icons.TwoTone.SelectAll,
                            Modifier.weight(1f), onClick = {
                                current.selectedNames = current.visible().map { it.name }.toSet()
                                batchMenu = false
                            })
                        actionButton("反选", Icons.TwoTone.FlipToBack,
                            Modifier.weight(1f), onClick = {
                                current.selectedNames = current.visible().map { it.name }
                                    .filterNot { it in current.selectedNames }.toSet()
                                batchMenu = false
                            })
                    }
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                        TextButton(onClick = { batchMenu = false }) { Text("关闭") }
                    }
'''
if s.count(old)!=1:raise SystemExit("D70a batch menu drift")
s=s.replace(old,new,1)
# The icons may vary by library versions: use known existing extended icons.
s=s.replace("Icons.TwoTone.FlipToBack", "Icons.TwoTone.ContentCopy")
# No intermediate captured anchor when selection toggles; marker is saved
# only by actual scrolling / path change. Prior LaunchedEffect uses snapshots.
# Explicitly prevent the app from treating active-pane color change as navigation.
assert 'Row(Modifier.fillMaxWidth().height(40.dp).padding(horizontal = 6.dp)' not in s
assert '· 已选 ' in s
assert 'onLongPress = { onMenu(item) }' in s
assert 'onSelect(item, pane.selectedNames.isNotEmpty())' in s
assert 'snapshotFlow { pane.scroll.firstVisibleItemIndex' in s
p.write_text(s,encoding="utf-8")
print("D70a: remove first-selection viewport reflow; selection count in fixed header; select-all/invert in batch menu")
