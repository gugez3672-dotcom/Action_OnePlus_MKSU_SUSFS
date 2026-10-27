package com.daily.notes.data.terminal

import android.content.Context
import android.provider.Settings
import java.io.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.coroutines.delay
import org.json.JSONObject

/** App-private control never writes to script stdin or opens a cleanup Shell. */
internal class DnRootSessionControl(private val context: Context) {
    private val root = File(context.filesDir, "terminal/sessions")
    private fun bootCount() = Settings.Global.getInt(context.contentResolver, Settings.Global.BOOT_COUNT, -1)
    private fun directory(token: String): File {
        require(token.matches(Regex("[a-f0-9-]{36}")))
        return File(root, token)
    }
    data class State(val phase: String, val pid: Int, val start: Long, val code: Int) {
        val finished get() = phase == "FINISHED" || phase == "FAILED"
    }
    data class Saved(val id: String, val label: String, val directory: String)
    fun prepare(token: String, mode: String, label: String, workingDirectory: String): File {
        val target = directory(token)
        check(target.mkdirs())
        File(target, "command").writeText("RUN\n")
        File(target, "view").writeText("RUN\n")
        File(target, "description.json").writeText(JSONObject().put("mode", mode).put("label", label)
            .put("directory", workingDirectory).put("boot", bootCount()).toString())
        return target
    }
    fun state(token: String): State? = runCatching {
        val lines = File(directory(token), "state").readLines()
        State(lines[0], lines[1].toInt(), lines[2].toLong(), lines[3].toInt())
    }.getOrNull()
    fun forget(token: String) { directory(token).deleteRecursively() }
    fun connect(token: String): File = directory(token).also {
        check(it.isDirectory)
        File(it, "view").writeText("RUN\n")
    }
    fun detach(token: String) { File(directory(token), "view").writeText("DETACH\n") }
    fun savedBackground(): List<Saved> = root.listFiles().orEmpty().mapNotNull { dir ->
        runCatching {
            val description = JSONObject(File(dir, "description.json").readText())
            if (description.getString("mode") != "background" || description.optInt("boot", -2) != bootCount()
                || state(dir.name)?.finished != false) null
            else Saved(dir.name, description.getString("label"), description.getString("directory"))
        }.getOrNull()
    }
    suspend fun terminate(token: String): Boolean = withContext(Dispatchers.IO) {
        if (state(token)?.finished == true) return@withContext true
        runCatching { File(directory(token), "command").writeText("STOP\n") }.getOrElse { return@withContext false }
        repeat(35) {
            if (state(token)?.finished == true) return@withContext true
            delay(100)
        }
        false
    }
}
