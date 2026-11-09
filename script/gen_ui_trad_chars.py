"""重建 UI 繁中残留字表 `resource/verify/ui_sc_trad_chars.txt`。

用途：`script/verify_ui_sc.py` 用它粗筛「译文里是否还残留繁中/日文字」。

做法（可复跑，全部离线、只用项目自带文件）：
  1. 取官方繁中 UI 文本 `resource/official_tjs/main/syslangtext_cn.ini` +
     `help_conf_cn.txt`，与初版补丁里的简中版（`archive/releases/unencrypted.xp3` 的
     `main/syslangtext_cn.ini` / `main/help_conf_cn.txt`）逐字对齐，收集「繁中侧被换掉的字」；
  2. 减去简中正文语料 `resource/chs_text` 里出现过的字（繁简同形的白名单，避免误报）；
  3. 追加已知的日文专用字 `訳`。

依赖的可选输入：初版补丁包（`archive/`，gitignore 的本地材料）。没有它时只做第 2/3 步会不完整，
所以脚本会在缺文件时直接报错，而不是生成一张可疑的表。

用法（从项目根执行）：

    mamba run -n GalRev python script/gen_ui_trad_chars.py
"""

from __future__ import annotations

import argparse
import glob
import mmap
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tool import krkr_text, xp3


def read_text_file(path: str) -> str:
    raw = Path(path).read_bytes()
    if raw[:2] == krkr_text.MAGIC:
        return krkr_text.decode_bytes(raw)[1]
    if raw[:2] == b"\xff\xfe":
        return raw.decode("utf-16-le").lstrip("\ufeff")
    return raw.decode("utf-8-sig")


def read_from_xp3(archive: str, logical: str) -> str:
    import hashlib

    name = hashlib.md5(logical.encode("utf-16-le")).hexdigest()
    fp = open(archive, "rb")
    mm = mmap.mmap(fp.fileno(), 0, access=mmap.ACCESS_READ)
    try:
        for e in xp3.parse_xp3(mm, show_log=False):
            if not e.name or not e.segms or e.name != name:
                continue
            data = bytes(xp3.extract_entry(mm, e))
            if data[:2] == krkr_text.MAGIC:
                return krkr_text.decode_bytes(data)[1]
            if data[:2] == b"\xff\xfe":
                return data.decode("utf-16-le").lstrip("\ufeff")
            return data.decode("utf-8-sig")
    finally:
        mm.close()
        fp.close()
    raise SystemExit(f"{archive} 里没有 {logical}")


def cjk(c: str) -> bool:
    return "\u3400" <= c <= "\u9fff" or "\uf900" <= c <= "\ufaff"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--official-tjs", default="resource/official_tjs/main")
    ap.add_argument("--initial-patch", default="archive/releases/unencrypted.xp3")
    ap.add_argument("--chs-text", default="resource/chs_text/scripts/*.jsonl")
    ap.add_argument("--out", default="resource/verify/ui_sc_trad_chars.txt")
    args = ap.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if not os.path.exists(args.initial_patch):
        raise SystemExit(f"缺少初版补丁包（繁→简的对照物）：{args.initial_patch}")

    pairs = [
        (os.path.join(args.official_tjs, "syslangtext_cn.ini"), "main/syslangtext_cn.ini"),
        (os.path.join(args.official_tjs, "help_conf_cn.txt"), "main/help_conf_cn.txt"),
    ]
    trad: set[str] = set()
    for official_path, logical in pairs:
        if not os.path.exists(official_path):
            raise SystemExit(f"缺少官方文件：{official_path}（先用 unpack_xp3.py --only main/ 解出来）")
        off = read_text_file(official_path).replace("\r\n", "\n").split("\n")
        simp = read_from_xp3(args.initial_patch, logical).replace("\r\n", "\n").split("\n")
        for la, lb in zip(off, simp):
            if len(la) == len(lb):
                trad |= {a for a, b in zip(la, lb) if a != b}
            else:
                trad |= set(la) - set(lb)

    white = ""
    for path in glob.glob(args.chs_text):
        white += Path(path).read_text(encoding="utf-8")

    trad = {c for c in trad if cjk(c)}
    overlap = sorted(trad & set(white))
    final = sorted(trad - set(white) | set("訳"))

    dest = Path(args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    text = (
        "# 繁中/日文专用字表（script/verify_ui_sc.py 的粗筛用；由 script/gen_ui_trad_chars.py 生成）\n"
        "# 来源：官方 main/syslangtext_cn.ini + main/help_conf_cn.txt 与初版补丁里的简中版逐字对齐，\n"
        "#       取「繁体侧被换掉的字」，再减去简中正文语料 resource/chs_text 里出现过的字。\n"
        "# 命中说明该行没转成简中；只作线索，最终以人工比对为准。\n"
        + "".join(final) + "\n"
    )
    dest.write_text(text, encoding="utf-8")
    print(f"{dest}: {len(final)} 字（白名单排除 {len(overlap)} 个繁简同形字：{''.join(overlap)}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
