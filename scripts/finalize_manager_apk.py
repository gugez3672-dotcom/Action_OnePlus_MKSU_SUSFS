#!/usr/bin/env python3
"""Validate a freshly built official backend, align and sign the Daily Notes arm64 APK.

Passwords are read by apksigner from a local ignored file, never command text.
"""
import argparse
import hashlib
from pathlib import Path
import subprocess
import zipfile
import struct
import json
import re

parser = argparse.ArgumentParser()
parser.add_argument("--base", type=Path, required=True)
parser.add_argument("--daemon-file", type=Path, required=True, help="Fresh official backend ELF")
parser.add_argument("--backend-record", type=Path, required=True)
parser.add_argument("--sdk", type=Path, required=True)
parser.add_argument("--keystore", type=Path, required=True)
parser.add_argument("--password-file", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--daemon-library", help="Output ELF filename; defaults to the component configuration")
args = parser.parse_args()
component_file = Path(__file__).resolve().parents[1] / "manager-custom/components.json"
component_config = json.loads(component_file.read_text()) if component_file.exists() else {}
library_name = args.daemon_library or component_config.get("daemon_library", "libksud.so")
assert re.fullmatch(r"lib[a-zA-Z0-9_]+\.so", library_name)
daemon_entries = {"lib/arm64-v8a/libksud.so", "lib/arm64-v8a/" + library_name}
output_entry = "lib/arm64-v8a/" + library_name
args.output.parent.mkdir(parents=True, exist_ok=True)
daemon = args.daemon_file.read_bytes()
record = json.loads(args.backend_record.read_text('utf-8'))
assert record['source_commit'] == '75e179d378d7aaa0de8946358a3384444c3e36b0'
assert record['package'] == 'com.daily.notes' and record['old_backend_imported'] is False
assert record['backend_sha256'] == hashlib.sha256(daemon).hexdigest()
assert record['branding_patch_sha256'] == hashlib.sha256((component_file.parent.parent / 'manager-support/official-backend-branding.patch').read_bytes()).hexdigest()
assert daemon[:4] == b'\x7fELF' and daemon[4] == 2 and struct.unpack_from('<H', daemon, 18)[0] == 183
assert library_name == 'libnote_runtime.so'
staging = args.output.with_suffix(".unaligned.apk")
aligned = args.output.with_suffix(".aligned.apk")
with zipfile.ZipFile(args.base) as source, zipfile.ZipFile(staging, "w") as target:
    for entry in source.infolist():
        if entry.filename in daemon_entries or entry.filename.startswith("META-INF/"):
            continue
        target.writestr(entry, source.read(entry))
    entry = zipfile.ZipInfo(output_entry)
    entry.compress_type = zipfile.ZIP_STORED
    entry.external_attr = 0o100755 << 16
    target.writestr(entry, daemon)
tools = args.sdk / "build-tools/37.0.0"
subprocess.run([str(tools / "zipalign.exe"), "-P", "16", "-f", "4", str(staging), str(aligned)], check=True)
signer = tools / "apksigner.bat"
subprocess.run([str(signer), "sign", "--ks", str(args.keystore), "--ks-key-alias", "notes",
                "--ks-pass", "file:" + str(args.password_file),
                "--v1-signing-enabled", "false", "--v2-signing-enabled", "true",
                "--v3-signing-enabled", "false", "--v4-signing-enabled", "false",
                "--out", str(args.output), str(aligned)], check=True)
verification = subprocess.check_output([str(signer), "verify", "--verbose", "--print-certs", str(args.output)], text=True)
expected = "7b6fcd9e7f440833ee8a5a3860f3ff5b7b367a0dabb36c1d5f0fd52064bf283e"
assert expected in verification.lower(), "Wrong manager signing certificate"
assert "Verified using v2 scheme (APK Signature Scheme v2): true" in verification
for scheme in ("v1", "v3", "v3.1", "v4"):
    assert not any(scheme + " scheme" in line and line.endswith("true") for line in verification.splitlines())
data = args.output.read_bytes()
eocd = data.rfind(b"PK\x05\x06")
central = struct.unpack_from("<I", data, eocd + 16)[0]
assert data[central-16:central] == b"APK Sig Block 42"
length = struct.unpack_from("<Q",data,central-24)[0]
start = central-length-8
assert struct.unpack_from("<Q",data,start)[0] == length
pos, ids = start+8, []
v2 = None
while pos < central-24:
    size = struct.unpack_from("<Q",data,pos)[0]
    assert size >= 4 and pos+8+size <= central-24
    identifier = struct.unpack_from("<I",data,pos+8)[0]
    ids.append(identifier)
    if identifier == 0x7109871a:
        v2 = data[pos+12:pos+8+size]
    pos += 8+size
assert ids.count(0x7109871a) == 1 and all(i in (0x7109871a,0x42726577) for i in ids), ids
def field(blob, offset=0):
    size = struct.unpack_from('<I', blob, offset)[0]
    end = offset + 4 + size
    assert end <= len(blob)
    return blob[offset+4:end], end
signers, _ = field(v2)
signer, end = field(signers)
assert end == len(signers), 'Expected one signing certificate identity'
signed_data, _ = field(signer)
_, offset = field(signed_data)
certificates, _ = field(signed_data, offset)
certificate, end = field(certificates)
assert end == len(certificates) and len(certificate) == 890
assert hashlib.sha256(certificate).hexdigest() == expected
with zipfile.ZipFile(args.output) as final:
    assert final.read(output_entry) == daemon
    if library_name != "libksud.so":
        assert not any(name.endswith("/libksud.so") for name in final.namelist())
    for library in ("libdn_session.so", "libdn_bash.so", "libreadline.so", "libncursesw.so", "libiconv.so", "libandroid-support.so"):
        assert "lib/arm64-v8a/" + library in final.namelist(), library
    with zipfile.ZipFile(args.base) as compiled:
        for name in compiled.namelist():
            if name.startswith("META-INF/") or name in daemon_entries: continue
            assert compiled.read(name) == final.read(name), name
subprocess.run([str(tools / "zipalign.exe"), "-c", "-P", "16", "4", str(args.output)], check=True)
print(verification)
print("backend_sha256=" + hashlib.sha256(daemon).hexdigest())
print("apk_sha256=" + hashlib.sha256(args.output.read_bytes()).hexdigest())
print("apk=" + str(args.output.resolve()))
