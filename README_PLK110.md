# PLK110 SUSFS build baseline

This repository is intentionally fixed to one device and one firmware baseline:

- Device: OnePlus 15 / `PLK110`
- Current firmware: `PLK110_16.0.8.302(CN01)`
- Current stock GKI identifier: `6.12.23-android16-5-gb2a876903b49-ab14541642-4k`
- Root manager: SukiSU Ultra `4.2.0`
- Target: SukiSU builtin `4.2.0` + SUSFS `2.3.0`

The workflow uses the exact `gb2a876903b49` common-kernel commit reported by the
running phone. The SoC and modules/device-tree repositories are pinned to the
official `PLK110_16.0.8.302(CN01)` synchronization commits. The running phone's
`/proc/config.gz` is checked in as the stock reference, and changes to scheduling,
CPU frequency/idle, ZRAM, LTO/CFI, module ABI/signing, preemption, or debug
hardening fail the build.

The workflow is manual-only and pins every security-sensitive source used by the
kernel integration. Patch failures are fatal. KPM, extra ZRAM algorithms,
third-party hide patches, debug mode, and SUSFS kernel logging are disabled.
The stock `CONFIG_LTO_NONE=y` setting is retained.

Two obsolete Android test-suite prebuilts (`asuite` and `tradefed`) are removed
from the local manifest because CodeLinaro no longer publishes the referenced
branch. They are not kernel or device-driver build inputs.

The kernel zip and the stable SUSFS userspace module are packaged separately.
Do not install the userspace module until the new kernel has completed a clean
boot and its effective SUSFS feature list has been verified.

Important: the phone currently uses SukiSU in LKM mode through `init_boot_a`.
That LKM must not be left active when switching to the builtin SukiSU kernel.
The transition and recovery commands are deliberately not automated here.
