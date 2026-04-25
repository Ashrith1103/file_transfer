"""Packet drop / corruption simulation.

The :class:`NetworkSimulator` is used by the server session to decide, on a
per-chunk basis, whether to drop the chunk silently or corrupt its first byte
before sending.  All randomness is driven by the configured rates so that
tests can set them to 0.0 for deterministic clean transfers.
"""

from __future__ import annotations

import random


class NetworkSimulator:
    """Simulates an unreliable network link.

    Parameters
    ----------
    drop_rate:
        Probability (0.0–1.0) that :meth:`should_drop` returns ``True``.
    corrupt_rate:
        Probability (0.0–1.0) that :meth:`corrupt` actually flips a byte.
    """

    def __init__(self, drop_rate: float = 0.0, corrupt_rate: float = 0.0) -> None:
        if not (0.0 <= drop_rate <= 1.0):
            raise ValueError(f"drop_rate must be in [0, 1], got {drop_rate}")
        if not (0.0 <= corrupt_rate <= 1.0):
            raise ValueError(f"corrupt_rate must be in [0, 1], got {corrupt_rate}")
        self.drop_rate = drop_rate
        self.corrupt_rate = corrupt_rate

    def should_drop(self) -> bool:
        """Return ``True`` if this chunk should be silently dropped."""
        return self.drop_rate > 0.0 and random.random() < self.drop_rate

    def corrupt(self, data: bytes) -> bytes:
        """Return *data*, possibly with its first byte flipped.

        No-ops on empty payloads.  Returns the original bytes unchanged when
        the corruption roll fails or the rate is zero.
        """
        if data and self.corrupt_rate > 0.0 and random.random() < self.corrupt_rate:
            return bytes([data[0] ^ 0xFF]) + data[1:]
        return data
