#!/usr/bin/env python3
"""DN46: safe editor: complete reads, UTF8 validation, SHA conflict protection,
verified same-directory temporary save, backup and fullscreen UI."""
from pathlib import Path
p=Path("source/manager/app/src/main/java/com/resukisu/resukisu/ui/screen/main/ToolsPage.kt")
s=p.read_text()
def rep(a,b):
    global s
    if s.count(a)!=1: raise SystemExit("DN46 anchor mismatch: "+a[:90]+" count="+str(s.count(a)))
    s=s.replace(a,b,1)
rep('import androidx.compose.material3.Scaffold\n',
'''import androidx.compose.material3.Scaffold
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
''')
rep('    var editorBusy by remember { mutableStateOf(false) }\n',
'''    var editorBusy by remember { mutableStateOf(false) }
    var editorError by remember { mutableStateOf("") }
    var editorHash by remember { mutableStateOf("") }
    var editorOriginal by remember { mutableStateOf("") }
    val editorLimit = 192 * 1024
''')
a=s.index('    fun loadEditor(path: String) {')
b=s.index('    LaunchedEffect(tab, currentPath) {',a)
s=s[:a]+r'''    fun loadEditor(path: String) {
        editorPath = path
        editorBusy = true
        editorError = ""
        editorHash = ""
        editorText = ""
        editorOriginal = ""
        showEditor = true
        scope.launch {
            val probe = execRoot(
                "if [ -L " + shellQuote(path) + " ]; then echo LINK; " +
                "elif [ ! -f " + shellQuote(path) + " ]; then echo NOT_FILE; " +
                "else /data/adb/ksu/bin/busybox stat -c %s -- " + shellQuote(path) + "; fi"
            )
            val n = probe.out.trim().toLongOrNull()
            if (!probe.success || n == null || n < 0 || n > editorLimit) {
                editorError = when {
                    probe.out.trim() == "LINK" -> "符号链接不允许直接编辑，请打开实际目标"
                    probe.out.trim() == "NOT_FILE" -> "仅支持普通文件"
                    n != null && n > editorLimit -> "文件超过 192 KiB，拒绝截断读取"
                    else -> "读取大小失败: " + probe.out.take(120)
                }
                editorBusy = false
                return@launch
            }
            val raw = execRoot("/data/adb/ksu/bin/busybox base64 -- " + shellQuote(path))
            val bytes = runCatching { Base64.decode(raw.out, Base64.DEFAULT) }.getOrNull()
            if (!raw.success || bytes == null || bytes.size.toLong() != n) {
                editorError = "读取不完整，已禁止保存"
                editorBusy = false
                return@launch
            }
            val decoded = String(bytes, Charsets.UTF_8)
            if (bytes.contains(0.toByte()) ||
                !decoded.toByteArray(Charsets.UTF_8).contentEquals(bytes)) {
                editorError = "文件不是纯 UTF-8 文本，禁止覆盖保存"
                editorBusy = false
                return@launch
            }
            val sha = execRoot("/data/adb/ksu/bin/busybox sha256sum -- " + shellQuote(path))
            val hash = sha.out.trim().substringBefore(" ").lowercase(Locale.ROOT)
            if (!sha.success || !hash.matches(Regex("[a-f0-9]{64}"))) {
                editorError = "读取 SHA-256 失败，已禁止保存"
                editorBusy = false
                return@launch
            }
            editorText = decoded
            editorOriginal = decoded
            editorHash = hash
            editorBusy = false
        }
    }

    fun saveEditor() {
        if (editorBusy || editorHash.isBlank() || editorError.isNotBlank()) return
        if (editorText == editorOriginal) {
            showEditor = false
            return
        }
        val bytes = editorText.toByteArray(Charsets.UTF_8)
        if (bytes.size > editorLimit) {
            editorError = "保存内容超过 192 KiB，已阻止写入"
            return
        }
        val path = editorPath
        val expected = editorHash
        val encoded = Base64.encodeToString(bytes, Base64.NO_WRAP)
        val newHash = java.security.MessageDigest.getInstance("SHA-256")
            .digest(bytes).joinToString("") { "%02x".format(it.toInt() and 0xff) }
        editorBusy = true
        scope.launch {
            // Preserve mode, ownership and xattrs by copying the original file to
            // a same-dir temporary first. Verify actual bytes before replacement.
            val script = """
BB=/data/adb/ksu/bin/busybox
P=${shellQuote(path)}
EXPECTED=${shellQuote(expected)}
NEW_HASH=${shellQuote(newHash)}
if [ ! -f "${'$'}P" ] || [ -L "${'$'}P" ]; then echo '源文件已改变类型'; exit 70; fi
CURRENT=$(${'$'}BB sha256sum -- "${'$'}P" | ${'$'}BB cut -d ' ' -f1)
if [ "${'$'}CURRENT" != "${'$'}EXPECTED" ]; then echo '文件被外部修改，拒绝覆盖'; exit 71; fi
TMP="${'$'}P.dn-temp-${'$'}${'$'}"
BACKUP="${'$'}P.dn-bak-$(date +%s)-${'$'}${'$'}"
if ! ${'$'}BB cp -a -- "${'$'}P" "${'$'}TMP"; then echo '临时副本失败'; exit 72; fi
if ! printf '%s' ${shellQuote(encoded)} | ${'$'}BB base64 -d > "${'$'}TMP"; then
  ${'$'}BB rm -f -- "${'$'}TMP"; echo '临时文件写入失败'; exit 73
fi
GOT=$(${'$'}BB sha256sum -- "${'$'}TMP" | ${'$'}BB cut -d ' ' -f1)
if [ "${'$'}GOT" != "${'$'}NEW_HASH" ]; then
  ${'$'}BB rm -f -- "${'$'}TMP"; echo '新文件 SHA-256 不匹配'; exit 74
fi
CURRENT=$(${'$'}BB sha256sum -- "${'$'}P" | ${'$'}BB cut -d ' ' -f1)
if [ "${'$'}CURRENT" != "${'$'}EXPECTED" ]; then
  ${'$'}BB rm -f -- "${'$'}TMP"; echo '保存期间原文件已改变'; exit 75
fi
if ! ${'$'}BB cp -a -- "${'$'}P" "${'$'}BACKUP"; then
  ${'$'}BB rm -f -- "${'$'}TMP"; echo '备份失败，原文件未改动'; exit 76
fi
if ! ${'$'}BB mv -f -- "${'$'}TMP" "${'$'}P"; then
  echo '替换失败，备份保留'; exit 77
fi
echo "保存成功，备份 ${'$'}BACKUP"
""".trimIndent()
            val result = execRoot(script)
            editorBusy = false
            if (result.success) {
                editorOriginal = editorText
                editorHash = newHash
                showEditor = false
                dualWindows.windows.forEach { pane ->
                    if (pane.path == parentPath(path)) pane.refresh()
                }
                fileError = result.out.ifBlank { "保存成功" }
            } else editorError = result.out.ifBlank { "保存失败，未确认替换" }
        }
    }

'''+s[b:]
a=s.index('    if (showEditor) {\n        AlertDialog(')
b=s.index('\n}\n',a)
s=s[:a]+r'''    if (showEditor) {
        Dialog(onDismissRequest = { if (!editorBusy && editorText == editorOriginal) showEditor = false },
            properties = DialogProperties(usePlatformDefaultWidth = false)) {
            Surface(modifier = Modifier.fillMaxSize().padding(5.dp),
                shape = MaterialTheme.shapes.medium) {
                Column(Modifier.fillMaxSize().padding(12.dp)) {
                    Text(editorPath.substringAfterLast('/'),
                        style = MaterialTheme.typography.titleMedium,
                        maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(editorPath, style = MaterialTheme.typography.labelSmall,
                        maxLines = 2, overflow = TextOverflow.Ellipsis,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                    if (editorError.isNotBlank())
                        Text(editorError, style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.error)
                    Spacer(Modifier.height(8.dp))
                    if (editorBusy) {
                        Box(Modifier.weight(1f).fillMaxWidth(),
                            contentAlignment = Alignment.Center) { CircularProgressIndicator() }
                    } else {
                        OutlinedTextField(
                            value = editorText, onValueChange = { editorText = it },
                            modifier = Modifier.weight(1f).fillMaxWidth(),
                            enabled = editorError.isBlank(),
                            textStyle = MaterialTheme.typography.bodySmall.copy(fontFamily = FontFamily.Monospace),
                        )
                    }
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                        TextButton(onClick = { showEditor = false }, enabled = !editorBusy) {
                            Text(if (editorText != editorOriginal) "放弃修改" else "关闭")
                        }
                        TextButton(onClick = { saveEditor() },
                            enabled = !editorBusy && editorError.isBlank() && editorHash.isNotBlank()) {
                            Text("保存并备份")
                        }
                    }
                }
            }
        }
    }'''+s[b:]
