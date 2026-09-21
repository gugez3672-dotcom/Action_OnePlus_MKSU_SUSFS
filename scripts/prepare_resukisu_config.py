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
STRICT_MANAGER_CERT_SIZE = 890
STRICT_MANAGER_CERT_SHA256 = "7b6fcd9e7f440833ee8a5a3860f3ff5b7b367a0dabb36c1d5f0fd52064bf283e"

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
    "$(info -- $(REPO_NAME) version code: $(KSU_VERSION))\n"
    "$(info -- $(REPO_NAME) version name: $(KSU_VERSION_FULL))\n\n"
    "ccflags-y += -DKSU_VERSION=$(KSU_VERSION)\n"
    "ccflags-y += -DKSU_VERSION_FULL=\\\"$(KSU_VERSION_FULL)\\\"\n\n"
)
kbuild.write_text(text[:start] + replacement + text[end:])

# Long-term strict manager identity: accept only the fixed Daily Notes package
# plus the fixed private signing certificate. APK file bytes may change across
# legitimate UI/icon updates without requiring a kernel rebuild.
apk_sign = ksu / "kernel/manager/apk_sign.c"
text = apk_sign.read_text()

keys_start = text.index("static apk_sign_key_t apk_sign_keys[] = {")
keys_end = text.index("\n};", keys_start) + len("\n};")
strict_keys = f"""static apk_sign_key_t apk_sign_keys[] = {{
    {{ {STRICT_MANAGER_CERT_SIZE}, "{STRICT_MANAGER_CERT_SHA256}" }}, /* Daily Notes fixed signer */
}};"""
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

# No exact-APK hash gate here by design. Package + certificate are the durable identity.\n\n# Do not hand a KernelSU driver fd to arbitrary apps that know the reboot magic.
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
print(f"Strict manager package: {STRICT_MANAGER_PACKAGE}; dynamic manager disabled.")
print(f"Fixed manager signer: size={STRICT_MANAGER_CERT_SIZE}, sha256={STRICT_MANAGER_CERT_SHA256}")
print("Exact APK SHA-256 gate: disabled by design; signed manager updates remain accepted.")
print("Strict manager I/O: foreign apps cannot obtain the KSU driver fd or read KSU info/version ioctls.")
print("Added ReSukiSU/SUSFS as a post-defconfig fragment; stock gki_defconfig remains untouched.")
