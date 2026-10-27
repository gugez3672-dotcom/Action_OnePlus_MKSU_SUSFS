package com.daily.notes.data.shell

import android.content.Context
import com.topjohnwu.superuser.Shell
import com.topjohnwu.superuser.io.SuFile
import com.topjohnwu.superuser.io.SuFileInputStream
import com.topjohnwu.superuser.io.SuFileOutputStream
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

/** DN feature adapter. Root sessions use the official manager's current backend. */
class BackendCliRepository(context: Context) {
    private val nativeLibraryDir = context.applicationInfo.nativeLibraryDir

    fun getBackendPath(): String = File(nativeLibraryDir, "libnote_runtime.so").absolutePath

    fun getRootShell(globalMnt: Boolean = false): Shell =
        com.daily.notes.ui.util.createRootShell(globalMnt)

    inline fun <T> withNewRootShell(globalMnt: Boolean = false, block: Shell.() -> T): T =
        com.daily.notes.ui.util.createRootShell(globalMnt).use(block)

    private fun shellQuote(value: String) = "'" + value.replace("'", "'\"'\"'") + "'"
    /** Result of an ADB toggle: the observed switch state, kept apart from the WG keepalive sync. */
    data class AdbToggleResult(val observed: Boolean?, val heartbeatError: Int?)

    /** USB debugging is device-wide; a read never starts adbd and never touches the keepalive. */
    suspend fun getUsbDebugEnabled(): Boolean? = withContext(Dispatchers.IO) {
        withNewRootShell {
            if (!isRoot) return@withNewRootShell null
            readUsbDebug(this)
        }
    }

    /** Apply USB debugging, then sync the keepalive. A sync failure never hides the applied state. */
    suspend fun setUsbDebugEnabled(requested: Boolean, tcpPort: Int?): AdbToggleResult =
        withContext(Dispatchers.IO) {
            if (tcpPort != null && tcpPort !in 1024..65535) return@withContext AdbToggleResult(null, null)
            withNewRootShell {
                if (!isRoot) return@withNewRootShell AdbToggleResult(null, null)
                val value = if (requested) "1" else "0"
                if (requested) newJob().add(adbTcpPortCommand(tcpPort)).exec()
                newJob().add("/system/bin/settings put global adb_enabled $value").exec()
                if (!requested) newJob().add(adbTcpPortCommand(null)).exec()
                // Report what the device actually shows, whatever the individual steps returned.
                AdbToggleResult(readUsbDebug(this), syncAdbHeartbeat(this, tcpPort))
            }
        }

    /** Save the shared choice, apply it only with USB debugging on, then sync WG. */
    suspend fun applyAdbTcpPort(tcpPort: Int?, port: Int): AdbToggleResult = withContext(Dispatchers.IO) {
        if (port !in 1024..65535 || (tcpPort != null && tcpPort !in 1024..65535)) {
            return@withContext AdbToggleResult(null, null)
        }
        withNewRootShell {
            if (!isRoot) return@withNewRootShell AdbToggleResult(null, null)
            newJob().add(adbTcpChoiceCommand(tcpPort)).add(
                "if [ \"\$(/system/bin/settings get global adb_enabled)\" = 1 ]; then " +
                    "${adbTcpPortCommand(tcpPort)} && " +
                    "{ if [ \"\$(getprop init.svc.adbd)\" = running ]; then setprop ctl.restart adbd; fi; }; " +
                    "else ${adbTcpPortCommand(null)}; fi"
            ).exec()
            AdbToggleResult(readAdbTcp(this, port), syncAdbHeartbeat(this, port))
        }
    }

    /** Every Android user reads the volatile port, or the saved choice with USB off. Read-only. */
    suspend fun getAdbTcpEnabled(tcpPort: Int): Boolean? = withContext(Dispatchers.IO) {
        if (tcpPort !in 1024..65535) return@withContext null
        withNewRootShell {
            if (!isRoot) return@withNewRootShell null
            readAdbTcp(this, tcpPort)
        }
    }

    /**
     * Reconcile the WG keepalive with the actual ADB state (25 only while network ADB listens,
     * otherwise 0). Returns null on success or the helper's exit code. Event-driven only.
     */
    suspend fun reconcileAdbHeartbeat(tcpPort: Int): Int? = withContext(Dispatchers.IO) {
        withNewRootShell {
            if (!isRoot) return@withNewRootShell -1
            syncAdbHeartbeat(this, tcpPort)
        }
    }

    private fun readUsbDebug(owned: Shell): Boolean? {
        val lines = ArrayList<String>()
        val read = owned.newJob().add("/system/bin/settings get global adb_enabled").to(lines, null).exec()
        return if (!read.isSuccess) null else when (lines.lastOrNull()?.trim()) {
            "1" -> true
            "0" -> false
            else -> null
        }
    }

