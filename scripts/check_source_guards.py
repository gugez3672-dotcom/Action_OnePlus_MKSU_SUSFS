"""Exercise source gates by injecting real regressions, always restoring bytes.

This is a source-only test. It never invokes a kernel build or contacts devices.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--fixture', type=Path, required=True)
    args = cli.parse_args()
    fixture = args.fixture.resolve()
    verifier = Path(__file__).with_name('verify_official_sources.py').resolve()
    ksu = 'kernel_workspace/kernel_platform/KernelSU/kernel/'
    common = 'kernel_workspace/kernel_platform/common/'
    cases = [
        ('unparenthesized compound SUS_MAP negation', common + 'fs/proc/task_mmu.c',
         '!(SUSFS_IS_INODE_SUS_MAP(file_inode(vma->vm_file)))',
         '!SUSFS_IS_INODE_SUS_MAP(file_inode(vma->vm_file))'),
        ('manager fd exposed', ksu + 'supercall/supercall.c',
         '    if (!manager_or_root())\n        return -EPERM;', '    if (0)\n        return -EPERM;'),
        ('unprivileged reboot task queued', ksu + 'supercall/supercall.c',
         '    /* Return to stock reboot validation without queueing work or exposing a fd. */\n'
         '    if (!manager_or_root())\n        return -EPERM;',
         '    if (0)\n        return -EPERM;'),
        ('reboot magic success leaks driver presence', ksu + 'supercall/supercall.c',
         '    /* Return to stock reboot validation without queueing work or exposing a fd. */\n'
         '    if (!manager_or_root())\n        return -EPERM;',
         '    if (!manager_or_root())\n        return 0;'),
        ('info permission reopened', ksu + 'supercall/dispatch.c',
         '.name = "GET_INFO",\n        .handler = do_get_info,\n        .perm_check = manager_or_root',
         '.name = "GET_INFO",\n        .handler = do_get_info,\n        .perm_check = always_allow'),
        ('SU session accidentally restricted', ksu + 'supercall/supercall.c',
         '    // This descriptor must be installed after the exec into ksud.',
         '    if (!manager_or_root()) return -EPERM;'),
        ('SUSFS source changed', common + 'fs/susfs.c', 'synchronize_rcu();', '/* removed RCU synchronization */'),
        ('public IKCONFIG leaked root delta', common + 'arch/arm64/configs/plk110_a67_stock_ikconfig',
         'CONFIG_IKCONFIG=y', 'CONFIG_IKCONFIG=n'),
        ('old fork Kconfig silently introduced', common + 'arch/arm64/configs/plk110_official.fragment',
         'CONFIG_KSU=y', 'CONFIG_KSU=y\nCONFIG_KSU_MULTI_MANAGER_SUPPORT=y'),
        ('SUS_MAP misplaced into smaps_rollup_open', common + 'fs/proc/task_mmu.c',
         'static int smaps_rollup_open(struct inode *inode, struct file *file)\n{',
         'static int smaps_rollup_open(struct inode *inode, struct file *file)\n{\n'
         '\tif (SUSFS_IS_INODE_SUS_MAP(file_inode(vma->vm_file))) return 0;'),
        ('SUS_MAP misplaced into pte_is_pinned', common + 'fs/proc/task_mmu.c',
         'static inline bool pte_is_pinned(struct vm_area_struct *vma, unsigned long addr, pte_t pte)\n{',
         'static inline bool pte_is_pinned(struct vm_area_struct *vma, unsigned long addr, pte_t pte)\n{\n'
         '\tif (SUSFS_IS_INODE_SUS_MAP(file_inode(vma->vm_file))) goto bypass_orig_flow;'),
        ('rollup path left unfiltered', common + 'fs/proc/task_mmu.c',
         '\t\tif (!vma->vm_file || !(SUSFS_IS_INODE_SUS_MAP(file_inode(vma->vm_file))))', '\t\tif (1)'),
        ('rollup cursor no longer advances', common + 'fs/proc/task_mmu.c',
         '\t\tlast_vma_end = vma->vm_end;', '\t\tif (0) last_vma_end = vma->vm_end;'),
    ]
    passed = []
    subprocess.run([sys.executable, str(verifier)], cwd=fixture, check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for label, relative, old, new in cases:
        target = fixture / relative
        original = target.read_bytes()
        text = original.decode()
        if old not in text:
            raise RuntimeError(f'test preimage drift: {label}')
        try:
            target.write_bytes(text.replace(old, new, 1).encode())
            result = subprocess.run([sys.executable, str(verifier)], cwd=fixture,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            if result.returncode == 0:
                raise RuntimeError(f'source gate missed regression: {label}')
            passed.append(label)
        finally:
            target.write_bytes(original)
    subprocess.run([sys.executable, str(verifier)], cwd=fixture, check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (fixture / 'artifacts/NEGATIVE_SOURCE_GUARDS.json').write_text(json.dumps({
        'passed': True, 'caught_regressions': passed, 'original_sources_restored': True,
        'compiled': False,
    }, indent=2) + '\n')
    print(f'PASS: all {len(passed)} injected regressions rejected; original sources restored.')


if __name__ == '__main__':
    main()
