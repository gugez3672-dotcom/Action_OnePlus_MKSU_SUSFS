#!/usr/bin/env python3
"""Daily Notes: default-hide installed module UI and home module count.

Applied after dn35 and dn36 on pinned upstream ReSukiSU.
The module list is hidden ONLY in the UI state; module repository, on-disk
modules, enable/disable operations, and kernel features remain unchanged.
The module title requires an uninterrupted 2,000 ms press (not system long press).
"""
from pathlib import Path

BASE = Path("source/manager/app/src/main/java/com/resukisu/resukisu")

def replace_once(path: Path, before: str, after: str) -> None:
    source = path.read_text(encoding="utf-8")
    count = source.count(before)
    if count != 1:
        raise SystemExit(f"{path}: expected one anchor, found {count}: {before[:110]!r}")
    path.write_text(source.replace(before, after, 1), encoding="utf-8")

vm = BASE / "ui/viewmodel/ModuleViewModel.kt"
replace_once(
    vm,
    "data class ModuleUiState(\n    val moduleList: List<InstalledModule> = emptyList(),\n",
    "data class ModuleUiState(\n    val moduleList: List<InstalledModule> = emptyList(),\n"
    "    val showInstalledModules: Boolean = false,\n",
)
replace_once(
    vm,
    "    data object ReloadSettings : ModuleUiAction\n",
    "    data object ReloadSettings : ModuleUiAction\n"
    "    data object ToggleInstalledModules : ModuleUiAction\n"
    "    data object HideInstalledModules : ModuleUiAction\n",
)
replace_once(
    vm,
    "private data class ModuleControls(\n    val search: String = \"\",\n",
    "private data class ModuleControls(\n    val search: String = \"\",\n"
    "    val showInstalledModules: Boolean = false,\n",
)
replace_once(
    vm,
    "                modules = source.modules,\n                search = local.search,\n",
    "                modules = if (local.showInstalledModules) source.modules else emptyList(),\n"
    "                search = local.search,\n",
)
replace_once(
    vm,
    "            moduleSizes = local.moduleSizes,\n",
    "            moduleSizes = local.moduleSizes,\n"
    "            showInstalledModules = local.showInstalledModules,\n",
)
replace_once(
    vm,
    "            ModuleUiAction.ReloadSettings -> modulePreferences.reload()\n",
    "            ModuleUiAction.ReloadSettings -> modulePreferences.reload()\n"
    "            ModuleUiAction.ToggleInstalledModules -> controls.update {\n"
    "                it.copy(showInstalledModules = !it.showInstalledModules)\n"
    "            }\n"
    "            ModuleUiAction.HideInstalledModules -> controls.update {\n"
    "                it.copy(showInstalledModules = false)\n"
    "            }\n",
)

# Extend the existing SearchAppBar title modifier introduced by dn35 without
# altering Superuser's normal long-press behavior. Two-second press only on Modules.
bar = BASE / "ui/component/SearchBar.kt"
replace_once(
    bar,
    "import androidx.compose.foundation.gestures.detectTapGestures\n",
    "import androidx.compose.foundation.gestures.detectTapGestures\n"
    "import androidx.compose.foundation.gestures.awaitEachGesture\n"
    "import androidx.compose.foundation.gestures.awaitFirstDown\n"
    "import androidx.compose.foundation.gestures.waitForUpOrCancellation\n",
)
replace_once(
    bar,
    "import androidx.compose.ui.input.pointer.pointerInput\n",
    "import androidx.compose.ui.input.pointer.pointerInput\n"
    "import kotlinx.coroutines.withTimeoutOrNull\n",
)
replace_once(
    bar,
    "    onTitleLongPress: (() -> Unit)? = null,\n",
    "    onTitleLongPress: (() -> Unit)? = null,\n"
    "    onTitleHoldTwoSeconds: (() -> Unit)? = null,\n",
)
replace_once(
    bar,
    """                    modifier = if (onTitleLongPress != null) {
                        Modifier.pointerInput(onTitleLongPress) {
                            detectTapGestures(onLongPress = { onTitleLongPress() })
                        }
                    } else Modifier,
""",
    """                    modifier = when {
                        onTitleHoldTwoSeconds != null -> Modifier.pointerInput(onTitleHoldTwoSeconds) {
                            awaitEachGesture {
                                awaitFirstDown(requireUnconsumed = false)
                                // A release OR gesture cancellation before 2,000ms aborts.
                                val endedBeforeDeadline = withTimeoutOrNull(2_000L) {
                                    waitForUpOrCancellation()
                                    true
                                }
                                if (endedBeforeDeadline == null) {
                                    onTitleHoldTwoSeconds()
                                    // Only one toggle per continuous finger-down.
                                    waitForUpOrCancellation()
                                }
                            }
                        }
                        onTitleLongPress != null -> Modifier.pointerInput(onTitleLongPress) {
                            detectTapGestures(onLongPress = { onTitleLongPress() })
                        }
                        else -> Modifier
                    },
""",
)

