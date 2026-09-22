from pathlib import Path
import xml.etree.ElementTree as ET

ANDROID_NS = "http://schemas.android.com/apk/res/android"
ET.register_namespace("android", ANDROID_NS)

main = Path("source/manager/app/src/main/java/com/resukisu/resukisu/ui/MainActivity.kt")
t = main.read_text()

# Import Service/IBinder/Process aliases and start a same-process task-removal sentinel.
if "import android.app.Service" not in t:
    t = t.replace(
        "import android.content.Context\n",
        "import android.app.Service\nimport android.content.Context\n",
        1,
    )
if "import android.os.IBinder" not in t:
    t = t.replace(
        "import android.os.Bundle\n",
        "import android.os.Bundle\nimport android.os.IBinder\nimport android.os.Process\n",
        1,
    )

create_anchor = '''            super.onCreate(savedInstanceState)

            splashScreen.setKeepOnScreenCondition {
'''
create_new = '''            super.onCreate(savedInstanceState)

            // Keep a lightweight same-process sentinel while the manager task exists.
            // When the task is removed from Recents, it kills only the manager process.
            // Root jobs explicitly detached by the Tools page are outside this app cgroup
            // and therefore remain alive.
            startService(Intent(this, ManagerTaskRemovalService::class.java))

            splashScreen.setKeepOnScreenCondition {
'''
if create_anchor not in t:
    raise SystemExit("onCreate anchor missing")
t = t.replace(create_anchor, create_new, 1)

destroy_old = '''    override fun onDestroy() {
        try {
            themeUtils.unregisterThemeChangeObserver(this, themeChangeObserver)
            super.onDestroy()
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }
}
'''
destroy_new = '''    override fun onDestroy() {
        val shouldKillProcess = isFinishing && !isChangingConfigurations
        try {
            themeUtils.unregisterThemeChangeObserver(this, themeChangeObserver)
            super.onDestroy()
        } catch (e: Exception) {
            e.printStackTrace()
        } finally {
            // Fallback for OEMs that finish the root activity on task removal but keep
            // the app process cached. Never fire for configuration-change recreation.
            if (shouldKillProcess) {
                Process.killProcess(Process.myPid())
            }
        }
    }
}

class ManagerTaskRemovalService : Service() {
    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int =
        START_NOT_STICKY

    override fun onTaskRemoved(rootIntent: Intent?) {
        // The manager task has been swiped away. Stop the sentinel and terminate
        // the manager process so no UI/root-terminal/session helper remains cached.
        // Detached root jobs are separate processes in root cgroups and survive.
        stopSelf()
        Process.killProcess(Process.myPid())
    }
}
'''
if destroy_old not in t:
    raise SystemExit("onDestroy anchor missing")
t = t.replace(destroy_old, destroy_new, 1)
main.write_text(t)

# Register the sentinel as non-exported and do NOT stop it automatically with task:
# onTaskRemoved must run first so it can terminate the process deterministically.
manifest = Path("source/manager/app/src/main/AndroidManifest.xml")
tree = ET.parse(manifest)
root = tree.getroot()
app = root.find("application")
if app is None:
    raise SystemExit("manifest application missing")

name_key = f"{{{ANDROID_NS}}}name"
exported_key = f"{{{ANDROID_NS}}}exported"
stop_with_task_key = f"{{{ANDROID_NS}}}stopWithTask"

service_name = ".ui.ManagerTaskRemovalService"
service = next((s for s in app.findall("service") if s.get(name_key) == service_name), None)
if service is None:
    service = ET.SubElement(app, "service")
    service.set(name_key, service_name)
service.set(exported_key, "false")
service.set(stop_with_task_key, "false")

tree.write(manifest, encoding="utf-8", xml_declaration=True)

out = main.read_text()
mout = manifest.read_text()
assert "class ManagerTaskRemovalService : Service()" in out
assert "onTaskRemoved(rootIntent: Intent?)" in out
assert "Process.killProcess(Process.myPid())" in out
assert "isFinishing && !isChangingConfigurations" in out
assert 'android:name=".ui.ManagerTaskRemovalService"' in mout or ".ui.ManagerTaskRemovalService" in mout
