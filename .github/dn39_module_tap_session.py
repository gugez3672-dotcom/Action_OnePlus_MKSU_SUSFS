#!/usr/bin/env python3
"""Daily Notes session-scoped, tap-to-toggle module-list visibility.

Apply after dn35..dn38, including the WebUI backend lookup fix.
Single title tap toggles only the presentation list. Keep it visible across
main-page navigation, internal WebUI, and in-app operations. Reset on fresh
main manager launch and when the main Activity really finishes; never persist.
Home module count remains visually 0. No change to module storage or kernel.
"""
from pathlib import Path

BASE = Path("source/manager/app/src/main/java/com/resukisu/resukisu")

def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one anchor, found {count}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")

# A process-memory flag is shared by the main page's ModuleViewModel.
# WebUIActivity creates a different ModuleViewModel, and HorizontalPager may
# destroy/recreate the ModulePage while tabs change. Neither may reset the flag.
vm = BASE / "ui/viewmodel/ModuleViewModel.kt"
replace_once(
    vm,
    "data class ModuleUiState(\n",
    """/**
 * Transient visibility shared across manager pages / ViewModel instances.
 * Never backed by SharedPreferences, disk, or kernel state.
 */
object ModuleVisibilitySession {
    private val state = MutableStateFlow(false)
    val visible: StateFlow<Boolean> = state.asStateFlow()

    fun toggle() {
        state.value = !state.value
    }

    fun reset() {
        state.value = false
    }
}

data class ModuleUiState(
""",
)
replace_once(
    vm,
    """private data class ModuleControls(
    val search: String = "",
    val showInstalledModules: Boolean = false,
""",
    """private data class ModuleControls(
    val search: String = "",
""",
)
replace_once(
    vm,
    """        observeInstalledModules(),
        controls,
        modulePreferences.preferences,
    ) { source, local, preferences ->
""",
    """        observeInstalledModules(),
        controls,
        modulePreferences.preferences,
        ModuleVisibilitySession.visible,
    ) { source, local, preferences, showModules ->
""",
)
replace_once(
    vm,
    "modules = if (local.showInstalledModules) source.modules else emptyList(),",
    "modules = if (showModules) source.modules else emptyList(),",
)
replace_once(
    vm,
    "showInstalledModules = local.showInstalledModules,",
    "showInstalledModules = showModules,",
)
replace_once(
    vm,
    """            ModuleUiAction.ToggleInstalledModules -> controls.update {
                it.copy(showInstalledModules = !it.showInstalledModules)
            }
            ModuleUiAction.HideInstalledModules -> controls.update {
                it.copy(showInstalledModules = false)
            }
""",
    """            ModuleUiAction.ToggleInstalledModules -> ModuleVisibilitySession.toggle()
            ModuleUiAction.HideInstalledModules -> ModuleVisibilitySession.reset()
""",
)

