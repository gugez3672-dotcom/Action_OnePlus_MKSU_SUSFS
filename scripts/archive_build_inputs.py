"""Archive every pinned kernel build input so a build can be replayed offline.

Usage: python scripts/archive_build_inputs.py <SOURCE_MANIFEST.xml> <output dir>

Reads inputs.lock.json and the SOURCE_MANIFEST.xml a successful build exported.
Each git input becomes a bare repository holding exactly the pinned commit under
refs/heads/pinned; downloads are kept with their SHA256. Re-running resumes:
finished entries are verified and skipped. INDEX.json lists what was archived.
"""
import hashlib
import json
import subprocess
import tarfile
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = json.loads((ROOT / 'inputs.lock.json').read_text(encoding='utf-8'))

# Pinned outside the lock: the workflow names them directly.
ANYKERNEL_URL = 'https://github.com/Numbersf/AnyKernel3.git'
MANIFEST_URL = 'https://github.com/OnePlusOSS/kernel_manifest.git'
REPO_LAUNCHER_URL = 'https://gerrit.googlesource.com/git-repo/+/refs/tags/v2.68.1/repo?format=TEXT'
CLANG_URL = ('https://android.googlesource.com/platform/prebuilts/clang/host/linux-x86/+archive/'
             '{commit}/clang-r536225.tar.gz')
# googlesource +archive tarballs are generated per request and not byte-stable;
# the payload is identified by the pinned commit and the clang version string.
CLANG_SHA256 = None
ACTIONS = {
    'easimon/maximize-build-space': 'c28619d8999a147d5e09c1199f84ff6af6ad5794',
    'actions/checkout': '11d5960a326750d5838078e36cf38b85af677262',
    'actions/upload-artifact': 'ea165f8d65b6e75b540449e92b4886f43607fa02',
}


def git(*args, cwd=None):
    return subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def archive_git(url, commit, dest, full_history=False):
    dest = Path(dest)
    if dest.is_dir():
        try:
            if git('rev-parse', 'refs/heads/pinned', cwd=dest) == commit:
                return 'kept'
        except subprocess.CalledProcessError:
            pass
    dest.mkdir(parents=True, exist_ok=True)
    git('init', '-q', '--bare', str(dest))
    depth = [] if full_history else ['--depth=1']
    git('fetch', '-q', *depth, '--no-tags', url, commit, cwd=dest)
    fetched = git('rev-parse', 'FETCH_HEAD', cwd=dest)
    if fetched != commit:
        raise RuntimeError(f'{url}: fetched {fetched}, expected {commit}')
    git('update-ref', 'refs/heads/pinned', commit, cwd=dest)
    git('symbolic-ref', 'HEAD', 'refs/heads/pinned', cwd=dest)
    return 'fetched'


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def download(url, dest, expected=None, transform=None):
    dest = Path(dest)
    if dest.is_file() and (expected is None or sha256(dest) == expected):
        return 'kept', sha256(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + '.part')
    with urllib.request.urlopen(url, timeout=120) as response, open(tmp, 'wb') as out:
        for block in iter(lambda: response.read(1 << 20), b''):
            out.write(block)
    if transform:
        tmp.write_bytes(transform(tmp.read_bytes()))
    actual = sha256(tmp)
    if expected and actual != expected:
        tmp.unlink()
        raise RuntimeError(f'{url}: sha256 {actual}, expected {expected}')
    tmp.replace(dest)
    return 'fetched', actual


def main():
    manifest_path, out = Path(sys.argv[1]), Path(sys.argv[2])
    manifest = ET.parse(manifest_path).getroot()
    remotes = {r.get('name'): r.get('fetch').rstrip('/') for r in manifest.findall('remote')}
    default_remote = manifest.find('default').get('remote')
    index = {'lock': LOCK, 'source_manifest_sha256': sha256(manifest_path), 'git': {}, 'files': {}}
    (out / 'SOURCE_MANIFEST.xml').parent.mkdir(parents=True, exist_ok=True)
    (out / 'SOURCE_MANIFEST.xml').write_bytes(manifest_path.read_bytes())
    (out / 'inputs.lock.json').write_bytes((ROOT / 'inputs.lock.json').read_bytes())

    jobs = [('kernel_manifest', MANIFEST_URL, LOCK['oneplus_manifest'], False),
            ('KernelSU', LOCK['kernelsu']['repository'], LOCK['kernelsu']['commit'], True),
            ('susfs4ksu', LOCK['susfs']['repository'], LOCK['susfs']['commit'], False),
            ('AnyKernel3', ANYKERNEL_URL, LOCK['anykernel'], False)]
    for project in manifest.findall('project'):
        name = project.get('name')
        url = f"{remotes[project.get('remote') or default_remote]}/{name}"
        jobs.append((f'oneplus/{name}', url, project.get('revision'), False))
    for name, sha in ACTIONS.items():
        jobs.append((f'actions/{name}', f'https://github.com/{name}.git', sha, False))

    for key, url, commit, full in jobs:
        print(f'[git] {key} {commit[:12]} ...', flush=True)
        state = archive_git(url, commit, out / 'git' / f'{key}.git', full)
        index['git'][key] = {'url': url, 'commit': commit, 'state': state}
        print(f'      {state}', flush=True)

    import base64
    files = [('repo', REPO_LAUNCHER_URL, LOCK['repo_launcher_sha256'], base64.b64decode),
             ('clang-r536225.tar.gz', CLANG_URL.format(commit=LOCK['clang_prebuilt']), CLANG_SHA256, None)]
    for name, url, expected, transform in files:
        print(f'[file] {name} ...', flush=True)
        state, digest = download(url, out / 'files' / name, expected, transform)
        index['files'][name] = {'url': url, 'sha256': digest, 'state': state}
        print(f'      {state} {digest[:16]}', flush=True)

    with tarfile.open(out / 'files' / 'clang-r536225.tar.gz') as tar:
        names = {n.lstrip('./'): n for n in tar.getnames()}
        version = tar.extractfile(names['AndroidVersion.txt']).read().decode().split()[0]
        binary = tar.extractfile(names['bin/clang-19']).read()
    for marker in (LOCK['llvm_commit'], LOCK['clang_android_build']):
        if marker.encode() not in binary:
            raise RuntimeError(f'clang payload mismatch: {marker} not in bin/clang-19')
    index['files']['clang-r536225.tar.gz'].update(
        clang_version=version, llvm_commit=LOCK['llvm_commit'], android_build=LOCK['clang_android_build'])
    (out / 'INDEX.json').write_text(json.dumps(index, indent=2) + '\n', encoding='utf-8')
    print(f"Archived {len(index['git'])} git inputs and {len(index['files'])} files to {out}")


if __name__ == '__main__':
    main()
