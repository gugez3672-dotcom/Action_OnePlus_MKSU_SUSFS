#!/usr/bin/env python3
"""K31 kernel-only fixes on top of the exact K30 tree (ReSukiSU 6ec8d9a8 after
apply_k30_upstream_fixes.py). Exact pre-images only; any drift fails closed.
Writes nothing unless every fix and every postcondition succeeds.

1. #3871 semantics: the task_work callback must scan synchronously.
   ReSukiSU 6ec8d9a8 track_throne(0) re-queues the scan to init (pid 1) via
   ksu_run_in_init_if_possible(), so K30 still crowned the manager after the
   packages.list rename returned. Upstream ab23091 and BakaSU 8450dd28 scan
   synchronously in the renamer's task_work. The inline fallback (fsnotify
   context, locks held) keeps the asynchronous track_throne(0) on purpose.
2. BakaSU 3d1185d8 (#423): no copy_to_user() inside rcu_read_lock() in
   ksu_handle_get_managers_cmd(). The ioctl output layout is unchanged.
3. KernelSU 469c4282 (#3924): init.rc matched by mounted path, not the source
   dentry name. K30's two accepted paths are kept.
4. KernelSU 6ebd714c (#3733, BakaSU a855ec67), the prerequisite of fix 1 upstream:
   the manager scan runs with ksu_cred and opens APKs and directories without
   fsnotify events or atime updates.
"""
from __future__ import annotations

from pathlib import Path

KSU = Path("kernel_workspace/kernel_platform/KernelSU/kernel")
OBS = KSU / "manager/pkg_observer.c"
MGR = KSU / "manager/manager.c"
RC = KSU / "runtime/ksud_integration.c"
COMPAT = KSU / "compat/kernel_compat.h"
APK = KSU / "manager/apk_sign.c"
THRONE = KSU / "manager/throne_tracker.c"
REPORT = Path("artifacts/K31_KERNEL_FIXSET.txt")


def replace_exact(text: str, old: str, new: str, title: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"{title}: expected exactly one pre-image, found {text.count(old)}")
    if new in text:
        raise RuntimeError(f"{title}: post-image already present")
    return text.replace(old, new, 1)


TW_OLD = """    if (current->flags & PF_EXITING)
        return;
    track_throne(0);
}
"""
TW_NEW = """    if (current->flags & PF_EXITING)
        return;
    /* K31: scan before the rename returns (upstream #3871 / BakaSU 8450dd28).
       track_throne(0) would re-queue the scan to init and run it later. */
    track_throne(TRACK_THRONE_FORCE_SYNCHRONOUS);
}
"""

MGR_OLD = """    struct ksu_manager_node *pos;
    int count = 0;
    u16 max_allowed = cmd->count;

    rcu_read_lock();
    list_for_each_entry_rcu (pos, &ksu_manager_appid_list, list) {
        if (count < max_allowed) {
            struct ksu_manager_entry entry = { .uid = pos->appid, .signature_index = pos->signature_index };

            void __user *dest = (void __user *)((char *)arg + sizeof(struct ksu_get_managers_cmd) +
                                                (count * sizeof(struct ksu_manager_entry)));

            if (copy_to_user(dest, &entry, sizeof(entry))) {
                rcu_read_unlock();
                return -EFAULT;
            }
        }
        count++;
    }
    rcu_read_unlock();

    cmd->total_count = count;
    return 0;
"""
MGR_NEW = """    struct ksu_manager_node *pos;
    struct ksu_manager_entry *entries;
    u16 max_allowed = cmd->count;
    int count = 0;
    int copy_count;

    /* K31 (BakaSU 3d1185d8): never copy_to_user() inside rcu_read_lock(). */
    entries = kcalloc(max_allowed, sizeof(*entries), GFP_KERNEL);
    if (!entries && max_allowed)
        return -ENOMEM;

    rcu_read_lock();
    list_for_each_entry_rcu (pos, &ksu_manager_appid_list, list) {
        if (count < max_allowed) {
            entries[count].uid = pos->appid;
            entries[count].signature_index = pos->signature_index;
        }
        count++;
    }
    rcu_read_unlock();

    cmd->total_count = count;

    copy_count = min_t(int, count, max_allowed);
    if (copy_count && copy_to_user((char __user *)arg + sizeof(*cmd), entries, copy_count * sizeof(*entries))) {
        kfree(entries);
        return -EFAULT;
    }

    kfree(entries);
    return 0;
"""

