"""Custom exceptions for the file transfer project."""

from __future__ import annotations


class FileTransferError(RuntimeError):
    """Base class for all project-level errors."""


class ProtocolError(FileTransferError):
    """Raised when the peer sends malformed or unexpected protocol data."""


class ChecksumMismatchError(FileTransferError):
    """Raised when a computed checksum does not match the expected value."""

    def __init__(self, expected: str, actual: str, context: str = "") -> None:
        label = f" ({context})" if context else ""
        super().__init__(f"checksum mismatch{label}: expected {expected}, got {actual}")
        self.expected = expected
        self.actual = actual


class RetransmitLimitError(FileTransferError):
    """Raised when the client exhausts all retransmission attempts."""

    def __init__(self, max_retries: int, missing: int) -> None:
        super().__init__(
            f"transfer failed after {max_retries} retransmission attempt(s); "
            f"{missing} chunk(s) still missing"
        )
        self.max_retries = max_retries
        self.missing = missing
