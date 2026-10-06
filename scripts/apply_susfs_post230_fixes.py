#!/usr/bin/env python3
from pathlib import Path

ROOT = Path("kernel_workspace/kernel_platform/common")

def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one preimage, found {count} in {path}")
    path.write_text(text.replace(old, new, 1))

# Upstream SUSFS gki-android16-6.12 fixes backported onto the pinned
# CCTV18 OKI baseline 8dce4337. KernelSU/ReSukiSU upstream sync is excluded.
#
# c8f64e41e3dea2cd44754d7472d3cd0bc0b40784
#   SUS_MOUNT: fix clone_mnt() race.
# 2528bdb0e2e76d26b9b174a8314ac115c9f00b3c
# 889b537e556a1308cd08eeae95413b579e0d0ac8
# ebbc112e84d21e31ab2aca9aee8aa972ee92ec72
#   SUS_KSTAT: fix statfs f_flags and consolidate wrappers.
# b213c54126fb243595ce7876e91d84d6e0861fec
#   SUS_KSTAT: make is_statically bool, matching userspace ABI.

# 1) SUS_MOUNT clone_mnt() race fix.
namespace = ROOT / "fs/namespace.c"
replace_once(
    namespace,
    """\tstruct mount *mnt;\n\tint err;\n\n#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT\n\t// - We will just stop checking for ksu process if /sdcard/Android is accessible,\n""",
    """\tstruct mount *mnt;\n\tint err;\n#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT\n\tbool is_mnt_ksu_unshared = false;\n\n\t// - We will just stop checking for ksu process if /sdcard/Android is accessible,\n""",
    "clone_mnt bool state",
)
replace_once(
    namespace,
    """\t\t\tif (flag & CL_COPY_MNT_NS) {\n\t\t\t\tmnt = susfs_alloc_unshare_ksu_vfsmnt(old->mnt_devname, old->mnt_id);\n\t\t\t\tgoto bypass_orig_flow;\n\t\t\t}\n""",
    """\t\t\tif (flag & CL_COPY_MNT_NS) {\n\t\t\t\tmnt = susfs_alloc_unshare_ksu_vfsmnt(old->mnt_devname, old->mnt_id);\n\t\t\t\tis_mnt_ksu_unshared = true;\n\t\t\t\tgoto bypass_orig_flow;\n\t\t\t}\n""",
    "clone_mnt unshare state set",
)
replace_once(
    namespace,
    """#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT\n\tif (static_branch_unlikely(&susfs_is_sdcard_android_data_not_decrypted)) {\n\t\tif (susfs_is_current_ksu_domain() && (flag & CL_COPY_MNT_NS))\n\t\t\tmnt->mnt.mnt_flags |= VFSMOUNT_MNT_FLAGS_KSU_UNSHARED_MNT;\n\t}\n#endif // #ifdef CONFIG_KSU_SUSFS_SUS_MOUNT\n""",
    """#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT\n\tif (unlikely(is_mnt_ksu_unshared))\n\t\tmnt->mnt.mnt_flags |= VFSMOUNT_MNT_FLAGS_KSU_UNSHARED_MNT;\n#endif // #ifdef CONFIG_KSU_SUSFS_SUS_MOUNT\n""",
    "clone_mnt flag commit",
)

# 2) SUS_KSTAT statfs/f_flags fix + wrappers.
statfs = ROOT / "fs/statfs.c"
replace_once(
    statfs,
    """#ifdef CONFIG_KSU_SUSFS_SUS_KSTAT\nstatic int susfs_statfs_by_dentry(struct dentry *dentry, struct kstatfs *buf, bool *is_fuse)\n{\n\tint retval;\n\n\tif (!dentry->d_sb->s_op->statfs)\n\t\treturn -ENOSYS;\n\n\tmemset(buf, 0, sizeof(*buf));\n\tretval = security_sb_statfs(dentry);\n\tif (retval)\n\t\treturn retval;\n\tif (!susfs_sus_kstat_spoof_vfs_statfs(d_backing_inode(dentry), buf, is_fuse))\n\t\tgoto bypass_orig_flow;\n\tretval = dentry->d_sb->s_op->statfs(dentry, buf);\nbypass_orig_flow:\n\tif (retval == 0 && buf->f_frsize == 0)\n\t\tbuf->f_frsize = buf->f_bsize;\n\treturn retval;\n}\n#endif // #ifdef CONFIG_KSU_SUSFS_SUS_KSTAT\n""",
    """#ifdef CONFIG_KSU_SUSFS_SUS_KSTAT\nint statfs_by_dentry_wrapper(struct dentry *dentry, struct kstatfs *buf)\n{\n\treturn statfs_by_dentry(dentry, buf);\n}\n\nint calculate_f_flags_wrapper(struct vfsmount *mnt)\n{\n\treturn calculate_f_flags(mnt);\n}\n\nstatic int susfs_statfs_by_dentry(struct dentry *dentry, struct vfsmount *mnt, struct kstatfs *buf, bool *is_fuse)\n{\n\tint retval;\n\n\tif (!dentry->d_sb->s_op->statfs)\n\t\treturn -ENOSYS;\n\n\tmemset(buf, 0, sizeof(*buf));\n\tretval = security_sb_statfs(dentry);\n\tif (retval)\n\t\treturn retval;\n\tif (!susfs_sus_kstat_spoof_vfs_statfs(d_backing_inode(dentry), buf, is_fuse)) {\n\t\tif (buf->f_frsize == 0)\n\t\t\tbuf->f_frsize = buf->f_bsize;\n\t\treturn retval;\n\t}\n\tretval = dentry->d_sb->s_op->statfs(dentry, buf);\n\tif (retval == 0) {\n\t\tbuf->f_flags = calculate_f_flags(mnt);\n\t\tif (buf->f_frsize == 0)\n\t\t\tbuf->f_frsize = buf->f_bsize;\n\t}\n\treturn retval;\n}\n#endif // #ifdef CONFIG_KSU_SUSFS_SUS_KSTAT\n""",
    "statfs SUS_KSTAT implementation",
)
replace_once(
    statfs,
    """\t\t\t// - here we do not call calculate_f_flags() as buf->f_flags will be spoofed\n\t\t\t//   by susfs_statfs_by_dentry().\n\t\t\treturn susfs_statfs_by_dentry(path->dentry, buf, &is_fuse);\n""",
    """\t\t\t// - here we do not call calculate_f_flags() here as buf->f_flags on the\n\t\t\t//   sus_kstat path will be handled by susfs_statfs_by_dentry().\n\t\t\treturn susfs_statfs_by_dentry(path->dentry, path->mnt, buf, &is_fuse);\n""",
    "vfs_statfs SUS_KSTAT call",
)

