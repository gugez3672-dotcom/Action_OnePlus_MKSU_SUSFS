"""Inventory final Android identity surfaces and enforce reviewed exact exceptions."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TOKEN = re.compile(r'(?i)(?<![A-Za-z])(?:kernelsu|ksud|ksuinit|ksu)(?![a-z])')
FORBIDDEN = re.compile(r'(?i)me[./]weishu[./]kernelsu|com[./](?:resukisu|sukisu)|Java_me_weishu|lib(?:ksud|kernelsu|ksu)\.so')


def dex_strings(data):
    size, offset = struct.unpack_from('<II', data, 56)
    for i in range(size):
        pos = struct.unpack_from('<I', data, offset + 4*i)[0]
        while data[pos] & 128:
            pos += 1
        pos += 1
        end = data.index(0, pos)
        yield data[pos:end].decode('utf-8', errors='replace')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('apk', type=Path)
    parser.add_argument('--inventory-only', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sdk = Path(os.environ.get('ANDROID_HOME', ROOT / '.inputs/android-sdk'))
    exe = '.exe' if os.name == 'nt' else ''
    aapt = sdk / ('build-tools/37.0.0/aapt2' + exe)
    native = {}
    hits = []
    blocked = []

    def inspect(location, strings):
        for value in sorted(set(strings)):
            if FORBIDDEN.search(value):
                blocked.append({'location': location, 'value': value})
            if TOKEN.search(value):
                hits.append({'location': location, 'value': value,
                             'sha256': hashlib.sha256(value.encode()).hexdigest()})

    manifest = subprocess.check_output([str(aapt), 'dump', 'xmltree', '--file', 'AndroidManifest.xml', str(args.apk)], encoding='utf-8')
    badging = subprocess.check_output([str(aapt), 'dump', 'badging', str(args.apk)], encoding='utf-8')
    assert "package: name='com.daily.notes' versionCode='36200' versionName='D2.0.0'" in badging
    assert "application-label:'Daily Notes'" in badging
    assert 'StartupPreload' in manifest and 'notes' in manifest
    inspect('AndroidManifest.xml', manifest.splitlines())
    resources = subprocess.check_output([str(aapt), 'dump', 'resources', str(args.apk)], encoding='utf-8')
    inspect('resources.arsc', resources.splitlines())
    lock = json.loads((ROOT / 'inputs.lock.json').read_text('utf-8'))
    backend_record = json.loads((ROOT / 'manager-artifacts/branded-official-backend/BUILD_RECORD.json').read_text('utf-8'))
    fs_record = json.loads((ROOT / 'manager-artifacts/FSCTL_BUILD_RECORD.json').read_text('utf-8'))
    assert backend_record['source_commit'] == lock['kernelsu']['commit']
    assert fs_record['commit'] == lock['susfs']['commit']
    with zipfile.ZipFile(args.apk) as apk:
        names = apk.namelist()
        assert len(names) == len(set(names)), 'Duplicate APK entry'
        for name in names:
            assert not FORBIDDEN.search(name), name
            assert not name.endswith('/libadbroot.so'), name
            data = apk.read(name)
            if name.endswith('.dex'):
                inspect(name, dex_strings(data))
            elif name.endswith('.so'):
                assert name.startswith('lib/arm64-v8a/'), name
                assert data.startswith(b'\x7fELF') and struct.unpack_from('<H', data, 18)[0] == 183
                native[name] = hashlib.sha256(data).hexdigest()
                inspect(name, (s.decode('ascii') for s in re.findall(rb'[ -~]{5,}', data)))
            elif name.startswith('assets/'):
                inspect(name, (s.decode('utf-8', errors='replace') for s in re.findall(rb'[\x20-\x7e]{4,}', data)))
        assert native['lib/arm64-v8a/libnote_runtime.so'] == backend_record['backend_sha256']
        assert native['lib/arm64-v8a/libnote_filesystem.so'] == fs_record['sha256']
        for helper, digest in json.loads((ROOT / 'docs/D111-inputs.json').read_text('utf-8'))['packaged_helpers'].items():
            assert hashlib.sha256(apk.read(helper)).hexdigest() == digest, helper
    policy_path = ROOT / 'manager-support/apk-identity-exceptions.json'
    known = {}
    if policy_path.is_file():
        for item in json.loads(policy_path.read_text('utf-8'))['entries']:
            assert item['reason'].strip()
            known[(item['location'], item['sha256'])] = item
    unknown = [item for item in hits if (item['location'], item['sha256']) not in known]
    result = {'apk_sha256': hashlib.sha256(args.apk.read_bytes()).hexdigest(), 'bytes': args.apk.stat().st_size,
        'passed': not blocked and not unknown, 'blocked': blocked, 'unknown': unknown,
        'identity_inventory': hits, 'native_sha256': native,
        'manifest': manifest, 'badging': badging,
        'boundary': 'Static payload checks only; Android launch, JNI, root, Binder, PTY and module mounts need device validation.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'identity_entries': len(hits), 'unknown': len(unknown), 'blocked': len(blocked),
                      'native_libraries': len(native), 'passed': result['passed']}))
    assert not blocked, 'Forbidden legacy identity in APK; see audit report'
    if not args.inventory_only:
        assert not unknown, 'Unreviewed exact identity exceptions; see audit report'


if __name__ == '__main__':
    main()
