#!/usr/bin/env python3
"""Experimental Android 16 / 6.12 port of tiann/KernelSU PR #3877.

Base: ReSukiSU 6ec8d9a8 + CCTV18 SUSFS4OKI 8dce4337.
Upstream: tiann/KernelSU a85dcbcfc3b09ae410f31aae124d04f3777fdf1c.

The original SUSFS Inline Hook calls the legacy exported
security_context_to_sid_with_policy() ABI from selinux/hooks.c and
selinux/selinuxfs.c. Do not just replace the ReSukiSU file.
No part of this experiment changes the original PGuard baseline.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path("kernel_workspace")
PINNED = ROOT / "kernel_platform/KernelSU/kernel/feature/selinux_hide.c"
UPSTREAM = ROOT / "ksu3877/kernel/feature/selinux_hide.c"
HOOKS = ROOT / "kernel_platform/common/security/selinux/hooks.c"
REPORT = Path("artifacts/KSUPR3877_EXPERIMENTAL.txt")


def function(src: str, declaration: str) -> str:
    pat = re.compile(r"^" + declaration + r"\([^;{}]*\)\s*\{", re.M)
    matches = list(pat.finditer(src))
    if not matches:
        raise RuntimeError(f"Function not found: {declaration}")
    # ReSukiSU retains a second parser for legacy Linux kernels; for
    # PLK110 6.12 we intentionally select the first (6.6+) definition.
    if len(matches) != 1 and declaration != "static int string_to_context_struct":
        raise RuntimeError(f"Ambiguous function: {declaration}: {len(matches)}")
    start = matches[0].start()
    opening = src.rfind("{", matches[0].start(), matches[0].end())
    depth = 0
    for i in range(opening, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start : i + 1]
    raise RuntimeError(f"Unclosed function: {declaration}")


def exactly_once(src: str, original: str, replacement: str, name: str) -> str:
    n = src.count(original)
    if n != 1:
        raise RuntimeError(f"{name}: expected 1 occurrence, found {n}")
    return src.replace(original, replacement, 1)


def rename_symbols(src: str, changes: dict[str, str]) -> str:
    for old, new in changes.items():
        src = re.sub(r"\b" + re.escape(old) + r"\b", new, src)
    return src


def main() -> None:
    old = PINNED.read_text()
    new = UPSTREAM.read_text()
    hooks = HOOKS.read_text()
    assert "ksu_selinux_hide_running" in hooks
    assert "CONFIG_KSU_SUSFS" in hooks
    assert "security_context_to_sid_with_policy" in hooks
    assert "KSU_COMPAT_HAS_SUSFS_FEATURE_SELINUX_HIDE" in old
    assert "struct task_security_struct" in new or "ksu_task_security_struct" in new

    # PR #3877 parses backup and live SELinux contexts together. Preserve the
    # older branch implementations through their preprocessor gates.
    old_parser = function(old, "static int string_to_context_struct")
    upstream_parser = function(new, "static int string_to_context_struct")
    if "orig_sidtabp" not in upstream_parser or "orig_ctx" not in upstream_parser:
        raise RuntimeError("Unexpected upstream parser")
    # Validate original-policy context against the original context, not backup.
    upstream_parser = exactly_once(
        upstream_parser,
        "policydb_context_isvalid(orig_pol, ctx)",
        "policydb_context_isvalid(orig_pol, orig_ctx)",
        "Fix original context validity",
    )
    old = exactly_once(old, old_parser, upstream_parser, "Dual-context parser")

    # Keep the original externally linked ABI for the SUSFS inline hooks.
    # Export a richer, separate entry point for setprocattr, which must use
    # live SID rather than the backup SID.
    old_helper = function(old, "__maybe_static int security_context_to_sid_with_policy")
    upstream_helper = function(new, "static int security_context_to_sid_with_policy")
    upstream_helper = exactly_once(
        upstream_helper,
        "static int security_context_to_sid_with_policy(",
        "int ksu_security_context_to_sid_with_policy_ex(",
        "Extended dual-policy helper",
    )
    if "orig_sid_p" not in upstream_helper or "rcu_read_lock()" not in upstream_helper:
        raise RuntimeError("Expected PR #3877 dual SID behavior")
    legacy_wrapper = """
