"""Per-client session handler.

Each accepted TCP connection gets its own :class:`ClientSession` instance,
running inside a dedicated daemon thread.  Sessions are fully isolated: they
share no mutable state, so an error in one session cannot affect another.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from socket import socket
from typing import TYPE_CHECKING

from core import (
    Chunk,
    ProtocolError,
    atomic_write,
    raise_if_error,
    receive_message,
    send_message,
    sha256_bytes,
    split_bytes,
)
from simulation import NetworkSimulator

if TYPE_CHECKING:
    from config import ServerConfig


class ClientSession:
    """Handle the full upload → chunk → retransmit → done lifecycle for one client."""

    def __init__(
        self,
        sock: socket,
        address: tuple[str, int],
        config: "ServerConfig",
    ) -> None:
        self._sock = sock
        self._address = address
        self._config = config
        self._sim = NetworkSimulator(config.drop_rate, config.corrupt_rate)
        self.client_id = uuid.uuid4().hex[:12]

    def run(self) -> None:
        """Entry point called from the server's thread pool.

        All exceptions are caught, logged to stdout, and—where possible—
        forwarded to the client as ERROR messages so the peer doesn't hang.
        """
        self._sock.settimeout(self._config.client_socket_timeout)
        with self._sock:
            try:
                self._handle()
            except Exception as exc:
                print(
                    f"{self.client_id} error from {self._address[0]}:{self._address[1]}: {exc}",
                    flush=True,
                )
                try:
                    send_message(self._sock, {"type": "ERROR", "message": str(exc)})
                except Exception:
                    pass

    # ── Internal ──────────────────────────────────────────────────────────────

    def _handle(self) -> None:
        header, payload = receive_message(self._sock)
        if header.get("type") != "UPLOAD":
            raise ProtocolError(f"expected UPLOAD, got {header.get('type')!r}")

        file_name = Path(str(header.get("file_name", "upload.bin"))).name
        claimed_checksum = str(header.get("checksum", ""))
        actual_checksum = sha256_bytes(payload)

        if claimed_checksum and claimed_checksum != actual_checksum:
            send_message(
                self._sock,
                {
                    "type": "ERROR",
                    "message": "upload checksum mismatch",
                    "expected": claimed_checksum,
                    "actual": actual_checksum,
                },
            )
            return

        storage_path = self._config.storage_dir / f"{self.client_id}_{file_name}"
        atomic_write(storage_path, payload)

        chunks = split_bytes(payload, self._config.chunk_size)
        send_message(
            self._sock,
            {
                "type": "META",
                "client_id": self.client_id,
                "file_name": file_name,
                "file_size": len(payload),
                "chunk_size": self._config.chunk_size,
                "total_chunks": len(chunks),
                "checksum": actual_checksum,
            },
        )

        # First pass: all chunks, errors simulated.
        self._send_batch(chunks, simulate_errors=True)

        chunk_map: dict[int, Chunk] = {c.seq: c for c in chunks}
        while True:
            request, _ = receive_message(self._sock)
            raise_if_error(request)
            rtype = request.get("type")
            if rtype == "DONE":
                print(
                    f"{self.client_id} complete from {self._address[0]}:{self._address[1]}",
                    flush=True,
                )
                return
            if rtype != "RETRANSMIT":
                raise ProtocolError(f"expected RETRANSMIT or DONE, got {rtype!r}")

            seqs = [int(s) for s in request.get("seqs", [])]
            resend = [chunk_map[s] for s in seqs if s in chunk_map]
            # Retransmissions are always clean — no drops or corruption.
            self._send_batch(resend, simulate_errors=False)

    def _send_batch(self, chunks: list[Chunk], *, simulate_errors: bool) -> None:
        """Send *chunks* in shuffled order, then send END_BATCH.

        Shuffling simulates out-of-order delivery over a real network.
        """
        import random
        ordered = list(chunks)
        random.shuffle(ordered)

        for chunk in ordered:
            if simulate_errors and self._sim.should_drop():
                continue

            data = chunk.data
            if simulate_errors:
                data = self._sim.corrupt(data)

            send_message(
                self._sock,
                {
                    "type": "CHUNK",
                    "client_id": self.client_id,
                    "seq": chunk.seq,
                    "checksum": chunk.digest,
                    "size": len(chunk.data),
                },
                data,
            )

        send_message(self._sock, {"type": "END_BATCH"})