RC_OLD = """    const char *short_name = fp->f_path.dentry->d_name.name;
    if (strcmp(short_name, "init.rc")) {
        // we are only interested in the `init.rc` file name.
        return false;
    }
"""
RC_NEW = "    /* K31 (KernelSU #3924): bind mounts keep the source dentry name; match the mounted path. */\n"

# KernelSU #3733 (upstream 6ebd714c, BakaSU a855ec67), kernel part for GKI 6.12 only.
# The synchronous #3871 scan runs in the renamer's task (system_server), so the
# scan must use ksu_cred, and must not emit fsnotify events or touch atime on
# other apps' APKs.
COMPAT_INC_OLD = "#include <linux/fs.h>\n"
COMPAT_INC_NEW = "#include <linux/namei.h>\n#include <linux/cred.h>\n#include <linux/fs.h>\n#include <linux/err.h>\n"
COMPAT_HELPER = """
/* K31 (KernelSU #3733): open without fsnotify events (GKI 6.12: dentry_open + __FMODE_NONOTIFY). */
static inline struct file *ksu_filp_open_nonotify(const char *path, int flags)
{
    struct path p;
    struct file *f;
    int ret = kern_path(path, (flags & O_NOFOLLOW) ? 0 : LOOKUP_FOLLOW, &p);

    if (ret)
        return ERR_PTR(ret);
    f = dentry_open(&p, flags | __FMODE_NONOTIFY, current_cred());
    path_put(&p);
    return f;
}
"""
APK_OLD = """    struct file *fp = filp_open(path, O_RDONLY, 0);
    if (IS_ERR(fp)) {
        pr_err("open %s error.\\n", path);
        return false;
    }

    // disable inotify for this file
    fp->f_mode |= FMODE_NONOTIFY;
"""
APK_NEW = """    struct file *fp = ksu_filp_open_nonotify(path, O_RDONLY | O_NOATIME);
    if (IS_ERR(fp)) {
        pr_err("open %s error.\\n", path);
        return false;
    }
"""
DIR_OLD = "            file = filp_open(pos->dirpath, O_RDONLY | O_NOFOLLOW, 0);\n"
DIR_NEW = "            file = ksu_filp_open_nonotify(pos->dirpath, O_RDONLY | O_NOFOLLOW);\n"
INC_OLD = '#include "compat/kernel_compat.h"\n'
INC_NEW = '#include "compat/kernel_compat.h"\n#include "ksu.h"\n'
CRED_OLD = "    INIT_LIST_HEAD(&uid_list);\n"
CRED_NEW = ("    INIT_LIST_HEAD(&uid_list);\n\n"
            "    /* K31 (#3733): scan with KernelSU credentials, not the caller's (system_server). */\n"
            "    const struct cred *old_cred = override_creds(ksu_cred);\n")
REVERT_OLD = """    if (diff_map)
        bitmap_free(diff_map);
}
"""
REVERT_NEW = """    if (diff_map)
        bitmap_free(diff_map);
    revert_creds(old_cred);
}
"""


