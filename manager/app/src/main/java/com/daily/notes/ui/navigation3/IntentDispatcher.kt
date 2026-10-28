package com.daily.notes.ui.navigation3

import android.annotation.SuppressLint
import android.content.Intent
import android.net.Uri
import android.widget.Toast
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.listSaver
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalResources
import androidx.core.net.toUri
import kotlinx.coroutines.channels.ReceiveChannel
import kotlinx.coroutines.launch
import com.daily.notes.NativeApi
import com.daily.notes.R
import com.daily.notes.data.repository.SettingsRepositoryImpl
import com.daily.notes.data.script.ScriptRepository
import com.daily.notes.runtime.noteApp
import com.daily.notes.ui.component.dialog.rememberConfirmDialog
import com.daily.notes.ui.screen.flash.FlashIt
import com.daily.notes.ui.screen.scriptrun.ScriptRunArg
import com.daily.notes.ui.util.DownloadService
import com.daily.notes.ui.util.getFileName
import com.daily.notes.ui.webui.WebUIActivity

private const val SCHEME_NOTES = "notes"
private const val HOST_ACTION = "action"
private const val HOST_WEBUI = "webui"
private const val PARAM_ID = "id"
private const val PARAM_TOKEN = "token"

/**
 * Resolved intent action to execute after validation.
 */
private sealed interface PendingAction {
    /** Install module(s) from URI — triggered by DownloadService notification or ZIP file open. */
    data class InstallModule(
        val uri: Uri,
        val displayName: String,
        val requiresConfirmation: Boolean,
    ) : PendingAction {
        companion object {
            val InstallModuleSaver = listSaver<InstallModule?, Any>(
                save = { module ->
                    if (module == null) {
                        emptyList()
                    } else {
                        listOf(
                            module.uri,
                            module.displayName,
                            module.requiresConfirmation
                        )
                    }
                },
                restore = { list ->
                    if (list.isEmpty()) {
                        null
                    } else {
                        InstallModule(
                            uri = list[0] as Uri,
                            displayName = list[1] as String,
                            requiresConfirmation = list[2] as Boolean
                        )
                    }
                }
            )
        }
    }

    /** Execute a module's action script — triggered by shortcut or deep link. */
    data class ExecuteAction(val moduleId: String) : PendingAction

    /** Open a module's WebUI — triggered by shortcut. */
    data class OpenWebUI(val moduleId: String) : PendingAction
}

private sealed interface ModuleDeepLink {
    data class Action(val moduleId: String) : ModuleDeepLink
    data class WebUi(val moduleId: String) : ModuleDeepLink
}

private fun buildInternalWebUiUri(moduleId: String): Uri {
    return Uri.Builder()
        .scheme(SCHEME_NOTES)
        .authority(HOST_WEBUI)
        .appendQueryParameter(PARAM_ID, moduleId)
        .build()
}

fun getDisplayName(uri: Uri): String {
    return uri.getFileName(noteApp) ?: uri.lastPathSegment ?: "Unknown"
}

/**
 * Resolve an intent snapshot into a [PendingAction].
 * Returns null if the intent carries no recognized action.
 */
private fun resolveIntent(intent: Intent): PendingAction? {
    // DownloadService notification: install module
    if (intent.action == DownloadService.ACTION_INSTALL_MODULE) {
        val token = intent.getStringExtra(DownloadService.EXTRA_TOKEN)?.takeIf { it.isNotBlank() } ?: return null
        if (token != SettingsRepositoryImpl().intentToken) return null
        val uriString = intent.getStringExtra(DownloadService.EXTRA_MODULE_URI)
            ?: return null
        val uri = uriString.toUri()
        return PendingAction.InstallModule(
            uri = uri,
            displayName = getDisplayName(uri),
            requiresConfirmation = false,
        )
    }

    // File manager: open ZIP
    val viewUri = intent.data
    if (viewUri != null && viewUri.scheme == "content" && intent.type == "application/zip") {
        return PendingAction.InstallModule(
            uri = viewUri,
            displayName = getDisplayName(viewUri),
            requiresConfirmation = true,
        )
    }

    // Check deep links
    return when (val deepLink = parseValidatedDeepLink(intent.data)) {
        is ModuleDeepLink.Action -> PendingAction.ExecuteAction(deepLink.moduleId)
        is ModuleDeepLink.WebUi -> PendingAction.OpenWebUI(deepLink.moduleId)
        null -> null
    }
}

