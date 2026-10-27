"""Regression tests for silent preinit fallback in an otherwise successful build."""
import unittest
from preinit_gate import verify_preinit


class PreinitTests(unittest.TestCase):
    def setUp(self):
        self.symbols = ('1000 T ksu_preinit_init\n1100 T ksu_preinit_handle_post_execveat\n'
                        '2000 R ksu_preinit_runner_start\n2800 R ksu_preinit_runner_end\n')
        self.logs = {'preflight.log': 'configuration complete', 'build.log': 'link complete'}

    def test_runner_and_functions_are_required(self):
        self.assertEqual(verify_preinit(b'Image', self.symbols, self.logs)['runner_bytes'], 2048)

    def test_warning_in_successful_build_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'silently disabled'):
            verify_preinit(b'Image', self.symbols, self.logs | {'build.log': 'warning: preinit disabled\nBUILD SUCCESS'})

    def test_warning_in_configuration_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'silently disabled'):
            verify_preinit(b'Image', self.symbols, self.logs | {'preflight.log': 'KernelSU: preinit disabled'})

    def test_compiled_fallback_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'fallback'):
            verify_preinit(b'ksu_preinit_init: KSU_NO_PREINIT flag is defined', self.symbols, self.logs)

    def test_missing_handler_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'function missing'):
            verify_preinit(b'Image', self.symbols.replace('1100 T ksu_preinit_handle_post_execveat\n', ''), self.logs)

    def test_empty_runner_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'empty'):
            verify_preinit(b'Image', self.symbols.replace('2800 R', '2000 R'), self.logs)

    def test_missing_log_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'missing compiler log'):
            verify_preinit(b'Image', self.symbols, {'build.log': 'OK'})


if __name__ == '__main__':
    unittest.main()
