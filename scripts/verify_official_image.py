"""Additional official-route artifact gates, after generic stock ABI verification."""
import json
from pathlib import Path
import re
from preinit_gate import verify_preinit

lock = json.loads(Path('inputs.lock.json').read_text())
out = Path('artifacts')
verdict = json.loads((out / 'VERDICT.json').read_text())
assert verdict['passed'] is True and verdict['exact_stock_banner_match'] is True
image = (out / 'Image').read_bytes()
symbols = (out / 'System.map').read_text()
config = (out / 'image.config').read_text()
preinit = verify_preinit(image, symbols, {name: (out / name).read_text(errors='replace')
                                        for name in ('preflight.log', 'build.log')})
for symbol in ('kernelsu_init', 'susfs_init', 'ksu_install_fd', 'ksu_install_su_fd'):
    assert re.search(r' [Tt] ' + symbol + r'$', symbols, re.M), symbol
for setting in ('CONFIG_KSU=y', 'CONFIG_KSU_SUSFS=y', 'CONFIG_SCHED_CLASS_EXT=y', 'CONFIG_MODVERSIONS=y'):
    assert setting in config.splitlines(), setting
assert not re.search(r'(?m)^CONFIG_(?:PLK110_PARTITION_GUARD|KPM)=y$', config)
assert 'plk110_pguard_' not in symbols and b'PLK110-PGuard' not in image
assert lock['manager']['package'].encode() in image
assert lock['manager']['certificate_sha256'].encode() in image
for wrong in (b'ReSukiSU-', b'BakaSU-', b'c371061b19d8c7d7d6133c6a9bafe198fa944e50c1b31c9d8daa8d7f1fc2d2d6'):
    assert wrong not in image, 'foreign manager/fork identity in Image'
assert re.search(r'__trace(?:iter|point)_android_vh_scx_restore_flags', (out / 'Module.symvers').read_text())
report = {'passed': True, 'kernelsu': lock['kernelsu'], 'susfs': lock['susfs'],
          'preinit': preinit,
          'pguard': False, 'embedded_k_number': False,
          'device_boot_and_module_loading': 'UNTESTED'}
(out / 'OFFICIAL_IMAGE_GATE.json').write_text(json.dumps(report, indent=2) + '\n')
print('PASS: official compiled symbols, private manager gate, stock ABI/banner and no PGuard.')
