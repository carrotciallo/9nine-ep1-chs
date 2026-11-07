#!/usr/bin/env python3
"""PSB (v2/v3) full parser, ported from FreeMote (UlyssesWu) semantics."""
import struct, sys
from pathlib import Path

class Psb:
    def __init__(self, data: bytes):
        self.d = data
        assert data[:3] == b"PSB"
        (self.version, self.hdr_len, self.off_names, self.off_str_off,
         self.off_str_data, self.off_chunk_off, self.off_chunk_len,
         self.off_chunk_data, self.off_entries) = struct.unpack_from("<HxxIIIIIII", data, 4) \
            if False else (struct.unpack_from("<H", data, 4)[0],) + struct.unpack_from("<8I", data, 8)
        # strings
        offs, _ = self._array_at(self.off_str_off)
        self.strings = []
        for o in offs:
            s = self.off_str_data + o
            e = data.find(b"\x00", s)
            self.strings.append(data[s:e].decode("utf-8", "replace"))
        # names
        charset, p = self._array_at(self.off_names)
        namesdata, p = self._array_at(p)
        nameidx, p = self._array_at(p)
        self.names = []
        for idx in nameidx:
            lst = []
            chr_ = namesdata[idx]
            while chr_ != 0:
                code = namesdata[chr_]
                lst.append((chr_ - charset[code]) & 0xFF)
                chr_ = code
            lst.reverse()
            self.names.append(bytes(lst).decode("utf-8", "replace"))
        self.root, _ = self._unpack(self.off_entries)

    def _int(self, pos, width):
        return int.from_bytes(self.d[pos:pos+width], "little")

    def _array_at(self, pos):
        t = self.d[pos]
        assert 0x0D <= t <= 0x14, f"array type {t:#x} at {pos:#x}"
        cw = t - 0x0D + 1
        count = self._int(pos + 1, cw)
        p = pos + 1 + cw
        et = self.d[p]; p += 1
        ew = et - 0x0C
        vals = [self._int(p + i * ew, ew) for i in range(count)]
        return vals, p + count * ew

    def _unpack(self, pos):
        t = self.d[pos]
        if t == 0x00 or t == 0x01: return None, pos + 1
        if t == 0x02: return False, pos + 1
        if t == 0x03: return True, pos + 1
        if t == 0x04: return 0, pos + 1
        if 0x05 <= t <= 0x0C:
            w = t - 0x04
            return self._int(pos + 1, w), pos + 1 + w
        if 0x0D <= t <= 0x14:
            return self._array_at(pos)
        if 0x15 <= t <= 0x18:
            w = t - 0x14
            idx = self._int(pos + 1, w)
            return ("str", idx, self.strings[idx] if idx < len(self.strings) else f"<bad {idx}>"), pos + 1 + w
        if 0x19 <= t <= 0x1C:
            w = t - 0x18
            return ("res", self._int(pos + 1, w)), pos + 1 + w
        if t == 0x1D: return 0.0, pos + 1
        if t == 0x1E: return struct.unpack_from("<f", self.d, pos + 1)[0], pos + 5
        if t == 0x1F: return struct.unpack_from("<d", self.d, pos + 1)[0], pos + 9
        if t == 0x20:  # List
            offs, base = self._array_at(pos + 1)
            return [self._unpack(base + o)[0] for o in offs], base + (max(offs) if offs else 0)
        if t == 0x21:  # Objects
            nameidx, p = self._array_at(pos + 1)
            offs, base = self._array_at(p)
            out = {}
            for ni, o in zip(nameidx, offs):
                out[self.names[ni]] = self._unpack(base + o)[0]
            return out, base + (max(offs) if offs else 0)
        if 0x22 <= t <= 0x25:
            w = t - 0x21
            return ("xres", self._int(pos + 1, w)), pos + 1 + w
        raise ValueError(f"unknown type {t:#x} at {pos:#x}")

def shape(v, depth=0, maxdepth=3):
    pad = "  " * depth
    if isinstance(v, dict):
        print(f"{pad}dict[{len(v)}] keys={list(v.keys())[:14]}")
        if depth < maxdepth:
            for k in list(v.keys())[:6]:
                print(f"{pad} {k}:")
                shape(v[k], depth + 1, maxdepth)
    elif isinstance(v, list):
        print(f"{pad}list[{len(v)}]")
        if depth < maxdepth and v:
            shape(v[0], depth + 1, maxdepth)
    elif isinstance(v, tuple):
        print(f"{pad}{v[0]}: {str(v[-1])[:60]!r}")
    else:
        print(f"{pad}{type(v).__name__}: {str(v)[:60]!r}")

if __name__ == "__main__":
    for f in sys.argv[1:]:
        p = Psb(Path(f).read_bytes())
        print(f"===== {f} ver={p.version} names={len(p.names)} strings={len(p.strings)}")
        print("names:", p.names[:40])
        shape(p.root)
