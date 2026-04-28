from __future__ import annotations

import argparse
from pathlib import Path

from config import (
    CLIENT_DOWNLOAD_DIR,
    CHUNK_SIZE,
    CORRUPT_RATE,
    DROP_RATE,
    MAX_RETRIES,
    SERVER_HOST,
    SERVER_PORT,
    ServerConfig,
)
from client import FileTransferClient
from core import sha256_file
from server import FileTransferServer


def _server_cmd(args: argparse.Namespace) -> None:
    server = FileTransferServer(
        ServerConfig(
            host=args.host,
            port=args.port,
            chunk_size=args.chunk_size,
            drop_rate=args.drop_rate,
            corrupt_rate=args.corrupt_rate,
            storage_dir=args.storage_dir,
        )
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.stop()


def _client_cmd(args: argparse.Namespace) -> None:
    client = FileTransferClient(
        host=args.host,
        port=args.port,
        max_retries=args.max_retries,
        output_dir=args.output_dir,
    )
    output = client.transfer(args.file)
    print("Transfer Successful")
    print(f"Saved : {output}")
    print(f"SHA256: {sha256_file(output)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BigEndian file transfer system")
    sub = parser.add_subparsers(dest="command", required=True)


    sp = sub.add_parser("server", help="Start the TCP server")
    sp.add_argument("--host", default=SERVER_HOST)
    sp.add_argument("--port", type=int, default=SERVER_PORT)
    sp.add_argument("--chunk-size", type=int, default=CHUNK_SIZE)
    sp.add_argument("--drop-rate", type=float, default=DROP_RATE,
                    help="Probability (0–1) of silently dropping a chunk on first pass")
    sp.add_argument("--corrupt-rate", type=float, default=CORRUPT_RATE,
                    help="Probability (0–1) of corrupting a chunk's first byte on first pass")
    sp.add_argument("--storage-dir", type=Path, default=Path("server_storage"))
    sp.set_defaults(func=_server_cmd)


    cp = sub.add_parser("client", help="Upload and verify a file")
    cp.add_argument("file", type=Path, help="Path to the file to transfer")
    cp.add_argument("--host", default=SERVER_HOST)
    cp.add_argument("--port", type=int, default=SERVER_PORT)
    cp.add_argument("--output-dir", type=Path, default=CLIENT_DOWNLOAD_DIR)
    cp.add_argument("--max-retries", type=int, default=MAX_RETRIES,
                    help="Max retransmission attempts before giving up")
    cp.set_defaults(func=_client_cmd)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
