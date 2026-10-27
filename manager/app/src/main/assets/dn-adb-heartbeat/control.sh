#!/system/bin/sh
# D110: event-driven WG keepalive; no resident process or periodic polling.
# prepare: invoked before Box4 starts; sync: manager event + SIGHUP if changed.
set -eu
umask 077
base=/data/adb/ksu/dn-adb-heartbeat
config=/data/adb/box/sing-box/config.json
core=/data/adb/box/bin/sing-box
busybox=/data/adb/ksu/bin/busybox
case "${1:-}" in prepare|sync) mode=$1;; *) exit 2;; esac
[ -r "$config" ] && [ -x "$core" ] && [ -r "$base/keepalive.awk" ] || exit 3

# Serialize app instances in different Android users. Bounded wait; recover a
# lock left by a killed command/reboot, using boot ID and the recorded PID.
lock=$base/lock
boot=$(cat /proc/sys/kernel/random/boot_id)
attempt=0
while ! mkdir "$lock" 2>/dev/null; do
    oldboot=; oldpid=
    if [ -r "$lock/owner" ]; then read -r oldboot oldpid < "$lock/owner" || true; fi
    case "$oldpid" in ''|*[!0-9]*) alive=0;; *) if kill -0 "$oldpid" 2>/dev/null; then alive=1; else alive=0; fi;; esac
    if { [ -n "$oldboot" ] && { [ "$oldboot" != "$boot" ] || [ "$alive" = 0 ]; }; } || { [ -z "$oldboot" ] && [ "$attempt" -ge 20 ]; }; then
        rm -f "$lock/owner"; rmdir "$lock" 2>/dev/null || true
    fi
    attempt=$((attempt + 1))
    [ "$attempt" -lt 50 ] || exit 4
    sleep 0.1
done
printf '%s %s\n' "$boot" "$$" > "$lock/owner"
tmp=$config.d110.$$
cleanup() { rm -f "$tmp" "$lock/owner"; rmdir "$lock" 2>/dev/null || true; }
trap cleanup EXIT
trap 'exit 1' HUP INT TERM

# Keepalive runs only while network ADB is actually listening on the chosen
# port; anything else (off, USB debugging off, after reboot) means 0.
want=${2:-}
case "$want" in ''|*[!0-9]*) want=$(cat /data/adb/ksu/.adb_tcp_port 2>/dev/null || true);; esac
case "$want" in ''|*[!0-9]*) want=8363;; esac
interval=0
port=$(getprop service.adb.tcp.port)
case "$port" in ''|*[!0-9]*) port=0;; esac
if [ "$(/system/bin/settings get global adb_enabled)" = 1 ] && [ "$port" = "$want" ]; then
    # adbd can be briefly restarting directly after a manager toggle.
    attempt=0
    while [ "$(getprop init.svc.adbd)" != running ] && [ "$mode" = sync ] && [ "$attempt" -lt 20 ]; do
        attempt=$((attempt + 1)); sleep 0.1
    done
    if [ "$(getprop init.svc.adbd)" = running ]; then interval=25; fi
fi
"$busybox" awk -v interval="$interval" -f "$base/keepalive.awk" "$config" > "$tmp" || exit 5
if "$busybox" cmp -s "$config" "$tmp"; then exit 0; fi

# Validate before replacement. Errors can include private configuration, so
# capture them in a root-only file rather than the manager/ADB output.
export ENABLE_DEPRECATED_LEGACY_DNS_FAKEIP_OPTIONS=true
export ENABLE_DEPRECATED_LEGACY_DNS_SERVERS=true
export ENABLE_DEPRECATED_OUTBOUND_DNS_RULE_ITEM=true
export ENABLE_DEPRECATED_MISSING_DOMAIN_RESOLVER=true
"$core" check -c "$tmp" > "$base/check.log" 2>&1 || exit 6
chmod 600 "$tmp"
chown 0:3005 "$tmp"
chcon --reference="$config" "$tmp" 2>/dev/null || true
cp -p "$config" "$base/previous.json"
mv -f "$tmp" "$config"

if [ "$mode" = sync ]; then
    # Use Box4's own PID file: no shell loop over every Android process.
    # A stopped/disabled Box4 is never started by this helper.
    pidfile=/data/adb/box/run/sing-box.pid
    target=$(cat "$pidfile" 2>/dev/null || true)
    case "$target" in ''|*[!0-9]*) target=0;; esac
    if [ "$target" -gt 1 ] && kill -0 "$target" 2>/dev/null; then
        executable=$(readlink "/proc/$target/exe" 2>/dev/null || true)
        command=$($busybox tr '\000' ' ' < "/proc/$target/cmdline" 2>/dev/null || true)
        if [ "$executable" != "$core" ]; then cp -p "$base/previous.json" "$config"; exit 7; fi
        case "$command" in *'run -D /data/adb/box/sing-box '*) :;; *) cp -p "$base/previous.json" "$config"; exit 7;; esac
        if ! kill -HUP "$target"; then cp -p "$base/previous.json" "$config"; exit 8; fi
    fi
fi
printf 'keepalive=%s mode=%s\n' "$interval" "$mode"