p.write_text(s)
assert "拒绝截断读取" in s
assert "文件被外部修改，拒绝覆盖" in s
assert "sha256sum --" in s
assert "DialogProperties(usePlatformDefaultWidth = false)" in s
assert "dualWindows.windows.forEach" in s
print("DN46 complete-read SHA-guarded safe editor with backup, fullscreen UI")
}P.dn-bak-$(${'
if ! ${'$'}BB cp -a -- "${'$'}P" "${'$'}TMP"; then echo '临时副本失败'; exit 72; fi
if ! printf '%s' ${shellQuote(encoded)} | ${'$'}BB base64 -d > "${'$'}TMP"; then
  ${'$'}BB rm -f -- "${'$'}TMP"; echo '临时文件写入失败'; exit 73
fi
GOT=$(${'$'}BB sha256sum -- "${'$'}TMP" | ${'$'}BB cut -d ' ' -f1)
if [ "${'$'}GOT" != "${'$'}NEW_HASH" ]; then
  ${'$'}BB rm -f -- "${'$'}TMP"; echo '新文件 SHA-256 不匹配'; exit 74
fi
CURRENT=$(${'$'}BB sha256sum -- "${'$'}P" | ${'$'}BB cut -d ' ' -f1)
if [ "${'$'}CURRENT" != "${'$'}EXPECTED" ]; then
  ${'$'}BB rm -f -- "${'$'}TMP"; echo '保存期间原文件已改变'; exit 75
fi
if ! ${'$'}BB cp -a -- "${'$'}P" "${'$'}BACKUP"; then
  ${'$'}BB rm -f -- "${'$'}TMP"; echo '备份失败，原文件未改动'; exit 76
fi
if ! ${'$'}BB mv -f -- "${'$'}TMP" "${'$'}P"; then
  echo '替换失败，备份保留'; exit 77
fi
echo "保存成功，备份 ${'$'}BACKUP"
""".trimIndent()
            val result = execRoot(script)
            editorBusy = false
            if (result.success) {
                editorOriginal = editorText
                editorHash = newHash
                showEditor = false
                dualWindows.windows.forEach { pane ->
                    if (pane.path == parentPath(path)) pane.refresh()
                }
                fileError = result.out.ifBlank { "保存成功" }
            } else editorError = result.out.ifBlank { "保存失败，未确认替换" }
        }
    }

'''+s[b:]
# Fix the backup date substitution to use standard $(date...) rather than arithmetic expansion.
s=s.replace('BACKUP="${'$'}P.dn-bak-$((${'$'}BB date +%s))-${'$'}${'$'}"',
    'BACKUP="${'$'}P.dn-bak-$(${'$'}BB date +%s)-${'$'}${'$'}"') if False else s
a=s.index('    if (showEditor) {\n        AlertDialog(')
b=s.index('\n}\n',a)
s=s[:a]+r'''    if (showEditor) {
        Dialog(onDismissRequest = { if (!editorBusy && editorText == editorOriginal) showEditor = false },
            properties = DialogProperties(usePlatformDefaultWidth = false)) {
            Surface(modifier = Modifier.fillMaxSize().padding(5.dp),
                shape = MaterialTheme.shapes.medium) {
                Column(Modifier.fillMaxSize().padding(12.dp)) {
                    Text(editorPath.substringAfterLast('/'),
                        style = MaterialTheme.typography.titleMedium,
                        maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(editorPath, style = MaterialTheme.typography.labelSmall,
                        maxLines = 2, overflow = TextOverflow.Ellipsis,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                    if (editorError.isNotBlank())
                        Text(editorError, style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.error)
                    Spacer(Modifier.height(8.dp))
                    if (editorBusy) {
                        Box(Modifier.weight(1f).fillMaxWidth(),
                            contentAlignment = Alignment.Center) { CircularProgressIndicator() }
                    } else {
                        OutlinedTextField(
                            value = editorText, onValueChange = { editorText = it },
                            modifier = Modifier.weight(1f).fillMaxWidth(),
                            enabled = editorError.isBlank(),
                            textStyle = MaterialTheme.typography.bodySmall.copy(fontFamily = FontFamily.Monospace),
                        )
                    }
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                        TextButton(onClick = { showEditor = false }, enabled = !editorBusy) {
                            Text(if (editorText != editorOriginal) "放弃修改" else "关闭")
                        }
                        TextButton(onClick = { saveEditor() },
                            enabled = !editorBusy && editorError.isBlank() && editorHash.isNotBlank()) {
                            Text("保存并备份")
                        }
                    }
                }
            }
        }
    }'''+s[b:]
p.write_text(s)
assert "拒绝截断读取" in s
assert "文件被外部修改，拒绝覆盖" in s
assert "sha256sum --" in s
assert "DialogProperties(usePlatformDefaultWidth = false)" in s
assert "dualWindows.windows.forEach" in s
print("DN46 complete-read SHA-guarded safe editor with backup, fullscreen UI")
}BB date +%s)-${'
if ! ${'$'}BB cp -a -- "${'$'}P" "${'$'}TMP"; then echo '临时副本失败'; exit 72; fi
if ! printf '%s' ${shellQuote(encoded)} | ${'$'}BB base64 -d > "${'$'}TMP"; then
  ${'$'}BB rm -f -- "${'$'}TMP"; echo '临时文件写入失败'; exit 73
fi
GOT=$(${'$'}BB sha256sum -- "${'$'}TMP" | ${'$'}BB cut -d ' ' -f1)
if [ "${'$'}GOT" != "${'$'}NEW_HASH" ]; then
  ${'$'}BB rm -f -- "${'$'}TMP"; echo '新文件 SHA-256 不匹配'; exit 74
fi
CURRENT=$(${'$'}BB sha256sum -- "${'$'}P" | ${'$'}BB cut -d ' ' -f1)
if [ "${'$'}CURRENT" != "${'$'}EXPECTED" ]; then
  ${'$'}BB rm -f -- "${'$'}TMP"; echo '保存期间原文件已改变'; exit 75
fi
if ! ${'$'}BB cp -a -- "${'$'}P" "${'$'}BACKUP"; then
  ${'$'}BB rm -f -- "${'$'}TMP"; echo '备份失败，原文件未改动'; exit 76
fi
if ! ${'$'}BB mv -f -- "${'$'}TMP" "${'$'}P"; then
  echo '替换失败，备份保留'; exit 77
fi
echo "保存成功，备份 ${'$'}BACKUP"
""".trimIndent()
            val result = execRoot(script)
            editorBusy = false
            if (result.success) {
                editorOriginal = editorText
                editorHash = newHash
                showEditor = false
                dualWindows.windows.forEach { pane ->
                    if (pane.path == parentPath(path)) pane.refresh()
                }
                fileError = result.out.ifBlank { "保存成功" }
            } else editorError = result.out.ifBlank { "保存失败，未确认替换" }
        }
    }

