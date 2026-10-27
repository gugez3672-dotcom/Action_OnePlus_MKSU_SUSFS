"""The two K32-proven A67 build adaptations; exact preimages, no root changes."""
from pathlib import Path


def once(text, old, new, label):
    if text.count(old) != 1 or new in text:
        raise RuntimeError(f'{label}: preimage drift or already applied')
    return text.replace(old, new, 1)


def main():
    common = Path('kernel_workspace/kernel_platform/common')
    make = common / 'scripts/Makefile.vmlinux'
    stamp = Path('kernel_workspace/kernel_platform/build/kernel/kleaf/impl/stamp.bzl')
    rule = ('vmlinux: scripts/link-vmlinux.sh vmlinux.o $(KBUILD_LDS) FORCE\n'
            '\t+$(call if_changed_dep,link_vmlinux)\n')
    updates = {
        make: once(make.read_text(), rule,
                   rule + '\t$(Q)cp $(objtree)/vmlinux $(objtree)/vmlinux_oki\n', 'vmlinux_oki'),
        stamp: once(stamp.read_text(),
                    'scmversion_prefix="-$android_release-$KMI_GENERATION-$oki_infix"',
                    'scmversion_prefix="-$android_release-$KMI_GENERATION"', 'stock release'),
    }
    for path, text in updates.items():
        path.write_text(text, encoding='utf-8', newline='\n')
    print('Applied the two pinned stock build adaptations.')


if __name__ == '__main__':
    main()
