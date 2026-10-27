package com.daily.notes.terminal

import android.os.ParcelFileDescriptor
import jackpal.androidterm.emulatorview.TermSession
import java.io.File
import java.io.IOException

/**
 * A terminal session backed by a real pty and a shell that is a direct child of
 * the app (MT's model). The base [TermSession] owns the VT100 emulator and the
 * reader/writer threads; this subclass only supplies the process and the pty.
 *
 * Recycling: finish() closes the master fd (via the AutoClose streams), which
 * makes the kernel SIGHUP the pty session so the shell and its foreground jobs
 * exit — no supervisor, no leak. Anything the user detached inside the shell
 * (setsid/nohup) loses the controlling terminal and survives, exactly like MT.
 */
class DnShellTermSession(
    cmd: String,
    argv: Array<String>,
    envp: Array<String>,
    private val initialCommand: String = "",
) : TermSession(/* exitOnEOF = */ true) {

    private val master: ParcelFileDescriptor =
        ParcelFileDescriptor.open(File("/dev/ptmx"), ParcelFileDescriptor.MODE_READ_WRITE)

    /** Shell pid, or -1 if the fork failed. */
    val pid: Int = NativePty.createSubprocess(cmd, argv, envp, master.fd)

    @Volatile
    var exitCode: Int? = null
        private set

    /** Invoked once on the main thread when the shell exits (code, or 128+signal). */
    var onExit: ((Int) -> Unit)? = null

    /** Invoked on the main thread when Enter is pressed after the shell has exited. */
    var onEnterAfterExit: (() -> Unit)? = null

    @Volatile
    private var exited = false

    init {
        if (pid <= 0) {
            master.close()
            throw IOException("PTY child process could not be started")
        }
        // Chinese / UTF-8 script output would otherwise render as mojibake.
        setDefaultUTF8Mode(true)
        setTermOut(ParcelFileDescriptor.AutoCloseOutputStream(master))
        setTermIn(ParcelFileDescriptor.AutoCloseInputStream(master))
        if (pid > 0) {
            Thread({
                val code = NativePty.waitFor(pid)
                exitCode = code
                exited = true
                android.os.Handler(android.os.Looper.getMainLooper()).post { onExit?.invoke(code) }
            }, "dn-term-watch-$pid").apply {
                isDaemon = true
                start()
            }
        } else {
            exitCode = -1
        }
    }

    override fun initializeEmulator(columns: Int, rows: Int) {
        super.initializeEmulator(columns, rows)
        // Runs after the shell has sourced /system/etc/mkshrc, so this PS1 sticks.
        if (initialCommand.isNotEmpty()) write(initialCommand)
    }

    /**
     * The shell closed the PTY. Keep the emulator and its transcript on screen
     * (the output and exit code stay readable) instead of finishing the session;
     * the user closes it with Enter, or from the menu.
     */
    override fun onProcessExit() {
        exited = true
    }

    override fun write(data: ByteArray, offset: Int, count: Int) {
        if (!exited) {
            super.write(data, offset, count)
            return
        }
        for (i in offset until offset + count) {
            val b = data[i].toInt()
            if (b == '\r'.code || b == '\n'.code) {
                // Post: closing tears this session down, so leave write() first.
                val callback = onEnterAfterExit
                android.os.Handler(android.os.Looper.getMainLooper()).post { callback?.invoke() }
                return
            }
        }
    }

    override fun updateSize(columns: Int, rows: Int) {
        if (pid > 0) NativePty.setPtyWindowSize(master.fd, rows, columns)
        super.updateSize(columns, rows)
    }

    override fun finish() {
        // Nudge any leftover foreground jobs, then let the base close the master.
        // The app UID cannot signal a root process group. Closing the PTY
        // master below causes the kernel's terminal hangup instead.
        super.finish()
    }
}
