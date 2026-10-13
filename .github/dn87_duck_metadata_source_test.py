#!/usr/bin/env python3
"""D87 Duck metadata-only source experiment on the VERIFIED D82 build recipe.

This applies AFTER the original D82 patch sequence and BEFORE Gradle/R8.
It changes only Android component entry points. Original core / JNI stays intact.
No DEX rewriting, package identity change, key change, or executable rewrite.
"""
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path("source/manager/app/src/main")
JAVA = ROOT / "java"
ANDROID = "http://schemas.android.com/apk/res/android"
ET.register_namespace("android", ANDROID)
ET.register_namespace("tools", "http://schemas.android.com/tools")
def attr(name):
    return f"{{{ANDROID}}}{name}"

app_source = JAVA / "com/resukisu/resukisu/KernelSUApplication.kt"
main_source = JAVA / "com/resukisu/resukisu/ui/MainActivity.kt"
preload_source = JAVA / "com/resukisu/resukisu/magica/AppZygotePreload.java"
jni_source = ROOT / "cpp/jni.c"
manifest = ROOT / "AndroidManifest.xml"
settings = JAVA / "com/resukisu/resukisu/data/settings/SettingsPlatformRepository.kt"

# D82's upstream component classes are final Kotlin classes by default.
# Make only these two open: their existing methods and code remain unchanged.
for src, needle, replacement in (
    (app_source, "class KernelSUApplication : Application()", "open class KernelSUApplication : Application()"),
    (main_source, "class MainActivity : ComponentActivity()", "open class MainActivity : ComponentActivity()"),
):
    content = src.read_text(encoding="utf-8")
    if content.count(needle) != 1:
        raise SystemExit(f"Unexpected source, refused to modify: {src} : {needle}")
    src.write_text(content.replace(needle, replacement, 1), encoding="utf-8")

if "public class AppZygotePreload implements ZygotePreload" not in preload_source.read_text():
    raise SystemExit("ZygotePreload source unexpectedly changed")
native_method = "forkDontCareAndExecKsud"
jni_symbol = "Java_com_resukisu_resukisu_magica_AppZygotePreload_forkDontCareAndExecKsud"
if native_method not in preload_source.read_text() or jni_symbol not in jni_source.read_text():
    raise SystemExit("JNI method/export mismatch. Must NEVER silently rename native entrypoint.")

# Neutral manifest-visible delegates keep the complex D82 startup + PTY
# paths identical and avoid breaking explicitly referenced upstream activities.
entry = JAVA / "com/daily/notes/entry"
entry.mkdir(parents=True, exist_ok=True)
generated = {
    "NoteApp.kt": '''package com.daily.notes.entry

import com.resukisu.resukisu.KernelSUApplication

class NoteApp : KernelSUApplication()
''',
    "NoteHome.kt": '''package com.daily.notes.entry

import com.resukisu.resukisu.ui.MainActivity

class NoteHome : MainActivity()
''',
    "NotePreload.java": '''package com.daily.notes.entry;

import com.resukisu.resukisu.magica.AppZygotePreload;

/**
 * Framework-visible name only; all preload/JNI behavior stays in the
 * original superclass, whose native symbol matches libkernelsu.so.
 */
public final class NotePreload extends AppZygotePreload { }
''',
}
for name, content in generated.items():
    out = entry / name
    if out.exists():
        raise SystemExit(f"Refusing to overwrite file: {out}")
    out.write_text(content, encoding="utf-8")

tree = ET.parse(manifest)
application = tree.getroot().find("application")
if application is None:
    raise SystemExit("Application node not found")
if application.get(attr("name")) != ".KernelSUApplication":
    raise SystemExit(f"Unexpected manifest app class: {application.get(attr('name'))}")
old_preload = application.get(attr("zygotePreloadName"))
if old_preload != "com.resukisu.resukisu.magica.AppZygotePreload":
    raise SystemExit(f"Unexpected zygote preload {old_preload}")
application.set(attr("name"), "com.daily.notes.entry.NoteApp")
application.set(attr("zygotePreloadName"), "com.daily.notes.entry.NotePreload")

activities = [x for x in application.findall("activity") if x.get(attr("name")) == ".ui.MainActivity"]
aliases = [x for x in application.findall("activity-alias") if x.get(attr("name")) == ".ui.MainActivityAlias"]
if len(activities) != 1 or len(aliases) != 1:
    raise SystemExit("Expected one D82 launcher activity and one alias")
activities[0].set(attr("name"), "com.daily.notes.entry.NoteHome")
aliases[0].set(attr("name"), "com.daily.notes.entry.NoteHomeAlias")
aliases[0].set(attr("targetActivity"), "com.daily.notes.entry.NoteHome")
tree.write(manifest, encoding="utf-8", xml_declaration=True)

# D82's alternate icon setting hardcodes old component class names; align it.
# This preserves both launcher icon modes instead of silently disabling one.
settings_text = settings.read_text(encoding="utf-8")
for old, new in (
    ('"com.resukisu.resukisu.ui.MainActivity"', '"com.daily.notes.entry.NoteHome"'),
    ('"com.resukisu.resukisu.ui.MainActivityAlias"', '"com.daily.notes.entry.NoteHomeAlias"'),
):
    if settings_text.count(old) != 1:
        raise SystemExit(f"Unexpected launcher toggle call: {old}, count={settings_text.count(old)}")
    settings_text = settings_text.replace(old, new, 1)
settings.write_text(settings_text, encoding="utf-8")

# Activity alias doesn't need a Java class: the manifest alias name is a
# component identifier, not a runtime class definition.
out = manifest.read_text(encoding="utf-8")
for fragment in (
    "com.daily.notes.entry.NoteApp",
    "com.daily.notes.entry.NotePreload",
    "com.daily.notes.entry.NoteHome",
    "com.daily.notes.entry.NoteHomeAlias",
):
    if fragment not in out:
        raise SystemExit(f"Missing manifest entry {fragment}")
if any(token in out for token in (
    'android:name=".KernelSUApplication"',
    'android:name=".ui.MainActivity"',
    'android:name=".ui.MainActivityAlias"',
    'com.resukisu.resukisu.magica.AppZygotePreload',
)):
    raise SystemExit("Original Duck metadata leaked in manifest")
print("D87: Application, Launcher & Zygote metadata neutralized in source")
print("D87: JNI native method and symbol are unchanged and verified")
print("D87: original package name, manager certificate and kernel UAPI remain unchanged")
