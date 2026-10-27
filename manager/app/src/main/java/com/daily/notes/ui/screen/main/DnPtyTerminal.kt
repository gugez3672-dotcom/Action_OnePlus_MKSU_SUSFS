package com.daily.notes.ui.screen.main

import android.content.ClipboardManager
import android.content.Context
import android.view.GestureDetector
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.inputmethod.InputMethodManager
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.twotone.ArrowDropDown
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.lifecycle.ViewModel
import com.daily.notes.terminal.DnShellTermSession
import com.daily.notes.data.terminal.DnTerminalEnvironment
import com.daily.notes.R
import com.daily.notes.ui.component.DnToolSwitchButton
import com.daily.notes.ui.component.DnToolSwitchTarget
import jackpal.androidterm.emulatorview.EmulatorView
import jackpal.androidterm.emulatorview.ColorScheme
import java.io.File
import java.util.UUID
import kotlin.math.roundToInt

/**
 * D99 terminal: an MT-style interactive root terminal built on the ATE emulator
 * and a forkpty shell that is a direct child of the app. Nothing is spawned
 * until the user opens a session; closing a session (or swiping the app away)
 * closes the pty master, which SIGHUPs the shell — no supervisor, no leak.
 */
internal class DnTerminalViewModel : ViewModel() {
    var showingTerminal by mutableStateOf(false)
    fun controller(context: Context, daemon: String): DnPtyTerminalController =
        DnTerminalLifetime.controller(context, daemon)
}

internal class DnPtyTerminalController(private val context: Context, @Suppress("UNUSED_PARAMETER") daemon: String) {
    private val environment = DnTerminalEnvironment(context)
    internal class Session(val id: String, val number: Int, val labelText: String,
            val terminal: DnShellTermSession, val isScript: Boolean = false) {
        val label: String get() = labelText
        var exitCode by mutableStateOf<Int?>(null)
        var closing by mutableStateOf(false)
        val background: Boolean get() = false
        val running get() = exitCode == null
    }

    val sessions = mutableStateListOf<Session>()
    var activeId by mutableStateOf<String?>(null)
        private set
    val active: Session? get() = sessions.firstOrNull { it.id == activeId }
    // Background sessions were removed in D99; keep the field for UI compatibility.
    val backgroundTasks: List<Session> = emptyList()
    var failure by mutableStateOf("")
        private set
    var control by mutableStateOf(false)
    var alt by mutableStateOf(false)
    var keepAwake by mutableStateOf(false)
    // Font size in dp. ATE's EmulatorView.setTextSize multiplies by density itself.
    // Every launch opens at 10 (user's choice; MT's own default is 12).
    var fontSize by mutableStateOf(10)
        private set

    private var display: EmulatorView? = null

    /** No-op: D99 never auto-starts a session (unlike the old auto-open). */
    fun ensure() {}

    private fun quote(value: String) = "'" + value.replace("'", "'\\''") + "'"

    // A session is created only by an explicit terminal or file-run action.
    fun newRoot() = startShell("/sdcard")

