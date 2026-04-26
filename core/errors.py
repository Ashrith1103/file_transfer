from __future__ import annotations


class FileTransferError(RuntimeError):
    pass



class ProtocolError(FileTransferError):
    pass



class ChecksumMismatchError(FileTransferError):


    def __init__(self, expected: str, actual: str, context: str = "") -> None:
        label = f" ({context})" if context else ""
        super().__init__(f"checksum mismatch{label}: expected {expected}, got {actual}")
        self.expected = expected
        self.actual = actual


class RetransmitLimitError(FileTransferError):


    def __init__(self, max_retries: int, missing: int) -> None:
        super().__init__(
            f"transfer failed after {max_retries} retransmission attempt(s); "
            f"{missing} chunk(s) still missing"
        )
        self.max_retries = max_retries
        self.missing = missing
