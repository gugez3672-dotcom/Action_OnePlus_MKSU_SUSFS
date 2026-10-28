"""Rename presentation literals; prove Rust tokens outside literals are identical."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import argparse

ROOT = Path(__file__).resolve().parents[1]


def apply_directory_identity(source):
    """Keep displayed metadata separate from the installed directory used by commands."""
    path = source / 'userspace/ksud/src/module.rs'
    text = path.read_text('utf-8')
    start = text.index('fn list_module(')
    end = text.index('\npub fn list_modules()', start)
    body = text[start:end]
    marker = '        // If id is missing or empty, use directory name as fallback\n'
    addition = '''        // DN: commands and WebUI must use the physical installed directory.
        let Some(dir_id) = path.file_name().and_then(|name| name.to_str()) else {
            continue;
        };
        module_prop_map.insert("dir_id".to_owned(), dir_id.to_owned());

'''
    assert body.count(marker) == 1 and body.count('.get("id")') == 2
    body = body.replace(marker, addition + marker).replace('.get("id")', '.get("dir_id")')
    path.write_text(text[:start] + body + text[end:], encoding='utf-8', newline='\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=ROOT / '.inputs/BackendSource')
    parser.add_argument('--output', type=Path, default=ROOT / 'manager-support')
    args = parser.parse_args()
    source = args.source
    tool = ROOT / '.inputs/literal-audit-target/release' / ('notes-literal-audit.exe' if __import__('os').name == 'nt' else 'notes-literal-audit')
    subprocess.run(['git', 'diff', '--exit-code'], cwd=source, stdout=subprocess.DEVNULL, check=True)
    backup = ROOT / '.inputs/backend-before-branding'
    backup.mkdir(exist_ok=True)
    records = []
    verified = []
    for folder in ('userspace/ksud', 'userspace/ksuinit'):
        for path in sorted((source / folder).rglob('*.rs')):
            original = path.read_bytes()
            entries = json.loads(subprocess.check_output([str(tool), 'list', str(path)], text=True, encoding='utf-8'))
            changes = []
            relative = path.relative_to(source).as_posix()
            for entry in entries:
                value = entry['value']
                updated = value
                reason = 'Exact upstream runtime interface; retain this literal at this source location.'
                if entry['source'].startswith(('///', '//!')):
                    replacement = entry['source'].replace('KernelSU', 'Daily Notes')
                    replacement = re.sub(r'\bksud\b', 'note_runtime', replacement)
                    if replacement != entry['source']:
                        changes.append((entry['start'], entry['end'], replacement.encode()))
                        reason = 'Clap/help documentation presentation only.'
                    else:
                        reason = 'Documentation of an exact upstream protocol identifier.'
                elif entry['source'] == entry['token']:
                    if 'me.weishu.kernelsu' in value:
                        updated = value.replace('me.weishu.kernelsu', 'com.daily.notes')
                    elif value in ('kernelsu_patched_{}.img', 'kernelsu_restore_{}.img'):
                        updated = value.replace('kernelsu_', 'notes_')
                    elif value == 'CONFIG_KSU_DEBUG is not enabled':
                        updated = 'Debug support is not enabled'
                    elif value.startswith('Shell SU ADB Only - '):
                        updated = 'Shell SU ADB Only - require adbd or a trusted root process when shell is granted root'
                    elif value == "don't use ksu fd wrapper":
                        updated = "don't use the restricted descriptor wrapper"
                    elif value == 'set KSU_NO_NEW_PRIVS':
                        updated = 'set restricted privilege mode'
                    elif not ('http://' in value or 'https://' in value):
                        updated = value.replace('KernelSU', 'Daily Notes')
                        if ' ' in updated and '/data/' not in updated and '`ksud ' not in updated:
                            updated = re.sub(r'\bksud\b', 'runtime', updated)
                            updated = re.sub(r'\bksu(?= fds| fd)', 'runtime', updated)
                            updated = updated.replace('ksuctl failed:', 'runtime ioctl failed:')
                            updated = updated.replace('Failed to load ksuinit', 'Failed to load startup helper')
                    if updated != value:
                        prefix = entry['token'][0] if entry['token'].startswith(('b', 'c')) else ''
                        changes.append((entry['start'], entry['end'], (prefix + json.dumps(updated, ensure_ascii=False)).encode()))
                        reason = 'Application identity or diagnostic/help presentation only.'
                    elif path.name == 'build.rs':
                        reason = 'Build-time environment/header interface; not part of the Android payload.'
                    elif 'lkm_image' in relative:
                        reason = 'Exact LKM capsule/ELF bootstrap ABI or its diagnostic; paired with the unmodified official bootstrap object.'
                    elif path.name in ('module.rs', 'feature.rs'):
                        reason = 'Exact module/metamodule environment interface consumed by third-party modules.'
                    elif path.name in ('defs.rs', 'assets.rs', 'boot_patch.rs'):
                        reason = 'Exact installed root path, boot ramdisk field, asset suffix or backup format shared with the official runtime.'
                    elif path.name in ('ksucalls.rs', 'unload.rs', 'restorecon.rs', 'su.rs', 'debug.rs'):
                        reason = 'Exact kernel descriptor, SELinux context, debug parameter or documented command option.'
                    elif path.name == 'sulog.rs':
                        reason = 'Exact log-daemon property interface; must match the official manager log reader.'
                    elif path.name == 'soft_reboot.rs':
                        reason = 'Inherited waitsys descriptor environment interface.'
                    elif path.name == 'preinit.rs':
                        reason = 'Recovery message documents the real installed daemon command; preserve usable recovery instructions.'
                records.append({'file': relative, 'line': entry['line'], 'before': value, 'after': updated, 'reason': reason})
            if not changes:
                continue
            target = backup / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(original)
            after = original
            for start, end, value in sorted(changes, reverse=True):
                assert after[start:end] == original[start:end]
                after = after[:start] + value + after[end:]
            path.write_bytes(after)
            subprocess.run([str(tool), 'verify', str(target), str(path)], check=True)
            verified.append(relative)
    # Only package metadata changes: preserve dependency versions, aliases and Rust implementation.
    edits = {
        'userspace/ksud/Cargo.toml': [('name = "ksud"', 'name = "note_runtime"'),
            ('ksuinit = { path = "../ksuinit" }', 'ksuinit = { package = "note_startup", path = "../ksuinit" }')],
        'userspace/ksuinit/Cargo.toml': [('name = "ksuinit"', 'name = "note_startup"')],
        'Cargo.toml': [('[profile.release.package.ksud]', '[profile.release.package.note_runtime]')],
        'Cargo.lock': [('name = "ksud"', 'name = "note_runtime"'), ('name = "ksuinit"', 'name = "note_startup"'), (' "ksuinit",', ' "note_startup",')],
    }
    for relative, replacements in edits.items():
        path = source / relative
        text = path.read_text('utf-8')
        for before, after in replacements:
            assert text.count(before) == 1, (relative, before)
            text = text.replace(before, after)
        path.write_text(text, encoding='utf-8', newline='\n')
    # Installer banners are display text. Exported KSU_* variables and mount source remain exact.
    for path in (source / 'userspace/ksud').rglob('*.sh'):
        original = path.read_bytes()
        after = original.replace(b'Powered by KernelSU', b'Powered by Daily Notes').replace(b'# KernelSU installer script', b'# Daily Notes installer script')
        if after != original:
            path.write_bytes(after)
    apply_directory_identity(source)
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    patch = subprocess.check_output(['git', 'diff', '--binary'], cwd=source)
    (out / 'official-backend-branding.patch').write_bytes(patch)
    report = {'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip(),
        'patch_sha256': hashlib.sha256(patch).hexdigest(), 'rust_files_token_equivalent': verified,
        'package_metadata_only': edits, 'literal_policy': records,
        'scope': 'Exact source/literal entries, not a blanket allowance for ksu strings. Final ELF/APK audit remains required.',
        'installer_comments': 'Only installer presentation banner comments renamed; module environment/hook interfaces unchanged.',
        'functional_adaptations': [{'file': 'userspace/ksud/src/module.rs',
            'change': 'Export physical dir_id; preinit/config lookup uses the same physical ID; declared module.prop id is preserved.',
            'boundary': 'No kernel UAPI, permission, mount or installer implementation changes.'}]}
    (out / 'backend-literal-policy.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(f'Presentation renamed with Rust token equivalence in {len(verified)} files; {len(records)} exact literal policy entries recorded.')


if __name__ == '__main__':
    main()