    private fun startShell(directory: String, script: String? = null) {
        failure = ""
        try {
            environment.prepare(requireSupervisor = false)
            val root = File(context.filesDir, "terminal")
            val native = File(context.applicationInfo.nativeLibraryDir)
            val bash = File(native, "libdn_bash.so")
            val rc = File(root, "bashrc")
            val workDir = if (script == null) "/sdcard" else directory
            val vars = linkedMapOf(
                "HOME" to File(root, "home").path,
                "TMPDIR" to File(root, "tmp").path,
                "LD_LIBRARY_PATH" to File(root, "lib").path,
                "SHELL" to bash.path,
                "TERMINFO" to File(root, "terminfo").path,
                "DN_BASH" to bash.path,
                "DN_RC" to rc.path,
                "DN_EXIT_LABEL" to context.getString(R.string.dn_terminal_exit_code),
                "DN_INTERPRETER_ERROR" to context.getString(R.string.dn_terminal_interpreter_error),
                "LANG" to "C.UTF-8",
                "TERM" to "xterm-256color",
                "PATH" to "${File(root, "tools").path}:/system/bin:/system/xbin:/vendor/bin:/product/bin:/data/adb/ksu/bin",
            )
            val setup = vars.entries.joinToString(" ") { (key, value) -> "$key=${quote(value)}" }
            val initialCommand = buildString {
                append("export ").append(setup).append("; ")
                append("cd ").append(quote(workDir)).append(" 2>/dev/null || cd /sdcard; ")
                append("printf '\\033[2J\\033[H'; ")
                append("export DN_SCRIPT=").append(quote(script.orEmpty())).append("; ")
                append("exec ").append(quote(bash.path)).append(" --noprofile --rcfile ")
                    .append(quote(rc.path)).append(" -i")
            }
            val cmd = "/system/bin/su"
            // Pass setup as su's command argument. Typing it into an echoing
            // PTY leaves a long, wrapped copy in the terminal scrollback.
            val argv = arrayOf("su", "-c", initialCommand)
            val env = (vars.entries.map { (key, value) -> "$key=$value" } +
                listOf("ANDROID_ROOT=/system", "ANDROID_DATA=/data", "USER=root", "LOGNAME=root")).toTypedArray()
            val term = DnShellTermSession(cmd, argv, env)
            // Reuse the lowest free number so closing session 1 frees "1" again.
            val number = generateSequence(1) { it + 1 }.first { n -> sessions.none { it.number == n } }
            val record = Session(UUID.randomUUID().toString(), number,
                context.getString(R.string.dn_terminal_root_number, number), term, script != null)
            term.onExit = { code ->
                record.exitCode = code
                // An interactive shell the user exits closes at once. A file run
                // from the file manager keeps its output on screen (its result is
                // what the user wants to read) until Enter closes the session.
                if (!record.isScript) end(record.id)
                else display?.invalidate()
                syncLifetime()
            }
            term.onEnterAfterExit = { end(record.id) }
            sessions.add(record)
            activeId = record.id
            attachActive()
            syncLifetime()
        } catch (e: Exception) {
            failure = context.getString(R.string.dn_terminal_start_failed, e.message ?: e.javaClass.simpleName)
        }
    }

    /** Opening the terminal from Files: reuse a session, or start one on demand. */
    fun openAt(@Suppress("UNUSED_PARAMETER") directory: String) {
        if (sessions.isEmpty()) newRoot() else activeId?.let { select(it) } ?: select(sessions.last().id)
    }

    /** Run a file in a foreground root session, preserving its output on screen. */
    fun openScript(path: String) = startShell(path.substringBeforeLast('/').ifEmpty { "/" }, path)
    fun closeBackgroundWindow(id: String? = activeId) {}
    fun showBackground(@Suppress("UNUSED_PARAMETER") task: Session) {}

    fun select(id: String) {
        val record = sessions.firstOrNull { it.id == id } ?: return
        activeId = record.id
        control = false
        alt = false
        display?.let { view ->
            view.attachSession(record.terminal)
            view.requestFocus()
            view.post { keyboard(true) }
        }
    }

    fun attach(view: EmulatorView) {
        display = view
        view.setDensity(context.resources.displayMetrics)
        view.setTextSize(fontSize)
        // Colours sampled from MT's terminal: light-grey text, grey block cursor.
        view.setColorScheme(ColorScheme(0xfff0f0f0.toInt(), 0xff000000.toInt(),
            0xff000000.toInt(), 0xffa9aaa9.toInt()))
        view.isFocusable = true
        view.isFocusableInTouchMode = true
        // ATE's own tap only requests focus; once the IME was dismissed (Back,
        // system gesture) nothing brought it back. A tap always shows it here;
        // returning false keeps ATE's mouse-tracking tap handling intact.
        view.setExtGestureListener(object : GestureDetector.SimpleOnGestureListener() {
            override fun onSingleTapUp(e: MotionEvent): Boolean {
                keyboard(true)
                return false
            }
        })
        active?.let { view.attachSession(it.terminal) }
        view.onResume()
        view.requestFocus()
    }

    private fun attachActive() {
        val view = display ?: return
        active?.let { view.attachSession(it.terminal) }
    }

    fun detach() {
        display?.onPause()
        display = null
    }

    fun key(code: Int) {
        if (active?.exitCode != null) return
        display?.let { view ->
            view.requestFocus()
            view.onKeyDown(code, KeyEvent(KeyEvent.ACTION_DOWN, code))
            view.onKeyUp(code, KeyEvent(KeyEvent.ACTION_UP, code))
            control = false
            alt = false
        }
    }

    fun toggleControl() {
        control = !control
        display?.setSoftwareControlKeyActive(control)
    }

    fun toggleAlt() {
        alt = !alt
        display?.setSoftwareAltKeyActive(alt)
    }

