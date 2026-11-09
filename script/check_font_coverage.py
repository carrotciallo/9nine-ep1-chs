"""检查简中语料的字形覆盖率：直接读 OTF/TTF 的 cmap 表，不依赖第三方库。

用法（从项目根执行）：

    # 1) 先把官方字体解出来（字体在 data.xp3 的 font/ 目录，小写路径）
    mamba run -n GalRev python script/check_font_coverage.py --extract official_fonts

    # 2) 再看语料缺哪些字
    mamba run -n GalRev python script/check_font_coverage.py --font resource/official_fonts/font/sourcehansanstc-bold.otf

支持 cmap format 4（BMP）与 format 12（全平面），足以覆盖 Source Han 系列。
"""

from __future__ import annotations

import argparse
import hashlib
import mmap
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tool import cx, textset, xp3

# 官方 data.xp3 里的字体条目（全部小写路径）
FONT_NAMES = [
    "font/sourcehansansjp-medium.otf", "font/sourcehansansjp-bold.otf", "font/sourcehansansjp-heavy.otf",
    "font/sourcehanserifjp-bold.otf", "font/sourcehanserifjp-heavy.otf",
    "font/sourcehansanstc-medium.otf", "font/sourcehansanstc-bold.otf", "font/sourcehansanstc-heavy.otf",
    "font/sourcehanseriftc-bold.otf", "font/sourcehanseriftc-heavy.otf",
]


def md5_name(path: str) -> str:
    return hashlib.md5(path.encode("utf-16-le")).hexdigest()


def extract_fonts(out_dir: str, archive: str, profile: str) -> list[str]:
    crypt = cx.CxCrypt.load(profile)
    fp = open(archive, "rb")
    mm = mmap.mmap(fp.fileno(), 0, access=mmap.ACCESS_READ)
    ents = {e.name: e for e in xp3.parse_xp3(mm, show_log=False) if e.name and e.segms}
    out = []
    for name in FONT_NAMES:
        e = ents.get(md5_name(name))
        if e is None:
            print(f"跳过（归档里没有）：{name}")
            continue
        plain = crypt.crypt(e.adlr.hash, bytes(xp3.extract_entry(mm, e)))
        path = os.path.join(out_dir, name.replace("/", os.sep))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path) and os.path.getsize(path) == len(plain):
            print(f"已存在：{path}")
        else:
            with open(path, "wb") as fp2:
                fp2.write(plain)
            print(f"解出：{path}  {len(plain)} B")
        out.append(path)
    mm.close()
    fp.close()
    return out


def _tables(data: bytes) -> dict[str, tuple[int, int]]:
    tag = data[:4]
    if tag not in (b"OTTO", b"\x00\x01\x00\x00", b"true", b"ttcf"):
        raise SystemExit(f"不是 sfnt 字体（head={tag!r}）")
    if tag == b"ttcf":
        raise SystemExit("暂不支持 TTC 集合字体")
    num = struct.unpack_from(">H", data, 4)[0]
    out = {}
    for i in range(num):
        off = 12 + i * 16
        name = data[off:off + 4].decode("latin-1")
        table_off, length = struct.unpack_from(">II", data, off + 8)
        out[name] = (table_off, length)
    return out


def cmap_codepoints(path: str) -> set[int]:
    data = open(path, "rb").read()
    tables = _tables(data)
    if "cmap" not in tables:
        raise SystemExit(f"{path}: 没有 cmap 表")
    base, _length = tables["cmap"]
    num = struct.unpack_from(">H", data, base + 2)[0]
    points: set[int] = set()
    for i in range(num):
        rec = base + 4 + i * 8
        plat, enc, sub_off = struct.unpack_from(">HHI", data, rec)
        sub = base + sub_off
        fmt = struct.unpack_from(">H", data, sub)[0]
        if fmt == 4:
            segx2 = struct.unpack_from(">H", data, sub + 6)[0]
            seg = segx2 // 2
            ends = struct.unpack_from(">" + "H" * seg, data, sub + 14)
            starts = struct.unpack_from(">" + "H" * seg, data, sub + 16 + segx2)
            deltas = struct.unpack_from(">" + "h" * seg, data, sub + 16 + 2 * segx2)
            ro_pos = sub + 16 + 3 * segx2
            ranges = struct.unpack_from(">" + "H" * seg, data, ro_pos)
            for s, e, d, r in zip(starts, ends, deltas, ranges):
                for cp in range(s, min(e, 0xFFFF) + 1):
                    if cp == 0xFFFF:
                        continue
                    if r == 0:
                        glyph = (cp + d) & 0xFFFF
                    else:
                        gpos = ro_pos + 2 * r + 2 * (cp - s)
                        if gpos + 2 > len(data):
                            continue
                        glyph = struct.unpack_from(">H", data, gpos)[0]
                        if glyph:
                            glyph = (glyph + d) & 0xFFFF
                    if glyph:
                        points.add(cp)
        elif fmt == 12:
            n = struct.unpack_from(">I", data, sub + 12)[0]
            for k in range(n):
                s, e, g = struct.unpack_from(">III", data, sub + 16 + k * 12)
                if g:
                    points.update(range(s, e + 1))
    return points


def corpus_chars(text_dir: str) -> set[str]:
    chars: set[str] = set()
    for script in textset.names(text_dir):
        for rec in textset.records_for(text_dir, script):
            for key in ("name", "text"):
                for ch in (rec.get(key) or ""):
                    if ch not in "\n\r\t":
                        chars.add(ch)
        for rec in textset.records_for(text_dir, script, textset.SELECTS):
            for ch in (rec.get("text") or ""):
                chars.add(ch)
    return chars


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--extract", metavar="DIR", help="从 data.xp3 解出官方字体到 DIR")
    ap.add_argument("--archive", default="E:/SteamLibrary/steamapps/common/nine_kokoiro/data.xp3")
    ap.add_argument("--profile", default="resource/cx/profile_9nine.json")
    ap.add_argument("--text", default="resource/chs_text")
    ap.add_argument("--font", action="append", default=[], help="要检查的字体文件（可重复）")
    args = ap.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if args.extract:
        extract_fonts(args.extract, args.archive, args.profile)
        return 0

    if not args.font:
        raise SystemExit("给 --font 或 --extract")

    chars = corpus_chars(args.text)
    cps = {ord(c) for c in chars}
    print(f"语料字符：{len(chars)} 个（去重，含显示名与选项）")
    worst = 0
    for path in args.font:
        covered = cmap_codepoints(path)
        missing = sorted(c for c in chars if ord(c) not in covered)
        worst = max(worst, len(missing))
        print(f"\n{os.path.basename(path)}：cmap {len(covered)} 字，缺 {len(missing)} 字")
        if missing:
            print("  缺字（前 200）：", "".join(missing[:200]))
    return 0 if worst == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
