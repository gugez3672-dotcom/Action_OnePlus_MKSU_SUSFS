#!/usr/bin/env python3
"""Map GitHub Actions run_number to Daily Notes manager APK version.

Every workflow invocation has its own number, even when the build fails:
  run #74 -> Android versionName D1.0.74, versionCode 35174.
A rerun of the same GitHub Actions run retains its run_number (and version).
Do not modify KernelSU UAPI, kernel, ksud, package name or signing.
"""
from pathlib import Path
import os
import re

run_number = os.environ.get("GITHUB_RUN_NUMBER", "").strip()
if not re.fullmatch(r"[1-9][0-9]*", run_number):
    raise SystemExit(f"Missing/invalid GITHUB_RUN_NUMBER: {run_number!r}")
revision = int(run_number)
version = f"D1.0.{revision}"
version_code = 35100 + revision
if version_code <= 35154:
    raise SystemExit("Android versionCode must exceed existing signed APK 35154")
if os.environ.get("MANAGER_DISPLAY_VERSION") != version:
    raise SystemExit("Version drift between GitHub workflow and manager patch")
if os.environ.get("MANAGER_VERSION_CODE") != str(version_code):
    raise SystemExit("VersionCode drift between GitHub workflow and manager patch")

app_root = Path("source/manager/build.gradle.kts")
content = app_root.read_text(encoding="utf-8")
patches = {
    'extra["managerVersionCode"] = 30000 + getGitCommitCount() + 700':
        f'extra["managerVersionCode"] = {version_code}',
    'extra["managerVersionName"] = getGitDescribe()':
        f'extra["managerVersionName"] = "{version}"',
}
for before, after in patches.items():
    if content.count(before) != 1:
        raise SystemExit(f"Unexpected upstream Gradle version anchor: {before}")
    content = content.replace(before, after, 1)
app_root.write_text(content, encoding="utf-8")

apk = Path("source/manager/app/build.gradle.kts").read_text(encoding="utf-8")
# DN23 intentionally pins the previous public version. Upgrade the actual
# Android versionName after its patch; keep the manager versionCode monotonic.
old_name = 'versionName = "V4.2.0"'
if apk.count(old_name) != 1:
    raise SystemExit("Unexpected DN23 application versionName override")
apk = apk.replace(old_name, f'versionName = "{version}"', 1)
Path("source/manager/app/build.gradle.kts").write_text(apk, encoding="utf-8")
assert f'versionName = "{version}"' in apk
assert 'versionCode = managerVersionCode' in apk
assert 'applicationId = "com.daily.notes"' in apk

assert f'extra["managerVersionName"] = "{version}"' in content
assert f'extra["managerVersionCode"] = {version_code}' in content
print(f"DN57 versionName={version}, versionCode={version_code}, package=com.daily.notes; KSU UAPI unchanged")
