#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json
from pathlib import Path
assert json.loads(Path('artifacts/VERDICT.json').read_text())['passed'] is True
PY
git clone --filter=blob:none --no-checkout --depth=1 --branch master \
  https://github.com/Numbersf/AnyKernel3.git AnyKernelSource
git -C AnyKernelSource fetch --depth=1 origin "$ANYKERNEL_COMMIT"
git -C AnyKernelSource checkout --detach "$ANYKERNEL_COMMIT"
test "$(git -C AnyKernelSource rev-parse HEAD)" = "$ANYKERNEL_COMMIT"
mkdir AnyKernel3
git -C AnyKernelSource archive HEAD | tar -x -C AnyKernel3
cp artifacts/Image AnyKernel3/Image
sed -i 's/^kernel.string=.*/kernel.string=PLK110 A67 SukiSU 4.2 + SUSFS 2.3/' AnyKernel3/anykernel.sh
sed -i 's/^do.devicecheck=.*/do.devicecheck=1/' AnyKernel3/anykernel.sh
sed -i 's/^device.name1=.*/device.name1=PLK110/' AnyKernel3/anykernel.sh
sed -i 's/^device.name2=.*/device.name2=OP60FFL1/' AnyKernel3/anykernel.sh
sed -i 's/^PATCH_VBMETA_FLAG=.*/PATCH_VBMETA_FLAG=0/' AnyKernel3/anykernel.sh
grep -qx 'BLOCK=boot' AnyKernel3/anykernel.sh
grep -qx 'IS_SLOT_DEVICE=auto' AnyKernel3/anykernel.sh
grep -qx 'PATCH_VBMETA_FLAG=0' AnyKernel3/anykernel.sh
grep -qx 'do.modules=0' AnyKernel3/anykernel.sh
! grep -Eq '^[[:space:]]*(patch_fstab|flash_generic|write_boot.*vendor)' AnyKernel3/anykernel.sh
for forbidden in \
  dtb dtb.img dtbo dtbo.img recovery_dtbo recovery_dtbo.img \
  vendor_boot vendor_boot.img init_boot init_boot.img vbmeta vbmeta.img \
  vendor_kernel_boot vendor_kernel_boot.img \
  vendor_dlkm vendor_dlkm.img system_dlkm system_dlkm.img \
  recovery recovery.img abl abl.img vendor_ramdisk vendor_patch modules; do
  test ! -e "AnyKernel3/$forbidden"
done
! find AnyKernel3 -iname '*.zip' -print -quit | grep -q .
(
  cd AnyKernel3
  zip -r9 ../artifacts/PLK110_A67_SukiSU-4.2_SUSFS-2.3_NoKPM.zip .
)
cp AnyKernel3/anykernel.sh artifacts/packaged_anykernel.sh
printf 'anykernel=%s\nverified_stock_run=%s\nverified_stock_commit=%s\n' \
  "$ANYKERNEL_COMMIT" "$VERIFIED_STOCK_RUN" "$VERIFIED_STOCK_COMMIT" >> artifacts/SOURCE_PINS.txt
cat > artifacts/READ_ME.txt <<'EOF'
Target: OnePlus 15 PLK110, PLK110_16.0.8.302(CN01), A67 kernel 6.12.23.
SukiSU 4.2 builtin + SUSFS 2.3; KPM, adb root and SUSFS debug logging disabled.
Offline Image configuration, stock module CRCs and original module signer trust
have passed verification. See VERDICT.json and SOURCE_PINS.txt for evidence.
The AnyKernel package replaces only the boot kernel and contains no modules,
device trees, init_boot or vendor_boot images. Device boot has NOT been tested.
The phone baseline uses SukiSU LKM in init_boot. Any future transition from LKM
to builtin needs its own boot/recovery plan; this build does not perform it.
EOF
