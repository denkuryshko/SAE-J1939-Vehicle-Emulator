"""Waiting for the emulator's threads in tests: poll for the event, never sleep a fixed time.

CI runners (macOS above all) can be several times slower than a desktop, so a fixed sleep that is
plenty here is sometimes too short there.
"""

import time


def wait_until(predicate, timeout=3.0, step=0.01):
    """Poll `predicate` until it is true or `timeout` s pass; return its last value."""
    end = time.time() + timeout
    while True:
        value = predicate()
        if value or time.time() >= end:
            return value
        time.sleep(step)
