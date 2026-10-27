package com.daily.notes.domain.usecase

import android.util.Log
import com.daily.notes.data.shell.BackendCliRepository
import com.topjohnwu.superuser.ShellUtils
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Switch the foreground Android user between 0 and 11 (settings-title short press).
 * Matches the D98 behaviour recovered from its APK: read the current foreground
 * user and run `am switch-user` for its pair. Returns the target user.
 */
class SwitchUserUseCase(private val backend: BackendCliRepository) {
    suspend operator fun invoke(): Result<Int> = withContext(Dispatchers.IO) {
        runCatching {
            backend.withNewRootShell {
                check(isRoot) { "Root shell unavailable" }
                val current = ShellUtils.fastCmd(this, "/system/bin/am get-current-user").trim().toIntOrNull()
                    ?: error("Current Android user unavailable")
                val target = when (current) {
                    0 -> 11
                    11 -> 0
                    else -> error("Only users 0 and 11 are supported")
                }
                check(newJob().add("/system/bin/am switch-user $target").exec().isSuccess) {
                    "Android user switch failed"
                }
                target
            }
        }.onFailure { Log.e("ApplicationControl", "Android user switch failed", it) }
    }
}
