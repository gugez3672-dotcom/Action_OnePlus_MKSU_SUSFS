package com.daily.notes.data.susfs

import android.content.Context
import com.daily.notes.data.shell.BackendCliRepository
import com.topjohnwu.superuser.io.SuFile
import com.topjohnwu.superuser.io.SuFileInputStream
import com.topjohnwu.superuser.io.SuFileOutputStream
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest

/** Official tool commands, with early capture and post-metamodule updates kept separate. */
class OfficialFsConfig(private val context: Context) {
    companion object {
        const val DIRECTORY = "/data/adb/daily-notes/filesystem"
        private val scalarKeys = setOf("version", "enabled", "cmdline_or_bootconfig", "avc_log_spoofing",
            "logging", "hide_sus_mnts_for_non_su_procs", "uname", "sus_path", "sus_kstat", "open_redirect", "sus_map", "priority_packages")
        private val statFields = listOf("ino", "dev", "nlink", "size", "atime", "atime_nsec", "mtime", "mtime_nsec", "ctime", "ctime_nsec", "blocks", "blksize")
        private val uidSchemes = listOf("NonApp", "RootExceptSu", "NonSu", "UnmountedApp", "Unmounted")
        fun defaults(): JSONObject = JSONObject().put("version", 2).put("enabled", true)
            .put("cmdline_or_bootconfig", "").put("avc_log_spoofing", false).put("logging", false)
            .put("hide_sus_mnts_for_non_su_procs", false)
            .put("uname", JSONObject().put("release", "default").put("version", "default"))
            .put("sus_path", JSONArray()).put("sus_kstat", JSONArray()).put("open_redirect", JSONArray())
            .put("sus_map", JSONArray()).put("priority_packages", "")
        private fun quote(value: String): String {
            require('\u0000' !in value) { "NUL is not supported" }
            return "'" + value.replace("'", "'\"'\"'") + "'"
        }
        private fun path(value: String): String {
            require(value.startsWith('/') && value.length < 256 && '\u0000' !in value) { "Invalid absolute path" }
            return value
        }
        fun compile(config: JSONObject): Pair<String, String> {
            require(config.getInt("version") == 2) { "Unsupported configuration version" }
            require(config.keys().asSequence().all { it in scalarKeys }) { "Unknown configuration field" }
            val early = mutableListOf<List<String>>()
            val late = mutableListOf<List<String>>()
            require(!config.getBoolean("logging")) { "Logging is not compiled into this kernel" }
            early += listOf("enable_avc_log_spoofing", if (config.getBoolean("avc_log_spoofing")) "1" else "0")
            early += listOf("hide_sus_mnts_for_non_su_procs", if (config.getBoolean("hide_sus_mnts_for_non_su_procs")) "1" else "0")
            val uname = config.getJSONObject("uname")
            early += listOf("set_uname", uname.getString("release"), uname.getString("version"))
            config.getString("cmdline_or_bootconfig").takeIf { it.isNotEmpty() }?.let { early += listOf("set_cmdline_or_bootconfig", path(it)) }
            val packages = config.optString("priority_packages", "")
            if (packages.isNotEmpty()) {
                require(packages.split(',').all { it.matches(Regex("[A-Za-z0-9_]+(?:\\.[A-Za-z0-9_]+)+")) })
                late += listOf("set_priority_uid_filter", packages)
            }
            val paths = config.getJSONArray("sus_path")
            for (i in 0 until paths.length()) {
                val entry = paths.getJSONObject(i)
                late += listOf(if (entry.getBoolean("is_loop")) "add_sus_path_loop" else "add_sus_path", path(entry.getString("path")))
            }
            val maps = config.getJSONArray("sus_map")
            for (i in 0 until maps.length()) late += listOf("add_sus_map", path(maps.getString(i)))
            val stats = config.getJSONArray("sus_kstat")
            for (i in 0 until stats.length()) {
                val entry = stats.getJSONObject(i)
                val target = path(entry.getString("path"))
                when (entry.getString("spoof_type")) {
                    "Normal", "FullClone" -> {
                        early += listOf("add_sus_kstat", target)
                        late += listOf(if (entry.getString("spoof_type") == "FullClone") "update_sus_kstat_full_clone" else "update_sus_kstat", target)
                    }
                    "Statically" -> {
                        val values = entry.getJSONObject("statically")
                        early += listOf("add_sus_kstat_statically", target) + statFields.map { key ->
                            if (values.isNull(key)) "default" else values.get(key).toString().also { require(it.matches(Regex("[0-9]+"))) }
                        }
                    }
                    else -> error("Unknown statistics mode")
                }
            }
            val redirects = config.getJSONArray("open_redirect")
            for (i in 0 until redirects.length()) {
                val entry = redirects.getJSONObject(i)
                val scheme = uidSchemes.indexOf(entry.getString("uid_scheme"))
                require(scheme >= 0) { "Invalid UID scheme" }
                late += listOf("add_open_redirect", path(entry.getString("target_path")), path(entry.getString("redirected_path")), scheme.toString())
            }
            fun script(commands: List<List<String>>): String = "#!/system/bin/sh\nstatus=0\n" +
                (if (config.getBoolean("enabled")) commands.joinToString("\n", postfix = "\nexit \"\$status\"\n") { args ->
                    quote("$DIRECTORY/fsctl") + " " + args.joinToString(" ", transform = ::quote) + " || status=1"
                } else "exit 0\n")
            return script(early) to script(late)
        }
    }
    private val backend = BackendCliRepository(context)

