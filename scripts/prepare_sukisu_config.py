"""Declare exact feature choices and pin build metadata without network queries."""
from pathlib import Path

kp = Path('kernel_workspace/kernel_platform')
path = kp / 'KernelSU/kernel/Makefile'
text = path.read_text()
start = text.index('git_short_sha    = ')
end = text.index('$(info -- $(REPO_NAME) version:')
assert start < end and 'releases/latest' in text[start:end]
# Official v4.2.0 release manager is SukiSU_v4.2.0_40900_releases.apk.
# The source is the pinned builtin commit, not a moving main branch or the
# surrounding OnePlus modules repository that Bazel's sandbox exposes to git.
text = text[:start] + (
    '# Fixed to the audited SukiSU v4.2.0 builtin source.\n'
    'KSU_VERSION := 40900\n'
    'KSU_VERSION_FULL := v4.2.0-e2912817@builtin\n'
) + text[end:]
path.write_text(text)
fragment = kp / 'common/arch/arm64/configs/plk110_sukisu.fragment'
fragment.write_text(Path('baselines/PLK110_16.0.8.302_expected_sukisu_susfs.config.additions').read_text())
path = kp / 'common/BUILD.bazel'
text = path.read_text()
anchor = 'post_defconfig_fragments = ["arch/arm64/configs/plk110_stock.fragment"],'
assert text.count(anchor) == 1
text = text.replace(anchor, 'post_defconfig_fragments = [\n'
                    '        "arch/arm64/configs/plk110_stock.fragment",\n'
                    '        "arch/arm64/configs/plk110_sukisu.fragment",\n'
                    '    ],')
path.write_text(text)
print('Pinned SukiSU version metadata and feature fragment; upstream gki_defconfig unchanged.')
