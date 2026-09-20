#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$ROOT/_termux_custom_work"
OUT="$ROOT/termux-custom/out"
CUSTOM_PACKAGE="${CUSTOM_PACKAGE:-io.aurel.terminal}"
CUSTOM_APP_NAME="${CUSTOM_APP_NAME:-Aurel Terminal}"

export CUSTOM_PACKAGE CUSTOM_APP_NAME

echo "Host: $(uname -a)"
echo "Docker: $(docker --version 2>/dev/null || true)"

rm -rf "$WORK" "$OUT"
mkdir -p "$WORK" "$OUT"

echo "==> Clone upstream sources"
git clone --depth=1 https://github.com/termux/termux-app.git "$WORK/termux-app"
git clone --depth=1 https://github.com/termux/termux-packages.git "$WORK/termux-packages"

APP_SHA="$(git -C "$WORK/termux-app" rev-parse HEAD)"
PACKAGES_SHA="$(git -C "$WORK/termux-packages" rev-parse HEAD)"

echo "==> Patch package identity and bootstrap prefix"
python3 "$ROOT/termux-custom/patch_termux.py"   --app "$WORK/termux-app"   --packages "$WORK/termux-packages"

echo "==> Build aarch64 bootstrap from source"
cd "$WORK/termux-packages"
set +e
./scripts/run-docker.sh ./scripts/build-bootstraps.sh   -f   --architectures aarch64   --add openssh,curl,wget,git,jq,tmux   2>&1 | tee "$OUT/bootstrap-build.log"
BOOTSTRAP_RC=${PIPESTATUS[0]}
set -e
if [[ $BOOTSTRAP_RC -ne 0 ]]; then
  echo "Bootstrap build failed with code $BOOTSTRAP_RC"
  exit "$BOOTSTRAP_RC"
fi

BOOTSTRAP_ZIP="$WORK/termux-packages/bootstrap-aarch64.zip"
test -s "$BOOTSTRAP_ZIP"
cp "$BOOTSTRAP_ZIP" "$OUT/bootstrap-aarch64.zip"

echo "==> Install custom bootstrap into app source"
cp "$BOOTSTRAP_ZIP" "$WORK/termux-app/app/src/main/cpp/bootstrap-aarch64.zip"

echo "==> Build arm64-v8a APK"
cd "$WORK/termux-app"
export TERMUX_PACKAGE_VARIANT="apt-android-7"
export TERMUX_SPLIT_APKS_FOR_DEBUG_BUILDS="1"
export TERMUX_APP_VERSION_NAME="0.118.0+aurel"
export TERMUX_APK_VERSION_TAG="aurel-custom"

set +e
./gradlew assembleDebug --stacktrace 2>&1 | tee "$OUT/apk-build.log"
APK_RC=${PIPESTATUS[0]}
set -e
if [[ $APK_RC -ne 0 ]]; then
  echo "APK build failed with code $APK_RC"
  exit "$APK_RC"
fi

APK="$(find "$WORK/termux-app/app/build/outputs/apk/debug" -maxdepth 1 -type f -name '*arm64-v8a.apk' | head -n 1)"
if [[ -z "$APK" || ! -s "$APK" ]]; then
  echo "arm64-v8a APK not found"
  find "$WORK/termux-app/app/build/outputs/apk/debug" -maxdepth 1 -type f -print || true
  exit 1
fi

cp "$APK" "$OUT/AurelTerminal-arm64-v8a.apk"

echo "==> Validate output"
VALIDATED_BY="none"
if command -v apkanalyzer >/dev/null 2>&1; then
  FOUND_PACKAGE="$(apkanalyzer manifest application-id "$OUT/AurelTerminal-arm64-v8a.apk" | tr -d '\r')"
  [[ "$FOUND_PACKAGE" == "$CUSTOM_PACKAGE" ]] || {
    echo "Unexpected application id: '$FOUND_PACKAGE'"
    exit 1
  }
  VALIDATED_BY="apkanalyzer"
elif command -v aapt >/dev/null 2>&1; then
  FOUND_PACKAGE="$(aapt dump badging "$OUT/AurelTerminal-arm64-v8a.apk" | sed -n "s/^package: name='\([^']*\)'.*/\1/p" | head -n 1)"
  [[ "$FOUND_PACKAGE" == "$CUSTOM_PACKAGE" ]] || {
    echo "Unexpected application id: '$FOUND_PACKAGE'"
    exit 1
  }
  VALIDATED_BY="aapt"
fi

(
  cd "$OUT"
  sha256sum AurelTerminal-arm64-v8a.apk bootstrap-aarch64.zip > SHA256SUMS.txt
)

cat > "$OUT/build-info.txt" <<EOF
Custom package: $CUSTOM_PACKAGE
Display name: $CUSTOM_APP_NAME
Architecture: arm64-v8a / aarch64
Package variant: apt-android-7
Termux app commit: $APP_SHA
Termux packages commit: $PACKAGES_SHA
APK validation: $VALIDATED_BY

Bundled extra packages:
- openssh
- curl
- wget
- git
- jq
- tmux

Important:
- Java namespaces remain com.termux.* by design, as recommended by upstream.
- This build uses the upstream public debug/test signing key.
- Official Termux package repositories are compiled for com.termux and must not
  be mixed with this custom package prefix. Common tools are bundled into the
  bootstrap instead.
EOF

echo "==> Finished"
ls -lh "$OUT"
