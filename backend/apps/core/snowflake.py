"""Snowflake ID generator (application-layer).

Format (64-bit signed integer):
- 1 sign bit (unused)
- 41 bits timestamp (ms since custom epoch)
- 10 bits worker id
- 12 bits sequence

This matches the design described in docs/实验报告/方案.md.
"""

from __future__ import annotations

import threading
import time


class Snowflake:
    def __init__(self, worker_id: int, epoch_ms: int = 1704067200000) -> None:
        # default epoch: 2024-01-01T00:00:00Z
        if worker_id < 0 or worker_id > 1023:
            raise ValueError("worker_id must be in [0, 1023]")
        self._worker_id = int(worker_id)
        self._epoch_ms = int(epoch_ms)
        self._lock = threading.Lock()
        self._last_ms = -1
        self._seq = 0

    def next_id(self) -> int:
        with self._lock:
            now_ms = int(time.time() * 1000)
            if now_ms < self._last_ms:
                # clock moved backwards; wait
                now_ms = self._last_ms

            if now_ms == self._last_ms:
                self._seq = (self._seq + 1) & 0xFFF
                if self._seq == 0:
                    # sequence overflow in same ms; wait next ms
                    while True:
                        now_ms = int(time.time() * 1000)
                        if now_ms > self._last_ms:
                            break
            else:
                self._seq = 0

            self._last_ms = now_ms
            ts_part = (now_ms - self._epoch_ms) & 0x1FFFFFFFFFF  # 41 bits
            return (ts_part << 22) | (self._worker_id << 12) | self._seq
