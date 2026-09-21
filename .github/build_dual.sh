#!/usr/bin/env bash
set -euo pipefail

RESUKISU_COMMIT=6ec8d9a8a8be30878c388504cacf8ae7849c757b
UPSTREAM_MANAGER_RUN=35234729417
KEY_ALIAS=notes
EXPECTED_MANAGER_CERT_SHA256=7b6fcd9e7f440833ee8a5a3860f3ff5b7b367a0dabb36c1d5f0fd52064bf283e
EXPECTED_MANAGER_CERT_SIZE=890

: "${MANAGER_KEYSTORE_B64:?MANAGER_KEYSTORE_B64 is required}"
: "${MANAGER_KEYSTORE_PASSWORD:?MANAGER_KEYSTORE_PASSWORD is required}"

git clone https://github.com/ReSukiSU/ReSukiSU.git source
git -C source checkout "$RESUKISU_COMMIT"
test "$(git -C source rev-parse HEAD)" = "$RESUKISU_COMMIT"
python3 .github/dn_patch.py

cd source/manager
printf '%s' "$MANAGER_KEYSTORE_B64" | base64 -d > key.jks
test -s key.jks
keytool -list -keystore key.jks -storepass "$MANAGER_KEYSTORE_PASSWORD" -alias "$KEY_ALIAS" >/dev/null
keytool -exportcert \
  -alias "$KEY_ALIAS" \
  -keystore key.jks \
  -storepass "$MANAGER_KEYSTORE_PASSWORD" \
  -file manager-cert.der >/dev/null
CERT_SIZE=$(stat -c%s manager-cert.der)
CERT_SHA256=$(sha256sum manager-cert.der | awk '{print $1}')
echo "permanent_cert_size=$CERT_SIZE"
echo "permanent_cert_sha256=$CERT_SHA256"
test "$CERT_SIZE" = "$EXPECTED_MANAGER_CERT_SIZE"
test "$CERT_SHA256" = "$EXPECTED_MANAGER_CERT_SHA256"

{
  echo "KEYSTORE_FILE=key.jks"
  echo "KEYSTORE_PASSWORD=$MANAGER_KEYSTORE_PASSWORD"
  echo "KEY_ALIAS=$KEY_ALIAS"
  echo "KEY_PASSWORD=$MANAGER_KEYSTORE_PASSWORD"
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
      -P "$MANAGER_KEYSTORE_PASSWORD" -S "$MANAGER_KEYSTORE_PASSWORD" \
      -n "DailyNotes_2.4.3_40203_variant-$n" --no-strip
  )
  APK=$(find source/dist -maxdepth 1 -type f -name '*.apk' | head -n1)
  test -n "$APK"
  cp "$APK" "out/DailyNotes-2.4.3-variant-$n-final.apk"
done

AAPT=$(find "${ANDROID_HOME}/build-tools" -type f -name aapt 2>/dev/null | sort -V | tail -n1)
APKSIGNER=$(find "${ANDROID_HOME}/build-tools" -type f -name apksigner 2>/dev/null | sort -V | tail -n1)
test -x "$AAPT"
test -x "$APKSIGNER"

for n in a b; do
  APK="out/DailyNotes-2.4.3-variant-$n-final.apk"
  "$APKSIGNER" verify --verbose "$APK" > "out/variant-$n-apksigner.txt"
  grep -q 'Verified using v2 scheme (APK Signature Scheme v2): true' "out/variant-$n-apksigner.txt"
  BADGING=$("$AAPT" dump badging "$APK")
  PKG=$(printf '%s\n' "$BADGING" | sed -n "s/^package: name='\([^']*\)'.*/\1/p" | head -n1)
  test "$PKG" = "com.daily.notes"
  if [ "$n" = "a" ]; then
    ! printf '%s\n' "$BADGING" | grep -q '^launchable-activity:'
  else
    printf '%s\n' "$BADGING" | grep -q '^launchable-activity:'
  fi
done

sha256sum out/DailyNotes-2.4.3-variant-*-final.apk > out/SHA256SUMS.txt
cat > out/VARIANTS.txt <<EOF
source_commit=$RESUKISU_COMMIT
package=com.daily.notes
cert_sha256=$EXPECTED_MANAGER_CERT_SHA256
cert_size=$EXPECTED_MANAGER_CERT_SIZE
variant_a=no_launcher_no_exported_entry
variant_b=launcher_enabled_notes_activity_exported
kernel_rebuild_required=no
EOF
