#!/system/bin/sh
# Exit 88 means a deliberate collision skip; 90 means an unsafe destination.
# No paths are evaluated as shell source. The Kotlin caller passes four quoted args.
BB=/data/adb/ksu/bin/busybox
KIND=$1 S=$2 D=$3 MODE=$4
case "${S##*/}" in ''|.|..) exit 90;; esac
case "$KIND" in copy|move|delete) ;; *) exit 91;; esac
case "$MODE" in skip|rename|replace) ;; *) exit 91;; esac
SOURCE_PARENT=${S%/*}
[ -n "$SOURCE_PARENT" ] || SOURCE_PARENT=/
SP=$($BB realpath "$SOURCE_PARENT") || exit 89
SC="${SP%/}/${S##*/}"
case "$SC" in /|/data|/system|/vendor|/product|/metadata|/dev|/proc|/sys|/storage) exit 90;; esac
[ -e "$SC" ] || [ -L "$SC" ] || exit 89
S=$SC
if [ "$KIND" = delete ]; then
    $BB rm -rf -- "$S"
    exit $?
fi
DEST_PARENT=${D%/*}
case "${D##*/}" in ''|.|..) exit 90;; esac
[ -n "$DEST_PARENT" ] || DEST_PARENT=/
DP=$($BB realpath "$DEST_PARENT") || exit 89
[ -d "$DP" ] || exit 89
DC="${DP%/}/${D##*/}"
D=$DC
if [ "$SC" = "$DC" ]; then
    [ "$KIND" = copy ] && [ "$MODE" = rename ] || exit 90
fi
if [ -d "$S" ] && [ ! -L "$S" ]; then
    SR=$($BB realpath "$S") || exit 89
    case "$DP/" in "$SR/"*) exit 90;; esac
fi
if [ "$MODE" = rename ]; then
    n=1
    while [ -e "$D" ] || [ -L "$D" ]; do
        D="$DC ($n)"
        n=$((n + 1))
        [ "$n" -le 1000 ] || exit 82
    done
elif [ "$MODE" = replace ]; then
    if [ -d "$S" ] && [ ! -L "$S" ]; then
        if [ -e "$D" ] || [ -L "$D" ]; then exit 88; fi
    else
        [ -f "$S" ] && [ ! -L "$S" ] && [ ! -d "$D" ] && [ ! -L "$D" ] || exit 83
    fi
else
    if [ -e "$D" ] || [ -L "$D" ]; then exit 88; fi
fi
shared_storage() {
    case "$1" in /storage/*|/mnt/media_rw/*|/mnt/runtime/*|/mnt/user/*) return 0;; esac
    return 1
}

# Never request source SELinux labels (-Z). Shared storage has synthetic
# ownership/modes/times, so do not request those on either side of a transfer.
COPY_FLAGS=-a
if shared_storage "$SP" || shared_storage "$DP"; then COPY_FLAGS=-RP; fi

safe_tree() {
    local entry
    if [ -L "$1" ] || [ -f "$1" ]; then return 0; fi
    [ -d "$1" ] || return 1
    for entry in "$1"/* "$1"/.[!.]* "$1"/..?*; do
        [ -e "$entry" ] || [ -L "$entry" ] || continue
        safe_tree "$entry" || return 1
    done
}

verify_tree() {
    local left="$1" right="$2" entry a b
    if [ -L "$left" ]; then
        [ -L "$right" ] || return 1
        a=$($BB readlink -- "$left") || return 1
        b=$($BB readlink -- "$right") || return 1
        [ "$a" = "$b" ]
    elif [ -f "$left" ]; then
        [ -f "$right" ] && [ ! -L "$right" ] || return 1
        a=$($BB sha256sum < "$left") || return 1
        b=$($BB sha256sum < "$right") || return 1
        a=${a%% *} b=${b%% *}
        [ "${#a}" -eq 64 ] && [ "$a" = "$b" ]
    elif [ -d "$left" ]; then
        [ -d "$right" ] && [ ! -L "$right" ] || return 1
        for entry in "$left"/* "$left"/.[!.]* "$left"/..?*; do
            [ -e "$entry" ] || [ -L "$entry" ] || continue
            verify_tree "$entry" "$right/${entry##*/}" || return 1
        done
        for entry in "$right"/* "$right"/.[!.]* "$right"/..?*; do
            [ -e "$entry" ] || [ -L "$entry" ] || continue
            [ -e "$left/${entry##*/}" ] || [ -L "$left/${entry##*/}" ] || return 1
        done
    else
        return 1
    fi
}

safe_tree "$S" || exit 90
STAGE=$($BB mktemp -d "$DP/.dn-transfer.XXXXXXXX") || exit 84
BAK= KEEP_BAK=0
cleanup() {
    $BB rm -rf -- "$STAGE"
    if [ -n "$BAK" ] && [ "$KEEP_BAK" = 0 ]; then $BB rm -f -- "$BAK"; fi
}
trap cleanup EXIT
trap 'exit 130' HUP INT TERM

# BusyBox mv's EXDEV fallback forces the source SELinux context onto DEST.
# Avoid that fallback entirely: create under destination policy, verify content,
# then rename the staged object within its destination filesystem.
$BB cp "$COPY_FLAGS" -- "$S" "$STAGE/item" || exit 84
verify_tree "$S" "$STAGE/item" || exit 85
if [ "$MODE" = replace ] && [ -f "$D" ]; then
    [ ! -L "$D" ] || exit 83
    BAK=$($BB mktemp "$DP/.dn-old.XXXXXXXX") || exit 86
    $BB cp "$COPY_FLAGS" -- "$D" "$BAK" || exit 86
    verify_tree "$D" "$BAK" || exit 86
fi
if [ "$MODE" = replace ]; then
    [ ! -L "$D" ] && [ ! -d "$D" ] || exit 83
    $BB mv -fT -- "$STAGE/item" "$D" || exit 87
else
    $BB mv -nT -- "$STAGE/item" "$D" || exit 87
    # mv -n returns success when a concurrent collision caused a skip.
    if [ -e "$STAGE/item" ] || [ -L "$STAGE/item" ]; then exit 88; fi
fi
KEEP_BAK=1
if [ "$KIND" = move ]; then $BB rm -rf -- "$S" || exit 87; fi
exit 0
