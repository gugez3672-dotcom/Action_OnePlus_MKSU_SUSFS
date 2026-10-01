# Apply PLK110 A67 Partition Guard v1 as the only kernel delta on top of #11.
from pathlib import Path

common = Path("kernel_workspace/kernel_platform/common")

def replace_once(rel, old, new):
    path = common / rel
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"unexpected source layout for {rel}: anchor count={count}")
    path.write_text(text.replace(old, new, 1))

pguard_c = r"""
// SPDX-License-Identifier: GPL-2.0-only
/*
 * PLK110 A67 Partition Guard v1
 *
 * Runtime-only guard for destructive raw block-device operations. It is
 * intentionally outside firmware/bootloader paths and does not alter normal
 * filesystem I/O. Dynamic modem NV/calibration partitions are audit-only in v1.
 */
#include <linux/blkdev.h>
#include <linux/cred.h>
#include <linux/errno.h>
#include <linux/kernel.h>
#include <linux/overflow.h>
#include <linux/sched.h>
#include <linux/spinlock.h>
#include <linux/string.h>

#include "blk.h"

#define PLK110_PGUARD_VERSION "PLK110-PGuard-v1"
#define PLK110_PGUARD_MAX_RANGES 256
#define PLK110_PGUARD_GPT_SECTORS 64

enum plk110_pguard_mode {
	PLK110_PG_NONE = 0,
	PLK110_PG_HARD,
	PLK110_PG_AUDIT,
	PLK110_PG_MARKER,
};

struct plk110_pguard_rule {
	const char *name;
	enum plk110_pguard_mode mode;
};

struct plk110_pguard_range {
	struct gendisk *disk;
	sector_t start;
	sector_t nr_sectors;
	enum plk110_pguard_mode mode;
	char name[PARTITION_META_INFO_VOLNAMELTH];
};

static const char plk110_pguard_version[] __used = PLK110_PGUARD_VERSION;

/*
 * HARD: static boot/verified-boot/baseband firmware partitions that Android
 * runtime should never raw-write on this frozen A67 baseline.
 *
 * AUDIT: device-specific NV/calibration state which can have legitimate
 * runtime writers. v1 records attempts but deliberately does not block them.
 *
 * MARKER: identifies an internal PLK110 UFS LUN so its primary/backup GPT can
 * be protected without blocking normal I/O to the marker partition itself.
 */
static const struct plk110_pguard_rule plk110_pguard_rules[] = {
	{ "xbl_a", PLK110_PG_HARD },
	{ "xbl_b", PLK110_PG_HARD },
	{ "xbl_config_a", PLK110_PG_HARD },
	{ "xbl_config_b", PLK110_PG_HARD },
	{ "abl_a", PLK110_PG_HARD },
	{ "abl_b", PLK110_PG_HARD },
	{ "uefi_a", PLK110_PG_HARD },
	{ "uefi_b", PLK110_PG_HARD },
	{ "uefisecapp_a", PLK110_PG_HARD },
	{ "uefisecapp_b", PLK110_PG_HARD },
	{ "imagefv_a", PLK110_PG_HARD },
	{ "imagefv_b", PLK110_PG_HARD },
	{ "devcfg_a", PLK110_PG_HARD },
	{ "devcfg_b", PLK110_PG_HARD },
	{ "tz_a", PLK110_PG_HARD },
	{ "tz_b", PLK110_PG_HARD },
	{ "hyp_a", PLK110_PG_HARD },
	{ "hyp_b", PLK110_PG_HARD },
	{ "aop_a", PLK110_PG_HARD },
	{ "aop_b", PLK110_PG_HARD },
	{ "qupfw_a", PLK110_PG_HARD },
	{ "qupfw_b", PLK110_PG_HARD },
	{ "keymaster_a", PLK110_PG_HARD },
	{ "keymaster_b", PLK110_PG_HARD },
	{ "cpucp_a", PLK110_PG_HARD },
	{ "cpucp_b", PLK110_PG_HARD },
	{ "shrm_a", PLK110_PG_HARD },
	{ "shrm_b", PLK110_PG_HARD },
	{ "efisp", PLK110_PG_HARD },
	{ "efisp_a", PLK110_PG_HARD },
	{ "efisp_b", PLK110_PG_HARD },

	{ "boot_a", PLK110_PG_HARD },
	{ "boot_b", PLK110_PG_HARD },
	{ "init_boot_a", PLK110_PG_HARD },
	{ "init_boot_b", PLK110_PG_HARD },
	{ "vendor_boot_a", PLK110_PG_HARD },
	{ "vendor_boot_b", PLK110_PG_HARD },
	{ "dtbo_a", PLK110_PG_HARD },
	{ "dtbo_b", PLK110_PG_HARD },
	{ "vbmeta_a", PLK110_PG_HARD },
	{ "vbmeta_b", PLK110_PG_HARD },
	{ "vbmeta_system_a", PLK110_PG_HARD },
	{ "vbmeta_system_b", PLK110_PG_HARD },
	{ "vbmeta_vendor_a", PLK110_PG_HARD },
	{ "vbmeta_vendor_b", PLK110_PG_HARD },
	{ "recovery_a", PLK110_PG_HARD },
	{ "recovery_b", PLK110_PG_HARD },
	{ "modem_a", PLK110_PG_HARD },
	{ "modem_b", PLK110_PG_HARD },

	{ "modemst1", PLK110_PG_AUDIT },
	{ "modemst2", PLK110_PG_AUDIT },
	{ "fsg", PLK110_PG_AUDIT },
	{ "fsc", PLK110_PG_AUDIT },
	{ "persist", PLK110_PG_AUDIT },
	{ "persistbak", PLK110_PG_AUDIT },
	{ "oplusreserve1", PLK110_PG_AUDIT },
	{ "oplusreserve2", PLK110_PG_AUDIT },
	{ "oplusreserve3", PLK110_PG_AUDIT },
	{ "oplusreserve4", PLK110_PG_AUDIT },

	{ "super", PLK110_PG_MARKER },
	{ "userdata", PLK110_PG_MARKER },
	{ "metadata", PLK110_PG_MARKER },
	{ "misc", PLK110_PG_MARKER },
};

static struct plk110_pguard_range plk110_pguard_ranges[PLK110_PGUARD_MAX_RANGES];
static unsigned int plk110_pguard_nr_ranges;
static DEFINE_SPINLOCK(plk110_pguard_lock);

static enum plk110_pguard_mode plk110_pguard_name_mode(const char *name)
{
	size_t i;

	if (!name || !name[0])
		return PLK110_PG_NONE;

	for (i = 0; i < ARRAY_SIZE(plk110_pguard_rules); i++) {
		if (!strcmp(name, plk110_pguard_rules[i].name))
			return plk110_pguard_rules[i].mode;
	}
	return PLK110_PG_NONE;
}

static bool plk110_pguard_overlap(sector_t a_start, sector_t a_nr,
				  sector_t b_start, sector_t b_nr)
{
	sector_t a_end, b_end;

	if (!a_nr || !b_nr)
		return false;
	if (check_add_overflow(a_start, a_nr, &a_end))
		a_end = (sector_t)-1;
	if (check_add_overflow(b_start, b_nr, &b_end))
		b_end = (sector_t)-1;

	return a_start < b_end && b_start < a_end;
}

static void plk110_pguard_log(const char *action, unsigned int op,
			      struct block_device *bdev, const char *target,
			      sector_t abs_sector, sector_t nr_sectors)
{
	pr_warn_ratelimited(
		"PGuard: %s op=%s disk=%s target=%s sector=%llu sectors=%llu pid=%d uid=%u comm=%s\n",
		action, blk_op_str((enum req_op)op), bdev->bd_disk->disk_name,
		target ? target : "-", (unsigned long long)abs_sector,
		(unsigned long long)nr_sectors, task_pid_nr(current),
		__kuid_val(current_uid()), current->comm);
}

void plk110_pguard_register_partition(struct block_device *bdev)
{
	struct plk110_pguard_range *slot;
	enum plk110_pguard_mode mode;
	const char *name;
	unsigned long flags;
	unsigned int i;

	if (!bdev || !bdev->bd_meta_info)
		return;

	name = (const char *)bdev->bd_meta_info->volname;
	mode = plk110_pguard_name_mode(name);
	if (mode == PLK110_PG_NONE)
		return;

	spin_lock_irqsave(&plk110_pguard_lock, flags);
	for (i = 0; i < plk110_pguard_nr_ranges; i++) {
		slot = &plk110_pguard_ranges[i];
		if (slot->disk == bdev->bd_disk &&
		    slot->start == bdev->bd_start_sect &&
		    slot->nr_sectors == bdev_nr_sectors(bdev) &&
		    !strcmp(slot->name, name)) {
			spin_unlock_irqrestore(&plk110_pguard_lock, flags);
			return;
		}
	}

	if (plk110_pguard_nr_ranges >= PLK110_PGUARD_MAX_RANGES) {
		spin_unlock_irqrestore(&plk110_pguard_lock, flags);
		pr_err_ratelimited("PGuard: range cache full; refusing to forget existing guards\n");
		return;
	}

	slot = &plk110_pguard_ranges[plk110_pguard_nr_ranges++];
	slot->disk = bdev->bd_disk;
	slot->start = bdev->bd_start_sect;
	slot->nr_sectors = bdev_nr_sectors(bdev);
	slot->mode = mode;
	strscpy(slot->name, name, sizeof(slot->name));
	spin_unlock_irqrestore(&plk110_pguard_lock, flags);

	pr_info("PGuard: register disk=%s target=%s start=%llu sectors=%llu mode=%u\n",
		bdev->bd_disk->disk_name, name,
		(unsigned long long)bdev->bd_start_sect,
		(unsigned long long)bdev_nr_sectors(bdev), mode);
}

static bool plk110_pguard_lookup_overlap(struct block_device *bdev,
					 sector_t abs_sector,
					 sector_t nr_sectors,
					 struct plk110_pguard_range *hit,
					 bool *managed)
{
	unsigned long flags;
	unsigned int i;
	bool found = false;

	*managed = false;
	spin_lock_irqsave(&plk110_pguard_lock, flags);
	for (i = 0; i < plk110_pguard_nr_ranges; i++) {
		const struct plk110_pguard_range *r = &plk110_pguard_ranges[i];

		if (r->disk != bdev->bd_disk)
			continue;
		*managed = true;
		if (r->mode == PLK110_PG_MARKER)
			continue;
		if (!plk110_pguard_overlap(abs_sector, nr_sectors,
					    r->start, r->nr_sectors))
			continue;
		*hit = *r;
		found = true;
		if (r->mode == PLK110_PG_HARD)
			break;
	}
	spin_unlock_irqrestore(&plk110_pguard_lock, flags);
	return found;
}

bool plk110_pguard_disk_managed(struct block_device *bdev)
{
	unsigned long flags;
	unsigned int i;
	bool managed = false;

	if (!bdev)
		return false;

	spin_lock_irqsave(&plk110_pguard_lock, flags);
	for (i = 0; i < plk110_pguard_nr_ranges; i++) {
		if (plk110_pguard_ranges[i].disk == bdev->bd_disk) {
			managed = true;
			break;
		}
	}
	spin_unlock_irqrestore(&plk110_pguard_lock, flags);
	return managed;
}

int plk110_pguard_check_bio(struct bio *bio)
{
	struct block_device *bdev;
	enum plk110_pguard_mode mode;
	enum req_op op;
	const char *name;

	if (!bio || !bio_sectors(bio))
		return 0;

	op = bio_op(bio);
	switch (op) {
	case REQ_OP_WRITE:
	case REQ_OP_DISCARD:
	case REQ_OP_SECURE_ERASE:
	case REQ_OP_WRITE_ZEROES:
		break;
	default:
		return 0;
	}

	bdev = bio->bi_bdev;
	if (!bdev)
		return 0;

	/*
	 * Normal filesystem I/O reaches this hook on its named partition before
	 * blk_partition_remap(). Known non-protected/marker partitions are safe
	 * to pass immediately. Managed-UFS BLKPG mutation is blocked separately.
	 */
	if (bdev->bd_meta_info) {
		name = (const char *)bdev->bd_meta_info->volname;
		mode = plk110_pguard_name_mode(name);
		if (mode == PLK110_PG_HARD) {
			plk110_pguard_log("DENY-BIO", op, bdev, name,
					  bdev->bd_start_sect + bio->bi_iter.bi_sector,
					  bio_sectors(bio));
			return -EPERM;
		}
		if (mode == PLK110_PG_AUDIT)
			plk110_pguard_log("AUDIT-BIO", op, bdev, name,
					  bdev->bd_start_sect + bio->bi_iter.bi_sector,
					  bio_sectors(bio));
		return 0;
	}

	/*
	 * Do not scan dm/loop/zram traffic. Stacked targets resubmit lower bios;
	 * a dm-linear bypass reaches the physical PLK110 sdX UFS disk here.
	 */
	if (bdev->bd_disk->disk_name[0] != 's' ||
	    bdev->bd_disk->disk_name[1] != 'd')
		return 0;
	if (!plk110_pguard_disk_managed(bdev))
		return 0;

	return plk110_pguard_check_sectors(bdev, bio->bi_iter.bi_sector,
					   bio_sectors(bio), op);
}

int plk110_pguard_check_sectors(struct block_device *bdev, sector_t sector,
				sector_t nr_sectors, unsigned int op)
{
	struct plk110_pguard_range hit = { };
	sector_t abs_sector, capacity, gpt_tail;
	enum plk110_pguard_mode direct_mode = PLK110_PG_NONE;
	const char *direct_name = NULL;
	bool managed = false;

	if (!bdev || !nr_sectors)
		return 0;

	if (check_add_overflow(bdev->bd_start_sect, sector, &abs_sector))
		return -EPERM;

	if (bdev->bd_meta_info) {
		direct_name = (const char *)bdev->bd_meta_info->volname;
		direct_mode = plk110_pguard_name_mode(direct_name);
		if (direct_mode == PLK110_PG_HARD) {
			plk110_pguard_log("DENY", op, bdev, direct_name,
					  abs_sector, nr_sectors);
			return -EPERM;
		}
		if (direct_mode == PLK110_PG_AUDIT)
			plk110_pguard_log("AUDIT", op, bdev, direct_name,
					  abs_sector, nr_sectors);
	}

	if (plk110_pguard_lookup_overlap(bdev, abs_sector, nr_sectors,
					 &hit, &managed)) {
		if (hit.mode == PLK110_PG_HARD) {
			plk110_pguard_log("DENY", op, bdev, hit.name,
					  abs_sector, nr_sectors);
			return -EPERM;
		}
		if (hit.mode == PLK110_PG_AUDIT &&
		    direct_mode != PLK110_PG_AUDIT)
			plk110_pguard_log("AUDIT", op, bdev, hit.name,
					  abs_sector, nr_sectors);
	}

	if (!managed)
		return 0;

	/* Protect both GPT copies on every recognized internal PLK110 UFS LUN. */
	capacity = get_capacity(bdev->bd_disk);
	if (capacity) {
		if (plk110_pguard_overlap(abs_sector, nr_sectors, 0,
					  min_t(sector_t, capacity,
						PLK110_PGUARD_GPT_SECTORS))) {
			plk110_pguard_log("DENY", op, bdev, "primary-gpt",
					  abs_sector, nr_sectors);
			return -EPERM;
		}

		gpt_tail = capacity > PLK110_PGUARD_GPT_SECTORS ?
			capacity - PLK110_PGUARD_GPT_SECTORS : 0;
		if (plk110_pguard_overlap(abs_sector, nr_sectors, gpt_tail,
					  capacity - gpt_tail)) {
			plk110_pguard_log("DENY", op, bdev, "backup-gpt",
					  abs_sector, nr_sectors);
			return -EPERM;
		}
	}

	return 0;
}

int plk110_pguard_check_bytes(struct block_device *bdev, u64 start, u64 len,
			      unsigned int op)
{
	u64 end;
	sector_t first, last;

	if (!len)
		return 0;
	if (check_add_overflow(start, len, &end) || !end)
		return -EPERM;

	first = (sector_t)(start >> SECTOR_SHIFT);
	last = (sector_t)((end - 1) >> SECTOR_SHIFT);
	if (last < first)
		return -EPERM;

	return plk110_pguard_check_sectors(bdev, first, last - first + 1, op);
}
"""
(common / "block/plk110_partition_guard.c").write_text(pguard_c.lstrip())

