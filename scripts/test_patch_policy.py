"""Ensure fuzzy success and misleading function text cannot satisfy source gates."""
import unittest
from c_source_checks import function_body
from susfs_patch_policy import reject_fuzzy_log


class PatchPolicyTests(unittest.TestCase):
    def test_offset_without_fuzz_is_allowed(self):
        reject_fuzzy_log('Hunk #4 succeeded at 1200 (offset -228 lines).')

    def test_every_nonzero_fuzz_is_rejected(self):
        for fuzz in (1, 2, 3, 20):
            with self.subTest(fuzz=fuzz), self.assertRaises(ValueError):
                reject_fuzzy_log(f'Hunk #4 succeeded at 1512 with fuzz {fuzz}.')

    def test_comments_strings_and_calls_do_not_define_a_function(self):
        source = ('/* int target(int v) { bad(); } */\n'
                  'int caller(void) { target(1); return 0; }\n'
                  'static int target(int v)\n{\n const char *s = "}"; /* { */ return v;\n}\n')
        body = function_body(source, 'target')
        self.assertIn('return v;', body)
        self.assertNotIn('bad()', body)

    def test_duplicate_definitions_are_rejected(self):
        with self.assertRaises(ValueError):
            function_body('int target(void) { return 1; }\nint target(void) { return 2; }', 'target')


if __name__ == '__main__':
    unittest.main()