susfs = ROOT / "fs/susfs.c"
replace_once(
    susfs,
    """static DEFINE_MUTEX(susfs_mutex_lock_sus_kstat);\nstatic DEFINE_HASHTABLE(SUS_KSTAT_HLIST, 14);\n\nstatic int statfs_by_dentry(struct dentry *dentry, struct kstatfs *buf)\n{\n\tint retval;\n\n\tif (!dentry->d_sb->s_op->statfs)\n\t\treturn -ENOSYS;\n\n\tmemset(buf, 0, sizeof(*buf));\n\tretval = security_sb_statfs(dentry);\n\tif (retval)\n\t\treturn retval;\n\tretval = dentry->d_sb->s_op->statfs(dentry, buf);\n\tif (retval == 0 && buf->f_frsize == 0)\n\t\tbuf->f_frsize = buf->f_bsize;\n\treturn retval;\n}\n""",
    """static DEFINE_MUTEX(susfs_mutex_lock_sus_kstat);\nstatic DEFINE_HASHTABLE(SUS_KSTAT_HLIST, 14);\n\nextern int calculate_f_flags_wrapper(struct vfsmount *mnt);\nextern int statfs_by_dentry_wrapper(struct dentry *dentry, struct kstatfs *buf);\n""",
    "susfs statfs wrappers",
)
replace_once(
    susfs,
    """\t\terr = statfs_by_dentry(no_sus_vfsmnt->mnt_root, &new_entry->spoofed_kstatfs);\n\t\tdput(no_sus_vfsmnt->mnt_root);\n""",
    """\t\terr = statfs_by_dentry_wrapper(no_sus_vfsmnt->mnt_root, &new_entry->spoofed_kstatfs);\n\t\tif (!err)\n\t\t\tnew_entry->spoofed_kstatfs.f_flags = calculate_f_flags_wrapper(no_sus_vfsmnt);\n\t\tdput(no_sus_vfsmnt->mnt_root);\n""",
    "susfs fuse statfs snapshot",
)
replace_once(
    susfs,
    """\terr = statfs_by_dentry(no_sus_vfsmnt->mnt_root, &new_entry->spoofed_kstatfs);\n\tdput(no_sus_vfsmnt->mnt_root);\n""",
    """\terr = statfs_by_dentry_wrapper(no_sus_vfsmnt->mnt_root, &new_entry->spoofed_kstatfs);\n\tif (!err)\n\t\tnew_entry->spoofed_kstatfs.f_flags = calculate_f_flags_wrapper(no_sus_vfsmnt);\n\tdput(no_sus_vfsmnt->mnt_root);\n""",
    "susfs normal statfs snapshot",
)

# 3) Kernel/userspace structure type alignment.
susfs_h = ROOT / "include/linux/susfs.h"
replace_once(
    susfs_h,
    "\tint                                     is_statically;\n",
    "\tbool                                    is_statically;\n",
    "is_statically bool ABI",
)

# Contract checks: exactly the intended upstream end-state, and no accidental
# KernelSU/ReSukiSU sync is performed by this script.
checks = {
    namespace: [
        "bool is_mnt_ksu_unshared = false;",
        "is_mnt_ksu_unshared = true;",
        "if (unlikely(is_mnt_ksu_unshared))",
    ],
    statfs: [
        "int statfs_by_dentry_wrapper(struct dentry *dentry, struct kstatfs *buf)",
        "int calculate_f_flags_wrapper(struct vfsmount *mnt)",
        "buf->f_flags = calculate_f_flags(mnt);",
        "susfs_statfs_by_dentry(path->dentry, path->mnt, buf, &is_fuse)",
    ],
    susfs: [
        "extern int calculate_f_flags_wrapper(struct vfsmount *mnt);",
        "extern int statfs_by_dentry_wrapper(struct dentry *dentry, struct kstatfs *buf);",
        "new_entry->spoofed_kstatfs.f_flags = calculate_f_flags_wrapper(no_sus_vfsmnt);",
    ],
    susfs_h: [
        "bool                                    is_statically;",
    ],
}
for path, needles in checks.items():
    text = path.read_text()
    for needle in needles:
        if needle not in text:
            raise SystemExit(f"postcondition missing in {path}: {needle}")

print("Applied audited SUSFS post-2.3.0 fixset: c8f64e41, 2528bdb0, 889b537e, ebbc112e, b213c541")