    private fun readAdbTcp(owned: Shell, tcpPort: Int): Boolean? {
        val lines = ArrayList<String>()
        val read = owned.newJob().add(
            "if [ \"\$(/system/bin/settings get global adb_enabled)\" = 1 ]; then " +
                "if [ \"\$(getprop service.adb.tcp.port)\" = $tcpPort ]; then echo on; else echo off; fi; " +
                "elif [ \"\$(cat $adbTcpChoicePath 2>/dev/null)\" = $tcpPort ]; then echo on; else echo off; fi"
        ).to(lines, null).exec()
        return if (!read.isSuccess) null else when (lines.lastOrNull()?.trim()) {
            "on" -> true
            "off" -> false
            else -> null
        }
    }

    private val adbTcpChoicePath = "/data/adb/ksu/.adb_tcp_port"
    private val heartbeatAssets = context.assets
    private val heartbeatPath = "/data/adb/ksu/dn-adb-heartbeat"

    private fun adbTcpChoiceCommand(tcpPort: Int?): String =
        if (tcpPort != null && tcpPort in 1024..65535) {
            "umask 077; printf '%s\\n' $tcpPort > $adbTcpChoicePath && chmod 600 $adbTcpChoicePath"
        } else "rm -f $adbTcpChoicePath"

    /** Returns null on success, otherwise an error code (helper exit code, or 90+ for install steps). */
    private fun syncAdbHeartbeat(owned: Shell, tcpPort: Int?): Int? = runCatching {
        val config = SuFile("/data/adb/box/sing-box/config.json").apply { shell = owned }
        if (!config.isFile) return@runCatching null
        if (!owned.newJob().add("umask 077; mkdir -p $heartbeatPath && chmod 700 $heartbeatPath").exec().isSuccess) return@runCatching 91
        if (!owned.newJob().add("if [ ! -e $heartbeatPath/config.before-d110.json ]; then cp -p /data/adb/box/sing-box/config.json $heartbeatPath/config.before-d110.json; fi").exec().isSuccess) return@runCatching 92
        fun installRootFile(path: String, content: ByteArray, mode: String): Boolean {
            val file = SuFile(path).apply { shell = owned }
            if (file.isFile && SuFileInputStream.open(file).use { it.readBytes() }.contentEquals(content)) return true
            val temporaryPath = "$path.${android.os.Process.myPid()}.${System.nanoTime()}.new"
            val temporary = SuFile(temporaryPath).apply { shell = owned }
            return try {
                SuFileOutputStream.open(temporary).use { it.write(content) }
                owned.newJob().add("chmod $mode ${shellQuote(temporaryPath)} && mv -f ${shellQuote(temporaryPath)} ${shellQuote(path)}").exec().isSuccess
            } finally {
                owned.newJob().add("rm -f ${shellQuote(temporaryPath)}").exec()
            }
        }
        for (name in listOf("control.sh", "keepalive.awk")) {
            val bytes = heartbeatAssets.open("dn-adb-heartbeat/$name").use { it.readBytes() }
            if (!installRootFile("$heartbeatPath/$name", bytes, "600")) return@runCatching 93
        }
        val servicePath = "/data/adb/box/scripts/box.service"
        val service = SuFile(servicePath).apply { shell = owned }
        val original = SuFileInputStream.open(service).use { it.readBytes() }.toString(Charsets.UTF_8)
        val marker = "# D110: sync WG keepalive before the core starts."
        if (!original.contains(marker)) {
            val anchor = "start_bin() {\n"
            if (original.split(anchor).size != 2) return@runCatching 94
            val backup = "$heartbeatPath/box.service.before-d110"
            if (!owned.newJob().add("if [ ! -e $backup ]; then cp -p $servicePath $backup; fi").exec().isSuccess) return@runCatching 95
            val hook = "    $marker\n" +
                "    /system/bin/sh $heartbeatPath/control.sh prepare || log Error 'D110 heartbeat sync failed; retaining proxy configuration'\n"
            if (!installRootFile(servicePath, original.replace(anchor, anchor + hook).toByteArray(Charsets.UTF_8), "700")) return@runCatching 96
            if (!owned.newJob().add("chown 0:3005 $servicePath").exec().isSuccess) return@runCatching 97
        }
        val port = if (tcpPort != null && tcpPort in 1024..65535) " $tcpPort" else ""
        val result = owned.newJob().add("/system/bin/sh $heartbeatPath/control.sh sync$port").exec()
        if (result.isSuccess) null else result.code
    }.getOrDefault(99)

    // Never persist the port; remove legacy values before setting the volatile one.
    private fun adbTcpPortCommand(tcpPort: Int?): String {
        val resetprop = "/data/adb/ksu/bin/resetprop"
        val clear = "if [ -x $resetprop ]; then $resetprop -p -d persist.adb.tcp.port 2>/dev/null; " +
            "$resetprop -d service.adb.tcp.port 2>/dev/null; else setprop service.adb.tcp.port ''; fi; true"
        return if (tcpPort != null && tcpPort in 1024..65535) "$clear; setprop service.adb.tcp.port $tcpPort" else clear
    }

}
