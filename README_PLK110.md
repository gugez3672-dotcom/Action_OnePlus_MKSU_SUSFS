# PLK110 SUSFS build baseline

This repository is intentionally fixed to one device and one firmware baseline:

- Device: OnePlus 15 / `PLK110`
- Current firmware: `PLK110_16.0.3.505(CN01)`
- Current stock GKI identifier: `6.12.23-android16-5-g188c695beb6d-ab14367805-4k`
- Root manager: SukiSU Ultra `4.2.0`
- Target: SukiSU builtin `4.2.0` + SUSFS `2.3.0`

The workflow uses the exact `g188c695beb6d` common-kernel commit reported by the
running phone. OnePlus has not published a `.505`-named vendor-source snapshot,
so the SoC and modules/device-tree repositories are pinned to the closest public
CN snapshot, `PLK110_16.0.3.503(CN01)`. This distinction is recorded rather than
claiming an unavailable exact `.505` source match.

The workflow is manual-only and pins every security-sensitive source used by the
kernel integration. Patch failures are fatal. KPM, extra ZRAM algorithms,
third-party hide patches, debug mode, and SUSFS kernel logging are disabled.

The kernel zip and the stable SUSFS userspace module are packaged separately.
Do not install the userspace module until the new kernel has completed a clean
boot and its effective SUSFS feature list has been verified.

Important: the phone currently uses SukiSU in LKM mode through `init_boot_a`.
That LKM must not be left active when switching to the builtin SukiSU kernel.
The transition and recovery commands are deliberately not automated here.
