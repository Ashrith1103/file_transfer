\
\
\
\
\


from __future__ import annotations

import os
import shutil
import sys
import threading
import time
from pathlib import Path

from client import FileTransferClient
from config import ServerConfig
from core import sha256_file
from server import FileTransferServer


ROOT = Path("test_artifacts") / "manual_multi_file_test"
INPUT_DIR = ROOT / "inputs"
OUTPUT_DIR = ROOT / "downloads"
STORAGE_DIR = ROOT / "server_storage"


def create_input_files() -> list[Path]:
    if ROOT.exists():
        shutil.rmtree(ROOT, ignore_errors=True)
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    files = [
        ("small_text.txt", b"Hello BigEndian!\n" * 20),
        ("empty_file.txt", b""),
        ("one_chunk.bin", os.urandom(1024)),
        ("medium_binary.bin", os.urandom(256 * 1024)),
        ("large_binary.bin", os.urandom(2 * 1024 * 1024)),
    ]

    paths: list[Path] = []
    for name, data in files:
        path = INPUT_DIR / name
        path.write_bytes(data)
        paths.append(path)
    return paths


def start_server() -> FileTransferServer:
    server = FileTransferServer(
        ServerConfig(
            host="127.0.0.1",
            port=0,
            chunk_size=1024,
            drop_rate=0.10,
            corrupt_rate=0.10,
            storage_dir=STORAGE_DIR,
        )
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    deadline = time.time() + 5
    while server.bound_port == 0 and time.time() < deadline:
        time.sleep(0.05)
    if server.bound_port == 0:
        raise RuntimeError("server did not start")
    return server


def run_client(source: Path, server: FileTransferServer, results: dict[Path, Path], errors: list[str], lock: threading.Lock) -> None:
    try:
        client = FileTransferClient(
            host="127.0.0.1",
            port=server.bound_port,
            max_retries=20,
            output_dir=OUTPUT_DIR,
        )
        output = client.transfer(source)
        with lock:
            results[source] = output
    except BaseException as exc:
        with lock:
            errors.append(f"{source.name}: {exc}")


def main() -> int:
    sources = create_input_files()
    server = start_server()
    print(f"Server started on 127.0.0.1:{server.bound_port}")
    print(f"Sending {len(sources)} files at the same time...\n")

    results: dict[Path, Path] = {}
    errors: list[str] = []
    lock = threading.Lock()

    threads = [
        threading.Thread(target=run_client, args=(source, server, results, errors, lock))
        for source in sources
    ]
    start = time.time()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)

    server.stop()
    elapsed = time.time() - start

    print("Transfer Summary")
    print("=" * 60)
    success_count = 0
    for source in sources:
        output = results.get(source)
        if output and output.exists() and sha256_file(source) == sha256_file(output):
            success_count += 1
            print(f"OK     {source.name:<24} -> {output}")
        else:
            print(f"FAILED {source.name}")
    for error in errors:
        print(f"ERROR  {error}")
    print("-" * 60)
    print(f"{success_count} / {len(sources)} transfers succeeded in {elapsed:.2f}s")

    return 0 if success_count == len(sources) and not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
