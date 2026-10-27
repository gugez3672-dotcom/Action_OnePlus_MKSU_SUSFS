package com.daily.notes.ui.screen.main

import android.content.Context
import android.content.Intent
import android.util.Base64
import android.util.Log
import androidx.core.content.FileProvider
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Folder
import androidx.compose.material.icons.twotone.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.input.nestedscroll.NestedScrollConnection
import androidx.compose.ui.input.nestedscroll.NestedScrollSource
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.Popup
import androidx.compose.ui.window.PopupProperties
import com.daily.notes.data.shell.BackendCliRepository
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import com.daily.notes.R
import com.daily.notes.ui.component.DnToolSwitchButton
import com.daily.notes.ui.component.DnToolSwitchTarget
import com.daily.notes.data.files.DnFileCommands
import com.daily.notes.data.files.DnApkInstaller
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.util.Locale

private val dark = Color(0xFF292929)
private val grey = Color(0xFF777777)
private val white = Color.White
private val pale = Color(0xFFF6F6F6)
private val divider = Color(0xFFE4E4E4)

internal data class DualEntry(val name: String, val folder: Boolean, val size: Long, val mtime: Long)
internal data class DualAnchor(val name: String?, val index: Int, val offset: Int)
private data class DualTarget(val side: Int, val directory: String, val entry: DualEntry)
private data class DualOperation(val kind: String, val from: DualTarget,
    val others: List<DualTarget> = emptyList(), val destinationDir: String = "")
private data class DualResult(val value: String, val ok: Boolean, val code: Int)
private fun qs(v: String) = "'" + v.replace("'", "'\"'\"'") + "'"
private fun joined(d: String, n: String) = if (d == "/") "/" + n else d + "/" + n
private fun parentDir(d: String) = if (d == "/") "/" else d.trimEnd('/').substringBeforeLast('/', "").ifEmpty { "/" }
private fun textFile(n: String) = listOf(".txt",".sh",".prop",".conf",".json",".xml",".log",".rc",".md",".ini",".yml")
    .any { n.endsWith(it, true) }
private fun fileExtension(name: String) = name.substringAfterLast('.', "").lowercase(Locale.ROOT)
private fun dateText(n: Long): String = if (n <= 0L) "" else
    java.text.SimpleDateFormat("yy-MM-dd HH:mm", Locale.getDefault()).format(java.util.Date(n * 1000L))
private fun sizeText(n: Long): String = when {
    n < 1024L -> n.toString() + "B"
    n < 1048576L -> "%.1fK".format(Locale.US, n / 1024.0)
    n < 1073741824L -> "%.1fM".format(Locale.US, n / 1048576.0)
    else -> "%.1fG".format(Locale.US, n / 1073741824.0)
}