makefile = common / "block/Makefile"
text = makefile.read_text()
anchor = "obj-$(CONFIG_BLOCK_HOLDER_DEPRECATED)\t+= holder.o\n"
if text.count(anchor) != 1:
    raise SystemExit("unexpected block/Makefile tail")
makefile.write_text(text.replace(
    anchor,
    anchor + "obj-$(CONFIG_PLK110_PARTITION_GUARD) += plk110_partition_guard.o\n",
    1,
))

kconfig = common / "block/Kconfig"
text = kconfig.read_text()
anchor = "if BLOCK\n\n"
if text.count(anchor) != 1:
    raise SystemExit("unexpected block/Kconfig BLOCK anchor")
entry = """if BLOCK

config PLK110_PARTITION_GUARD
\tbool "PLK110 A67 runtime partition guard"
\tdefault n
\thelp
\t  Block destructive raw writes, discard, secure erase and zeroout against
\t  selected PLK110 boot-chain/verified-boot partitions and the primary/
\t  backup GPT while Android is running. Dynamic modem NV/calibration
\t  partitions are audit-only in v1 to avoid disrupting legitimate firmware
\t  maintenance. This does not affect bootloader/Fastboot/EDL operations.

"""
kconfig.write_text(text.replace(anchor, entry, 1))

