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
sed -i 's/^kernel.string=.*/kernel.string=PLK110 A67 ReSukiSU + SUSFS stock scheduler ABI/' AnyKernel3/anykernel.sh
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

(
  cd AnyKernel3
  zip -r9 ../artifacts/PLK110_A67_ReSukiSU_SUSFS_StockScheduler_NoKPM.zip .
)
cp AnyKernel3/anykernel.sh artifacts/packaged_anykernel.sh
printf 'anykernel=%s\nresukisu=%s\nsusfs4oki=%s\nverified_stock_run=%s\nverified_stock_commit=%s\n' \
  "$ANYKERNEL_COMMIT" "$RESUKISU_COMMIT" "$SUSFS4OKI_COMMIT" "$VERIFIED_STOCK_RUN" "$VERIFIED_STOCK_COMMIT" \
  >> artifacts/SOURCE_PINS.txt

cat > artifacts/READ_ME.txt <<'EOF'
Target: OnePlus 15 PLK110, PLK110_16.0.8.302(CN01), A67 kernel 6.12.23.
ReSukiSU + SUSFS; KPM, extra scheduler, ADIOS, Re-Kernel, BBR/Brutal,
Droidspaces, BBG and extra network patches are intentionally excluded.

The build starts from the exact verified A67 OnePlus common/module source pins.
Offline validation requires:
1. actual Image config matches the running stock config except declared ReSukiSU/SUSFS deltas;
2. all captured stock vendor-module required symbol CRCs still match;
3. the original stock module signer certificate remains trusted;
4. CONFIG_SCHED_CLASS_EXT remains enabled.

The AnyKernel package replaces only the boot kernel Image and contains no
vendor modules, device trees, init_boot, vendor_boot, vendor_dlkm or system_dlkm.
Device boot and runtime Oplus/WALT module loading still require on-device verification.
EOF
