"""Structured read-only status for the Lite terminal console."""

import os
import re
import time


_ANSI = re.compile(r'\x1b\[[0-9;]*m')


def build_payload(snapshot, version, device, protocol):
    threads, rti, ignition, warnings = snapshot
    return {
        'pid': os.getpid(), 'updated': time.time(), 'version': version,
        'device': f'{device} | {protocol}', 'rti': bool(rti), 'ign': bool(ignition),
        'threads': threads,
        'warnings': [_ANSI.sub('', warning) for warning in warnings],
    }
