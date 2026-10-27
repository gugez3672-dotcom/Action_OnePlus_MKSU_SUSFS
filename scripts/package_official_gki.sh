#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json
from pathlib import Path
for name in ('VERDICT.json', 'OFFICIAL_IMAGE_GATE.json'):
    assert json.loads((Path('artifacts') / name).read_text())['passed'] is True, name
PY

git clone --filter=blob:none --no-checkout --depth=1 --branch master \
  https://github.com/Numbersf/AnyKernel3.git AnyKernelSource
git -C AnyKernelSource fetch --depth=1 origin "$ANYKERNEL_COMMIT"
git -C AnyKernelSource checkout --detach "$ANYKERNEL_COMMIT"
test "$(git -C AnyKernelSource rev-parse HEAD)" = "$ANYKERNEL_COMMIT"
mkdir AnyKernel3
git -C AnyKernelSource archive HEAD | tar -x -C AnyKernel3
cp artifacts/Image AnyKernel3/Image
sed -i 's/^kernel.string=.*/kernel.string=PLK110 A67 KernelSU + SUSFS/' AnyKernel3/anykernel.sh
sed -i 's/^do.devicecheck=.*/do.devicecheck=1/' AnyKernel3/anykernel.sh
sed -i 's/^device.name1=.*/device.name1=PLK110/' AnyKernel3/anykernel.sh
sed -i 's/^device.name2=.*/device.name2=OP60FFL1/' AnyKernel3/anykernel.sh
sed -i 's/^PATCH_VBMETA_FLAG=.*/PATCH_VBMETA_FLAG=0/' AnyKernel3/anykernel.sh
grep -qx 'BLOCK=boot' AnyKernel3/anykernel.sh
grep -qx 'IS_SLOT_DEVICE=auto' AnyKernel3/anykernel.sh
grep -qx 'PATCH_VBMETA_FLAG=0' AnyKernel3/anykernel.sh
grep -qx 'do.devicecheck=1' AnyKernel3/anykernel.sh
grep -qx 'do.modules=0' AnyKernel3/anykernel.sh
! grep -Eq '^[[:space:]]*(patch_fstab|flash_generic|write_boot.*vendor)' AnyKernel3/anykernel.sh
for forbidden in \
  dtb dtb.img dtbo dtbo.img recovery_dtbo recovery_dtbo.img \
  vendor_boot vendor_boot.img init_boot init_boot.img vbmeta vbmeta.img \
  vendor_kernel_boot vendor_kernel_boot.img vendor_dlkm vendor_dlkm.img \
  system_dlkm system_dlkm.img recovery recovery.img abl abl.img \
  vendor_ramdisk vendor_patch modules; do
  test ! -e "AnyKernel3/$forbidden"
done
test -z "$(find AnyKernel3 -type f \( -iname '*.zip' -o -iname '*.apk' -o -iname '*.img' \) -print -quit)"
run_number="${GITHUB_RUN_NUMBER:?Actions run number is required for the package label}"
cp inputs.lock.json artifacts/inputs.lock.json
cp AnyKernel3/anykernel.sh artifacts/packaged_anykernel.sh
(
  cd AnyKernel3
  zip -r9 "../artifacts/PLK110_A67_K${run_number}_KernelSU_SUSFS.zip" .
)
python3 - <<'PY'
import hashlib
import json
import os
from pathlib import Path
lock = json.loads(Path('inputs.lock.json').read_text())
record = {
    'K': int(os.environ['GITHUB_RUN_NUMBER']), 'definition_commit': os.environ['GITHUB_SHA'],
    'image_sha256': hashlib.sha256(Path('artifacts/Image').read_bytes()).hexdigest(),
    'kernelsu': lock['kernelsu'], 'susfs': lock['susfs'], 'anykernel': lock['anykernel'],
    'pguard': False, 'embedded_k_number': False,
    'on_device': 'UNTESTED; not installed or booted by CI',
}
Path('artifacts/BUILD_RECORD.json').write_text(json.dumps(record, indent=2) + '\n')
PY
cat > artifacts/READ_ME.txt <<'EOF'
Target: OnePlus 15 PLK110, PLK110_16.0.8.302(CN01), A67, stock scheduler.
Official tiann KernelSU + official simonpunk SUSFS; exact inputs in inputs.lock.json.
K is an external Actions/package label. Image identity is recorded by SHA256.
The Image uses the stock banner and stock public IKCONFIG. No embedded K suffix.
This version has NO PGuard partition-write protection.
Checks cover config deltas, stock module symbol CRCs, signer trust and source invariants.
The AnyKernel package replaces the boot kernel Image only and contains no vendor modules,
device trees, init_boot, vendor_boot, vbmeta, vendor_dlkm or system_dlkm images.
CI success does not establish device boot, root, module compatibility or detection results.
Do not flash without verified K32/boot and /data/adb backups and the planned USB recovery path.
EOF
