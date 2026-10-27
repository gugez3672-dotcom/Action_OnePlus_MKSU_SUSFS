package com.daily.notes.ui.viewmodel

import android.os.Build
import android.system.Os
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import com.daily.notes.BuildConfig
import com.daily.notes.NativeApi
import com.daily.notes.data.repository.SettingsRepository
import com.daily.notes.data.repository.SettingsRepositoryImpl
import com.daily.notes.getKernelVersion
import com.daily.notes.runtime.noteApp
import com.daily.notes.ui.screen.home.HomeUiState
import com.daily.notes.ui.screen.home.SystemInfo
import com.daily.notes.ui.screen.home.getManagerVersion
import com.daily.notes.ui.util.checkNewVersion
import com.daily.notes.ui.util.getSELinuxStatusRaw
import com.daily.notes.ui.util.module.LatestVersionInfo
import com.daily.notes.ui.util.resolveDeviceName
import com.daily.notes.ui.util.rootAvailable

class HomeViewModel(
    private val settingsRepo: SettingsRepository = SettingsRepositoryImpl()
) : ViewModel() {

    private val _uiState = MutableStateFlow(buildState())
    val uiState: StateFlow<HomeUiState> = _uiState.asStateFlow()

    fun refresh() {
        viewModelScope.launch {
            val baseState = withContext(Dispatchers.IO) { buildState() }
            _uiState.update { baseState }
            if (baseState.checkUpdateEnabled) {
                val latestVersionInfo = withContext(Dispatchers.IO) { checkNewVersion() }
                _uiState.update { it.copy(latestVersionInfo = latestVersionInfo) }
            }
        }
    }

    private fun buildState(): HomeUiState {
        val kernelVersion = getKernelVersion()
        val isManager = NativeApi.isManager
        val ksuVersion = if (isManager) NativeApi.version else null
        val kernelUAPIVersion = if (isManager) NativeApi.kernelUAPIVersion else null
        val managerUAPIVersion = NativeApi.managerUAPIVersion
        val lkmMode = ksuVersion?.let { if (kernelVersion.isGKI()) NativeApi.isLkmMode else null }
        val isRootAvailable = rootAvailable()
        val managerVersion = getManagerVersion(noteApp)

        return HomeUiState(
            kernelVersion = kernelVersion,
            ksuVersion = ksuVersion,
            lkmMode = lkmMode,
            isLkmBundled = lkmMode == true && NativeApi.isLkmBundled,
            isManager = isManager,
            isManagerPrBuild = BuildConfig.IS_PR_BUILD,
            isKernelPrBuild = NativeApi.isPrBuild,
            requiresNewKernel = isManager && NativeApi.managerUAPIVersion > NativeApi.kernelUAPIVersion,
            requiresNewManager = isManager && NativeApi.managerUAPIVersion < NativeApi.kernelUAPIVersion,
            kernelUAPIVersion = kernelUAPIVersion,
            managerUAPIVersion = managerUAPIVersion,
            isRootAvailable = isRootAvailable,
            isSafeMode = NativeApi.isSafeMode,
            isLateLoadMode = NativeApi.isLateLoadMode,
            checkUpdateEnabled = settingsRepo.checkUpdate,
            latestVersionInfo = LatestVersionInfo(),
            currentManagerVersionCode = managerVersion.versionCode,
            systemInfo = SystemInfo(
                kernelVersion = Os.uname().release,
                managerVersion = "${managerVersion.versionName} (${managerVersion.versionCode}-${managerUAPIVersion})",
                deviceModel = resolveDeviceName(),
                fingerprint = Build.FINGERPRINT,
                selinuxStatus = getSELinuxStatusRaw(),
                seccompStatus = runCatching {
                    Os.prctl(21 /* PR_GET_SECCOMP */, 0, 0, 0, 0)
                }.getOrDefault(-1),
            ),
        )
    }
}
