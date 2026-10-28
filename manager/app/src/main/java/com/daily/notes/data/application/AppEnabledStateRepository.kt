package com.daily.notes.data.application

import android.content.Context
import com.daily.notes.data.shell.BackendCliRepository
import com.topjohnwu.superuser.Shell
import com.topjohnwu.superuser.ShellUtils
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject

/** Reads and changes one package in the Android user represented by the selected app UID. */
class AppEnabledStateRepository(context: Context, private val backend: BackendCliRepository) {
    // Keep the D96 ledger so a package disabled by D96 can regain its original state.
    private val preferences = context.getSharedPreferences("batch_app_control_v1", Context.MODE_PRIVATE)
    private val managerPackage = context.packageName
    private val packagePattern = Regex("[A-Za-z0-9_]+(?:\\.[A-Za-z0-9_]+)+")
    private val statePattern = Regex("(?m)^\\s*User (\\d+):[^\\n]*installed=(true|false)[^\\n]*enabled=(\\d+)")

    data class PackageState(val disabled: Boolean, val protected: Boolean)

    suspend fun state(uid: Int, packageName: String): PackageState = withContext(Dispatchers.IO) {
        backend.withNewRootShell {
            check(isRoot) { "Root shell unavailable" }
            require(uid >= 0 && packagePattern.matches(packageName)) { "Invalid selected application" }
            val userId = uid / 100000
            val enabled = enabledState(this, userId, packageName)
                ?: error("Selected application is not installed for user $userId")
            PackageState(enabled !in 0..1, packageName in protectedPackages(this, userId))
        }
    }

    suspend fun toggle(uid: Int, packageName: String): PackageState = withContext(Dispatchers.IO) {
        backend.withNewRootShell {
            check(isRoot) { "Root shell unavailable" }
            require(uid >= 0 && packagePattern.matches(packageName)) { "Invalid selected application" }
            val userId = uid / 100000
            val before = enabledState(this, userId, packageName)
                ?: error("Selected application is not installed for user $userId")
            val protected = packageName in protectedPackages(this, userId)
            if (before in 0..1) {
                check(!protected) { "Protected application cannot be disabled" }
                remember(userId, packageName, before)
                val result = newJob().add("/system/bin/cmd package disable-user --user $userId $packageName").exec()
                val after = enabledState(this, userId, packageName)
                if (result.isSuccess && after == 3) PackageState(true, false)
                else {
                    if (after == before) forget(userId, packageName)
                    error("Package disable failed")
                }
            } else {
                val original = managedState(userId, packageName)
                val verb = if (original == null || original == 1) "enable" else "default-state"
                val result = newJob().add("/system/bin/cmd package $verb --user $userId $packageName").exec()
                val after = enabledState(this, userId, packageName)
                if (result.isSuccess && after in 0..1) {
                    forget(userId, packageName)
                    PackageState(false, protected)
                } else error("Package restore failed")
            }
        }
    }

    private fun enabledState(shell: Shell, userId: Int, name: String): Int? {
        val output = commandOutput(shell, "/system/bin/cmd package dump-package $name")
        return statePattern.findAll(output).firstOrNull {
            it.groupValues[1].toIntOrNull() == userId && it.groupValues[2] == "true"
        }?.groupValues?.get(3)?.toIntOrNull()
    }

    private fun commandOutput(shell: Shell, command: String): String {
        val lines = ArrayList<String>()
        val result = shell.newJob().add(command).to(lines, null).exec()
        check(result.isSuccess) { "Package state query failed" }
        return lines.joinToString("\n")
    }

    private fun protectedPackages(shell: Shell, userId: Int): Set<String> {
        val fixed = setOf(
            managerPackage, "android", "com.android.systemui", "com.android.settings",
            "com.android.phone", "com.android.permissioncontroller", "com.google.android.permissioncontroller",
            "com.android.providers.settings", "com.android.providers.media",
        )
        val home = ShellUtils.fastCmd(
            shell,
            "/system/bin/cmd package resolve-activity --user $userId --brief -a android.intent.action.MAIN -c android.intent.category.HOME"
        ).lineSequence().lastOrNull { '/' in it }?.substringBefore('/')
        val ime = ShellUtils.fastCmd(shell, "/system/bin/settings --user $userId get secure default_input_method")
            .trim().substringBefore('/')
        return fixed + listOfNotNull(home, ime).filter { packagePattern.matches(it) }
    }

    private fun key(userId: Int, name: String) = "$userId:$name"

    private fun managedState(userId: Int, name: String): Int? =
        runCatching { JSONObject(preferences.getString("states", "{}") ?: "{}") }
            .getOrDefault(JSONObject()).optInt(key(userId, name), -1).takeIf { it in 0..1 }

    @Synchronized
    private fun remember(userId: Int, name: String, state: Int) {
        val json = JSONObject(preferences.getString("states", "{}") ?: "{}")
        json.put(key(userId, name), state)
        check(preferences.edit().putString("states", json.toString()).commit()) { "Recovery record unavailable" }
    }

    @Synchronized
    private fun forget(userId: Int, name: String) {
        val json = JSONObject(preferences.getString("states", "{}") ?: "{}")
        json.remove(key(userId, name))
        check(preferences.edit().putString("states", json.toString()).commit()) { "Recovery record unavailable" }
    }
}
