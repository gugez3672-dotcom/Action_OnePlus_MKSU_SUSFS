"""Exercise Git application across EOF boundaries, including the K41 failure."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from patch_text import unified_file_patch


class PatchTextTests(unittest.TestCase):
    def test_eof_combinations_and_following_file_roundtrip(self):
        for before_eof in ('', '\n'):
            for after_eof in ('', '\n'):
                with self.subTest(before_eof=before_eof, after_eof=after_eof):
                    before = '#ifndef TEST\n#define TEST\nint a;\n#endif' + before_eof
                    after = '#ifndef TEST\n#define TEST\nint b;\n#endif' + after_eof
                    other_before = 'int c;\n'
                    other_after = 'int d;\n'
                    patch = (unified_file_patch('first.h', before, after) +
                             unified_file_patch('second.c', other_before, other_after))
                    self.assertNotIn('#endifdiff --git', patch)
                    with tempfile.TemporaryDirectory(prefix='patch-eof-') as directory:
                        first = Path(directory) / 'first.h'
                        second = Path(directory) / 'second.c'
                        first.write_bytes(before.encode())
                        second.write_bytes(other_before.encode())
                        subprocess.run(['git', '-c', 'core.autocrlf=false', 'apply', '--whitespace=nowarn', '-'],
                                       cwd=directory, input=patch.encode(), check=True, capture_output=True)
                        self.assertEqual(first.read_bytes(), after.encode())
                        self.assertEqual(second.read_bytes(), other_after.encode())

    def test_unchanged_file_is_empty(self):
        self.assertEqual(unified_file_patch('same.c', 'int x;', 'int x;'), '')


if __name__ == '__main__':
    unittest.main()
