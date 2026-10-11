#!/usr/bin/env python3
"""D70b true PTY integration using pinned Termux terminal-view 0.118.0.

Termux native PTY + terminal-emulator handle keyboard, ANSI, cursor, resize and
interactive applications. Start ReSukiSU's existing ksud debug su -g in PTY.
Never insert an extra 'su' command. Preserve DN69 file pane and Root features.
"""
from pathlib import Path
base=Path("source/manager")
app=base/"app"
tools=app/"src/main/java/com/resukisu/resukisu/ui/screen/main/ToolsPage.kt"
gradle=app/"build.gradle.kts"
rules=app/"proguard-rules.pro"
terminal=tools.parent/"DnPtyTerminal.kt"

if terminal.exists(): raise SystemExit("D70b duplicate terminal integration")
terminal.write_text(r'''package com.resukisu.resukisu.ui.screen.main

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.util.Log
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.inputmethod.InputMethodManager
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import com.termux.terminal.TerminalSession
import com.termux.terminal.TerminalSessionClient
import com.termux.view.TerminalView
import com.termux.view.TerminalViewClient

// Termux's actual /dev/ptmx session; no fake prompt, output-line editor or pipes.
internal class DnPtyTerminalController(private val daemon: String) {
    private var session: TerminalSession? = null
    private var display: TerminalView? = null
    private val awaiting = mutableListOf<String>()
    var status by mutableStateOf("未启动")
        private set
    var path by mutableStateOf("/")
        private set
    var failure by mutableStateOf("")
        private set

    private val sessionClient = object : TerminalSessionClient {
        override fun onTextChanged(changedSession: TerminalSession) {
            display?.post { display?.onScreenUpdated() }
        }
        override fun onTitleChanged(changedSession: TerminalSession) = Unit
        override fun onSessionFinished(finishedSession: TerminalSession) {
            status = "会话结束"
            display?.post { display?.onScreenUpdated() }
        }
        override fun onCopyTextToClipboard(session: TerminalSession, text: String) {
            val ctx = display?.context ?: return
            val cb = ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            cb.setPrimaryClip(ClipData.newPlainText("Terminal", text))
        }
        override fun onPasteTextFromClipboard(session: TerminalSession) {
            val ctx = display?.context ?: return
            val cb = ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            val text = cb.primaryClip?.getItemAt(0)?.coerceToText(ctx)?.toString().orEmpty()
            send(text)
        }
        override fun onBell(session: TerminalSession) = Unit
        override fun onColorsChanged(session: TerminalSession) {
            display?.post { display?.invalidate() }
        }
        override fun onTerminalCursorStateChange(state: Boolean) = Unit
        override fun getTerminalCursorStyle(): Int? = null
        override fun logError(tag: String, message: String) { Log.e(tag, message) }
        override fun logWarn(tag: String, message: String) { Log.w(tag, message) }
        override fun logInfo(tag: String, message: String) { Log.i(tag, message) }
        override fun logDebug(tag: String, message: String) { Log.d(tag, message) }
        override fun logVerbose(tag: String, message: String) = Unit
        override fun logStackTraceWithMessage(tag: String, message: String, e: Exception) {
            Log.w(tag, message, e)
        }
        override fun logStackTrace(tag: String, e: Exception) { Log.w(tag, e) }
    }
    private inner class TerminalInputClient(private val context: Context) : TerminalViewClient {
        override fun onScale(scale: Float): Float = scale.coerceIn(0.6f, 2.5f)
        override fun onSingleTapUp(e: MotionEvent) {
            display?.let {
                it.requestFocus()
                (context.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager)
                    .showSoftInput(it, InputMethodManager.SHOW_IMPLICIT)
            }
        }
        override fun shouldBackButtonBeMappedToEscape(): Boolean = false
        override fun shouldEnforceCharBasedInput(): Boolean = false
        override fun shouldUseCtrlSpaceWorkaround(): Boolean = false
        override fun isTerminalViewSelected(): Boolean = true
        override fun copyModeChanged(copyMode: Boolean) = Unit
        override fun onKeyDown(keyCode: Int, e: KeyEvent, session: TerminalSession): Boolean = false
        override fun onKeyUp(keyCode: Int, e: KeyEvent): Boolean = false
        override fun onLongPress(event: MotionEvent): Boolean = false
        override fun readControlKey(): Boolean = false
        override fun readAltKey(): Boolean = false
        override fun readShiftKey(): Boolean = false
        override fun readFnKey(): Boolean = false
        override fun onCodePoint(codePoint: Int, ctrlDown: Boolean, session: TerminalSession): Boolean = false
        override fun onEmulatorSet() {
            flushPending()
        }
        override fun logError(tag: String, message: String) { Log.e(tag, message) }
        override fun logWarn(tag: String, message: String) { Log.w(tag, message) }
        override fun logInfo(tag: String, message: String) { Log.i(tag, message) }
        override fun logDebug(tag: String, message: String) { Log.d(tag, message) }
        override fun logVerbose(tag: String, message: String) = Unit
        override fun logStackTraceWithMessage(tag: String, message: String, e: Exception) {
            Log.w(tag, message, e)
        }
        override fun logStackTrace(tag: String, e: Exception) { Log.w(tag, e) }
    }

    fun ensure() {
        if (session?.isRunning == true) return
        failure = ""
        try {
            session = TerminalSession(
                daemon, "/",
                arrayOf(daemon, "debug", "su", "-g"),
                arrayOf(
                    "TERM=xterm-256color",
                    "COLORTERM=truecolor",
                    "LANG=C.UTF-8",
                    "HOME=/data/local/tmp",
                    "TMPDIR=/data/local/tmp",
                    "PATH=/system/bin:/system/xbin:/vendor/bin:/product/bin:/data/adb/ksu/bin",
                    "ANDROID_ROOT=/system",
                    "ANDROID_DATA=/data"
                ),
                3000, sessionClient,
            )
            status = "Root PTY"
        } catch (t: Throwable) {
            status = "终端启动失败"
            failure = t.message ?: t.javaClass.simpleName
            Log.e("DailyNotesPTY", "PTY start failed", t)
        }
    }

    fun attach(view: TerminalView) {
        ensure()
        display = view
        view.setTerminalViewClient(TerminalInputClient(view.context))
        view.setTextSize(15)
        session?.let { view.attachSession(it) }
        view.isFocusable = true
        view.isFocusableInTouchMode = true
        view.requestFocus()
    }

    fun detach() { display = null }
    fun send(text: String) {
        if (text.isEmpty()) return
        ensure()
        val running = session
        if (running != null && running.isRunning) {
            val bytes = text.toByteArray(Charsets.UTF_8)
            running.write(bytes, 0, bytes.size)
        } else {
            awaiting.add(text)
        }
    }
    fun sendLine(command: String) = send(command + "\n")
    fun changeDirectory(destination: String) {
        path = destination
        sendLine("cd " + "'" + destination.replace("'", "'\"'\"'") + "'")
    }
    private fun flushPending() {
        val terminal = session ?: return
        if (!terminal.isRunning) return
        awaiting.forEach { line ->
            val bytes = line.toByteArray(Charsets.UTF_8)
            terminal.write(bytes, 0, bytes.size)
        }
        awaiting.clear()
    }
    fun clear() { send("\u000c") }
    fun interrupt() { send("\u0003") }
    fun stop() {
        session?.finishIfRunning()
        session = null
        awaiting.clear()
        status = "已停止"
    }
    fun close() {
        stop()
        display = null
    }
}

@Composable
internal fun DnPtyTerminalPanel(
    controller: DnPtyTerminalController,
    onFiles: () -> Unit,
) {
    val ctx = LocalContext.current
    DisposableEffect(controller) { onDispose { controller.detach() } }
    Column(Modifier.fillMaxSize()) {
        Row(
            modifier = Modifier.fillMaxWidth().height(53.dp).padding(horizontal = 2.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            TextButton(onClick = onFiles) { Text("‹ 文件") }
            Column(Modifier.weight(1f)) {
                Text("Root 终端", style = MaterialTheme.typography.titleMedium)
                Text(controller.status + " · " + controller.path,
                    style = MaterialTheme.typography.labelSmall,
                    maxLines = 1)
            }
            TextButton(onClick = { controller.interrupt() }) { Text("中断") }
            TextButton(onClick = { controller.clear() }) { Text("清屏") }
        }
        if (controller.failure.isNotBlank()) {
            Text(controller.failure, color = MaterialTheme.colorScheme.error)
        }
        AndroidView(
            factory = { context ->
                TerminalView(context, null).apply {
                    setBackgroundColor(android.graphics.Color.BLACK)
                    controller.attach(this)
                }
            },
            update = {},
            modifier = Modifier.fillMaxWidth().weight(1f)
                .background(Color.Black),
        )
        Row(
            modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState())
                .padding(vertical = 2.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            val extra = listOf(
                "ESC" to "\u001b",
                "TAB" to "\t",
                "CTRL+C" to "\u0003",
                "↑" to "\u001b[A",
                "↓" to "\u001b[B",
                "←" to "\u001b[D",
                "→" to "\u001b[C",
                "HOME" to "\u001b[H",
                "END" to "\u001b[F",
                "ENTER" to "\r",
            )
            extra.forEach { (label, code) ->
                TextButton(onClick = { controller.send(code) }) { Text(label) }
            }
            TextButton(onClick = { controller.stop(); controller.ensure() }) {
                Text("重开")
            }
        }
    }
}
''', encoding="utf-8")

