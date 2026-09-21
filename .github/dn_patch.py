from pathlib import Path
from textwrap import dedent
import re
import xml.etree.ElementTree as ET

root = Path("source/manager")
pkg = "com.daily.notes"

app_gradle = root / "app/build.gradle.kts"
t = app_gradle.read_text()
if 'applicationId = "' in t:
    t = re.sub(r'applicationId\s*=\s*"[^"]+"', f'applicationId = "{pkg}"', t, count=1)
else:
    anchor = "        versionName = managerVersionName\n"
    if t.count(anchor) != 1:
        raise SystemExit("unexpected app gradle")
    t = t.replace(anchor, anchor + f'        applicationId = "{pkg}"\n', 1)
app_gradle.write_text(t)

root_gradle = root / "build.gradle.kts"
t = root_gradle.read_text()
t = re.sub(r'extra\["managerVersionCode"\]\s*=.*', 'extra["managerVersionCode"] = 40203', t, count=1)
t = re.sub(r'extra\["managerVersionName"\]\s*=.*', 'extra["managerVersionName"] = "2.4.3"', t, count=1)
root_gradle.write_text(t)

strings = root / "app/src/main/res/values/strings.xml"
s = strings.read_text().replace(
    '<string name="app_name" translatable="false">ReSukiSU</string>',
    '<string name="app_name" translatable="false">Daily Notes</string>'
)
strings.write_text(s)

ANDROID_NS = "http://schemas.android.com/apk/res/android"
TOOLS_NS = "http://schemas.android.com/tools"
ET.register_namespace("android", ANDROID_NS)
ET.register_namespace("tools", TOOLS_NS)

manifest = root / "app/src/main/AndroidManifest.xml"
tree = ET.parse(manifest)
mroot = tree.getroot()
for node in list(mroot.findall("uses-permission")):
    if node.get(f"{{{ANDROID_NS}}}name") == "android.permission.REQUEST_INSTALL_PACKAGES":
        mroot.remove(node)

app = mroot.find("application")
def aname(n):
    return n.get(f"{{{ANDROID_NS}}}name")

main = next(x for x in app.findall("activity") if aname(x) == ".ui.MainActivity")
alias = next(x for x in app.findall("activity-alias") if aname(x) == ".ui.MainActivityAlias")
recv = next(x for x in app.findall("receiver") if aname(x) == ".magica.BootCompletedReceiver")

main.set(f"{{{ANDROID_NS}}}exported", "false")
for f in list(main.findall("intent-filter")):
    main.remove(f)
alias.set(f"{{{ANDROID_NS}}}exported", "false")
alias.set(f"{{{ANDROID_NS}}}enabled", "false")
for f in list(alias.findall("intent-filter")):
    alias.remove(f)
recv.set(f"{{{ANDROID_NS}}}exported", "false")
tree.write(manifest, encoding="utf-8", xml_declaration=True)

ksu_cli = root / "app/src/main/java/com/resukisu/resukisu/data/shell/KsuCli.kt"
t = ksu_cli.read_text()
st = t.index("    suspend fun isOfficialSignature")
en = t.index("\n    suspend fun getFeatureStatus", st)
ksu_cli.write_text(t[:st] + "    suspend fun isOfficialSignature(packageResourcePath: String): Boolean = true\n" + t[en:])

updater = root / "app/src/main/java/com/resukisu/resukisu/domain/usecase/CheckManagerUpdateUseCase.kt"
t = updater.read_text()
st = t.index("    suspend operator fun invoke")
en = t.index("\n}", st)
updater.write_text(t[:st] + "    suspend operator fun invoke(channel: ManagerUpdateChannel): ManagerUpdateInfo? = null\n" + t[en:])

settings_repo = root / "app/src/main/java/com/resukisu/resukisu/data/settings/SettingsPlatformRepository.kt"
t = settings_repo.read_text()
old = (
    '        val packageName = application.packageName\n'
    '        val main = ComponentName(packageName, "$packageName.ui.MainActivity")\n'
    '        val alias = ComponentName(packageName, "$packageName.ui.MainActivityAlias")\n'
)
new = (
    '        val packageName = application.packageName\n'
    '        val main = ComponentName(packageName, "com.daily.notes.ui.NotesActivity")\n'
    '        val alias = ComponentName(packageName, "com.daily.notes.ui.NotesAlias")\n'
)
settings_repo.write_text(t.replace(old, new, 1))

colors = root / "app/src/main/res/values/colors.xml"
ct = colors.read_text()
ct = re.sub(r'<color name="ic_launcher_background">#[0-9A-Fa-f]{6,8}</color>',
            '<color name="ic_launcher_background">#111827</color>', ct)
colors.write_text(ct)

