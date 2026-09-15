import os
import shutil
from pathlib import Path
import sys

phase = sys.argv[1]
out = Path(os.environ['GITHUB_WORKSPACE']) / 'artifacts'
paths = [Path(x) for x in (out / f'{phase}.outputs.txt').read_text().splitlines() if x]
wanted = ['.config'] if phase == 'preflight' else ['Image', 'vmlinux', 'System.map', 'Module.symvers']

for name in wanted:
    found = []
    for p in paths:
        if p.is_file() and p.name == name:
            found.append(p)
            continue
        if p.is_dir():
            candidate = p / name
            if candidate.is_file():
                found.append(candidate)

    if len(found) != 1:
        raise SystemExit(f'Expected one {name} from explicit GKI target, found: {found}')

    dest = out / ('gki_preflight.config' if name == '.config' else name)
    shutil.copy2(found[0], dest)
    print(f'{found[0]} -> {dest}')
