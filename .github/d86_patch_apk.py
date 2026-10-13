#!/usr/bin/env python3
"""D86 binary hotfix preview; full D86 sources are archived separately."""
import hashlib, struct, sys, zipfile, zlib
from pathlib import Path
source=Path(sys.argv[1]); destination=Path(sys.argv[2])
EXPECTED="206f0cb6ec96376d37ec3aa3f68d8f0826b4b87ca8de2f9a73308155e43c6e95"
assert hashlib.sha256(source.read_bytes()).hexdigest()==EXPECTED
def dex_patch(blob, a, b):
    assert len(a)==len(b)
    d=bytearray(blob);count,off=struct.unpack_from("<II",d,0x38);hits=[]
    for i in range(count):
        p=struct.unpack_from("<I",d,off+i*4)[0]
        while True:
            n=d[p];p+=1
            if n<128:break
        e=d.index(0,p)
        if d[p:e]==a:hits.append((i,p))
    assert len(hits)==1,(a,hits)
    idx,pos=hits[0]
    uses=sum(d[j]==0x1a and struct.unpack_from("<H",d,j+2)[0]==idx for j in range(len(d)-4))
    assert uses==1,(a,uses)
    d[pos:pos+len(b)]=b
    d[12:32]=hashlib.sha1(d[32:]).digest()
    struct.pack_into("<I",d,8,zlib.adler32(d[12:])&0xffffffff)
    return bytes(d)
changes=[]
with zipfile.ZipFile(source) as src,zipfile.ZipFile(destination,"w") as dst:
    for f in src.infolist():
        name=f.filename
        if name=="META-INF/MANIFEST.MF" or (name.startswith("META-INF/") and name.upper().endswith((".SF",".RSA",".DSA",".EC"))):
            continue
        b=src.read(f)
        if name=="classes.dex":
            b=dex_patch(b,b"D1.0.85",b"D1.0.86");changes.append(name)
        elif name=="classes2.dex":
            b=dex_patch(b,b"-M",b"-p");changes.append(name)
        elif name=="AndroidManifest.xml":
            assert b.count("D1.0.85".encode("utf-16le"))==1
            assert b.count(struct.pack("<I",35185))==1
            b=b.replace("D1.0.85".encode("utf-16le"),"D1.0.86".encode("utf-16le"))
            b=b.replace(struct.pack("<I",35185),struct.pack("<I",35186));changes.append(name)
        elif name=="assets/dn-terminal/start-shell":
            assert b.count(b"trap '' HUP")==1
            b=b.replace(b"trap '' HUP",b"# allow SIGHUP");changes.append(name)
        elif name=="assets/dn-terminal/bashrc":
            assert b.count(b"    unset DN_SCRIPT dn_result")==1
            b=b.replace(b"    unset DN_SCRIPT dn_result",b'    exit "$dn_result"');changes.append(name)
        dst.writestr(f,b)
assert sorted(changes)==sorted(["classes.dex","classes2.dex","AndroidManifest.xml","assets/dn-terminal/start-shell","assets/dn-terminal/bashrc"])
with zipfile.ZipFile(destination) as z:assert z.testzip() is None
print("D86 preview patch targets verified:",changes)
