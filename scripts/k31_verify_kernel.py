#!/usr/bin/env python3
"""K31 static invariants: do not confuse source checks with a compiled build."""
from __future__ import annotations

from pathlib import Path
import re

KP = Path('kernel_workspace/kernel_platform')


def verify(kp: Path) -> list[str]:
    kernel = kp / 'KernelSU/kernel'
    common = kp / 'common'
    kbuild = (kernel / 'Kbuild').read_text()
    manager = (kernel / 'manager/apk_sign.c').read_text()
    supercall = (kernel / 'supercall/supercall.c').read_text()
    dispatch = (kernel / 'supercall/dispatch.c').read_text()
    hooks = (common / 'security/selinux/hooks.c').read_text()
    sel = (kernel / 'feature/selinux_hide.c').read_text()
    pkg = (kernel / 'manager/pkg_observer.c').read_text()
    pguard = (common / 'block/plk110_partition_guard.c').read_text()
    errors = []
    def need(condition: bool, label: str) -> None:
        if not condition:
            errors.append(label)
    need('KSU_MANAGER_PACKAGE := com.daily.notes' in kbuild, 'strict manager package')
    need('7b6fcd9e7f440833ee8a5a3860f3ff5b7b367a0dabb36c1d5f0fd52064bf283e' in manager,
         'frozen manager signer')
    need('ksu_is_dynamic_manager_enabled()' not in manager, 'dynamic manager should remain disabled')
    need('!is_manager()' in supercall, 'foreign-app fd installation restriction')
    for cmd in ['GET_INFO', 'GET_INFO_LEGACY', 'CHECK_SAFEMODE', 'GET_FULL_VERSION']:
        m = re.search(r'\.cmd\s*=\s*KSU_IOCTL_'+cmd+r'\s*,(?P<body>.*?)(?=\n\s*\},)', dispatch, re.S)
        need(bool(m and '.perm_check = manager_or_root' in m.group('body')), 'restricted '+cmd)
    need('ksu_security_context_to_sid_with_policy_ex' in hooks and
         'ksu_security_context_to_sid_with_policy_ex' in sel, '#3877 dual SID contract')
    need('policydb_context_isvalid(orig_pol, orig_ctx)' in sel,
         'K30 #3877 original-policy validity correctness')
    need('task_work_add(current, cb, TWA_RESUME)' in pkg,
         'K30 #3871 task-work deferral')
    need('PLK110_PGUARD_GPT_SECTORS' in pguard, 'PGuard GPT bounds')
    need('{ "init_boot_a", PLK110_PG_HARD }' in pguard, 'PGuard init_boot')
    need('{ "vendor_boot_a", PLK110_PG_HARD }' in pguard, 'PGuard vendor_boot')
    need(not re.search(r'\{ "boot(?:_a|_b)?", PLK110_PG_HARD \}', pguard),
         'PGuard boot exempt as K30')
    if errors:
        raise RuntimeError('K31 preflight contract failed: '+ '; '.join(errors))
    return ['fixed manager and signer', 'reboot supercall gate',
            'restricted info ioctls', '#3877 live/backup policy bridge',
            '#3871 deferred observer', 'PGuard partition and boot contract']

if __name__ == '__main__':
    for label in verify(KP):
        print('OK:', label)
