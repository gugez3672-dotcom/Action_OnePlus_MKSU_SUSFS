#!/usr/bin/env python3
"""Apply Daily Notes independent manager version from one version manifest.

Only Android application versionName/versionCode are changed. Do not patch KSU
UAPI constants, kernel root protocol, ksud binaries, package name or signing.
To release the next version change .github/daily-notes-version.txt to D1.0.75.
"""
from pathlib import Path
import re

version_file = Path(".github/daily-notes-version.txt")
version = version_file.read_text(encoding="utf-8").strip()
match = re.fullmatch(r"D1\.0\.(\d{1,3})", version)
if not match:
    raise SystemExit(f"Daily Notes version format invalid: {version!r}")
revision = int(match.group(1))
version_code = 35100 + revision
if version_code <= 35154:
    raise SystemExit("Android versionCode must exceed existing signed APK 35154")

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
assert 'versionName = managerVersionName' in apk
assert 'versionCode = managerVersionCode' in apk
assert 'applicationId = "com.daily.notes"' in apk

assert f'extra["managerVersionName"] = "{version}"' in content
assert f'extra["managerVersionCode"] = {version_code}' in content
print(f"DN57 versionName={version}, versionCode={version_code}, package=com.daily.notes; KSU UAPI unchanged")
