"""从初版补丁包（樱空素材）里抽出简中界面贴图，落成 `_sc` 变体名。

用法（从项目根执行）：

    mamba run -n GalRev python script/extract_ui_sc.py \\
        --from-xp3 archive/releases/unencrypted.xp3 --out resource/ui_sc

为什么单独一个脚本：这 20 张 `pimg` 与 2 张 `attention` 图是第三方（樱空
汉化组）素材，不进仓库（`.gitignore` 掉 `resource/ui_sc/uipsd`、`resource/ui_sc/image`）。
文本类（`syslangtext_sc.ini` / `help_conf_sc.txt` / `help_exch_sc.txt`）是
本项目的语料源，直接放仓库。

引擎按「当前 UI 语言 tag」请求语言变体名（见 `doc/engine-mechanics.md`
「UI 文案」）：界面贴图请求 `uipsd/<tag>/<name>_<tag>.pimg`，所以这里把
初版包里的 `<name>`（樱空通用名，内容已简中）改写成 `<name>_sc.pimg`，
并把 attention 图写成 `image/attention_sc.png`。

幂等：已存在且大小一致的输出跳过（`--force` 强制重写）。
"""

from __future__ import annotations

import argparse
import hashlib
import mmap
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tool import xp3

# 初版包里的 20 张界面贴图（uipsd/）与 2 张注意图（image/）
PIMG = [
    "conf", "conf_sys", "conf_mes", "conf_snd", "conf_voice", "conf_dlg", "conf_key",
    "dialog", "backlog", "message", "file", "file_load", "file_save", "extra",
    "quickconf", "qlpopup", "bgmtitle", "9_voicedialog", "exchview", "title",
]
PNG = ["attention", "attention2"]


def name_hash(path: str) -> str:
    return hashlib.md5(path.encode("utf-16-le")).hexdigest()


def load_index(archive: str):
    fp = open(archive, "rb")
    mm = mmap.mmap(fp.fileno(), 0, access=mmap.ACCESS_READ)
    by_hash = {e.name: e for e in xp3.parse_xp3(mm, show_log=False) if e.name and e.segms}
    return fp, mm, by_hash


def pick(by_hash, candidates):
    for cand in candidates:
        entry = by_hash.get(name_hash(cand))
        if entry is not None:
            return cand, entry
    return None, None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-xp3", default="archive/releases/unencrypted.xp3")
    ap.add_argument("--out", default="resource/ui_sc")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if not os.path.exists(args.from_xp3):
        raise SystemExit(f"初版补丁包不存在: {args.from_xp3}")

    fp, mm, by_hash = load_index(args.from_xp3)
    done = skipped = 0
    total = 0

    def emit(candidates, dest_rel):
        nonlocal done, skipped, total
        src, entry = pick(by_hash, candidates)
        if entry is None:
            raise SystemExit(f"初版包里没有 {' / '.join(candidates)}")
        dest = os.path.join(args.out, dest_rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if not args.force and os.path.exists(dest) and os.path.getsize(dest) == entry.info.fsize:
            skipped += 1
            total += entry.info.fsize
            print(f"跳过 {dest_rel}（已有）")
            return
        data = bytes(xp3.extract_entry(mm, entry))
        if len(data) != entry.info.fsize:
            raise SystemExit(f"{src}: 解出长度 {len(data)} != 索引 {entry.info.fsize}")
        with open(dest, "wb") as out:
            out.write(data)
        if open(dest, "rb").read() != data:
            raise SystemExit(f"回读不一致: {dest}")
        done += 1
        total += len(data)
        print(f"{src:32s} -> {dest_rel:34s} {len(data):9d}B")

    for base in PIMG:
        emit([f"uipsd/{base}.pimg", f"uipsd/cn/{base}_cn.pimg"],
             f"uipsd/sc/{base}_sc.pimg")
    for base in PNG:
        emit([f"image/{base}.png", f"image/{base}_cn.png"],
             f"image/{base}_sc.png")

    mm.close()
    fp.close()
    print(f"\n导出 {done} 个，跳过 {skipped} 个，共 {total / 1e6:.1f} MB -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
