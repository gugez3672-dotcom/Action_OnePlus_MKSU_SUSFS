"""Add only ReSukiSU/SUSFS feature deltas on top of the verified PLK110 A67 stock GKI."""
from pathlib import Path
import subprocess

kp = Path("kernel_workspace/kernel_platform")
ksu = kp / "KernelSU"

# ReSukiSU's Kbuild derives version metadata through git. Kleaf/Bazel sandboxes
# do not reliably expose the sibling repository's .git directory, so freeze the
# metadata from the pinned commit before entering Bazel.
commit = subprocess.check_output(
    ["git", "-C", str(ksu), "rev-parse", "--short=8", "HEAD"], text=True
).strip()
count = int(subprocess.check_output(
    ["git", "-C", str(ksu), "rev-list", "--count", "HEAD"], text=True
).strip())
version = 30700 + count

STRICT_MANAGER_PACKAGE = "com.daily.notes"
STRICT_MANAGER_APK_SHA256 = "346f9be72eca3a574986ddf0ee40294ede2c6146d024d1c44e8e860d4d5a6fd2"

kbuild = ksu / "kernel/Kbuild"
text = kbuild.read_text()
start = text.index("GIT_BIN :=")
end = text.index("KERNEL_VERSION :=", start)
replacement = (
    "# Fixed from the pinned ReSukiSU commit for hermetic Kleaf builds.\n"
    "# Keep KSU_SRC inside the kernel source tree so ReSukiSU helper includes\n"
    "# resolve correctly inside Bazel/Kleaf's sandbox.\n"
    "KSU_SRC := $(srctree)/drivers/kernelsu\n"
    f"KSU_VERSION := {version}\n"
    f"KSU_VERSION_FULL := ReSukiSU-{commit}@PLK110-A67\n\n"
    f"KSU_MANAGER_PACKAGE := {STRICT_MANAGER_PACKAGE}\n\n"
    f"KSU_MANAGER_APK_SHA256 := {STRICT_MANAGER_APK_SHA256}\n"
    f"ccflags-y += -DKSU_MANAGER_APK_SHA256=\\\"{STRICT_MANAGER_APK_SHA256}\\\"\n\n"
    "$(info -- $(REPO_NAME) version code: $(KSU_VERSION))\n"
    "$(info -- $(REPO_NAME) version name: $(KSU_VERSION_FULL))\n\n"
    "ccflags-y += -DKSU_VERSION=$(KSU_VERSION)\n"
    "ccflags-y += -DKSU_VERSION_FULL=\\\"$(KSU_VERSION_FULL)\\\"\n\n"
)
kbuild.write_text(text[:start] + replacement + text[end:])

# Strict manager identity: accept only the pinned ReSukiSU signing certificate,
# require the exact manager package, and remove the dynamic-manager fallback.
apk_sign = ksu / "kernel/manager/apk_sign.c"
text = apk_sign.read_text()

keys_start = text.index("static apk_sign_key_t apk_sign_keys[] = {")
keys_end = text.index("\n};", keys_start) + len("\n};")
strict_keys = """static apk_sign_key_t apk_sign_keys[] = {
    { 878, "06de283eff2a368fa627b9cc10a1c313ec752d05f16184d4764a6b09c4854df9" }, /* final Daily Notes only */
};"""
text = text[:keys_start] + strict_keys + text[keys_end:]

dyn_start = text.index("    if (!signature_valid && ksu_is_dynamic_manager_enabled()) {")
dyn_end = text.index("    return signature_valid;", dyn_start)
text = (
    text[:dyn_start]
    + "    /* Strict-manager build: dynamic manager signatures are intentionally disabled. */\n"
    + text[dyn_end:]
)
apk_sign.write_text(text)

assert "EXPECTED_SIZE_OFFICIAL" not in text[keys_start:keys_start + len(strict_keys) + 64]
assert "ksu_is_dynamic_manager_enabled()" not in text

# Final identity layer: hash the exact installed base.apk bytes. Because package
# filtering runs before signature/hash verification, this cost is paid only for
# the one pinned manager package, not for every installed application.
hash_anchor = "static bool read_exact(struct file *fp, void *buffer, size_t size, loff_t *pos, loff_t end)\n"
if text.count(hash_anchor) != 1:
    raise SystemExit("unexpected apk_sign read_exact anchor")
hash_helper = r'''#ifdef KSU_MANAGER_APK_SHA256
static bool check_apk_file_sha256(const char *path)
{
    struct file *fp;
    struct crypto_shash *alg;
    struct sdesc *sdesc;
    unsigned char *buf = NULL;
    unsigned char digest[SHA256_DIGEST_SIZE];
    char hash_str[SHA256_DIGEST_SIZE * 2 + 1];
    loff_t pos = 0;
    ssize_t n;
    bool ok = false;
    int ret;

    fp = filp_open(path, O_RDONLY, 0);
    if (IS_ERR(fp))
        return false;
    fp->f_mode |= FMODE_NONOTIFY;

    alg = crypto_alloc_shash("sha256", 0, 0);
    if (IS_ERR(alg))
        goto out_file;

    sdesc = init_sdesc(alg);
    if (IS_ERR(sdesc))
        goto out_alg;

    buf = kmalloc(4096, GFP_KERNEL);
    if (!buf)
        goto out_desc;

    ret = crypto_shash_init(&sdesc->shash);
    if (ret)
        goto out;

    while ((n = ksu_kernel_read_compat(fp, buf, 4096, &pos)) > 0) {
        ret = crypto_shash_update(&sdesc->shash, buf, n);
        if (ret)
            goto out;
    }
    if (n < 0)
        goto out;

    ret = crypto_shash_final(&sdesc->shash, digest);
    if (ret)
        goto out;

    bin2hex(hash_str, digest, SHA256_DIGEST_SIZE);
    hash_str[SHA256_DIGEST_SIZE * 2] = '\0';
    ok = strcmp(hash_str, KSU_MANAGER_APK_SHA256) == 0;

out:
    kfree(buf);
out_desc:
    kfree(sdesc);
out_alg:
    crypto_free_shash(alg);
out_file:
    filp_close(fp, NULL);
    return ok;
}
#endif

'''
text = text.replace(hash_anchor, hash_helper + hash_anchor, 1)

