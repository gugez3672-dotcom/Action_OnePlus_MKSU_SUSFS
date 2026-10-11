#!/usr/bin/env python3
"""#26: small SELinux correctness backports on top of boot-tested #25.

Targets pinned ReSukiSU 6ec8d9a8, Android 16 / Linux 6.12, SUSFS inline
hooks. Keep PR #3877's working adaptation untouched.

References:
 - KernelSU #3746 (bd82a853b55d2660fead11009165dfdde8fcbf64)
 - KernelSU 0ff54fab4e741d958daf3048d7711644c40eca79
 - #25 device audit: boot-completed backup_sepolicy cleanup can race
   the statically installed SUSFS inline read paths.

The boot-life backup policy is retained rather than freed asynchronously.
This is specific to the built-in, non-unloadable PLK110 kernel.
"""
from __future__ import annotations

from pathlib import Path

KSU = Path("kernel_workspace/kernel_platform/KernelSU/kernel")
RULES = KSU / "selinux/rules.c"
SEPOLICY = KSU / "selinux/sepolicy.c"
BOOT_EVENT = KSU / "runtime/boot_event.c"
REPORT = Path("artifacts/SELINUX_CORRECTNESS_26.txt")


def replace_exact(text: str, before: str, after: str, label: str, n: int = 1) -> str:
    count = text.count(before)
    if count != n:
        raise RuntimeError(f"{label}: expected {n} old patterns, got {count}")
    return text.replace(before, after)


