"""protocol.py - Application-level protocol: message building, framing, file bytes.

Framing:  [4-byte big-endian length][JSON payload (UTF-8)]
File transfer: a "file" JSON message (metadata) is followed by exactly
`filesize` raw bytes on the same TCP connection.
"""
import json
import struct

CHUNK_SIZE = 64 * 1024            # 64 KB chunks for file transfer
MAX_MESSAGE_SIZE = 1024 * 1024    # sanity limit for a JSON message (1 MB)

HELLO, HELLO_ACK, TEXT, FILE = "hello", "hello_ack", "text", "file"


# ---------- message builders ----------
def make_hello(peer_id, peer_name, port):
    return {"type": HELLO, "peer_id": peer_id, "peer_name": peer_name, "port": port}


def make_hello_ack(peer_id, peer_name, port):
    return {"type": HELLO_ACK, "peer_id": peer_id, "peer_name": peer_name, "port": port}


def make_text(sender_id, sender_name, message):
    return {"type": TEXT, "sender_id": sender_id, "sender_name": sender_name, "message": message}


def make_file(sender_id, sender_name, filename, filesize):
    return {"type": FILE, "sender_id": sender_id, "sender_name": sender_name,
            "filename": filename, "filesize": filesize}


# ---------- framing ----------
def send_json(sock, obj):
    """Encode obj as JSON and send it as [4-byte length][payload]."""
    payload = json.dumps(obj).encode("utf-8")
    sock.sendall(struct.pack("!I", len(payload)) + payload)


def recv_exact(sock, n):
    """Read exactly n bytes (recv() may return fewer, so loop). Raises ConnectionError."""
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("connection closed by peer")
        buf.extend(chunk)
    return bytes(buf)


def recv_json(sock):
    """Read one framed JSON message and return it as a dict."""
    (length,) = struct.unpack("!I", recv_exact(sock, 4))
    if length == 0 or length > MAX_MESSAGE_SIZE:
        raise ValueError(f"invalid message length: {length}")
    return json.loads(recv_exact(sock, length).decode("utf-8"))


# ---------- raw file bytes ----------
def send_file_bytes(sock, path, progress=None):
    """Send file contents in chunks (never loads the whole file in memory)."""
    sent = 0
    with open(path, "rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            sock.sendall(chunk)
            sent += len(chunk)
            if progress:
                progress(sent)
    return sent


def recv_file_bytes(sock, dest_path, filesize):
    """Receive exactly `filesize` bytes from sock and write them to dest_path."""
    remaining = filesize
    with open(dest_path, "wb") as f:
        while remaining > 0:
            chunk = sock.recv(min(CHUNK_SIZE, remaining))
            if not chunk:
                raise ConnectionError("connection lost during file transfer")
            f.write(chunk)
            remaining -= len(chunk)