'''+s[b:]
# Fix the backup date substitution to use standard $(date...) rather than arithmetic expansion.
s=s.replace('BACKUP="${'$'}P.dn-bak-$((${'$'}BB date +%s))-${'$'}${'$'}"',
    'BACKUP="${'$'}P.dn-bak-$(${'$'}BB date +%s)-${'$'}${'$'}"') if False else s
a=s.index('    if (showEditor) {\n        AlertDialog(')
b=s.index('\n}\n',a)
s=s[:a]+r'''    if (showEditor) {
        Dialog(onDismissRequest = { if (!editorBusy && editorText == editorOriginal) showEditor = false },
            properties = DialogProperties(usePlatformDefaultWidth = false)) {
            Surface(modifier = Modifier.fillMaxSize().padding(5.dp),
                shape = MaterialTheme.shapes.medium) {
                Column(Modifier.fillMaxSize().padding(12.dp)) {
                    Text(editorPath.substringAfterLast('/'),
                        style = MaterialTheme.typography.titleMedium,
                        maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(editorPath, style = MaterialTheme.typography.labelSmall,
                        maxLines = 2, overflow = TextOverflow.Ellipsis,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                    if (editorError.isNotBlank())
                        Text(editorError, style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.error)
                    Spacer(Modifier.height(8.dp))
                    if (editorBusy) {
                        Box(Modifier.weight(1f).fillMaxWidth(),
                            contentAlignment = Alignment.Center) { CircularProgressIndicator() }
                    } else {
                        OutlinedTextField(
                            value = editorText, onValueChange = { editorText = it },
                            modifier = Modifier.weight(1f).fillMaxWidth(),
                            enabled = editorError.isBlank(),
                            textStyle = MaterialTheme.typography.bodySmall.copy(fontFamily = FontFamily.Monospace),
                        )
                    }
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                        TextButton(onClick = { showEditor = false }, enabled = !editorBusy) {
                            Text(if (editorText != editorOriginal) "放弃修改" else "关闭")
                        }
                        TextButton(onClick = { saveEditor() },
                            enabled = !editorBusy && editorError.isBlank() && editorHash.isNotBlank()) {
                            Text("保存并备份")
                        }
                    }
                }
            }
        }
    }'''+s[b:]
p.write_text(s)
assert "拒绝截断读取" in s
assert "文件被外部修改，拒绝覆盖" in s
assert "sha256sum --" in s
assert "DialogProperties(usePlatformDefaultWidth = false)" in s
assert "dualWindows.windows.forEach" in s
print("DN46 complete-read SHA-guarded safe editor with backup, fullscreen UI")
}${'
if ! ${'$'}BB cp -a -- "${'$'}P" "${'$'}TMP"; then echo '临时副本失败'; exit 72; fi
if ! printf '%s' ${shellQuote(encoded)} | ${'$'}BB base64 -d > "${'$'}TMP"; then
  ${'$'}BB rm -f -- "${'$'}TMP"; echo '临时文件写入失败'; exit 73
fi
GOT=$(${'$'}BB sha256sum -- "${'$'}TMP" | ${'$'}BB cut -d ' ' -f1)
if [ "${'$'}GOT" != "${'$'}NEW_HASH" ]; then
  ${'$'}BB rm -f -- "${'$'}TMP"; echo '新文件 SHA-256 不匹配'; exit 74
fi
CURRENT=$(${'$'}BB sha256sum -- "${'$'}P" | ${'$'}BB cut -d ' ' -f1)
if [ "${'$'}CURRENT" != "${'$'}EXPECTED" ]; then
  ${'$'}BB rm -f -- "${'$'}TMP"; echo '保存期间原文件已改变'; exit 75
fi
if ! ${'$'}BB cp -a -- "${'$'}P" "${'$'}BACKUP"; then
  ${'$'}BB rm -f -- "${'$'}TMP"; echo '备份失败，原文件未改动'; exit 76
fi
if ! ${'$'}BB mv -f -- "${'$'}TMP" "${'$'}P"; then
  echo '替换失败，备份保留'; exit 77
fi
echo "保存成功，备份 ${'$'}BACKUP"
""".trimIndent()
            val result = execRoot(script)
            editorBusy = false
            if (result.success) {
                editorOriginal = editorText
                editorHash = newHash
                showEditor = false
                dualWindows.windows.forEach { pane ->
                    if (pane.path == parentPath(path)) pane.refresh()
                }
                fileError = result.out.ifBlank { "保存成功" }
            } else editorError = result.out.ifBlank { "保存失败，未确认替换" }
        }
    }

'''+s[b:]
# Fix the backup date substitution to use standard $(date...) rather than arithmetic expansion.
s=s.replace('BACKUP="${'$'}P.dn-bak-$((${'$'}BB date +%s))-${'$'}${'$'}"',
    'BACKUP="${'$'}P.dn-bak-$(${'$'}BB date +%s)-${'$'}${'$'}"') if False else s
a=s.index('    if (showEditor) {\n        AlertDialog(')
b=s.index('\n}\n',a)
s=s[:a]+r'''    if (showEditor) {
        Dialog(onDismissRequest = { if (!editorBusy && editorText == editorOriginal) showEditor = false },
            properties = DialogProperties(usePlatformDefaultWidth = false)) {
            Surface(modifier = Modifier.fillMaxSize().padding(5.dp),
                shape = MaterialTheme.shapes.medium) {
                Column(Modifier.fillMaxSize().padding(12.dp)) {
                    Text(editorPath.substringAfterLast('/'),
                        style = MaterialTheme.typography.titleMedium,
                        maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(editorPath, style = MaterialTheme.typography.labelSmall,
                        maxLines = 2, overflow = TextOverflow.Ellipsis,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                    if (editorError.isNotBlank())
                        Text(editorError, style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.error)
                    Spacer(Modifier.height(8.dp))
                    if (editorBusy) {
                        Box(Modifier.weight(1f).fillMaxWidth(),
                            contentAlignment = Alignment.Center) { CircularProgressIndicator() }
                    } else {
                        OutlinedTextField(
                            value = editorText, onValueChange = { editorText = it },
                            modifier = Modifier.weight(1f).fillMaxWidth(),
                            enabled = editorError.isBlank(),
                            textStyle = MaterialTheme.typography.bodySmall.copy(fontFamily = FontFamily.Monospace),
                        )
                    }
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                        TextButton(onClick = { showEditor = false }, enabled = !editorBusy) {
                            Text(if (editorText != editorOriginal) "放弃修改" else "关闭")
                        }
                        TextButton(onClick = { saveEditor() },
                            enabled = !editorBusy && editorError.isBlank() && editorHash.isNotBlank()) {
                            Text("保存并备份")
                        }
                    }
                }
            }
        }
    }'''+s[b:]
p.write_text(s)
assert "拒绝截断读取" in s
assert "文件被外部修改，拒绝覆盖" in s
assert "sha256sum --" in s
assert "DialogProperties(usePlatformDefaultWidth = false)" in s
assert "dualWindows.windows.forEach" in s
print("DN46 complete-read SHA-guarded safe editor with backup, fullscreen UI")
}"
if ! ${'$'}BB cp -a -- "${'$'}P" "${'$'}TMP"; then echo '临时副本失败'; exit 72; fi
if ! printf '%s' ${shellQuote(encoded)} | ${'$'}BB base64 -d > "${'$'}TMP"; then
  ${'$'}BB rm -f -- "${'$'}TMP"; echo '临时文件写入失败'; exit 73
