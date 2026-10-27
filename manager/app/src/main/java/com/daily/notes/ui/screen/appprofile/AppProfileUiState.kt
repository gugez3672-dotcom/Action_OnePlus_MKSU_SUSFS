package com.daily.notes.ui.screen.appprofile

import androidx.compose.runtime.Immutable
import com.daily.notes.NativeApi
import com.daily.notes.ui.screen.superuser.GroupedApps

@Immutable
data class AppProfileUiState(
    val uid: Int,
    val packageName: String,
    val profile: NativeApi.Profile,
    val appGroup: GroupedApps,
    val sharedUserId: String,
) {
    val isUidGroup get() = appGroup.apps.size > 1
}

@Immutable
data class AppProfileActions(
    val onBack: () -> Unit,
    val onLaunchApp: (String, Int) -> Unit,
    val onForceStopApp: (String, Int) -> Unit,
    val onRestartApp: (String, Int) -> Unit,
    val onViewTemplate: (String) -> Unit,
    val onManageTemplate: () -> Unit,
    val onProfileChange: (NativeApi.Profile) -> Unit,
)
