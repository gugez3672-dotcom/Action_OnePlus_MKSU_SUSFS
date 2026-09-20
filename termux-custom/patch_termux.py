#!/usr/bin/env python3
import argparse
import os
import re
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--app", required=True)
parser.add_argument("--packages", required=True)
args = parser.parse_args()

app = Path(args.app)
packages = Path(args.packages)
package_name = os.environ.get("CUSTOM_PACKAGE", "io.aurel.terminal")
app_name = os.environ.get("CUSTOM_APP_NAME", "Aurel Terminal")

def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")

def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")

def replace_required(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Expected pattern not found for {label}: {old!r}")
    return text.replace(old, new)

# termux-packages: package identity controls the Android app data dir and $PREFIX.
properties = packages / "scripts/properties.sh"
s = read(properties)
s = replace_required(
    s,
    'TERMUX_APP__PACKAGE_NAME="com.termux"',
    f'TERMUX_APP__PACKAGE_NAME="{package_name}"',
    "TERMUX_APP__PACKAGE_NAME",
)
write(properties, s)

# Current master has a stale variable at this call site. Use the architecture
# currently being built so the generated bootstrap second-stage metadata is valid.
bootstrap_script = packages / "scripts/build-bootstraps.sh"
s = read(bootstrap_script)
# Current master references an undefined per-arch built-marker directory when
# -f is used. With an empty variable that becomes "rm -f /*". Use the actual
# built marker directory defined by the script instead.
s = s.replace(
    'rm -f "$TERMUX_BUILT_PACKAGES_DIRECTORY_FOR_ARCH"/*',
    'mkdir -p "$TERMUX_BUILT_PACKAGES_DIRECTORY"\\n\\t\\trm -f "$TERMUX_BUILT_PACKAGES_DIRECTORY"/*',
)
s = s.replace(
    'add_termux_bootstrap_second_stage_files "$package_arch"',
    'add_termux_bootstrap_second_stage_files "$TERMUX_ARCH"',
)
write(bootstrap_script, s)

# termux-app Gradle configuration.
build_gradle = app / "app/build.gradle"
s = read(build_gradle)

if re.search(r'(?m)^\s*applicationId\s+["\']', s):
    s = re.sub(
        r'(?m)^(\s*)applicationId\s+["\'][^"\']+["\']',
        rf'\1applicationId "{package_name}"',
        s,
        count=1,
    )
else:
    s = replace_required(
        s,
        "    defaultConfig {\n",
        f'    defaultConfig {{\n        applicationId "{package_name}"\n',
        "applicationId insertion",
    )

s = replace_required(
    s,
    'manifestPlaceholders.TERMUX_PACKAGE_NAME = "com.termux"',
    f'manifestPlaceholders.TERMUX_PACKAGE_NAME = "{package_name}"',
    "manifest package",
)

# Display labels only; keep Java namespaces com.termux.* unchanged.
for key, old_name, new_name in [
    ("TERMUX_APP_NAME", "Termux", app_name),
    ("TERMUX_API_APP_NAME", "Termux:API", f"{app_name}:API"),
    ("TERMUX_BOOT_APP_NAME", "Termux:Boot", f"{app_name}:Boot"),
    ("TERMUX_FLOAT_APP_NAME", "Termux:Float", f"{app_name}:Float"),
    ("TERMUX_STYLING_APP_NAME", "Termux:Styling", f"{app_name}:Styling"),
    ("TERMUX_TASKER_APP_NAME", "Termux:Tasker", f"{app_name}:Tasker"),
    ("TERMUX_WIDGET_APP_NAME", "Termux:Widget", f"{app_name}:Widget"),
]:
    s = s.replace(
        f'manifestPlaceholders.{key} = "{old_name}"',
        f'manifestPlaceholders.{key} = "{new_name}"',
    )

# Build only the phone architecture.
s = re.sub(
    r"include 'x86', 'x86_64', 'armeabi-v7a', 'arm64-v8a'",
    "include 'arm64-v8a'",
    s,
    count=1,
)
s = s.replace("universalApk true", "universalApk false", 1)

# Never replace our custom bootstrap with an upstream com.termux bootstrap.
pattern = re.compile(
    r'def downloadBootstrap\(String arch, String expectedChecksum, String version\) \{.*?\n\}\n\nclean \{',
    re.S,
)
replacement = f'''def downloadBootstrap(String arch, String expectedChecksum, String version) {{
    if (arch != "aarch64") return
    def localUrl = "src/main/cpp/bootstrap-" + arch + ".zip"
    def file = new File(projectDir, localUrl)
    if (!file.exists()) {{
        throw new GradleException("Custom bootstrap missing: " + localUrl)
    }}
}}

clean {{'''
s, n = pattern.subn(replacement, s, count=1)
if n != 1:
    raise RuntimeError("Failed to replace downloadBootstrap()")
write(build_gradle, s)

# Runtime constants: application id and app label.
constants = app / "termux-shared/src/main/java/com/termux/shared/termux/TermuxConstants.java"
s = read(constants)
s = replace_required(
    s,
    'public static final String TERMUX_PACKAGE_NAME = "com.termux";',
    f'public static final String TERMUX_PACKAGE_NAME = "{package_name}";',
    "TermuxConstants package",
)
s = replace_required(
    s,
    'public static final String TERMUX_APP_NAME = "Termux";',
    f'public static final String TERMUX_APP_NAME = "{app_name}";',
    "TermuxConstants app name",
)
write(constants, s)

# Resource entities used by the app and shared library.
for rel in [
    "app/src/main/res/values/strings.xml",
    "termux-shared/src/main/res/values/strings.xml",
]:
    p = app / rel
    s = read(p)
    s = replace_required(
        s,
        '<!ENTITY TERMUX_PACKAGE_NAME "com.termux">',
        f'<!ENTITY TERMUX_PACKAGE_NAME "{package_name}">',
        f"{rel} package entity",
    )
    s = replace_required(
        s,
        '<!ENTITY TERMUX_APP_NAME "Termux">',
        f'<!ENTITY TERMUX_APP_NAME "{app_name}">',
        f"{rel} app entity",
    )
    s = s.replace(
        '<!ENTITY TERMUX_PREFIX_DIR_PATH "/data/data/com.termux/files/usr">',
        f'<!ENTITY TERMUX_PREFIX_DIR_PATH "/data/data/{package_name}/files/usr">',
    )
    write(p, s)

# Android shortcut intents target the applicationId, while targetClass remains
# in the original Java namespace as recommended upstream.
shortcuts = app / "app/src/main/res/xml/shortcuts.xml"
s = read(shortcuts)
s = replace_required(
    s,
    'android:targetPackage="com.termux"',
    f'android:targetPackage="{package_name}"',
    "shortcut targetPackage",
)
write(shortcuts, s)

# Sanity checks.
checks = {
    "applicationId": (build_gradle, f'applicationId "{package_name}"'),
    "manifest package": (build_gradle, f'TERMUX_PACKAGE_NAME = "{package_name}"'),
    "runtime constant": (constants, f'TERMUX_PACKAGE_NAME = "{package_name}"'),
    "packages prefix source": (properties, f'TERMUX_APP__PACKAGE_NAME="{package_name}"'),
    "shortcut package": (shortcuts, f'android:targetPackage="{package_name}"'),
}
for label, (path, needle) in checks.items():
    if needle not in read(path):
        raise RuntimeError(f"Sanity check failed: {label}")

shared_strings = read(app / "termux-shared/src/main/res/values/strings.xml")
if "/data/data/com.termux/files/usr" in shared_strings:
    raise RuntimeError("Old com.termux prefix still present in shared strings")

print(f"Patched Termux for package: {package_name}")
print(f"Display name: {app_name}")
print("Java namespaces intentionally remain com.termux.* for upstream compatibility.")
