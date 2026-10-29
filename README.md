# PLK110 A67 kernel

- `inputs.lock.json`: pinned sources.
- `.github/workflows/Build-ReSukiSU-StockSched.yml`: manual build (`review_ack=reviewed`, `k_number=<K>`).
- `scripts/`, `patches/`, `baselines/`: build steps, patches and stock references.
- `scripts/archive_build_inputs.py <SOURCE_MANIFEST.xml> <dir>`: archive all pinned inputs locally.
