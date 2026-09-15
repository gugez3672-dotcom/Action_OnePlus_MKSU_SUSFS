"""Exact stock configuration policy shared by preflight and Image validation."""
import re

GENERATED = {'CONFIG_CC_VERSION_TEXT', 'CONFIG_RUSTC_VERSION_TEXT', 'CONFIG_BINDGEN_VERSION_TEXT'}
STOCK_CERT_SHA256 = 'f28dbcc60085b21a3cff1342482897fa640b468847473147834f26c4feb2df43'
TRUST_CONFIG = {'CONFIG_SYSTEM_TRUSTED_KEYS': '"certs/plk110_stock.pem"'}


def config(text):
    result = {}
    for line in text.splitlines():
        if m := re.fullmatch(r'(CONFIG_\w+)=(.*)', line):
            result[m[1]] = m[2]
        elif m := re.fullmatch(r'# (CONFIG_\w+) is not set', line):
            result[m[1]] = 'n'
    return result


def compare(stock, actual, additions=None):
    required = TRUST_CONFIG | (additions or {})
    delta = {k: {'stock': stock.get(k, 'n'), 'image': actual.get(k, 'n')}
             for k in sorted(stock.keys() | actual.keys())
             if stock.get(k, 'n') != actual.get(k, 'n')}
    unexpected = {k: v for k, v in delta.items()
                  if k not in GENERATED and (k not in required or v['image'] != required[k])}
    unmet = {k: {'expected': v, 'actual': actual.get(k, 'n')}
             for k, v in required.items() if actual.get(k, 'n') != v}
    return delta, unexpected, unmet
