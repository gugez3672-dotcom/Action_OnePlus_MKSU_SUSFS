# Original PLK110 A.67 module signing certificate

The adjacent PEM contains only the original public X.509 certificate, extracted
from the backed-up stock boot Image. No private signing key is present.

- Firmware: `PLK110_16.0.8.302(CN01)`
- Stock boot SHA256 (also confirmed against live boot_a):
  `7a52a39773e918d0848dad2d764ca2c9467158a2b41590450a3974bb3379647e`
- Stock Image SHA256:
  `8820d79f4566baeb439162597ba0c852dff52a9a2b658ea25e6a1b3dd09c1cf1`
- DER certificate SHA256:
  `f28dbcc60085b21a3cff1342482897fa640b468847473147834f26c4feb2df43`
- Certificate serial: `6e2dd27b61c8671d2c2afb38e907fe98dc8f0230`

Offline CMS signature verification: all 103 signed original module files verify
with this certificate. The other 915 captured module files are unsigned; the
1018 total includes copies shared by vendor_boot and vendor_dlkm.

The build keeps MODULE_SIG, MODULE_SIG_ALL, MODULE_SIG_PROTECT and
TRIM_UNUSED_KSYMS enabled. A standard post-defconfig fragment adds this original
public certificate to SYSTEM_TRUSTED_KEYS. Final verification checks its presence
inside the Image's actual system_certificate_list, located using System.map.
This restores original module signer trust without requiring the original
private key. It does not prove that a newly built Image boots on the device.
