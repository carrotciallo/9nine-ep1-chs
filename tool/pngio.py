"""极小 PNG 读写（8bit RGBA/RGB，非隔行），只依赖标准库 `zlib`/`struct`。

项目只需要两类用途：
  * 把解出来的 TLG 贴图存成 PNG 便于人工检查（`script/check_tlg.py`）；
  * 读入外部渲染好的 PNG（如 PowerShell GDI+ 画的中文标签）再编码回 TLG。

不支持：隔行、16bit、调色板、tRNS 之外的奇怪组合。
"""

from __future__ import annotations

import struct
import zlib

SIG = b"\x89PNG\r\n\x1a\n"


def _chunks(data: bytes):
    if data[:8] != SIG:
        raise ValueError("不是 PNG")
    pos = 8
    while pos < len(data):
        (length,) = struct.unpack_from(">I", data, pos)
        ctype = data[pos + 4: pos + 8]
        body = data[pos + 8: pos + 8 + length]
        yield ctype, body
        pos += 12 + length


def read(data: bytes) -> tuple[int, int, bytes]:
    """返回 (width, height, RGBA8 像素)。灰度/RGB 会补 alpha=255。"""
    w = h = None
    bit_depth = color_type = interlace = None
    idat = bytearray()
    palette = None
    trns = None
    for ctype, body in _chunks(data):
        if ctype == b"IHDR":
            w, h, bit_depth, color_type, _comp, _filt, interlace = struct.unpack(">IIBBBBB", body)
        elif ctype == b"PLTE":
            palette = body
        elif ctype == b"tRNS":
            trns = body
        elif ctype == b"IDAT":
            idat += body
        elif ctype == b"IEND":
            break
    if interlace:
        raise ValueError("不支持隔行 PNG")
    if bit_depth != 8:
        raise ValueError(f"只支持 8bit，得到 {bit_depth}")
    if color_type == 6:
        channels = 4
    elif color_type == 2:
        channels = 3
    elif color_type == 0:
        channels = 1
    elif color_type == 3:
        channels = 1
    else:
        raise ValueError(f"不支持的颜色类型 {color_type}")
    raw = zlib.decompress(bytes(idat))
    stride = w * channels
    out = bytearray(w * h * 4)
    prev = bytearray(stride)
    pos = 0
    for y in range(h):
        ftype = raw[pos]
        pos += 1
        line = bytearray(raw[pos: pos + stride])
        pos += stride
        if ftype == 1:
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 0xFF
        elif ftype == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ftype == 3:
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif ftype == 4:
            for i in range(stride):
                a = line[i - channels] if i >= channels else 0
                b = prev[i]
                c = prev[i - channels] if i >= channels else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pred) & 0xFF
        elif ftype != 0:
            raise ValueError(f"未知过滤类型 {ftype}")
        base = y * w * 4
        if color_type == 6:
            out[base: base + w * 4] = line
        elif color_type == 2:
            for x in range(w):
                out[base + x * 4: base + x * 4 + 3] = line[x * 3: x * 3 + 3]
                out[base + x * 4 + 3] = 255
        elif color_type == 0:
            for x in range(w):
                g = line[x]
                out[base + x * 4: base + x * 4 + 4] = bytes((g, g, g, 255))
        else:  # 调色板
            for x in range(w):
                idx = line[x]
                r, g, b = palette[idx * 3: idx * 3 + 3]
                a = trns[idx] if trns and idx < len(trns) else 255
                out[base + x * 4: base + x * 4 + 4] = bytes((r, g, b, a))
        prev = line
    return w, h, bytes(out)


def write(w: int, h: int, rgba: bytes, level: int = 9) -> bytes:
    """把 RGBA8 像素写成 PNG（过滤类型 0，够用）。"""
    if len(rgba) != w * h * 4:
        raise ValueError("像素长度与尺寸不符")
    raw = bytearray()
    stride = w * 4
    for y in range(h):
        raw.append(0)
        raw += rgba[y * stride:(y + 1) * stride]

    def chunk(ctype: bytes, body: bytes) -> bytes:
        return (struct.pack(">I", len(body)) + ctype + body
                + struct.pack(">I", zlib.crc32(ctype + body) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    return (SIG + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), level))
            + chunk(b"IEND", b""))
