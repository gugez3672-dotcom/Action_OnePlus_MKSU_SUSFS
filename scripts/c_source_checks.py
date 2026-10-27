"""Small source assertions scoped to actual named C function bodies."""
import re


def masked_c(text):
    pattern = r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\''
    return re.sub(pattern, lambda match: re.sub(r'[^\n]', ' ', match[0]), text, flags=re.S)


def function_span(text, name):
    masked = masked_c(text)
    found = []
    for match in re.finditer(r'\b' + re.escape(name) + r'\s*\(', masked):
        position = match.end()
        depth = 1
        while position < len(masked) and depth:
            depth += (masked[position] == '(') - (masked[position] == ')')
            position += 1
        while position < len(masked) and masked[position].isspace():
            position += 1
        if position >= len(masked) or masked[position] != '{':
            continue
        start = position
        depth = 1
        position += 1
        while position < len(masked) and depth:
            depth += (masked[position] == '{') - (masked[position] == '}')
            position += 1
        if depth:
            raise ValueError(f'unbalanced function body: {name}')
        found.append((start, position))
    if len(found) != 1:
        raise ValueError(f'expected one C definition for {name}, got {len(found)}')
    return found[0]


def function_body(text, name):
    start, end = function_span(text, name)
    return text[start:end]


def verify_smaps_hooks(text):
    smap = function_body(text, 'show_smap')
    rollup = function_body(text, 'show_smaps_rollup')
    predicate = 'SUSFS_IS_INODE_SUS_MAP(file_inode(vma->vm_file))'
    if smap.count(predicate) != 1:
        raise ValueError('show_smap: exactly one SUS_MAP predicate is required')
    if not smap.index(predicate) < smap.index('return 0;') < smap.index('if (!vma_pages(vma))'):
        raise ValueError('show_smap: hidden VMA must return before stats/pad handling')
    for forbidden in ('smaps_rollup_open', 'pte_is_pinned'):
        body = function_body(text, forbidden)
        if 'SUSFS_IS_INODE_SUS_MAP' in body or 'bypass_orig_flow' in body:
            raise ValueError(f'SUS_MAP hook in wrong function: {forbidden}')
    if rollup.count('smap_gather_stats(') != 3 or rollup.count(predicate) != 3:
        raise ValueError('show_smaps_rollup: all three old-structure paths must be guarded')
    for indent, offset in (('\t\t', '0'), ('\t\t\t\t', '0'), ('\t\t\t\t', 'last_vma_end')):
        expected = ('#ifdef CONFIG_KSU_SUSFS_SUS_MAP\n'
                    f'{indent}if (!vma->vm_file || !{predicate})\n'
                    '#endif\n'
                    f'{indent}\tsmap_gather_stats(vma, &mss, {offset});\n'
                    f'{indent}last_vma_end = vma->vm_end;')
        if expected not in rollup:
            raise ValueError(f'rollup guard or last_vma_end update missing: {offset}/{len(indent)}')
    if 'goto bypass_orig_flow' in rollup:
        raise ValueError('unexpected new-structure rollup label in the A67 adaptation')
    return {'show_smap': 'early hidden-VMA return', 'show_smaps_rollup': '3 guarded gather paths; cursor always advances',
            'forbidden_functions': ['smaps_rollup_open', 'pte_is_pinned']}