blk_h = common / "block/blk.h"
text = blk_h.read_text()
anchor = "#endif /* BLK_INTERNAL_H */\n"
if text.count(anchor) != 1:
    raise SystemExit("unexpected block/blk.h end")
decl = """
#ifdef CONFIG_PLK110_PARTITION_GUARD
void plk110_pguard_register_partition(struct block_device *bdev);
bool plk110_pguard_disk_managed(struct block_device *bdev);
int plk110_pguard_check_bio(struct bio *bio);
int plk110_pguard_check_sectors(struct block_device *bdev, sector_t sector,
\t\t\t\tsector_t nr_sectors, unsigned int op);
int plk110_pguard_check_bytes(struct block_device *bdev, u64 start, u64 len,
\t\t\t      unsigned int op);
#else
static inline void plk110_pguard_register_partition(struct block_device *bdev)
{
}
static inline bool plk110_pguard_disk_managed(struct block_device *bdev)
{
\treturn false;
}
static inline int plk110_pguard_check_bio(struct bio *bio)
{
\treturn 0;
}
static inline int plk110_pguard_check_sectors(struct block_device *bdev,
\t\t\t\t\t       sector_t sector,
\t\t\t\t\t       sector_t nr_sectors,
\t\t\t\t\t       unsigned int op)
{
\treturn 0;
}
static inline int plk110_pguard_check_bytes(struct block_device *bdev,
\t\t\t\t\t     u64 start, u64 len,
\t\t\t\t\t     unsigned int op)
{
\treturn 0;
}
#endif

"""
blk_h.write_text(text.replace(anchor, decl + anchor, 1))

