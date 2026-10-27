package com.daily.notes.data.terminal

import android.content.Context
import android.system.Os
import com.daily.notes.R
import java.io.File

internal class DnTerminalEnvironment(private val context: Context) {
    private val root = File(context.filesDir, "terminal")
    private val native = File(context.applicationInfo.nativeLibraryDir)
    private val home = File(root, "home")
    private val temporary = File(root, "tmp")
    private val library = File(root, "lib")
    private val tools = File(root, "tools")
    private val startup = File(root, "startup")

    private fun link(name: String, target: File, directory: File) {
        val output = File(directory, name)
        if (runCatching { Os.readlink(output.path) }.getOrNull() == target.path) return
        if (output.exists() || runCatching { Os.lstat(output.path) }.isSuccess) check(output.delete())
        Os.symlink(target.path, output.path)
    }

    private fun asset(name: String, destination: File) {
        val children = context.assets.list(name).orEmpty()
        if (children.isNotEmpty()) {
            destination.mkdirs()
            children.forEach { asset("$name/$it", File(destination, it)) }
        } else {
            destination.parentFile?.mkdirs()
            val bytes = context.assets.open(name).use { it.readBytes() }
            if (!destination.exists() || !destination.readBytes().contentEquals(bytes)) destination.writeBytes(bytes)
        }
    }

    @Synchronized
    fun prepare(requireSupervisor: Boolean = true) {
        listOf(root, home, temporary, library, tools, startup).forEach { check(it.isDirectory || it.mkdirs()) }
        native.listFiles().orEmpty().filter { it.name.endsWith(".so") }.forEach { link(it.name, it, library) }
        mapOf("libreadline.so.8" to "libreadline.so", "libhistory.so.8" to "libhistory.so",
            "libncursesw.so.6" to "libncursesw.so").forEach { (name, target) ->
            val file = File(native, target)
            if (file.exists()) link(name, file, library)
        }
        val bash = File(native, "libdn_bash.so")
        check(bash.isFile && bash.canExecute()) { "Built-in Bash is not executable" }
        link("bash", bash, tools)
        check(File(tools, "bash").canExecute()) { "Shell entry is not executable" }
        asset("dn-terminal/terminfo", File(root, "terminfo"))
        asset("dn-terminal/bashrc", File(root, "bashrc"))
        asset("dn-terminal/start-shell", File(startup, "sh"))
        check(File(startup, "sh").setExecutable(true, true))
        if (requireSupervisor) {
            val supervisor = File(native, "libdn_session.so")
            check(supervisor.isFile && supervisor.canExecute()) { "Session manager is not executable" }
        }
    }

    val startupShell: String get() = File(startup, "sh").path

    fun variables(directory: String, script: String?, token: String, mode: String, control: File): Array<String> = arrayOf(
        "TERM=xterm-256color", "COLORTERM=truecolor", "LANG=C.UTF-8", "USER=root", "LOGNAME=root",
        "HOME=${home.path}", "TMPDIR=${temporary.path}", "LD_LIBRARY_PATH=${library.path}",
        "SHELL=${File(tools, "bash").path}",
        "TERMINFO=${File(root, "terminfo").path}",
        "PATH=${startup.path}:/system/bin:/system/xbin:/vendor/bin:/product/bin:/data/adb/ksu/bin",
        "ANDROID_ROOT=/system", "ANDROID_DATA=/data", "DN_TOOLS=${tools.path}",
        "DN_BASH=${File(native, "libdn_bash.so").path}", "DN_RC=${File(root, "bashrc").path}",
        "DN_CWD=$directory", "DN_SCRIPT=${script.orEmpty()}", "DN_SESSION_ID=$token",
        "DN_MODE=$mode", "DN_CONTROL_DIR=${control.path}", "DN_APP_UID=${android.os.Process.myUid()}",
        "DN_OWNER_PID=${android.os.Process.myPid()}",
        "DN_OWNER_START=${File("/proc/self/stat").readText().substringAfterLast(") ").trim().split(Regex("\\s+"))[19]}",
        "DN_SUPERVISOR=${File(native, "libdn_session.so").path}",
        "DN_EXIT_LABEL=${context.getString(R.string.dn_terminal_exit_code)}",
        "DN_INTERPRETER_ERROR=${context.getString(R.string.dn_terminal_interpreter_error)}",
    )
}
