#!/usr/bin/env python3
"""D85 V2 exact-payload class/JNI audit patch. Fail closed on any mismatch.

Only same-byte-length substitutions are permitted, preserving DEX string indexes,
binary AXML string lengths and ELF layout. APK signing is a separate CI step.
"""
import argparse
import hashlib
import json
import struct
import zipfile
import zlib
from pathlib import Path

OLD_BASE = "com.resukisu.resukisu"
NEW_BASE = "com.notepads.notepads"
NAMES = {
    "KernelSUApplication": "NotebookApplication",
    "AppZygotePreload": "AppThreadPreload",
    "MainActivityAlias": "HomeActivityAlias",
    "MainActivity": "HomeActivity",
}
COMPONENTS = {
    "application": (f"{OLD_BASE}.KernelSUApplication", f"{NEW_BASE}.NotebookApplication"),
    "zygote": (f"{OLD_BASE}.magica.AppZygotePreload", f"{NEW_BASE}.magica.AppThreadPreload"),
    "launcher": (f"{OLD_BASE}.ui.MainActivity", f"{NEW_BASE}.ui.HomeActivity"),
    "launcher_alias": (f"{OLD_BASE}.ui.MainActivityAlias", f"{NEW_BASE}.ui.HomeActivityAlias"),
}
JNI = (
    "Java_com_resukisu_resukisu_magica_AppZygotePreload_forkDontCareAndExecKsud",
    "Java_com_notepads_notepads_magica_AppThreadPreload_forkDontCareAndExecKsud",
)


def check_same_length(pairs):
    for old, new in pairs:
        if len(old.encode()) != len(new.encode()):
            raise ValueError(f"Refusing unequal-length rewrite: {old} -> {new}")


def patch_bytes(buf: bytes, pairs, *, allow_utf16=False):
    counts = {}
    for old, new in sorted(pairs, key=lambda item: len(item[0]), reverse=True):
        encodings = ["utf-8", "utf-16le"] if allow_utf16 else ["utf-8"]
        for encoding in encodings:
            src, dst = old.encode(encoding), new.encode(encoding)
            if len(src) != len(dst):
                raise AssertionError("not length preserving")
            matches = buf.count(src)
            if matches:
                buf = buf.replace(src, dst)
            counts[f"{old} [{encoding}]"] = matches
    return buf, counts


def dex_header_fix(content):
    if len(content) < 112 or not content.startswith(b"dex\n"):
        raise ValueError("Unexpected DEX header")
    data = bytearray(content)
    expected = struct.unpack_from("<I", data, 32)[0]
    if expected != len(data):
        raise ValueError(f"DEX file_size mismatch {expected} != {len(data)}")
    data[12:32] = hashlib.sha1(data[32:]).digest()
    struct.pack_into("<I", data, 8, zlib.adler32(data[12:]) & 0xFFFFFFFF)
    return bytes(data)


def get_pairs(dot=False):
    items = []
    for old, new in COMPONENTS.values():
        if dot:
            items.append((old, new))
        else:
            items.append((old.replace(".", "/"), new.replace(".", "/")))
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args()
    source, target = Path(args.input), Path(args.output)
    check_same_length(list(COMPONENTS.values()) + [JNI])
    all_pairs = get_pairs(dot=True) + get_pairs(dot=False)
    check_same_length(all_pairs)
    report = {"baseline_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "entries": {}}
    changed_files = set()

    with zipfile.ZipFile(source, "r") as zin, zipfile.ZipFile(target, "w") as zout:
        file_names = set(zin.namelist())
        dex_names = [n for n in file_names if n.startswith("classes") and n.endswith(".dex")]
        native = [n for n in file_names if n.endswith("/libkernelsu.so")]
        if "AndroidManifest.xml" not in file_names or not dex_names or len(native) != 1:
            raise RuntimeError("Missing manifest, classes*.dex or unique libkernelsu.so")

        seen_manifest = {k: 0 for k in COMPONENTS}
        seen_dex = {k: 0 for k in ("application", "zygote", "launcher")}
        jni_matches = 0
        for entry in zin.infolist():
            name = entry.filename
            original = zin.read(entry)
            updated = original
            local_counts = {}
            if name == "AndroidManifest.xml":
                updated, local_counts = patch_bytes(original, get_pairs(dot=True), allow_utf16=True)
                for component, (old, _) in COMPONENTS.items():
                    seen_manifest[component] += sum(local_counts.get(f"{old} [{e}]", 0)
                                                    for e in ("utf-8", "utf-16le"))
            elif name in dex_names:
                updated, local_counts = patch_bytes(original, all_pairs)
                for component in seen_dex:
                    old = COMPONENTS[component][0].replace(".", "/")
                    seen_dex[component] += local_counts.get(f"{old} [utf-8]", 0)
                if updated != original:
                    updated = dex_header_fix(updated)
            elif name == native[0]:
                # Direct JNI name lookup is required by AppZygotePreload.doPreload().
                # Do not alter the daemon libksud.so or the Root UAPI.
                updated, local_counts = patch_bytes(original, [JNI] +
                                                    get_pairs(dot=False) + get_pairs(dot=True))
                jni_matches = local_counts.get(f"{JNI[0]} [utf-8]", 0)
            if updated != original:
                changed_files.add(name)
                report["entries"][name] = {
                    "old_sha256": hashlib.sha256(original).hexdigest(),
                    "new_sha256": hashlib.sha256(updated).hexdigest(),
                    "replacements": {k: v for k, v in local_counts.items() if v},
                }
            if name.startswith("META-INF/") and name.upper().endswith((".RSA", ".SF", ".DSA", ".EC")):
                continue  # original is V2-only; protect against accidental legacy entries
            zout.writestr(entry, updated)

    report["manifest_components"] = seen_manifest
    report["dex_classes"] = seen_dex
    report["jni_symbol_rewrites"] = jni_matches
    report["changed_files"] = sorted(changed_files)
    if any(n == 0 for n in seen_manifest.values()):
        raise RuntimeError(f"Manifest class not found, refusing APK: {seen_manifest}")
    if any(n == 0 for n in seen_dex.values()):
        raise RuntimeError(f"DEX class not found, refusing APK: {seen_dex}")
    if jni_matches < 1:
        raise RuntimeError("Required native JNI export not found; refusing APK")
    expected = set(["AndroidManifest.xml", native[0]])
    if not expected.issubset(changed_files) or not any(n in changed_files for n in dex_names):
        raise RuntimeError(f"Unexpected changes: {sorted(changed_files)}")
    if not changed_files.issubset(expected | set(dex_names)):
        raise RuntimeError("Non-target APK member changed")

    # Verify no untouched content drift (especially libksud.so and resource tables).
    with zipfile.ZipFile(source) as a, zipfile.ZipFile(target) as b:
        for name in a.namelist():
            if name not in changed_files and not name.startswith("META-INF/"):
                if hashlib.sha256(a.read(name)).digest() != hashlib.sha256(b.read(name)).digest():
                    raise RuntimeError(f"Unexpected payload drift: {name}")
    Path(args.report).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print("Manifest:", seen_manifest)
    print("DEX:", seen_dex)
    print("JNI symbols:", jni_matches)
    print("Modified only:", ", ".join(sorted(changed_files)))


if __name__ == "__main__":
    main()
