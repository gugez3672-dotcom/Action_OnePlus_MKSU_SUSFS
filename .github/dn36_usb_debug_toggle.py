#!/usr/bin/env python3
"""Add a real, one-shot USB debugging toggle above ADB Root in Daily Notes.

Applied to the pinned ReSukiSU source AFTER dn35, without changing kernel
configuration, ADB Root policy, app grants, or long-running services.
"""
from pathlib import Path

BASE = Path("source/manager/app/src/main/java/com/resukisu/resukisu")
RES = Path("source/manager/app/src/main/res")

def replace_once(path: Path, before: str, after: str) -> None:
    source = path.read_text(encoding="utf-8")
    count = source.count(before)
    if count != 1:
        raise SystemExit(f"{path}: expected one anchor, found {count}: {before[:100]!r}")
    path.write_text(source.replace(before, after, 1), encoding="utf-8")

# Existing privileged runner already used by the manager itself. Never use
# bare non-root "settings put" and never start a service or a polling thread.
cli = BASE / "data/shell/KsuCli.kt"
replace_once(
    cli,
    "    fun getMetaModuleImplement(): String {\n",
    """    /**
     * Reads adb_enabled from Android global settings. The optional requested
     * state writes a literal 0/1, then reads back the actual system value.
     * null means root/command/readback failed (not "off").
     *
     * USB debugging is separate from the kernel's ADB Root feature.
     */
    suspend fun getUsbDebugEnabled(requested: Boolean? = null): Boolean? =
        withContext(Dispatchers.IO) {
            withNewRootShell {
                if (!isRoot) return@withNewRootShell null
                if (requested != null) {
                    val value = if (requested) "1" else "0"
                    val write = newJob()
                        .add("/system/bin/settings put global adb_enabled $value")
                        .exec()
                    if (!write.isSuccess) return@withNewRootShell null
                }
                val lines = ArrayList<String>()
                val read = newJob()
                    .add("/system/bin/settings get global adb_enabled")
                    .to(lines, null)
                    .exec()
                if (!read.isSuccess) {
                    null
                } else {
                    when (lines.firstOrNull()?.trim()) {
                        "1" -> true
                        "0" -> false
                        else -> null
                    }
                }
            }
        }

    fun getMetaModuleImplement(): String {
""",
)

