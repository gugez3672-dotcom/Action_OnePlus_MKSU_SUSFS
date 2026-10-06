#!/usr/bin/env python3
from pathlib import Path
import hashlib

BASELINE = Path("baselines/PLK110_16.0.8.302_stock.config")
COMMON = Path("kernel_workspace/kernel_platform/common")
PUBLIC = COMMON / "arch/arm64/configs/plk110_a67_stock_ikconfig"
MAKEFILE = COMMON / "kernel/Makefile"

EXPECTED_SHA256 = "e239b50cb4c660493edfdc2ae4908b56cf5cae1e826f71f637da85e4aea3ecd0"

data = BASELINE.read_bytes()
actual = hashlib.sha256(data).hexdigest()
if actual != EXPECTED_SHA256:
    raise SystemExit(f"stock config SHA256 drift: {actual} != {EXPECTED_SHA256}")

text = data.decode()
required = ("CONFIG_IKCONFIG=y\n", "CONFIG_IKCONFIG_PROC=y\n")
for item in required:
    if item not in text:
        raise SystemExit(f"stock config missing required line: {item.strip()}")

for forbidden in (
    "CONFIG_KSU=y",
    "CONFIG_KSU_SUSFS=y",
    "CONFIG_PLK110_PARTITION_GUARD=y",
    "CONFIG_KSU_FULL_NAME_FORMAT=",
):
    if forbidden in text:
        raise SystemExit(f"stock public IKCONFIG unexpectedly contains root/PGuard option: {forbidden}")

PUBLIC.write_bytes(data)

make = MAKEFILE.read_text()
old = "$(obj)/config_data: $(KCONFIG_CONFIG) FORCE"
new = "$(obj)/config_data: arch/arm64/configs/plk110_a67_stock_ikconfig FORCE"
if make.count(old) != 1:
    raise SystemExit(f"kernel/Makefile IKCONFIG rule preimage count != 1: {make.count(old)}")
if new in make:
    raise SystemExit("kernel/Makefile public IKCONFIG rule already modified")
MAKEFILE.write_text(make.replace(old, new, 1))

# The build's real KCONFIG_CONFIG is deliberately untouched. Only the embedded
# IKCONFIG source consumed by kernel/configs.c is redirected to the exact stock
# A67 config, preserving /proc/config.gz while keeping compiled ReSukiSU/SUSFS/PGuard.
post = MAKEFILE.read_text()
if post.count(new) != 1 or old in post:
    raise SystemExit("public IKCONFIG redirection postcondition failed")

print(f"Prepared stock public IKCONFIG: {PUBLIC} sha256={actual}")
