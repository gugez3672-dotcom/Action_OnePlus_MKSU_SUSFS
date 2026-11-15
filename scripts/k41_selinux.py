"""K41: retain native A67 parsing/permissions, add upstream coverage and epochs.

The upstream KSU generation/original-type bookkeeping is retained by the rebased
SUSFS 519 patch. Unlike a second parser, these hooks reuse the native parser and
validate its type against the exact policy object and generation under RCU.
"""
from prepare_official_kernel import once


def native_epoch_parser(text):
    text = once(text,
        '\tif (!typdatum || typdatum->attribute ||\n\t    (type_bound && typdatum->value > type_bound))\n'
        '\t\tgoto out;\n',
        '\tif (!typdatum || typdatum->attribute)\n\t\tgoto out;\n'
        '#ifdef CONFIG_KSU_SUSFS\n'
        '\tif (type_bound) {\n'
        '\t\tint original = ksu_type_is_original(pol, type_bound, typdatum->value);\n'
        '\t\tif (original < 0) {\n\t\t\trc = -EAGAIN;\n\t\t\tgoto out;\n\t\t}\n'
        '\t\tif (!original)\n\t\t\tgoto out;\n\t}\n'
        '#endif\n', 'native parser epoch check')
    text = once(text, 'static noinline int string_to_context_struct(',
        '#ifdef CONFIG_KSU_SUSFS\n'
        'extern int ksu_type_is_original(struct policydb *db, u32 policy_generation, u32 type_value);\n'
        '#endif\n\nstatic noinline int string_to_context_struct(', 'original type declaration')
    text = once(text,
        '\tsidtab = policy->sidtab;\n\trc = string_to_context_struct(policydb, sidtab, scontext2,\n',
        '\tsidtab = policy->sidtab;\n'
        '\t/* Nonzero requests hiding; bind it to this RCU policy generation. */\n'
        '\tif (type_bound) {\n'
        '\t\tif (!policy->latest_granting) {\n\t\t\trc = -EAGAIN;\n\t\t\tgoto out_unlock;\n\t\t}\n'
        '\t\ttype_bound = policy->latest_granting;\n\t}\n'
        '\trc = string_to_context_struct(policydb, sidtab, scontext2,\n', 'RCU generation binding')
    return text.replace('/* As security_context_to_sid; types above a nonzero type_bound are undefined. */',
        '/* Nonzero type_bound hides non-original types using the current policy epoch. */')


def native_xattr(text):
    # Move the existing native-helper declarations before inode_setxattr.
    start = text.index('int security_context_to_sid_bounded(')
    end = text.index('static int selinux_lsm_setattr(', start)
    helper = text[start:end]
    helper = once(helper,
        '#ifdef CONFIG_KSU_SUSFS\nextern u32 ksu_selinux_hide_type_bound;\n#endif\n',
        '/* The parser obtains the bound from the exact live policy generation. */\n',
        'remove unversioned bound declaration')
    helper = once(helper, '\t\treturn READ_ONCE(ksu_selinux_hide_type_bound);',
                  '\t\treturn 1;', 'request epoch-checked hiding')
    text = text[:start] + text[end:]
    anchor = 'static int selinux_inode_setxattr('
    text = once(text, anchor, helper + anchor, 'native xattr declaration position')
    start = text.index(anchor)
    end = text.index('static void selinux_inode_post_setxattr(', start)
    body = text[start:end]
    body = once(body,
        '\trc = security_context_to_sid(value, size, &newsid,\n\t\t\t\t     GFP_KERNEL);',
        '\t/* Keep MAC_ADMIN force parsing, as in upstream KSU #3996. */\n'
        '\tif (selinux_hide_type_bound() &&\n'
        '\t    cap_capable(current_cred(), &init_user_ns, CAP_MAC_ADMIN, CAP_OPT_NOAUDIT))\n'
        '\t\trc = security_context_to_sid_bounded(value, size, &newsid, GFP_KERNEL, 1);\n'
        '\telse\n'
        '\t\trc = security_context_to_sid(value, size, &newsid, GFP_KERNEL);',
        'native inode xattr bounded parse')
    return text[:start] + body + text[end:]


