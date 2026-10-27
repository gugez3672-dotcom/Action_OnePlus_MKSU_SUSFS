"""The official driver linkage, with checked preimages for the pinned stock tree."""
from pathlib import Path

common = Path('kernel_workspace/kernel_platform/common')
link = common / 'drivers/kernelsu'
make = common / 'drivers/Makefile'
kconfig = common / 'drivers/Kconfig'
obj = 'obj-$(CONFIG_KSU) += kernelsu/'
source = 'source "drivers/kernelsu/Kconfig"'
make_text = make.read_text()
config_text = kconfig.read_text()
assert not link.exists() and not link.is_symlink(), 'KernelSU driver link already exists'
assert obj not in make_text and source not in config_text
assert config_text.splitlines().count('endmenu') == 1, 'unexpected stock drivers/Kconfig layout'
link.symlink_to(Path('..') / '..' / 'KernelSU' / 'kernel', target_is_directory=True)
make.write_text(make_text + '\n' + obj + '\n', encoding='utf-8', newline='\n')
kconfig.write_text(config_text.replace('\nendmenu', '\n' + source + '\nendmenu', 1),
                  encoding='utf-8', newline='\n')
print('Linked the pinned official driver into the stock build tree.')