fg = dedent("""\
<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="108dp" android:height="108dp"
    android:viewportWidth="108" android:viewportHeight="108">
    <path android:fillColor="#F8FAFC"
        android:pathData="M31,20 C27.1,20 24,23.1 24,27 L24,81 C24,84.9 27.1,88 31,88 L77,88 C80.9,88 84,84.9 84,81 L84,37 L67,20 Z"/>
    <path android:fillColor="#60A5FA"
        android:pathData="M67,20 L84,37 L73,37 C69.7,37 67,34.3 67,31 Z"/>
    <path android:fillColor="#CBD5E1"
        android:pathData="M36,45 L71,45 C72.1,45 73,45.9 73,47 C73,48.1 72.1,49 71,49 L36,49 C34.9,49 34,48.1 34,47 C34,45.9 34.9,45 36,45 Z"/>
    <path android:fillColor="#94A3B8"
        android:pathData="M36,57 L67,57 C68.1,57 69,57.9 69,59 C69,60.1 68.1,61 67,61 L36,61 C34.9,61 34,60.1 34,59 C34,57.9 34.9,57 36,57 Z"/>
    <path android:fillColor="#94A3B8"
        android:pathData="M36,69 L59,69 C60.1,69 61,69.9 61,71 C61,72.1 60.1,73 59,73 L36,73 C34.9,73 34,72.1 34,71 C34,69.9 34.9,69 36,69 Z"/>
    <path android:fillColor="#3B82F6"
        android:pathData="M78,72 A6,6 0,1 1,66 72 A6,6 0,1 1,78 72"/>
</vector>
""")
mono = dedent("""\
<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="108dp" android:height="108dp"
    android:viewportWidth="108" android:viewportHeight="108">
    <path android:fillColor="#000000"
        android:pathData="M31,20 L67,20 L84,37 L84,81 C84,84.9 80.9,88 77,88 L31,88 C27.1,88 24,84.9 24,81 L24,27 C24,23.1 27.1,20 31,20 Z M36,45 L73,45 L73,49 L36,49 Z M36,57 L69,57 L69,61 L36,61 Z M36,69 L61,69 L61,73 L36,73 Z"/>
</vector>
""")
for name in ("ic_launcher_foreground.xml", "ic_launcher_foreground_alt.xml"):
    (root / "app/src/main/res/drawable" / name).write_text(fg)
for name in ("ic_launcher_monochrome.xml", "ic_launcher_monochrome_alt.xml"):
    (root / "app/src/main/res/drawable" / name).write_text(mono)

text_ext = {".kt", ".java", ".xml", ".kts", ".gradle", ".properties", ".pro", ".txt", ".c", ".cc", ".cpp", ".h", ".hpp", ".rs", ".toml", ".json"}
repls = [
    ("com.resukisu.resukisu", "com.daily.notes"),
    ("com/resukisu/resukisu", "com/daily/notes"),
    ("Java_com_resukisu_resukisu", "Java_com_daily_notes"),
    (".magica", ".sync"),
    (".ui.webui", ".ui.document"),
    (".data.download", ".data.transfer"),
    ("KernelSUApplication", "NotesApplication"),
    ("MainActivityAlias", "NotesAlias"),
    ("MainActivity", "NotesActivity"),
    ("WebUIActivity", "DocumentActivity"),
    ("BackgroundCropActivity", "ImageCropActivity"),
    ("MagicaService", "SyncService"),
    ("DownloadService", "TransferService"),
    ("BootCompletedReceiver", "StartupReceiver"),
    ("AppZygotePreload", "PreloadInitializer"),
    ("magica.LAUNCH", "sync.START"),
]
for p in root.rglob("*"):
    if not p.is_file() or p.suffix.lower() not in text_ext:
        continue
    try:
        old = p.read_text()
    except UnicodeDecodeError:
        continue
    new = old
    for a,b in repls:
        new = new.replace(a,b)
    if new != old:
        p.write_text(new)

renames = {
    root / "app/src/main/java/com/resukisu/resukisu/KernelSUApplication.kt": root / "app/src/main/java/com/resukisu/resukisu/NotesApplication.kt",
    root / "app/src/main/java/com/resukisu/resukisu/magica/MagicaService.java": root / "app/src/main/java/com/resukisu/resukisu/magica/SyncService.java",
    root / "app/src/main/java/com/resukisu/resukisu/magica/BootCompletedReceiver.java": root / "app/src/main/java/com/resukisu/resukisu/magica/StartupReceiver.java",
    root / "app/src/main/java/com/resukisu/resukisu/magica/AppZygotePreload.java": root / "app/src/main/java/com/resukisu/resukisu/magica/PreloadInitializer.java",
}
for src,dst in renames.items():
    if src.exists():
        src.rename(dst)
