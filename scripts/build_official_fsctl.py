"""Build the exact 519 userspace tool, with only its display identity renamed."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    lock = json.loads((ROOT / 'inputs.lock.json').read_text())
    upstream = ROOT / '.inputs/susfs4ksu'
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=upstream, text=True).strip() == lock['susfs']['commit']
    source = ROOT / '.inputs/fsctl-source'
    if not source.exists():
        shutil.copytree(upstream / 'ksu_susfs/jni', source)
    tag = source / 'includes/susfs_defs.h'
    before = (upstream / 'ksu_susfs/jni/includes/susfs_defs.h').read_text()
    assert before.count('#define TAG "ksu_susfs"') == 1
    tag.write_text(before.replace('#define TAG "ksu_susfs"', '#define TAG "note_filesystem"'), encoding='utf-8', newline='\n')
    help_file = source / 'features/sus_mount.c'
    help_before = (upstream / 'ksu_susfs/jni/features/sus_mount.c').read_text()
    assert help_before.count('in KSU manager') == 1
    help_file.write_text(help_before.replace('in KSU manager', 'in the manager'), encoding='utf-8', newline='\n')
    ndk = Path(os.environ.get('ANDROID_HOME', ROOT / '.inputs/android-sdk')) / 'ndk/29.0.14206865/toolchains/llvm/prebuilt'
    llvm = ndk / ('windows-x86_64' if os.name == 'nt' else 'linux-x86_64')
    compiler = llvm / ('bin/clang.exe' if os.name == 'nt' else 'bin/clang')
    output = ROOT / 'manager/app/src/main/jniLibs/arm64-v8a/libnote_filesystem.so'
    sources = sorted(source.glob('*.c')) + sorted((source / 'features').glob('*.c'))
    subprocess.run([str(compiler), '--target=aarch64-linux-android26', '-O3', '-fPIE', '-pie',
        '-fstack-protector-strong', '-D_FORTIFY_SOURCE=2', '-flto=thin', '-ffunction-sections',
        '-fdata-sections', '-fvisibility=hidden', '-Wl,--gc-sections', '-Wl,-z,max-page-size=16384', '-Wl,-s',
        f'-ffile-prefix-map={source.as_posix()}=notes/filesystem', '-I', str(source / 'includes'),
        *map(str, sources), '-o', str(output)], check=True)
    data = output.read_bytes()
    assert b'ksu_susfs' not in data
    report = {'commit': lock['susfs']['commit'], 'sha256': hashlib.sha256(data).hexdigest(),
        'bytes': len(data), 'adaptation': 'Display TAG and one help-text manager reference renamed; official syscall constants and command implementations unchanged.',
        'source_sha256': {p.relative_to(source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(source.rglob('*')) if p.is_file()}}
    out = ROOT / 'manager-artifacts'
    out.mkdir(exist_ok=True)
    (out / 'FSCTL_BUILD_RECORD.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('Official 519 arm64 userspace tool built; display tag cleaned and source hashes recorded.')


if __name__ == '__main__':
    main()
