"""Cx 解密回归测试（黄金向量）。

用法（从项目根执行）：

    mamba run -n GalRev python script/verify_cx.py

做法：从官方 `data.xp3` 里按 md5 名字取若干条目，用 `tool/cx.py` 解密，比对
`sha256(明文)` 与下面记录的**黄金值**。黄金值来自「GARbro 的 `ICrypt.Decrypt` 输出」，
已逐字节比对过 21 个条目（见 doc/acceptance-criteria.md §2）；此后不依赖 .NET 即可回归。

覆盖：scn（剧情）、startup.tjs（TJS2 字节码）、syslangtext（TVP 加扰文本）、
embfontlist（字体登记表）——四种不同的解压/加扰路径。
"""

from __future__ import annotations

import hashlib
import mmap
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tool import cx, xp3

GAME = "E:/SteamLibrary/steamapps/common/nine_kokoiro/data.xp3"

# (索引名, adlr 哈希, sha256(明文))
GOLDEN = [
    ("scn/a01.txt.scn", 0x426F158F,
     "9afd2c1d9719b6c50a07aa9eb6a58bced60736066f969b67f35f13d41ff8b8f2"),
    ("scn/a09.txt.scn", 0xBEA696EB,
     "efe489d69b2a6d3cbebe00ea30000681c58916be696945557beb850383714a42"),
    ("startup.tjs", 0xE425CD85,
     "25fbd9f90fa7e7a783b1c4485b86e0004257dc056475623ef79bd11a304d0cf5"),
    ("main/syslangtext_cn.ini", 0x4452D595,
     "a73a90291e95c4d2d83de1317566dad1705db4c512a4793e7d18f74ad79b0a93"),
    ("font/embfontlist.tjs", 0x7BE9A7A9,
     "48464c9717f2f106004e22e2a183dece09cc1d4fdd158f9a49f2dcf906c3c705"),
]


def name_hash(path: str) -> str:
    return hashlib.md5(path.encode("utf-16-le")).hexdigest()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not os.path.exists(GAME):
        print(f"跳过：找不到 {GAME}")
        return 0
    crypt = cx.CxCrypt.load("resource/cx/profile_9nine.json")
    fp = open(GAME, "rb")
    mm = mmap.mmap(fp.fileno(), 0, access=mmap.ACCESS_READ)
    try:
        entries = {e.name: e for e in xp3.parse_xp3(mm, show_log=False) if e.name}
        bad = 0
        for path, adler, digest in GOLDEN:
            entry = entries.get(name_hash(path)) or entries.get(path)
            if entry is None:
                print(f"FAIL 找不到条目 {path}")
                bad += 1
                continue
            if entry.adlr.hash != adler:
                print(f"FAIL {path}: adler {entry.adlr.hash:#x} != {adler:#x}")
                bad += 1
                continue
            plain = crypt.crypt(adler, bytes(xp3.extract_entry(mm, entry)))
            got = hashlib.sha256(plain).hexdigest()
            ok = got == digest
            print(f"{'ok  ' if ok else 'FAIL'} {path}  {len(plain)}B")
            bad += 0 if ok else 1
    finally:
        mm.close()
        fp.close()
    print(f"\n{len(GOLDEN) - bad}/{len(GOLDEN)} 通过")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
