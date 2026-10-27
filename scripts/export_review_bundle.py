"""Export uncommitted code and actual source-check evidence for human review."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def git(*args):
    return subprocess.check_output(['git', *args])


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--fixture', type=Path, required=True)
    args = cli.parse_args()
    out = Path('review')
    out.mkdir(exist_ok=True)
    evidence = args.fixture / 'artifacts'
    copied = []
    for name in ('LOCAL_OFFICIAL_OVERLAY.patch', 'OFFICIAL_COMMON_PATCH.log', 'OFFICIAL_KSU_PATCH.log',
                 'OFFICIAL_10_KSU.patch', 'OFFICIAL_50_COMMON.patch',
                 'OFFICIAL_50_STRICT_SUBSET.patch', 'A67_SUSFS_519_COMPAT.patch',
                 'OFFICIAL_SUSFS_INTEGRATION.json', 'OFFICIAL_KERNEL_PREPARATION.json',
                 'SOURCE_INVARIANTS.json', 'SOURCE_STATE.json', 'NEGATIVE_SOURCE_GUARDS.json',
                 'MANAGER_CERTIFICATE_GATE.json', 'REVIEW_SOURCE_DOWNLOADS.json',
                 'CLAUDE_B1_REGRESSION.json', 'VERIFIED_STOCK_RUN_CHECK.json',
                 'STATIC_UNIT_TESTS.log',
                 'COMMON_BUILD_ADAPTATIONS.patch', 'KERNELSU_EFFECTIVE.patch', 'KLEAF_STAMP_ADAPTATION.patch'):
        shutil.copyfile(evidence / name, out / name)
        copied.append(name)
    tracked = {entry.decode() for entry in git('ls-files', '-z').split(b'\0') if entry}
    others = {entry.decode() for entry in git('ls-files', '--others', '--exclude-standard', '-z').split(b'\0') if entry}
    changes = []
    files = {}
    for relative in sorted(tracked | others):
        if relative.startswith('review/'):
            continue
        path = Path(relative)
        before = git('show', 'HEAD:' + relative) if relative in tracked else b''
        after = path.read_bytes() if path.is_file() else b''
        if after:
            files[relative] = hashlib.sha256(after).hexdigest()
        if before == after:
            continue
        if b'\0' in before or b'\0' in after:
            raise RuntimeError(f'binary file requires explicit review export: {relative}')
        changes.append(f'diff --git a/{relative} b/{relative}\n')
        changes.extend(difflib.unified_diff(before.decode().splitlines(keepends=True),
            after.decode().splitlines(keepends=True),
            fromfile='a/' + relative if relative in tracked else '/dev/null',
            tofile='b/' + relative if path.is_file() else '/dev/null'))
    (out / 'BUILD_DEFINITION_CHANGESET.patch').write_text(''.join(changes), encoding='utf-8', newline='\n')
    (out / 'CODE_SHA256.json').write_text(json.dumps({
        'base_commit': git('rev-parse', 'HEAD').decode().strip(),
        'branch': git('branch', '--show-current').decode().strip(),
        'code_sha256': files, 'source_evidence': copied,
        'committed': False, 'pushed': False, 'compiled': False, 'device_connected': False,
    }, indent=2, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    print(f'Exported complete review changeset, {len(files)} code fingerprints and {len(copied)} evidence files.')


if __name__ == '__main__':
    main()