    private fun clipboard() = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
    fun paste() {
        val session = active?.terminal ?: return
        if (!session.isRunning) return
        val text = clipboard().primaryClip?.getItemAt(0)?.coerceToText(context)?.toString() ?: return
        if (text.isNotEmpty()) session.write(text)
    }

    fun reset() {
        active?.terminal?.reset()
    }

    fun resizeFont(value: Int) {
        fontSize = value.coerceIn(8, 36)
        display?.setTextSize(fontSize)
    }

    fun toggleWake() { keepAwake = !keepAwake; syncLifetime() }

    fun end(id: String? = activeId) {
        val record = sessions.firstOrNull { it.id == id } ?: return
        if (record.closing) return
        record.closing = true
        val index = sessions.indexOf(record)
        if (activeId == record.id) {
            val remaining = sessions.filter { it !== record }
            val next = remaining.getOrNull(index.coerceAtMost(remaining.lastIndex))
            if (next == null) {
                keyboard(false)
                display?.detachSession()
                activeId = null
            } else select(next.id)
        }
        sessions.remove(record)
        // Switch the view away before the old emulator and PTY are released.
        runCatching { record.terminal.finish() }
        syncLifetime()
    }

    fun closeOrdinary() {
        display?.detachSession()
        activeId = null
        sessions.toList().forEach { runCatching { it.terminal.finish() } }
        sessions.clear()
        syncLifetime()
    }

    fun keyboard(show: Boolean? = null) {
        val view = display ?: return
        val imm = view.context.getSystemService(InputMethodManager::class.java)
        val insets = ViewCompat.getWindowInsetsController(view)
        val visible = ViewCompat.getRootWindowInsets(view)?.isVisible(WindowInsetsCompat.Type.ime()) == true
        if (show == true || (show == null && !visible)) {
            // Focus first: the IME only serves the focused view. If the window has
            // not yet made it the served view, retry on the next frame.
            if (!view.hasFocus()) view.requestFocus()
            insets?.show(WindowInsetsCompat.Type.ime())
            if (imm?.showSoftInput(view, InputMethodManager.SHOW_IMPLICIT) != true) {
                view.post {
                    view.requestFocus()
                    imm?.showSoftInput(view, InputMethodManager.SHOW_IMPLICIT)
                }
            }
        } else {
            insets?.hide(WindowInsetsCompat.Type.ime())
            imm?.hideSoftInputFromWindow(view.windowToken, 0)
            if (show == false) view.clearFocus()
        }
    }

    private var lifetimeCount = -1
    private var lifetimeWake = false
    private fun syncLifetime() {
        val count = sessions.count { it.running }
        if (count != lifetimeCount || keepAwake != lifetimeWake) {
            lifetimeCount = count; lifetimeWake = keepAwake
            DnTerminalService.sync(context, count, keepAwake)
        }
    }
}

