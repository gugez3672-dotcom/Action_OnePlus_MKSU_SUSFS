#!/usr/bin/env python3
"""DN41: constrain menu-cell Modifier.weight to the caller RowScope."""
from pathlib import Path
p = Path("source/manager/app/src/main/java/com/resukisu/resukisu/ui/screen/main/DnDualPane.kt")
s = p.read_text()
old = "@Composable fun option(title: String, action: () -> Unit) {"
new = "@Composable fun option(title: String, modifier: Modifier, action: () -> Unit) {"
if s.count(old) != 1: raise SystemExit("DN41 option declaration drift")
s = s.replace(old, new)
old = "Box(Modifier.weight(1f).height(48.dp).clickable {"
new = "Box(modifier.height(48.dp).clickable {"
if s.count(old) != 1: raise SystemExit("DN41 menu cell body drift")
s = s.replace(old, new)
for label in ("复制 →","移动 →","删除","重命名","编辑","属性","终端"):
    old = 'option("' + label + '") {'
    new = 'option("' + label + '", Modifier.weight(1f)) {'
    if s.count(old) != 1: raise SystemExit("DN41 missing menu label " + label)
    s = s.replace(old,new)
old = 'option(if (c.entry.name.endsWith(".sh", true)) "运行脚本" else "打开") {'
new = 'option(if (c.entry.name.endsWith(".sh", true)) "运行脚本" else "打开", Modifier.weight(1f)) {'
if s.count(old) != 1: raise SystemExit("DN41 dynamic menu cell anchor drift")
s = s.replace(old,new)
old = '''        val action = when (o.kind) {
            "delete" -> "rm -rf -- " + qs(source)
'''
new = '''        if (o.kind == "delete" && source in setOf(
                "/", "/data", "/system", "/vendor", "/product", "/metadata", "/dev", "/proc", "/sys")) {
            operation = null
            message = "禁止从文件管理器删除关键系统根目录"
            return
        }
        val action = when (o.kind) {
            "delete" -> "rm -rf -- " + qs(source)
'''
if s.count(old) != 1: raise SystemExit("DN41 delete guard drift")
s = s.replace(old,new)
p.write_text(s)
assert s.count('Modifier.weight(1f)) {') >= 8
assert 'if (o.kind == "delete" && source in setOf(' in s
print("DN41 menu RowScope and system-root deletion guards validated.")
