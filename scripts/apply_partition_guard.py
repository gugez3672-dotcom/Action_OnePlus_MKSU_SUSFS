"""Apply PLK110 PGuard v1 to the verified A67 common kernel.

The guard is intentionally narrow:
- blocks mutating Linux block I/O to xbl/xbl_config/abl/uefi/uefisecapp/efisp
  (including _a/_b slot suffixes);
- blocks whole-disk I/O ranges overlapping those protected partitions;
- blocks the first/last 1 MiB GPT guard bands on phone UFS disks identified by
  known Android GPT partition names.

It does not change bootloader/fastboot behavior and does not add a Kconfig delta.
"""
from pathlib import Path

path = Path("kernel_workspace/kernel_platform/common/block/blk-core.c")
text = path.read_text()

marker = "/* PLK110_PGUARD_V1 */"
if marker in text:
    raise SystemExit("PGuard already applied")

anchor = """static noinline int should_fail_bio(struct bio *bio)
{
	if (should_fail_request(bdev_whole(bio->bi_bdev), bio->bi_iter.bi_size))
		return -EIO;
	return 0;
}
"""
if text.count(anchor) != 1:
    raise SystemExit("unexpected blk-core.c should_fail_bio anchor")

guard = r'''
/* PLK110_PGUARD_V1
 *
 * Runtime-only protection for the PLK110 early boot chain.  This sits in the
 * Linux block layer, so bootloader / fastboot writes are intentionally outside
 * its scope.
 */
#define PGUARD_GPT_GUARD_SECTORS	2048U /* 1 MiB at 512-byte sectors */

static bool pguard_name_matches(const u8 *raw, const char *base)
{
	size_t n, b;

	if (!raw || !base)
		return false;

	n = strnlen((const char *)raw, PARTITION_META_INFO_VOLNAMELTH);
	b = strlen(base);

	if (n == b && !strncasecmp((const char *)raw, base, b))
		return true;

	return n == b + 2 &&
	       !strncasecmp((const char *)raw, base, b) &&
	       raw[b] == '_' && (raw[b + 1] == 'a' || raw[b + 1] == 'b');
}

static bool pguard_is_protected_partition(const struct block_device *bdev)
{
	static const char * const protected_names[] = {
		"xbl",
		"xbl_config",
		"abl",
		"uefi",
		"uefisecapp",
		"efisp",
	};
	const struct partition_meta_info *info;
	unsigned int i;

	if (!bdev || !bdev_is_partition((struct block_device *)bdev))
		return false;

	info = READ_ONCE(bdev->bd_meta_info);
	if (!info)
		return false;

	for (i = 0; i < ARRAY_SIZE(protected_names); i++)
		if (pguard_name_matches(info->volname, protected_names[i]))
			return true;

	return false;
}

static bool pguard_is_phone_partition(const struct block_device *bdev)
{
	static const char * const phone_markers[] = {
		"xbl", "xbl_config", "abl", "uefi", "uefisecapp", "efisp",
		"boot", "init_boot", "vendor_boot", "vbmeta", "dtbo",
		"super", "userdata", "metadata", "persist", "modem",
	};
	const struct partition_meta_info *info;
	unsigned int i;

	if (!bdev || !bdev_is_partition((struct block_device *)bdev))
		return false;

	info = READ_ONCE(bdev->bd_meta_info);
	if (!info)
		return false;

	for (i = 0; i < ARRAY_SIZE(phone_markers); i++)
		if (pguard_name_matches(info->volname, phone_markers[i]))
			return true;

	return false;
}

static bool pguard_is_mutating_bio(const struct bio *bio)
{
	switch (bio_op((struct bio *)bio)) {
	case REQ_OP_WRITE:
	case REQ_OP_DISCARD:
	case REQ_OP_SECURE_ERASE:
	case REQ_OP_WRITE_ZEROES:
	case REQ_OP_ZONE_APPEND:
	case REQ_OP_ZONE_RESET:
	case REQ_OP_ZONE_RESET_ALL:
		return true;
	default:
		return false;
	}
}

static bool pguard_ranges_overlap(sector_t a_start, sector_t a_len,
				  sector_t b_start, sector_t b_len)
{
	sector_t a_end, b_end;

	if (!a_len || !b_len)
		return false;

	a_end = a_start + a_len - 1;
	b_end = b_start + b_len - 1;

	if (a_end < a_start)
		a_end = (sector_t)-1;
	if (b_end < b_start)
		b_end = (sector_t)-1;

	return a_start <= b_end && b_start <= a_end;
}

static bool pguard_disk_has_phone_marker(struct gendisk *disk)
{
	struct block_device *part;
	unsigned long idx;
	bool found = false;

	if (!disk)
		return false;

	rcu_read_lock();
	xa_for_each(&disk->part_tbl, idx, part) {
		if (pguard_is_phone_partition(part)) {
			found = true;
			break;
		}
	}
	rcu_read_unlock();

	return found;
}

static bool pguard_whole_disk_overlap(struct block_device *bdev,
				      sector_t start, sector_t nr)
{
	struct gendisk *disk = bdev->bd_disk;
	struct block_device *part;
	unsigned long idx;
	sector_t total;
	bool blocked = false;

	if (!disk || !nr)
		return false;

	/* Protect both primary and backup GPT regions, but only on disks that
	 * carry known Android/Qualcomm partitions.  This avoids affecting normal
	 * removable SCSI disks.
	 */
	if (pguard_disk_has_phone_marker(disk)) {
		total = bdev_nr_sectors(bdev);
		if (total &&
		    (pguard_ranges_overlap(start, nr, 0,
			min_t(sector_t, total, PGUARD_GPT_GUARD_SECTORS)) ||
		     (total > PGUARD_GPT_GUARD_SECTORS &&
		      pguard_ranges_overlap(start, nr,
				total - PGUARD_GPT_GUARD_SECTORS,
				PGUARD_GPT_GUARD_SECTORS))))
			return true;
	}

	/* A root process can bypass /dev/block/by-name/* and write the parent
	 * disk directly.  Reject any such range that overlaps a protected GPT
	 * partition.
	 */
	rcu_read_lock();
	xa_for_each(&disk->part_tbl, idx, part) {
		if (!pguard_is_protected_partition(part))
			continue;
		if (pguard_ranges_overlap(start, nr, part->bd_start_sect,
					  bdev_nr_sectors(part))) {
			blocked = true;
			break;
		}
	}
	rcu_read_unlock();

	return blocked;
}

static bool pguard_block_bio(struct bio *bio)
{
	struct block_device *bdev;
	sector_t start, nr;

	if (!bio || !pguard_is_mutating_bio(bio))
		return false;

	bdev = bio->bi_bdev;
	nr = bio_sectors(bio);
	if (!bdev || !nr)
		return false;

	if (bdev_is_partition(bdev)) {
		if (!pguard_is_protected_partition(bdev))
			return false;

		pr_warn_ratelimited("PGuard: blocked op=%u to protected partition %pg sector=%llu nr=%llu\n",
				    bio_op(bio), bdev,
				    (unsigned long long)bio->bi_iter.bi_sector,
				    (unsigned long long)nr);
		return true;
	}

	start = bio->bi_iter.bi_sector;
	if (!pguard_whole_disk_overlap(bdev, start, nr))
		return false;

	pr_warn_ratelimited("PGuard: blocked op=%u to protected raw range %pg sector=%llu nr=%llu\n",
			    bio_op(bio), bdev,
			    (unsigned long long)start,
			    (unsigned long long)nr);
	return true;
}
'''

text = text.replace(anchor, anchor + guard, 1)

call_anchor = """	if (should_fail_bio(bio))
		goto end_io;
	bio_check_ro(bio);
"""
if text.count(call_anchor) != 1:
    raise SystemExit("unexpected submit_bio_noacct guard anchor")

text = text.replace(
    call_anchor,
    """	if (should_fail_bio(bio))
		goto end_io;
	if (unlikely(pguard_block_bio(bio))) {
		status = BLK_STS_PROTECTION;
		goto end_io;
	}
	bio_check_ro(bio);
""",
    1,
)

path.write_text(text)
print("Applied PLK110 PGuard v1 to block/blk-core.c")
print("Protected: GPT guard bands + xbl/xbl_config/abl/uefi/uefisecapp/efisp (+ _a/_b).")
