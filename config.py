"""All tuneable constants in one place.

Importing from config.py is the single source of truth for every
tunable value in the project.  Nothing else should hard-code these.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


# ── Network ──────────────────────────────────────────────────────────────────

SERVER_HOST: str = "127.0.0.1"
SERVER_PORT: int = 5001

# How long (seconds) the client waits for a connection to be established.
CLIENT_CONNECT_TIMEOUT: float = 10.0

# How long (seconds) either side waits for an individual socket read before
# treating the peer as dead.
CLIENT_SOCKET_TIMEOUT: float = 30.0
SERVER_CLIENT_SOCKET_TIMEOUT: float = 60.0

# ── Protocol ─────────────────────────────────────────────────────────────────

CHUNK_SIZE: int = 1024

# Maximum allowed header size (bytes).  Guards against malformed peers sending
# pathologically large JSON headers.
MAX_HEADER_SIZE: int = 64 * 1024

# Number of bytes used to encode the header length in each framed message.
LENGTH_PREFIX_SIZE: int = 4

# ── Reliability ───────────────────────────────────────────────────────────────

# Maximum number of retransmission rounds the client will attempt before
# giving up and raising ProtocolError.
MAX_RETRIES: int = 5

# ── Storage ───────────────────────────────────────────────────────────────────

SERVER_STORAGE_DIR: Path = Path("server_storage")
CLIENT_DOWNLOAD_DIR: Path = Path("client_downloads")

# ── Error simulation ─────────────────────────────────────────────────────────

# Probability (0.0 – 1.0) that a chunk is silently dropped on the first pass.
DROP_RATE: float = 0.0

# Probability (0.0 – 1.0) that a chunk's first byte is bit-flipped on the
# first pass.
CORRUPT_RATE: float = 0.0


@dataclass
class ServerConfig:
    host: str = SERVER_HOST
    port: int = SERVER_PORT
    chunk_size: int = CHUNK_SIZE
    drop_rate: float = DROP_RATE
    corrupt_rate: float = CORRUPT_RATE
    storage_dir: Path = field(default_factory=lambda: SERVER_STORAGE_DIR)
    client_socket_timeout: float = SERVER_CLIENT_SOCKET_TIMEOUT
