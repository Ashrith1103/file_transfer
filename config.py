\
\
\
\


from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path




SERVER_HOST: str = "127.0.0.1"
SERVER_PORT: int = 5001


CLIENT_CONNECT_TIMEOUT: float = 10.0



CLIENT_SOCKET_TIMEOUT: float = 30.0
SERVER_CLIENT_SOCKET_TIMEOUT: float = 60.0



CHUNK_SIZE: int = 1024



MAX_HEADER_SIZE: int = 64 * 1024


LENGTH_PREFIX_SIZE: int = 4





MAX_RETRIES: int = 5



SERVER_STORAGE_DIR: Path = Path("server_storage")
CLIENT_DOWNLOAD_DIR: Path = Path("client_downloads")




DROP_RATE: float = 0.0



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
