"""两条硬闸：零改动往返等价性 + 行内控制码守恒。

用法（从项目根执行）：

    mamba run -n GalRev python script/verify_roundtrip.py \\
        --official resource/official_scn/scn --built tmp/build/scn --text resource/chs_text

1. **零改动往返**：对每个 scn 调 `PsbFile.rebuild({})`，重建后的 PSB body 除 header
   checksum（`0x28`，4 B）外必须与原文逐字节一致；重建必须幂等。
2. **控制码守恒**：产物 cn 正文里的引擎控制码（`%...;`、`#RRGGBBAA;`、`#;`、`\\n`、ruby）
   必须与民汉源文**完全一致**（逐行比多重集合）；并与官方日文对照，列出两侧不一致的行，
   作为「民汉漏译控制码」的提示（不判失败）。
"""

from __future__ import annotations

import argparse
import collections
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tool import mdf, psb, textset

TOKENS = re.compile(r"%[A-Za-z0-9_\-]+;|#[0-9A-Fa-f]{6,8};|#;|\[[^\[\]]+,\d+\]|\\n")


def norm(body: bytes) -> bytes:
    return body[:0x28] + body[0x2C:]


def codes(text: str) -> collections.Counter:
    return collections.Counter(TOKENS.findall(text or ""))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--official", required=True)
    ap.add_argument("--built", required=True)
    ap.add_argument("--text", required=True)
    args = ap.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    fails = []
    roundtrip_ok = 0
    built_dir = os.path.join(args.built, "scn")
    for fname in sorted(os.listdir(args.official)):
        if not fname.endswith(".scn"):
            continue
        for tag, base in (("official", args.official), ("built", built_dir)):
            path = os.path.join(base, fname)
            if not os.path.exists(path):
                if tag == "built":
                    fails.append(f"{fname}: 缺少回写产物")
                continue
            with open(path, "rb") as fp:
                raw = fp.read()
            f = psb.PsbFile(raw)
            once = f.rebuild({})
            twice = psb.PsbFile(once).rebuild({})
            if norm(psb.PsbFile(once).body) != norm(f.body):
                fails.append(f"{fname}({tag}): 零改动往返不一致")
            elif once != twice:
                fails.append(f"{fname}({tag}): 重建不幂等")
            else:
                roundtrip_ok += 1

    code_bad = 0
    hint_rows = 0
    for fname in sorted(os.listdir(args.official)):
        if not fname.endswith(".scn"):
            continue
        script = fname.removesuffix(".scn")
        with open(os.path.join(args.official, fname), "rb") as fp:
            off = mdf.MdfScript(fp.read())
        with open(os.path.join(args.built, "scn", fname), "rb") as fp:
            new = mdf.MdfScript(fp.read())
        src = {(r["scene"], r["row"]): r for r in textset.records_for(args.text, script)}
        off_rows = {(m.scene, m.row): m for m in off.iter_messages()}
        for msg in new.iter_messages():
            key = (msg.scene, msg.row)
            if len(msg.blocks) < 3:
                continue
            want = (src.get(key) or {}).get("text") or ""
            got = msg.blocks[2].text or ""
            if codes(got) != codes(want):
                code_bad += 1
                fails.append(f"{script} {key}: 产物控制码与民汉源不一致")
            jp = off_rows.get(key)
            if jp is not None and len(jp.blocks) >= 3 and codes(jp.blocks[0].text) != codes(got):
                hint_rows += 1

    print(f"零改动往返：{roundtrip_ok} 个文件通过")
    print(f"控制码：产物与民汉源不一致 {code_bad} 行；与官方日文不同 {hint_rows} 行（提示项）")
    for f in fails[:10]:
        print("  FAIL", f)
    print(f"失败项：{len(fails)}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
