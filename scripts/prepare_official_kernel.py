"""Hermetic official metadata, official manager parameters, and K32 access gates.

Does not alter the APK signature parser, protocol layouts, SU-session creation,
or official KSU feature defaults. No PGuard and no embedded K/run identifier.
"""
import hashlib
import difflib
import json
from pathlib import Path


def once(text, old, new, label):
    if text.count(old) != 1 or new in text:
        raise RuntimeError(f'{label}: expected exactly one unmodified preimage')
    return text.replace(old, new, 1)


def harden_supercall(text):
    text = once(text,
        'int ksu_install_fd(void)\n{\n    return ksu_install_fd_with_permissions(O_CLOEXEC, 0);\n}',
        'int ksu_install_fd(void)\n{\n'
        '    /* Keep manager descriptors private; SU-session descriptors use their own path. */\n'
        '    if (!manager_or_root())\n        return -EPERM;\n'
        '    return ksu_install_fd_with_permissions(O_CLOEXEC, 0);\n}', 'manager fd')
    text = once(text,
        'int ksu_supercall_reboot_handler(void __user **arg)\n{\n    struct ksu_install_fd_tw *tw;\n',
        'int ksu_supercall_reboot_handler(void __user **arg)\n{\n    struct ksu_install_fd_tw *tw;\n\n'
        '    /* Return to stock reboot validation without queueing work or exposing a fd. */\n'
        '    if (!manager_or_root())\n        return -EPERM;\n', 'reboot install entry')
    # Installation is checked again in ksu_install_fd when task_work actually runs.
    # Never pass a negative return value to ksu_close_fd on copy_to_user failure.
    text = once(text, '        ksu_close_fd(fd);\n',
                '        if (fd >= 0)\n            ksu_close_fd(fd);\n', 'fd failure cleanup')
    return text


def harden_dispatch(text):
    for cmd in ('GET_INFO', 'GET_INFO_LEGACY', 'CHECK_SAFEMODE'):
        marker = f'.cmd = KSU_IOCTL_{cmd},'
        if text.count(marker) != 1:
            raise RuntimeError(f'ioctl preimage drift: {cmd}')
        start = text.index(marker)
        end = text.index('    },', start)
        block = text[start:end]
        block = once(block, '.perm_check = always_allow', '.perm_check = manager_or_root', cmd)
        if '.allow_su_session = true' in block:
            raise RuntimeError(f'unexpected SU-session bypass: {cmd}')
        text = text[:start] + block + text[end:]
    return text


def main():
    lock = json.loads(Path('inputs.lock.json').read_text())
    ksu = Path('kernel_workspace/kernel_platform/KernelSU/kernel')
    common = Path('kernel_workspace/kernel_platform/common')
    kbuild_path = ksu / 'Kbuild'
    kbuild = kbuild_path.read_text()
    start = kbuild.index('MDIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))')
    end = kbuild.index('KSU_NEW_DCACHE_FLUSH :=', start)
    # Retain the official 30000 + history-count formula; freeze the count outside
    # Bazel, where the sibling KernelSU .git is otherwise invisible.
    frozen = ('# Official version formula, frozen from the pinned complete Git history.\n'
              f"KSU_GIT_VERSION := {lock['kernelsu']['git_count']}\n"
              '$(eval KSU_VERSION=$(shell expr 30000 + $(KSU_GIT_VERSION)))\n'
              '$(info -- KernelSU version: $(KSU_VERSION))\n'
              'ccflags-y += -DKSU_VERSION=$(KSU_VERSION)\n\n')
    identity = ('# Values for the official supported build parameters.\n'
                'KSU_KERNEL_DIR := $(srctree)/drivers/kernelsu\n'
                f"KSU_PACKAGE_NAME := {lock['manager']['package']}\n"
                f"KSU_EXPECTED_SIZE := {lock['manager']['certificate_size']}\n"
                f"KSU_EXPECTED_HASH := {lock['manager']['certificate_sha256']}\n"
                'KSU_IS_PR_BUILD := 0\n\n')
    kbuild = identity + kbuild[:start] + frozen + kbuild[end:]
    build_path = common / 'BUILD.bazel'
    build = once(build_path.read_text(),
        'post_defconfig_fragments = ["arch/arm64/configs/plk110_stock.fragment"],',
        'post_defconfig_fragments = [\n'
        '        "arch/arm64/configs/plk110_stock.fragment",\n'
        '        "arch/arm64/configs/plk110_official.fragment",\n    ],', 'root fragment')
    apk = ksu / 'manager/apk_sign.c'
    apk_before = hashlib.sha256(apk.read_bytes()).hexdigest()
    updates = {
        kbuild_path: kbuild,
        ksu / 'supercall/supercall.c': harden_supercall((ksu / 'supercall/supercall.c').read_text()),
        ksu / 'supercall/dispatch.c': harden_dispatch((ksu / 'supercall/dispatch.c').read_text()),
        build_path: build,
        common / 'arch/arm64/configs/plk110_official.fragment':
            Path('baselines/PLK110_A67_official.config.additions').read_text(),
    }
    overlay = []
    for path, text in updates.items():
        original = path.read_text() if path.exists() else ''
        relative = str(path.relative_to(Path('kernel_workspace/kernel_platform'))).replace('\\', '/')
        overlay.extend(difflib.unified_diff(original.splitlines(keepends=True), text.splitlines(keepends=True),
                                           fromfile='a/' + relative, tofile='b/' + relative))
        path.write_text(text, encoding='utf-8', newline='\n')
    Path('artifacts/LOCAL_OFFICIAL_OVERLAY.patch').write_text(''.join(overlay), encoding='utf-8', newline='\n')
    assert hashlib.sha256(apk.read_bytes()).hexdigest() == apk_before
    report = {
        'official_version': lock['kernelsu']['version'], 'embedded_k_number': False,
        'official_manager_build_parameters': lock['manager'],
        'apk_signature_parser_unchanged': True,
        'manager_fd_permission': 'manager_or_root at entry and actual installation',
        'info_ioctl_permissions': ['GET_INFO', 'GET_INFO_LEGACY', 'CHECK_SAFEMODE'],
        'su_session_fd_path_unchanged': True, 'pguard': False,
        'compiled': False, 'device_tested': False,
    }
    Path('artifacts/OFFICIAL_KERNEL_PREPARATION.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Prepared official metadata, package/certificate gate, and K32 fd/info access controls.')


if __name__ == '__main__':
    main()
