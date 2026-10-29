"""Fail-closed source invariants before entering the compiler."""
import hashlib
import json
from pathlib import Path
import re
from c_source_checks import function_body, verify_smaps_hooks


def read(root, relative):
    return (root / relative).read_text()


def main():
    lock = json.loads(Path('inputs.lock.json').read_text())
    common = Path('kernel_workspace/kernel_platform/common')
    ksu = Path('kernel_workspace/kernel_platform/KernelSU/kernel')
    susfs = Path('kernel_workspace/susfs4ksu')
    driver = common / 'drivers/kernelsu'
    assert driver.is_symlink() and driver.is_dir() and driver.resolve() == ksu.resolve(), 'wrong driver source linkage'
    assert read(common, 'drivers/Makefile').count('obj-$(CONFIG_KSU) += kernelsu/') == 1
    assert read(common, 'drivers/Kconfig').count('source "drivers/kernelsu/Kconfig"') == 1
    supercall = read(ksu, 'supercall/supercall.c')
    install = supercall.split('int ksu_install_fd(void)\n{', 1)[1].split('\n}', 1)[0]
    entry = supercall.split('int ksu_supercall_reboot_handler(void __user **arg)\n{', 1)[1].split('\n}', 1)[0]
    assert 'if (!manager_or_root())' in install and 'return -EPERM;' in install
    assert entry.index('if (!manager_or_root())') < entry.index('kzalloc')
    assert 'if (!manager_or_root())\n        return -EPERM;' in entry
    assert entry.index('return -EPERM;') < entry.index('kzalloc')
    reboot = function_body(read(common, 'kernel/reboot.c'), 'SYSCALL_DEFINE4')
    assert 'ret = ksu_handle_sys_reboot(magic1, magic2, cmd, &arg);' in reboot
    assert 'if (ret) {\n\t\tgoto orig_flow;\n\t}' in reboot
    assert 'if (!ns_capable(pid_ns->user_ns, CAP_SYS_BOOT))\n\t\treturn -EPERM;' in reboot
    smaps = verify_smaps_hooks(read(common, 'fs/proc/task_mmu.c'))
    su = supercall.split('int ksu_install_su_fd(void)\n{', 1)[1].split('\n}', 1)[0]
    assert 'KSU_DRIVER_PERMISSION_SU_SESSION' in su and 'manager_or_root' not in su
    assert 'if (fd >= 0)\n            ksu_close_fd(fd);' in supercall
    dispatch = read(ksu, 'supercall/dispatch.c')
    for cmd in ('GET_INFO', 'GET_INFO_LEGACY', 'CHECK_SAFEMODE'):
        block = dispatch.split(f'.cmd = KSU_IOCTL_{cmd},', 1)[1].split('    },', 1)[0]
        assert '.perm_check = manager_or_root' in block and 'always_allow' not in block
        assert 'allow_su_session' not in block
    assert 'KSU_IOCTL_GET_FULL_VERSION' not in dispatch, 'new version ioctl requires an explicit access review'
    assert '.allow_su_session = true' in dispatch, 'official SU-session support was lost'
    kbuild = read(ksu, 'Kbuild')
    for setting in (
        f"KSU_PACKAGE_NAME := {lock['manager']['package']}",
        f"KSU_EXPECTED_SIZE := {lock['manager']['certificate_size']}",
        f"KSU_EXPECTED_HASH := {lock['manager']['certificate_sha256']}",
        f"KSU_GIT_VERSION := {lock['kernelsu']['git_count']}",
        'KSU_KERNEL_DIR := $(srctree)/drivers/kernelsu',
        'ccflags-y += -DEXPECTED_SIZE=$(KSU_EXPECTED_SIZE)',
        'ccflags-y += -DEXPECTED_HASH=\\"$(KSU_EXPECTED_HASH)\\"',
    ):
        assert setting in kbuild, setting
    assert not re.search(r'(?m)^GIT\s*[:?]?=', kbuild), 'Git version probing remains inside Bazel'
    assert 'KSU_VERSION_FULL' not in kbuild and 'ReSukiSU' not in kbuild and 'PGuard' not in kbuild
    assert 'kernelsu-objs += hook/arm64/syscall_hook.o' not in kbuild

    hooks = {
        'fs/exec.c': 'ksu_handle_execveat_sucompat',
        'fs/open.c': 'ksu_handle_faccessat',
        'fs/stat.c': 'ksu_handle_stat',
        'kernel/reboot.c': 'ksu_handle_sys_reboot',
        'kernel/sys.c': 'ksu_handle_setresuid',
        'drivers/input/input.c': 'ksu_handle_input_handle_event',
        'security/selinux/selinuxfs.c': 'ksu_selinux_hide_running',
    }
    for file, hook in hooks.items():
        assert hook in read(common, file), f'missing manual hook {file}: {hook}'
    selinux_hooks = read(common, 'security/selinux/hooks.c')
    assert 'handle_selinux_setprocattr' not in selinux_hooks, 'app attr writes must use stock setprocattr'
    assert 'selinux_hide_type_bound());' in selinux_hooks, 'missing SELinux hide type bound'
    assert 'WRITE_ONCE(ksu_selinux_hide_type_bound' in read(ksu, 'selinux/rules.c')
    observer = read(ksu, 'manager/pkg_observer.c')
    callback = observer.split('static void ksu_track_throne_tw_func', 1)[1].split('\n}', 1)[0]
    assert callback.index('track_throne(false);') < callback.index('susfs_parse_priority_app_strings();')
    source_hashes = {}
    for directory in ('fs', 'include/linux'):
        for source in (susfs / 'kernel_patches' / directory).iterdir():
            if source.is_file():
                target = common / directory / source.name
                assert source.read_bytes() == target.read_bytes(), f'official source changed: {target}'
                source_hashes[str(target.relative_to(common))] = hashlib.sha256(target.read_bytes()).hexdigest()
    priority = read(common, 'fs/susfs.c')
    assert priority.count('synchronize_rcu();') >= 2, 'SUSFS 519 UID filter fix missing'
    fragment = read(common, 'arch/arm64/configs/plk110_official.fragment')
    assert fragment == Path('baselines/PLK110_A67_official.config.additions').read_text()
    kconfig_symbols = set(re.findall(r'^config (\w+)', read(ksu, 'Kconfig'), re.M))
    for name in re.findall(r'(?:^|# )CONFIG_(\w+)', fragment, re.M):
        assert name in kconfig_symbols, f'obsolete fork Kconfig option: {name}'
    assert 'PLK110_PARTITION_GUARD' not in fragment
    assert not (common / 'block/plk110_partition_guard.c').exists()
    public = common / 'arch/arm64/configs/plk110_a67_stock_ikconfig'
    assert public.read_bytes() == Path('baselines/PLK110_16.0.8.302_stock.config').read_bytes()
    assert hashlib.sha256(public.read_bytes()).hexdigest() == lock['stock_config_sha256']
    report = {'passed': True, 'scope': 'Source checks only; compile and device checks pending.',
              'official_added_source_hashes': source_hashes, 'manual_hooks': hooks,
              'manager_info_access': 'manager_or_root', 'su_session_preserved': True,
              'unprivileged_reboot_magic': 'falls back to stock validation', 'smaps_hooks': smaps,
              'pguard': False, 'embedded_k_number': False}
    Path('artifacts/SOURCE_INVARIANTS.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS: official pins/hooks, K32 gates, SU session, stock public config, no PGuard/K suffix.')


if __name__ == '__main__':
    main()
