"""把官方 `data.xp3`（Cx 加密变体）或明文 xp3 解包成松散文件。

用法（从项目根执行）：

    # 官方 Cx 变体：名字在索引里是 md5(UTF-16LE 路径)，按候选名反查
    mamba run -n GalRev python script/unpack_xp3.py \\
        "E:/SteamLibrary/steamapps/common/nine_kokoiro/data.xp3" \\
        --cx-profile resource/cx/profile_9nine.json \\
        --only scn/ --out resource/official_scn

    # 明文包（archive/ 里的初版补丁）
    mamba run -n GalRev python script/unpack_xp3.py archive/releases/unencrypted.xp3 --out tmp/patch_files

要点：
  * 索引本身是明文（`0x17` 处 `0x80` 的变体：真索引偏移在 `0x20`），条目内容才是 Cx 加密；
    加密参数注入自 `--cx-profile`（见 `tool/cx.py`）。
  * 条目名是 md5(UTF-16LE 全路径) 的十六进制。给 `--only <前缀>` 时按候选名反查
    （候选 = 已知脚本名 + `--names` 文件里的清单）；不给前缀则原样用哈希名落盘。
  * 同一内容的三个别名（全路径 / basename / md5）按 `(adlr 哈希, 大小)` 去重。
  * 幂等：已存在且大小一致的输出文件跳过（`--force` 可强制重写）。
"""

from __future__ import annotations

import argparse
import hashlib
import mmap
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tool import cx, xp3

PROTECTED = xp3.TVP_XP3_FILE_PROTECTED


def name_hash(path: str) -> str:
    return hashlib.md5(path.encode("utf-16-le")).hexdigest()


def hxv4_style_name(entry) -> str:
    return entry.name or ""


def load_entries(archive: str):
    fp = open(archive, "rb")
    mm = mmap.mmap(fp.fileno(), 0, access=mmap.ACCESS_READ)
    entries = [e for e in xp3.parse_xp3(mm, show_log=False) if e.name and e.segms]
    return fp, mm, entries


def dedupe(entries):
    """同一内容多个别名 -> 取名字最长的那条（全路径）。

    官方包的索引名就是 md5 十六进制（每个文件一条），明文包会额外登记全路径与 basename；
    所以按内容（adlr 密钥 + 大小）去重，名字只用于落盘。
    """
    groups = {}
    for e in entries:
        groups.setdefault((e.adlr.hash, e.info.fsize), []).append(e)
    out = []
    for bucket in groups.values():
        out.append(max(bucket, key=lambda e: len(e.name)))
    return out


def candidate_names(prefix: str):
    """按前缀生成候选名（官方索引里的名字是哈希，需要反查）。"""
    names = []
    if prefix.startswith("scn/"):
        names += [f"scn/a{i:02d}.txt.scn" for i in range(1, 30)]
    extra = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "resource", "name_candidates.txt")
    if os.path.exists(extra):
        with open(extra, encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if line and not line.startswith("#") and line.startswith(prefix):
                    names.append(line)
    return names


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("archive")
    ap.add_argument("--out", required=True)
    ap.add_argument("--cx-profile", help="Cx 参数（官方加密变体必给）")
    ap.add_argument("--only", action="append", default=[],
                    help="只导出该前缀（按候选名反查，可多次给）")
    ap.add_argument("--names", help="候选名清单文件（每行一个路径）")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    crypt = cx.CxCrypt.load(args.cx_profile) if args.cx_profile else None
    fp, mm, entries = load_entries(args.archive)
    try:
        uniq = dedupe(entries)
        by_name = {e.name: e for e in entries}
        wanted = []
        if args.only:
            for prefix in args.only:
                for name in candidate_names(prefix):
                    entry = by_name.get(name_hash(name))
                    if entry is None:
                        print(f"未命中 {name}")
                        continue
                    wanted.append((name, entry))
        else:
            wanted = [(e.name, e) for e in uniq]

        done = skipped = 0
        for name, entry in wanted:
            dest = os.path.join(args.out, name)
            os.makedirs(os.path.dirname(dest) or args.out, exist_ok=True)
            if not args.force and os.path.exists(dest) and os.path.getsize(dest) == entry.info.fsize:
                skipped += 1
                continue
            data = bytes(xp3.extract_entry(mm, entry))
            if crypt is not None and (entry.info.flags & PROTECTED):
                data = crypt.crypt(entry.adlr.hash, data)
            with open(dest, "wb") as out:
                out.write(data)
            done += 1
            print(f"{name}  {len(data)}B  flags={entry.info.flags:#x}")
        print(f"\n导出 {done} 个，跳过 {skipped} 个 -> {args.out}")
    finally:
        mm.close()
        fp.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
