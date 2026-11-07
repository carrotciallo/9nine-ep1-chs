#!/usr/bin/env python3
"""Kirikiri2 TVP text-stream scrambler (FE FE mode 0/1/2).

Header: FE FE <mode> FF FE
  mode 0: per-uint16 XOR  (legacy, buggy)
  mode 1: per-uint16 even/odd bit swap  (involution; used by 9-nine EP1)
  mode 2: zlib of UTF-16LE, 2×int64 sizes then compressed payload

Body after the 5-byte header is UTF-16LE code units, never a second BOM.
Newlines are CRLF. encode(decode(x)) is byte-identical for mode 0 and 1.
"""
from __future__ import annotations

import argparse
import struct
import sys
import zlib
from pathlib import Path

MAGIC = b"\xfe\xfe"
BOM = b"\xff\xfe"


def _mode1_swap(data: bytearray) -> None:
    for i in range(0, len(data) - 1, 2):
        c = data[i] | (data[i + 1] << 8)
        c = ((c & 0xAAAA) >> 1) | ((c & 0x5555) << 1)
        data[i] = c & 0xFF
        data[i + 1] = (c >> 8) & 0xFF


def _mode0_decode(data: bytearray) -> None:
    for i in range(0, len(data) - 1, 2):
        if data[i + 1] == 0 and data[i] < 0x20:
            continue
        data[i + 1] ^= data[i] & 0xFE
        data[i] ^= 1


def _mode0_encode(data: bytearray) -> None:
    for i in range(0, len(data) - 1, 2):
        if data[i + 1] == 0 and data[i] < 0x20:
            continue
        data[i] ^= 1
        data[i + 1] ^= data[i] & 0xFE


def decode_bytes(raw: bytes) -> tuple[int, str]:
    if len(raw) < 5 or raw[:2] != MAGIC:
        raise ValueError(f"not a Kirikiri scrambled text (head {raw[:5].hex()})")
    mode = raw[2]
    if raw[3:5] != BOM:
        raise ValueError(f"missing UTF-16LE BOM after mode, got {raw[3:5].hex()}")
    if mode == 2:
        if len(raw) < 21:
            raise ValueError("truncated mode-2 header")
        compressed_len, uncompressed_len = struct.unpack_from("<QQ", raw, 5)
        payload = raw[21 : 21 + compressed_len]
        body = zlib.decompress(payload)
        if len(body) != uncompressed_len:
            raise ValueError(
                f"mode2 size mismatch: zlib {len(body)} vs header {uncompressed_len}"
            )
        return mode, body.decode("utf-16-le")
    body = bytearray(raw[5:])
    if mode == 0:
        _mode0_decode(body)
    elif mode == 1:
        _mode1_swap(body)
    else:
        raise ValueError(f"unsupported scramble mode {mode}")
    return mode, bytes(body).decode("utf-16-le")


def encode_bytes(text: str, mode: int = 1) -> bytes:
    body = bytearray(text.encode("utf-16-le"))
    if mode == 1:
        _mode1_swap(body)
        return MAGIC + bytes([mode]) + BOM + bytes(body)
    if mode == 0:
        _mode0_encode(body)
        return MAGIC + bytes([mode]) + BOM + bytes(body)
    if mode == 2:
        raw_utf16 = bytes(body)
        compressed = zlib.compress(raw_utf16, 6)
        return (
            MAGIC
            + bytes([mode])
            + BOM
            + struct.pack("<QQ", len(compressed), len(raw_utf16))
            + compressed
        )
    raise ValueError(f"unsupported scramble mode {mode}")


def decode_file(path: Path) -> tuple[int, str]:
    return decode_bytes(path.read_bytes())


def encode_file(text: str, path: Path, mode: int = 1) -> None:
    path.write_bytes(encode_bytes(text, mode))


def _cli(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Kirikiri2 TVP text-stream scrambler")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("decode", help="scrambled binary -> UTF-8 text")
    d.add_argument("src")
    d.add_argument("dst")
    e = sub.add_parser("encode", help="UTF-8 text -> scrambled binary")
    e.add_argument("src")
    e.add_argument("dst")
    e.add_argument("--mode", type=int, default=1, choices=(0, 1, 2))
    t = sub.add_parser("roundtrip", help="decode+encode and cmp against src")
    t.add_argument("src")
    args = p.parse_args(argv)
    if args.cmd == "decode":
        mode, text = decode_file(Path(args.src))
        Path(args.dst).write_bytes(text.encode("utf-8"))
        print(f"decoded mode={mode} chars={len(text)} -> {args.dst}")
        return 0
    if args.cmd == "encode":
        text = Path(args.src).read_bytes().decode("utf-8")
        encode_file(text, Path(args.dst), args.mode)
        print(f"encoded mode={args.mode} -> {args.dst}")
        return 0
    src = Path(args.src)
    raw = src.read_bytes()
    mode, text = decode_bytes(raw)
    back = encode_bytes(text, mode)
    ok = back == raw
    print(f"{src.name}: mode={mode} chars={len(text)} roundtrip={'OK' if ok else 'FAIL'} "
          f"dlen={len(back)-len(raw)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(_cli())