page = BASE / "ui/screen/main/SettingsPage.kt"
replace_once(
    page,
    "import androidx.compose.material.icons.twotone.Adb\n",
    "import androidx.compose.material.icons.twotone.Adb\n"
    "import androidx.compose.material.icons.twotone.Usb\n",
)
replace_once(
    page,
    "import androidx.lifecycle.compose.collectAsStateWithLifecycle\n",
    "import androidx.lifecycle.Lifecycle\n"
    "import androidx.lifecycle.compose.LifecycleEventEffect\n"
    "import androidx.lifecycle.compose.collectAsStateWithLifecycle\n",
)
replace_once(
    page,
    "import com.resukisu.resukisu.domain.usecase.GenerateBugreportUseCase\n",
    "import com.resukisu.resukisu.data.shell.KsuCliRepository\n"
    "import com.resukisu.resukisu.domain.usecase.GenerateBugreportUseCase\n",
)
replace_once(
    page,
    "import com.resukisu.resukisu.ui.util.LocalSnackbarHost\n",
    "import com.resukisu.resukisu.ui.util.LocalPagerPage\n"
    "import com.resukisu.resukisu.ui.util.LocalSelectedPage\n"
    "import com.resukisu.resukisu.ui.util.LocalSnackbarHost\n",
)
replace_once(
    page,
    "    val generateBugreport = koinInject<GenerateBugreportUseCase>()\n",
    """    val generateBugreport = koinInject<GenerateBugreportUseCase>()
    val usbDebugCli = koinInject<KsuCliRepository>()
    val selectedPage = LocalSelectedPage.current
    val currentPagerPage = LocalPagerPage.current
    var usbDebugEnabled by remember { mutableStateOf<Boolean?>(null) }
    var usbDebugBusy by remember { mutableStateOf(false) }
""",
)
replace_once(
    page,
    "        val scope = rememberCoroutineScope()\n",
    """        val scope = rememberCoroutineScope()

        // Refresh on tab selection and when the app returns from background.
        // There is no periodic poll or persistent background process.
        LaunchedEffect(selectedPage, currentPagerPage) {
            if (selectedPage == currentPagerPage && !usbDebugBusy) {
                usbDebugEnabled = usbDebugCli.getUsbDebugEnabled()
            }
        }
        LifecycleEventEffect(Lifecycle.Event.ON_RESUME) {
            if (selectedPage == currentPagerPage && !usbDebugBusy) {
                scope.launch {
                    usbDebugEnabled = usbDebugCli.getUsbDebugEnabled()
                }
            }
        }
""",
)
replace_once(
    page,
    """                            item(
                                visible = Build.VERSION.SDK_INT > Build.VERSION_CODES.Q
                            ) {
                                val adbRootSummary = when (uiState.adbRootStatus) {
""",
    """                            // Android USB debugging; distinct from ADB Root below.
                            item {
                                val failureText = stringResource(R.string.settings_usb_debug_error)
                                SettingsSwitchWidget(
                                    icon = Icons.TwoTone.Usb,
                                    title = stringResource(R.string.settings_usb_debug),
                                    description = stringResource(R.string.settings_usb_debug_summary),
                                    checked = usbDebugEnabled == true,
                                    enabled = usbDebugEnabled != null && !usbDebugBusy,
                                    onCheckedChange = { requested ->
                                        if (!usbDebugBusy) {
                                            usbDebugBusy = true
                                            scope.launch {
                                                try {
                                                    val observed = usbDebugCli.getUsbDebugEnabled(requested)
                                                    usbDebugEnabled = observed
                                                    if (observed != requested) {
                                                        snackBarHost.showReplacingSnackbar(failureText)
                                                    }
                                                } catch (_: Exception) {
                                                    usbDebugEnabled = null
                                                    snackBarHost.showReplacingSnackbar(failureText)
                                                } finally {
                                                    usbDebugBusy = false
                                                }
                                            }
                                        }
                                    },
                                )
                            }

                            item(
                                visible = Build.VERSION.SDK_INT > Build.VERSION_CODES.Q
                            ) {
                                val adbRootSummary = when (uiState.adbRootStatus) {
""",
)

translations = [
    ("values/strings.xml",
     """    <string name="settings_usb_debug">USB debugging</string>
    <string name="settings_usb_debug_summary">Enable or disable USB debugging in system settings</string>
    <string name="settings_usb_debug_error">Failed to change USB debugging. Check root access.</string>
"""),
    ("values-zh-rCN/strings.xml",
     """    <string name="settings_usb_debug">USB 调试</string>
    <string name="settings_usb_debug_summary">切换系统 USB 调试，无需进入开发者选项</string>
    <string name="settings_usb_debug_error">切换 USB 调试失败，请检查 Root 权限</string>
"""),
]
for file, xml in translations:
    path = RES / file
    replace_once(path, "</resources>", xml + "</resources>")

# Build-time invariants / fail-closed checks.
out = page.read_text()
cli_text = cli.read_text()
assert out.index("title = stringResource(R.string.settings_usb_debug)") < out.index(
    "title = stringResource(id = R.string.settings_adb_root)")
assert "checked = usbDebugEnabled == true" in out
assert "enabled = usbDebugEnabled != null && !usbDebugBusy" in out
assert "LifecycleEventEffect(Lifecycle.Event.ON_RESUME)" in out
assert "LaunchedEffect(selectedPage, currentPagerPage)" in out
assert "withNewRootShell" in cli_text
assert "/system/bin/settings put global adb_enabled $value" in cli_text
assert "/system/bin/settings get global adb_enabled" in cli_text
assert "SettingsUiAction.SetAdbRoot" in out
print("Daily Notes USB debugging toggle patch applied; source anchors verified.")
