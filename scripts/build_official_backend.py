"""Compile the pinned official backend independently of every old DN binary."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = ROOT / '.inputs/BackendSource'
    lock = json.loads((ROOT / 'inputs.lock.json').read_text())
    actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
    assert actual == lock['kernelsu']['commit']
    patch = subprocess.check_output(['git', 'diff', '--binary'], cwd=source)
    branded = bool(patch)
    if branded:
        policy = json.loads((ROOT / 'manager-support/backend-literal-policy.json').read_text('utf-8'))
        assert hashlib.sha256(patch).hexdigest() == policy['patch_sha256'], 'unreviewed backend source changes'
        assert patch == (ROOT / 'manager-support/official-backend-branding.patch').read_bytes()
    assets = source / 'userspace/ksud/bin/aarch64'
    asset_hashes = {}
    assert {p.name for p in assets.iterdir() if p.is_file()} == {'bootctl', 'busybox', 'waitsys'}
    for asset in assets.iterdir():
        if not asset.is_file():
            continue
        upstream = subprocess.check_output(['git', 'show', 'HEAD:' + asset.relative_to(source).as_posix()], cwd=source)
        assert asset.read_bytes() == upstream, f'Changed official binary asset: {asset.name}'
        asset_hashes[asset.name] = hashlib.sha256(upstream).hexdigest()
    sdk = Path(os.environ.get('ANDROID_HOME', ROOT / '.inputs/android-sdk'))
    ndk = sdk / 'ndk/29.0.14206865'
    windows = os.name == 'nt'
    suffix = '.exe' if windows else ''
    llvm = ndk / 'toolchains/llvm/prebuilt' / ('windows-x86_64' if windows else 'linux-x86_64')
    cargo = Path('D:/CodexTools/rust/cargo/bin/cargo.exe') if windows else Path(shutil.which('cargo'))
    env = os.environ.copy()
    remaps = [(str(source), 'notes/source'), ('userspace/ksud', 'notes/runtime'),
              (r'userspace\ksud', 'notes/runtime'), ('userspace/ksuinit', 'notes/startup'),
              (r'userspace\ksuinit', 'notes/startup')]
    for checkout in (ROOT / '.inputs/cargo-home/git/checkouts').glob('ksu_props-*/*'):
        if checkout.is_dir():
            remaps.append((str(checkout), 'notes/properties'))
    # Cover both spellings: rustc on Windows emits relative backslash panic locations.
    remap_flags = ' '.join(f'--remap-path-prefix={before}={after}' for before, after in remaps)
    env.update(
        CARGO_HOME=str(ROOT / '.inputs/cargo-home'),
        CARGO_TARGET_DIR=str(ROOT / '.inputs/backend-target'),
        ANDROID_NDK_HOME=str(ndk), CARGO_NET_GIT_FETCH_WITH_CLI='true',
        LIBCLANG_PATH=str(llvm / 'bin') if windows else '/usr/lib/llvm-18/lib',
        CARGO_TARGET_AARCH64_LINUX_ANDROID_LINKER=str(llvm / ('bin/clang' + suffix)),
        CARGO_TARGET_AARCH64_LINUX_ANDROID_RUSTFLAGS=(
            '-Clink-arg=--target=aarch64-linux-android26 -Clink-arg=-Wl,-z,max-page-size=16384 '
            f'--remap-path-prefix={(source / "userspace/ksud").as_posix()}=notes/runtime '
            f'--remap-path-prefix={(source / "userspace/ksuinit").as_posix()}=notes/startup '
            f'--remap-path-prefix={(ROOT / ".inputs/cargo-home").as_posix()}=notes/dependencies {remap_flags}'),
        CC_aarch64_linux_android=str(llvm / ('bin/clang' + suffix)),
        CXX_aarch64_linux_android=str(llvm / ('bin/clang++' + suffix)),
        AR_aarch64_linux_android=str(llvm / ('bin/llvm-ar' + suffix)),
        CFLAGS_aarch64_linux_android='--target=aarch64-linux-android26',
        CXXFLAGS_aarch64_linux_android='--target=aarch64-linux-android26',
        BINDGEN_EXTRA_CLANG_ARGS_aarch64_linux_android=f'--target=aarch64-linux-android26 --sysroot={(llvm / "sysroot").as_posix()}',
        KSU_PACKAGE_NAME=lock['manager']['package'],
    )
    paths = [str(cargo.parent), str(llvm / 'bin')]
    if windows:
        host = next(Path('D:/CodexTools/llvm-mingw').glob('llvm-mingw-*/bin'))
        env.update(RUSTUP_HOME='D:/CodexTools/rust/runtime',
            CARGO_TARGET_X86_64_PC_WINDOWS_GNU_LINKER=str(host / 'x86_64-w64-mingw32-clang.exe'),
            CC_x86_64_pc_windows_gnu=str(host / 'x86_64-w64-mingw32-clang.exe'),
            AR_x86_64_pc_windows_gnu=str(host / 'llvm-ar.exe'))
        paths.insert(1, str(host))
    env['PATH'] = os.pathsep.join(paths + [env['PATH']])
    # A clean runner has no git dependency checkout when remaps are first assembled.
    # Fetch before collecting any newly created property-crate paths, otherwise panic
    # locations leak that upstream checkout name on Linux only.
    subprocess.run([str(cargo), 'fetch', '--locked', '--target', 'aarch64-linux-android',
        '--manifest-path', 'userspace/ksud/Cargo.toml'], cwd=source, env=env, check=True)
    for checkout in (ROOT / '.inputs/cargo-home/git/checkouts').glob('ksu_props-*/*'):
        remap = (str(checkout), 'notes/properties')
        if checkout.is_dir() and remap not in remaps:
            env['CARGO_TARGET_AARCH64_LINUX_ANDROID_RUSTFLAGS'] += f' --remap-path-prefix={remap[0]}={remap[1]}'
    subprocess.run([str(cargo), 'build', '--release', '--locked', '--target', 'aarch64-linux-android',
        '--manifest-path', 'userspace/ksud/Cargo.toml'], cwd=source, env=env, check=True)
    binary = ROOT / '.inputs/backend-target/aarch64-linux-android/release' / ('note_runtime' if branded else 'ksud')
    raw = binary.read_bytes()
    out = ROOT / 'manager-artifacts' / ('branded-official-backend' if branded else 'raw-official-backend')
    out.mkdir(parents=True, exist_ok=True)
    payload = out / 'libnote_runtime.so'
    shutil.copyfile(binary, payload)
    subprocess.run([str(llvm / ('bin/llvm-strip' + suffix)), '--strip-all', str(payload)], check=True)
    data = payload.read_bytes()
    assert data.startswith(b'\x7fELF') and int.from_bytes(data[18:20], 'little') == 183
    (out / 'BUILD_RECORD.json').write_text(json.dumps({
        'stage': 'Branded official build; release audit still required.' if branded else 'Raw official build; static cleanup and release audit still required.',
        'source_commit': actual, 'package': env['KSU_PACKAGE_NAME'],
        'cargo_lock_sha256': hashlib.sha256((source / 'Cargo.lock').read_bytes()).hexdigest(),
        'backend_sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
        'unstripped_sha256': hashlib.sha256(raw).hexdigest(),
        'strip': 'NDK llvm-strip --strip-all; dynamic symbols and runtime interfaces retained',
        'old_backend_imported': False,
        'official_embedded_assets_sha256': asset_hashes,
        'rustc': subprocess.check_output([str(cargo.parent / ('rustc.exe' if windows else 'rustc')), '--version'], env=env, text=True).strip(),
        'target': 'aarch64-linux-android', 'ndk': '29.0.14206865',
        'branding_patch_sha256': hashlib.sha256(patch).hexdigest() if branded else None,
    }, indent=2) + '\n', encoding='utf-8')
    print('Fresh official arm64 backend built; recorded separately from release payloads.')


if __name__ == '__main__':
    main()