// Preserve CCTV18 SUSFS's existing symbol and argument ABI.
__maybe_static int security_context_to_sid_with_policy(struct selinux_policy *policy,
                                                       const char *scontext, u32 scontext_len,
                                                       u32 *sid, u32 def_sid, gfp_t gfp_flags)
{
    return ksu_security_context_to_sid_with_policy_ex(policy, scontext, scontext_len,
                                                       sid, def_sid, gfp_flags, NULL, NULL);
}
"""
    old = exactly_once(
        old, old_helper, upstream_helper + "\n" + legacy_wrapper,
        "ReSukiSU dual-policy SID helper",
    )
    if "#include <linux/rcupdate.h>" not in old:
        old = exactly_once(
            old, "#include <linux/cred.h>",
            "#include <linux/cred.h>\n#include <linux/rcupdate.h>",
            "RCU header",
        )

    # The SUSFS patch intercepts setprocattr *in the stock SELinux hooks.c*,
    # unlike KernelSU upstream's LSM hook. Port the PR #3877 checks there;
    # otherwise its timing-side-channel fix would never execute.
    orig_hook = function(hooks, "static int my_setprocattr")
    prefix_map = {
        "cred_sid": "ksu_3877_cred_sid",
        "task_sid_obj": "ksu_3877_task_sid_obj",
        "ptrace_parent_sid": "ksu_3877_ptrace_parent_sid",
        "ksu_task_security_struct": "task_security_struct",
    }
    helpers = "\n\n".join(
        rename_symbols(function(new, pat), prefix_map)
        for pat in (
            "static inline u32 cred_sid",
            "static inline u32 task_sid_obj",
            "static u32 ptrace_parent_sid",
        )
    )
    new_hook = function(new, "static int __nocfi my_setprocattr")
    new_hook = rename_symbols(new_hook, prefix_map)
    new_hook = exactly_once(
        new_hook,
        "static int __nocfi my_setprocattr(",
        "static int my_setprocattr(",
        "SUSFS-hook signature",
    )
    new_hook = exactly_once(
        new_hook,
        "current_uid().val < 10000",
        "current_uid().val < 10000 || !ksu_selinux_hide_running",
        "SUSFS-hook activation gate",
    )
    new_hook = rename_symbols(
        new_hook,
        {
            "ksu_avc_has_perm_compat": "avc_has_perm",
            "ksu_security_bounded_transition_compat": "security_bounded_transition",
            "security_context_to_sid_with_policy":
                "ksu_security_context_to_sid_with_policy_ex",
        },
    )
    new_hook = exactly_once(
        new_hook,
        "((setprocattr_fn)selinux_setprocattr_hook.original)(name, value, size)",
        "selinux_setprocattr(name, value, size)",
        "Call original stock SELinux hook",
    )
    assert "commit_creds(new);" in new_hook
    assert "PROCESS__DYNTRANSITION" in new_hook
    assert "PROCESS__PTRACE" in new_hook
    hooks = exactly_once(
        hooks, orig_hook, helpers + "\n\n" + new_hook,
        "SUSFS inline setprocattr PR #3877 port",
    )

    symbol = "extern bool ksu_selinux_hide_running __read_mostly;"
    extended_decl = """
extern int ksu_security_context_to_sid_with_policy_ex(
    struct selinux_policy *policy, const char *scontext, u32 scontext_len,
    u32 *sid, u32 def_sid, gfp_t gfp_flags, u32 *orig_sid_p, int *orig_rc_p);"""
    hooks = exactly_once(hooks, symbol, symbol + extended_decl, "External SID helper")
    if "#include <linux/rcupdate.h>" not in hooks:
        hooks = exactly_once(
            hooks, "#include <linux/cred.h>",
            "#include <linux/cred.h>\n#include <linux/rcupdate.h>",
            "SELinux RCU header",
        )

    assert "ksu_security_context_to_sid_with_policy_ex" in old
    assert "ksu_security_context_to_sid_with_policy_ex" in hooks
    assert old.count("static int string_to_context_struct(") >= 1
    assert "return selinux_setprocattr(name, value, size);" in hooks
    PINNED.write_text(old)
    HOOKS.write_text(hooks)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        "EXPERIMENTAL / NOT DEVICE-VALIDATED / DO NOT FLASH\n"
        "Target: OnePlus 15 PLK110 A67 Android 16 kernel 6.12\n"
        "ReSukiSU: 6ec8d9a8a8be30878c388504cacf8ae7849c757b\n"
        "SUSFS4OKI: 8dce4337bcd15807c5449bbeff6e02a967138db0\n"
        "Reference: tiann/KernelSU PR #3877 "
        "(a85dcbcfc3b09ae410f31aae124d04f3777fdf1c)\n"
        "Includes: dual-policy SELinux SID mapping, RCU handling, "
        "original setprocattr permission flow, preserved old SUSFS ABI.\n"
        "Needs: compilation, static review, boot test, and Chunqiu 4.6.0 recheck.\n"
    )
    print("Prepared EXPERIMENTAL PR #3877 backport; do not flash without audit.")


if __name__ == "__main__":
    main()
