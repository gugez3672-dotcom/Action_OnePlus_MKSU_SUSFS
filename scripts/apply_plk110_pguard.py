# Apply PLK110 A67 Partition Guard v2 as the only kernel delta on top of #11.
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
 * PLK110 A67 Partition Guard v2
 *
 * Runtime-only guard for destructive raw block-device operations. It is
 * intentionally outside firmware/bootloader paths and does not alter normal
 * filesystem I/O. Dynamic modem NV/calibration partitions remain quiet pass-through.
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

#define PLK110_PGUARD_VERSION "PLK110-PGuard-v2"
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
 * runtime writers. These ranges deliberately remain pass-through and silent.
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

	/*
	 * Also cover unslotted spellings and the remaining static SM8850
	 * firmware families seen in the PLK110 firmware set.  Entries that are
	 * absent from this exact A67 GPT are inert; registration only occurs for
	 * real partition_meta_info names discovered by the kernel.
	 */
	{ "xbl", PLK110_PG_HARD },
	{ "xbl_config", PLK110_PG_HARD },
	{ "abl", PLK110_PG_HARD },
	{ "uefi", PLK110_PG_HARD },
	{ "uefisecapp", PLK110_PG_HARD },
	{ "imagefv", PLK110_PG_HARD },
	{ "devcfg", PLK110_PG_HARD },
	{ "tz", PLK110_PG_HARD },
	{ "hyp", PLK110_PG_HARD },
	{ "aop", PLK110_PG_HARD },
	{ "qupfw", PLK110_PG_HARD },
	{ "keymaster", PLK110_PG_HARD },
	{ "cpucp", PLK110_PG_HARD },
	{ "shrm", PLK110_PG_HARD },

	{ "xbl_ac_config", PLK110_PG_HARD },
	{ "xbl_ac_config_a", PLK110_PG_HARD },
	{ "xbl_ac_config_b", PLK110_PG_HARD },
	{ "tz_ac_config", PLK110_PG_HARD },
	{ "tz_ac_config_a", PLK110_PG_HARD },
	{ "tz_ac_config_b", PLK110_PG_HARD },
	{ "tz_qti_config", PLK110_PG_HARD },
	{ "tz_qti_config_a", PLK110_PG_HARD },
	{ "tz_qti_config_b", PLK110_PG_HARD },
	{ "hyp_ac_config", PLK110_PG_HARD },
	{ "hyp_ac_config_a", PLK110_PG_HARD },
	{ "hyp_ac_config_b", PLK110_PG_HARD },
	{ "aop_config", PLK110_PG_HARD },
	{ "aop_config_a", PLK110_PG_HARD },
	{ "aop_config_b", PLK110_PG_HARD },
	{ "engineering_cdt", PLK110_PG_HARD },
	{ "engineering_cdt_a", PLK110_PG_HARD },
	{ "engineering_cdt_b", PLK110_PG_HARD },
	{ "oplus_sec", PLK110_PG_HARD },
	{ "oplus_sec_a", PLK110_PG_HARD },
	{ "oplus_sec_b", PLK110_PG_HARD },
	{ "pvmfw", PLK110_PG_HARD },
	{ "pvmfw_a", PLK110_PG_HARD },
	{ "pvmfw_b", PLK110_PG_HARD },
	{ "pvmfw_signed", PLK110_PG_HARD },
	{ "pvmfw_signed_a", PLK110_PG_HARD },
	{ "pvmfw_signed_b", PLK110_PG_HARD },
	{ "qtvm_dtbo", PLK110_PG_HARD },
	{ "qtvm_dtbo_a", PLK110_PG_HARD },
	{ "qtvm_dtbo_b", PLK110_PG_HARD },
	{ "oplus_storagefw", PLK110_PG_HARD },
	{ "oplus_storagefw_a", PLK110_PG_HARD },
	{ "oplus_storagefw_b", PLK110_PG_HARD },
	{ "cdt", PLK110_PG_HARD },
	{ "cdt_a", PLK110_PG_HARD },
	{ "cdt_b", PLK110_PG_HARD },
	{ "ddr", PLK110_PG_HARD },
	{ "ddr_a", PLK110_PG_HARD },
	{ "ddr_b", PLK110_PG_HARD },
	{ "ocdt", PLK110_PG_HARD },
	{ "ocdt_a", PLK110_PG_HARD },
	{ "ocdt_b", PLK110_PG_HARD },
	{ "dinfo", PLK110_PG_AUDIT },
	{ "dinfo_a", PLK110_PG_AUDIT },
	{ "dinfo_b", PLK110_PG_AUDIT },
	{ "uefivarstore", PLK110_PG_AUDIT },
	{ "uefivarstore_a", PLK110_PG_AUDIT },
	{ "uefivarstore_b", PLK110_PG_AUDIT },
	{ "secretkeeper", PLK110_PG_HARD },
	{ "secretkeeper_a", PLK110_PG_HARD },
	{ "secretkeeper_b", PLK110_PG_HARD },

	{ "bluetooth", PLK110_PG_HARD },
	{ "bluetooth_a", PLK110_PG_HARD },
	{ "bluetooth_b", PLK110_PG_HARD },
	{ "dsp", PLK110_PG_HARD },
	{ "dsp_a", PLK110_PG_HARD },
	{ "dsp_b", PLK110_PG_HARD },
	{ "cpucp_dtb", PLK110_PG_HARD },
	{ "cpucp_dtb_a", PLK110_PG_HARD },
	{ "cpucp_dtb_b", PLK110_PG_HARD },
	{ "soccp", PLK110_PG_HARD },
	{ "soccp_a", PLK110_PG_HARD },
	{ "soccp_b", PLK110_PG_HARD },
	{ "soccp_debug", PLK110_PG_HARD },
	{ "soccp_debug_a", PLK110_PG_HARD },
	{ "soccp_debug_b", PLK110_PG_HARD },
	{ "soccp_dcd", PLK110_PG_HARD },
	{ "soccp_dcd_a", PLK110_PG_HARD },
	{ "soccp_dcd_b", PLK110_PG_HARD },
	{ "pdp", PLK110_PG_HARD },
	{ "pdp_a", PLK110_PG_HARD },
	{ "pdp_b", PLK110_PG_HARD },
	{ "pdp_cdb", PLK110_PG_HARD },
	{ "pdp_cdb_a", PLK110_PG_HARD },
	{ "pdp_cdb_b", PLK110_PG_HARD },
	{ "dcp", PLK110_PG_HARD },
	{ "dcp_a", PLK110_PG_HARD },
	{ "dcp_b", PLK110_PG_HARD },
	{ "tme_fw", PLK110_PG_HARD },
	{ "tme_fw_a", PLK110_PG_HARD },
	{ "tme_fw_b", PLK110_PG_HARD },
	{ "tme_config", PLK110_PG_HARD },
	{ "tme_config_a", PLK110_PG_HARD },
	{ "tme_config_b", PLK110_PG_HARD },
	{ "tme_seq_patch", PLK110_PG_HARD },
	{ "tme_seq_patch_a", PLK110_PG_HARD },
	{ "tme_seq_patch_b", PLK110_PG_HARD },
	{ "multiimgqti", PLK110_PG_HARD },
	{ "multiimgqti_a", PLK110_PG_HARD },
	{ "multiimgqti_b", PLK110_PG_HARD },
	{ "multiimgoem", PLK110_PG_HARD },
	{ "multiimgoem_a", PLK110_PG_HARD },
	{ "multiimgoem_b", PLK110_PG_HARD },
	{ "spuservice", PLK110_PG_HARD },
	{ "spuservice_a", PLK110_PG_HARD },
	{ "spuservice_b", PLK110_PG_HARD },
	{ "featenabler", PLK110_PG_HARD },
	{ "featenabler_a", PLK110_PG_HARD },
	{ "featenabler_b", PLK110_PG_HARD },

	{ "boot", PLK110_PG_HARD },
	{ "init_boot", PLK110_PG_HARD },
	{ "vendor_boot", PLK110_PG_HARD },
	{ "dtbo", PLK110_PG_HARD },
	{ "vbmeta", PLK110_PG_HARD },
	{ "vbmeta_system", PLK110_PG_HARD },
	{ "vbmeta_vendor", PLK110_PG_HARD },
	{ "recovery", PLK110_PG_HARD },
	{ "modem", PLK110_PG_HARD },

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
		/*
	 * Dynamic NV/calibration partitions are intentionally pass-through.
	 * Keep them silent in the steady state: PGuard logs only actual denies
	 * and exceptional internal failures.
	 */
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
	}

	if (plk110_pguard_lookup_overlap(bdev, abs_sector, nr_sectors,
					 &hit, &managed)) {
		if (hit.mode == PLK110_PG_HARD) {
			plk110_pguard_log("DENY", op, bdev, hit.name,
					  abs_sector, nr_sectors);
			return -EPERM;
		}
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

(common / "include/linux/plk110_pguard.h").write_text(r"""
/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef _LINUX_PLK110_PGUARD_H
#define _LINUX_PLK110_PGUARD_H
#include <linux/blkdev.h>
#ifdef CONFIG_PLK110_PARTITION_GUARD
bool plk110_pguard_disk_managed(struct block_device *bdev);
#else
static inline bool plk110_pguard_disk_managed(struct block_device *bdev)
{
	return false;
}
#endif
#endif
""".lstrip())

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
\t  partitions remain pass-through to avoid disrupting legitimate firmware
\t  maintenance. v2 also blocks destructive raw SCSI/UFS passthrough paths.
\t  This does not affect bootloader/Fastboot/EDL operations.

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
\t * PLK110 PGuard v2 lower-layer backstop. This catches destructive bios
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

# Raw SCSI passthrough through /dev/block/sdX bypasses normal filesystem BIO
# classification. Preserve read-only inquiry/health commands, but deny outbound
# or explicitly destructive commands on a managed internal UFS disk.
replace_once(
    "drivers/scsi/sd.c",
    '#include <scsi/scsi_ioctl.h>\n',
    '#include <scsi/scsi_ioctl.h>\n#include <scsi/sg.h>\n#include <linux/plk110_pguard.h>\n',
)
replace_once(
    "drivers/scsi/sd.c",
    """static int sd_ioctl(struct block_device *bdev, blk_mode_t mode,
		    unsigned int cmd, unsigned long arg)
""",
    """static bool plk110_pguard_scsi_destructive_opcode(u8 opcode)
{
	switch (opcode) {
	case 0x04: /* FORMAT UNIT */
	case 0x0a: /* WRITE(6) */
	case 0x0d: /* WRITE SAME(32) */
	case 0x15: /* MODE SELECT(6) */
	case 0x19: /* ERASE */
	case 0x2a: /* WRITE(10) */
	case 0x2e: /* WRITE AND VERIFY(10) */
	case 0x3b: /* WRITE BUFFER / firmware download */
	case 0x3f: /* WRITE LONG */
	case 0x41: /* WRITE SAME(10) */
	case 0x42: /* UNMAP */
	case 0x48: /* SANITIZE */
	case 0x4c: /* LOG SELECT */
	case 0x55: /* MODE SELECT(10) */
	case 0x5f: /* PERSISTENT RESERVE OUT */
	case 0x83: /* EXTENDED COPY */
	case 0x89: /* COMPARE AND WRITE */
	case 0x8a: /* WRITE(16) */
	case 0x8b: /* ORWRITE(16) */
	case 0x93: /* WRITE SAME(16) */
	case 0x94: /* ZBC OUT */
	case 0xaa: /* WRITE(12) */
	case 0xae: /* WRITE AND VERIFY(12) */
	case 0xb5: /* SECURITY PROTOCOL OUT */
	case 0xea: /* WRITE LONG(2) */
		return true;
	default:
		return false;
	}
}

static int sd_ioctl(struct block_device *bdev, blk_mode_t mode,
		    unsigned int cmd, unsigned long arg)
""",
)
replace_once(
    "drivers/scsi/sd.c",
    """	if (bdev_is_partition(bdev) && !capable(CAP_SYS_RAWIO))
		return -ENOIOCTLCMD;

	/*
	 * If we are in the middle of error recovery, don't let anyone
""",
    """	if (bdev_is_partition(bdev) && !capable(CAP_SYS_RAWIO))
		return -ENOIOCTLCMD;

#ifdef CONFIG_PLK110_PARTITION_GUARD
	if (plk110_pguard_disk_managed(bdev) &&
	    (cmd == SG_IO || cmd == SCSI_IOCTL_SEND_COMMAND)) {
		u8 opcode = 0;
		bool outbound = false;

		if (cmd == SG_IO) {
			struct sg_io_hdr hdr;

			if (copy_from_user(&hdr, p, sizeof(hdr)))
				return -EFAULT;
			if (!hdr.cmdp || !hdr.cmd_len)
				return -EINVAL;
			if (copy_from_user(&opcode, hdr.cmdp, sizeof(opcode)))
				return -EFAULT;
			outbound = hdr.dxfer_direction == SG_DXFER_TO_DEV ||
				   hdr.dxfer_direction == SG_DXFER_TO_FROM_DEV;
		} else {
			Scsi_Ioctl_Command __user *sic = p;
			unsigned int inlen;

			if (get_user(inlen, &sic->inlen) ||
			    copy_from_user(&opcode, &sic->data[0], sizeof(opcode)))
				return -EFAULT;
			outbound = inlen != 0;
		}

		(void)outbound;

		if (plk110_pguard_scsi_destructive_opcode(opcode)) {
			pr_warn_ratelimited(
				"PGuard: DENY SCSI-PASSTHRU disk=%s cmd=0x%x opcode=0x%02x pid=%d uid=%u comm=%s\n",
				disk->disk_name, cmd, opcode, task_pid_nr(current),
				__kuid_val(current_uid()), current->comm);
			return -EPERM;
		}
	}
#endif

	/*
	 * If we are in the middle of error recovery, don't let anyone
""",
)

# UFS BSG on this exact baseline does not accept raw SCSI COMMAND UPIUs, but it
# can persistently mutate descriptors/attributes/flags and advanced RPMB state.
# Block only those mutations and leave read/query diagnostics untouched.
replace_once(
    "drivers/ufs/core/ufs_bsg.c",
    """	bsg_reply->reply_payload_rcv_len = 0;

	ufshcd_rpm_get_sync(hba);

	msgcode = bsg_request->msgcode;
""",
    """	bsg_reply->reply_payload_rcv_len = 0;

	msgcode = bsg_request->msgcode;
#ifdef CONFIG_PLK110_PARTITION_GUARD
	if (msgcode == UPIU_TRANSACTION_QUERY_REQ) {
		u8 qop = bsg_request->upiu_req.qr.opcode;

		if (qop == UPIU_QUERY_OPCODE_WRITE_DESC ||
		    qop == UPIU_QUERY_OPCODE_WRITE_ATTR ||
		    qop == UPIU_QUERY_OPCODE_SET_FLAG ||
		    qop == UPIU_QUERY_OPCODE_CLEAR_FLAG ||
		    qop == UPIU_QUERY_OPCODE_TOGGLE_FLAG) {
			pr_warn_ratelimited(
				"PGuard: AUDIT UFS-BSG query-op=0x%02x pid=%d uid=%u comm=%s\n",
				qop, task_pid_nr(current), __kuid_val(current_uid()),
				current->comm);
		}
	}

	if (msgcode == UPIU_TRANSACTION_ARPMB_CMD &&
	    job->request_len >= sizeof(struct ufs_rpmb_request)) {
		struct ufs_rpmb_request *rpmb_req = job->request;
		u16 type = be16_to_cpu(rpmb_req->ehs_req.meta.req_resp_type);

		if (type == UFS_RPMB_WRITE_KEY ||
		    type == UFS_RPMB_WRITE ||
		    type == UFS_RPMB_SEC_CONF_WRITE ||
		    type == UFS_RPMB_PURGE_ENABLE) {
			pr_warn_ratelimited(
				"PGuard: AUDIT UFS-BSG RPMB type=0x%04x pid=%d uid=%u comm=%s\n",
				type, task_pid_nr(current), __kuid_val(current_uid()),
				current->comm);
		}
	}
#endif

	ufshcd_rpm_get_sync(hba);

""",
)

print("Applied PLK110 Partition Guard v2.")
print("Hard-protect: GPT + expanded PLK110 SM8850 boot/verified-boot/subsystem firmware raw writes.")
print("Lower-layer bio backstop: blocks dm-linear/whole-disk LBA bypass attempts.")
print("Raw passthrough: blocks destructive SCSI CDBs; UFS-BSG/RPMB mutations are audit-only.")
print("Quiet pass-through: modemst/fsg/fsc/persist/oplusreserve calibration/NV state.")
print("Normal filesystem I/O, userdata/super contents and firmware/bootloader paths are unchanged.")
