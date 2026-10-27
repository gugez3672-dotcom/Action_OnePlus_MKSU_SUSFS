"""Verify the fixed kernel identity against the public certificate in a V2 APK.

Reads an existing signed APK only. Does not read keys, sign, build or install.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct


def take(data, offset):
    if offset + 4 > len(data):
        raise ValueError('truncated length')
    length = struct.unpack_from('<I', data, offset)[0]
    end = offset + 4 + length
    if end > len(data):
        raise ValueError('truncated value')
    return data[offset + 4:end], end


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--apk', type=Path, required=True)
    cli.add_argument('--report', type=Path)
    args = cli.parse_args()
    data = args.apk.read_bytes()
    eocd = data.rfind(b'PK\x05\x06')
    assert eocd >= 0
    central = struct.unpack_from('<I', data, eocd + 16)[0]
    assert data[central-16:central] == b'APK Sig Block 42'
    length = struct.unpack_from('<Q', data, central - 24)[0]
    start = central - length - 8
    assert struct.unpack_from('<Q', data, start)[0] == length
    position = start + 8
    values = []
    while position < central - 24:
        size, identifier = struct.unpack_from('<QI', data, position)
        assert size >= 4 and position + 8 + size <= central - 24
        if identifier == 0x7109871a:
            values.append(data[position+12:position+8+size])
        position += 8 + size
    assert len(values) == 1
    signers, end = take(values[0], 0)
    assert end == len(values[0])
    signer, end = take(signers, 0)
    assert end == len(signers), 'multiple signers require a separate gate review'
    signed, _ = take(signer, 0)
    _, offset = take(signed, 0)  # Digests.
    certificates, _ = take(signed, offset)
    certificate, end = take(certificates, 0)
    assert end == len(certificates), 'unexpected certificate chain'
    identity = json.loads(Path('inputs.lock.json').read_text())['manager']
    digest = hashlib.sha256(certificate).hexdigest()
    assert len(certificate) == identity['certificate_size'], 'kernel certificate size mismatch'
    assert digest == identity['certificate_sha256'], 'kernel certificate SHA256 mismatch'
    result = {'passed': True, 'certificate_size': len(certificate), 'certificate_sha256': digest,
              'apk_sha256': hashlib.sha256(data).hexdigest(),
              'scope': 'Public certificate extraction; this does not replace apksigner signature verification.'}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + '\n')
    print('PASS: existing manager V2 certificate matches the kernel size/hash parameters.')


if __name__ == '__main__':
    main()