replace_once(
    "block/partitions/core.c",
    '#include "check.h"\n',
    '#include "check.h"\n#include "../blk.h"\n',
)
replace_once(
    "block/partitions/core.c",
    """\tif (info) {
\t\terr = -ENOMEM;
\t\tbdev->bd_meta_info = kmemdup(info, sizeof(*info), GFP_KERNEL);
\t\tif (!bdev->bd_meta_info)
\t\t\tgoto out_put;
\t}

\t/* delay uevent until 'holders' subdir is created */
""",
    """\tif (info) {
\t\terr = -ENOMEM;
\t\tbdev->bd_meta_info = kmemdup(info, sizeof(*info), GFP_KERNEL);
\t\tif (!bdev->bd_meta_info)
\t\t\tgoto out_put;
\t}

\t/* Sticky boot-lifetime cache: do not unregister on BLKPG delete/rescan. */
\tplk110_pguard_register_partition(bdev);

\t/* delay uevent until 'holders' subdir is created */
""",
)

replace_once(
    "block/blk-core.c",
    """\tmight_sleep();

\t/*
\t * For a REQ_NOWAIT based request, return -EOPNOTSUPP
""",
    """\tmight_sleep();

\t/*
\t * PLK110 PGuard v1 lower-layer backstop. This catches destructive bios
\t * resubmitted by stackers such as dm-linear, while the helper fast-paths
\t * ordinary named filesystem partitions.
\t */
\tif (unlikely(plk110_pguard_check_bio(bio))) {
\t\tbio->bi_status = BLK_STS_IOERR;
\t\tbio_endio(bio);
\t\treturn;
\t}

\t/*
\t * For a REQ_NOWAIT based request, return -EOPNOTSUPP
""",
)

