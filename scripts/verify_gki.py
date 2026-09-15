"""Validate the actual Image, never a config from a different Bazel target."""
import argparse
import gzip
import hashlib
import json
import re
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--artifacts', type=Path, default=Path('artifacts'))
parser.add_argument('--baseline', type=Path, default=Path('baselines/PLK110_16.0.8.302_stock.config'))
parser.add_argument('--abi', type=Path, default=Path('baselines/PLK110_A67_module_abi.json'))
parser.add_argument('--release', default='6.12.23-android16-5-gb2a876903b49-ab14541642-4k')
args = parser.parse_args()
out = args.artifacts

def config(text):
    result = {}
    for line in text.splitlines():
        if m := re.fullmatch(r'(CONFIG_\w+)=(.*)', line):
            result[m[1]] = m[2]
        elif m := re.fullmatch(r'# (CONFIG_\w+) is not set', line):
            result[m[1]] = 'n'
    return result

data = (out / 'Image').read_bytes()
start, end = data.find(b'IKCFG_ST'), data.find(b'IKCFG_ED')
if start < 0 or end <= start:
    raise SystemExit('Image has no extractable IKCONFIG; cannot verify it')
actual_bytes = gzip.decompress(data[start + 8:end])
(out / 'image.config').write_bytes(actual_bytes)
actual = config(actual_bytes.decode())
stock = config(args.baseline.read_text())
ignored = {'CONFIG_CC_VERSION_TEXT', 'CONFIG_RUSTC_VERSION_TEXT', 'CONFIG_BINDGEN_VERSION_TEXT'}
delta = {k: {'stock': stock.get(k, 'n'), 'image': actual.get(k, 'n')}
         for k in sorted(stock.keys() | actual.keys())
         if stock.get(k, 'n') != actual.get(k, 'n')}
functional = {k: v for k, v in delta.items() if k not in ignored}
(out / 'config_delta.json').write_text(json.dumps(delta, indent=2) + '\n')
preflight = config((out / 'gki_preflight.config').read_text())
preflight_delta = {k: [preflight.get(k, 'n'), actual.get(k, 'n')]
                   for k in sorted(preflight.keys() | actual.keys())
                   if preflight.get(k, 'n') != actual.get(k, 'n')}
banner_match = re.search(rb'Linux version [^\x00\n]+', data)
banner = banner_match[0].decode(errors='replace') if banner_match else ''
(out / 'KERNEL_BANNER.txt').write_text(banner + '\n')
release = banner.split(' ')[2] if banner else ''
abi = json.loads(args.abi.read_text())
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
passed = (not functional and not preflight_delta and not missing and not mismatches
          and not root_symbols and release == args.release)
report = {'passed': passed, 'scope': 'Offline stock kernel config and module CRC verification; boot untested.',
          'release': release, 'expected_release': args.release,
          'image_sha256': hashlib.sha256(data).hexdigest(),
          'functional_config_differences': functional,
          'preflight_vs_image_config_differences': preflight_delta,
          'root_symbols': root_symbols, 'module_abi': abi_report,
          'toolchain': {k: actual.get(k) for k in sorted(ignored)}}
(out / 'VERDICT.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
raise SystemExit(0 if passed else 1)
