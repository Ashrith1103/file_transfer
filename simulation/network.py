\
\
\
\
\
\


from __future__ import annotations

import random


class NetworkSimulator:
\
\
\
\
\
\
\
\


    def __init__(self, drop_rate: float = 0.0, corrupt_rate: float = 0.0) -> None:
        if not (0.0 <= drop_rate <= 1.0):
            raise ValueError(f"drop_rate must be in [0, 1], got {drop_rate}")
        if not (0.0 <= corrupt_rate <= 1.0):
            raise ValueError(f"corrupt_rate must be in [0, 1], got {corrupt_rate}")
        self.drop_rate = drop_rate
        self.corrupt_rate = corrupt_rate

    def should_drop(self) -> bool:

        return self.drop_rate > 0.0 and random.random() < self.drop_rate

    def corrupt(self, data: bytes) -> bytes:
\
\
\
\

        if data and self.corrupt_rate > 0.0 and random.random() < self.corrupt_rate:
            return bytes([data[0] ^ 0xFF]) + data[1:]
        return data
