"""Record adapted build inputs, then prove they stayed unchanged across build targets."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])


def digest(path):
    if path.is_symlink():
        return hashlib.sha256(('symlink:' + os.readlink(path)).encode()).hexdigest()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('phase', choices=('record', 'verify'))
    cli.add_argument('--review-fixture', action='store_true', help='No SCM stamping in an indexed, uncommitted source subset')
    args = cli.parse_args()
    workspace = Path('kernel_workspace')
    out = Path('artifacts')
    record_path = out / 'SOURCE_STATE.json'
    if args.phase == 'record':
        common = workspace / 'kernel_platform/common'
        ksu = workspace / 'kernel_platform/KernelSU'
        report = json.loads((out / 'OFFICIAL_SUSFS_INTEGRATION.json').read_text())
        paths = {Path('inputs.lock.json'), Path('baselines/PLK110_A67_official.config.additions'),
                 Path('baselines/PLK110_A67_stock.banner')}
        common_changed = git(common, 'diff', '--name-only', '-z').decode().split('\0')
        common_extra = set(report['copied_sources']) | {
            'arch/arm64/configs/plk110_official.fragment',
            'arch/arm64/configs/plk110_stock.fragment',
            'arch/arm64/configs/plk110_a67_stock_ikconfig', 'certs/plk110_stock.pem',
            'drivers/kernelsu',
        }
        paths.update(common / rel for rel in common_changed if rel)
        paths.update(common / rel for rel in common_extra)
        # All tracked KSU kernel files, including unchanged headers consumed by
        # the official preinit runner, are part of the frozen build input.
        paths.update(ksu / rel for rel in git(ksu, 'ls-files', 'kernel', 'uapi').decode().splitlines())
        paths.add(workspace / 'kernel_platform/build/kernel/kleaf/impl/stamp.bzl')
        hashes = {str(path).replace('\\', '/'): digest(path)
                  for path in sorted(paths)}
        if args.review_fixture and not (out / 'REVIEW_SOURCE_DOWNLOADS.json').is_file():
            raise RuntimeError('--review-fixture requires the explicit source-subset manifest')
        record_path.write_text(json.dumps({'sha256': hashes, 'review_fixture': args.review_fixture}, indent=2) + '\n')
        (out / 'COMMON_BUILD_ADAPTATIONS.patch').write_bytes(git(common, 'diff', '--binary'))
        (out / 'KERNELSU_EFFECTIVE.patch').write_bytes(git(ksu, 'diff', '--binary'))
        (out / 'KLEAF_STAMP_ADAPTATION.patch').write_bytes(
            git(workspace, 'diff', '--', 'kernel_platform/build/kernel/kleaf/impl/stamp.bzl'))
        # K32's stock SCM stamping requires tracked common adaptations to be
        # hidden from setlocalversion. Export them FIRST, and verify their bytes
        # after both build targets; do not discard or silently skip any changes.
        changed = [rel for rel in common_changed if rel]
        if changed and not args.review_fixture:
            git(common, 'update-index', '--assume-unchanged', '--', *changed)
        if not args.review_fixture and git(common, 'status', '-uno', '--porcelain').strip():
            raise RuntimeError('common tracked worktree remains dirty for SCM stamping')
        print(f'Recorded {len(hashes)} adapted source hashes before build.')
    else:
        recorded = json.loads(record_path.read_text())['sha256']
        bad = [rel for rel, expected in recorded.items()
               if not Path(rel).exists() or digest(Path(rel)) != expected]
        if bad:
            raise RuntimeError(f'source inputs changed after preflight: {bad[:10]}')
        print(f'PASS: all {len(recorded)} source hashes unchanged.')


if __name__ == '__main__':
    main()
