#!/usr/bin/env bash
set -euo pipefail

RESUKISU_COMMIT=6ec8d9a8a8be30878c388504cacf8ae7849c757b
UPSTREAM_MANAGER_RUN=35234729417
KEY_ALIAS=notes
KEYSTORE_PASSWORD=ChangeMe_2026_Custom_Manager
KEY_PASSWORD=ChangeMe_2026_Custom_Manager

git clone https://github.com/ReSukiSU/ReSukiSU.git source
git -C source checkout "$RESUKISU_COMMIT"
python3 .github/dn_patch.py

cd source/manager
keytool -genkeypair -noprompt \
  -keystore key.jks \
  -storepass "$KEYSTORE_PASSWORD" \
  -keypass "$KEY_PASSWORD" \
  -alias "$KEY_ALIAS" \
  -keyalg RSA -keysize 2048 -validity 3650 \
  -dname "CN=Daily Notes CI, OU=Build, O=Local, L=Local, ST=Local, C=US"
{
  echo "KEYSTORE_FILE=key.jks"
  echo "KEYSTORE_PASSWORD=$KEYSTORE_PASSWORD"
  echo "KEY_ALIAS=$KEY_ALIAS"
  echo "KEY_PASSWORD=$KEY_PASSWORD"
} >> gradle.properties

chmod +x gradlew
./gradlew assembleRelease -Pcommit="$RESUKISU_COMMIT"
REL=app/build/outputs/apk/release
APK=$(find "$REL" -maxdepth 1 -type f -name '*arm64-v8a*release.apk' | head -n1)
test -n "$APK"
mkdir -p ../../variants
cp "$APK" ../../variants/variant-a-base.apk
cd ../..

python3 - <<'PY'
from pathlib import Path
import xml.etree.ElementTree as ET
NS="http://schemas.android.com/apk/res/android"
ET.register_namespace("android",NS)
p=Path("source/manager/app/src/main/AndroidManifest.xml")
tree=ET.parse(p)
root=tree.getroot()
app=root.find("application")
main=next(x for x in app.findall("activity") if x.get(f"{{{NS}}}name")==".ui.NotesActivity")
main.set(f"{{{NS}}}exported","true")
main.set(f"{{{NS}}}enabled","true")
f=ET.SubElement(main,"intent-filter")
a=ET.SubElement(f,"action")
a.set(f"{{{NS}}}name","android.intent.action.MAIN")
c=ET.SubElement(f,"category")
c.set(f"{{{NS}}}name","android.intent.category.LAUNCHER")
tree.write(p,encoding="utf-8",xml_declaration=True)
PY

cd source/manager
rm -rf app/build/outputs/apk/release
./gradlew assembleRelease -Pcommit="$RESUKISU_COMMIT"
REL=app/build/outputs/apk/release
APK=$(find "$REL" -maxdepth 1 -type f -name '*arm64-v8a*release.apk' | head -n1)
test -n "$APK"
cp "$APK" ../../variants/variant-b-base.apk
cd ../..

curl -fL --retry 3 \
  "https://nightly.link/ReSukiSU/ReSukiSU/actions/runs/$UPSTREAM_MANAGER_RUN/ksud-aarch64-linux-android.zip" \
  -o ksud.zip
unzip -o ksud.zip -d ksud >/dev/null
BIN=$(find ksud -type f -name ksud | head -n1)
test -n "$BIN"
mkdir -p source/target/aarch64-linux-android/release
cp "$BIN" source/target/aarch64-linux-android/release/ksud

mkdir -p out
for n in a b; do
  REL=source/manager/app/build/outputs/apk/release
  rm -rf "$REL" source/dist
  mkdir -p "$REL"
  cp "variants/variant-$n-base.apk" "$REL/custom-base.apk"
  (
    cd source
    python3 repack_apk.py repack \
      -b release -t release -a arm64-v8a \
      -K manager/key.jks -A "$KEY_ALIAS" \
      -P "$KEYSTORE_PASSWORD" -S "$KEY_PASSWORD" \
      -n "DailyNotes_2.4.3_40203_variant-$n" --no-strip
  )
  APK=$(find source/dist -maxdepth 1 -type f -name '*.apk' | head -n1)
  test -n "$APK"
  cp "$APK" "out/DailyNotes-2.4.3-variant-$n-ci.apk"
done
sha256sum out/*.apk > out/SHA256SUMS.txt
