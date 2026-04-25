"""TCP server with per-client thread dispatch."""

from __future__ import annotations

import socket
import threading

from config import ServerConfig
from server.session import ClientSession


class FileTransferServer:
    """Multi-client TCP server.

    Each accepted connection is handed to a :class:`~server.session.ClientSession`
    running in a dedicated daemon thread, so sessions are fully isolated and
    the main accept loop is never blocked by session work.
    """

    def __init__(self, config: ServerConfig) -> None:
        self.config = config
        self._stop = threading.Event()
        self._sock: socket.socket | None = None
        self.bound_port: int = config.port

    def serve_forever(self) -> None:
        """Accept connections until :meth:`stop` is called."""
        self.config.storage_dir.mkdir(parents=True, exist_ok=True)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind((self.config.host, self.config.port))
            srv.listen()
            # Short timeout so the accept loop can check _stop periodically.
            srv.settimeout(0.5)
            self._sock = srv
            self.bound_port = srv.getsockname()[1]
            print(f"server listening on {self.config.host}:{self.bound_port}", flush=True)

            while not self._stop.is_set():
                try:
                    client_sock, address = srv.accept()
                except TimeoutError:
                    continue
                except OSError:
                    if self._stop.is_set():
                        break
                    raise

                session = ClientSession(client_sock, address, self.config)
                thread = threading.Thread(target=session.run, daemon=True)
                thread.start()

    def stop(self) -> None:
        """Signal the server to stop accepting new connections."""
        self._stop.set()
        if self._sock:
            self._sock.close()
