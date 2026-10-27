package com.daily.notes.data.application

import android.content.Context
import com.daily.notes.data.shell.BackendCliRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File

/** Runs the manager's own short-lived, arm64 network-history tool as root. */
class TrafficStatisticsRepository(
    private val context: Context,
    private val backend: BackendCliRepository,
) {
    suspend fun clear(): Int = withContext(Dispatchers.IO) {
        val binary = File(context.applicationInfo.nativeLibraryDir, "libdn_netstats.so")
        check(binary.isFile) { "Network statistics tool is missing" }
        val lockFile = File(context.filesDir, "netstats.lock")
        backend.withNewRootShell {
            check(isRoot) { "Root shell unavailable" }
            val output = ArrayList<String>()
            val errors = ArrayList<String>()
            val result = newJob().add(
                "DN_NETSTATS_LOCK_FILE=${lockFile.absolutePath} ${binary.absolutePath} clear"
            ).to(output, errors).exec()
            check(result.isSuccess) { errors.joinToString("\n").ifBlank { "Network statistics clear failed" } }
            val response = JSONObject(output.lastOrNull { it.trimStart().startsWith("{") }
                ?: error("Network statistics result missing"))
            check(response.optString("scope") == "users10-11-and-removed") { "Unexpected clear scope" }
            val after = response.getJSONObject("after")
            check(listOf("cellBytes", "wifiBytes", "cellTagBytes", "wifiTagBytes")
                .all { after.optLong(it) == 0L }) { "Network history still contains target traffic" }
            response.getInt("changedRecords")
        }
    }
}
