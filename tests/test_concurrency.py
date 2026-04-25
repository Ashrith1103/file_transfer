"""Concurrency tests: multiple simultaneous clients, session isolation."""

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


def _start_server(tmp: Path) -> FileTransferServer:
    server = FileTransferServer(
        ServerConfig(
            host="127.0.0.1",
            port=0,
            chunk_size=256,
            drop_rate=0.3,
            corrupt_rate=0.3,
            storage_dir=tmp / "storage",
        )
    )
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    deadline = time.time() + 5
    while server.bound_port == 0 and time.time() < deadline:
        time.sleep(0.02)
    return server


class TestConcurrency(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path("test_artifacts") / uuid.uuid4().hex
        self.tmp.mkdir(parents=True)
        self.server = _start_server(self.tmp)
        self.downloads = self.tmp / "downloads"
        self.downloads.mkdir()

    def tearDown(self) -> None:
        self.server.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _client(self) -> FileTransferClient:
        return FileTransferClient(
            "127.0.0.1", self.server.bound_port,
            max_retries=15, output_dir=self.downloads,
        )

    def test_five_concurrent_clients_isolated(self) -> None:
        """Five clients running simultaneously must each get their own file back intact."""
        sources = []
        for i in range(5):
            p = self.tmp / f"client_{i}.dat"
            p.write_bytes(os.urandom(1_000 + i * 500))
            sources.append(p)

        errors: list[BaseException] = []
        outputs: dict[Path, Path] = {}
        lock = threading.Lock()

        def run(src: Path) -> None:
            try:
                out = self._client().transfer(src)
                with lock:
                    outputs[src] = out
            except BaseException as exc:
                with lock:
                    errors.append(exc)

        threads = [threading.Thread(target=run, args=(s,)) for s in sources]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)

        self.assertFalse(errors, f"client errors: {errors}")
        self.assertEqual(set(sources), set(outputs))
        for src, out in outputs.items():
            self.assertEqual(sha256_file(src), sha256_file(out), f"mismatch for {src.name}")

    def test_ten_concurrent_clients(self) -> None:
        """Stress test: ten clients, small files, verify all complete successfully."""
        sources = [self.tmp / f"stress_{i}.bin" for i in range(10)]
        for p in sources:
            p.write_bytes(os.urandom(512))

        errors: list[BaseException] = []
        outputs: list[Path] = []
        lock = threading.Lock()

        def run(src: Path) -> None:
            try:
                out = self._client().transfer(src)
                with lock:
                    outputs.append(out)
            except BaseException as exc:
                with lock:
                    errors.append(exc)

        threads = [threading.Thread(target=run, args=(s,)) for s in sources]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)

        self.assertFalse(errors, f"errors: {errors}")
        self.assertEqual(10, len(outputs))


if __name__ == "__main__":
    unittest.main()
