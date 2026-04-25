# BigEndian File Transfer — Refactored Package Structure

Python implementation of both the single-client and multi-client file transfer
challenges.  Uses only the Python standard library (3.10+).

## Project structure

```
file_transfer/
├── core/
│   ├── __init__.py
│   ├── protocol.py     # Chunk format, framing, atomic write
│   ├── checksum.py     # SHA-256 helpers
│   └── errors.py       # Custom exceptions
├── server/
│   ├── __init__.py
│   ├── server.py       # TCP server, client dispatch
│   └── session.py      # Per-client session handler
├── client/
│   ├── __init__.py
│   └── client.py       # Upload, receive, verify
├── simulation/
│   ├── __init__.py
│   └── network.py      # Packet drop / corruption simulation
├── tests/
│   ├── test_protocol.py    # Unit tests (no sockets)
│   ├── test_transfer.py    # Single-client integration tests
│   └── test_concurrency.py # Multi-client concurrency tests
├── config.py           # All tuneable constants in one place
└── main.py             # Entry point to run everything
```

## Run

Start the server (from inside the `file_transfer/` directory):

```bash
python main.py server --drop-rate 0.2 --corrupt-rate 0.2
```

Transfer a file:

```bash
python main.py client path/to/data.txt
```

### CLI flags

**server**

| Flag | Default | Description |
|------|---------|-------------|
| `--host` | `127.0.0.1` | Bind address |
| `--port` | `5001` | Listen port |
| `--chunk-size` | `1024` | Bytes per chunk |
| `--drop-rate` | `0.0` | Probability a chunk is dropped on the first pass |
| `--corrupt-rate` | `0.0` | Probability a chunk is corrupted on the first pass |
| `--storage-dir` | `server_storage` | Where uploaded files are saved |

**client**

| Flag | Default | Description |
|------|---------|-------------|
| `--host` | `127.0.0.1` | Server address |
| `--port` | `5001` | Server port |
| `--output-dir` | `client_downloads` | Where received files are written |
| `--max-retries` | `5` | Max retransmission rounds before giving up |

## Test

```bash
python -m unittest discover -s tests -v
```

Tests cover:

| Suite | Tests |
|-------|-------|
| `test_protocol` | split_bytes (empty, boundary, reassembly), checksums, error hierarchy, atomic_write |
| `test_transfer` | binary, empty, 1-byte, exact-boundary, 1 MB, clean-server (max_retries=0) |
| `test_concurrency` | 5 concurrent clients, 10 concurrent clients (stress) |

## Protocol wire format

```
[ 4-byte big-endian header-length ][ JSON header ][ optional binary payload ]
```

| Message | Direction | Purpose |
|---------|-----------|---------|
| `UPLOAD` | client → server | File bytes + source SHA-256 |
| `META` | server → client | Session metadata, chunk count, full-file SHA-256 |
| `CHUNK` | server → client | One sequence-numbered chunk + per-chunk SHA-256 |
| `END_BATCH` | server → client | Marks end of a chunk batch |
| `RETRANSMIT` | client → server | Request re-send of listed sequence numbers |
| `DONE` | client → server | Confirms final checksum matched |
| `ERROR` | either | Reports a fatal protocol error |

### Reliability flow

1. Server sends all chunks **shuffled** (simulates out-of-order delivery).
2. Client verifies each chunk's SHA-256; corrupted chunks are discarded.
3. After `END_BATCH`, client sends a `RETRANSMIT` listing missing/corrupt seqs.
4. Server resends those chunks **cleanly** (no error simulation on retransmits).
5. Repeat until all chunks received or `--max-retries` is exhausted.
6. Client verifies the full-file SHA-256 and writes atomically via temp-file rename.
