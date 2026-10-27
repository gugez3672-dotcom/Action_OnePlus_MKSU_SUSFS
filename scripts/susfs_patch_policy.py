"""Separate six incompatible official hunks from exact-context A67 hunks.

The replacement source changes live in patches/PLK110_A67_SUSFS_519_compat.patch.
Neither the official upstream patch nor its source repository is modified.
All retained and replacement hunks are applied with git apply (no fuzz).
"""
import re


REPLACED = {
    'fs/exec.c': {1: ''},
    'fs/proc/base.c': {1: ''},
    'security/selinux/hooks.c': {1: ''},
    'fs/proc/task_mmu.c': {4: 'show_smap(', 5: 'show_smaps_rollup(', 6: 'show_smaps_rollup('},
}


def strict_official_patch(data):
    text = data.decode('utf-8')
    starts = [match.start() for match in re.finditer(r'^diff --git ', text, re.M)]
    if not starts:
        raise ValueError('no official file sections')
    starts.append(len(text))
    output = []
    replaced = []
    seen = set()
    for begin, end in zip(starts, starts[1:]):
        section = text[begin:end]
        match = re.match(r'diff --git a/(\S+) b/(\S+)\n', section)
        if not match or match[1] != match[2]:
            raise ValueError('unsupported official file header')
        relative = match[1]
        hunks = list(re.finditer(r'^@@ .*?@@[^\n]*\n', section, re.M))
        output.append(section[:hunks[0].start()])
        for number, hunk in enumerate(hunks, 1):
            stop = hunks[number].start() if number < len(hunks) else len(section)
            if number in REPLACED.get(relative, {}):
                expected = REPLACED[relative][number]
                if expected and expected not in hunk[0]:
                    raise ValueError(f'official hunk changed: {relative} #{number}')
                replaced.append({'file': relative, 'hunk': number, 'header': hunk[0].strip()})
                seen.add((relative, number))
            else:
                output.append(section[hunk.start():stop])
    expected = {(relative, number) for relative, values in REPLACED.items() for number in values}
    if seen != expected:
        raise ValueError(f'compatibility hunk inventory drift: {seen ^ expected}')
    return ''.join(output).encode(), replaced


def reject_fuzzy_log(log):
    if re.search(r'\bwith fuzz\s+[1-9]\d*\b', log, re.I):
        raise ValueError('fuzzy source patching is forbidden')