private fun parseValidatedDeepLink(uri: Uri?): ModuleDeepLink? {
    if (uri?.scheme != SCHEME_NOTES) return null

    val moduleId = uri.getQueryParameter(PARAM_ID)?.takeIf { it.isNotBlank() } ?: return null
    val token = uri.getQueryParameter(PARAM_TOKEN)?.takeIf { it.isNotBlank() } ?: return null
    if (token != SettingsRepositoryImpl().intentToken) return null

    return when (uri.host) {
        HOST_ACTION -> ModuleDeepLink.Action(moduleId)
        HOST_WEBUI -> ModuleDeepLink.WebUi(moduleId)
        else -> null
    }
}

@SuppressLint("StringFormatInvalid")
@Composable
fun IntentDispatcher(intentChannel: ReceiveChannel<Intent>) {
    val context = LocalContext.current
    val resources = LocalResources.current
    val navigator = LocalNavigator.current
    val isSafeMode = NativeApi.isSafeMode
    val isManager = NativeApi.isManager
    var pendingZipInstall by rememberSaveable(stateSaver = PendingAction.InstallModule.InstallModuleSaver) { mutableStateOf(null) }
    val scope = rememberCoroutineScope()

    // A one-shot script ZIP opens the run page, which also offers installing it as a module.
    val openModuleZip: (Uri) -> Unit = { uri ->
        scope.launch {
            val script = ScriptRepository.peekOneshot(uri)
            if (script != null) {
                navigator.push(Route.ScriptRun(ScriptRunArg(uri, offerInstall = true, displayName = script.name)))
            } else {
                navigator.push(Route.Flash(FlashIt.FlashModules(listOf(uri))))
            }
        }
    }

    val installDialog = rememberConfirmDialog(
        onConfirm = {
            pendingZipInstall?.let { action -> openModuleZip(action.uri) }
            pendingZipInstall = null
        },
        onDismiss = { pendingZipInstall = null }
    )

    CollectIntentChannel(intentChannel) { intent ->
        if (!isManager) return@CollectIntentChannel
        val action = resolveIntent(intent) ?: return@CollectIntentChannel

        when (action) {
            is PendingAction.InstallModule -> {
                if (isSafeMode) {
                    Toast.makeText(
                        context,
                        resources.getString(R.string.safe_mode_module_disabled),
                        Toast.LENGTH_SHORT
                    ).show()
                    return@CollectIntentChannel
                }
                if (action.requiresConfirmation) {
                    pendingZipInstall = action
                    installDialog.showConfirm(
                        title = resources.getString(R.string.module),
                        content = resources.getString(
                            R.string.module_install_prompt_with_name,
                            "\n${action.displayName}"
                        )
                    )
                } else {
                    openModuleZip(action.uri)
                }
            }

            is PendingAction.ExecuteAction -> {
                navigator.push(Route.ExecuteModuleAction(action.moduleId, fromShortcut = true))
            }

            is PendingAction.OpenWebUI -> {
                val webIntent = Intent(context, WebUIActivity::class.java)
                    .setData(buildInternalWebUiUri(action.moduleId))
                context.startActivity(webIntent)
            }
        }
    }
}

/**
 * Receive intents inside a [LaunchedEffect] tied to the channel identity.
 * Each emitted intent is processed exactly once; no activity.intent mutation needed.
 */
@Composable
private fun CollectIntentChannel(intentChannel: ReceiveChannel<Intent>, onIntent: suspend (Intent) -> Unit) {
    LaunchedEffect(intentChannel) {
        for (intent in intentChannel) {
            onIntent(intent)
        }
    }
}
