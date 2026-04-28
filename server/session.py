from __future__ import annotations

import random
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
        self._sock.settimeout(self._config.client_socket_timeout)
        with self._sock:
            try:
                self._handle()
            except Exception as exc:
                print(
                    f"SERVER {self.client_id}: error from {self._address[0]}:{self._address[1]}: {exc}",
                    flush=True,
                )
                try:
                    send_message(self._sock, {"type": "ERROR", "message": str(exc)})
                except Exception:
                    pass

    def _handle(self) -> None:
        header, payload = receive_message(self._sock)
        if header.get("type") != "UPLOAD":
            raise ProtocolError(f"expected UPLOAD, got {header.get('type')!r}")

        file_name = Path(str(header.get("file_name", "upload.bin"))).name
        claimed_checksum = str(header.get("checksum", ""))
        actual_checksum = sha256_bytes(payload)
        print(
            f"SERVER {self.client_id}: received upload {file_name}, {len(payload)} bytes",
            flush=True,
        )

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
        print(
            f"SERVER {self.client_id}: divided {file_name} into {len(chunks)} chunk(s), "
            f"chunk_size={self._config.chunk_size}",
            flush=True,
        )
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

        self._send_batch(chunks, simulate_errors=True)

        chunk_map: dict[int, Chunk] = {c.seq: c for c in chunks}
        while True:
            request, _ = receive_message(self._sock)
            raise_if_error(request)
            rtype = request.get("type")
            if rtype == "DONE":
                print(
                    f"SERVER {self.client_id}: DONE received, transfer complete from "
                    f"{self._address[0]}:{self._address[1]}",
                    flush=True,
                )
                return
            if rtype != "RETRANSMIT":
                raise ProtocolError(f"expected RETRANSMIT or DONE, got {rtype!r}")

            seqs = [int(s) for s in request.get("seqs", [])]
            print(f"SERVER {self.client_id}: retransmit request for {len(seqs)} chunk(s)", flush=True)
            resend = [chunk_map[s] for s in seqs if s in chunk_map]
            self._send_batch(resend, simulate_errors=False)

    def _send_batch(self, chunks: list[Chunk], *, simulate_errors: bool) -> None:
        ordered = list(chunks)
        random.shuffle(ordered)

        for chunk in ordered:
            if simulate_errors and self._sim.should_drop():
                print(f"SERVER {self.client_id}: DROP chunk {chunk.seq + 1}", flush=True)
                continue

            data = chunk.data
            if simulate_errors:
                data = self._sim.corrupt(data)
                if data != chunk.data:
                    print(f"SERVER {self.client_id}: CORRUPT chunk {chunk.seq + 1}", flush=True)

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
            print(f"SERVER {self.client_id}: SENT chunk {chunk.seq + 1}", flush=True)

        send_message(self._sock, {"type": "END_BATCH"})
        print(f"SERVER {self.client_id}: END_BATCH sent ({len(chunks)} chunk(s))", flush=True)