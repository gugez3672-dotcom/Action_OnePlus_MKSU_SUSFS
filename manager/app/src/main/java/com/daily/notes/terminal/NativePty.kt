package com.daily.notes.terminal

/**
 * Minimal JNI PTY shim (libdn_pty.so). The app opens /dev/ptmx itself and hands
 * the master fd here; the shell is forked as a direct child of the app on that
 * pty. Closing the master fd is the primary teardown (kernel SIGHUP -> the whole
 * pty session exits, root included). See manager-custom/native/dn_pty.c.
 */
object NativePty {
    init { System.loadLibrary("dn_pty") }

    /** Fork the shell on [masterFd] (an open /dev/ptmx). Returns the child pid, or -1. */
    external fun createSubprocess(cmd: String, argv: Array<String>, envp: Array<String>, masterFd: Int): Int

    external fun setPtyWindowSize(fd: Int, row: Int, col: Int)

    /** Block until [pid] exits; returns the exit code, 128+signal, or -1. */
    external fun waitFor(pid: Int): Int

    /** Signal [pid] (use a negative pid for the whole process group). */
    external fun sendSignal(pid: Int, signal: Int)

    const val SIGHUP = 1
}
