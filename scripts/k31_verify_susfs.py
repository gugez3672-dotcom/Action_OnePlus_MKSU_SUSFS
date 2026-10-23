#!/usr/bin/env python3
"""Read-only SUSFS ABI/correctness assertions for K31 Android16-6.12.

Run after the 5f236a7b SUSFS patch and before any compilation. Missing
critical security/correctness markers cause a hard failure, never a fallback.
"""
from __future__ import annotations

from pathlib import Path
import re

ROOT = Path('kernel_workspace/kernel_platform/common')


def verify(root: Path) -> list[str]:
    h = (root / 'include/linux/susfs.h').read_text(encoding='utf-8')
    c = (root / 'fs/susfs.c').read_text(encoding='utf-8')
    ns = (root / 'fs/namespace.c').read_text(encoding='utf-8')
    statfs = (root / 'fs/statfs.c').read_text(encoding='utf-8')
    tests = {
        'KSTAT bit8 unique': r'#define\s+KSTAT_SPOOF_CTIME_TV_SEC\s+\(1\s*<<\s*8\)',
        'KSTAT is_statically bool': r'\bbool\s+is_statically\s*;',
    }
    for label, regex in tests.items():
        if not re.search(regex, h):
            raise RuntimeError(f'SUSFS {label} failed')
    # Prevent first-order KSTAT collision regressions (ino bit 0 vs ctime bit 8).
    if '(1 < 8)' in h:
        raise RuntimeError('SUS_KSTAT ctime typo still present')
    checks = [
        ('SUS_MOUNT clone state', ns, 'is_mnt_ksu_unshared = true;'),
        ('SUS_MOUNT per-clone flag', ns, 'if (unlikely(is_mnt_ksu_unshared))'),
        ('SUS_KSTAT statfs flags', statfs, 'buf->f_flags = calculate_f_flags(mnt);'),
        ('SUS_KSTAT statfs wrapper', statfs, 'statfs_by_dentry_wrapper('),
        ('SUS_KSTAT no kstat update leak', c, 'susfs_update_sus_kstat('),
    ]
    for label, haystack, needle in checks:
        if needle not in haystack:
            raise RuntimeError(f'SUSFS {label} absent')
    alloc = c.index('void susfs_get_enabled_features(')
    following = c[alloc:alloc+850]
    if not re.search(r'if\s*\(!info\)\s*\{.*?\breturn\s*;', following, re.S):
        raise RuntimeError('SUSFS allocation failure must return early')
    if re.search(r'if\s*\(!info\)\s*\{\s*info->err', following):
        raise RuntimeError('NULL dereference still present in SUSFS features')
    return [*tests, *(x[0] for x in checks), 'allocation-failure early return']


if __name__ == '__main__':
    for x in verify(ROOT):
        print('OK:', x)
