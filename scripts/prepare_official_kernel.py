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


STOCK_PARSER_ANCHOR = 'static int string_to_context_struct(struct policydb *pol,\n'
STOCK_PARSER_END = 'out:\n\tif (rc)\n\t\tcontext_destroy(ctx);\n\treturn rc;\n}\n'
HIDE_PARSER_START = '/*\n * Caveat:  Mutates scontext.\n */\nstatic int string_to_context_struct('
HIDE_PARSER_SHA256 = '7d667a071019e4dc2d9841b842deb04ad66bf229d834d9fec4e58fab58ab2f2a'
HIDE_PARSER_ENTRY = 'ksu_string_to_context_struct('


def share_stock_context_parser(text):
    # One out-of-line copy of the stock parser, reachable with an explicit policy.
    text = once(text, STOCK_PARSER_ANCHOR,
                'static noinline int string_to_context_struct(struct policydb *pol,\n', 'stock parser noinline')
    return once(text, STOCK_PARSER_END, STOCK_PARSER_END +
        '\n/* SELinux hide parses the backup and live policies with the stock parser. */\n'
        'int ksu_string_to_context_struct(struct policydb *pol, struct sidtab *sidtabp,\n'
        '\t\t\t\t char *scontext, struct context *ctx, u32 def_sid);\n\n'
        'int ksu_string_to_context_struct(struct policydb *pol, struct sidtab *sidtabp,\n'
        '\t\t\t\t char *scontext, struct context *ctx, u32 def_sid)\n'
        '{\n\treturn string_to_context_struct(pol, sidtabp, scontext, ctx, def_sid);\n}\n',
        'stock parser entry')


def use_stock_context_parser(text):
    # Replace the hide copy of the parser: a context rejected by the backup
    # policy then runs exactly the stock code; the live policy is parsed only
    # after the backup context is fully valid. Live IDs still come only from
    # the live policy; SID sync and ESTALE retry in the caller are unchanged.
    if text.count(HIDE_PARSER_START) != 1 or HIDE_PARSER_ENTRY in text:
        raise RuntimeError('selinux_hide parser preimage drift')
    start = text.index(HIDE_PARSER_START)
    end = text.index('\n}\n', start) + 3
    if hashlib.sha256(text[start:end].encode()).hexdigest() != HIDE_PARSER_SHA256:
        raise RuntimeError('selinux_hide parser preimage drift')
    parser = (
        'int ksu_string_to_context_struct(struct policydb *pol, struct sidtab *sidtabp, char *scontext,\n'
        '                                 struct context *ctx, u32 def_sid);\n\n'
        '/*\n * Caveat:  Mutates scontext.\n */\n'
        'static int string_to_context_struct(struct policydb *pol, struct policydb *orig_pol, struct sidtab *sidtabp,\n'
        '                                    struct sidtab *orig_sidtabp, char *scontext, const char *source, u32 source_len,\n'
        '                                    struct context *ctx, struct context *orig_ctx, u32 def_sid, int *orig_rc_p)\n'
        '{\n'
        '    int rc;\n\n'
        '    // the stock parser destroys ctx on failure; orig_ctx stays untouched\n'
        '    rc = ksu_string_to_context_struct(pol, sidtabp, scontext, ctx, def_sid);\n'
        '    if (rc) {\n'
        '        *orig_rc_p = -EINVAL;\n'
        '        return rc;\n'
        '    }\n\n'
        '    // backup context is valid; parse the live policy from the original string\n'
        '    memcpy(scontext, source, source_len);\n'
        "    scontext[source_len] = '\\0';\n"
        '    *orig_rc_p = ksu_string_to_context_struct(orig_pol, orig_sidtabp, scontext, orig_ctx, def_sid);\n'
        '    return 0;\n'
        '}\n')
    text = text[:start] + parser + text[end:]
    if 'symtab_search(' in text or text.count(HIDE_PARSER_ENTRY) != 3:
        raise RuntimeError('selinux_hide parser replacement drift')
    return text


