"""Chunk format, framing helpers, and message-level constants.

Wire format
-----------
Every message is framed as:

    [ 4-byte big-endian header-length ][ JSON header ][ optional binary payload ]

The header is a JSON object that always contains a ``type`` field and an
auto-injected ``payload_length`` field (set by :func:`send_message`).  The
payload immediately follows the header with no separator.

Message types
-------------
UPLOAD      client → server   File bytes + source SHA-256
META        server → client   Session metadata, chunk count, full-file SHA-256
CHUNK       server → client   One sequence-numbered chunk + per-chunk SHA-256
END_BATCH   server → client   Marks the end of a chunk batch
RETRANSMIT  client → server   Request re-send of listed sequence numbers
DONE        client → server   Confirms final checksum matched; closes session
ERROR       either direction  Reports a fatal protocol error
"""

from __future__ import annotations

import json
import os
import struct
from dataclasses import dataclass
from pathlib import Path
from socket import socket
from typing import Any

from core.checksum import sha256_bytes
from core.errors import ProtocolError
from config import CHUNK_SIZE, LENGTH_PREFIX_SIZE, MAX_HEADER_SIZE


# ── Data types ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Chunk:
    """A single fixed-size fragment of a file, ready to transmit."""

    seq: int
    data: bytes
    digest: str  # SHA-256 of *data*


# ── Framing ───────────────────────────────────────────────────────────────────


def send_message(sock: socket, header: dict[str, Any], payload: bytes = b"") -> None:
    """Frame and send a message over *sock*.

    *header* must be JSON-serialisable.  ``payload_length`` is injected
    automatically; callers must not set it manually.
    """
    header = dict(header)
    header["payload_length"] = len(payload)
    encoded = json.dumps(header, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_HEADER_SIZE:
        raise ProtocolError(f"header exceeds maximum size ({len(encoded)} > {MAX_HEADER_SIZE})")
    sock.sendall(struct.pack("!I", len(encoded)))
    sock.sendall(encoded)
    if payload:
        sock.sendall(payload)


def receive_message(sock: socket) -> tuple[dict[str, Any], bytes]:
    """Read and return the next framed message from *sock*.

    Returns a ``(header, payload)`` tuple.  Raises :class:`~core.errors.ProtocolError`
    on any framing violation.
    """
    raw = _read_exact(sock, LENGTH_PREFIX_SIZE)
    header_size = struct.unpack("!I", raw)[0]
    if not (0 < header_size <= MAX_HEADER_SIZE):
        raise ProtocolError(f"invalid header length: {header_size}")

    header: dict[str, Any] = json.loads(_read_exact(sock, header_size).decode("utf-8"))
    payload_length = int(header.get("payload_length", 0))
    if payload_length < 0:
        raise ProtocolError("negative payload_length in header")
    payload = _read_exact(sock, payload_length) if payload_length else b""
    return header, payload


def _read_exact(sock: socket, size: int) -> bytes:
    """Read exactly *size* bytes from *sock*, blocking until satisfied."""
    buf: list[bytes] = []
    remaining = size
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ProtocolError("connection closed unexpectedly")
        buf.append(chunk)
        remaining -= len(chunk)
    return b"".join(buf)


# ── Chunking ──────────────────────────────────────────────────────────────────


def split_bytes(data: bytes, chunk_size: int = CHUNK_SIZE) -> list[Chunk]:
    """Split *data* into fixed-size :class:`Chunk` objects.

    Each chunk is tagged with a monotonically increasing sequence number and
    the SHA-256 digest of its payload, enabling per-chunk integrity checks on
    the receiving side.

    Empty *data* produces a single zero-length chunk (seq=0).  This ensures
    the protocol round-trip completes cleanly for zero-byte files: the server
    sends one chunk, the client reassembles it, and the full-file checksum of
    ``b""`` matches on both sides.
    """
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be positive, got {chunk_size}")
    slices = _slice(data, chunk_size)
    return [Chunk(seq=i, data=part, digest=sha256_bytes(part)) for i, part in enumerate(slices)]


def _slice(data: bytes, chunk_size: int) -> list[bytes]:
    if not data:
        return [b""]
    return [data[i : i + chunk_size] for i in range(0, len(data), chunk_size)]


# ── Atomic file write ─────────────────────────────────────────────────────────


def atomic_write(path: Path, data: bytes) -> None:
    """Write *data* to *path* atomically.

    A sibling temp file is written and fsynced before being renamed into place,
    so a crash mid-write never leaves *path* in a partially-written state.
    The temp file is cleaned up on any exception.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with tmp.open("wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def raise_if_error(header: dict[str, Any]) -> None:
    """Raise :class:`~core.errors.ProtocolError` if *header* is an ERROR message."""
    if header.get("type") == "ERROR":
        raise ProtocolError(str(header.get("message", "server returned an error")))
