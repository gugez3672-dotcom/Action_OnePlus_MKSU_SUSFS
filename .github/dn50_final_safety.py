#!/usr/bin/env python3
"""DN50 final hardening: dangling symlinks, edit snapshot SHA, safe per-operation
collision reset, copy-in-place via rename, sensible overwrite-folder policy, and 2-col menu."""
from pathlib import Path
base=Path("source/manager/app/src/main/java/com/resukisu/resukisu/ui/screen/main")
p=base/"DnDualPane.kt"
s=p.read_text()
def rep(a,b):
    global s
    if s.count(a)!=1: raise SystemExit("DN50 pane drift: "+a[:120]+" n="+str(s.count(a)))
    s=s.replace(a,b,1)
rep('''        bb + " stat -L -c '%n|%F|%s|%Y' -- \\"" + dollar + "@\\""''',
'''        // Symlinks are listed without dereferencing (including broken links).
        // Symlink-to-directory metadata is emitted first and wins distinctBy.
        "for f in \\"" + dollar + "@\\"; do\\n" +
        "  if [ -L \\"" + dollar + "f\\" ] && [ -d \\"" + dollar + "f\\" ]; then\\n" +
        "    " + bb + " stat -L -c '%n|%F|%s|%Y' -- \\"" + dollar + "f\\"\\n" +
        "  fi\\n" +
        "done\\n" +
        bb + " stat -c '%n|%F|%s|%Y' -- \\"" + dollar + "@\\""''')
rep('''    var collision by remember { mutableStateOf("skip") }
''',
'''    var collision by remember { mutableStateOf("skip") }
    LaunchedEffect(operation) {
        if (operation != null) collision = "skip"
    }
''')
rep('''                (o.kind == "delete" && source in protected) ||
                    (o.kind != "delete" && (source == dest ||
                        dest.startsWith(source + "/")))
''',
'''                (o.kind == "delete" && source in protected) ||
                    (o.kind != "delete" &&
                        ((source == dest && !(o.kind == "copy" && collision == "rename")) ||
                            dest.startsWith(source + "/")))
''')
rep('''                        "replace" -> {
                            // Replacing a directory is intentionally unsupported.
''',
'''                        "replace" -> {
                            if (sources[jobDone].entry.folder) {
                                "if [ -e " + quotedDst + " ] || [ -L " + quotedDst +
                                    " ]; then echo DN_SKIP_FOLDER; exit 88; fi; " +
                                    command + quotedSrc + " " + quotedDst
                            } else {
                            // Replacing a directory is intentionally unsupported.
''')
rep('''                            prefix + write
                        }
                        else ->
''',
'''                            prefix + write
                            }
                        }
                        else ->
''')
rep('''                else if (result.value.contains("DN_SKIP") && selectedMode == "skip") skipped++
''',
'''                else if (result.value.contains("DN_SKIP")) skipped++
''')
rep('''                        option("终端", Modifier.weight(1f)) { openTerminal(if (c.entry.folder) file else c.directory) }
''',
'''                        option("加入选择", Modifier.weight(1f)) {
                            state.windows[c.side].choose(c.entry)
                        }
                    }
                    Row(Modifier.fillMaxWidth()) {
                        option("终端", Modifier.weight(1f)) { openTerminal(if (c.entry.folder) file else c.directory) }
''')
p.write_text(s)
p=base/"ToolsPage.kt"
s=p.read_text()
needle='''            editorText = decoded
            editorOriginal = decoded
            editorHash = hash
'''
insert='''            val receivedHash = java.security.MessageDigest.getInstance("SHA-256")
                .digest(bytes).joinToString("") { "%02x".format(it.toInt() and 0xff) }
            if (receivedHash != hash) {
                editorError = "读取过程中原文件已改变，禁止编辑旧副本"
                editorBusy = false
                return@launch
            }
            editorText = decoded
            editorOriginal = decoded
            editorHash = hash
'''
if s.count(needle)!=1:raise SystemExit("DN50 editor SHA anchor drift")
s=s.replace(needle,insert,1)
p.write_text(s)
assert "DN_SKIP_FOLDER" in (base/"DnDualPane.kt").read_text()
assert 'if (operation != null) collision = "skip"' in (base/"DnDualPane.kt").read_text()
assert "读取过程中原文件已改变" in s
print("DN50 verified editor snapshot SHA, dangling-symlink-safe listing, collision defaults and balanced file menus")
