"""Upload, receive, verify — the client side of the file transfer protocol."""

from __future__ import annotations

import socket
from pathlib import Path

from config import CLIENT_CONNECT_TIMEOUT, CLIENT_DOWNLOAD_DIR, CLIENT_SOCKET_TIMEOUT, MAX_RETRIES
from core import (
    ChecksumMismatchError,
    ProtocolError,
    RetransmitLimitError,
    atomic_write,
    raise_if_error,
    receive_message,
    send_message,
    sha256_bytes,
    sha256_file,
)


RETRANSMIT_BATCH_SIZE = 1000


class FileTransferClient:
    """Connect to a :class:`~server.server.FileTransferServer` and transfer a file.

    Parameters
    ----------
    host:
        Server hostname or IP address.
    port:
        Server TCP port.
    max_retries:
        Maximum number of RETRANSMIT rounds before giving up.
    output_dir:
        Directory where the received file is written.
    """

    def __init__(
        self,
        host: str,
        port: int,
        max_retries: int = MAX_RETRIES,
        output_dir: Path = CLIENT_DOWNLOAD_DIR,
    ) -> None:
        self.host = host
        self.port = port
        self.max_retries = max_retries
        self.output_dir = output_dir

    def transfer(self, source: Path) -> Path:
        """Upload *source*, receive it back in verified chunks, and write it to disk.

        Returns
        -------
        Path
            The path of the successfully written output file.

        Raises
        ------
        ChecksumMismatchError
            If the assembled file's checksum doesn't match the server's.
        RetransmitLimitError
            If chunks are still missing after *max_retries* rounds.
        ProtocolError
            On any framing or protocol violation.
        """
        data = source.read_bytes()

        with socket.create_connection((self.host, self.port), timeout=CLIENT_CONNECT_TIMEOUT) as sock:
            # Apply a per-read timeout for the rest of the session so a stalled
            # or crashed server doesn't block the client indefinitely.
            sock.settimeout(CLIENT_SOCKET_TIMEOUT)

            send_message(
                sock,
                {
                    "type": "UPLOAD",
                    "file_name": source.name,
                    "file_size": len(data),
                    "checksum": sha256_bytes(data),
                },
                data,
            )

            meta, _ = receive_message(sock)
            raise_if_error(meta)
            if meta.get("type") != "META":
                raise ProtocolError(f"expected META, got {meta.get('type')!r}")

            client_id = str(meta["client_id"])
            total_chunks = int(meta["total_chunks"])
            expected_checksum = str(meta["checksum"])
            file_name = Path(str(meta["file_name"])).name

            received: dict[int, bytes] = {}
            missing = self._receive_batch(sock, client_id, total_chunks, received)

            for attempt in range(1, self.max_retries + 1):
                if not missing:
                    break
                if attempt > self.max_retries:
                    raise RetransmitLimitError(self.max_retries, len(missing))
                missing = self._request_retransmits(sock, client_id, total_chunks, received, missing)

            if missing:
                raise RetransmitLimitError(self.max_retries, len(missing))

            assembled = b"".join(received[i] for i in range(total_chunks))
            actual_checksum = sha256_bytes(assembled)
            if actual_checksum != expected_checksum:
                raise ChecksumMismatchError(expected_checksum, actual_checksum, "full file")

            self.output_dir.mkdir(parents=True, exist_ok=True)
            output_path = self.output_dir / f"received_{file_name}"
            atomic_write(output_path, assembled)
            send_message(sock, {"type": "DONE", "checksum": actual_checksum})
            return output_path

    # ── Internal ──────────────────────────────────────────────────────────────

    def _receive_batch(
        self,
        sock: socket.socket,
        client_id: str,
        total_chunks: int,
        received: dict[int, bytes],
    ) -> list[int]:
        """Read CHUNK messages until END_BATCH.

        Chunks whose per-chunk digest doesn't match are discarded so they will
        appear in the next RETRANSMIT request.

        Returns a sorted list of sequence numbers still missing after this batch.
        """
        while True:
            header, payload = receive_message(sock)
            raise_if_error(header)
            mtype = header.get("type")

            if mtype == "END_BATCH":
                return sorted(seq for seq in range(total_chunks) if seq not in received)

            if mtype != "CHUNK":
                raise ProtocolError(f"unexpected message type: {mtype!r}")
            if header.get("client_id") != client_id:
                raise ProtocolError("received chunk belonging to a different session")

            seq = int(header["seq"])
            if not (0 <= seq < total_chunks):
                continue  # ignore out-of-range sequence numbers

            if sha256_bytes(payload) == str(header["checksum"]):
                received[seq] = payload
            else:
                # Corrupted chunk — discard and let it be retransmitted.
                received.pop(seq, None)

    def _request_retransmits(
        self,
        sock: socket.socket,
        client_id: str,
        total_chunks: int,
        received: dict[int, bytes],
        missing: list[int],
    ) -> list[int]:
        """Request missing chunks in bounded batches."""
        for start in range(0, len(missing), RETRANSMIT_BATCH_SIZE):
            batch = missing[start : start + RETRANSMIT_BATCH_SIZE]
            send_message(sock, {"type": "RETRANSMIT", "seqs": batch})
            self._receive_batch(sock, client_id, total_chunks, received)
        return sorted(seq for seq in range(total_chunks) if seq not in received)
