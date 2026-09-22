from pathlib import Path

dest = Path("source/manager/app/src/main/java/com/resukisu/resukisu/ui/screen/BottomBarDestination.kt")
t = dest.read_text()
if "Icons.TwoTone.Build" not in t:
    t = t.replace(
        "import androidx.compose.material.icons.twotone.AdminPanelSettings\n",
        "import androidx.compose.material.icons.twotone.AdminPanelSettings\nimport androidx.compose.material.icons.twotone.Build\n",
        1,
    )
if "import com.resukisu.resukisu.ui.screen.main.ToolsPage" not in t:
    t = t.replace(
        "import com.resukisu.resukisu.ui.screen.main.SuperUserPage\n",
        "import com.resukisu.resukisu.ui.screen.main.SuperUserPage\nimport com.resukisu.resukisu.ui.screen.main.ToolsPage\n",
        1,
    )
t = t.replace("        R.string.superuser,\n", "        R.string.dn_authorization,\n", 1)

module_block = """    Module(
        { bottomPadding -> ModulePage(bottomPadding) },
        R.string.module,
        Icons.TwoTone.Extension,
        Icons.TwoTone.Extension,
        true
    ),
"""
tools_block = """    Tools(
        { bottomPadding -> ToolsPage(bottomPadding) },
        R.string.dn_tools,
        Icons.TwoTone.Build,
        Icons.TwoTone.Build,
        true
    ),
"""
if "    Tools(" not in t:
    if module_block not in t:
        raise SystemExit("Module destination block not found")
    t = t.replace(module_block, module_block + tools_block, 1)
dest.write_text(t)

nav = Path("source/manager/app/src/main/java/com/resukisu/resukisu/ui/activity/component/NavigationBar.kt")
t = nav.read_text()
t = t.replace(
    "                        modifier = Modifier.defaultMinSize(minWidth = 76.dp)\n",
    "                        modifier = Modifier.defaultMinSize(minWidth = if (destinations.size >= 5) 62.dp else 76.dp)\n",
    1,
)
nav.write_text(t)

for path, auth, tools in [
    ("source/manager/app/src/main/res/values/strings.xml", "Authorization", "Tools"),
    ("source/manager/app/src/main/res/values-zh-rCN/strings.xml", "授权", "工具"),
]:
    p = Path(path)
    text = p.read_text()
    if 'name="dn_authorization"' not in text:
        text = text.replace(
            "</resources>",
            '    <string name="dn_authorization">' + auth + '</string>\n'
            '    <string name="dn_tools">' + tools + '</string>\n'
            "</resources>",
            1,
        )
    p.write_text(text)

