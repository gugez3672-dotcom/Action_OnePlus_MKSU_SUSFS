from pathlib import Path

p = Path("source/manager/app/src/main/java/com/resukisu/resukisu/ui/screen/main/ToolsPage.kt")
t = p.read_text()

# Add a dedicated detached/background launcher. The ordinary interactive terminal
# remains inside the manager app cgroup and therefore dies with the manager.
# Only jobs started through this function are moved to root cgroups.
anchor = '''    fun sendTerminalLine() {
'''
if anchor not in t:
    raise SystemExit("sendTerminalLine anchor missing")

fn = r'''    fun runScriptDetached(path: String) {
        terminalHint = "正在启动独立后台…"

        scope.launch {
            val busybox = "/data/adb/ksu/bin/busybox"
            val parent = parentPath(path)
            val token = System.currentTimeMillis().toString()
            val jobDir = "/data/adb/ksu/dn_jobs"
            val logPath = "$jobDir/job_$token.log"
            val cgroupPath = "$jobDir/job_$token.cgroup"
            val readyPath = "$jobDir/.ready_$token"

            // Preserve the selected file byte-for-byte. This is important for
            // self-extracting shell scripts with an appended gzip/zip payload.
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

            // The helper shell starts in the manager cgroup, moves only itself to
            // the root cgroups, records readiness, then execs the selected job.
            // Descendants inherit the detached cgroup. The manager terminal itself
            // never moves, so closing/swiping the manager still kills all manager-
            // owned shell/session/helper processes.
            val child = buildString {
                append("pid=\$\$; ")
                append("for cg in /acct /dev/cg2_bpf /sys/fs/cgroup /dev/memcg/apps; do ")
                append("f=\"\$cg/cgroup.procs\"; ")
                append("if [ -e \"\$f\" ]; then printf '%s' \"\$pid\" > \"\$f\" 2>/dev/null || true; fi; ")
                append("done; ")
                append("$busybox mkdir -p " + shellQuote(jobDir) + "; ")
                append("cat /proc/\$\$/cgroup > " + shellQuote(cgroupPath) + " 2>/dev/null || true; ")
                append(": > " + shellQuote(readyPath) + "; ")
                append("cd " + shellQuote(parent) + " || exit 127; ")
                append(execPart)
            }

            val launch = buildString {
                append("$busybox mkdir -p " + shellQuote(jobDir) + "; ")
                append("rm -f " + shellQuote(readyPath) + "; ")
                append("$busybox sh -c " + shellQuote(child))
                append(" </dev/null >>" + shellQuote(logPath) + " 2>&1 & ")
                append("launcher=\$!; ")
                append("ok=0; ")
                append("for i in 1 2 3 4 5; do ")
                append("if [ -f " + shellQuote(readyPath) + " ]; then ok=1; break; fi; ")
                append("$busybox sleep 1; ")
                append("done; ")
                append("rm -f " + shellQuote(readyPath) + "; ")
                append("if [ \"\$ok\" = 1 ]; then ")
                append("printf 'DETACHED_OK pid=%s log=%s cgroup=%s' \"\$launcher\" ")
                append(shellQuote(logPath) + " " + shellQuote(cgroupPath) + "; ")
                append("else printf 'DETACHED_FAIL pid=%s' \"\$launcher\"; exit 1; fi")
            }

            val result = execRoot(launch)
            if (result.success && result.out.contains("DETACHED_OK")) {
                terminalOutput = (
                    terminalOutput +
                        "\n# 独立后台已启动: " + path.substringAfterLast('/') +
                        "\n# 管理器/终端关闭后：此后台任务继续运行" +
                        "\n# 日志: " + logPath +
                        "\n# cgroup: " + cgroupPath + "\n"
                ).takeLast(180_000)
                terminalHint = "独立后台已启动"
            } else {
                terminalOutput = (
                    terminalOutput +
                        "\n[独立后台启动失败]\n" +
                        result.out + "\n"
                ).takeLast(180_000)
                terminalHint = "后台启动失败"
            }
            tab = 1
        }
    }

'''

t = t.replace(anchor, fn + anchor, 1)

# Add a separate, explicit action for detached/background execution.
menu_anchor = '''                                ) {
                                    Icon(Icons.TwoTone.Terminal, null)
                                    Spacer(Modifier.width(10.dp))
                                    Text("Root 执行 → 终端")
                                }
'''
if menu_anchor not in t:
    raise SystemExit("Root terminal menu anchor missing")

menu = menu_anchor + r'''                                TextButton(
                                    onClick = {
                                        showActions = false
                                        runScriptDetached(fullPath)
                                    },
                                ) {
                                    Icon(Icons.TwoTone.Terminal, null)
                                    Spacer(Modifier.width(10.dp))
                                    Text("Root 后台运行（独立）")
                                }
'''

t = t.replace(menu_anchor, menu, 1)

p.write_text(t)

assert "fun runScriptDetached(path: String)" in t
assert "Root 后台运行（独立）" in t
assert "for cg in /acct /dev/cg2_bpf /sys/fs/cgroup /dev/memcg/apps" in t
assert "cat /proc/$$/cgroup" in t
assert "exec $busybox setsid" in t
assert "manager cgroup" in t