internal class DnFileWindow(val side: Int, ctx: Context, initial: String) {
    private val prefs = ctx.getSharedPreferences("daily_notes_dual_files", Context.MODE_PRIVATE)
    var path by mutableStateOf(prefs.getString("path_" + side, initial) ?: initial)
    var files by mutableStateOf<List<DualEntry>>(emptyList())
    var filter by mutableStateOf("")
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
        restoring = true
        sortMode = mode
        reversed = descending
        refreshId++
        prefs.edit().putString("sort_" + path, mode)
            .putBoolean("reverse_" + path, descending).apply()
    }
    var selectedNames by mutableStateOf<Set<String>>(emptySet())
    var selectAnchor by mutableIntStateOf(-1)
    private var selectionAnchorName: String? = null
    fun choose(entry: DualEntry, range: Boolean = false) {
        val entries = visible()
        val index = entries.indexOfFirst { it.name == entry.name }
        if (index < 0) return
        val anchor = entries.indexOfFirst { it.name == selectionAnchorName }
        if (range && selectedNames.isNotEmpty() && selectAnchor >= 0 && anchor >= 0) {
            val low = minOf(index, anchor)
            val high = maxOf(index, anchor)
            selectedNames = selectedNames + entries.subList(low, high + 1).map { it.name }
        } else {
            selectedNames = if (entry.name in selectedNames) selectedNames - entry.name
                else selectedNames + entry.name
        }
        selectAnchor = index
        selectionAnchorName = entry.name
    }
    var error by mutableStateOf("")
    var loading by mutableStateOf(false)
    var refreshId by mutableIntStateOf(0)
    var restoring = true
    var back by mutableStateOf<List<String>>(emptyList())
    var forward by mutableStateOf<List<String>>(emptyList())
    val scroll = LazyListState()
    private val anchors = mutableMapOf<String, DualAnchor>()
    private data class Cache(val files: List<DualEntry>, val at: Long)
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
    private fun key(p: String) = "pos_" + side + "_" +
        Base64.encodeToString(p.toByteArray(Charsets.UTF_8), Base64.NO_WRAP or Base64.URL_SAFE)
    fun capture() {
        if (restoring) return
        val i = scroll.firstVisibleItemIndex
        val shown = visible()
        val anchor = DualAnchor(shown.getOrNull(i - 1)?.name, i, scroll.firstVisibleItemScrollOffset)
        anchors[path] = anchor
        prefs.edit().putString(key(path), JSONObject().put("name", anchor.name)
            .put("index", i).put("offset", anchor.offset).toString()).apply()
    }
    fun saved(): DualAnchor? {
        anchors[path]?.let { return it }
        return runCatching {
            val o = JSONObject(prefs.getString(key(path), "") ?: "")
            DualAnchor(if (o.isNull("name")) null else o.optString("name"),
                o.optInt("index"), o.optInt("offset"))
        }.getOrNull()
    }
    fun navigate(destination: String, push: Boolean = true) {
        val d = destination.replace(Regex("/+"), "/").trimEnd('/').ifEmpty { "/" }
        if (!d.startsWith("/")) return
        if (d == path) { refresh(); return }
        capture()
        rememberFiles(path, files)
        if (push) { back = (back + path).takeLast(48); forward = emptyList() }
        path = d
        prefs.edit().putString("path_" + side, path).apply()
        filter = ""
        sortMode = prefs.getString("sort_" + path, "name") ?: "name"
        reversed = prefs.getBoolean("reverse_" + path, false)
        selectedNames = emptySet()
        selectAnchor = -1
        restoring = true
        files = cached(d) ?: emptyList()
        refreshId++
    }
    fun backwards() {
        val p = back.lastOrNull() ?: return
        back = back.dropLast(1)
        forward = (forward + path).takeLast(48)
        navigate(p, false)
    }
    fun forwards() {
        val p = forward.lastOrNull() ?: return
        forward = forward.dropLast(1)
        back = (back + path).takeLast(48)
        navigate(p, false)
    }
    fun refresh() { capture(); restoring = true; invalidate(path); refreshId++ }
}
internal class DnDualWindows(ctx: Context) {
    private val prefs = ctx.getSharedPreferences("daily_notes_dual_files", Context.MODE_PRIVATE)
    val windows = listOf(DnFileWindow(0, ctx, "/data/adb"), DnFileWindow(1, ctx, "/storage/emulated/0"))
    var active by mutableIntStateOf(prefs.getInt("active_pane", 0).coerceIn(0, 1))
    var bookmarks by mutableStateOf(prefs.getStringSet("favorites", emptySet())?.toSet() ?: emptySet())
    fun toggleBookmark(path: String) {
        val newSet = if (path in bookmarks) bookmarks - path else bookmarks + path
        bookmarks = newSet
        prefs.edit().putStringSet("favorites", newSet.toSet()).apply()
    }
    fun activate(index: Int) {
        if (index != active) {
            windows[active].capture()
            active = index
            prefs.edit().putInt("active_pane", index).apply()
        }
    }
}
private suspend fun cmd(cli: BackendCliRepository, command: String): DualResult = withContext(Dispatchers.IO) {
    val output = arrayListOf<String>()
    val errors = arrayListOf<String>()
    val r = cli.withNewRootShell(globalMnt = true) {
        newJob().add(command).to(output, errors).exec()
    }
    DualResult((output + errors).joinToString("\n"), r.isSuccess, r.code)
}
private suspend fun readDirectory(cli: BackendCliRepository, path: String): DualResult {
    // NUL-separated names are encoded once per batch. Metadata never includes
    // a name, so newlines, pipes, Unicode and dangling links stay unambiguous.
    val script = """
        BB=/data/adb/ksu/bin/busybox
        P=${qs(path)}
        [ -d "${'$'}P" ] && [ -r "${'$'}P" ] && [ -x "${'$'}P" ] || exit 2
        emit() {
            printf 'N:'
            printf '%s\0' "${'$'}@" | ${'$'}BB base64 -w 0
            printf '\nD:%s\n' "${'$'}flags"
            ${'$'}BB stat -c 'M:%s|%Y' -- "${'$'}@"
        }
        set --
        flags=
        for f in "${'$'}P"/* "${'$'}P"/.[!.]* "${'$'}P"/..?*; do
            [ -e "${'$'}f" ] || [ -L "${'$'}f" ] || continue
            set -- "${'$'}@" "${'$'}{f##*/}"
            if [ -d "${'$'}f" ]; then flags="${'$'}{flags}D"; else flags="${'$'}{flags}F"; fi
            if [ "${'$'}#" -eq 32 ]; then
                (cd "${'$'}P" && emit "${'$'}@") || exit 3
                set --; flags=
            fi
        done
        [ "${'$'}#" -eq 0 ] || (cd "${'$'}P" && emit "${'$'}@")
    """.trimIndent()
    return cmd(cli, "(\n" + script + "\n)")
}
private fun parseEntries(s: String): List<DualEntry> {
    val lines = s.lineSequence().toList()
    val entries = mutableListOf<DualEntry>()
    var index = 0
    while (index < lines.size) {
        val line = lines[index++]
        if (!line.startsWith("N:")) continue
        val names = runCatching { String(Base64.decode(line.drop(2), Base64.DEFAULT), Charsets.UTF_8)
            .split('\u0000').dropLast(1) }.getOrNull() ?: continue
        val flags = lines.getOrNull(index++)?.removePrefix("D:") ?: continue
        val batch = mutableListOf<DualEntry>()
        for ((i, name) in names.withIndex()) {
            val metadata = lines.getOrNull(index++)?.removePrefix("M:")?.split('|') ?: continue
            val size = metadata.getOrNull(0)?.toLongOrNull() ?: continue
            val time = metadata.getOrNull(1)?.toLongOrNull() ?: continue
            batch.add(DualEntry(name, flags.getOrNull(i) == 'D', size, time))
        }
        if (batch.size == names.size && flags.length == names.size) entries.addAll(batch)
    }
    return entries.distinctBy { it.name }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun DnDualFiles(
    state: DnDualWindows,
    openTerminal: (String) -> Unit,
    runScript: (String) -> Unit,
    openEditor: (String) -> Unit,
) {
    val backendContext = LocalContext.current
    val cli = remember(backendContext) { BackendCliRepository(backendContext) }
    val context = LocalContext.current
    val commands = remember(context) { DnFileCommands(context) }
    val apkInstaller = remember(context) { DnApkInstaller(context) }
    val commandFailed = stringResource(R.string.dn_files_operation_failed)
    val apkOpenFailed = stringResource(R.string.dn_files_apk_open_failed)
    val unsafeDestination = stringResource(R.string.dn_files_unsafe_destination)
    val completedFormat = stringResource(R.string.dn_files_completed_compact)
    val cancelledText = stringResource(R.string.dn_files_cancelled)
    val scope = rememberCoroutineScope()
    val current = state.windows[state.active]
    var choice by remember { mutableStateOf<DualTarget?>(null) }
    var operation by remember { mutableStateOf<DualOperation?>(null) }
    var pendingTransfer by remember { mutableStateOf<DualOperation?>(null) }
    var rename by remember { mutableStateOf<DualTarget?>(null) }
    var renameText by remember { mutableStateOf(TextFieldValue("")) }
    var properties by remember { mutableStateOf<String?>(null) }
    var addressDialog by remember { mutableStateOf(false) }
    var address by remember { mutableStateOf("") }
    var newDialog by remember { mutableStateOf(false) }
    var newName by remember { mutableStateOf("") }
    var filterVisible by remember { mutableStateOf(false) }
    var sortDialog by remember { mutableStateOf(false) }
    var favoritesDialog by remember { mutableStateOf(false) }
    var chmodTarget by remember { mutableStateOf<DualTarget?>(null) }
    var chmodMode by remember { mutableStateOf("0644") }
    val clipboard = LocalClipboardManager.current
    var message by remember { mutableStateOf("") }
    var openingApk by remember { mutableStateOf(false) }
    var collision by remember { mutableStateOf("skip") }
    var conflictCount by remember { mutableStateOf<Int?>(null) }
    var working by remember { mutableStateOf(false) }
    var wantCancel by remember { mutableStateOf(false) }
    var jobName by remember { mutableStateOf("") }
    var jobDone by remember { mutableIntStateOf(0) }
    var jobTotal by remember { mutableIntStateOf(0) }
    var jobErrors by remember { mutableStateOf<List<String>>(emptyList()) }
    var detailedErrors by remember { mutableStateOf(false) }
    LaunchedEffect(message) {
        if (message.isNotBlank()) {
            delay(2500L)
            message = ""
        }
    }
    var expandedMenu by remember { mutableStateOf(false) }
    var batchMenu by remember { mutableStateOf(false) }
    fun installApk(path: String) {
        if (openingApk) return
        openingApk = true
        scope.launch {
            try {
                val staged = apkInstaller.stage(cli, path)
                val uri = FileProvider.getUriForFile(context,
                    "${context.packageName}.fileprovider", staged)
                val intent = Intent(Intent.ACTION_INSTALL_PACKAGE).apply {
                    setDataAndType(uri, "application/vnd.android.package-archive")
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                }
                try {
                    context.startActivity(intent)
                } catch (_: android.content.ActivityNotFoundException) {
                    context.startActivity(Intent(Intent.ACTION_VIEW).apply {
                        setDataAndType(uri, "application/vnd.android.package-archive")
                        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                    })
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Log.e("DailyNotesFiles", "Cannot open APK installer for $path", e)
                message = apkOpenFailed
            } finally {
                openingApk = false
            }
        }
    }
    fun batchAction(kind: String, stageForPaste: Boolean = false) {
        val selected = current.files.filter { it.name in current.selectedNames }
            .map { DualTarget(state.active, current.path, it) }
        if (selected.isNotEmpty()) {
            val request = DualOperation(kind, selected.first(), selected.drop(1),
                state.windows[1 - current.side].path)
            if (stageForPaste) {
                pendingTransfer = request
                // Browsing the target must not keep the source pane in selection mode.
                current.selectedNames = emptySet()
                current.selectAnchor = -1
            } else operation = request
        }
        batchMenu = false
    }

    fun doOperation(o: DualOperation) {
        if (working) return
        val sources = listOf(o.from) + o.others
        val pairs = sources.map { target ->
            joined(target.directory, target.entry.name) to joined(o.destinationDir, target.entry.name)
        }
        val selectedMode = collision
        operation = null
        pendingTransfer = null
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
            try {
                for ((source, target) in pairs) {
                    if (wantCancel) break
                    jobName = source.substringAfterLast('/')
                    val result = cmd(cli, commands.build(o.kind, source, target, selectedMode))
                    jobDone++
                    when {
                        result.ok -> succeeded++
                        result.code == 88 -> skipped++
                        result.code == 90 -> errors.add(jobName + ": " + unsafeDestination)
                        else -> errors.add(jobName + ": " + result.value.take(200).ifBlank { commandFailed })
                    }
                }
                jobErrors = errors
                message = String.format(completedFormat, succeeded, skipped, errors.size) +
                    (if (wantCancel) cancelledText else "")
                if (errors.isNotEmpty()) detailedErrors = true
            } finally {
                val affected = sources.map { it.directory }.toSet() +
                    (if (o.kind == "delete") emptySet() else setOf(o.destinationDir))
                state.windows.forEach { pane ->
                    affected.forEach(pane::invalidate)
                    if (pane.side == o.from.side && pane.path == o.from.directory) {
                        pane.selectedNames = emptySet()
                        pane.selectAnchor = -1
                    }
                    if (pane.path in affected) pane.refresh()
                }
                working = false
            }
        }
    }
    LaunchedEffect(operation) {
        val requested = operation ?: return@LaunchedEffect
        collision = "skip"
        conflictCount = null
        if (requested.kind == "delete") return@LaunchedEffect
        val targets = (listOf(requested.from) + requested.others).map {
            joined(requested.destinationDir, it.entry.name)
        }
        val check = """
            set -- ${targets.joinToString(" ", transform = ::qs)}
            n=0
            for f do
                if [ -e "${'$'}f" ] || [ -L "${'$'}f" ]; then n=${'$'}((n+1)); fi
            done
            printf '%s\n' "${'$'}n"
        """.trimIndent()
        val result = cmd(cli, check)
        if (operation != requested) return@LaunchedEffect
        val found = if (result.ok) result.value.trim().toIntOrNull() else null
        when {
            found == null -> {
                operation = null
                message = result.value.take(200).ifBlank { commandFailed }
            }
            found == 0 -> doOperation(requested)
            else -> conflictCount = found
        }
    }
    BackHandler(current.selectedNames.isNotEmpty() || pendingTransfer != null || current.path != "/") {
        if (current.selectedNames.isNotEmpty()) {
            current.selectedNames = emptySet(); current.selectAnchor = -1
        } else if (pendingTransfer != null) pendingTransfer = null
        else current.navigate(parentDir(current.path))
    }
    Column(Modifier.fillMaxSize()) {
        // Compact toolbar; the first action matches the terminal's Files button.
        Surface(color = MaterialTheme.colorScheme.background, modifier = Modifier.fillMaxWidth()) {
            Row(
                modifier = Modifier.fillMaxWidth().height(48.dp).padding(horizontal = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                DnToolSwitchButton(
                    target = DnToolSwitchTarget.Terminal,
                    contentDescription = stringResource(R.string.dn_terminal_root),
                    onClick = { openTerminal(current.path) },
                )
                Column(
                    modifier = Modifier.weight(1f)
                        .clickable { address = current.path; addressDialog = true }
                        .padding(start = 5.dp, end = 4.dp),
                    verticalArrangement = Arrangement.Center,
                ) {
                    Text(
                        text = current.path,
                        color = MaterialTheme.colorScheme.onBackground,
                        fontSize = 18.sp,
                        lineHeight = 22.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        val pendingStatus = pendingTransfer?.let { pending ->
                            stringResource(
                                if (pending.kind == "move") R.string.dn_files_clipboard_move_prompt
                                else R.string.dn_files_clipboard_copy_prompt,
                                pending.others.size + 1,
                            )
                        }
                        val statusText = pendingStatus ?: if (openingApk)
                            stringResource(R.string.dn_files_apk_preparing) else message
                        Text(
                            text = "文件夹 " + current.files.count { it.folder } +
                                "  文件 " + current.files.count { !it.folder } +
                                (if (state.active == 0) "  · 左" else "  · 右") +
                                (if (current.selectedNames.isNotEmpty())
                                    "  · 已选 " + current.selectedNames.size else ""),
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 11.sp,
                            lineHeight = 15.sp,
                            maxLines = 1,
                        )
                        if (statusText.isNotEmpty()) {
                            Spacer(Modifier.width(4.dp))
                            Text(
                                text = statusText,
                                modifier = Modifier.weight(1f).then(
                                    if (pendingStatus == null) Modifier.clickable { message = "" }
                                    else Modifier
                                ),
                                color = if (pendingStatus != null) MaterialTheme.colorScheme.secondary
                                    else if (jobErrors.isNotEmpty()) MaterialTheme.colorScheme.error
                                    else MaterialTheme.colorScheme.primary,
                                fontSize = 10.sp,
                                lineHeight = 15.sp,
                                textAlign = TextAlign.End,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                            )
                        }
                    }
                }
                IconButton(
                    onClick = { current.navigate(parentDir(current.path)) },
                    enabled = current.path != "/",
                    modifier = Modifier.size(40.dp),
                ) {
                    Icon(Icons.TwoTone.ArrowUpward, "返回上级",
                        tint = if (current.path != "/") MaterialTheme.colorScheme.onBackground else Color.Gray)
                }
                Box(Modifier.size(40.dp)) {
                    IconButton(
                        onClick = { expandedMenu = true },
                        modifier = Modifier.size(40.dp),
                    ) {
                        Icon(Icons.TwoTone.MoreVert, stringResource(R.string.dn_files_actions),
                            tint = MaterialTheme.colorScheme.onBackground)
                    }
                    if (expandedMenu) {
                        val menuWidth = LocalConfiguration.current.screenWidthDp.dp / 2 - 12.dp
                        val density = LocalDensity.current
                        Popup(
                            alignment = Alignment.TopEnd,
                            offset = with(density) { IntOffset(0, 44.dp.roundToPx()) },
                            onDismissRequest = { expandedMenu = false },
                            properties = PopupProperties(focusable = true),
                        ) {
                            Surface(
                                modifier = Modifier.width(menuWidth).heightIn(max = 400.dp),
                                shape = RoundedCornerShape(14.dp),
                                color = MaterialTheme.colorScheme.surface,
                                tonalElevation = 4.dp,
                                shadowElevation = 10.dp,
                            ) {
                                Column(Modifier.verticalScroll(rememberScrollState()).padding(vertical = 4.dp)) {
                                    @Composable fun menuAction(
                                        label: String,
                                        icon: androidx.compose.ui.graphics.vector.ImageVector,
                                        enabled: Boolean = true,
                                        action: () -> Unit,
                                    ) {
                                        val foreground = MaterialTheme.colorScheme.onSurface
                                            .copy(alpha = if (enabled) 1f else 0.38f)
                                        Row(
                                            Modifier.fillMaxWidth().heightIn(min = 44.dp)
                                                .clickable(enabled = enabled) {
                                                    expandedMenu = false
                                                    action()
                                                }.padding(horizontal = 12.dp, vertical = 7.dp),
                                            verticalAlignment = Alignment.CenterVertically,
                                        ) {
                                            Icon(icon, null, Modifier.size(18.dp), tint = foreground)
                                            Spacer(Modifier.width(10.dp))
                                            Text(label, fontSize = 13.sp, maxLines = 2,
                                                overflow = TextOverflow.Ellipsis, color = foreground)
                                        }
                                    }
                                    menuAction(stringResource(R.string.dn_files_menu_back),
                                        Icons.TwoTone.ArrowBack, current.back.isNotEmpty()) { current.backwards() }
                                    menuAction(stringResource(R.string.dn_files_menu_forward),
                                        Icons.TwoTone.ArrowForward, current.forward.isNotEmpty()) { current.forwards() }
                                    menuAction(stringResource(R.string.dn_files_menu_refresh), Icons.TwoTone.Refresh) {
                                        current.refresh()
                                    }
                                    menuAction(stringResource(R.string.dn_files_menu_sync), Icons.TwoTone.SyncAlt) {
                                        state.windows[1 - state.active].navigate(current.path)
                                    }
                                    menuAction(stringResource(R.string.dn_files_menu_new), Icons.TwoTone.CreateNewFolder) {
                                        newName = ""; newDialog = true
                                    }
                                    menuAction(stringResource(if (filterVisible) R.string.dn_files_menu_filter_off
                                        else R.string.dn_files_menu_filter), Icons.TwoTone.FilterList) {
                                        filterVisible = !filterVisible
                                        if (!filterVisible) current.filter = ""
                                    }
                                    menuAction(stringResource(R.string.dn_files_menu_sort), Icons.TwoTone.Sort) {
                                        sortDialog = true
                                    }
                                    menuAction(stringResource(if (current.path in state.bookmarks)
                                        R.string.dn_files_menu_unbookmark else R.string.dn_files_menu_bookmark),
                                        Icons.TwoTone.Star) { state.toggleBookmark(current.path) }
                                    menuAction(stringResource(R.string.dn_files_menu_favorites), Icons.TwoTone.FolderSpecial) {
                                        favoritesDialog = true
                                    }
                                    menuAction(stringResource(R.string.dn_files_menu_path), Icons.TwoTone.Edit) {
                                        address = current.path; addressDialog = true
                                    }
                                }
                            }
                        }
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
        Box(Modifier.fillMaxSize()) {
        Row(Modifier.fillMaxSize()) {
            state.windows.forEachIndexed { index, pane ->
                DnFileList(pane, cli, state.active == index, Modifier.weight(1f).fillMaxHeight(),
                    onTap = { e ->
                        state.activate(index)
                        if (pane.selectedNames.isNotEmpty()) pane.choose(e)
                        else if (e.folder) pane.navigate(joined(pane.path, e.name))
                        else if (fileExtension(e.name) == "apk") installApk(joined(pane.path, e.name))
                        else if (e.name.endsWith(".sh", ignoreCase = true))
                            runScript(joined(pane.path, e.name))
                        else if (textFile(e.name)) openEditor(joined(pane.path, e.name))
                        else choice = DualTarget(index, pane.path, e)
                    },
                    onMenu = { e ->
                        state.activate(index)
                        if (pane.selectedNames.isNotEmpty()) batchMenu = true
                        else choice = DualTarget(index, pane.path, e)
                    },
                    onSelect = { e, range -> state.activate(index); pane.choose(e, range) },
                    onActivate = { state.activate(index) })
                if (index == 0) Box(Modifier.width(1.dp).fillMaxHeight().background(Color.LightGray))
            }
        }
        pendingTransfer?.let { pending ->
            Column(
                modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                SmallFloatingActionButton(
                    onClick = { pendingTransfer = null },
                    containerColor = MaterialTheme.colorScheme.errorContainer,
                ) {
                    Icon(Icons.TwoTone.Close, stringResource(R.string.dn_files_clipboard_cancel))
                }
                FloatingActionButton(
                    onClick = { operation = pending.copy(destinationDir = current.path) },
                ) {
                    Icon(Icons.TwoTone.ContentPaste, stringResource(R.string.dn_files_clipboard_paste))
                }
            }
        }
        }
    }
    if (sortDialog) {
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
    if (batchMenu && current.selectedNames.isNotEmpty()) {
        val copyLabel = stringResource(if (state.active == 0) R.string.dn_files_copy_right else R.string.dn_files_copy_left)
        val moveLabel = stringResource(if (state.active == 0) R.string.dn_files_move_right else R.string.dn_files_move_left)
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
                        onLongPress: (() -> Unit)? = null,
                        onClick: () -> Unit,
                    ) {
                        val buttonModifier = modifier.height(54.dp).let { base ->
                            if (onLongPress == null) base.clickable(onClick = onClick)
                            else base.combinedClickable(onClick = onClick, onLongClick = onLongPress)
                        }
                        Row(
                            buttonModifier.padding(horizontal = 7.dp),
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
                        actionButton(copyLabel, Icons.TwoTone.ContentCopy,
                            Modifier.weight(1f),
                            onLongPress = { batchAction("copy", stageForPaste = true) },
                            onClick = { batchAction("copy") })
                        actionButton(moveLabel, Icons.TwoTone.DriveFileMove,
                            Modifier.weight(1f),
                            onLongPress = { batchAction("move", stageForPaste = true) },
                            onClick = { batchAction("move") })
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
                    Row(Modifier.fillMaxWidth()) {
                        actionButton("全选", Icons.TwoTone.SelectAll,
                            Modifier.weight(1f), onClick = {
                                current.selectedNames = current.visible().map { it.name }.toSet()
                                batchMenu = false
                            })
                        actionButton("反选", Icons.TwoTone.ContentCopy,
                            Modifier.weight(1f), onClick = {
                                current.selectedNames = current.visible().map { it.name }
                                    .filterNot { it in current.selectedNames }.toSet()
                                batchMenu = false
                            })
                    }
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                        TextButton(onClick = { batchMenu = false }) { Text("关闭") }
                    }
                }
            }
        }
    }
    choice?.takeIf { !working }?.let { c ->
        val file = joined(c.directory, c.entry.name)
        val copyLabel = stringResource(if (c.side == 0) R.string.dn_files_copy_right else R.string.dn_files_copy_left)
        val moveLabel = stringResource(if (c.side == 0) R.string.dn_files_move_right else R.string.dn_files_move_left)
        Dialog(onDismissRequest = { choice = null }) {
            Surface(
                shape = RoundedCornerShape(14.dp),
                color = MaterialTheme.colorScheme.surface,
                tonalElevation = 2.dp,
            ) {
                Column(Modifier.padding(8.dp)) {
                    Text(c.entry.name, fontSize = 16.sp, fontWeight = FontWeight.SemiBold,
                        maxLines = 1, overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.padding(start = 10.dp, top = 8.dp, end = 10.dp))
                    Text(file, fontSize = 11.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(start = 10.dp, end = 10.dp, bottom = 5.dp))
                    HorizontalDivider()
                    @Composable fun option(
                        title: String,
                        modifier: Modifier,
                        onLongPress: (() -> Unit)? = null,
                        action: () -> Unit,
                    ) {
                        val img = when (title) {
                            copyLabel, "复制路径" -> Icons.TwoTone.ContentCopy
                            moveLabel -> Icons.TwoTone.DriveFileMove
                            "删除" -> Icons.TwoTone.Delete
                            "重命名" -> Icons.TwoTone.Edit
                            "属性", "权限" -> Icons.TwoTone.Info
                            "终端", "运行脚本" -> Icons.TwoTone.Terminal
                            "加入选择" -> Icons.TwoTone.Folder
                            else -> Icons.TwoTone.Description
                        }
                        Row(
                            modifier.height(49.dp)
                                .combinedClickable(
                                    onClick = { choice = null; action() },
                                    onLongClick = onLongPress?.let { longAction ->
                                        { choice = null; longAction() }
                                    },
                                )
                                .padding(start = 9.dp, end = 2.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Icon(img, null, modifier = Modifier.size(21.dp),
                                tint = MaterialTheme.colorScheme.onSurfaceVariant)
                            Spacer(Modifier.width(7.dp))
                            Text(title, fontSize = 13.sp, maxLines = 1,
                                overflow = TextOverflow.Ellipsis)
                        }
                    }
                    Row(Modifier.fillMaxWidth()) {
                        option(copyLabel, Modifier.weight(1f),
                            action = { operation = DualOperation("copy", c, destinationDir = state.windows[1 - c.side].path) },
                            onLongPress = { pendingTransfer = DualOperation("copy", c) })
                        option(moveLabel, Modifier.weight(1f),
                            action = { operation = DualOperation("move", c, destinationDir = state.windows[1 - c.side].path) },
                            onLongPress = { pendingTransfer = DualOperation("move", c) })
                    }
                    Row(Modifier.fillMaxWidth()) {
                        option("删除", Modifier.weight(1f)) { operation = DualOperation("delete", c) }
                        option("重命名", Modifier.weight(1f)) {
                            rename = c
                            val n = c.entry.name
                            renameText = TextFieldValue(n, selection = TextRange(0,
                                n.lastIndexOf('.').takeIf { it > 0 } ?: n.length))
                        }
                    }
                    Row(Modifier.fillMaxWidth()) {
                        option("编辑", Modifier.weight(1f)) { openEditor(file) }
                        option("属性", Modifier.weight(1f)) {
                            properties = "读取中…"
                            scope.launch { properties = cmd(cli,
                                "/data/adb/ksu/bin/busybox stat -- " + qs(file) +
                                "; ls -ldZ " + qs(file)).value }
                        }
                    }
                    Row(Modifier.fillMaxWidth()) {
                        option("十六进制预览", Modifier.weight(1f)) {
                            properties = "读取中…"
                            scope.launch {
                                properties = cmd(cli,
                                    "/data/adb/ksu/bin/busybox hexdump -C -n 512 -- " + qs(file)).value
                            }
                        }
                        option("加入选择", Modifier.weight(1f)) {
                            state.windows[c.side].choose(c.entry)
                        }
                    }
                    Row(Modifier.fillMaxWidth()) {
                        option("复制路径", Modifier.weight(1f)) {
                            clipboard.setText(AnnotatedString(file))
                            message = "已复制完整路径"
                        }
                        option("权限", Modifier.weight(1f)) {
                            chmodTarget = c
                            chmodMode = "0644"
                        }
                    }
                    Row(Modifier.fillMaxWidth()) {
                        option("终端", Modifier.weight(1f)) { openTerminal(if (c.entry.folder) file else c.directory) }
                        option(if (c.entry.name.endsWith(".sh", true)) "运行脚本" else "打开", Modifier.weight(1f)) {
                            if (c.entry.name.endsWith(".sh", true)) runScript(file)
                            else if (c.entry.folder) state.windows[c.side].navigate(file)
                            else if (fileExtension(c.entry.name) == "apk") installApk(file)
                            else openEditor(file)
                        }
                    }
                }
            }
        }
    }
    operation?.takeIf { it.kind == "delete" || conflictCount != null }?.let { o ->
        val source = joined(o.from.directory, o.from.entry.name)
        val dest = joined(o.destinationDir, o.from.entry.name)
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
                        Text(stringResource(R.string.dn_files_conflict_count, conflictCount ?: 0),
                            style = MaterialTheme.typography.labelMedium)
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
    rename?.let { c ->
        AlertDialog(onDismissRequest = { rename = null }, title = { Text("重命名") },
            text = { OutlinedTextField(value = renameText, onValueChange = { renameText = it }, singleLine = true) },
            confirmButton = { TextButton(onClick = {
                val name = renameText.text
                if (name.isNotEmpty() && name != "." && name != ".." && '/' !in name && '\u0000' !in name) {
                    val old = joined(c.directory, c.entry.name)
                    val new = joined(c.directory, name)
                    scope.launch {
                        val result = cmd(cli, "if [ -e " + qs(new) + " ] || [ -L " + qs(new) + " ]; then exit 73; fi; /data/adb/ksu/bin/busybox mv -nT -- " +
                            qs(old) + " " + qs(new))
                        message = if (result.ok) "重命名完成" else result.value.ifBlank { "失败" }
                        state.windows[c.side].refresh()
                    }
                } else message = "无效文件名"
                rename = null
            }) { Text("确定") } },
            dismissButton = { TextButton(onClick = { rename = null }) { Text("取消") } })
    }
    if (addressDialog) {
        AlertDialog(onDismissRequest = { addressDialog = false }, title = { Text("路径跳转") },
            text = { OutlinedTextField(value = address, onValueChange = { address = it }, singleLine = true) },
            confirmButton = { TextButton(onClick = {
                if (address.startsWith("/")) current.navigate(address) else message = "请输入绝对路径"
                addressDialog = false
            }) { Text("跳转") } },
            dismissButton = { TextButton(onClick = { addressDialog = false }) { Text("取消") } })
    }
    if (newDialog) {
        AlertDialog(onDismissRequest = { newDialog = false }, title = { Text("新建文件或文件夹") },
            text = { OutlinedTextField(value = newName, onValueChange = { newName = it }, singleLine = true) },
            confirmButton = {
                Row {
                    listOf("文件", "文件夹").forEach { type ->
                        TextButton(onClick = {
                            val name = newName
                            if (name.isNotEmpty() && name != "." && name != ".." && '/' !in name && '\u0000' !in name) {
                                val path = joined(current.path, name)
                                scope.launch {
                                    val r = cmd(cli, if (type == "文件")
                                        "if [ -e " + qs(path) + " ] || [ -L " + qs(path) + " ]; then exit 73; fi; set -C; : > " + qs(path)
                                        else "mkdir -- " + qs(path))
                                    message = if (r.ok) "创建完成" else r.value.ifBlank { "失败" }
                                    current.refresh()
                                }
                            } else message = "无效文件名"
                            newDialog = false
                        }) { Text(type) }
                    }
                }
            },
            dismissButton = { TextButton(onClick = { newDialog = false }) { Text("取消") } })
    }
    properties?.let { data ->
        AlertDialog(
            onDismissRequest = { properties = null },
            title = { Text("文件详情") },
            text = {
                SelectionContainer {
                    Column(Modifier.heightIn(max = 360.dp).verticalScroll(rememberScrollState())) {
                        Text(data, style = MaterialTheme.typography.bodySmall.copy(
                            fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace))
                    }
                }
            },
            confirmButton = { TextButton(onClick = { properties = null }) { Text("完成") } },
        )
    }
    chmodTarget?.let { entry ->
        val full = joined(entry.directory, entry.entry.name)
        AlertDialog(
            onDismissRequest = { chmodTarget = null },
            title = { Text("修改文件权限") },
            text = {
                Column {
                    Text(full, style = MaterialTheme.typography.bodySmall,
                        maxLines = 2, overflow = TextOverflow.Ellipsis)
                    Spacer(Modifier.height(7.dp))
                    OutlinedTextField(
                        value = chmodMode, onValueChange = { chmodMode = it },
                        singleLine = true, label = { Text("八进制权限，例如 0644 / 0755") },
                    )
                    Text("仅修改选中文件；不递归修改子目录。",
                        style = MaterialTheme.typography.labelSmall)
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    val mode = chmodMode
                    if (!mode.matches(Regex("[0-7]{3,4}"))) {
                        message = "权限格式必须是 3～4 位八进制数字"
                    } else {
                        scope.launch {
                            val result = cmd(cli,
                                "if [ -L " + qs(full) + " ]; then echo '不支持修改符号链接权限'; exit 80; fi; " +
                                "/data/adb/ksu/bin/busybox chmod " + mode + " -- " + qs(full))
                            message = if (result.ok) "权限已修改" else
                                result.value.ifBlank { "修改失败" }
                            state.windows[entry.side].refresh()
                        }
                    }
                    chmodTarget = null
                }) { Text("确定") }
            },
            dismissButton = { TextButton(onClick = { chmodTarget = null }) { Text("取消") } },
        )
    }
    if (favoritesDialog) {
        AlertDialog(
            onDismissRequest = { favoritesDialog = false },
            title = { Text("目录书签") },
            text = {
                Column(Modifier.heightIn(max = 360.dp).verticalScroll(rememberScrollState())) {
                    if (state.bookmarks.isEmpty()) {
                        Text("暂无书签。在文件页右上角可收藏当前目录。")
                    }
                    state.bookmarks.sorted().forEach { saved ->
                        Row(Modifier.fillMaxWidth().heightIn(min = 44.dp)
                            .clickable {
                                current.navigate(saved)
                                favoritesDialog = false
                            }, verticalAlignment = Alignment.CenterVertically) {
                            Text(saved, modifier = Modifier.weight(1f), maxLines = 2,
                                style = MaterialTheme.typography.bodySmall)
                            IconButton(onClick = { state.toggleBookmark(saved) },
                                modifier = Modifier.size(36.dp)) {
                                Icon(Icons.TwoTone.Delete, "删除书签")
                            }
                        }
                    }
                }
            },
            confirmButton = { TextButton(onClick = { favoritesDialog = false }) { Text("关闭") } },
        )
    }
}

@Composable
private fun DnFileList(
    pane: DnFileWindow, cli: BackendCliRepository, active: Boolean, modifier: Modifier,
    onTap: (DualEntry) -> Unit, onMenu: (DualEntry) -> Unit,
    onSelect: (DualEntry, Boolean) -> Unit, onActivate: () -> Unit
) {
    LaunchedEffect(pane.path, pane.sortMode, pane.reversed) {
        if (pane.restoring && pane.files.isNotEmpty()) {
            val mark = pane.saved()
            withFrameNanos { }
            if (mark != null) {
                val index = mark.name?.let { name ->
                    pane.visible().indexOfFirst { it.name == name }.takeIf { it >= 0 }?.plus(1)
                } ?: mark.index
                pane.scroll.scrollToItem(index.coerceIn(0, pane.visible().size), mark.offset.coerceAtLeast(0))
            }
        }
    }
    LaunchedEffect(pane.path, pane.refreshId) {
        val path = pane.path
        val id = pane.refreshId
        pane.loading = true
        pane.error = ""
        try {
            val r = readDirectory(cli, path)
            if (id != pane.refreshId || path != pane.path) return@LaunchedEffect
            if (!r.ok) pane.error = r.value.ifBlank { "无法访问目录" }
            else {
                val files = parseEntries(r.value)
                pane.files = files
                pane.rememberFiles(path, files)
                if (pane.restoring) {
                    val mark = pane.saved()
                    withFrameNanos { }
                    if (mark != null) {
                        val idx = mark.name?.let { n -> pane.visible().indexOfFirst { it.name == n }.takeIf { it >= 0 }?.plus(1) }
                            ?: mark.index
                        pane.scroll.scrollToItem(idx.coerceIn(0, pane.visible().size), mark.offset.coerceAtLeast(0))
                    } else pane.scroll.scrollToItem(0)
                    pane.restoring = false
                }
            }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            if (id == pane.refreshId && path == pane.path) pane.error = e.message ?: "读取失败"
        } finally {
            if (id == pane.refreshId && path == pane.path) pane.loading = false
        }
    }
    LaunchedEffect(pane) {
        snapshotFlow { pane.scroll.firstVisibleItemIndex to pane.scroll.firstVisibleItemScrollOffset }
            .collectLatest {
                delay(300)
                pane.capture()
            }
    }
    DisposableEffect(pane) { onDispose { pane.capture() } }
    val shown = pane.visible()
    // Nested scroll pass-through: the user's vertical drag activates its pane,
    // but returns Offset.Zero so LazyColumn keeps the entire scroll gesture.
    val paneFocusConnection = remember(pane, onActivate) {
        object : NestedScrollConnection {
            override fun onPreScroll(available: Offset, source: NestedScrollSource): Offset {
                if (source == NestedScrollSource.UserInput && available.y != 0f) {
                    onActivate()
                }
                return Offset.Zero
            }
        }
    }
    Column(modifier.nestedScroll(paneFocusConnection)
        .background(if (active) white else pale)) {
        if (pane.error.isNotBlank()) Text(pane.error, color = Color.Red, fontSize = 11.sp, maxLines = 2)
        // Loading does not clear the existing rows or reset scroll state.
        if (pane.loading && pane.files.isEmpty())
            Text("读取中…", fontSize = 11.sp, color = grey, modifier = Modifier.padding(2.dp))
        LazyColumn(state = pane.scroll, modifier = Modifier.fillMaxSize()) {
            item(key = "parent_" + pane.path) {
                Row(Modifier.fillMaxWidth().height(40.dp).clickable {
                    onActivate()
                    pane.navigate(parentDir(pane.path))
                }.padding(horizontal = 3.dp), verticalAlignment = Alignment.CenterVertically) {
                    FolderGlyph()
                    Spacer(Modifier.width(3.dp))
                    Text("..", fontSize = 14.sp)
                }
            }
            items(shown, key = { pane.path + ":" + it.name }) { item ->
                var dragAmount = 0f
                Row(Modifier.fillMaxWidth().heightIn(min = 40.dp)
                    .background(if (item.name in pane.selectedNames) Color(0xFFDCE9FF) else Color.Transparent)
                    .pointerInput(item.name, pane.path) {
                        detectHorizontalDragGestures(
                            onHorizontalDrag = { change, delta ->
                                dragAmount += delta
                                change.consume()
                            },
                            onDragEnd = {
                                if (kotlin.math.abs(dragAmount) > 25f)
                                    onSelect(item, pane.selectedNames.isNotEmpty())
                                dragAmount = 0f
                            },
                            onDragCancel = { dragAmount = 0f },
                        )
                    }
                    .pointerInput(item.name, pane.path) {
                        detectTapGestures(
                            onTap = { onTap(item) },
                            onLongPress = { onMenu(item) },
                        )
                    }.padding(horizontal = 3.dp, vertical = 4.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    if (item.folder) FolderGlyph() else FileGlyph(item.name)
                    Spacer(Modifier.width(3.dp))
                    Column(Modifier.weight(1f)) {
                        Text(item.name, fontSize = 14.sp, lineHeight = 15.sp, color = dark,
                            maxLines = 2, overflow = TextOverflow.Ellipsis)
                        Text(dateText(item.mtime) + (if (item.folder) "" else "  " + sizeText(item.size)),
                            fontSize = 11.sp, lineHeight = 12.sp, color = grey,
                            maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                }
                HorizontalDivider(thickness = 0.3.dp, color = divider)
            }
        }
    }
}
@Composable
private fun FolderGlyph() {
    Box(Modifier.size(32.dp).background(dark, RoundedCornerShape(5.dp)),
        contentAlignment = Alignment.Center) {
        Icon(Icons.Filled.Folder, null, modifier = Modifier.size(20.dp), tint = white)
    }
}

@Composable
private fun FileGlyph(name: String) {
    val extension = fileExtension(name)
    if (extension == "apk") {
        Box(Modifier.size(32.dp).background(Color(0xFF338957), RoundedCornerShape(5.dp)),
            contentAlignment = Alignment.Center) {
            Icon(Icons.TwoTone.Android, null, modifier = Modifier.size(23.dp), tint = white)
        }
        return
    }
    val (icon, color) = when (extension) {
        "png", "jpg", "jpeg", "webp", "gif", "bmp", "svg", "heic", "avif" ->
            Icons.TwoTone.Image to Color(0xFF8C5AB6)
        "mp4", "mkv", "webm", "avi", "mov", "3gp", "ts" ->
            Icons.TwoTone.Movie to Color(0xFFB5536B)
        "mp3", "m4a", "aac", "flac", "ogg", "wav", "opus", "mid" ->
            Icons.TwoTone.Audiotrack to Color(0xFFAF713A)
        "zip", "7z", "rar", "tar", "gz", "xz", "zst", "bz2" ->
            Icons.TwoTone.Archive to Color(0xFF9A743B)
        "pdf" -> Icons.TwoTone.PictureAsPdf to Color(0xFFBB4C4C)
        "doc", "docx", "odt", "rtf", "epub" -> Icons.TwoTone.Description to Color(0xFF427CB0)
        "xls", "xlsx", "ods", "csv" -> Icons.TwoTone.TableChart to Color(0xFF39845F)
        "ppt", "pptx", "odp" -> Icons.TwoTone.Slideshow to Color(0xFFBA693F)
        "py", "js", "kt", "java", "c", "cpp", "h", "hpp", "go", "rs", "html", "css", "sql" ->
            Icons.TwoTone.Code to Color(0xFF447C88)
        "so", "elf", "bin", "exe" -> Icons.TwoTone.Memory to Color(0xFF626B78)
        else -> if (textFile(name)) Icons.TwoTone.Description to Color(0xFF427CB0)
            else Icons.TwoTone.InsertDriveFile to grey
    }
    Icon(icon, null, modifier = Modifier.size(32.dp), tint = color)
}