page = BASE / "ui/screen/main/ModulePage.kt"
replace_once(
    page,
    "import androidx.lifecycle.compose.collectAsStateWithLifecycle\n",
    "import androidx.lifecycle.Lifecycle\n"
    "import androidx.lifecycle.compose.LifecycleEventEffect\n"
    "import androidx.lifecycle.compose.collectAsStateWithLifecycle\n",
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
    "    val viewModel = koinViewModel<ModuleViewModel>()\n",
    "    val viewModel = koinViewModel<ModuleViewModel>()\n"
    "    val selectedPage = LocalSelectedPage.current\n"
    "    val currentPagerPage = LocalPagerPage.current\n",
)
replace_once(
    page,
    """    LaunchedEffect(Unit) {
        viewModel.dispatch(ModuleUiAction.Search(""))
        if (uiState.moduleList.isEmpty() || uiState.isNeedRefresh) {
            viewModel.dispatch(ModuleUiAction.Refresh())
        }
    }
""",
    """    LaunchedEffect(Unit) {
        // Always enter the modules page with an empty visible list.
        viewModel.dispatch(ModuleUiAction.HideInstalledModules)
        viewModel.dispatch(ModuleUiAction.Search(""))
        if (uiState.moduleList.isEmpty() || uiState.isNeedRefresh) {
            viewModel.dispatch(ModuleUiAction.Refresh())
        }
    }
    LaunchedEffect(selectedPage, currentPagerPage) {
        if (selectedPage != currentPagerPage) {
            viewModel.dispatch(ModuleUiAction.HideInstalledModules)
        }
    }
    LifecycleEventEffect(Lifecycle.Event.ON_STOP) {
        viewModel.dispatch(ModuleUiAction.HideInstalledModules)
    }
""",
)
replace_once(
    page,
    "                title = stringResource(R.string.module),\n",
    "                title = stringResource(R.string.module),\n"
    "                onTitleHoldTwoSeconds = {\n"
    "                    viewModel.dispatch(ModuleUiAction.ToggleInstalledModules)\n"
    "                },\n",
)

# A plain visual 0 in the HOME card; leave actual HomeViewModel and module
# repository counts intact for internal use, monitoring, and module operations.
home = BASE / "ui/screen/main/HomePage.kt"
replace_once(
    home,
    """                    uiState.systemInfo.superuserCount,
                    uiState.systemInfo.moduleCount
""",
    """                    uiState.systemInfo.superuserCount,
                    0 // UI mask only; real installed module count stays untouched.
""",
)

# Fail-closed static assertions: no persistent flags and no module mutations.
vm_text = vm.read_text()
bar_text = bar.read_text()
page_text = page.read_text()
home_text = home.read_text()
assert "if (local.showInstalledModules) source.modules else emptyList()" in vm_text
assert "val showInstalledModules: Boolean = false" in vm_text
assert "val showInstalledModules: Boolean = false" in vm_text
assert "onTitleHoldTwoSeconds = {" in page_text
assert "withTimeoutOrNull(2_000L)" in bar_text
assert "waitForUpOrCancellation()" in bar_text
assert "onTitleLongPress != null" in bar_text
assert "LifecycleEventEffect(Lifecycle.Event.ON_STOP)" in page_text
assert "LocalSelectedPage.current" in page_text
assert "ModuleUiAction.HideInstalledModules" in page_text
assert "uiState.systemInfo.superuserCount,\n                    0 // UI mask only;" in home_text
assert "updateCachedModuleEnabledUseCase" in vm_text
assert "setModuleRemoved(" in vm_text
print("Daily Notes module-list concealment: 2-second title hold, home 0, transient UI-only state verified.")
