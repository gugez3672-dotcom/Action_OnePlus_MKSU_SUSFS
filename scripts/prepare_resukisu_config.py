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

STRICT_MANAGER_PACKAGE = "com.resukisu.resukisu"

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

# Strict manager identity: accept only the pinned ReSukiSU signing certificate,
# require the exact manager package, and remove the dynamic-manager fallback.
apk_sign = ksu / "kernel/manager/apk_sign.c"
text = apk_sign.read_text()

keys_start = text.index("static apk_sign_key_t apk_sign_keys[] = {")
keys_end = text.index("\n};", keys_start) + len("\n};")
strict_keys = """static apk_sign_key_t apk_sign_keys[] = {
    { EXPECTED_SIZE_RESUKISU, EXPECTED_HASH_RESUKISU }, /* ReSukiSU/ReSukiSU only */
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
print(f"Strict manager package: {STRICT_MANAGER_PACKAGE}; only ReSukiSU certificate accepted; dynamic manager disabled.")
print("Added ReSukiSU/SUSFS as a post-defconfig fragment; stock gki_defconfig remains untouched.")
