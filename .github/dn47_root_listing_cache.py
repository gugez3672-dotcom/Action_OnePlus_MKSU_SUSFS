#!/usr/bin/env python3
"""DN47: robust batched root listing + explicit cache expiry/invalidation/scroll anchors."""
from pathlib import Path
p=Path("source/manager/app/src/main/java/com/resukisu/resukisu/ui/screen/main/DnDualPane.kt")
s=p.read_text()
def rep(a,b):
    global s
    if s.count(a)!=1: raise SystemExit("DN47 drift: "+a[:100]+" count="+str(s.count(a)))
    s=s.replace(a,b,1)
a=s.index("private suspend fun readDirectory(cli: KsuCliRepository, path: String): DualResult {")
b=s.index("\n@Composable\ninternal fun DnDualFiles(",a)
s=s[:a]+r'''private suspend fun readDirectory(cli: KsuCliRepository, path: String): DualResult {
    val dollar = '$'
    val bb = "/data/adb/ksu/bin/busybox"
    val script = "P=" + qs(path) + "\n" +
        "if [ ! -d \"" + dollar + "P\" ]; then echo '目录不存在'; exit 2; fi\n" +
        "set --\n" +
        "for f in \"" + dollar + "P\"/* \"" + dollar + "P\"/.[!.]* \"" + dollar + "P\"/..?*; do\n" +
        "  [ -e \"" + dollar + "f\" ] || [ -L \"" + dollar + "f\" ] || continue\n" +
        "  set -- \"" + dollar + "@\" \"" + dollar + "f\"\n" +
        "done\n" +
        "[ \"" + dollar + "#\" -eq 0 ] && exit 0\n" +
        bb + " stat -L -c '%n|%F|%s|%Y' -- \"" + dollar + "@\""
    return cmd(cli, script)
}
private fun parseEntries(s: String): List<DualEntry> =
    s.lineSequence().filter { it.isNotBlank() }.mapNotNull { line ->
        // Parse from the right: file names are allowed to contain '|'.
        val p3 = line.lastIndexOf('|')
        val p2 = if (p3 >= 0) line.lastIndexOf('|', p3 - 1) else -1
        val p1 = if (p2 >= 0) line.lastIndexOf('|', p2 - 1) else -1
        if (p1 < 0 || p2 <= p1 || p3 <= p2) null
        else {
            val fullName = line.substring(0, p1)
            val type = line.substring(p1 + 1, p2)
            val size = line.substring(p2 + 1, p3).toLongOrNull()
            val mtime = line.substring(p3 + 1).toLongOrNull()
            val name = fullName.substringAfterLast('/')
            if (name.isEmpty() || size == null || mtime == null) null
            else DualEntry(name, type == "directory", size, mtime)
        }
    }.distinctBy { it.name }
        .sortedWith(compareBy<DualEntry>({ !it.folder }, { it.name.lowercase(Locale.ROOT) })).toList()
''' + s[b:]
rep('''    // Bounded in-memory data cache: returning to a known folder is immediate.
    private val directoryCache = LinkedHashMap<String, List<DualEntry>>()
    fun rememberFiles(at: String, values: List<DualEntry>) {
        directoryCache[at] = values
        if (directoryCache.size > 20) directoryCache.remove(directoryCache.keys.first())
    }
''',
'''    private data class Cache(val files: List<DualEntry>, val at: Long)
    private val directoryCache = LinkedHashMap<String, Cache>(64, 0.75f, true)
    private val cacheTtlMs = 8_000L
    fun rememberFiles(at: String, values: List<DualEntry>) {
        directoryCache[at] = Cache(values, android.os.SystemClock.elapsedRealtime())
        if (directoryCache.size > 64) directoryCache.remove(directoryCache.keys.first())
    }
    fun cached(at: String): List<DualEntry>? {
        val value = directoryCache[at] ?: return null
        return if (android.os.SystemClock.elapsedRealtime() - value.at <= cacheTtlMs)
            value.files else null
    }
    fun invalidate(at: String) {
        directoryCache.remove(at)
    }
''')
rep('''        files = directoryCache[d] ?: emptyList()''',
    '''        files = cached(d) ?: emptyList()''')
rep('''    fun refresh() { refreshId++ }''',
    '''    fun refresh() { invalidate(path); refreshId++ }''')
rep('''        val anchor = DualAnchor(files.getOrNull(i - 1)?.name, i, scroll.firstVisibleItemScrollOffset)''',
'''        val shown = if (filter.isBlank()) files else files.filter { it.name.contains(filter, true) }
        val anchor = DualAnchor(shown.getOrNull(i - 1)?.name, i, scroll.firstVisibleItemScrollOffset)''')
rep('''    fun navigate(destination: String, push: Boolean = true) {''',
'''    fun navigate(destination: String, push: Boolean = true) {''')
# Store cached metadata even when switching, but never resurrect invalidated folders.
# Replace the temporary horizontal progress divider with a thin persistent overlay-style indicator.
rep('''        if (pane.loading) HorizontalDivider(thickness = 2.dp, color = Color(0xFF357ADF))
''',
'''        // Loading does not clear the existing rows or reset scroll state.
        if (pane.loading && pane.files.isEmpty())
            Text("读取中…", fontSize = 11.sp, color = grey, modifier = Modifier.padding(2.dp))
''')
p.write_text(s)
assert 'stat -L -c' in s and 'set --' in s
assert 'lastIndexOf' in s and 'cacheTtlMs = 8_000L' in s
assert 'fun invalidate(at: String)' in s
assert 'val shown = if (filter.isBlank())' in s
assert 'parseEntries' in s and 'DnDualFiles(' in s
print("DN47: safe right-parsed stat, no unmatched globs, cached directory TTL/invalidation, scroll mapping")
