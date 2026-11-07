#!/usr/bin/env python3
"""Decrypt 樱空 2017 momo.bin (X'moe-Core).

Layout: 45 files. Each index entry is 0x30 bytes (MSVC wstring + offset/size).
Payload is XOR with a 1024-byte table copied from kokoiro_chs.dll VA 0x1001bb80
(unpacked image). The table repeats for the whole file.

Index was dumped from the live FileSystem vector at 0xc29910.
"""
from __future__ import annotations

import argparse
import struct
from pathlib import Path

# 1024-byte keystream from unpacked kokoiro_chs.dll VA 0x1001bb80
TABLE_FILE = Path(__file__).with_name("momo_xor1024.bin")

# (name, offset, size) from live QueryFile vector
ENTRIES = [
    ("9_voicedialog.pimg", 4, 28286),
    ("a01.txt.scn", 28290, 649467),
    ("a02.txt.scn", 677757, 1415339),
    ("a03.txt.scn", 2093096, 753547),
    ("a04.txt.scn", 2846643, 2808694),
    ("a05.txt.scn", 5655337, 1131880),
    ("a06.txt.scn", 6787217, 1750202),
    ("a07.txt.scn", 8537419, 1138696),
    ("a08.txt.scn", 9676115, 895529),
    ("a09.txt.scn", 10571644, 144430),
    ("a10.txt.scn", 10716074, 825634),
    ("a11.txt.scn", 11541708, 628903),
    ("a12.txt.scn", 12170611, 462080),
    ("a13.txt.scn", 12632691, 1426861),
    ("a14.txt.scn", 14059552, 1534847),
    ("a15.txt.scn", 15594399, 1251829),
    ("a16.txt.scn", 16846228, 388513),
    ("a17.txt.scn", 17234741, 384553),
    ("appconfig.tjs", 17619294, 1142),
    ("attention.png", 17620436, 223591),
    ("attention2.png", 17844027, 262340),
    ("backlog.pimg", 18106367, 178393),
    ("bgmtitle.pimg", 18284760, 31698),
    ("conf.pimg", 18316458, 550755),
    ("conf_dlg.pimg", 18867213, 502099),
    ("conf_key.pimg", 19369312, 659353),
    ("conf_mes.pimg", 20028665, 650451),
    ("conf_snd.pimg", 20679116, 582889),
    ("conf_sys.pimg", 21262005, 495608),
    ("conf_voice.pimg", 21757613, 581373),
    ("custom.tjs", 22338986, 218176),
    ("default.tjs", 22557162, 18370),
    ("dialog.pimg", 22575532, 56591),
    ("embfontlist.tjs", 22632123, 24),
    ("exchview.pimg", 22632147, 422917),
    ("extra.pimg", 23055064, 524979),
    ("file.pimg", 23580043, 262784),
    ("file_load.pimg", 23842827, 449494),
    ("file_save.pimg", 24292321, 450040),
    ("help_conf.txt", 24742361, 10470),
    ("help_exch.txt", 24752831, 1878),
    ("message.pimg", 24754709, 1668065),
    ("qlpopup.pimg", 26422774, 10205),
    ("quickconf.pimg", 26432979, 69040),
    ("title.pimg", 26502019, 2298040),
]


def xor_table(data: bytes, table: bytes) -> bytes:
    n = len(table)
    return bytes(data[i] ^ table[i % n] for i in range(len(data)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("momo", type=Path, help="path to momo.bin")
    ap.add_argument("-o", "--out", type=Path, required=True)
    ap.add_argument("--table", type=Path, default=TABLE_FILE)
    args = ap.parse_args()
    table = args.table.read_bytes()
    if len(table) != 1024:
        raise SystemExit(f"table must be 1024 bytes, got {len(table)}")
    momo = args.momo.read_bytes()
    args.out.mkdir(parents=True, exist_ok=True)
    for name, off, sz in ENTRIES:
        pt = xor_table(momo[off : off + sz], table)
        (args.out / name).write_bytes(pt)
        print(f"{name:22} {sz:8d} {pt[:4]!r}")


if __name__ == "__main__":
    main()
