import os
import shutil
from pathlib import Path
import sys

phase = sys.argv[1]
out = Path(os.environ['GITHUB_WORKSPACE']) / 'artifacts'
paths = [Path(x) for x in (out / f'{phase}.outputs.txt').read_text().splitlines() if x]
wanted = ['.config'] if phase == 'preflight' else ['Image', 'vmlinux', 'System.map', 'Module.symvers']


def matches_output(path: Path, name: str) -> bool:
    if name == 'Module.symvers':
        return path.name == 'Module.symvers' or path.name.endswith('_Module.symvers')
    return path.name == name


for name in wanted:
    found = []
    for p in paths:
        if p.is_file() and matches_output(p, name):
            found.append(p)
            continue
        if p.is_dir():
            candidates = [p / name]
            if name == 'Module.symvers':
                candidates.extend(p.glob('*_Module.symvers'))
            found.extend(candidate for candidate in candidates if candidate.is_file())

    found = list(dict.fromkeys(found))
    if len(found) != 1:
        raise SystemExit(f'Expected one {name} from explicit GKI target, found: {found}')

    dest = out / ('gki_preflight.config' if name == '.config' else name)
    shutil.copy2(found[0], dest)
    print(f'{found[0]} -> {dest}')
