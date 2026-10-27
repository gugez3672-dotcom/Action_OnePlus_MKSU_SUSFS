"""Freeze the delivered D111 feature inputs without changing the shared worktree."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = '06b764651d8c14af8f79fe2fd00327023faa6d51119b2742241e6d2ba0083eb3'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument('daily_notes', type=Path)
    args = cli.parse_args()
    source = args.daily_notes.resolve()
    output = ROOT / '.inputs/D111-final'
    assert not output.exists(), 'Frozen inputs already exist; do not overwrite'
    apk = source / 'build/DailyNotes_D1.1.1_36111_com.daily.notes_V2-only.apk'
    assert digest(apk.read_bytes()) == EXPECTED
    app = source / 'source/manager/app/src/main'
    checks = {}
    with zipfile.ZipFile(apk) as archive:
        for name in ('control.sh', 'keepalive.awk'):
            entry = 'assets/dn-adb-heartbeat/' + name
            data = archive.read(entry)
            assert data == (app / entry).read_bytes()
            assert data == (source / 'manager-custom/adb-heartbeat' / name).read_bytes()
            checks[entry] = digest(data)
    implementation = (source / 'manager-custom/adb-heartbeat/BackendCli.inc.kt').read_text('utf-8').strip()
    assert implementation in (app / 'java/com/daily/notes/data/shell/BackendCli.kt').read_text('utf-8')
    assert (source / 'manager-custom/d97/SettingsPage.kt').read_bytes() == (
        app / 'java/com/daily/notes/ui/screen/main/SettingsPage.kt').read_bytes()
    assert json.loads((source / 'manager-custom/version.json').read_text()) == {'name': 'D1.1.1', 'code': 36111}
    roots = ['source/manager', 'manager-custom/src', 'manager-custom/native',
             'manager-custom/emulatorview', 'manager-custom/terminal-view', 'manager-custom/adb-heartbeat']
    ignore = shutil.ignore_patterns('build', '.gradle', '.cxx', '.idea', 'local.properties', '*.jks', '*.keystore', '*.pass')
    for name in roots:
        shutil.copytree(source / name, output / name, ignore=ignore)
    for name in ['manager-custom/version.json', 'manager-custom/components.json',
                 'manager-custom/terminal-packages.json', '.github/dn111_heartbeat_gate.py',
                 'docs/D111-heartbeat-gate.md']:
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)
    files = {p.relative_to(output).as_posix(): digest(p.read_bytes())
             for p in sorted(output.rglob('*')) if p.is_file()}
    status = subprocess.check_output(['git', 'status', '--porcelain=v1', '--untracked-files=normal'], cwd=source)
    record = {
        'version': 'D1.1.1', 'code': 36111, 'apk_sha256': EXPECTED,
        'verified_correspondence': ['delivered APK digest', 'both packaged heartbeat helpers',
                                   'final BackendCli implementation', 'final SettingsPage overlay', 'version metadata'],
        'boundary': 'Frozen current source; full source-to-DEX reproducibility is not claimed.',
        'source_worktree_status_sha256': digest(status), 'packaged_helpers': checks,
        'frozen_files': files,
    }
    (ROOT / 'docs/D111-inputs.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Frozen {len(files)} input files; final D111 APK and heartbeat correspondence verified; source untouched.')


if __name__ == '__main__':
    main()