def main() -> None:
    rules = RULES.read_text()
    sepol = SEPOLICY.read_text()
    boot = BOOT_EVENT.read_text()

    # 1. Official #3746: read the *live* RCU policy pointer under the mutex,
    # never sample it before the mutex and then "protect" the stale local.
    rules = replace_exact(
        rules,
        "struct selinux_policy *pol, *old_pol = selinux_state.policy;",
        "struct selinux_policy *pol, *old_pol;",
        "policy init declaration",
    )
    rules = replace_exact(
        rules,
        """    mutex_lock(&selinux_state.policy_mutex);
    backup_sepolicy =
        ksu_dup_sepolicy(rcu_dereference_protected(old_pol, lockdep_is_held(&selinux_state.policy_mutex)));""",
        """    mutex_lock(&selinux_state.policy_mutex);
    old_pol = rcu_dereference_protected(selinux_state.policy, lockdep_is_held(&selinux_state.policy_mutex));
    backup_sepolicy = ksu_dup_sepolicy(old_pol);""",
        "apply_kernelsu_rules mutex-to-pointer ordering",
    )
    rules = replace_exact(
        rules,
        "    old_pol = selinux_state.policy;\n    pol = ksu_dup_sepolicy(",
        "    old_pol = rcu_dereference_protected(selinux_state.policy, lockdep_is_held(&selinux_state.policy_mutex));\n    pol = ksu_dup_sepolicy(",
        "handle_sepolicy protected pointer",
    )
    rules = replace_exact(
        rules,
        "pol = ksu_dup_sepolicy(rcu_dereference_protected(old_pol, lockdep_is_held(&selinux_state.policy_mutex)));",
        "pol = ksu_dup_sepolicy(old_pol);",
        "both policy duplication paths", n=2,
    )

    # 2. Official 0ff54fab: retain insertion padding; only correct its
    # XPERMS field accounting and serialized node deletion accounting.
    sepol = replace_exact(
        sepol,
        """            grow_size += sizeof(u8);
            grow_size += sizeof(u8);
            grow_size += sizeof(u32) * ARRAY_SIZE(avdatum.u.xperms->perms.p);""",
        """            grow_size += sizeof(avdatum.u.xperms->specified) +
                         sizeof(avdatum.u.xperms->driver) +
                         sizeof(avdatum.u.xperms->perms.p);""",
        "XPERMS insertion capacity",
    )
    sepol = replace_exact(
        sepol,
        "int shrink_size = sizeof(struct avtab_key) + sizeof(struct avtab_datum);",
        """int shrink_size = sizeof(node->key.source_type) + sizeof(node->key.target_type) +
                      sizeof(node->key.target_class) + sizeof(node->key.specified);""",
        "serialized AVTAB node removal size",
    )
    sepol = replace_exact(
        sepol,
        """            if ((n->key.specified & AVTAB_XPERMS) && n->datum.u.xperms) {
                shrink_size += sizeof(u8) + sizeof(u8) + sizeof(u32) * ARRAY_SIZE(n->datum.u.xperms->perms.p);
            }""",
        """            if (n->key.specified & AVTAB_XPERMS)
                shrink_size += sizeof(n->datum.u.xperms->specified) +
                               sizeof(n->datum.u.xperms->driver) +
                               sizeof(n->datum.u.xperms->perms.p);
            else
                shrink_size += sizeof(n->datum.u.data);""",
        "AVTAB exact serialized datum size",
        # ReSukiSU carries this removal logic in both modern and legacy
        # avtab hash-table branches; both must preserve serialized sizing.
        n=2,
    )
    sepol = replace_exact(
        sepol,
        """        if (datum->u.xperms == NULL) {
            datum->u.xperms = (struct avtab_extended_perms *)(kzalloc(sizeof(xperms), GFP_KERNEL));
            if (!datum->u.xperms) {
                pr_err("alloc xperms failed\n");
                return;
            }
            memcpy(datum->u.xperms, &xperms, sizeof(xperms));
        }""".replace('"alloc xperms failed\n"', '"alloc xperms failed\\n"'),
        """        if (datum->u.xperms == NULL) {
            // Defensive fallback for unusual nodes without an xperm payload.
            datum->u.xperms = kmemdup(&xperms, sizeof(xperms), GFP_KERNEL);
            if (!datum->u.xperms) {
                pr_err("alloc xperms failed\\n");
                return;
            }
        } else {
            // Merge a later request for another bit of this same ioctl node.
            for (i = 0; i < ARRAY_SIZE(xperms.perms.p); i++)
                datum->u.xperms->perms.p[i] |= xperms.perms.p[i];
        }""",
        "existing XPERMS node update",
    )

    # 3. SUSFS has statically installed hooks that can retain backup_policy
    # pointers beyond their running-flag test. A one-shot boot-completed
    # reclamation lacks a readers-drained protocol. For built-in only, retain
    # its immutable initial snapshot until kernel shutdown; the static
    # hooks then have a stable lifetime, even across hide feature toggles.
    # Do not modify live sepolicy publication/freeing or the #3877 helper.
    boot = replace_exact(
        boot,
        "    ksu_selinux_hide_drop_backup_if_unused();",
        """    /* PLK110 #26: retain the backup policy until shutdown. SUSFS inline
     * context/access/setprocattr readers can be in flight across the
     * feature-running state gate. Do not free without a reader-drain
     * protocol. Built-in driver never unloads in this device profile.
     */
""".rstrip("\n"),
        "boot-completed backup policy reclamation",
    )

    # Static safety contracts
    assert "old_pol = selinux_state.policy" not in rules
    assert rules.count("old_pol = rcu_dereference_protected(selinux_state.policy,") == 2
    assert "sizeof(node->key.source_type)" in sepol
    assert "datum->u.xperms->perms.p[i] |= xperms.perms.p[i]" in sepol
    assert "ksu_selinux_hide_drop_backup_if_unused();" not in boot

    RULES.write_text(rules)
    SEPOLICY.write_text(sepol)
    BOOT_EVENT.write_text(boot)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        "PLK110 #26 SELinux correctness, built-in kernel only\n"
        "Base: ReSukiSU 6ec8d9a8 + #25 KernelSU PR3877 port\n"
        "Applied: upstream #3746 RCU policy pointer under mutex\n"
        "Applied: upstream 0ff54fab AVTAB delete size, XPERMS OR update\n"
        "Applied: boot-lifetime backup_sepolicy retention (SUSFS static hooks)\n"
        "Unmodified: PR3877 hooks, real policy RCU replacement, PGuard hooks\n"
        "Not changed: seqno, policy reload/-ESTALE, any userspace modules\n"
        "NO ACTUAL DEVICE TEST UNTIL BOOT AND SELINUX RUNTIME RECHECK\n"
    )
    print("Applied PLK110 #26 SELinux correctness backports and backup lifecycle guard.")


if __name__ == "__main__":
    main()
