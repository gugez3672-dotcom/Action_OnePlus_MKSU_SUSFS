"""Add only ReSukiSU/SUSFS feature deltas on top of the verified PLK110 A67 stock GKI."""
from pathlib import Path

kp = Path("kernel_workspace/kernel_platform")
fragment = kp / "common/arch/arm64/configs/plk110_resukisu.fragment"
fragment.write_text(
    Path("baselines/PLK110_16.0.8.302_expected_resukisu_susfs.config.additions").read_text()
)

path = kp / "common/BUILD.bazel"
text = path.read_text()
anchor = 'post_defconfig_fragments = ["arch/arm64/configs/plk110_stock.fragment"],'
assert text.count(anchor) == 1, "unexpected stock post_defconfig_fragments"
text = text.replace(
    anchor,
    'post_defconfig_fragments = [\n'
    '        "arch/arm64/configs/plk110_stock.fragment",\n'
    '        "arch/arm64/configs/plk110_resukisu.fragment",\n'
    '    ],',
    1,
)
path.write_text(text)
print("Added ReSukiSU/SUSFS as a post-defconfig fragment; stock gki_defconfig remains untouched.")
