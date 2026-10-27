"""Export the single source lock to Actions; no compiler or network calls."""
import json
import os
from pathlib import Path

lock = json.loads(Path('inputs.lock.json').read_text(encoding='utf-8'))
assert lock['pguard'] is False and lock['kernel_embedded_k_number'] is False
assert lock['kernelsu']['version'] == 30000 + lock['kernelsu']['git_count']
values = {
    'MANIFEST_COMMIT': lock['oneplus_manifest'],
    'COMMON_COMMIT': lock['oneplus_common'],
    'SOC_COMMIT': lock['oneplus_soc'],
    'MODULES_COMMIT': lock['oneplus_modules'],
    'KERNELSU_COMMIT': lock['kernelsu']['commit'],
    'SUSFS_COMMIT': lock['susfs']['commit'],
    'ANYKERNEL_COMMIT': lock['anykernel'],
    'EXPECTED_KERNEL_RELEASE': lock['kernel_release'],
    'STOCK_CONFIG_SHA256': lock['stock_config_sha256'],
    'AOSP_CLANG_PREBUILT_COMMIT': lock['clang_prebuilt'],
    'EXPECTED_CLANG_BUILD': lock['clang_android_build'],
    'EXPECTED_LLVM_COMMIT': lock['llvm_commit'],
    'VERIFIED_STOCK_RUN': lock['stock_reference_run'],
    'VERIFIED_STOCK_COMMIT': lock['stock_reference_commit'],
    'REPO_LAUNCHER_SHA256': lock['repo_launcher_sha256'],
}
lines = []
for key, value in values.items():
    if not isinstance(value, str) or '\n' in value or '\r' in value:
        raise SystemExit(f'invalid environment value: {key}')
    lines.append(f'{key}={value}\n')
with Path(os.environ['GITHUB_ENV']).open('a', encoding='utf-8', newline='\n') as output:
    output.writelines(lines)
print('Exported pinned inputs; KSU version', lock['kernelsu']['version'])