g=gradle.read_text(encoding="utf-8")
anchor='''    implementation(libs.com.github.topjohnwu.libsu.core)
'''
if g.count(anchor)!=1: raise SystemExit("D70b Gradle anchor drift")
g=g.replace(anchor,'''    // Embedded interactive PTY/ANSI engine. Termux terminal libraries are
    // Apache-2.0-licensed components (termux-app has separate GPLv3 code).
    implementation("com.termux.termux-app:terminal-view:0.118.0")
'''+anchor,1)
gradle.write_text(g,encoding="utf-8")
r=rules.read_text(encoding="utf-8")
r+='''

# Keep Termux PTY JNI class names and Java callbacks (native exported symbols).
-keep class com.termux.terminal.JNI { *; }
-keep class com.termux.terminal.TerminalSession { *; }
-keep class com.termux.terminal.TerminalSessionClient { *; }
-keep class com.termux.view.TerminalView { *; }
-keep class com.termux.view.TerminalViewClient { *; }
'''
rules.write_text(r,encoding="utf-8")

s=tools.read_text(encoding="utf-8")
begin=s.index('''    val session = remember {
        RootInteractiveSession(''')
end=s.index('''    suspend fun execRoot(command: String): CommandResult''',begin)
s=s[:begin]+'''    val pty = remember(ksuCli) { DnPtyTerminalController(ksuCli.getKsuDaemonPath()) }
    DisposableEffect(pty) { onDispose { pty.close() } }

'''+s[end:]
begin=s.index('''    fun ensureTerminalStarted() {''')
end=s.index('''    fun loadEditor(path: String) {''',begin)
s=s[:begin]+'''    fun ensureTerminalStarted() { pty.ensure() }
    fun openTerminalAt(path: String) {
        pty.changeDirectory(path)
        terminalHint = "Root PTY · " + path
        tab = 1
    }
    fun runScriptInTerminal(path: String) {
        pty.changeDirectory(parentPath(path))
        pty.sendLine("/system/bin/sh " + shellQuote(path))
        terminalHint = "Root PTY · 脚本"
        tab = 1
    }
    fun sendTerminalLine() {
        if (terminalInput.isNotBlank()) {
            pty.sendLine(terminalInput)
            terminalInput = ""
        }
    }

'''+s[end:]

start=s.index('''            } else {
                Row(''',s.index('''                DnDualFiles('''))
end=s.index('''            }
        }
    }

    if (showActions) {''',start)
s=s[:start]+'''            } else {
                DnPtyTerminalPanel(
                    controller = pty,
                    onFiles = { tab = 0 },
                )
'''+s[end:]
# A proper PTY must echo commands itself, avoiding duplicate synthetic lines.
assert 'RootInteractiveSession(listOf(' not in s
assert 'DnPtyTerminalPanel(' in s
assert 'fun runScriptInTerminal(path: String)' in s
assert 'fun sendTerminalLine()' in s
assert 'DnDualFiles(' in s
tools.write_text(s,encoding="utf-8")
print("D70b: Termux terminal-view 0.118.0 PTY + xterm renderer + live IME, Root ksud and terminal controls wired.")
