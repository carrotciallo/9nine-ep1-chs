"""校验回写产物：cn 轨换成民汉简中，其余语言块与官方逐值一致。

用法（从项目根执行）：

    mamba run -n GalRev python script/verify_patch.py \\
        --official resource/official_scn/scn --text resource/chs_text --built tmp/build/scn

判定（全过才返回 0）：

* 脚本集合、场景数、行数、选项数一致
* **非 cn 部分逐值不变**：jp / en 两个语言块的所有槽、以及 cn 块以外的全部字符串值、
  整数槽，都与官方相同（按槽路径比对，不受字符串池追加影响）
* **cn 部分**：正文等于民汉文本；plain 等于「正文去掉 `\\n`」；被记录的共享冲突行除外
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tool import mdf, psb, textset

CN_ROW = re.compile(r"\$\.scenes\[(\d+)\]\.texts\[(\d+)\]\[2\]\[2\]\[(\d+)\]$")
CN_SEL = re.compile(r"\$\.scenes\[(\d+)\]\.selects\[(\d+)\]\.language\[2\]\.\w+$")
RUBY = re.compile(r"\[[^\[\]]+,\d+\]")


def plain_of(text: str) -> str:
    return RUBY.sub(lambda m: m.group(0)[1:].rsplit(",", 1)[0], text).replace("\\n", "")


def slots(script: str, raw: bytes):
    f = psb.PsbFile(raw)
    ints, strs = f.record_slots("$")
    values = {}
    for path, pos, width, index in strs:
        values[(pos, width)] = f.string_value(index)
    return f, ints, strs, values


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--official", required=True)
    ap.add_argument("--text", required=True)
    ap.add_argument("--built", required=True)
    args = ap.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    skipped_path = os.path.join(args.built, "_skipped_shared.json")
    skipped = {}
    if os.path.exists(skipped_path):
        with open(skipped_path, encoding="utf-8") as fp:
            skipped = json.load(fp)
    skipped_paths = {rec["path"] for recs in skipped.values() for rec in recs}

    def _row_key(path: str):
        m = re.match(r"\$\.scenes\[(\d+)\]\.texts\[(\d+)\]", path or "")
        return (int(m.group(1)), int(m.group(2))) if m else None

    # 共享槽跳过的“权威清单”来自 writeback 的产物；不在此清单内的不一致一律判失败
    skipped_rows: dict[str, set] = {}
    for script_name, recs in skipped.items():
        for rec in recs:
            key = _row_key(rec.get("path"))
            if key is not None:
                skipped_rows.setdefault(script_name, set()).add(key)

    problems = []
    totals = {"rows": 0, "cn_text_ok": 0, "cn_text_skip": 0, "cn_plain_ok": 0, "cn_text_bad": 0}
    for fname in sorted(os.listdir(args.official)):
        if not fname.endswith(".scn"):
            continue
        script = fname.removesuffix(".scn")
        with open(os.path.join(args.official, fname), "rb") as fp:
            off_raw = fp.read()
        built_path = os.path.join(args.built, "scn", fname)
        if not os.path.exists(built_path):
            problems.append({"script": script, "kind": "missing_built"})
            continue
        with open(built_path, "rb") as fp:
            new_raw = fp.read()

        off_f, off_ints, off_strs, off_vals = slots(script, off_raw)
        new_f, new_ints, new_strs, new_vals = slots(script, new_raw)

        if len(off_ints) != len(new_ints):
            problems.append({"script": script, "kind": "int_slot_count",
                             "official": len(off_ints), "built": len(new_ints)})
        if [s[3] for s in off_ints] != [s[3] for s in new_ints]:
            problems.append({"script": script, "kind": "int_values_changed"})
        if [(s[1], s[2]) for s in off_strs] != [(s[1], s[2]) for s in new_strs]:
            problems.append({"script": script, "kind": "string_slot_layout"})

        # 非 cn 槽：位置+宽度相同则值必须相同
        for s in off_strs:
            path = s[0]
            if CN_ROW.match(path) or CN_SEL.match(path):
                continue
            key = (s[1], s[2])
            if off_vals.get(key) != new_vals.get(key):
                problems.append({"script": script, "kind": "non_cn_changed", "path": path})

        rows = {(r["scene"], r["row"]): r for r in textset.records_for(args.text, script)}
        for msg in mdf.MdfScript(new_raw).iter_messages():
            totals["rows"] += 1
            if len(msg.blocks) < 3:
                continue
            cn = msg.blocks[2]
            rec = rows.get((msg.scene, msg.row))
            want = (rec or {}).get("text")
            prefix = f"$.scenes[{msg.scene}].texts[{msg.row}][2][2]"
            if cn.text == want:
                totals["cn_text_ok"] += 1
            elif (msg.scene, msg.row) in skipped_rows.get(script, set()):
                totals["cn_text_skip"] += 1
            else:
                totals["cn_text_bad"] += 1
                problems.append({"script": script, "kind": "cn_text_mismatch",
                                 "scene": msg.scene, "row": msg.row})
            if want is not None and cn.plains:
                exp = plain_of(want)
                if cn.plains[0][0] == exp:
                    totals["cn_plain_ok"] += 1
                elif f"{prefix}[2]" in skipped_paths:
                    pass
                else:
                    problems.append({"script": script, "kind": "cn_plain_mismatch",
                                     "scene": msg.scene, "row": msg.row})

    sel_total = sel_ok = 0
    for fname in sorted(os.listdir(args.official)):
        if not fname.endswith(".scn"):
            continue
        script = fname.removesuffix(".scn")
        built_path = os.path.join(args.built, "scn", fname)
        if not os.path.exists(built_path):
            continue
        with open(built_path, "rb") as fp:
            new = mdf.MdfScript(fp.read())
        recs = {(r["scene"], r["index"]): r for r in
                textset.records_for(args.text, script, textset.SELECTS)}
        for sel in new.iter_selects():
            cn = (sel.langs.get("cn") or {})
            rec = dict(recs.get((sel.scene, sel.index)) or {})
            for field in ("text", "searchtext", "speechtext"):
                want = rec.get(field) or rec.get("text")
                got = (cn.get(field) or {}).get("text")
                if want is None:
                    continue
                sel_total += 1
                if got == want:
                    sel_ok += 1
                else:
                    problems.append({"script": script, "kind": "select_mismatch",
                                     "index": sel.index, "field": field})
    totals["select_slots"] = sel_total
    totals["select_ok"] = sel_ok

    print(json.dumps(totals, ensure_ascii=False))
    for p in problems[:20]:
        print("  ", p)
    print(f"问题项：{len(problems)}")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
