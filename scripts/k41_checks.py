"""Source-order checks and executable tests of the real KSU epoch helpers."""
from pathlib import Path
import re
import subprocess
import tempfile
import os
from c_source_checks import function_body


def verify_k41_sources(common, ksu):
    def read(root, p):
        return (root / p).read_text()
    hooks = read(common, 'security/selinux/hooks.c')
    services = read(common, 'security/selinux/ss/services.c')
    rules = read(ksu, 'selinux/rules.c')
    hide = read(ksu, 'feature/selinux_hide.c')
    assert 'int ret;' not in function_body(read(ksu, 'core/init.c'), 'kernelsu_init'), 'unused legacy init ret'
    for relative in ('feature/selinux_hide.c', 'feature/sucompat.h', 'hook/setuid_hook.c'):
        assert 'diff --git' not in read(ksu, relative), f'patch header leaked into {relative}'
    assert 'handle_selinux_setprocattr' not in hooks
    assert 'LSM_HOOK_INIT(setprocattr, selinux_setprocattr)' in hooks
    assert 'LSM_HOOK_INIT(setselfattr, selinux_setselfattr)' in hooks
    attrs = function_body(hooks, 'selinux_lsm_setattr')
    assert 'security_context_to_sid_bounded' in attrs
    xattr = function_body(hooks, 'selinux_inode_setxattr')
    assert xattr.index('FILE__RELABELFROM') < xattr.index('security_context_to_sid_bounded')
    assert xattr.index('security_context_to_sid_bounded') < xattr.index('FILE__RELABELTO')
    assert 'cap_capable(current_cred(), &init_user_ns, CAP_MAC_ADMIN, CAP_OPT_NOAUDIT)' in xattr
    assert 'security_context_to_sid_force' in xattr, 'native privileged fallback was lost'
    parser = function_body(services, 'string_to_context_struct')
    assert parser.index('if (!typdatum || typdatum->attribute)') < parser.index('ksu_type_is_original')
    assert 'rc = -EAGAIN;' in parser and 'if (!original)' in parser
    core = function_body(services, 'security_context_to_sid_core')
    assert core.index('rcu_read_lock()') < core.index('type_bound = policy->latest_granting')
    assert core.index('type_bound = policy->latest_granting') < core.index('string_to_context_struct(')
    assert 'static int string_to_context_struct(' in hide and 'ksu_string_to_context_struct(' in hide
    assert 'symtab_search(' not in hide, 'duplicated context parser returned'
    assert 'ksu_set_original_types(db, &old_pol->policydb, pol->latest_granting)' in rules
    assert 'ksu_advance_original_types(' in rules
    assert 'avc_ss_reset(0)' not in rules and 'selnl_notify_policyload(0)' not in rules
    assert rules.count('ksu_selinux_hide_notify_policyload(seqno)') == 2
    notify = function_body(hide, 'ksu_selinux_hide_notify_policyload')
    assert 'ksu_selinux_hide_running && READ_ONCE(fake_status)' in notify
    assert notify.index('mutex_lock') < notify.index('selnl_notify_policyload_filtered') < notify.index('mutex_unlock')
    netlink = read(common, 'security/selinux/netlink.c')
    stock = function_body(netlink, 'selnl_notify_policyload')
    assert 'selnl_notify(SELNL_MSG_POLICYLOAD, &seqno)' in stock
    assert 'filtered' not in stock, 'stock notifications must not be filtered'
    assert 'netlink_broadcast_filtered' in function_body(netlink, 'selnl_notify_policyload_filtered')
    assert '__kuid_val(sock_i_uid(sk)) >= 10000' in function_body(netlink, 'selnl_filter_ksu_policyload')
    assert 'NOKPROBE_SYMBOL(do_execveat_common);' in read(common, 'fs/exec.c')
    return {'native_attr_and_setselfattr': True, 'native_xattr_permission_order': True,
            'native_parser_policy_epoch': True, 'stock_notifications_preserved': True,
            'ksu_recipient_filter': True, 'shared_stock_parser': True}


def check_epoch_helpers(ksu, compiler='cc'):
    source = (ksu / 'selinux/sepolicy.c').read_text()
    functions = []
    for name in ('ksu_set_original_types', 'ksu_advance_original_types', 'ksu_type_is_original'):
        match = re.search(r'^(?:bool|int) ' + name + r'\([^;]*?\)\s*\{', source, re.M)
        assert match, name
        signature = match[0][:-1]
        functions.append(signature + function_body(source, name) + '\n')
    harness = '''#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
typedef uint32_t u32;
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,v) ((x)=(v))
struct policydb { struct { u32 nprim; } p_types; };
static const struct policydb *ksu_original_types_policy;
static u32 ksu_original_types_limit, ksu_original_types_generation;
''' + '\n'.join(functions) + '''
int main(void) {
    struct policydb stock={{100}}, live={{102}}, next={{105}}, foreign={{105}}, reload={{90}};
    assert(ksu_type_is_original(&live, 2, 1) == -1);
    assert(ksu_set_original_types(&live, &stock, 2));
    assert(ksu_type_is_original(&live, 2, 1) == 1);
    assert(ksu_type_is_original(&live, 2, 100) == 1);
    assert(ksu_type_is_original(&live, 2, 101) == 0);
    assert(ksu_type_is_original(&live, 2, 0) == 0);
    assert(ksu_type_is_original(&live, 2, 103) == -1);
    assert(ksu_type_is_original(&live, 1, 1) == -1);
    assert(ksu_type_is_original(&foreign, 2, 1) == -1);
    assert(ksu_advance_original_types(&next, &live, 2, 3));
    assert(ksu_type_is_original(&next, 3, 100) == 1);
    assert(ksu_type_is_original(&next, 3, 101) == 0);
    assert(ksu_type_is_original(&live, 2, 1) == -1);
    assert(!ksu_advance_original_types(&foreign, &live, 2, 4));
    assert(ksu_type_is_original(&next, 3, 1) == -1);
    assert(ksu_set_original_types(&reload, &reload, 5));
    assert(ksu_type_is_original(&reload, 5, 90) == 1);
    assert(ksu_type_is_original(&reload, 5, 91) == -1);
    assert(!ksu_set_original_types(&live, &stock, 0));
    assert(ksu_type_is_original(&reload, 5, 1) == -1);
    return 0;
}
'''
    with tempfile.TemporaryDirectory(prefix='k41-epochs-') as directory:
        src = Path(directory) / 'epochs.c'
        binary = Path(directory) / ('epochs.exe' if os.name == 'nt' else 'epochs')
        src.write_text(harness)
        subprocess.run([compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                        str(src), '-o', str(binary)], check=True, capture_output=True)
        subprocess.run([str(binary)], check=True, capture_output=True)
    return {'actual_upstream_helpers': True, 'assertions': 20,
            'scope': 'sequential policy identity/generation/type transitions; not concurrency or device tests'}
