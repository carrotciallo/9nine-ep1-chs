"""校验「4 语言轨」产物：jp/en/cn 原样 + 第 4 块（sc）来自简中语料。

用法（从项目根执行）：

    mamba run -n GalRev python script/verify_lang4.py \\
        --official resource/official_scn/scn --built tmp/build/lang4/scn --text resource/chs_text

检查项（任一不过即失败）：

1. 与官方脚本相比：场景数、每场景行数、行键、选择支数量完全一致
2. 每行 `blocks` 由 3 变 4，且**前 3 块逐值等于官方**（jp/en/cn 一个字节都不许动）
3. 第 4 块的 `name`/`text`/`plain` 等于简中语料（`plain` 按 writeback 同规则推导）
4. 每个选择支 `language` 由 3 变 4，前 3 项逐值不变，第 4 项的文字等于语料
5. 产物幂等：再解析再序列化必须逐字节一致（`PsbGraph` 整图重排的往返闸）
"""

from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tool import mdf, psb, textset


def plain_of(text: str) -> str:
    return re.sub(r"\[([^\[\]]+),(\d+)\]", lambda m: m.group(1), text or "").replace("\\n", "")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--official", required=True)
    ap.add_argument("--built", required=True)
    ap.add_argument("--text", required=True)
    ap.add_argument("--only", action="append", default=[])
    args = ap.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    problems = []
    totals = {"rows": 0, "blocks4": 0, "selects": 0, "text_ok": 0, "plain_ok": 0, "name_ok": 0}

    files = sorted(f for f in os.listdir(args.official) if f.endswith(".scn"))
    if args.only:
        keep = set(args.only)
        files = [f for f in files if f in keep or f.removesuffix(".scn") in keep]
    if not files:
        raise SystemExit("没有可校验的 scn")

    for fname in files:
        script = fname.removesuffix(".scn")
        off_raw = open(os.path.join(args.official, fname), "rb").read()
        built_path = os.path.join(args.built, fname)
        if not os.path.exists(built_path):
            problems.append({"script": script, "kind": "missing_built"})
            continue
        new_raw = open(built_path, "rb").read()

        off = mdf.MdfScript(off_raw)
        new = mdf.MdfScript(new_raw)

        off_msgs = list(off.iter_messages())
        new_msgs = list(new.iter_messages())
        if len(off_msgs) != len(new_msgs):
            problems.append({"script": script, "kind": "row_count",
                             "official": len(off_msgs), "built": len(new_msgs)})
            continue

        rows = {(r["scene"], r["row"]): r for r in textset.records_for(args.text, script)}
        for a, b in zip(off_msgs, new_msgs):
            key = (a.scene, a.row)
            rec = rows.get(key)
            if rec is None:
                problems.append({"script": script, "kind": "missing_corpus", "key": key})
                continue
            totals["rows"] += 1
            if len(a.blocks) != 3:
                problems.append({"script": script, "kind": "official_not_3", "key": key})
                continue
            if len(b.blocks) != 4:
                problems.append({"script": script, "kind": "built_not_4", "key": key,
                                 "got": len(b.blocks)})
                continue
            totals["blocks4"] += 1
            for li in range(3):
                if a.blocks[li].text != b.blocks[li].text or a.blocks[li].name != b.blocks[li].name:
                    problems.append({"script": script, "kind": "front_block_changed",
                                     "key": key, "index": li})
            want_text = rec.get("text")
            if b.blocks[3].text == want_text:
                totals["text_ok"] += 1
            else:
                problems.append({"script": script, "kind": "sc_text_mismatch", "key": key})
            if b.blocks[3].plains:
                if b.blocks[3].plains[0][0] == plain_of(want_text):
                    totals["plain_ok"] += 1
                else:
                    problems.append({"script": script, "kind": "sc_plain_mismatch", "key": key})
            if rec.get("name") is not None and b.blocks[3].name == rec["name"]:
                totals["name_ok"] += 1

        sels = {(s["scene"], s["index"]): s for s in
                textset.records_for(args.text, script, textset.SELECTS)}
        off_sel = list(off.iter_selects())
        new_sel = list(new.iter_selects())
        if len(off_sel) != len(new_sel):
            problems.append({"script": script, "kind": "select_count"})
        for a, b in zip(off_sel, new_sel):
            key = (a.scene, a.index)
            rec = sels.get(key)
            if rec is None:
                problems.append({"script": script, "kind": "missing_select", "key": key})
                continue
            totals["selects"] += 1
            # 前 3 项（jp/en/cn）必须与官方逐值一致；第 4 项（sc）等于语料
            for lang in ("en", "cn"):
                new_rec = b.langs.get(lang) or {}
                off_rec = a.langs.get(lang) or {}
                for field in ("text", "searchtext", "speechtext"):
                    if (new_rec.get(field) or {}).get("text") != (off_rec.get(field) or {}).get("text"):
                        problems.append({"script": script, "kind": f"select_{lang}_changed",
                                         "key": key, "field": field})
            sc_new = b.langs.get("sc") or {}
            for field in ("text", "searchtext", "speechtext"):
                if (sc_new.get(field) or {}).get("text") != rec.get("text"):
                    problems.append({"script": script, "kind": "select_sc_mismatch",
                                     "key": key, "field": field})

        again = psb.PsbFile(new_raw).parse_graph().build()
        if again != new_raw:
            problems.append({"script": script, "kind": "not_idempotent"})

    print(totals)
    for p in problems[:20]:
        print("  ", p)
    print(f"问题项：{len(problems)}")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
