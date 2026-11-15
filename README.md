# PLK110 A67 kernel

- `inputs.lock.json`: pinned sources.
- `.github/workflows/Build-ReSukiSU-StockSched.yml`: manual build (`review_ack=reviewed`, `k_number=<K>`).
- `scripts/`, `patches/`, `baselines/`: build steps, patches and stock references.
- `scripts/archive_build_inputs.py <SOURCE_MANIFEST.xml> <dir>`: archive all pinned inputs locally.

## K41 combination

K41 uses official KernelSU `64833c00` / 32730 with the verified SUSFS
`519c86c5` common implementation. The 519 KSU integration patch is rebased
explicitly in `patches/K41_SUSFS519_KSU64833.patch`, with its hash in the lock.
This is not the newer SUSFS SELinux hash-table implementation.

- Retain K40's shared A67 parser and native five-attribute/setselfattr paths.
- Use upstream policy-object/generation/original-type checks inside that parser.
  Unknown native types still exit before any KSU type lookup; stale metadata
  returns EAGAIN instead of accepting a KSU-added type.
- Cover inode_setxattr at the native parse site, after RELABELFROM, preserving
  all native checks and the MAC_ADMIN force-parse path (upstream #3996 intent).
- Keep upstream policy generation tracking. For KSU policy updates only, filter
  application-owned SELinux netlink recipients while hiding and fake status are
  active. Stock notifications and system recipients retain normal delivery.
  This is a built-in A67 implementation of #3965's scope, not its dynamic hooks.
- Retain the earlier Claude draft's NOKPROBE_SYMBOL(do_execveat_common).
- Keep no PGuard and no changes to vendor modules, system services or phone state.

The rebased patch retains the 519 feature/selinux_hide.c on purpose: the native
overlay supplies xattr and notification handling. Non-SELinux upstream updates,
including file-wrapper reference balancing, remain in the new KSU source.
Conflicts in init/setuid/ksud integration retain SUSFS's built-in/manual paths;
rules.c keeps upstream sequence tracking plus the SUSFS batch-SID callback.

Verification includes strict source application, native permission-order checks,
20 executable assertions against the actual upstream type/epoch helper bodies,
and negative source regressions. Full kernel compilation and image/ABI gates run
only in GitHub Actions. Device boot, policy reload races, socket inheritance and
SELinux side-channel behavior still need device testing after artifact review.
