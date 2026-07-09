"""Minimal stdlib WebSocket client (RFC 6455) — read path for live-data frames.

abax ships no third-party WebSocket dependency, so this module implements just
enough of RFC 6455 to *consume* a text-frame stream: the opening HTTP Upgrade
handshake, server-frame parsing (unmasked, per spec), reassembly of continuation
frames, and the control-frame courtesies (reply to ping, honour close). Frames
we send — the handshake, pongs, the close — are masked, as a client must.

Only :func:`ws_messages` touches a socket. The handshake-accept computation and
the frame codec are pure functions so they can be unit-tested against the
worked examples in RFC 6455 without a live server.
"""

from __future__ import annotations

import base64
import hashlib
import os
import socket
import ssl
import struct
import threading
from typing import Iterator
from urllib.parse import urlsplit

#: The magic GUID a server concatenates with the client key (RFC 6455 §1.3).
_WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

OP_CONT = 0x0
OP_TEXT = 0x1
OP_BINARY = 0x2
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA


class WSError(Exception):
    """Raised on a failed handshake or a protocol violation."""


# -- pure helpers (unit-tested) -------------------------------------------

def accept_key(client_key: str) -> str:
    """The ``Sec-WebSocket-Accept`` value a server derives from *client_key*."""
    digest = hashlib.sha1((client_key + _WS_GUID).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def encode_frame(opcode: int, payload: bytes = b"", *, mask: bool = True) -> bytes:
    """Encode a single final frame. Client frames are masked (RFC 6455 §5.3)."""
    fin_op = 0x80 | (opcode & 0x0F)
    length = len(payload)
    if length < 126:
        header = struct.pack("!BB", fin_op, (0x80 if mask else 0) | length)
    elif length < 65536:
        header = struct.pack("!BBH", fin_op, (0x80 if mask else 0) | 126, length)
    else:
        header = struct.pack("!BBQ", fin_op, (0x80 if mask else 0) | 127, length)
    if not mask:
        return header + payload
    key = os.urandom(4)
    masked = bytes(b ^ key[i % 4] for i, b in enumerate(payload))
    return header + key + masked


def decode_frame(data: bytes) -> "tuple[int, int, bytes, int] | None":
    """Parse one frame from the front of *data*.

    Returns ``(fin, opcode, payload, consumed)`` or ``None`` if *data* does not
    yet hold a whole frame. Handles the masked case too (servers should not mask,
    but we unmask defensively).
    """
    if len(data) < 2:
        return None
    b0, b1 = data[0], data[1]
    fin = (b0 & 0x80) >> 7
    opcode = b0 & 0x0F
    masked = (b1 & 0x80) >> 7
    length = b1 & 0x7F
    off = 2
    if length == 126:
        if len(data) < off + 2:
            return None
        (length,) = struct.unpack("!H", data[off:off + 2])
        off += 2
    elif length == 127:
        if len(data) < off + 8:
            return None
        (length,) = struct.unpack("!Q", data[off:off + 8])
        off += 8
    mask_key = b""
    if masked:
        if len(data) < off + 4:
            return None
        mask_key = data[off:off + 4]
        off += 4
    if len(data) < off + length:
        return None
    payload = data[off:off + length]
    if masked:
        payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
    return (fin, opcode, payload, off + length)


# -- socket path ----------------------------------------------------------

def _connect(url: str, timeout: float) -> "tuple[socket.socket, str, str]":
    parts = urlsplit(url)
    secure = parts.scheme == "wss"
    host = parts.hostname or ""
    if not host:
        raise WSError(f"no host in WebSocket URL: {url!r}")
    port = parts.port or (443 if secure else 80)
    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"
    sock = socket.create_connection((host, port), timeout=timeout)
    if secure:
        ctx = ssl.create_default_context()
        sock = ctx.wrap_socket(sock, server_hostname=host)
    host_header = f"{host}:{port}" if parts.port else host
    return sock, host_header, path


def _handshake(sock: socket.socket, host_header: str, path: str) -> None:
    client_key = base64.b64encode(os.urandom(16)).decode("ascii")
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host_header}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {client_key}\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    )
    sock.sendall(request.encode("ascii"))
    # Read response headers up to the blank line.
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(1024)
        if not chunk:
            raise WSError("connection closed during handshake")
        buf += chunk
        if len(buf) > 65536:
            raise WSError("handshake response too large")
    head = buf.split(b"\r\n\r\n", 1)[0].decode("latin-1")
    lines = head.split("\r\n")
    if "101" not in lines[0]:
        raise WSError(f"handshake rejected: {lines[0]!r}")
    got = ""
    for line in lines[1:]:
        name, _, value = line.partition(":")
        if name.strip().lower() == "sec-websocket-accept":
            got = value.strip()
    if got != accept_key(client_key):
        raise WSError("handshake accept-key mismatch")


class _FrameReader:
    """Buffered reader that yields decoded frames from a socket."""

    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock
        self._buf = b""
        sock.settimeout(0.5)

    def next_frame(self, stop_event: threading.Event) -> "tuple[int, int, bytes] | None":
        while not stop_event.is_set():
            parsed = decode_frame(self._buf)
            if parsed is not None:
                fin, opcode, payload, consumed = parsed
                self._buf = self._buf[consumed:]
                return (fin, opcode, payload)
            try:
                chunk = self._sock.recv(4096)
            except TimeoutError:
                continue
            except OSError:
                return None
            if not chunk:
                return None
            self._buf += chunk
        return None


def ws_messages(url: str, *, stop_event: threading.Event,
                timeout: float = 10.0) -> Iterator[str]:
    """Connect to *url* and yield decoded text messages until closed/stopped.

    Continuation frames are reassembled; pings are answered with a pong; a close
    frame ends the stream. Binary and pong frames are ignored. Raises
    :class:`WSError` on a failed handshake (the caller reconnects).
    """
    sock, host_header, path = _connect(url, timeout)
    try:
        _handshake(sock, host_header, path)
        reader = _FrameReader(sock)
        parts: list[bytes] = []
        while not stop_event.is_set():
            frame = reader.next_frame(stop_event)
            if frame is None:
                break
            fin, opcode, payload = frame
            if opcode in (OP_TEXT, OP_BINARY, OP_CONT):
                parts.append(payload)
                if fin:
                    message = b"".join(parts)
                    parts = []
                    yield message.decode("utf-8", "replace")
            elif opcode == OP_PING:
                try:
                    sock.sendall(encode_frame(OP_PONG, payload))
                except OSError:
                    break
            elif opcode == OP_CLOSE:
                break
    finally:
        try:
            sock.close()
        except OSError:
            pass