# Replace the module-title 2s press recognizer with a normal single-tap
# callback. Preserve Superuser's independent onTitleLongPress behavior.
bar = BASE / "ui/component/SearchBar.kt"
replace_once(
    bar,
    """import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.waitForUpOrCancellation
""",
    """import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
""",
)
replace_once(
    bar,
    "import kotlinx.coroutines.withTimeoutOrNull\n",
    "",
)
replace_once(
    bar,
    """    onTitleLongPress: (() -> Unit)? = null,
    onTitleHoldTwoSeconds: (() -> Unit)? = null,
""",
    """    onTitleLongPress: (() -> Unit)? = null,
    onTitleClick: (() -> Unit)? = null,
""",
)
replace_once(
    bar,
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
    """                    modifier = when {
                        onTitleClick != null -> Modifier.clickable(onClick = onTitleClick)
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
    """import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
""",
    """import androidx.lifecycle.compose.collectAsStateWithLifecycle
""",
)
replace_once(
    page,
    """import com.resukisu.resukisu.ui.util.LocalPagerPage
import com.resukisu.resukisu.ui.util.LocalSelectedPage
import com.resukisu.resukisu.ui.util.LocalSnackbarHost
""",
    """import com.resukisu.resukisu.ui.util.LocalSnackbarHost
""",
)
replace_once(
    page,
    """    val viewModel = koinViewModel<ModuleViewModel>()
    val selectedPage = LocalSelectedPage.current
    val currentPagerPage = LocalPagerPage.current
""",
    """    val viewModel = koinViewModel<ModuleViewModel>()
""",
)
replace_once(
    page,
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
    """    LaunchedEffect(Unit) {
        // Do not reset module visibility on tab changes or returning from WebUI.
        viewModel.dispatch(ModuleUiAction.Search(""))
        if (uiState.moduleList.isEmpty() || uiState.isNeedRefresh) {
            viewModel.dispatch(ModuleUiAction.Refresh())
        }
    }
""",
)
replace_once(
    page,
    """                onTitleHoldTwoSeconds = {
                    viewModel.dispatch(ModuleUiAction.ToggleInstalledModules)
                },
""",
    """                onTitleClick = {
                    viewModel.dispatch(ModuleUiAction.ToggleInstalledModules)
                },
""",
)

# Exit semantics: every fresh MainActivity starts concealed. When the main
# Activity actually finishes, reset even if Android retains this app process.
# Do not reset on pause/stop: WebUI and system pickers may stop MainActivity
# while the user is still performing an operation inside the manager.
main = BASE / "ui/MainActivity.kt"
replace_once(
    main,
    "import com.resukisu.resukisu.ui.viewmodel.ModuleViewModel\n",
    "import com.resukisu.resukisu.ui.viewmodel.ModuleViewModel\n"
    "import com.resukisu.resukisu.ui.viewmodel.ModuleVisibilitySession\n",
)
replace_once(
    main,
    """            super.onCreate(savedInstanceState)

            splashScreen.setKeepOnScreenCondition {
""",
    """            super.onCreate(savedInstanceState)
            // New manager task/session: never carry over a previous reveal.
            // A configuration-change recreation retains the current session.
            if (savedInstanceState == null) {
                ModuleVisibilitySession.reset()
            }

            splashScreen.setKeepOnScreenCondition {
""",
)
replace_once(
    main,
    """    override fun onDestroy() {
        try {
            themeUtils.unregisterThemeChangeObserver(this, themeChangeObserver)
""",
    """    override fun onDestroy() {
        try {
            // Do not reset on WebUI navigation or configuration changes.
            if (isFinishing) {
                ModuleVisibilitySession.reset()
            }
            themeUtils.unregisterThemeChangeObserver(this, themeChangeObserver)
""",
)

# Fail-closed: neither UI tab transitions nor lifecycle stops may reset it.
v, p, b, a = (f.read_text() for f in (vm, page, bar, main))
home = (BASE / "ui/screen/main/HomePage.kt").read_text()
webui = (BASE / "ui/webui/WebViewHelper.kt").read_text()
assert "ModuleVisibilitySession.visible" in v and "if (showModules) source.modules else emptyList()" in v
assert "showInstalledModules = showModules" in v
assert "ModuleVisibilitySession.toggle()" in v and "ModuleVisibilitySession.reset()" in v
assert "onTitleClick = {" in p and "onTitleHoldTwoSeconds" not in p
assert "onTitleClick != null -> Modifier.clickable(onClick = onTitleClick)" in b
assert "onTitleLongPress != null -> Modifier.pointerInput(onTitleLongPress)" in b
assert "onTitleHoldTwoSeconds" not in b and "withTimeoutOrNull(2_000L)" not in b
assert "ModuleUiAction.HideInstalledModules" not in p
assert "LifecycleEventEffect" not in p and "LocalSelectedPage" not in p
assert "if (savedInstanceState == null)" in a and "if (isFinishing)" in a
assert a.count("ModuleVisibilitySession.reset()") == 2
assert "uiState.systemInfo.superuserCount,\n                    0 // UI mask only;" in home
assert "moduleRepository.installedModules.value.modules.find" in webui
print("Daily Notes: title tap toggle, session-persistent reveal, exit reset, home 0 and WebUI compatibility verified.")
