"""Preserve trust in the public key that signs this phone's stock GKI modules."""
import hashlib
import ssl
from pathlib import Path
from config_policy import STOCK_CERT_SHA256

root = Path('kernel_workspace/kernel_platform/common')
pem = Path('baselines/PLK110_A67_stock_module_signer.pem').read_text()
der = ssl.PEM_cert_to_DER_cert(pem)
assert hashlib.sha256(der).hexdigest() == STOCK_CERT_SHA256, 'wrong stock certificate'
(root / 'certs/plk110_stock.pem').write_text(pem)
(root / 'arch/arm64/configs/plk110_stock.fragment').write_text(
    'CONFIG_SYSTEM_TRUSTED_KEYS="certs/plk110_stock.pem"\n')
path = root / 'BUILD.bazel'
text = path.read_text()
anchor = 'common_kernel(\n    name = "kernel_aarch64",\n'
assert text.count(anchor) == 1, 'unexpected kernel_aarch64 declaration'
text = text.replace(anchor, anchor +
    '    post_defconfig_fragments = ["arch/arm64/configs/plk110_stock.fragment"],\n', 1)
path.write_text(text)
print('Added original public certificate through a post-defconfig fragment; normal checks retained.')
