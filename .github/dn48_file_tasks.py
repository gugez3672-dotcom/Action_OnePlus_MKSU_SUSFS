#!/usr/bin/env python3
"""DN48: cancellable-between-items task progress and explicit collision policy;
protect existing targets; batch operations still use the OTHER pane path."""
from pathlib import Path
p=Path("source/manager/app/src/main/java/com/resukisu/resukisu/ui/screen/main/DnDualPane.kt")
s=p.read_text()
def rep(a,b):
    global s
    if s.count(a)!=1: raise SystemExit("DN48 drift: "+a[:100]+" x "+str(s.count(a)))
    s=s.replace(a,b,1)
rep('''    var message by remember { mutableStateOf("") }
''',
'''    var message by remember { mutableStateOf("") }
    var collision by remember { mutableStateOf("skip") }
    var working by remember { mutableStateOf(false) }
    var wantCancel by remember { mutableStateOf(false) }
    var jobName by remember { mutableStateOf("") }
    var jobDone by remember { mutableIntStateOf(0) }
    var jobTotal by remember { mutableIntStateOf(0) }
    var jobErrors by remember { mutableStateOf<List<String>>(emptyList()) }
    var detailedErrors by remember { mutableStateOf(false) }
''')
a=s.index("    fun doOperation(o: DualOperation) {")
b=s.index("    BackHandler(current.back.isNotEmpty())",a)
replacement=r'''    fun doOperation(o: DualOperation) {
        if (working) return
        val sources = listOf(o.from) + o.others
        val opposite = state.windows[1 - o.from.side]
        val destinationDir = opposite.path // freeze target when confirmation is pressed
        val protected = setOf("/", "/data", "/system", "/vendor", "/product",
            "/metadata", "/dev", "/proc", "/sys", "/storage")
        val pairs = sources.map { target ->
            joined(target.directory, target.entry.name) to joined(destinationDir, target.entry.name)
        }
        if (pairs.any { (source, dest) ->
                (o.kind == "delete" && source in protected) ||
                    (o.kind != "delete" && (source == dest ||
                        dest.startsWith(source + "/")))
            }) {
            operation = null
            message = "拒绝关键目录操作或复制到自身子目录"
            return
        }
        val selectedMode = collision
        operation = null
        working = true
        wantCancel = false
        jobDone = 0
        jobTotal = pairs.size
        jobName = ""
        jobErrors = emptyList()
        scope.launch {
            val errors = mutableListOf<String>()
            var skipped = 0
            var succeeded = 0
            for ((source, target) in pairs) {
                if (wantCancel) break
                jobName = source.substringAfterLast('/')
                val quotedSrc = qs(source)
                val quotedDst = qs(target)
                val shell: String
                if (o.kind == "delete") {
                    shell = "rm -rf -- " + quotedSrc
                } else {
                    // Never silently replace a file or directory. Skip is default.
                    val command = if (o.kind == "copy") "cp -a -- " else "mv -- "
                    shell = when (selectedMode) {
                        "rename" -> {
                            val d = '$'
                            "DEST=" + quotedDst + "\n" +
                                "ORIG=" + quotedDst + "\n" +
                                "n=1\n" +
                                "while [ -e \"" + d + "DEST\" ] || [ -L \"" + d + "DEST\" ]; do\n" +
                                "  DEST=\"" + d + "ORIG (" + d + "n)\"\n" +
                                "  n=$((n + 1))\n" +
                                "  [ \"" + d + "n\" -le 1000 ] || exit 82\n" +
                                "done\n" +
                                command + quotedSrc + " \"" + d + "DEST\""
                        }
                        "replace" -> {
                            // Replacing a directory is intentionally unsupported.
                            // For files: create verified copy in destination directory,
                            // backup old target, then swap; remove source only on move.
                            val d = '$'
                            val prefix = "S=" + quotedSrc + "\nD=" + quotedDst + "\n" +
                                "BB=/data/adb/ksu/bin/busybox\n" +
                                "if [ -d \"" + d + "S\" ] || [ -d \"" + d + "D\" ] || [ -L \"" +
                                d + "D\" ]; then echo '不支持覆盖文件夹或链接'; exit 83; fi\n"
                            val write = "TMP=\"" + d + "D.dn-new-" + d + d + "\"\n" +
                                "BAK=\"" + d + "D.dn-old-" + d + d + "\"\n" +
                                d + "BB cp -a -- \"" + d + "S\" \"" + d + "TMP\" || exit 84\n" +
                                "A=$(" + d + "BB sha256sum -- \"" + d + "S\" | " + d + "BB cut -d ' ' -f1)\n" +
                                "B=$(" + d + "BB sha256sum -- \"" + d + "TMP\" | " + d + "BB cut -d ' ' -f1)\n" +
                                "if [ \"" + d + "A\" != \"" + d + "B\" ]; then " +
                                d + "BB rm -f -- \"" + d + "TMP\"; echo '目标副本校验失败'; exit 85; fi\n" +
                                "if [ -e \"" + d + "D\" ]; then\n" +
                                "  " + d + "BB cp -a -- \"" + d + "D\" \"" + d + "BAK\" || exit 86\n" +
                                "fi\n" +
                                d + "BB mv -f -- \"" + d + "TMP\" \"" + d + "D\" || exit 87\n" +
                                if (o.kind == "move")
                                    d + "BB rm -f -- \"" + d + "S\"" else ":"
                            prefix + write
                        }
                        else ->
                            "if [ -e " + quotedDst + " ] || [ -L " + quotedDst +
                                " ]; then echo DN_SKIP; exit 88; fi; " +
                                command + quotedSrc + " " + quotedDst
                    }
                }
                val result = cmd(cli, shell)
                jobDone++
                if (result.ok) succeeded++
                else if (result.value.contains("DN_SKIP") && selectedMode == "skip") skipped++
                else errors.add(jobName + ": " + result.value.take(200).ifBlank { "命令失败" })
                if (!result.ok && selectedMode != "skip") break
            }
            state.windows[o.from.side].selectedNames = emptySet()
            state.windows[o.from.side].selectAnchor = -1
            state.windows[o.from.side].refresh()
            if (o.kind != "delete") opposite.refresh()
            jobErrors = errors
            val interrupted = wantCancel
            working = false
            message = "完成 $succeeded 项 · 跳过 $skipped 项" +
                if (errors.isNotEmpty()) " · 失败 " + errors.size + " 项" else "" +
                if (interrupted) " · 已取消后续任务" else ""
            if (errors.isNotEmpty()) detailedErrors = true
        }
    }
'''
s=s[:a]+replacement+s[b:]
# Fix kotlin message Elvis/precedence with explicit string concatenation.
rep('''            message = "完成 $succeeded 项 · 跳过 $skipped 项" +
                if (errors.isNotEmpty()) " · 失败 " + errors.size + " 项" else "" +
                if (interrupted) " · 已取消后续任务" else ""
''',
'''            message = "完成 $succeeded 项 · 跳过 $skipped 项" +
                (if (errors.isNotEmpty()) " · 失败 " + errors.size + " 项" else "") +
                (if (interrupted) " · 已取消后续任务" else "")
''')
a=s.index("    operation?.let { o ->")
b=s.index("    rename?.let { c ->",a)
s=s[:a]+r'''    operation?.let { o ->
        val source = joined(o.from.directory, o.from.entry.name)
        val dest = joined(state.windows[1 - o.from.side].path, o.from.entry.name)
        val count = o.others.size + 1
        AlertDialog(
            onDismissRequest = { operation = null },
            title = { Text(when(o.kind) {
                "copy" -> "复制到对侧窗口 ($count 项)"
                "move" -> "移动到对侧窗口 ($count 项)"
                else -> "删除文件 ($count 项)"
            }) },
            text = {
                Column {
                    Text(if (o.kind == "delete") "确认删除：$source" else
                        "源：$source\n目标：$dest\n其余项目也使用右侧/左侧目标目录。")
                    if (o.kind != "delete") {
                        Spacer(Modifier.height(8.dp))
                        Text("目标重名时：", style = MaterialTheme.typography.labelMedium)
                        listOf(
                            "skip" to "跳过冲突项（默认）",
                            "rename" to "目标自动重命名",
                            "replace" to "覆盖普通文件并备份（高风险）",
                        ).forEach { (mode, label) ->
                            Row(Modifier.fillMaxWidth().clickable { collision = mode },
                                verticalAlignment = Alignment.CenterVertically) {
                                RadioButton(selected = collision == mode, onClick = { collision = mode })
                                Text(label, style = MaterialTheme.typography.bodySmall)
                            }
                        }
                    } else Text("删除后无法恢复，请确认选择的文件。")
                }
            },
            confirmButton = {
                TextButton(onClick = { doOperation(o) }) { Text("确定") }
            },
            dismissButton = { TextButton(onClick = { operation = null }) { Text("取消") } },
        )
    }
    if (working) {
        AlertDialog(
            onDismissRequest = { /* Task status remains until operations stop. */ },
            title = { Text("文件操作中 $jobDone / $jobTotal") },
            text = {
                Column {
                    Text(jobName, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    Spacer(Modifier.height(6.dp))
                    LinearProgressIndicator(
                        progress = { if (jobTotal > 0) jobDone.toFloat() / jobTotal else 0f },
                        modifier = Modifier.fillMaxWidth(),
                    )
                    Text("取消会在当前文件处理结束后停止后续项目",
                        style = MaterialTheme.typography.labelSmall)
                }
            },
            confirmButton = { TextButton(onClick = { wantCancel = true },
                enabled = !wantCancel) { Text(if (wantCancel) "等待停止" else "停止后续") } },
        )
    }
    if (detailedErrors) {
        AlertDialog(
            onDismissRequest = { detailedErrors = false },
            title = { Text("部分项目失败") },
            text = { Text(jobErrors.joinToString("\n"), maxLines = 12) },
            confirmButton = { TextButton(onClick = { detailedErrors = false }) { Text("知道了") } },
        )
    }
''' + s[b:]
# Disable further file menu actions while running; avoid conflicting changes.
rep('''    choice?.let { c ->
''','''    choice?.takeIf { !working }?.let { c ->
''')
# Avoid allowing navigation & selection while task still running on frozen target pane
# (the target path is already captured at confirmation).
p.write_text(s)
assert 'jobDone' in s and 'LinearProgressIndicator(' in s
assert '目标自动重命名' in s and 'DN_SKIP' in s and 'sha256sum' in s
assert 'val destinationDir = opposite.path' in s
assert 'DnDualFiles(' in s
print("DN48 collision choices, batch progress, cancel-between-items and failure details")
