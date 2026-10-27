/*
 * dn_pty.c — minimal JNI PTY shim for the Daily Notes terminal (D99 route B).
 *
 * This is the whole native side of the terminal. It replaces the old
 * dn_session.c supervisor and its reparent-under-a-root-daemon background
 * model. The design mirrors how MT's terminal actually works (observed live:
 * the interactive shell is a setsid session leader whose controlling terminal
 * is a pseudo-terminal slave owned by the app):
 *
 *   The app opens /dev/ptmx (master) on the Java side and hands the fd here.
 *   createSubprocess() forks INSIDE the app process; the child opens the pty
 *   slave, becomes a session leader (setsid), makes the slave its controlling
 *   terminal and exec's the shell. So the shell is a direct child of the app.
 *
 * Recycling is free and leak-proof: when the app closes the master fd (session
 * closed, or the task swiped away and the app process dies), the kernel tty
 * layer sends SIGHUP to the pty's foreground process group. That reaches the
 * root shell and its jobs regardless of uid, so they exit on their own. No
 * subreaper, no starttime bookkeeping, no lingering root processes.
 *
 * A shell may still keep something alive past this by detaching it itself
 * (setsid/nohup/disown inside the shell) — that process loses the controlling
 * terminal, is reparented to init, and survives, exactly like MT. We provide
 * no app-level "background task" machinery; the process model is enough.
 *
 * JNI surface (class com.daily.notes.terminal.NativePty):
 *   int  createSubprocess(String cmd, String[] argv, String[] envp, int masterFd)
 *   void setPtyWindowSize(int fd, int row, int col)
 *   int  waitFor(int pid)
 *   void sendSignal(int pid, int signal)
 */
#define _GNU_SOURCE
#include <jni.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/wait.h>
#include <termios.h>
#include <unistd.h>

/* Build a NULL-terminated char** from a Java String[] (NULL array -> {NULL}). */
static char **to_strv(JNIEnv *env, jobjectArray array) {
    jsize count = array ? (*env)->GetArrayLength(env, array) : 0;
    char **vector = (char **)calloc((size_t)count + 1, sizeof(char *));
    if (!vector) return NULL;
    for (jsize i = 0; i < count; i++) {
        jstring item = (jstring)(*env)->GetObjectArrayElement(env, array, i);
        const char *utf = item ? (*env)->GetStringUTFChars(env, item, NULL) : NULL;
        vector[i] = strdup(utf ? utf : "");
        if (utf) (*env)->ReleaseStringUTFChars(env, item, utf);
        if (item) (*env)->DeleteLocalRef(env, item);
    }
    return vector;
}

static void free_strv(char **vector) {
    if (!vector) return;
    for (char **p = vector; *p; p++) free(*p);
    free(vector);
}

/* Leave only fd 0/1/2 open in the child so no app fd leaks into the shell. */
static void close_extra_fds(void) {
    DIR *dir = opendir("/proc/self/fd");
    if (!dir) return;
    int dir_fd = dirfd(dir);
    struct dirent *entry;
    while ((entry = readdir(dir)) != NULL) {
        char *end = NULL;
        long fd = strtol(entry->d_name, &end, 10);
        if (end && *end == '\0' && fd > STDERR_FILENO && (int)fd != dir_fd) close((int)fd);
    }
    closedir(dir);
}

/*
 * createSubprocess(cmd, argv, envp, masterFd) -> child pid, or -1.
 * masterFd is an already-open /dev/ptmx master owned by the app. The shell
 * runs as a direct child of the app on that pty, as its session leader.
 */
JNIEXPORT jint JNICALL
Java_com_daily_notes_terminal_NativePty_createSubprocess(
        JNIEnv *env, jclass clazz, jstring cmd, jobjectArray argvArray,
        jobjectArray envpArray, jint masterFd) {
    (void)clazz;
    const char *path = (*env)->GetStringUTFChars(env, cmd, NULL);
    char *command = strdup(path ? path : "");
    if (path) (*env)->ReleaseStringUTFChars(env, cmd, path);
    char **argv = to_strv(env, argvArray);
    char **envp = to_strv(env, envpArray);
    if (!command || !argv || !envp) {
        free(command);
        free_strv(argv);
        free_strv(envp);
        return -1;
    }

    /* Keep the master out of the child, and unlock+name the slave. */
    fcntl(masterFd, F_SETFD, FD_CLOEXEC);
    char slave[64];
    memset(slave, 0, sizeof slave);
    if (unlockpt(masterFd) != 0) {
        free(command);
        free_strv(argv);
        free_strv(envp);
        return -1;
    }
    errno = 0;
    if (ptsname_r(masterFd, slave, sizeof slave) != 0 && errno != 0) {
        free(command);
        free_strv(argv);
        free_strv(envp);
        return -1;
    }

    pid_t pid = fork();
    if (pid < 0) {
        free(command);
        free_strv(argv);
        free_strv(envp);
        return -1;
    }
    if (pid == 0) {
        /* Child: new session, slave as controlling terminal, exec the shell. */
        setsid();
        int pts = open(slave, O_RDWR);
        if (pts < 0) _exit(127);
        ioctl(pts, TIOCSCTTY, 0);
        dup2(pts, 0);
        dup2(pts, 1);
        dup2(pts, 2);
        close_extra_fds();
        signal(SIGHUP, SIG_DFL);
        signal(SIGINT, SIG_DFL);
        signal(SIGQUIT, SIG_DFL);
        signal(SIGTERM, SIG_DFL);
        signal(SIGPIPE, SIG_DFL);
        signal(SIGCHLD, SIG_DFL);
        execve(command, argv, envp);
        _exit(127);
    }

    free(command);
    free_strv(argv);
    free_strv(envp);
    return (jint)pid;
}

/* Push a new window size to the pty so the shell and full-screen apps reflow. */
JNIEXPORT void JNICALL
Java_com_daily_notes_terminal_NativePty_setPtyWindowSize(
        JNIEnv *env, jclass clazz, jint fd, jint row, jint col) {
    (void)env;
    (void)clazz;
    struct winsize window;
    memset(&window, 0, sizeof window);
    window.ws_row = (unsigned short)(row > 0 ? row : 24);
    window.ws_col = (unsigned short)(col > 0 ? col : 80);
    ioctl(fd, TIOCSWINSZ, &window);
}

/* Block until the shell exits; returns its exit code, 128+signal, or -1. */
JNIEXPORT jint JNICALL
Java_com_daily_notes_terminal_NativePty_waitFor(
        JNIEnv *env, jclass clazz, jint pid) {
    (void)env;
    (void)clazz;
    int status = 0;
    pid_t result;
    do {
        result = waitpid((pid_t)pid, &status, 0);
    } while (result < 0 && errno == EINTR);
    if (result <= 0) return -1;
    if (WIFEXITED(status)) return WEXITSTATUS(status);
    if (WIFSIGNALED(status)) return 128 + WTERMSIG(status);
    return -1;
}

/*
 * Signal the shell or its process group. "end session" sends SIGHUP to the
 * negative pid (the whole group) so leftover foreground jobs quit immediately;
 * closing the master fd is still the primary teardown path.
 */
JNIEXPORT void JNICALL
Java_com_daily_notes_terminal_NativePty_sendSignal(
        JNIEnv *env, jclass clazz, jint pid, jint signal) {
    (void)env;
    (void)clazz;
    kill((pid_t)pid, signal);
}
