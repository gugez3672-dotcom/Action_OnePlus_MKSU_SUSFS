package com.daily.notes.data.files

import android.content.Context
import com.daily.notes.data.shell.BackendCliRepository
import java.io.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/** Gives the system installer an app-readable copy, including for root-only sources. */
internal class DnApkInstaller(private val context: Context) {
    private fun quote(value: String) = "'" + value.replace("'", "'\"'\"'") + "'"

    suspend fun stage(cli: BackendCliRepository, source: String): File = withContext(Dispatchers.IO) {
        require(source.startsWith('/') && source.endsWith(".apk", ignoreCase = true))
        val directory = File(context.cacheDir, "dn-apk-installer")
        check(directory.isDirectory || directory.mkdirs())
        val expired = System.currentTimeMillis() - 60 * 60 * 1000L
        directory.listFiles()?.filter { it.isFile && it.lastModified() < expired }?.forEach { it.delete() }

        // Create as the app first. Root only truncates and writes the existing inode,
        // so FileProvider can still read it with the app's owner and SELinux label.
        val target = File.createTempFile("package-", ".apk", directory)
        try {
            val output = arrayListOf<String>()
            val errors = arrayListOf<String>()
            val result = cli.withNewRootShell(globalMnt = true) {
                newJob().add("/system/bin/cat " + quote(source) + " > " + quote(target.absolutePath))
                    .to(output, errors).exec()
            }
            check(result.isSuccess && target.length() > 0L) {
                errors.joinToString("\n").ifBlank { "APK copy failed (${result.code})" }
            }
            target
        } catch (e: Exception) {
            target.delete()
            throw e
        }
    }
}
