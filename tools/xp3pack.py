#!/usr/bin/env python3
"""XP3 packer matching arcusmaximus/KirikiriTools Xp3Pack.

Index adlr checksum is 0 so version.dll skips game decryption.
Filenames in the index are UTF-16LE; use forward slashes.
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

HEADER = bytes([0x58, 0x50, 0x33, 0x0D, 0x0A, 0x20, 0x0A, 0x1A, 0x8B, 0x67, 0x01])
FILE_CHUNK = 0x656C6946  # File
INFO_CHUNK = 0x6F666E69  # info
SEGM_CHUNK = 0x6D676573  # segm
ADLR_CHUNK = 0x726C6461  # adlr


def _chunk(kind: int, payload: bytes) -> bytes:
    return struct.pack("<I Q", kind, len(payload)) + payload


def pack_xp3(entries: list[tuple[str, bytes]], dest: Path, compress: bool = True) -> None:
    """entries: (archive_path, file_bytes). Same bytes may be listed under several names."""
    blobs: list[bytes] = []
    blob_id: dict[int, int] = {}
    files: list[tuple[str, int]] = []
    for name, data in entries:
        key = id(data) if not isinstance(data, (bytes, bytearray)) else hash((len(data), data[:64], data[-64:]))
        # content-address so aliases share one blob
        key = hashlib_sha(data)
        if key not in blob_id:
            blob_id[key] = len(blobs)
            blobs.append(data)
        files.append((name.replace("\\", "/"), blob_id[key]))

    packed: list[tuple[int, int, int, bool]] = []  # offset, orig, comp, compressed
    body = bytearray()
    for data in blobs:
        offset = len(HEADER) + 8 + len(body)
        orig = len(data)
        if compress:
            comp = zlib.compress(data, 9)
            body += comp
            packed.append((offset, orig, len(comp), True))
        else:
            body += data
            packed.append((offset, orig, orig, False))

    index = bytearray()
    index.append(0)  # uncompressed index
    index += b"\x00" * 8  # size placeholder
    for name, bid in files:
        off, orig, csz, is_comp = packed[bid]
        name_u = name.encode("utf-16le")
        nchars = len(name)
        info = struct.pack("<I Q Q H", 0, orig, csz, nchars) + name_u
        segm = struct.pack("<I Q Q Q", 1 if is_comp else 0, off, orig, csz)
        adlr = struct.pack("<I", 0)
        payload = _chunk(INFO_CHUNK, info) + _chunk(SEGM_CHUNK, segm) + _chunk(ADLR_CHUNK, adlr)
        index += _chunk(FILE_CHUNK, payload)
    struct.pack_into("<Q", index, 1, len(index) - 9)

    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as f:
        f.write(HEADER)
        f.write(struct.pack("<Q", 0))
        f.write(body)
        index_off = f.tell()
        f.write(index)
        f.seek(len(HEADER))
        f.write(struct.pack("<Q", index_off))


def hashlib_sha(data: bytes) -> bytes:
    import hashlib

    return hashlib.sha256(data).digest()


def list_xp3(path: Path) -> list[tuple[str, int, int]]:
    data = path.read_bytes()
    if data[:3] != b"XP3":
        raise ValueError("not XP3")
    index_off = struct.unpack_from("<Q", data, 11)[0]
    idx = data[index_off:]
    flag = idx[0]
    if flag != 0:
        raise ValueError(f"compressed index flag={flag}")
    size = struct.unpack_from("<Q", idx, 1)[0]
    pos = 9
    end = 9 + size
    out = []
    while pos < end:
        kind, csz = struct.unpack_from("<I Q", idx, pos)
        pos += 12
        chunk = idx[pos : pos + csz]
        pos += csz
        if kind != FILE_CHUNK:
            continue
        inner = 0
        name = ""
        orig = 0
        csize = 0
        while inner < len(chunk):
            ck, cs = struct.unpack_from("<I Q", chunk, inner)
            inner += 12
            payload = chunk[inner : inner + cs]
            inner += cs
            if ck == INFO_CHUNK:
                orig, csize, nlen = struct.unpack_from("<Q Q H", payload, 4)
                name = payload[22 : 22 + nlen * 2].decode("utf-16le")
        out.append((name, orig, csize))
    return out
