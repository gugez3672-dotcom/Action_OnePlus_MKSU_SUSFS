"""Require compiled preinit runner support; forbid silent KSU_NO_PREINIT fallback."""
import re


def verify_preinit(image, system_map, logs):
    for name in ('preflight.log', 'build.log'):
        if name not in logs:
            raise ValueError(f'missing compiler log: {name}')
        if re.search(r'\bpreinit disabled\b', logs[name], re.I):
            raise ValueError(f'preinit silently disabled in {name}')
    if b'KSU_NO_PREINIT flag is defined' in image:
        raise ValueError('compiled KSU_NO_PREINIT fallback present in Image')
    for symbol in ('ksu_preinit_init', 'ksu_preinit_handle_post_execveat'):
        if not re.search(r' [Tt] ' + symbol + r'$', system_map, re.M):
            raise ValueError(f'compiled preinit function missing: {symbol}')
    addresses = {}
    for symbol in ('ksu_preinit_runner_start', 'ksu_preinit_runner_end'):
        match = re.search(r'^([0-9a-fA-F]+) \w ' + symbol + r'$', system_map, re.M)
        if not match:
            raise ValueError(f'preinit runner blob symbol missing: {symbol}')
        addresses[symbol] = int(match[1], 16)
    size = addresses['ksu_preinit_runner_end'] - addresses['ksu_preinit_runner_start']
    if size <= 0:
        raise ValueError('empty or inverted compiled preinit runner blob')
    return {'passed': True, 'runner_bytes': size, 'no_preinit_fallback': False,
            'compiler_logs_checked': ['preflight.log', 'build.log']}
