package com.daily.notes.ui.screen.notes

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.daily.notes.R
import com.daily.notes.data.susfs.OfficialFsConfig
import com.daily.notes.ui.navigation3.LocalNavigator
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun DnFilesystemScreen() {
    val context = LocalContext.current
    val navigator = LocalNavigator.current
    val repository = remember(context) { OfficialFsConfig(context) }
    val scope = rememberCoroutineScope()
    var config by remember { mutableStateOf(OfficialFsConfig.defaults()) }
    var loaded by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("") }
    var status by remember { mutableStateOf("") }
    var tab by rememberSaveable { mutableIntStateOf(0) }
    var adding by remember { mutableStateOf(false) }
    var path by remember { mutableStateOf("") }
    var redirected by remember { mutableStateOf("") }
    var loop by remember { mutableStateOf(false) }
    var mode by remember { mutableIntStateOf(0) }
    var scheme by remember { mutableIntStateOf(2) }
    val statFields = listOf("ino", "dev", "nlink", "size", "atime", "atime_nsec", "mtime", "mtime_nsec", "ctime", "ctime_nsec", "blocks", "blksize")
    var statValues by remember { mutableStateOf(statFields.associateWith { "" }) }
    val sections = listOf("状态", "标准功能", "隐藏路径", "隐藏映射", "统计信息", "打开重定向")
    fun edit(change: (JSONObject) -> Unit) {
        val next = JSONObject(config.toString())
        change(next)
        config = next
    }
    suspend fun refresh() {
        loaded = false
        try {
            config = repository.load()
            loaded = true
            status = repository.status()
        } catch (failure: Exception) { message = failure.message.orEmpty() }
    }
    LaunchedEffect(Unit) { refresh() }
    val exporter = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { uri ->
        if (uri != null) runCatching {
            context.contentResolver.openOutputStream(uri, "wt")!!.use { it.write(config.toString(2).toByteArray()) }
        }.onFailure { message = it.message.orEmpty() }
    }
    val importer = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) runCatching {
            val data = ByteArrayOutputStream()
            context.contentResolver.openInputStream(uri)!!.use { input ->
                val buffer = ByteArray(8192)
                while (true) {
                    val count = input.read(buffer)
                    if (count < 0) break
                    require(data.size() + count <= 1024 * 1024) { "Configuration exceeds 1 MiB" }
                    data.write(buffer, 0, count)
                }
            }
            val candidate = JSONObject(data.toString("UTF-8"))
            OfficialFsConfig.compile(candidate)
            config = candidate
        }.onFailure { message = it.message.orEmpty() }
    }
    fun arrayKey(): String = when (tab) { 2 -> "sus_path"; 3 -> "sus_map"; 4 -> "sus_kstat"; else -> "open_redirect" }
    if (adding) {
        AlertDialog(onDismissRequest = { adding = false }, title = { Text(sections[tab]) }, text = {
            Column(Modifier.heightIn(max = 480.dp).verticalScroll(rememberScrollState())) {
                OutlinedTextField(path, { path = it }, label = { Text("绝对路径") })
                if (tab == 2) Row { Text("路径循环"); Switch(loop, { loop = it }) }
                if (tab == 4) {
                    Row { listOf("Normal", "FullClone", "Statically").forEachIndexed { index, label ->
                        TextButton(onClick = { mode = index }) { Text(if (mode == index) "✓ $label" else label) }
                    } }
                    if (mode == 2) statFields.forEach { field ->
                        OutlinedTextField(statValues.getValue(field), { value -> statValues = statValues + (field to value) }, label = { Text("$field (空=default)") })
                    }
                }
                if (tab == 5) {
                    OutlinedTextField(redirected, { redirected = it }, label = { Text("重定向路径") })
                    FlowRow { listOf("NonApp", "RootExceptSu", "NonSu", "UnmountedApp", "Unmounted").forEachIndexed { index, label ->
                        TextButton(onClick = { scheme = index }) { Text(if (scheme == index) "✓ $label" else label) }
                    } }
                }
            }
        }, confirmButton = {
            TextButton(onClick = {
                runCatching {
                    val next = JSONObject(config.toString())
                    val entry: Any = when (tab) {
                        2 -> JSONObject().put("path", path).put("is_loop", loop)
                        3 -> path
                        4 -> JSONObject().put("path", path).put("spoof_type", listOf("Normal", "FullClone", "Statically")[mode]).put("statically", JSONObject().also { values ->
                            statValues.forEach { (field, value) -> values.put(field, if (value.isEmpty()) JSONObject.NULL else value) }
                        })
                        else -> JSONObject().put("target_path", path).put("redirected_path", redirected)
                            .put("uid_scheme", listOf("NonApp", "RootExceptSu", "NonSu", "UnmountedApp", "Unmounted")[scheme])
                    }
                    next.getJSONArray(arrayKey()).put(entry)
                    OfficialFsConfig.compile(next)
                    config = next
                    adding = false
                }.onFailure { message = it.message.orEmpty() }
            }) { Text(stringResource(android.R.string.ok)) }
        }, dismissButton = { TextButton(onClick = { adding = false }) { Text(stringResource(android.R.string.cancel)) } })
    }
    Scaffold(topBar = {
        TopAppBar(title = { Text("SUSFS") }, navigationIcon = {
            TextButton(onClick = { navigator.pop() }) { Text(stringResource(android.R.string.cancel)) }
        })
    }) { padding ->
        Column(Modifier.padding(padding).padding(12.dp)) {
            ScrollableTabRow(tab) { sections.forEachIndexed { index, label -> Tab(selected = tab == index, onClick = { tab = index }, text = { Text(label) }) } }
            if (busy) LinearProgressIndicator(Modifier.fillMaxWidth())
            if (message.isNotEmpty()) Text(message, color = MaterialTheme.colorScheme.primary)
            FlowRow {
                TextButton(enabled = !busy, onClick = { scope.launch { refresh() } }) { Text("刷新") }
                TextButton(enabled = loaded && !busy, onClick = { importer.launch(arrayOf("application/json", "text/*")) }) { Text("导入") }
                TextButton(enabled = loaded && !busy, onClick = { exporter.launch("DailyNotes-filesystem.json") }) { Text("导出") }
                TextButton(enabled = loaded && !busy, onClick = { config = OfficialFsConfig.defaults() }) { Text("编辑为默认配置") }
                TextButton(enabled = loaded && !busy, onClick = {
                    busy = true
                    val snapshot = JSONObject(config.toString())
                    scope.launch {
                        var saved = false
                        try {
                            repository.save(snapshot)
                            saved = true
                            repository.applyNow(snapshot)
                            message = "已保存并应用可即时生效的项目；统计信息捕获、删除及完全停用需重启。"
                        } catch (failure: Exception) {
                            message = (if (saved) "已保存；即时应用未完成：" else "未保存：") + failure.message
                        } finally { busy = false }
                    }
                }) { Text("保存并应用") }
            }
            Column(Modifier.weight(1f).verticalScroll(rememberScrollState())) {
                when (tab) {
                    0 -> { Text(status); Text("配置先在挂载前采集统计信息，元模块挂载后更新。这里使用通用启动脚本，不新增模块。") }
                    1 -> {
                        listOf("enabled" to "开机应用配置", "avc_log_spoofing" to "AVC 日志处理", "hide_sus_mnts_for_non_su_procs" to "非 SU 进程挂载隐藏").forEach { (key, label) ->
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                Text(label)
                                Switch(config.getBoolean(key), { value -> edit { it.put(key, value) } }, enabled = loaded && !busy)
                            }
                        }
                        Text("内核未编译日志功能，日志保持关闭。")
                        listOf("release", "version").forEach { field ->
                            OutlinedTextField(config.getJSONObject("uname").getString(field), { value -> edit { it.getJSONObject("uname").put(field, value) } }, label = { Text("uname $field") })
                        }
                        OutlinedTextField(config.getString("cmdline_or_bootconfig"), { value -> edit { it.put("cmdline_or_bootconfig", value) } }, label = { Text("bootconfig / cmdline 文件路径") })
                        OutlinedTextField(config.optString("priority_packages", ""), { value -> edit { it.put("priority_packages", value) } }, label = { Text("优先级 UID 过滤包名（逗号分隔）") })
                    }
                    else -> {
                        val key = arrayKey()
                        val entries = config.getJSONArray(key)
                        TextButton(enabled = loaded && !busy, onClick = { path = ""; redirected = ""; adding = true }) { Text("添加") }
                        for (i in 0 until entries.length()) Row(Modifier.fillMaxWidth()) {
                            Text(entries.get(i).toString(), Modifier.weight(1f))
                            TextButton(enabled = !busy, onClick = { edit { it.getJSONArray(key).remove(i) } }) { Text("删除") }
                        }
                    }
                }
            }
        }
    }
}