    suspend fun load(): JSONObject = withContext(Dispatchers.IO) {
        backend.withNewRootShell {
            check(isRoot) { "Root shell unavailable" }
            val active = SuFile("$DIRECTORY/active").apply { shell = this@withNewRootShell }
            if (!active.exists()) return@withNewRootShell defaults()
            val revision = SuFileInputStream.open(active).use { it.readBytes().toString(Charsets.UTF_8).trim() }
            require(revision.matches(Regex("[a-f0-9]{64}"))) { "Invalid active configuration" }
            val file = SuFile("$DIRECTORY/revisions/$revision/config.json").apply { shell = this@withNewRootShell }
            SuFileInputStream.open(file).use {
                JSONObject(it.readBytes().toString(Charsets.UTF_8)).also { value -> compile(value) }
            }
        }
    }

    suspend fun status(): String = withContext(Dispatchers.IO) {
        backend.withNewRootShell {
            check(isRoot) { "Root shell unavailable" }
            val helper = File(context.applicationInfo.nativeLibraryDir, "libnote_filesystem.so")
            check(helper.isFile) { "Filesystem helper missing" }
            val lines = arrayListOf<String>()
            val errors = arrayListOf<String>()
            val result = newJob().add(listOf("version", "enabled_features", "variant").joinToString("\n") {
                quote(helper.path) + " show " + it
            }).to(lines, errors).exec()
            check(result.isSuccess) { errors.joinToString("\n") }
            lines.joinToString("\n")
        }
    }

    suspend fun save(config: JSONObject) = withContext(Dispatchers.IO) {
        val scripts = compile(config)
        val revision = MessageDigest.getInstance("SHA-256")
            .digest((config.toString(2) + scripts.first + scripts.second).toByteArray())
            .joinToString("") { "%02x".format(it.toInt() and 255) }
        val directory = "$DIRECTORY/revisions/$revision"
        backend.withNewRootShell {
            check(isRoot) { "Root shell unavailable" }
            check(newJob().add("umask 077; mkdir -p '$directory' /data/adb/post-fs-data.d /data/adb/post-mount.d; chmod 700 '$DIRECTORY' '$DIRECTORY/revisions' '$directory'").exec().isSuccess)
            fun atomic(target: String, data: ByteArray, executable: Boolean) {
                val temporary = "$target.${android.os.Process.myPid()}.new"
                val file = SuFile(temporary).apply { shell = this@withNewRootShell }
                try {
                    SuFileOutputStream.open(file).use { it.write(data) }
                    check(newJob().add("chmod ${if (executable) 700 else 600} ${quote(temporary)} && chown 0:0 ${quote(temporary)} && mv -f ${quote(temporary)} ${quote(target)}").exec().isSuccess)
                } finally { newJob().add("rm -f ${quote(temporary)}").exec() }
            }
            // One shared root config, independent of the Android user running the manager.
            atomic("$DIRECTORY/fsctl", File(context.applicationInfo.nativeLibraryDir, "libnote_filesystem.so").readBytes(), true)
            atomic("$directory/config.json", config.toString(2).toByteArray(), false)
            atomic("$directory/early.sh", scripts.first.toByteArray(), true)
            atomic("$directory/late.sh", scripts.second.toByteArray(), true)
            fun wrapper(stage: String): ByteArray = ("#!/system/bin/sh\n" +
                "IFS= read -r revision < '$DIRECTORY/active' || exit 1\n" +
                "case \"\$revision\" in ''|*[!0123456789abcdef]*) exit 1;; esac\n" +
                "[ \"\${#revision}\" -eq 64 ] || exit 1\n" +
                "exec /system/bin/sh \"$DIRECTORY/revisions/\$revision/$stage.sh\"\n").toByteArray()
            atomic("/data/adb/post-fs-data.d/daily-notes-filesystem.sh", wrapper("early"), true)
            atomic("/data/adb/post-mount.d/daily-notes-filesystem.sh", wrapper("late"), true)
            // Publish only after the config and both stages are completely written.
            atomic("$DIRECTORY/active", "$revision\n".toByteArray(), false)
            // Capture must run before the metamodule mounts; saving does not fake a late capture.
        }
    }

    suspend fun applyNow(config: JSONObject) = withContext(Dispatchers.IO) {
        val current = JSONObject(config.toString()).put("sus_kstat", JSONArray())
        val scripts = compile(current)
        backend.withNewRootShell {
            check(isRoot) { "Root shell unavailable" }
            val errors = arrayListOf<String>()
            val result = newJob().add("(\n" + scripts.first + "\n)\na=\$?\n(\n" + scripts.second + "\n)\nb=\$?\n[ \"\$a\" -eq 0 ] && [ \"\$b\" -eq 0 ]").to(null, errors).exec()
            check(result.isSuccess) { errors.joinToString("\n").ifBlank { "Some settings could not be applied (${result.code})" } }
        }
    }
}
