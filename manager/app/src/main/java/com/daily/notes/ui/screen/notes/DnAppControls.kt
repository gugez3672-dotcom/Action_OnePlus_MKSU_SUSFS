package com.daily.notes.ui.screen.notes

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.daily.notes.R
import com.daily.notes.data.application.AppEnabledStateRepository
import com.daily.notes.data.model.AppInfo
import com.daily.notes.data.shell.BackendCliRepository
import com.daily.notes.ui.navigation3.LocalNavigator
import com.daily.notes.ui.navigation3.Route
import com.daily.notes.ui.viewmodel.SuperUserViewModel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@Composable
fun AppControlsButton(userId: Int = 0, packageName: String = "") {
    val navigator = LocalNavigator.current
    TextButton(onClick = { navigator.push(Route.AppControls(userId, packageName)) }) {
        Text(stringResource(R.string.dn_application_controls))
    }
}

@Composable
@OptIn(ExperimentalLayoutApi::class)
fun DnAppControlsScreen(initialUser: Int, packageName: String) {
    val context = LocalContext.current
    val navigator = LocalNavigator.current
    val backend = remember(context) { BackendCliRepository(context) }
    val states = remember(context) { AppEnabledStateRepository(context, backend) }
    val scope = rememberCoroutineScope()
    var user by remember { mutableIntStateOf(initialUser) }
    var selected by remember { mutableStateOf<Set<String>>(if (packageName.isEmpty()) emptySet() else setOf(packageName)) }
    val apps = SuperUserViewModel.apps.filter { !it.special && it.uid / 100000 == user }
        .distinctBy { it.packageName }.sortedBy { it.label }
    val users = SuperUserViewModel.apps.map { it.uid / 100000 }.distinct().sorted()
    var busy by remember { mutableStateOf(false) }
    var result by remember { mutableStateOf("") }
    var pending by remember { mutableStateOf<Int?>(null) }
    val labels = listOf(R.string.launch_app, R.string.force_stop_app, R.string.restart_app,
        R.string.dn_enable_apps, R.string.dn_disable_apps)
    suspend fun control(app: AppInfo, action: Int) = withContext(Dispatchers.IO) {
        val state = states.state(app.uid, app.packageName)
        check(action == 0 || action == 3 || !state.protected) { "Protected application" }
        if (action >= 3) {
            val desiredDisabled = action == 4
            if (state.disabled != desiredDisabled) states.toggle(app.uid, app.packageName)
        } else backend.withNewRootShell {
            check(isRoot) { "Root shell unavailable" }
            val name = app.packageName
            require(name.matches(Regex("[A-Za-z0-9_]+(?:\\.[A-Za-z0-9_]+)+")))
            val owner = app.uid / 100000
            if (action in 1..2) check(newJob().add("am force-stop --user $owner $name").exec().isSuccess)
            if (action == 0 || action == 2) {
                val lines = arrayListOf<String>()
                check(newJob().add("cmd package resolve-activity --brief --user $owner -a android.intent.action.MAIN -c android.intent.category.LAUNCHER $name").to(lines, null).exec().isSuccess)
                val component = lines.lastOrNull { it.startsWith("$name/") } ?: error("No launcher activity")
                val quoted = "'" + component.replace("'", "'\"'\"'") + "'"
                check(newJob().add("am start --user $owner -n $quoted").exec().isSuccess)
            }
        }
    }
    pending?.let { action ->
        AlertDialog(onDismissRequest = { pending = null }, title = { Text(stringResource(labels[action])) },
            text = { Text("${selected.size} · User $user") },
            confirmButton = { TextButton(onClick = {
                pending = null
                busy = true
                val targets = apps.filter { it.packageName in selected }
                scope.launch {
                    try {
                        val failures = mutableListOf<String>()
                        for (app in targets) runCatching { control(app, action) }
                            .onFailure { failures += "${app.packageName}: ${it.message}" }
                        result = "${targets.size - failures.size}/${targets.size}\n" + failures.joinToString("\n")
                    } finally { busy = false }
                }
            }) { Text(stringResource(android.R.string.ok)) } },
            dismissButton = { TextButton(onClick = { pending = null }) { Text(stringResource(android.R.string.cancel)) } })
    }
    Scaffold(topBar = {
        TopAppBar(title = { Text(stringResource(R.string.dn_application_controls)) }, navigationIcon = {
            TextButton(onClick = { navigator.pop() }) { Text(stringResource(android.R.string.cancel)) }
        })
    }) { padding ->
        Column(Modifier.padding(padding).padding(horizontal = 16.dp)) {
            Row {
                users.forEach { id -> TextButton(enabled = !busy, onClick = { user = id; selected = emptySet() }) { Text("User $id") } }
            }
            Row {
                TextButton(enabled = !busy, onClick = { selected = apps.map { it.packageName }.toSet() }) { Text(stringResource(R.string.dn_select_all)) }
                TextButton(enabled = !busy, onClick = { selected = emptySet() }) { Text(stringResource(R.string.dn_select_none)) }
            }
            FlowRow {
                labels.forEachIndexed { index, label ->
                    TextButton(enabled = selected.isNotEmpty() && !busy, onClick = { pending = index }) { Text(stringResource(label)) }
                }
            }
            if (busy) LinearProgressIndicator(Modifier.fillMaxWidth())
            if (result.isNotEmpty()) Text(result)
            LazyColumn {
                items(apps, key = { it.packageName }) { app ->
                    Row(Modifier.fillMaxWidth().clickable(enabled = !busy) {
                        selected = if (app.packageName in selected) selected - app.packageName else selected + app.packageName
                    }) {
                        Checkbox(checked = app.packageName in selected, onCheckedChange = null)
                        Column { Text(app.label); Text("${app.packageName} · ${app.uid}", style = MaterialTheme.typography.bodySmall) }
                    }
                }
            }
        }
    }
}