manager_return = "    return check_v2_signature(path, signature_index);\n"
if text.count(manager_return) != 1:
    raise SystemExit("unexpected is_manager_apk return")
text = text.replace(
    manager_return,
    """    if (!check_v2_signature(path, signature_index))
        return false;
#ifdef KSU_MANAGER_APK_SHA256
    if (!check_apk_file_sha256(path))
        return false;
#endif
    return true;
""",
    1,
)
apk_sign.write_text(text)

assert "KSU_MANAGER_APK_SHA256" in text
assert "check_apk_file_sha256" in text

# Do not hand a KernelSU driver fd to arbitrary apps that know the reboot magic.
# The real manager is already identified by throne_tracker and receives its fd
# through the manager setuid path; root/ksud remains allowed.
supercall = ksu / "kernel/supercall/supercall.c"
text = supercall.read_text()
include_anchor = '#include "klog.h" // IWYU pragma: keep\n'
if include_anchor not in text:
    raise SystemExit("unexpected supercall include layout")
text = text.replace(
    include_anchor,
    include_anchor + '#include "manager/manager_identity.h"\n',
    1,
)
fd_anchor = """    if (magic2 == KSU_INSTALL_MAGIC2) {
        int fd = ksu_install_fd();
"""
if text.count(fd_anchor) != 1:
    raise SystemExit("unexpected KSU fd install block")
text = text.replace(
    fd_anchor,
    """    if (magic2 == KSU_INSTALL_MAGIC2) {
        if (ksu_get_uid_t(current_uid()) != 0 && !is_manager()) {
            /* Swallow the KSU magic without exposing a driver fd. */
            return 0;
        }
        int fd = ksu_install_fd();
""",
    1,
)
supercall.write_text(text)

# Even if an fd is somehow inherited/passed, do not expose basic KSU state to
# an unrecognized app. This makes foreign managers behave as if KSU is absent.
dispatch = ksu / "kernel/supercall/dispatch.c"
text = dispatch.read_text()
strict_ioctl_perms = {
    '.cmd = KSU_IOCTL_GET_INFO,': 1,
    '.cmd = KSU_IOCTL_GET_INFO_LEGACY,': 1,
    '.cmd = KSU_IOCTL_CHECK_SAFEMODE,': 1,
    '.cmd = KSU_IOCTL_GET_FULL_VERSION,': 1,
}
for marker, expected in strict_ioctl_perms.items():
    start = text.index(marker)
    end = text.index("    },", start)
    block = text[start:end]
    if block.count(".perm_check = always_allow") != expected:
        raise SystemExit(f"unexpected permission block for {marker}")
    block = block.replace(".perm_check = always_allow", ".perm_check = manager_or_root")
    block = block.replace(".perm_check = manager_or_root ", ".perm_check = manager_or_root")
    text = text[:start] + block + text[end:]
dispatch.write_text(text)

assert 'if (ksu_get_uid_t(current_uid()) != 0 && !is_manager())' in supercall.read_text()
for marker in strict_ioctl_perms:
    start = text.index(marker)
    end = text.index("    },", start)
    assert ".perm_check = manager_or_root" in text[start:end]

fragment = kp / "common/arch/arm64/configs/plk110_resukisu.fragment"
fragment.write_text(
    Path("baselines/PLK110_16.0.8.302_expected_resukisu_susfs.config.additions").read_text()
)

path = kp / "common/BUILD.bazel"
text = path.read_text()
anchor = 'post_defconfig_fragments = ["arch/arm64/configs/plk110_stock.fragment"],'
assert text.count(anchor) == 1, "unexpected stock post_defconfig_fragments"
text = text.replace(
    anchor,
    'post_defconfig_fragments = [\n'
    '        "arch/arm64/configs/plk110_stock.fragment",\n'
    '        "arch/arm64/configs/plk110_resukisu.fragment",\n'
    '    ],',
    1,
)
path.write_text(text)
print(f"Pinned ReSukiSU metadata: version={version}, commit={commit}")
print(f"Strict manager package: {STRICT_MANAGER_PACKAGE}; only custom certificate accepted; dynamic manager disabled.")
print(f"Exact manager APK SHA-256: {STRICT_MANAGER_APK_SHA256}")
print("Strict manager I/O: foreign apps cannot obtain the KSU driver fd or read KSU info/version ioctls.")
print("Added ReSukiSU/SUSFS as a post-defconfig fragment; stock gki_defconfig remains untouched.")
