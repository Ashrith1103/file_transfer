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
        data = source.read_bytes()
        print(f"CLIENT upload {source.name}: {len(data)} bytes", flush=True)

        with socket.create_connection((self.host, self.port), timeout=CLIENT_CONNECT_TIMEOUT) as sock:
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
            print(f"CLIENT upload sent: {source.name}", flush=True)

            meta, _ = receive_message(sock)
            raise_if_error(meta)
            if meta.get("type") != "META":
                raise ProtocolError(f"expected META, got {meta.get('type')!r}")

            client_id = str(meta["client_id"])
            total_chunks = int(meta["total_chunks"])
            chunk_size = int(meta["chunk_size"])
            expected_checksum = str(meta["checksum"])
            file_name = Path(str(meta["file_name"])).name
            print(
                f"CLIENT {client_id}: server divided {file_name} into {total_chunks} chunk(s), "
                f"chunk_size={chunk_size}",
                flush=True,
            )

            received: dict[int, bytes] = {}
            missing = self._receive_batch(sock, client_id, total_chunks, received)

            for attempt in range(1, self.max_retries + 1):
                if not missing:
                    break
                if attempt > self.max_retries:
                    raise RetransmitLimitError(self.max_retries, len(missing))
                print(
                    f"CLIENT {client_id}: NACK {len(missing)} missing chunk(s), "
                    f"attempt {attempt}/{self.max_retries}",
                    flush=True,
                )
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
            print(f"CLIENT {client_id}: final checksum verified", flush=True)
            print(f"CLIENT {client_id}: saved {output_path}", flush=True)
            send_message(sock, {"type": "DONE", "checksum": actual_checksum})
            return output_path

    def _receive_batch(
        self,
        sock: socket.socket,
        client_id: str,
        total_chunks: int,
        received: dict[int, bytes],
    ) -> list[int]:
        while True:
            header, payload = receive_message(sock)
            raise_if_error(header)
            mtype = header.get("type")

            if mtype == "END_BATCH":
                missing = sorted(seq for seq in range(total_chunks) if seq not in received)
                print(
                    f"CLIENT {client_id}: batch ended, received {len(received)}/{total_chunks}, "
                    f"missing {len(missing)}",
                    flush=True,
                )
                return missing

            if mtype != "CHUNK":
                raise ProtocolError(f"unexpected message type: {mtype!r}")
            if header.get("client_id") != client_id:
                raise ProtocolError("received chunk belonging to a different session")

            seq = int(header["seq"])
            if not (0 <= seq < total_chunks):
                continue

            if sha256_bytes(payload) == str(header["checksum"]):
                received[seq] = payload
                print(f"CLIENT {client_id}: ACK chunk {seq + 1}/{total_chunks}", flush=True)
            else:
                received.pop(seq, None)
                print(f"CLIENT {client_id}: NACK corrupt chunk {seq + 1}/{total_chunks}", flush=True)

    def _request_retransmits(
        self,
        sock: socket.socket,
        client_id: str,
        total_chunks: int,
        received: dict[int, bytes],
        missing: list[int],
    ) -> list[int]:
        for start in range(0, len(missing), RETRANSMIT_BATCH_SIZE):
            batch = missing[start : start + RETRANSMIT_BATCH_SIZE]
            print(f"CLIENT {client_id}: requesting retransmit for {len(batch)} chunk(s)", flush=True)
            send_message(sock, {"type": "RETRANSMIT", "seqs": batch})
            self._receive_batch(sock, client_id, total_chunks, received)
        return sorted(seq for seq in range(total_chunks) if seq not in received)