replace_once(
    "block/fops.c",
    """\tssize_t ret;

\tif (bdev_read_only(bdev))
""",
    """\tssize_t ret;

\tif (iocb->ki_pos >= 0 &&
\t    plk110_pguard_check_bytes(bdev, (u64)iocb->ki_pos,
\t\t\t\t       (u64)iov_iter_count(from), REQ_OP_WRITE))
\t\treturn -EPERM;

\tif (bdev_read_only(bdev))
""",
)

replace_once(
    "block/fops.c",
    """\tif ((start | len) & (bdev_logical_block_size(bdev) - 1))
\t\treturn -EINVAL;

\tfilemap_invalidate_lock(inode->i_mapping);
""",
    """\tif ((start | len) & (bdev_logical_block_size(bdev) - 1))
\t\treturn -EINVAL;

\tif (plk110_pguard_check_bytes(bdev, (u64)start, (u64)len,
\t\t\t\t      REQ_OP_WRITE_ZEROES))
\t\treturn -EPERM;

\tfilemap_invalidate_lock(inode->i_mapping);
""",
)

replace_once(
    "block/fops.c",
    """static int blkdev_mmap(struct file *file, struct vm_area_struct *vma)
{
\tstruct inode *bd_inode = bdev_file_inode(file);

\tif (bdev_read_only(I_BDEV(bd_inode)))
""",
    """static int blkdev_mmap(struct file *file, struct vm_area_struct *vma)
{
\tstruct inode *bd_inode = bdev_file_inode(file);
\tstruct block_device *bdev = I_BDEV(bd_inode);

\tif ((vma->vm_flags & VM_WRITE) &&
\t    plk110_pguard_check_bytes(bdev,
\t\t\t\t       (u64)vma->vm_pgoff << PAGE_SHIFT,
\t\t\t\t       (u64)(vma->vm_end - vma->vm_start),
\t\t\t\t       REQ_OP_WRITE))
\t\treturn -EPERM;

\tif (bdev_read_only(bdev))
""",
)

