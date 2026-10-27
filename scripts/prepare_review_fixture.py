"""Download only the exact OnePlus files needed for source/patch review.

Creates an isolated fixture, never invokes a compiler, never changes a phone.
The KernelSU/SUSFS clones are local cached inputs. Existing output is refused.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
import urllib.request


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--output', type=Path, required=True)
    args = cli.parse_args()
    root = Path.cwd().resolve()
    output = args.output.resolve()
    if not output.is_relative_to(root / '.inputs') or output.exists():
        raise SystemExit('output must be a new directory inside this project .inputs/')
    lock = json.loads((root / 'inputs.lock.json').read_text())
    output.mkdir(parents=True)
    (output / 'artifacts').mkdir()
    shutil.copyfile(root / 'inputs.lock.json', output / 'inputs.lock.json')
    shutil.copytree(root / 'baselines', output / 'baselines')
    workspace = output / 'kernel_workspace'
    for name, relative in (('KernelSU', 'kernel_platform/KernelSU'), ('susfs4ksu', 'susfs4ksu')):
        subprocess.run(['git', 'clone', '--no-hardlinks', '--config', 'core.autocrlf=false',
                        str(root / '.inputs' / name), str(workspace / relative)], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    patch = (workspace / 'susfs4ksu/kernel_patches/50_add_susfs_in_gki-android16-6.12.patch').read_text()
    common_files = set(re.findall(r'^diff --git a/(\S+) b/\S+$', patch, re.M))
    common_files.update(('BUILD.bazel', 'drivers/Makefile', 'drivers/Kconfig', 'kernel/Makefile',
                         'scripts/Makefile.vmlinux', 'arch/arm64/configs/gki_defconfig', 'build.config.gki'))
    common = workspace / 'kernel_platform/common'
    (common / 'certs').mkdir(parents=True)
    (common / 'include/linux').mkdir(parents=True)
    stamp = 'kernel_platform/build/kernel/kleaf/impl/stamp.bzl'
    jobs = [('android_kernel_common_oneplus_sm8850', lock['oneplus_common'], rel, common / rel)
            for rel in sorted(common_files)]
    jobs.append(('android_kernel_modules_and_devicetree_oneplus_sm8850', lock['oneplus_modules'],
                 stamp, workspace / stamp))

    def download(job):
        repo, commit, relative, target = job
        url = f'https://raw.githubusercontent.com/OnePlusOSS/{repo}/{commit}/{relative}'
        for attempt in range(3):
            try:
                with urllib.request.urlopen(url, timeout=45) as response:
                    data = response.read()
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return {'url': url, 'path': str(target.relative_to(output)),
                'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}

    with ThreadPoolExecutor(max_workers=5) as pool:
        records = list(pool.map(download, jobs))
    # Index only explicit downloaded files, so git diff can check the adaptation.
    # No commit is created and no existing worktree/index is touched.
    for repo, paths in ((common, sorted(common_files)), (workspace, [stamp])):
        subprocess.run(['git', 'init', str(repo)], check=True, stdout=subprocess.PIPE)
        subprocess.run(['git', '-C', str(repo), 'config', 'core.autocrlf', 'false'], check=True)
        subprocess.run(['git', '-C', str(repo), 'add', '--', *paths], check=True)
    (output / 'artifacts/REVIEW_SOURCE_DOWNLOADS.json').write_text(json.dumps({
        'scope': 'Exact pinned source-file subset, not a complete build tree.',
        'compiled': False, 'files': records,
    }, indent=2) + '\n')
    print(f'Prepared {len(records)} exact source files in {output}; no compilation.')


if __name__ == '__main__':
    main()