def bound_stock_context_parser(text):
    # K40: a stock context_to_sid entry whose parser treats types above a bound
    # as undefined; the bound is 0 (no-op) for every existing caller.
    text = once(text, '\t\t\t\t    u32 def_sid)\n{\n\tstruct role_datum *role;',
                '\t\t\t\t    u32 def_sid,\n\t\t\t\t    u32 type_bound)\n{\n\tstruct role_datum *role;', 'parser bound arg')
    text = once(text, '\tif (!typdatum || typdatum->attribute)\n\t\tgoto out;\n\n\tctx->type = typdatum->value;',
                '\tif (!typdatum || typdatum->attribute ||\n\t    (type_bound && typdatum->value > type_bound))\n'
                '\t\tgoto out;\n\n\tctx->type = typdatum->value;', 'parser bound check')
    text = once(text, '\t\t\t\t\tu32 *sid, u32 def_sid, gfp_t gfp_flags,\n\t\t\t\t\tint force)\n{',
                '\t\t\t\t\tu32 *sid, u32 def_sid, gfp_t gfp_flags,\n\t\t\t\t\tint force, u32 type_bound)\n{', 'core bound arg')
    text = once(text, '\trc = string_to_context_struct(policydb, sidtab, scontext2,\n\t\t\t\t      &context, def_sid);',
                '\trc = string_to_context_struct(policydb, sidtab, scontext2,\n\t\t\t\t      &context, def_sid, type_bound);',
                'core parse')
    text = once(text, 'rc = string_to_context_struct(args->newp, NULL, s, newc, SECSID_NULL);',
                'rc = string_to_context_struct(args->newp, NULL, s, newc, SECSID_NULL, 0);', 'convert parse')
    text = once(text, '\treturn string_to_context_struct(pol, sidtabp, scontext, ctx, def_sid);\n',
                '\treturn string_to_context_struct(pol, sidtabp, scontext, ctx, def_sid, 0);\n', 'hide parse')
    text = once(text, '\t\t\t\t\t    sid, SECSID_NULL, gfp, 0);\n}\n',
                '\t\t\t\t\t    sid, SECSID_NULL, gfp, 0, 0);\n}\n\n'
                'int security_context_to_sid_bounded(const char *scontext, u32 scontext_len,\n'
                '\t\t\t\t    u32 *sid, gfp_t gfp, u32 type_bound);\n\n'
                '/* As security_context_to_sid; types above a nonzero type_bound are undefined. */\n'
                'int security_context_to_sid_bounded(const char *scontext, u32 scontext_len,\n'
                '\t\t\t\t    u32 *sid, gfp_t gfp, u32 type_bound)\n{\n'
                '\treturn security_context_to_sid_core(scontext, scontext_len,\n'
                '\t\t\t\t\t    sid, SECSID_NULL, gfp, 0, type_bound);\n}\n', 'bounded entry')
    text = once(text, '\t\t\t\t\t    sid, def_sid, gfp_flags, 1);\n',
                '\t\t\t\t\t    sid, def_sid, gfp_flags, 1, 0);\n', 'default core')
    text = once(text, '\t\t\t\t\t    sid, SECSID_NULL, GFP_KERNEL, 1);\n',
                '\t\t\t\t\t    sid, SECSID_NULL, GFP_KERNEL, 1, 0);\n', 'force core')
    if text.count('security_context_to_sid_core(') != 5:
        raise RuntimeError('context_to_sid_core caller drift')
    return text


HIDE_SETPROCATTR = (
    '#ifdef CONFIG_KSU_SUSFS\n'
    'static int handle_selinux_setprocattr(const char *name, void *value, size_t size)\n{\n'
    '\tif ((likely(!strcmp(name, "current") &&\n'
    '\t\t\t\tcurrent_uid().val >= 10000 &&\n'
    '\t\t\t\tksu_selinux_hide_running)))\n'
    '\t\treturn my_setprocattr(name, value, size);\n'
    '\treturn selinux_setprocattr(name, value, size);\n}\n'
    '#endif // #ifdef CONFIG_KSU_SUSFS\n\n')


