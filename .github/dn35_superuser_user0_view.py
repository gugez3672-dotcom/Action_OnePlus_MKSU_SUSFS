#!/usr/bin/env python3
"""Daily Notes user-0-only Superuser list, temporarily expanded by title long-press.

Input: ReSukiSU 6ec8d9a8 after existing Daily Notes launcher/tools patches.
This patch affects only Compose presentation and in-memory ViewModel controls.
It does not alter app enumeration, UID identity, or kernel allowlist persistence.
"""
from pathlib import Path

BASE = Path("source/manager/app/src/main/java/com/resukisu/resukisu")

def replace_once(path: Path, before: str, after: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(before)
    if count != 1:
        raise SystemExit(f"{path}: expected one anchor, found {count}: {before[:85]!r}")
    path.write_text(text.replace(before, after, 1), encoding="utf-8")

vm = BASE / "ui/viewmodel/SuperUserViewModel.kt"
replace_once(
    vm,
    "data class SuperUserUiState(\n    val appGroupList: List<InstalledAppGroup> = emptyList(),\n",
    "data class SuperUserUiState(\n    val appGroupList: List<InstalledAppGroup> = emptyList(),\n    val showOtherUsers: Boolean = false,\n",
)
replace_once(
    vm,
    "private data class SuperUserControls(\n    val search: String = \"\",\n",
    "private data class SuperUserControls(\n    val search: String = \"\",\n    val showOtherUsers: Boolean = false,\n",
)
replace_once(
    vm,
    "    data object Refresh : SuperUserUiAction\n",
    "    data object Refresh : SuperUserUiAction\n"
    "    data object ToggleOtherUsers : SuperUserUiAction\n"
    "    data object HideOtherUsers : SuperUserUiAction\n",
)
replace_once(
    vm,
    "                groups = source.groups,\n                search = local.search,\n",
    "                groups = source.groups,\n                showOtherUsers = local.showOtherUsers,\n                search = local.search,\n",
)
replace_once(
    vm,
    "            search = local.search,\n            showSystemApps = local.showSystemApps,\n",
    "            search = local.search,\n            showOtherUsers = local.showOtherUsers,\n            showSystemApps = local.showSystemApps,\n",
)
replace_once(
    vm,
    "        when (action) {\n            SuperUserUiAction.Refresh -> refresh()\n",
    "        when (action) {\n            SuperUserUiAction.Refresh -> refresh()\n"
    "            SuperUserUiAction.ToggleOtherUsers -> controls.value =\n"
    "                controls.value.copy(showOtherUsers = !controls.value.showOtherUsers)\n"
    "            SuperUserUiAction.HideOtherUsers -> controls.value =\n"
    "                controls.value.copy(showOtherUsers = false)\n",
)
replace_once(
    vm,
    "    private fun buildAppGroupList(\n        groups: List<InstalledAppGroup>,\n",
    "    private fun buildAppGroupList(\n        groups: List<InstalledAppGroup>,\n        showOtherUsers: Boolean,\n",
)
replace_once(
    vm,
    "    ): List<InstalledAppGroup> = groups\n        .filter { group ->\n",
    "    ): List<InstalledAppGroup> = groups\n"
    "        // Android app UID = userId * 100000 + appId. Do not use package name:\n"
    "        // an app may be installed for more than one Android user.\n"
    "        // Filter before text/system/sort so both granted and ungranted apps\n"
    "        // from other users are absent from normal list and search results.\n"
    "        .filter { group -> showOtherUsers || group.uid / 100000 == 0 }\n"
    "        .filter { group ->\n",
)

bar = BASE / "ui/component/SearchBar.kt"
replace_once(
    bar,
    "import androidx.compose.foundation.background\n",
    "import androidx.compose.foundation.background\n"
    "import androidx.compose.foundation.gestures.detectTapGestures\n",
)
replace_once(
    bar,
    "import androidx.compose.ui.Modifier\n",
    "import androidx.compose.ui.Modifier\n"
    "import androidx.compose.ui.input.pointer.pointerInput\n",
)
replace_once(
    bar,
    "    searchBarPlaceHolderText: String,\n) {\n",
    "    searchBarPlaceHolderText: String,\n"
    "    onTitleLongPress: (() -> Unit)? = null,\n"
    ") {\n",
)
replace_once(
    bar,
    "            title = {\n                Text(\n                    text = title\n                )\n            },\n",
    "            title = {\n"
    "                Text(\n"
    "                    text = title,\n"
    "                    modifier = if (onTitleLongPress != null) {\n"
    "                        Modifier.pointerInput(onTitleLongPress) {\n"
    "                            detectTapGestures(onLongPress = { onTitleLongPress() })\n"
    "                        }\n"
    "                    } else Modifier,\n"
    "                )\n"
    "            },\n",
)

page = BASE / "ui/screen/main/SuperUserPage.kt"
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
    "    val snackBarHostState = LocalSnackbarHost.current\n",
    "    val snackBarHostState = LocalSnackbarHost.current\n"
    "    val selectedPage = LocalSelectedPage.current\n"
    "    val currentPagerPage = LocalPagerPage.current\n",
)
replace_once(
    page,
    "    LaunchedEffect(Unit) {\n        viewModel.dispatch(SuperUserUiAction.Search(\"\"))\n    }\n",
    "    LaunchedEffect(Unit) {\n"
    "        // Reopening this screen must never restore the expanded user list.\n"
    "        viewModel.dispatch(SuperUserUiAction.HideOtherUsers)\n"
    "        viewModel.dispatch(SuperUserUiAction.Search(\"\"))\n"
    "    }\n"
    "    LaunchedEffect(selectedPage, currentPagerPage) {\n"
    "        if (selectedPage != currentPagerPage) {\n"
    "            viewModel.dispatch(SuperUserUiAction.HideOtherUsers)\n"
    "        }\n"
    "    }\n"
    "    LifecycleEventEffect(Lifecycle.Event.ON_STOP) {\n"
    "        viewModel.dispatch(SuperUserUiAction.HideOtherUsers)\n"
    "    }\n",
)
replace_once(
    page,
    "                title = stringResource(R.string.superuser),\n",
    "                title = stringResource(R.string.superuser),\n"
    "                onTitleLongPress = {\n"
    "                    viewModel.dispatch(SuperUserUiAction.ToggleOtherUsers)\n"
    "                },\n",
)
# Fail-closed guards: no permissions, persistence, or launcher state modified.
viewmodel = vm.read_text()
screen = page.read_text()
searchbar = bar.read_text()
assert "showOtherUsers || group.uid / 100000 == 0" in viewmodel
assert "setBooleanPreference(KEY_SHOW_OTHER_USERS" not in viewmodel
assert "onTitleLongPress = {" in screen
assert "LifecycleEventEffect(Lifecycle.Event.ON_STOP)" in screen
assert "LocalSelectedPage.current" in screen
assert "detectTapGestures(onLongPress = { onTitleLongPress() })" in searchbar
print("Daily Notes user-0 auth view patch applied; all source anchors verified.")