fi
GOT=$(${'$'}BB sha256sum -- "${'$'}TMP" | ${'$'}BB cut -d ' ' -f1)
if [ "${'$'}GOT" != "${'$'}NEW_HASH" ]; then
  ${'$'}BB rm -f -- "${'$'}TMP"; echo '新文件 SHA-256 不匹配'; exit 74
fi
CURRENT=$(${'$'}BB sha256sum -- "${'$'}P" | ${'$'}BB cut -d ' ' -f1)
if [ "${'$'}CURRENT" != "${'$'}EXPECTED" ]; then
  ${'$'}BB rm -f -- "${'$'}TMP"; echo '保存期间原文件已改变'; exit 75
fi
if ! ${'$'}BB cp -a -- "${'$'}P" "${'$'}BACKUP"; then
  ${'$'}BB rm -f -- "${'$'}TMP"; echo '备份失败，原文件未改动'; exit 76
fi
if ! ${'$'}BB mv -f -- "${'$'}TMP" "${'$'}P"; then
  echo '替换失败，备份保留'; exit 77
fi
echo "保存成功，备份 ${'$'}BACKUP"
""".trimIndent()
            val result = execRoot(script)
            editorBusy = false
            if (result.success) {
                editorOriginal = editorText
                editorHash = newHash
                showEditor = false
                dualWindows.windows.forEach { pane ->
                    if (pane.path == parentPath(path)) pane.refresh()
                }
                fileError = result.out.ifBlank { "保存成功" }
            } else editorError = result.out.ifBlank { "保存失败，未确认替换" }
        }
    }

'''+s[b:]
# Fix the backup date substitution to use standard $(date...) rather than arithmetic expansion.
s=s.replace('BACKUP="${'$'}P.dn-bak-$((${'$'}BB date +%s))-${'$'}${'$'}"',
    'BACKUP="${'$'}P.dn-bak-$(${'$'}BB date +%s)-${'$'}${'$'}"') if False else s
a=s.index('    if (showEditor) {\n        AlertDialog(')
b=s.index('\n}\n',a)
s=s[:a]+r'''    if (showEditor) {
        Dialog(onDismissRequest = { if (!editorBusy && editorText == editorOriginal) showEditor = false },
            properties = DialogProperties(usePlatformDefaultWidth = false)) {
            Surface(modifier = Modifier.fillMaxSize().padding(5.dp),
                shape = MaterialTheme.shapes.medium) {
                Column(Modifier.fillMaxSize().padding(12.dp)) {
                    Text(editorPath.substringAfterLast('/'),
                        style = MaterialTheme.typography.titleMedium,
                        maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(editorPath, style = MaterialTheme.typography.labelSmall,
                        maxLines = 2, overflow = TextOverflow.Ellipsis,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                    if (editorError.isNotBlank())
                        Text(editorError, style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.error)
                    Spacer(Modifier.height(8.dp))
                    if (editorBusy) {
                        Box(Modifier.weight(1f).fillMaxWidth(),
                            contentAlignment = Alignment.Center) { CircularProgressIndicator() }
                    } else {
                        OutlinedTextField(
                            value = editorText, onValueChange = { editorText = it },
                            modifier = Modifier.weight(1f).fillMaxWidth(),
                            enabled = editorError.isBlank(),
                            textStyle = MaterialTheme.typography.bodySmall.copy(fontFamily = FontFamily.Monospace),
                        )
                    }
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                        TextButton(onClick = { showEditor = false }, enabled = !editorBusy) {
                            Text(if (editorText != editorOriginal) "放弃修改" else "关闭")
                        }
                        TextButton(onClick = { saveEditor() },
                            enabled = !editorBusy && editorError.isBlank() && editorHash.isNotBlank()) {
                            Text("保存并备份")
                        }
                    }
                }
            }
        }
    }'''+s[b:]
p.write_text(s)
assert "拒绝截断读取" in s
assert "文件被外部修改，拒绝覆盖" in s
assert "sha256sum --" in s
assert "DialogProperties(usePlatformDefaultWidth = false)" in s
assert "dualWindows.windows.forEach" in s
print("DN46 complete-read SHA-guarded safe editor with backup, fullscreen UI")