def main() -> None:
    obs, mgr, rc = OBS.read_text(), MGR.read_text(), RC.read_text()
    compat, apk, throne = COMPAT.read_text(), APK.read_text(), THRONE.read_text()

    # #3733: helper before the header's final #endif, then the three call sites.
    if compat.count(COMPAT_INC_OLD) != 1 or not compat.rstrip().endswith("#endif"):
        raise RuntimeError("#3733: unexpected kernel_compat.h layout")
    if "ksu_filp_open_nonotify" in compat:
        raise RuntimeError("#3733: helper already present")
    compat = compat.replace(COMPAT_INC_OLD, COMPAT_INC_NEW, 1)
    head, tail = compat.rstrip().rsplit("#endif", 1)
    compat = head.rstrip() + "\n" + COMPAT_HELPER + "\n#endif" + tail + "\n"
    apk = replace_exact(apk, APK_OLD, APK_NEW, "#3733 apk_sign open")
    throne = replace_exact(throne, DIR_OLD, DIR_NEW, "#3733 search_manager open")
    throne = replace_exact(throne, INC_OLD, INC_NEW, "#3733 ksu.h include")
    if throne.count("bitmap_free(diff_map);\n}") != 1 or throne.count("    INIT_LIST_HEAD(&uid_list);\n") != 1:
        raise RuntimeError("#3733: do_track_throne layout changed")
    throne = replace_exact(throne, CRED_OLD, CRED_NEW, "#3733 override_creds")
    throne = replace_exact(throne, REVERT_OLD, REVERT_NEW, "#3733 revert_creds")

    # Preconditions: K30 #3871 port must be present exactly once.
    if obs.count("static void ksu_defer_track_throne(void)") != 1:
        raise RuntimeError("K30 #3871 task_work port missing; run apply_k30_upstream_fixes.py first")
    obs = replace_exact(obs, TW_OLD, TW_NEW, "#3871 synchronous task_work scan")
    mgr = replace_exact(mgr, MGR_OLD, MGR_NEW, "get_managers RCU copy_to_user")
    rc = replace_exact(rc, RC_OLD, RC_NEW, "#3924 init.rc mounted path")

    # Postconditions.
    assert obs.count("track_throne(TRACK_THRONE_FORCE_SYNCHRONOUS);") == 1
    assert obs.count("track_throne(0);") == 1, "inline fallback must stay asynchronous"
    assert "task_work_add(current, cb, TWA_RESUME)" in obs
    assert "copy_to_user" not in mgr[mgr.index("rcu_read_lock();", mgr.index("ksu_handle_get_managers_cmd")):
                                     mgr.index("rcu_read_unlock();", mgr.index("ksu_handle_get_managers_cmd"))]
    assert "short_name" not in rc[rc.index("static bool is_init_rc"):rc.index("static bool is_init_rc") + 900]
    assert '"/system/etc/init/hw/init.rc"' in rc and '"/init.rc"' in rc and "d_path(&fp->f_path" in rc

    assert throne.count("override_creds(ksu_cred)") == 1 and throne.count("revert_creds(old_cred)") == 1
    assert "filp_open(pos->dirpath" not in throne and "FMODE_NONOTIFY;" not in apk
    # the override must sit after the last early return of do_track_throne
    body = throne[throne.index("void do_track_throne"):throne.index("void track_throne(")]
    assert "return;" not in body[body.index("override_creds"):], "early return after override_creds"

    OBS.write_text(obs)
    MGR.write_text(mgr)
    RC.write_text(rc)
    COMPAT.write_text(compat)
    APK.write_text(apk)
    THRONE.write_text(throne)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        "base=ReSukiSU@6ec8d9a8 + K30 apply_k30_upstream_fixes.py\n"
        "fix=#3871 task_work scans synchronously (upstream ab23091, BakaSU 8450dd28)\n"
        "fix=get_managers_cmd copy_to_user outside RCU (BakaSU 3d1185d8)\n"
        "fix=#3924 init.rc mounted path (KernelSU 469c4282)\n"
        "verification=source pre/post-image assertions only; compile and device PENDING\n")
    print("Applied K31 kernel fixes: #3871 sync scan, #3733, get_managers RCU, #3924")


if __name__ == "__main__":
    main()