tool_page = Path("source/manager/app/src/main/java/com/resukisu/resukisu/ui/screen/main/ToolsPage.kt")
tool_page.write_text(r'''package com.resukisu.resukisu.ui.screen.main

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.weight
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.resukisu.resukisu.data.shell.KsuCliRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.koin.compose.koinInject

private data class RootEntry(val name: String, val directory: Boolean)
private data class RootRun(val text: String, val cwd: String? = null)

private fun shellQuote(value: String): String =
    "'" + value.replace("'", "'\"'\"'") + "'"

private fun joinPath(base: String, name: String): String =
    if (base == "/") "/" + name else base + "/" + name

private fun parentPath(path: String): String {
    if (path == "/") return "/"
    val clean = path.trimEnd('/')
    val cut = clean.lastIndexOf('/')
    return if (cut <= 0) "/" else clean.substring(0, cut)
}

@Composable
fun ToolsPage(bottomPadding: Dp) {
    val ksuCli: KsuCliRepository = koinInject()
    val scope = rememberCoroutineScope()

    var tab by rememberSaveable { mutableIntStateOf(0) }
    var terminalCwd by rememberSaveable { mutableStateOf("/") }
    var terminalInput by rememberSaveable { mutableStateOf("") }
    var terminalOutput by remember { mutableStateOf("Root Terminal\n$ id\nuid=0(root)\n") }
    var terminalBusy by remember { mutableStateOf(false) }

    var currentPath by rememberSaveable { mutableStateOf("/") }
    var entries by remember { mutableStateOf<List<RootEntry>>(emptyList()) }
    var fileBusy by remember { mutableStateOf(false) }
    var fileMessage by remember { mutableStateOf("") }

    var scriptPath by rememberSaveable { mutableStateOf("/data/local/tmp/") }
    var scriptOutput by remember { mutableStateOf("") }
    var scriptBusy by remember { mutableStateOf(false) }

    suspend fun execRoot(command: String, cwd: String = "/"): RootRun =
        withContext(Dispatchers.IO) {
            val stdout = ArrayList<String>()
            val stderr = ArrayList<String>()
            val marker = "__DN_PWD__"
            val wrapped = "cd " + shellQuote(cwd) +
                " 2>/dev/null || cd /; " + command +
                "\nprintf '\\n" + marker + "'; pwd"
            val result = ksuCli.withNewRootShell(globalMnt = true) {
                newJob().add(wrapped).to(stdout, stderr).exec()
            }
            val pwdLine = stdout.lastOrNull { it.startsWith(marker) }
            val cleanOut = stdout.filterNot { it.startsWith(marker) }
            val body = buildString {
                if (cleanOut.isNotEmpty()) append(cleanOut.joinToString("\n"))
                if (stderr.isNotEmpty()) {
                    if (isNotEmpty()) append('\n')
                    append(stderr.joinToString("\n"))
                }
                if (!result.isSuccess) {
                    if (isNotEmpty()) append('\n')
                    append("[exit: failed]")
                }
            }
            RootRun(
                text = body,
                cwd = pwdLine?.removePrefix(marker)?.trim()?.takeIf { it.isNotEmpty() },
            )
        }

    suspend fun listRoot(path: String): List<RootEntry> =
        withContext(Dispatchers.IO) {
            val stdout = ArrayList<String>()
            val stderr = ArrayList<String>()
            val cmd = "P=" + shellQuote(path) + """
for f in "$P"/* "$P"/.[!.]* "$P"/..?*; do
  [ -e "$f" ] || [ -L "$f" ] || continue
  if [ -d "$f" ]; then t=D; else t=F; fi
  n=$(basename "$f")
  printf '%s\t%s\n' "$t" "$n"
done
""".trimIndent()
            ksuCli.withNewRootShell(globalMnt = true) {
                newJob().add(cmd).to(stdout, stderr).exec()
            }
            stdout.mapNotNull { line ->
                val parts = line.split('\t', limit = 2)
                if (parts.size != 2) null else RootEntry(parts[1], parts[0] == "D")
            }.distinctBy { it.name }
                .sortedWith(compareBy<RootEntry>({ !it.directory }, { it.name.lowercase() }))
        }

    fun runTerminal() {
        val command = terminalInput.trim()
        if (command.isEmpty() || terminalBusy) return
        terminalInput = ""
        terminalBusy = true
        scope.launch {
            val oldCwd = terminalCwd
            val run = execRoot(command, oldCwd)
            if (run.cwd != null) terminalCwd = run.cwd
            terminalOutput += "\n" + oldCwd + " # " + command
            if (run.text.isNotEmpty()) terminalOutput += "\n" + run.text
            terminalBusy = false
        }
    }

    fun runScript(path: String, openTerminal: Boolean) {
        if (path.isBlank()) return
        if (openTerminal) {
            terminalBusy = true
            scope.launch {
                val parent = parentPath(path)
                val run = execRoot("/system/bin/sh " + shellQuote(path), parent)
                terminalCwd = run.cwd ?: parent
                terminalOutput += "\n" + parent + " # sh " + shellQuote(path)
                if (run.text.isNotEmpty()) terminalOutput += "\n" + run.text
                terminalBusy = false
                tab = 0
            }
        } else {
            scriptBusy = true
            scriptOutput = ""
            scope.launch {
                val run = execRoot("/system/bin/sh " + shellQuote(path), parentPath(path))
                scriptOutput = run.text.ifEmpty { "[执行完成，无输出]" }
                scriptBusy = false
            }
        }
    }

    LaunchedEffect(tab, currentPath) {
        if (tab == 1) {
            fileBusy = true
            fileMessage = ""
            runCatching { listRoot(currentPath) }
                .onSuccess { entries = it }
                .onFailure { fileMessage = it.message ?: "读取目录失败" }
            fileBusy = false
        }
    }

    Scaffold(containerColor = Color.Transparent) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(top = innerPadding.calculateTopPadding())
                .padding(horizontal = 16.dp)
                .padding(bottom = bottomPadding + 8.dp),
        ) {
            Text(
                text = "工具",
                style = MaterialTheme.typography.headlineLarge,
                modifier = Modifier.padding(top = 12.dp, bottom = 12.dp),
            )

            TabRow(selectedTabIndex = tab) {
                listOf("终端", "文件", "脚本").forEachIndexed { index, title ->
                    Tab(
                        selected = tab == index,
                        onClick = { tab = index },
                        text = { Text(title) },
                    )
                }
            }

            Spacer(Modifier.height(12.dp))

            when (tab) {
                0 -> {
                    Text("Root · " + terminalCwd, style = MaterialTheme.typography.titleMedium)
                    Spacer(Modifier.height(8.dp))
                    LazyColumn(modifier = Modifier.fillMaxWidth().weight(1f)) {
                        item { Text(terminalOutput, style = MaterialTheme.typography.bodyMedium) }
                    }
                    OutlinedTextField(
                        value = terminalInput,
                        onValueChange = { terminalInput = it },
                        label = { Text(if (terminalBusy) "执行中…" else "Root 命令") },
                        modifier = Modifier.fillMaxWidth(),
                        enabled = !terminalBusy,
                        maxLines = 4,
                    )
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        Button(
                            onClick = { runTerminal() },
                            enabled = !terminalBusy && terminalInput.isNotBlank(),
                        ) { Text("执行") }
                        OutlinedButton(
                            onClick = { terminalOutput = "Root Terminal\n" },
                            enabled = !terminalBusy,
                        ) { Text("清屏") }
                        OutlinedButton(
                            onClick = { terminalInput = "id; pwd; mount | head -n 20" },
                            enabled = !terminalBusy,
                        ) { Text("示例") }
                    }
                }

                1 -> {
                    Text(currentPath, style = MaterialTheme.typography.titleMedium)
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        OutlinedButton(
                            onClick = { currentPath = parentPath(currentPath) },
                            enabled = currentPath != "/" && !fileBusy,
                        ) { Text("上级") }
                        OutlinedButton(
                            onClick = {
                                scope.launch {
                                    fileBusy = true
                                    entries = listRoot(currentPath)
                                    fileBusy = false
                                }
                            },
                            enabled = !fileBusy,
                        ) { Text("刷新") }
                        OutlinedButton(
                            onClick = {
                                terminalCwd = currentPath
                                tab = 0
                            },
                        ) { Text("终端") }
                    }

                    if (fileMessage.isNotEmpty()) {
                        Text(fileMessage, color = MaterialTheme.colorScheme.error)
                    }

                    LazyColumn(modifier = Modifier.fillMaxWidth().weight(1f)) {
                        items(entries, key = { (if (it.directory) "D:" else "F:") + it.name }) { entry ->
                            val fullPath = joinPath(currentPath, entry.name)
                            Row(
                                modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp),
                                horizontalArrangement = Arrangement.SpaceBetween,
                            ) {
                                TextButton(
                                    onClick = {
                                        if (entry.directory) {
                                            currentPath = fullPath
                                        } else {
                                            scriptPath = fullPath
                                            tab = 2
                                        }
                                    },
                                    modifier = Modifier.weight(1f),
                                ) {
                                    Text(
                                        (if (entry.directory) "DIR  " else "FILE  ") + entry.name,
                                        modifier = Modifier.fillMaxWidth(),
                                    )
                                }
                                if (!entry.directory && entry.name.endsWith(".sh", ignoreCase = true)) {
                                    TextButton(onClick = { runScript(fullPath, true) }) {
                                        Text("Root执行")
                                    }
                                }
                            }
                            HorizontalDivider()
                        }
                    }
                }

                else -> {
                    Text("Root 脚本执行", style = MaterialTheme.typography.titleMedium)
                    Spacer(Modifier.height(8.dp))
                    OutlinedTextField(
                        value = scriptPath,
                        onValueChange = { scriptPath = it },
                        label = { Text("SH 文件绝对路径") },
                        modifier = Modifier.fillMaxWidth(),
                        enabled = !scriptBusy,
                        singleLine = true,
                    )
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        Button(
                            onClick = { runScript(scriptPath.trim(), false) },
                            enabled = scriptPath.isNotBlank() && !scriptBusy,
                        ) { Text(if (scriptBusy) "执行中…" else "Root执行") }
                        OutlinedButton(
                            onClick = {
                                currentPath = parentPath(scriptPath.trim().ifEmpty { "/" })
                                tab = 1
                            },
                            enabled = !scriptBusy,
                        ) { Text("打开目录") }
                    }
                    Text(
                        "默认使用 /system/bin/sh，不依赖 Termux、MT 或外部终端。",
                        style = MaterialTheme.typography.bodySmall,
                    )
                    Spacer(Modifier.height(12.dp))
                    LazyColumn(modifier = Modifier.fillMaxWidth().weight(1f)) {
                        item { Text(scriptOutput, style = MaterialTheme.typography.bodyMedium) }
                    }
                }
            }
        }
    }
}
''')

assert "Tools(" in dest.read_text()
assert "R.string.dn_authorization" in dest.read_text()
assert "fun ToolsPage(" in tool_page.read_text()
assert "withNewRootShell(globalMnt = true)" in tool_page.read_text()
assert "/system/bin/sh" in tool_page.read_text()
