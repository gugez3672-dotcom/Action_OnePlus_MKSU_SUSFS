"""Validate the actual Image, never a config from a different Bazel target."""
import argparse
import gzip
import hashlib
import json
import re
import ssl
import struct
from pathlib import Path
from config_policy import config, compare, GENERATED, STOCK_CERT_SHA256

parser = argparse.ArgumentParser()
parser.add_argument('--artifacts', type=Path, default=Path('artifacts'))
parser.add_argument('--baseline', type=Path, default=Path('baselines/PLK110_16.0.8.302_stock.config'))
parser.add_argument('--abi', type=Path, default=Path('baselines/PLK110_A67_module_abi.json'))
parser.add_argument('--release', default='6.12.23-android16-5-gb2a876903b49-ab14541642-4k')
parser.add_argument('--preflight', action='store_true')
parser.add_argument('--additions', type=Path)
parser.add_argument('--certificate', type=Path, default=Path('baselines/PLK110_A67_stock_module_signer.pem'))
args = parser.parse_args()
out = args.artifacts

stock = config(args.baseline.read_text())
additions = config(args.additions.read_text()) if args.additions else {}
preflight = config((out / 'gki_preflight.config').read_text())
if args.preflight:
    delta, unexpected, unmet = compare(stock, preflight, additions)
    report = {'passed': not unexpected and not unmet, 'config_differences': delta,
              'unexpected_config_differences': unexpected, 'unmet_required_config': unmet}
    (out / 'PREFLIGHT_VERDICT.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['passed'] else 1)

data = (out / 'Image').read_bytes()
start, end = data.find(b'IKCFG_ST'), data.find(b'IKCFG_ED')
if start < 0 or end <= start:
    raise SystemExit('Image has no extractable IKCONFIG; cannot verify it')
actual_bytes = gzip.decompress(data[start + 8:end])
(out / 'image.config').write_bytes(actual_bytes)
actual = config(actual_bytes.decode())
# Unlike other generated metadata, the C compiler identity is part of the
# PLK110 A67 stock-reproduction target. It must match the captured stock config
# exactly; a different Android clang build number is a failed reproduction.
stock_cc = stock.get('CONFIG_CC_VERSION_TEXT')
actual_cc = actual.get('CONFIG_CC_VERSION_TEXT')
cc_exact = stock_cc == actual_cc and stock_cc is not None
delta, functional, unmet = compare(stock, actual, additions)
(out / 'config_delta.json').write_text(json.dumps(delta, indent=2) + '\n')
preflight_delta = {k: [preflight.get(k, 'n'), actual.get(k, 'n')]
                   for k in sorted(preflight.keys() | actual.keys())
                   if preflight.get(k, 'n') != actual.get(k, 'n')}
banner_match = re.search(rb'Linux version [^\x00\n]+', data)
banner = banner_match[0].decode(errors='replace') if banner_match else ''
(out / 'KERNEL_BANNER.txt').write_text(banner + '\n')
release = banner.split(' ')[2] if banner else ''
abi = json.loads(args.abi.read_text())
assert abi['config_sha256'] == hashlib.sha256(args.baseline.read_text().encode()).hexdigest(), 'ABI baseline firmware mismatch'
symvers = {}
for line in (out / 'Module.symvers').read_text().splitlines():
    fields = line.split()
    if len(fields) >= 3:
        symvers[fields[1]] = {'crc': f'0x{int(fields[0], 16):08x}', 'provider': fields[2]}
module_exports = set(abi['module_exports'])
missing, mismatches, matched, external = [], {}, [], []
for symbol, crcs in abi['required_symbol_crcs'].items():
    if symbol in symvers:
        if symvers[symbol]['crc'] not in crcs:
            mismatches[symbol] = {'phone': crcs, 'built': symvers[symbol]}
        else:
            matched.append(symbol)
    elif symbol in module_exports:
        external.append(symbol)
    else:
        missing.append(symbol)
abi_report = {'matched': len(matched), 'resolved_by_existing_modules': len(external),
              'missing': missing, 'crc_mismatches': mismatches,
              'phone_module_count': len(abi['modules'])}
(out / 'MODULE_ABI_REPORT.json').write_text(json.dumps(abi_report, indent=2) + '\n')
root_symbols = {k: v for k, v in actual.items()
                if re.match(r'CONFIG_(KSU|SUSFS|KPM)', k) and v != 'n'}
unexpected_root = {k: v for k, v in root_symbols.items() if additions.get(k) != v}
# Locate the live built-in trust table via System.map, not a byte match anywhere
# in the Image. ARM64 Image starts at _text; the list size is an unsigned long.
addresses = {}
for line in (out / 'System.map').read_text().splitlines():
    fields = line.split()
    if len(fields) == 3:
        addresses[fields[2]] = int(fields[0], 16)
base = addresses['_text']
cert_offset = addresses['system_certificate_list'] - base
size_offset = addresses['system_certificate_list_size'] - base
assert 0 <= size_offset <= len(data) - 8, 'invalid certificate size offset'
cert_size = struct.unpack_from('<Q', data, size_offset)[0]
assert 0 <= cert_offset <= cert_offset + cert_size <= len(data), 'invalid certificate table'
der = ssl.PEM_cert_to_DER_cert(args.certificate.read_text())
assert hashlib.sha256(der).hexdigest() == STOCK_CERT_SHA256, 'wrong baseline certificate'
trusted = der in data[cert_offset:cert_offset + cert_size]
trust_report = {'original_signer_sha256': STOCK_CERT_SHA256, 'present_in_builtin_trust_table': trusted,
                'table_offset': cert_offset, 'table_size': cert_size}
passed = (not functional and not unmet and not preflight_delta and not missing and not mismatches
          and not unexpected_root and trusted and release == args.release and cc_exact)
report = {'passed': passed, 'scope': 'Offline Image config, stock module CRC and signer trust verification; boot untested.',
          'release': release, 'expected_release': args.release,
          'image_sha256': hashlib.sha256(data).hexdigest(),
          'functional_config_differences': functional,
          'all_config_differences': delta, 'unmet_required_config': unmet,
          'preflight_vs_image_config_differences': preflight_delta,
          'root_symbols': root_symbols, 'module_abi': abi_report, 'stock_signer_trust': trust_report,
          'toolchain': {k: actual.get(k) for k in sorted(GENERATED)},
          'stock_cc_version_text': stock_cc, 'actual_cc_version_text': actual_cc,
          'cc_version_exact_stock_match': cc_exact}
(out / 'VERDICT.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
raise SystemExit(0 if passed else 1)
