#!/usr/bin/env python3
"""K30 minimal upstream fixes against the *pinned K29* ReSukiSU + CCTV18 tree.

One and only one manager-observer callback fix and one SUSFS/SELinux status
state-consistency fix. No kernel/root/manager upstream sync is performed.

Refs:
- tiann/KernelSU PR #3871, commit ab23091edfeddc774e1e880b0919b211808a193e
- cctv18/susfs4oki oki-android16-6.12 5f236a7b573c5a21ad0e5871ee96b63b89486596
"""
from pathlib import Path

ROOT = Path("kernel_workspace")
KSU = ROOT / "kernel_platform/KernelSU/kernel"
COMMON = ROOT / "kernel_platform/common"
OBS = KSU / "manager/pkg_observer.c"
SEL = COMMON / "security/selinux/selinuxfs.c"
REPORT = Path("artifacts/K30_UPSTREAM_FIXSET.txt")


def replace_once(source: str, old: str, new: str, title: str) -> str:
    found = source.count(old)
    if found != 1:
        raise RuntimeError(f"{title}: expected exactly 1 old sequence; got {found}")
    if new in source:
        raise RuntimeError(f"{title}: new sequence unexpectedly present before patch")
    return source.replace(old, new, 1)


def main() -> None:
    obs_original = OBS.read_text()
    sel_original = SEL.read_text()
    obs = obs_original
    sel = sel_original

    # K29 uses track_throne(0) directly from the packages.list fsnotify event.
    # The upstream fix runs the scan using task_work on the original task,
    # after the directory/fsnotify locks are released. Do not use a kworker:
    # its mount namespace can differ from the task that changed packages.list.
    obs = replace_once(
        obs,
        "#include <linux/rculist.h>\n",
        "#include <linux/rculist.h>\n#include <linux/sched.h>\n#include <linux/task_work.h>\n",
        "KSU observer task_work includes",
    )
    task_work_helper = """static void ksu_track_throne_tw_func(struct callback_head *cb)
{
    kfree(cb);
    /* task_work may execute after exit_fs(); do not dereference file paths then. */
    if (current->flags & PF_EXITING)
        return;
    track_throne(0);
}

static void ksu_defer_track_throne(void)
{
    struct callback_head *cb;

    if (!(current->flags & PF_KTHREAD)) {
        cb = kzalloc(sizeof(*cb), GFP_KERNEL);
        if (cb) {
            cb->func = ksu_track_throne_tw_func;
            if (!task_work_add(current, cb, TWA_RESUME))
                return;
            kfree(cb);
        }
    }

    /* Same fallback as upstream #3871; diagnostic, never a silent skip. */
    pr_warn("defer track_throne failed, run it inline\\n");
    track_throne(0);
}

"""
    obs = replace_once(
        obs,
        "static struct fsnotify_group *g;\n\n",
        "static struct fsnotify_group *g;\n\n" + task_work_helper,
        "KSU observer task_work helper",
    )
    obs = replace_once(
        obs,
        '        pr_info("packages.list detected: %d\\n", mask);\n        track_throne(0);\n',
        '        pr_info("packages.list detected: %d\\n", mask);\n        ksu_defer_track_throne();\n',
        "KSU observer queue instead of inline scan",
    )

    # CCTV18 current code fixes an inconsistent enabled/running gate.
    # Restrict the change to selinuxfs fake status open; leave SELinux
    # policy, #3877 execution checks, helper ABI and fake_status lifetime
    # exactly as K29.
    old = "if (likely(current_uid().val >= 10000 && ksu_selinux_hide_enabled)) {"
    new = "if (likely(current_uid().val >= 10000 && ksu_selinux_hide_running)) {"
    if "static int my_sel_open_handle_status(" not in sel:
        raise RuntimeError("K29 SUSFS SELinux status hook missing")
    sel = replace_once(sel, old, new, "SELinux status running gate")

    # Preflight identities and invariants, fail if the sources drift.
    assert obs.count("static void ksu_defer_track_throne(void)") == 1
    assert obs.count("track_throne(0);") == 2  # task_work path and failure fallback
    assert obs.count("kсу_defer_track_throne();") == 0  # reject visually confusable name
    assert obs.count("ksu_defer_track_throne();") == 1
    assert "task_work_add(current, cb, TWA_RESUME)" in obs
    assert "if (current->flags & PF_EXITING)" in obs
    assert sel.count(new) == 1
    assert old not in sel
    assert "static int my_sel_open_handle_status(" in sel
    assert "fake_status" in sel

    # Atomic-at-the-script-level: do not write either file until all checks pass.
    OBS.write_text(obs)
    SEL.write_text(sel)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        "K30 minimal upstream backport, isolated from K29\n"
        "source=ReSukiSU@6ec8d9a8 + cctv18/susfs4oki@8dce4337\n"
        "ksu_observer=KernelSU#ab23091 (task_work, packages.list scan)\n"
        "susfs_selinux_status=cctv18@5f236a7b (enabled -> running, single hook)\n"
        "unchanged=KernelSU #3877 dual-policy SELinux; SUSFS interfaces; A67; PGuard\n"
        "verification=source assertions only; real device validation PENDING\n"
    )
    print("Applied K30 #3871 observer and SUSFS SELinux status state fix.")


if __name__ == "__main__":
    main()
