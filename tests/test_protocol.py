"""Unit tests for core protocol primitives (no sockets needed)."""

from __future__ import annotations

import unittest

from core.checksum import sha256_bytes, sha256_file
from core.errors import ChecksumMismatchError, ProtocolError, RetransmitLimitError
from core.protocol import atomic_write, split_bytes
import tempfile
from pathlib import Path


class TestSplitBytes(unittest.TestCase):
    def test_splits_into_correct_chunk_count(self) -> None:
        data = b"x" * 10
        chunks = split_bytes(data, chunk_size=3)
        self.assertEqual(4, len(chunks))  # 3+3+3+1

    def test_sequence_numbers_are_monotonic(self) -> None:
        chunks = split_bytes(b"hello world", chunk_size=2)
        self.assertEqual(list(range(len(chunks))), [c.seq for c in chunks])

    def test_chunk_data_reassembles_correctly(self) -> None:
        data = b"abcdefghij"
        chunks = split_bytes(data, chunk_size=3)
        self.assertEqual(data, b"".join(c.data for c in chunks))

    def test_empty_input_produces_one_empty_chunk(self) -> None:
        chunks = split_bytes(b"")
        self.assertEqual(1, len(chunks))
        self.assertEqual(0, chunks[0].seq)
        self.assertEqual(b"", chunks[0].data)

    def test_each_chunk_digest_matches_its_data(self) -> None:
        chunks = split_bytes(b"hello world", chunk_size=4)
        for chunk in chunks:
            self.assertEqual(sha256_bytes(chunk.data), chunk.digest)

    def test_invalid_chunk_size_raises(self) -> None:
        with self.assertRaises(ValueError):
            split_bytes(b"data", chunk_size=0)

    def test_exact_chunk_boundary(self) -> None:
        data = b"x" * 9
        chunks = split_bytes(data, chunk_size=3)
        self.assertEqual(3, len(chunks))


class TestChecksum(unittest.TestCase):
    def test_sha256_bytes_known_value(self) -> None:
        # echo -n "" | sha256sum → e3b0c44298fc1c149afb...
        self.assertTrue(sha256_bytes(b"").startswith("e3b0c4"))

    def test_sha256_bytes_consistency(self) -> None:
        self.assertEqual(sha256_bytes(b"hello"), sha256_bytes(b"hello"))

    def test_sha256_file_matches_sha256_bytes(self) -> None:
        data = b"test file content"
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(data)
            path = Path(f.name)
        try:
            self.assertEqual(sha256_bytes(data), sha256_file(path))
        finally:
            path.unlink()


class TestErrors(unittest.TestCase):
    def test_checksum_mismatch_error_message(self) -> None:
        err = ChecksumMismatchError("aaa", "bbb", "full file")
        self.assertIn("aaa", str(err))
        self.assertIn("bbb", str(err))
        self.assertIn("full file", str(err))

    def test_retransmit_limit_error_message(self) -> None:
        err = RetransmitLimitError(5, 3)
        self.assertIn("5", str(err))
        self.assertIn("3", str(err))

    def test_error_hierarchy(self) -> None:
        from core.errors import FileTransferError
        self.assertIsInstance(ProtocolError("x"), FileTransferError)
        self.assertIsInstance(ChecksumMismatchError("a", "b"), FileTransferError)
        self.assertIsInstance(RetransmitLimitError(1, 1), FileTransferError)


class TestAtomicWrite(unittest.TestCase):
    def test_write_and_read_back(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.bin"
            atomic_write(path, b"hello world")
            self.assertEqual(b"hello world", path.read_bytes())

    def test_creates_parent_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "deep" / "nested" / "file.bin"
            atomic_write(path, b"data")
            self.assertTrue(path.exists())

    def test_no_temp_file_left_on_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.bin"
            atomic_write(path, b"data")
            leftovers = list(Path(tmp).glob(".*"))
            self.assertEqual([], leftovers)


if __name__ == "__main__":
    unittest.main()