replace_once(
    "block/ioctl.c",
    """\tif (bdev_is_partition(bdev))
\t\treturn -EINVAL;

\tif (p.pno <= 0)
""",
    """\tif (bdev_is_partition(bdev))
\t\treturn -EINVAL;

\t/* Prevent synthetic overlapping partitions from bypassing cached guards. */
\tif (plk110_pguard_disk_managed(bdev)) {
\t\tpr_warn_ratelimited("PGuard: DENY BLKPG op=%d disk=%s\\n",
\t\t\t\t    op, bdev->bd_disk->disk_name);
\t\treturn -EPERM;
\t}

\tif (p.pno <= 0)
""",
)

replace_once(
    "block/ioctl.c",
    """\terr = blk_validate_byte_range(bdev, start, len);
\tif (err)
\t\treturn err;

\tfilemap_invalidate_lock(bdev->bd_mapping);
""",
    """\terr = blk_validate_byte_range(bdev, start, len);
\tif (err)
\t\treturn err;
\tif (plk110_pguard_check_bytes(bdev, start, len, REQ_OP_DISCARD))
\t\treturn -EPERM;

\tfilemap_invalidate_lock(bdev->bd_mapping);
""",
)

replace_once(
    "block/ioctl.c",
    """\tif (check_add_overflow(start, len, &end) ||
\t    end > bdev_nr_bytes(bdev))
\t\treturn -EINVAL;

\tfilemap_invalidate_lock(bdev->bd_mapping);
""",
    """\tif (check_add_overflow(start, len, &end) ||
\t    end > bdev_nr_bytes(bdev))
\t\treturn -EINVAL;
\tif (plk110_pguard_check_bytes(bdev, start, len, REQ_OP_SECURE_ERASE))
\t\treturn -EPERM;

\tfilemap_invalidate_lock(bdev->bd_mapping);
""",
)

replace_once(
    "block/ioctl.c",
    """\tif (end < start)
\t\treturn -EINVAL;

\t/* Invalidate the page cache, including dirty pages */
""",
    """\tif (end < start)
\t\treturn -EINVAL;
\tif (plk110_pguard_check_bytes(bdev, start, len, REQ_OP_WRITE_ZEROES))
\t\treturn -EPERM;

\t/* Invalidate the page cache, including dirty pages */
""",
)

print("Applied PLK110 Partition Guard v1.")
print("Hard-protect: GPT + static boot/verified-boot/baseband firmware raw writes.")
print("Lower-layer bio backstop: blocks dm-linear/whole-disk LBA bypass attempts.")
print("Audit-only: modemst/fsg/fsc/persist/oplusreserve calibration/NV state.")
print("Normal filesystem I/O, userdata/super contents and firmware/bootloader paths are unchanged.")
