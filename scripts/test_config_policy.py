"""Regression boundaries for the two-stage configuration gate."""
import unittest
from pathlib import Path
from config_policy import config, compare, TRUST_CONFIG


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.stock = config(Path('baselines/PLK110_16.0.8.302_stock.config').read_text())
        self.actual = self.stock | TRUST_CONFIG

    def test_original_trust_only_is_permitted(self):
        _, bad, unmet = compare(self.stock, self.actual)
        self.assertFalse(bad or unmet)

    def test_missing_original_trust_is_rejected(self):
        _, _, unmet = compare(self.stock, self.stock)
        self.assertIn('CONFIG_SYSTEM_TRUSTED_KEYS', unmet)

    def test_zstd_regression_is_rejected(self):
        actual = self.actual | {'CONFIG_DEBUG_INFO_COMPRESSED_ZSTD': 'n',
                                'CONFIG_DEBUG_INFO_COMPRESSED_NONE': 'y'}
        _, bad, _ = compare(self.stock, actual)
        self.assertEqual(len(bad), 2)

    def test_signature_protection_cannot_be_disabled(self):
        _, bad, _ = compare(self.stock, self.actual | {'CONFIG_MODULE_SIG_PROTECT': 'n'})
        self.assertIn('CONFIG_MODULE_SIG_PROTECT', bad)

    def test_root_is_rejected_in_stock_phase(self):
        _, bad, _ = compare(self.stock, self.actual | {'CONFIG_KSU': 'y'})
        self.assertIn('CONFIG_KSU', bad)

    def test_feature_phase_requires_exact_additions(self):
        additions = config(Path('baselines/PLK110_16.0.8.302_expected_sukisu_susfs.config.additions').read_text())
        actual = self.actual | additions
        _, bad, unmet = compare(self.stock, actual, additions)
        self.assertFalse(bad or unmet)
        actual['CONFIG_KSU_SUSFS'] = 'n'
        _, _, unmet = compare(self.stock, actual, additions)
        self.assertIn('CONFIG_KSU_SUSFS', unmet)
        actual['CONFIG_KPM'] = 'y'
        _, bad, _ = compare(self.stock, actual, additions)
        self.assertIn('CONFIG_KPM', bad)


if __name__ == '__main__':
    unittest.main()
