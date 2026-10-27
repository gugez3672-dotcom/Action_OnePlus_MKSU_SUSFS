"""Integrate official SUSFS using strict contexts and a separate A67 adaptation.

Six incompatible common hunks are replaced by the reviewed A67 source patch.
All other official content is retained verbatim. No fuzzy patching is accepted.
Logs, original/applied patch bytes and hashes are exported for review.
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from susfs_patch_policy import strict_official_patch, reject_fuzzy_log


def command(args, *, cwd=None, data=None):
    result = subprocess.run(args, cwd=cwd, input=data, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    output = result.stdout.decode('utf-8', errors='replace')
    if result.returncode:
        raise RuntimeError(f'{args[0]} failed ({result.returncode}):\n{output[-6000:]}')
    return output


def main():
    lock = json.loads(Path('inputs.lock.json').read_text())
    workspace = Path('kernel_workspace')
    ksu = workspace / 'kernel_platform/KernelSU'
    common = workspace / 'kernel_platform/common'
    susfs = workspace / 'susfs4ksu'
    out = Path('artifacts')
    out.mkdir(exist_ok=True)
    for source, expected in ((ksu, lock['kernelsu']['commit']), (susfs, lock['susfs']['commit'])):
        actual = command(['git', 'rev-parse', 'HEAD'], cwd=source).strip()
        if actual != expected:
            raise RuntimeError(f'{source}: wrong commit {actual}')
        command(['git', 'diff', '--exit-code'], cwd=source)
    if command(['git', 'rev-parse', '--is-shallow-repository'], cwd=ksu).strip() != 'false':
        raise RuntimeError('KernelSU full history is required for the official numeric version')
    count = int(command(['git', 'rev-list', '--count', 'HEAD'], cwd=ksu))
    if count != lock['kernelsu']['git_count']:
        raise RuntimeError(f'KernelSU version count drift: {count}')

    ksu_patch = (susfs / 'kernel_patches/KernelSU/10_enable_susfs_for_ksu.patch').read_bytes()
    common_patch = (susfs / 'kernel_patches/50_add_susfs_in_gki-android16-6.12.patch').read_bytes()
    ksu_log = command(['git', 'apply', '--check', '--whitespace=nowarn', '-'], cwd=ksu, data=ksu_patch)
    ksu_log += command(['git', 'apply', '--whitespace=nowarn', '-'], cwd=ksu, data=ksu_patch)
    (out / 'OFFICIAL_KSU_PATCH.log').write_text(ksu_log or 'git apply --check and apply: PASS\n')

    strict_patch, replacements = strict_official_patch(common_patch)
    compat_path = Path(__file__).resolve().parents[1] / 'patches/PLK110_A67_SUSFS_519_compat.patch'
    compat_patch = compat_path.read_bytes()
    common_log = ''
    for name, data in (('Retained official hunks', strict_patch), ('A67 compatibility hunks', compat_patch)):
        common_log += name + ': strict git apply (no fuzz)\n'
        common_log += command(['git', 'apply', '--check', '--verbose', '--whitespace=nowarn', '-'], cwd=common, data=data)
        common_log += command(['git', 'apply', '--verbose', '--whitespace=nowarn', '-'], cwd=common, data=data)
    reject_fuzzy_log(common_log)
    (out / 'OFFICIAL_COMMON_PATCH.log').write_text(common_log)
    rejected = [str(path) for path in common.rglob('*.rej')]
    if rejected:
        raise RuntimeError(f'patch rejects exist: {rejected[:10]}')

    hashes = {}
    for directory in ('fs', 'include/linux'):
        for source in sorted((susfs / 'kernel_patches' / directory).iterdir()):
            if source.is_file():
                target = common / directory / source.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                hashes[str(target.relative_to(common))] = hashlib.sha256(source.read_bytes()).hexdigest()

    # Upstream whitespace only: Kconfig space-tab, SELinux blank lines, dispatch.
    # Read/write with LF also avoids Windows checkout line-ending artifacts.
    whitespace = []
    for source in (ksu / 'kernel/Kconfig', ksu / 'kernel/selinux/selinux.c',
                   ksu / 'kernel/supercall/dispatch.c'):
        original = source.read_text()
        fixed = '\n'.join(line.rstrip() for line in original.splitlines()) + '\n'
        if source.name == 'Kconfig':
            fixed = fixed.replace('\t  \tjust disable', '\t  just disable')
        if fixed != original:
            source.write_text(fixed, encoding='utf-8', newline='\n')
            whitespace.append(str(source.relative_to(ksu)))
    stat = common / 'fs/stat.c'
    lines = stat.read_text().splitlines()
    for index, line in enumerate(lines):
        if 'query_flags | AT_GETATTR_NOSEC);' in line and index and 'request_mask,' in lines[index-1]:
            lines[index] = '\t\t\t\t\t\tquery_flags | AT_GETATTR_NOSEC);'
    stat.write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    memory = common / 'mm/memory.c'
    memory.write_text('\n'.join(line.rstrip() for line in memory.read_text().splitlines()) + '\n',
                      encoding='utf-8', newline='\n')
    for repo in (ksu, common):
        command(['git', 'diff', '--check'], cwd=repo)

    (out / 'OFFICIAL_10_KSU.patch').write_bytes(ksu_patch)
    (out / 'OFFICIAL_50_COMMON.patch').write_bytes(common_patch)
    (out / 'OFFICIAL_50_STRICT_SUBSET.patch').write_bytes(strict_patch)
    (out / 'A67_SUSFS_519_COMPAT.patch').write_bytes(compat_patch)
    report = {
        'kernelsu': lock['kernelsu'], 'susfs': lock['susfs'],
        'ksu_patch_sha256': hashlib.sha256(ksu_patch).hexdigest(),
        'common_patch_sha256': hashlib.sha256(common_patch).hexdigest(),
        'strict_official_subset_sha256': hashlib.sha256(strict_patch).hexdigest(),
        'a67_compatibility_patch_sha256': hashlib.sha256(compat_patch).hexdigest(),
        'a67_replaced_official_hunks': replacements,
        'copied_sources': hashes, 'ksu_whitespace_only_normalization': whitespace,
        'common_whitespace_only_normalization': ['fs/stat.c', 'mm/memory.c'],
        'ksu_patch_check': 'PASS', 'common_patch_dry_run_and_apply': 'PASS',
        'common_patch_max_fuzz': 0, 'patch_engine': 'strict git apply', 'rejected_hunks': 0,
        'compiled': False, 'device_tested': False,
    }
    (out / 'OFFICIAL_SUSFS_INTEGRATION.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Official KSU + retained common + explicit A67 compatibility patches applied with no fuzz/rejects.')


if __name__ == '__main__':
    main()
