"""Serialize text patches without joining a missing EOF newline to a header."""
import difflib


def unified_file_patch(relative, before, after):
    if before == after:
        return ''
    result = [f'diff --git a/{relative} b/{relative}\n']
    for line in difflib.unified_diff(before.splitlines(keepends=True),
                                     after.splitlines(keepends=True),
                                     fromfile='a/' + relative, tofile='b/' + relative):
        result.append(line)
        if not line.endswith('\n'):
            result.append('\n\\ No newline at end of file\n')
    return ''.join(result)
