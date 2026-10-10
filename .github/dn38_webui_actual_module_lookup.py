#!/usr/bin/env python3
"""Daily Notes WebUI fix after module UI concealment.

ModuleViewModel.uiState.moduleList is intentionally empty until the title is
held for 2s. WebUIActivity must validate against the authoritative module
repository, not against this UI-only filtered projection. Leave all backend,
installed modules, grants, WebUI security checks and concealment unchanged.
"""
from pathlib import Path

BASE = Path("source/manager/app/src/main/java/com/resukisu/resukisu")

def replace_once(path: Path, before: str, after: str):
    s = path.read_text(encoding="utf-8")
    count = s.count(before)
    if count != 1:
        raise SystemExit(f"{path}: expected one anchor, got {count}: {before[:100]!r}")
    path.write_text(s.replace(before, after, 1), encoding="utf-8")

activity = BASE / "ui/webui/WebUIActivity.kt"
replace_once(
    activity,
    "import com.resukisu.resukisu.data.AppSettingsRepository\n",
    "import com.resukisu.resukisu.data.AppSettingsRepository\n"
    "import com.resukisu.resukisu.data.module.ModuleRepository\n",
)
replace_once(
    activity,
    "    val moduleViewModel = koinViewModel<ModuleViewModel>()\n",
    "    val moduleViewModel = koinViewModel<ModuleViewModel>()\n"
    "    val moduleRepository = koinInject<ModuleRepository>()\n",
)
replace_once(
    activity,
    "            moduleViewModel,\n            superUserViewModel,\n",
    "            moduleViewModel,\n            moduleRepository,\n            superUserViewModel,\n",
)

helper = BASE / "ui/webui/WebViewHelper.kt"
replace_once(
    helper,
    "import com.resukisu.resukisu.data.AppSettingsRepository\n",
    "import com.resukisu.resukisu.data.AppSettingsRepository\n"
    "import com.resukisu.resukisu.data.module.ModuleRepository\n",
)
replace_once(
    helper,
    "    moduleViewModel: ModuleViewModel,\n    superUserViewModel: SuperUserViewModel,\n",
    "    moduleViewModel: ModuleViewModel,\n"
    "    moduleRepository: ModuleRepository,\n"
    "    superUserViewModel: SuperUserViewModel,\n",
)
replace_once(
    helper,
    """        val moduleInfo =
            moduleViewModel.uiState.value.moduleList.find { info -> info.id == moduleId }
""",
    """        // Never validate against ModuleViewModel.uiState.moduleList: it is a
        // deliberately filtered presentation projection when module hiding is on.
        // The repository still contains real modules and is updated by Refresh
        // just above, before its RefreshCompleted event is dispatched.
        val moduleInfo =
            moduleRepository.installedModules.value.modules.find { info -> info.id == moduleId }
""",
)

# Build guard: keep existing WebUI safety checks and actual refresh behavior.
h = helper.read_text()
a = activity.read_text()
assert "moduleRepository.installedModules.value.modules.find" in h
assert "moduleViewModel.uiState.value.moduleList.find" not in h
assert "moduleViewModel.dispatch(ModuleUiAction.Refresh())" in h
assert "if (!moduleInfo.hasWebUi || !moduleInfo.enabled || moduleInfo.remove)" in h
assert "moduleRepository = koinInject<ModuleRepository>()" in a
assert "moduleRepository,\n            superUserViewModel," in a
print("Daily Notes WebUI lookup now uses real ModuleRepository, not hidden UI module list.")