NOTIFY = '''
/* Built-in equivalent of upstream PR #3965: only KSU publications are filtered. */
void ksu_selinux_hide_notify_policyload(u32 seqno)
{
    mutex_lock(&selinux_hide_mutex);
    if (ksu_selinux_hide_running && READ_ONCE(fake_status))
        selnl_notify_policyload_filtered(seqno);
    else
        selnl_notify_policyload(seqno);
    mutex_unlock(&selinux_hide_mutex);
}

'''

NETLINK = '''
#ifdef CONFIG_KSU_SUSFS
/* A67 uses sock_i_uid; recipient ownership, not publisher credentials. */
static int selnl_filter_ksu_policyload(struct sock *sk, struct sk_buff *skb, void *data)
{
	return __kuid_val(sock_i_uid(sk)) >= 10000;
}

void selnl_notify_policyload_filtered(u32 seqno)
{
	struct sk_buff *skb;
	struct nlmsghdr *nlh;

	skb = nlmsg_new(sizeof(struct selnl_msg_policyload), GFP_USER);
	if (!skb)
		goto oom;
	nlh = nlmsg_put(skb, 0, 0, SELNL_MSG_POLICYLOAD,
			sizeof(struct selnl_msg_policyload), 0);
	if (!nlh) {
		kfree_skb(skb);
		goto oom;
	}
	selnl_add_payload(nlh, sizeof(struct selnl_msg_policyload), SELNL_MSG_POLICYLOAD, &seqno);
	NETLINK_CB(skb).dst_group = SELNLGRP_AVC;
	netlink_broadcast_filtered(selnl, skb, 0, SELNLGRP_AVC, GFP_USER,
				   selnl_filter_ksu_policyload, NULL);
	return;
oom:
	pr_err("SELinux: OOM sending KSU policy-load notification\\n");
}
#endif

'''


def extend_k41(updates, ksu, common):
    services = common / 'security/selinux/ss/services.c'
    hooks = common / 'security/selinux/hooks.c'
    updates[services] = native_epoch_parser(updates[services])
    updates[hooks] = native_xattr(updates[hooks])
    rules = ksu / 'selinux/rules.c'
    rules_text = updates[rules]
    assert rules_text.count('selnl_notify_policyload(seqno);') == 2
    rules_text = rules_text.replace('selnl_notify_policyload(seqno);',
                                    'ksu_selinux_hide_notify_policyload(seqno);')
    updates[rules] = once(rules_text, '#include "xfrm.h"\n',
        '#include "xfrm.h"\n#include "feature/selinux_hide.h"\n', 'notify declaration include')
    hide = ksu / 'feature/selinux_hide.c'
    updates[hide] = once(updates[hide], 'static int ksu_selinux_hide_enable()',
                        NOTIFY + 'static int ksu_selinux_hide_enable()', 'serialized KSU notify')
    hide_h = ksu / 'feature/selinux_hide.h'
    updates[hide_h] = once(hide_h.read_text(), '#define __KSU_H_SELINUX_HIDE\n',
        '#define __KSU_H_SELINUX_HIDE\n#include <linux/types.h>\n'
        'void ksu_selinux_hide_notify_policyload(u32 seqno);\n', 'KSU notify prototype')
    netlink = common / 'security/selinux/netlink.c'
    text = once(netlink.read_text(), '#include <net/netlink.h>\n',
                '#include <net/netlink.h>\n#include <net/sock.h>\n', 'socket UID header')
    updates[netlink] = once(text, 'static int __init selnl_init(void)',
                           NETLINK + 'static int __init selnl_init(void)', 'native filtered notification')
    security_h = common / 'security/selinux/include/security.h'
    updates[security_h] = once(security_h.read_text(), '#include <linux/types.h>\n',
        '#include <linux/types.h>\n\n#ifdef CONFIG_KSU_SUSFS\n'
        'void selnl_notify_policyload_filtered(u32 seqno);\n#endif\n', 'native notify prototype')
    return updates