def bound_stock_setattr(text):
    # K40: app attr writes run the stock selinux_setprocattr, so the newline and
    # permission paths are stock code; hiding is only the bound in the stock parse.
    hook = ('#ifdef CONFIG_KSU_SUSFS\n\tLSM_HOOK_INIT(setprocattr, handle_selinux_setprocattr),\n'
            '#else\n\tLSM_HOOK_INIT(setprocattr, selinux_setprocattr),\n#endif // #ifdef CONFIG_KSU_SUSFS\n')
    for old, new in ((HIDE_SETPROCATTR, ''), (hook, '\tLSM_HOOK_INIT(setprocattr, selinux_setprocattr),\n')):
        if text.count(old) != 1:
            raise RuntimeError('hide setprocattr dispatch: expected exactly one unmodified preimage')
        text = text.replace(old, new, 1)
    text = once(text, 'static int selinux_lsm_setattr(u64 attr, void *value, size_t size)\n{',
                'int security_context_to_sid_bounded(const char *scontext, u32 scontext_len,\n'
                '\t\t\t\t    u32 *sid, gfp_t gfp, u32 type_bound);\n'
                '#ifdef CONFIG_KSU_SUSFS\nextern u32 ksu_selinux_hide_type_bound;\n#endif\n\n'
                '/* SELinux hide: app UIDs do not see KernelSU-added types. */\n'
                'static inline u32 selinux_hide_type_bound(void)\n{\n'
                '#ifdef CONFIG_KSU_SUSFS\n'
                '\tif (current_uid().val >= 10000 && READ_ONCE(ksu_selinux_hide_running))\n'
                '\t\treturn READ_ONCE(ksu_selinux_hide_type_bound);\n'
                '#endif\n\treturn 0;\n}\n\n'
                'static int selinux_lsm_setattr(u64 attr, void *value, size_t size)\n{', 'setattr bound')
    text = once(text, '\t\terror = security_context_to_sid(value, size,\n\t\t\t\t\t\t&sid, GFP_KERNEL);\n'
                '\t\tif (error == -EINVAL && attr == LSM_ATTR_FSCREATE) {',
                '\t\terror = security_context_to_sid_bounded(value, size,\n\t\t\t\t\t\t&sid, GFP_KERNEL,\n'
                '\t\t\t\t\t\tselinux_hide_type_bound());\n'
                '\t\tif (error == -EINVAL && attr == LSM_ATTR_FSCREATE) {', 'setattr parse')
    if 'handle_selinux_setprocattr' in text:
        raise RuntimeError('hide setprocattr dispatch remains')
    return text


def publish_hide_type_bound(text):
    # KernelSU only appends types to the live policy, so the backup type count is the bound.
    text = once(text, 'struct selinux_policy *backup_sepolicy;\n',
                'struct selinux_policy *backup_sepolicy;\nu32 ksu_selinux_hide_type_bound;\n', 'bound definition')
    return once(text,
        '                pr_info("backup sepolicy success! latest_granting=%d\\n", backup_sepolicy->latest_granting);\n',
        '                WRITE_ONCE(ksu_selinux_hide_type_bound, backup_sepolicy->policydb.p_types.nprim);\n'
        '                pr_info("backup sepolicy success! latest_granting=%d\\n", backup_sepolicy->latest_granting);\n',
        'bound publish')


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
        ksu / 'feature/selinux_hide.c':
            use_stock_context_parser((ksu / 'feature/selinux_hide.c').read_text()),
        ksu / 'selinux/rules.c': publish_hide_type_bound((ksu / 'selinux/rules.c').read_text()),
        common / 'security/selinux/ss/services.c':
            bound_stock_context_parser(
                share_stock_context_parser((common / 'security/selinux/ss/services.c').read_text())),
        common / 'security/selinux/hooks.c': bound_stock_setattr((common / 'security/selinux/hooks.c').read_text()),
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
        'selinux_hide': 'selinuxfs context/access: shared stock parser, backup then live; '
                        '/proc attr writes: stock selinux_setprocattr, app UIDs bounded to backup type count',
        'compiled': False, 'device_tested': False,
    }
    Path('artifacts/OFFICIAL_KERNEL_PREPARATION.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Prepared official metadata, package/certificate gate, and K32 fd/info access controls.')


if __name__ == '__main__':
    main()
