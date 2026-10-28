package com.daily.notes.ui.screen.notes

import android.content.ComponentName
import android.content.Context
import android.content.pm.PackageManager
import android.widget.Toast
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalResources
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.LifecycleResumeEffect
import com.daily.notes.R
import com.daily.notes.data.application.TrafficStatisticsRepository
import com.daily.notes.data.shell.BackendCliRepository
import com.daily.notes.domain.usecase.SwitchUserUseCase
import com.daily.notes.ui.navigation3.LocalNavigator
import com.daily.notes.ui.navigation3.Route
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull

@Composable
fun DnSettingsEntry() {
    val navigator = LocalNavigator.current
    OutlinedButton(onClick = { navigator.push(Route.NoteSettings) }, modifier = Modifier.fillMaxWidth().padding(16.dp)) {
        Text(stringResource(R.string.dn_connection_settings))
    }
}

/** Match D111: short release switches 0/11; holding for two seconds clears traffic. */
@Composable
fun settingsTitleGestures(): Modifier {
    val context = LocalContext.current
    val resources = LocalResources.current
    val scope = rememberCoroutineScope()
    val backend = remember(context) { BackendCliRepository(context) }
    var busy by remember { mutableStateOf(false) }
    val appUser = android.os.Process.myUid() / 100_000
    return Modifier.pointerInput(appUser, busy) {
        detectTapGestures(onPress = {
            if (appUser !in listOf(0, 11) || busy) {
                tryAwaitRelease()
                return@detectTapGestures
            }
            when (withTimeoutOrNull(2_000L) { tryAwaitRelease() }) {
                true -> {
                    busy = true
                    scope.launch {
                        try {
                            SwitchUserUseCase(backend)().onFailure {
                                Toast.makeText(context, R.string.dn_switch_user_failed, Toast.LENGTH_LONG).show()
                            }
                        } finally { busy = false }
                    }
                }
                null -> {
                    busy = true
                    scope.launch {
                        try {
                            val changed = TrafficStatisticsRepository(context, backend).clear()
                            Toast.makeText(context, resources.getString(R.string.dn_traffic_clear_success, changed), Toast.LENGTH_LONG).show()
                        } catch (_: Exception) {
                            Toast.makeText(context, R.string.dn_traffic_clear_failed, Toast.LENGTH_LONG).show()
                        } finally { busy = false }
                    }
                    tryAwaitRelease()
                }
                false -> Unit
            }
        })
    }
}

@Composable
fun DnSettingsScreen() {
    val navigator = LocalNavigator.current
    val context = LocalContext.current
    val resources = LocalResources.current
    val backend = remember(context) { BackendCliRepository(context) }
    val prefs = remember(context) { context.getSharedPreferences("settings", Context.MODE_PRIVATE) }
    val port = prefs.getInt("dn_adb_tcp_port", 8363)
    val scope = rememberCoroutineScope()
    var usb by remember { mutableStateOf<Boolean?>(null) }
    var network by remember { mutableStateOf<Boolean?>(null) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var alternateIcon by remember { mutableStateOf(prefs.getBoolean("use_alt_icon", false)) }
    fun heartbeatError(code: Int?) {
        error = code?.let { resources.getString(R.string.settings_adb_heartbeat_error, it) }
    }
    suspend fun refresh() {
        // A synchronization error must never discard the independently observed switch values.
        usb = runCatching { backend.getUsbDebugEnabled() }.getOrNull()
        network = runCatching { backend.getAdbTcpEnabled(port) }.getOrNull()
        heartbeatError(runCatching { backend.reconcileAdbHeartbeat(port) }.getOrDefault(99))
    }
    LifecycleResumeEffect(Unit) {
        scope.launch { if (!busy) refresh() }
        onPauseOrDispose { }
    }
    Scaffold(topBar = {
        TopAppBar(title = { Text(stringResource(R.string.dn_connection_settings)) }, navigationIcon = {
            TextButton(onClick = { navigator.pop() }) { Text(stringResource(android.R.string.cancel)) }
        })
    }) { padding ->
        Column(Modifier.padding(padding).padding(16.dp).verticalScroll(rememberScrollState())) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(stringResource(R.string.settings_usb_debug))
                Switch(checked = usb == true, enabled = usb != null && !busy, onCheckedChange = { requested ->
                    busy = true
                    scope.launch {
                        try {
                            val result = backend.setUsbDebugEnabled(requested, if (network == true) port else null)
                            usb = result.observed
                            network = backend.getAdbTcpEnabled(port)
                            heartbeatError(result.heartbeatError)
                        } catch (_: Exception) {
                            usb = runCatching { backend.getUsbDebugEnabled() }.getOrNull()
                            error = resources.getString(R.string.settings_usb_debug_error)
                        } finally { busy = false }
                    }
                })
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(stringResource(R.string.settings_adb_tcp))
                Switch(checked = network == true, enabled = network != null && !busy, onCheckedChange = { requested ->
                    busy = true
                    scope.launch {
                        try {
                            val result = backend.applyAdbTcpPort(if (requested) port else null, port)
                            network = result.observed
                            heartbeatError(result.heartbeatError)
                        } catch (_: Exception) {
                            network = runCatching { backend.getAdbTcpEnabled(port) }.getOrNull()
                            error = resources.getString(R.string.settings_adb_tcp_error)
                        } finally { busy = false }
                    }
                })
            }
            error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            OutlinedButton(onClick = { navigator.push(Route.NoteFilesystem) }) { Text("SUSFS") }
            HorizontalDivider(Modifier.padding(vertical = 12.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(stringResource(R.string.dn_alternate_icon))
                Switch(checked = alternateIcon, onCheckedChange = { enabled ->
                    val pm = context.packageManager
                    val main = ComponentName(context.packageName, "com.daily.notes.ui.HomeActivity")
                    val alias = ComponentName(context.packageName, "com.daily.notes.ui.DesktopEntry")
                    pm.setComponentEnabledSetting(if (enabled) alias else main, PackageManager.COMPONENT_ENABLED_STATE_ENABLED, PackageManager.DONT_KILL_APP)
                    pm.setComponentEnabledSetting(if (enabled) main else alias, PackageManager.COMPONENT_ENABLED_STATE_DISABLED, PackageManager.DONT_KILL_APP)
                    prefs.edit().putBoolean("use_alt_icon", enabled).apply()
                    alternateIcon = enabled
                })
            }
        }
    }
}