@Composable
internal fun DnPtyTerminalPanel(controller: DnPtyTerminalController, onFiles: () -> Unit) {
    val returnToFiles = { controller.keyboard(false); onFiles() }
    BackHandler { returnToFiles() }
    var sessionsMenu by remember { mutableStateOf(false) }
    var terminalMenu by remember { mutableStateOf(false) }
    val current = controller.active
    DisposableEffect(controller) { onDispose { controller.keyboard(false); controller.detach() } }
    Column(Modifier.fillMaxSize().background(Color.Black).imePadding().navigationBarsPadding()) {
        // The Files button sits where Files shows its Terminal button, so the switch never moves.
        Row(Modifier.fillMaxWidth().height(48.dp).padding(horizontal = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            DnToolSwitchButton(
                target = DnToolSwitchTarget.Files,
                contentDescription = stringResource(R.string.dn_terminal_files),
                onClick = returnToFiles,
                tint = Color(0xFFD6D6D6),
            )
            Box(Modifier.weight(1f)) {
                TextButton(onClick = { sessionsMenu = true }, modifier = Modifier.fillMaxWidth()) {
                    Text(current?.label ?: stringResource(R.string.dn_terminal_root),
                        color = Color.White, fontSize = 15.sp, modifier = Modifier.weight(1f),
                        maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Icon(Icons.TwoTone.ArrowDropDown,
                        contentDescription = stringResource(R.string.dn_terminal_sessions), tint = Color.White)
                }
                DropdownMenu(sessionsMenu, onDismissRequest = { sessionsMenu = false }) {
                    controller.sessions.forEach { record ->
                        DropdownMenuItem(enabled = !record.closing,
                            text = { Text(record.label, maxLines = 1, overflow = TextOverflow.Ellipsis) },
                            trailingIcon = { RadioButton(record.id == current?.id, onClick = null) },
                            onClick = { sessionsMenu = false; controller.select(record.id) })
                    }
                }
            }
            TextButton(onClick = { controller.newRoot() }) { Text(stringResource(R.string.dn_terminal_new_short)) }
        }
        current?.exitCode?.let { Text(stringResource(R.string.dn_terminal_finished, it), color = Color.LightGray, fontSize = 11.sp) }
        if (controller.failure.isNotBlank()) Text(controller.failure, color = Color.Red)
        if (current != null) AndroidView(factory = { ctx ->
            EmulatorView(ctx, current.terminal, ctx.resources.displayMetrics).apply {
                setBackgroundColor(android.graphics.Color.BLACK)
                controller.attach(this)
                post { controller.keyboard(true) }
            }
        }, update = { it.keepScreenOn = controller.keepAwake },
            modifier = Modifier.weight(1f).fillMaxWidth())
        else Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
            TextButton(onClick = { controller.newRoot() }) { Text(stringResource(R.string.dn_terminal_empty)) }
        }
        // Fixed MT key grid. Native key translation respects application-cursor mode.
        val first = listOf(R.string.dn_terminal_esc to KeyEvent.KEYCODE_ESCAPE,
            R.string.dn_terminal_tab to KeyEvent.KEYCODE_TAB, R.string.dn_terminal_pgup to KeyEvent.KEYCODE_PAGE_UP,
            R.string.dn_terminal_home to KeyEvent.KEYCODE_MOVE_HOME, R.string.dn_terminal_up to KeyEvent.KEYCODE_DPAD_UP,
            R.string.dn_terminal_end_key to KeyEvent.KEYCODE_MOVE_END, R.string.dn_terminal_more_key to -1)
        val second = listOf(R.string.dn_terminal_ctrl to -2, R.string.dn_terminal_alt to -3,
            R.string.dn_terminal_pgdn to KeyEvent.KEYCODE_PAGE_DOWN, R.string.dn_terminal_left to KeyEvent.KEYCODE_DPAD_LEFT,
            R.string.dn_terminal_down to KeyEvent.KEYCODE_DPAD_DOWN, R.string.dn_terminal_right to KeyEvent.KEYCODE_DPAD_RIGHT,
            R.string.dn_terminal_keyboard_key to -4)
        listOf(first, second).forEach { row ->
            Row(Modifier.fillMaxWidth().background(Color(0xFF191919))) {
                row.forEach { (label, code) ->
                    val selected = (code == -2 && controller.control) || (code == -3 && controller.alt)
                    Box(Modifier.weight(1f).height(42.dp).background(if (selected) Color(0xFF405B60) else Color.Transparent)
                        .clickable {
                            when (code) {
                                -1 -> terminalMenu = true
                                -2 -> controller.toggleControl()
                                -3 -> controller.toggleAlt()
                                -4 -> controller.keyboard()
                                else -> controller.key(code)
                            }
                        }, contentAlignment = Alignment.Center) {
                        Text(stringResource(label), color = Color.White, fontSize = 13.sp)
                        if (code == -1) DropdownMenu(terminalMenu, onDismissRequest = { terminalMenu = false }) {
                            DropdownMenuItem(text = { Text(stringResource(R.string.dn_terminal_paste)) }, onClick = { terminalMenu = false; controller.paste() })
                            DropdownMenuItem(text = { Text(stringResource(R.string.dn_terminal_end)) }, onClick = {
                                terminalMenu = false; controller.activeId?.let { controller.end(it) }
                            })
                            DropdownMenuItem(text = { Text(stringResource(R.string.dn_terminal_reset)) }, onClick = { terminalMenu = false; controller.reset() })
                            DropdownMenuItem(text = { Text(stringResource(R.string.dn_terminal_font_up)) }, onClick = { controller.resizeFont(controller.fontSize + 2) })
                            DropdownMenuItem(text = { Text(stringResource(R.string.dn_terminal_font_down)) }, onClick = { controller.resizeFont(controller.fontSize - 2) })
                            DropdownMenuItem(text = { Text(stringResource(R.string.dn_terminal_wake)) },
                                trailingIcon = { Checkbox(controller.keepAwake, null) }, onClick = { controller.toggleWake() })
                        }
                    }
                }
            }
        }
    }
}
