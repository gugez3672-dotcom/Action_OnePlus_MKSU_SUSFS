from pathlib import Path

p = Path("source/manager/app/src/main/java/com/resukisu/resukisu/ui/screen/main/ToolsPage.kt")
t = p.read_text()

if "import android.widget.Toast" not in t:
    t = t.replace(
        "import android.util.Base64\n",
        "import android.util.Base64\nimport android.widget.Toast\n",
        1,
    )

start = t.index("    fun runScriptDetached(path: String) {")
end = t.index("\n\n    fun sendTerminalLine()", start)

new = r'''    fun runScriptDetached(path: String) {
        scope.launch {
            val busybox = "/data/adb/ksu/bin/busybox"
            val parent = parentPath(path)
            val token = System.currentTimeMillis().toString()
            val jobDir = "/data/adb/ksu/dn_jobs"
            val cgroupPath = "$jobDir/last.cgroup"
            val statusPath = "$jobDir/last.status"
            val pidPath = "$jobDir/last.pid"
            val pathRecord = "$jobDir/last.path"
            val readyPath = "$jobDir/.ready_$token"

            // Preflight: a missing setsid used to look like a successful launch,
            // because readiness was recorded before exec. Fail visibly instead.
            val setsidReady = execRoot(
                "$busybox --list 2>/dev/null | $busybox grep -qx setsid"
            ).success
            if (!setsidReady) {
                Toast.makeText(context, "后台启动失败：BusyBox 缺少 setsid", Toast.LENGTH_LONG).show()
                return@launch
            }

            // Constant-size housekeeping: one status set only, no rolling logs.
            execRoot(
                "$busybox mkdir -p " + shellQuote(jobDir) + "; " +
                    "$busybox rm -f " + shellQuote(jobDir) +
                    "/job_*.log " + shellQuote(jobDir) +
                    "/job_*.cgroup " + shellQuote(jobDir) +
                    "/.ready_* 2>/dev/null || true; " +
                    "rm -f " + shellQuote(statusPath) + " " +
                    shellQuote(pidPath) + " " + shellQuote(pathRecord) + " 2>/dev/null || true"
            )

            val magic = execRoot(
                "$busybox hexdump -n 4 -e '4/1 \"%02x\"' " + shellQuote(path) + " 2>/dev/null"
            ).out.trim().lowercase(Locale.ROOT)
            val isElf = magic == "7f454c46"

            val execPart = if (isElf) {
                "chmod 700 " + shellQuote(path) + " 2>/dev/null || true; " +
                    "exec $busybox setsid " + shellQuote(path)
            } else {
                "exec $busybox setsid $busybox ash " + shellQuote(path)
            }

            val child = buildString {
                append("pid=\$\$; ")
                append("for cg in /acct /dev/cg2_bpf /sys/fs/cgroup /dev/memcg/apps; do ")
                append("f=\"\$cg/cgroup.procs\"; ")
                append("if [ -e \"\$f\" ]; then printf '%s' \"\$pid\" > \"\$f\" 2>/dev/null || true; fi; ")
                append("done; ")
                append("for f in /dev/cpuset/foreground/cgroup.procs /dev/cpuctl/foreground/cgroup.procs; do ")
                append("if [ -e \"\$f\" ]; then printf '%s' \"\$pid\" > \"\$f\" 2>/dev/null || true; fi; ")
                append("done; ")
                append("$busybox mkdir -p " + shellQuote(jobDir) + "; ")
                append("cat /proc/\$\$/cgroup > " + shellQuote(cgroupPath) + " 2>/dev/null || true; ")
                append("printf '%s\\n' " + shellQuote(path) + " > " + shellQuote(pathRecord) + "; ")
                append(": > " + shellQuote(readyPath) + "; ")
                append("cd " + shellQuote(parent) + " || exit 127; ")
                append(execPart)
            }

            val launch = buildString {
                append("$busybox sh -c " + shellQuote(child))
                append(" </dev/null >/dev/null 2>&1 & ")
                append("launcher=\$!; ")
                append("printf '%s\\n' \"\$launcher\" > " + shellQuote(pidPath) + "; ")
                append("ok=0; ")
                append("for i in 1 2 3 4 5; do ")
                append("if [ -f " + shellQuote(readyPath) + " ]; then ok=1; break; fi; ")
                append("$busybox sleep 1; ")
                append("done; ")
                append("rm -f " + shellQuote(readyPath) + "; ")
                append("if [ \"\$ok\" != 1 ]; then ")
                append("printf 'READY=0\\nPID=%s\\n' \"\$launcher\" > " + shellQuote(statusPath) + "; ")
                append("printf 'DETACHED_FAIL pid=%s' \"\$launcher\"; exit 1; fi; ")
                append("$busybox sleep 1; ")
                append("if kill -0 \"\$launcher\" 2>/dev/null; then ")
                append("printf 'READY=1\\nLIVE=1\\nPID=%s\\n' \"\$launcher\" > " + shellQuote(statusPath) + "; ")
                append("printf 'DETACHED_LIVE pid=%s cgroup=%s' \"\$launcher\" " + shellQuote(cgroupPath) + "; ")
                append("else ")
                append("printf 'READY=1\\nLIVE=0\\nPID=%s\\n' \"\$launcher\" > " + shellQuote(statusPath) + "; ")
                append("printf 'DETACHED_SUBMITTED pid=%s cgroup=%s' \"\$launcher\" " + shellQuote(cgroupPath) + "; ")
                append("fi")
            }

            val result = execRoot(launch)
            when {
                result.success && result.out.contains("DETACHED_LIVE") -> {
                    Toast.makeText(context, "独立后台正在运行", Toast.LENGTH_SHORT).show()
                    terminalOutput = (
                        terminalOutput +
                            "\n# 独立后台运行中: " + path.substringAfterLast('/') +
                            "\n# 状态: " + statusPath +
                            "\n# cgroup: " + cgroupPath + "\n"
                    ).takeLast(180_000)
                }

                result.success && result.out.contains("DETACHED_SUBMITTED") -> {
                    Toast.makeText(
                        context,
                        "脚本已执行，主进程已退出；请按脚本自身后台状态确认",
                        Toast.LENGTH_LONG
                    ).show()
                    terminalOutput = (
                        terminalOutput +
                            "\n# 后台执行已提交: " + path.substringAfterLast('/') +
                            "\n# 主进程 1 秒内退出（不等于执行失败）" +
                            "\n# 状态: " + statusPath + "\n"
                    ).takeLast(180_000)
                }

                else -> {
                    Toast.makeText(context, "独立后台启动失败", Toast.LENGTH_LONG).show()
                    terminalOutput = (
                        terminalOutput +
                            "\n[独立后台启动失败]\n" +
                            result.out + "\n"
                    ).takeLast(180_000)
                }
            }

            // Do not switch to the terminal tab. Detached execution has no
            // interactive terminal, so showing disabled Stop/Ctrl+C was misleading.
        }
    }'''

t = t[:start] + new + t[end:]
p.write_text(t)

out = p.read_text()
assert "后台启动失败：BusyBox 缺少 setsid" in out
assert "DETACHED_LIVE" in out
assert "DETACHED_SUBMITTED" in out
assert "last.status" in out
assert "last.pid" in out
assert "last.path" in out
assert "Do not switch to the terminal tab" in out
assert "tab = 1" not in out[start:end]
