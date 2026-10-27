"""Review gate for manual triggers, source pins, and build command structure."""
import ast
import json
import os
from pathlib import Path
import re
import subprocess
import yaml

root = Path.cwd()
workflow = root / '.github/workflows/Build-ReSukiSU-StockSched.yml'
definition = yaml.load(workflow.read_text(), Loader=yaml.BaseLoader)
assert set(definition['on']) == {'workflow_dispatch'}, 'automatic build trigger is forbidden'
dispatch = definition['on']['workflow_dispatch']
assert dispatch['inputs']['review_ack']['required'] == 'true'
job = definition['jobs']['official-stock-sched']
assert "inputs.review_ack == 'reviewed'" in job['if']
assert definition['permissions'] == {'contents': 'read', 'actions': 'read'}
steps = job['steps']
commands = '\n'.join(step.get('run', '') for step in steps)
for old in ('apply_susfs_post230_fixes.py', 'port_ksu_3877_selinux_hide.py',
            'apply_k30_upstream_fixes.py', 'apply_k32_kernel_fixes.py', 'apply_plk110_pguard.py',
            'github.com/ReSukiSU', 'github.com/cctv18', 'D91-preserved-backend'):
    assert old not in commands, old
for command in ('scripts/integrate_official_susfs.py', 'scripts/prepare_official_kernel.py',
                'scripts/link_official_driver.py',
                'scripts/verify_official_sources.py', 'scripts/prepare_stock_ikconfig.py',
                'scripts/verify_official_image.py', 'scripts/package_official_gki.sh'):
    assert commands.count(command) == 1, command
order = [commands.index(marker) for marker in (
    'scripts/integrate_official_susfs.py', 'scripts/prepare_official_kernel.py',
    'scripts/prepare_stock_ikconfig.py', 'scripts/verify_official_sources.py',
    'scripts/check_source_guards.py --fixture .',
    'scripts/source_state.py record', 'scripts/build_gki.sh preflight',
    'scripts/build_gki.sh build', 'scripts/source_state.py verify',
    'scripts/verify_official_image.py', 'scripts/package_official_gki.sh')]
assert order == sorted(order), 'build/source/packaging gate order drift'
for path in (root / 'scripts').glob('*.py'):
    ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
for step in steps:
    if 'run' in step:
        subprocess.run([os.environ.get('TASK_BASH_EXE', 'bash'), '-n'], input=step['run'].encode(), check=True)
for path in (root / 'scripts').glob('*.sh'):
    subprocess.run([os.environ.get('TASK_BASH_EXE', 'bash'), '-n', str(path)], check=True)
lock = json.loads((root / 'inputs.lock.json').read_text())
assert lock['susfs']['commit'] == '519c86c5d8ad3832ff4a2e1a81dc1b81076f1693'
assert lock['manager']['version_code'] == 36200 and lock['pguard'] is False
print(f'PASS: manual reviewed trigger, {len(steps)} step bodies, Python/Bash syntax, fixed 519 inputs.')
