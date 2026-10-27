"""Compile the actual pinned SUS_MAP macro and exercise all visibility cases."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


def main():
    common = Path('kernel_workspace/kernel_platform/common')
    header = (common / 'include/linux/susfs_def.h').read_text()
    macro = re.search(r'(?m)^#define SUSFS_IS_INODE_SUS_MAP\(inode\).*?(?=\n\n)', header, re.S)[0]
    source = r'''
#include <stdio.h>
struct mapping { unsigned long flags; };
struct inode { struct mapping *i_mapping; };
struct file { struct inode *inode; };
struct vma { struct file *vm_file; };
#define file_inode(f) ((f)->inode)
#define unlikely(x) (x)
#define test_bit(b, p) (((*(p)) >> (b)) & 1UL)
#define AS_FLAGS_SUS_MAP 0
static int app;
static int susfs_is_current_proc_umounted_app(void) { return app; }
MACRO
static int visible(struct vma *vma) {
    return !vma->vm_file || !(SUSFS_IS_INODE_SUS_MAP(file_inode(vma->vm_file)));
}
int main(void) {
    for (int bits = 0; bits < 32; ++bits) {
        struct mapping map = { !!(bits & 8) };
        struct inode inode = { (bits & 4) ? &map : 0 };
        struct file file = { (bits & 2) ? &inode : 0 };
        struct vma vma = { (bits & 1) ? &file : 0 };
        app = !!(bits & 16);
        int expected = !((bits & 1) && (bits & 2) && (bits & 4) && (bits & 8) && app);
        if (visible(&vma) != expected) return bits + 1;
    }
    return 0;
}
'''.replace('MACRO', macro)
    compiler = os.environ.get('TASK_HOST_CLANG', 'clang')
    out = Path('artifacts')
    out.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='susmap-', dir=out) as temporary:
        folder = Path(temporary)
        cfile = folder / 'predicate.c'
        binary = folder / ('predicate.exe' if os.name == 'nt' else 'predicate')
        bad = source.replace('!(SUSFS_IS_INODE_SUS_MAP(file_inode(vma->vm_file)))',
                             '!SUSFS_IS_INODE_SUS_MAP(file_inode(vma->vm_file))')
        cfile.write_text(bad, encoding='utf-8')
        result = subprocess.run([compiler, '-Werror', '-Wlogical-op-parentheses', '-fsyntax-only', str(cfile)], capture_output=True)
        assert result.returncode and b'logical-op-parentheses' in result.stderr, 'old expression must fail the actual Clang diagnostic'
        cfile.write_text(source, encoding='utf-8')
        subprocess.run([compiler, '-Werror', '-Wlogical-op-parentheses', str(cfile), '-o', str(binary)], check=True)
        subprocess.run([str(binary.resolve())], check=True)
    (out / 'SUS_MAP_PREDICATE.json').write_text(json.dumps({
        'actual_upstream_macro': macro, 'old_expression_rejected_by_clang': True,
        'corrected_expression_compiles': True, 'visibility_combinations_passed': 32,
        'boundary': 'Host C macro/logic regression, not a substitute for the full A67 kernel build.',
    }, indent=2) + '\n', encoding='utf-8')
    print('PASS: original macro warning reproduced; corrected predicate passes Clang and 32 visibility combinations.')


if __name__ == '__main__':
    main()
