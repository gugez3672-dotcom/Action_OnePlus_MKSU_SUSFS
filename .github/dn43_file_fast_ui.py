#!/usr/bin/env python3
"""DN43: faster single-process directory metadata, cache on back, transient notices, light header."""
from pathlib import Path
p=Path("source/manager/app/src/main/java/com/resukisu/resukisu/ui/screen/main/DnDualPane.kt")
s=p.read_text()
def swap(old,new):
    global s
    if s.count(old)!=1: raise SystemExit("DN43 drift: "+old[:100]+" count="+str(s.count(old)))
    s=s.replace(old,new,1)

start=s.index("private suspend fun readDirectory(cli: KsuCliRepository, path: String): DualResult {")
end=s.index("private fun parseEntries(s: String): List<DualEntry> =",start)
fast=r'''private suspend fun readDirectory(cli: KsuCliRepository, path: String): DualResult {
    val d = '$'
    val bb = "/data/adb/ksu/bin/busybox"
    // One stat process per directory, instead of 3 fork/exec calls PER file.
    // Unmatched globs are harmless: stat skips them and the command exits 0.
    val script = "P=" + qs(path) + "\n" +
        "if [ ! -d \"" + d + "P\" ]; then echo '目录无法访问'; exit 2; fi\n" +
        "set -- \"" + d + "P\"/* \"" + d + "P\"/.[!.]* \"" + d + "P\"/..?*\n" +
        bb + " stat -c '%n|%F|%s|%Y' -- \"" + d + "@\" 2>/dev/null || true"
    return cmd(cli, script)
}
'''
s=s[:start]+fast+s[end:]
old=r'''    s.lineSequence().mapNotNull { line ->
        val parts = line.split('\t', limit = 4)
        if (parts.size != 4 || parts[0] !in listOf("D", "F")) null
        else DualEntry(parts[3], parts[0] == "D", parts[1].toLongOrNull() ?: 0L,
            parts[2].toLongOrNull() ?: 0L)
    }.distinctBy { it.name }.sortedWith(compareBy<DualEntry>({ !it.folder }, { it.name.lowercase(Locale.ROOT) })).toList()
'''
new=r'''    s.lineSequence().mapNotNull { line ->
        val parts = line.split('|', limit = 4)
        if (parts.size != 4 || parts[0].isBlank()) null
        else DualEntry(
            parts[0].substringAfterLast('/'), parts[1] == "directory",
            parts[2].toLongOrNull() ?: 0L, parts[3].toLongOrNull() ?: 0L)
    }.distinctBy { it.name }.sortedWith(compareBy<DualEntry>({ !it.folder }, { it.name.lowercase(Locale.ROOT) })).toList()
'''
swap(old,new)
swap('    private val anchors = mutableMapOf<String, DualAnchor>()\n',
'''    private val anchors = mutableMapOf<String, DualAnchor>()
    // Bounded in-memory data cache: returning to a known folder is immediate.
    private val directoryCache = LinkedHashMap<String, List<DualEntry>>()
    fun rememberFiles(at: String, values: List<DualEntry>) {
        directoryCache[at] = values
        if (directoryCache.size > 20) directoryCache.remove(directoryCache.keys.first())
    }
''')
swap('''        capture()
        if (push) { back = (back + path).takeLast(48); forward = emptyList() }
        path = d
''',
'''        capture()
        rememberFiles(path, files)
        if (push) { back = (back + path).takeLast(48); forward = emptyList() }
        path = d
''')
swap('''        restoring = true
        files = emptyList()
        refreshId++
''',
'''        restoring = true
        files = directoryCache[d] ?: emptyList()
        refreshId++
''')
swap('''                pane.files = files
                if (pane.restoring) {
''',
'''                pane.files = files
                pane.rememberFiles(path, files)
                if (pane.restoring) {
''')
# Prevent indefinite operation status banners.
swap('''    var message by remember { mutableStateOf("") }
''',
'''    var message by remember { mutableStateOf("") }
    LaunchedEffect(message) {
        if (message.isNotBlank()) {
            delay(2500L)
            message = ""
        }
    }
''')
# match ColorOS status bar surface instead of a black 56dp toolbar
swap('''Surface(color = dark, modifier = Modifier.fillMaxWidth())''',
     '''Surface(color = MaterialTheme.colorScheme.background, modifier = Modifier.fillMaxWidth())''')
swap('''tint = if (current.path != "/") white else Color.Gray''',
     '''tint = if (current.path != "/") MaterialTheme.colorScheme.onBackground else Color.Gray''')
swap('''                        color = white,
                        fontSize = 18.sp,''',
'''                        color = MaterialTheme.colorScheme.onBackground,
                        fontSize = 18.sp,''')
swap('''                        color = Color(0xFFCECECE),
                        fontSize = 11.sp,''',
'''                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 11.sp,''')
swap('''Icon(Icons.TwoTone.Terminal, "打开 Root 终端", tint = white)''',
     '''Icon(Icons.TwoTone.Terminal, "打开 Root 终端", tint = MaterialTheme.colorScheme.onBackground)''')
swap('''Icon(Icons.TwoTone.MoreVert, "文件管理操作", tint = white)''',
     '''Icon(Icons.TwoTone.MoreVert, "文件管理操作", tint = MaterialTheme.colorScheme.onBackground)''')
# Keep navigation restoration immediate even when opening cached directory.
swap('''    LaunchedEffect(pane.path, pane.refreshId) {
''',
'''    LaunchedEffect(pane.path) {
        if (pane.restoring && pane.files.isNotEmpty()) {
            val mark = pane.saved()
            withFrameNanos { }
            if (mark != null) {
                val index = mark.name?.let { name ->
                    pane.files.indexOfFirst { it.name == name }.takeIf { it >= 0 }?.plus(1)
                } ?: mark.index
                pane.scroll.scrollToItem(index.coerceIn(0, pane.files.size), mark.offset.coerceAtLeast(0))
                pane.restoring = false
            }
        }
    }
    LaunchedEffect(pane.path, pane.refreshId) {
''')

p.write_text(s)
assert "stat -c '%n|%F|%s|%Y'" in s
assert "directoryCache" in s
assert "pane.rememberFiles(path, files)" in s
assert "delay(2500L)" in s
assert "Surface(color = MaterialTheme.colorScheme.background" in s
assert "val destination = joined(opposite.path, o.from.entry.name)" in s
print("DN43: batched stat, cached folder returns, transient notice, ColorOS light header")
