from __future__ import annotations

import os
import shutil
import threading
import time
import unittest
import uuid
from pathlib import Path

from client import FileTransferClient
from config import ServerConfig
from core import sha256_file
from server import FileTransferServer


def _make_server(tmp: Path, drop: float = 0.35, corrupt: float = 0.35) -> FileTransferServer:
    return FileTransferServer(
        ServerConfig(
            host="127.0.0.1",
            port=0,
            chunk_size=256,
            drop_rate=drop,
            corrupt_rate=corrupt,
            storage_dir=tmp / "storage",
        )
    )


def _start(server: FileTransferServer) -> threading.Thread:
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    deadline = time.time() + 5
    while server.bound_port == 0 and time.time() < deadline:
        time.sleep(0.02)
    return t


class TestSingleClientTransfer(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path("test_artifacts") / uuid.uuid4().hex
        self.tmp.mkdir(parents=True)
        self.server = _make_server(self.tmp)
        self.thread = _start(self.server)
        self.downloads = self.tmp / "downloads"
        self.downloads.mkdir()

    def tearDown(self) -> None:
        self.server.stop()
        self.thread.join(timeout=3)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _client(self, max_retries: int = 15) -> FileTransferClient:
        return FileTransferClient(
            "127.0.0.1", self.server.bound_port,
            max_retries=max_retries, output_dir=self.downloads,
        )

    def test_binary_file_round_trip(self) -> None:
        src = self.tmp / "data.bin"
        src.write_bytes(os.urandom(8_193))
        out = self._client().transfer(src)
        self.assertEqual(sha256_file(src), sha256_file(out))

    def test_empty_file(self) -> None:
        src = self.tmp / "empty.bin"
        src.write_bytes(b"")
        out = self._client().transfer(src)
        self.assertEqual(b"", out.read_bytes())

    def test_single_byte_file(self) -> None:
        src = self.tmp / "one.bin"
        src.write_bytes(b"\xAB")
        out = self._client().transfer(src)
        self.assertEqual(b"\xAB", out.read_bytes())

    def test_exact_chunk_boundary(self) -> None:
        src = self.tmp / "exact.bin"
        src.write_bytes(os.urandom(256))
        out = self._client().transfer(src)
        self.assertEqual(src.read_bytes(), out.read_bytes())

    def test_large_file(self) -> None:
        src = self.tmp / "large.bin"
        src.write_bytes(os.urandom(1_048_576))
        out = self._client().transfer(src)
        self.assertEqual(sha256_file(src), sha256_file(out))

    def test_clean_server_no_retransmit(self) -> None:

        clean = _make_server(self.tmp, drop=0.0, corrupt=0.0)
        t = _start(clean)
        try:
            src = self.tmp / "clean.bin"
            src.write_bytes(os.urandom(4_096))
            client = FileTransferClient(
                "127.0.0.1", clean.bound_port,
                max_retries=0, output_dir=self.downloads,
            )
            out = client.transfer(src)
            self.assertEqual(src.read_bytes(), out.read_bytes())
        finally:
            clean.stop()
            t.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
