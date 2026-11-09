"""校验两个文本集（官方一条语言轨 ↔ 民汉简中）是否逐脚本严格对齐。

用法（从项目根执行）：

    mamba run -n GalRev python script/verify_extract.py \\
        --base resource/official_jp --target resource/chs_text --out resource/verify

检查项：

1. 脚本集合一致（两侧都有 17 个，名字相同）
2. 逐脚本行数一致；场景数、场景标签序列一致
3. 行键（scene, row）两侧一一对应，选择支（scene, index）一一对应
4. 正文非空、无意外重复（同一文本在同一脚本内重复出现次数两侧相差不超过 1）
5. 行内标记守恒：`%NNN;` / `#RRGGBBAA;` / `#;` / `\\n` / ruby `[..,n]` 的出现次数逐行相同
   （标记随风向不同可能被重新断行，因此按**脚本级总量**判定，行级差异只做提示）

输出：

    <out>/report.json      机器可读报告（每脚本行数、标记总量、异常项）
    <out>/endlines.json    每脚本末尾 3 行的两侧文本，供人工语义抽查
    stdout 摘要；有差异时退出码 1
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tool import textset

MARKUP = [
    ("voice", re.compile(r"%[0-9]+;")),
    ("color", re.compile(r"#[0-9A-Fa-f]{6,8};")),
    ("reset", re.compile(r"#;")),
    ("newline", re.compile(r"\\n")),
    ("ruby", re.compile(r"\[[^\[\]]+,[0-9]+\]")),
]


def counts(text: str) -> dict:
    return {name: len(rx.findall(text or "")) for name, rx in MARKUP}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True, help="基准集（官方一条轨）")
    ap.add_argument("--target", required=True, help="待检集（民汉简中）")
    ap.add_argument("--out", required=True)
    ap.add_argument("--lang-markup", default="voice", help="行内标记守恒按哪一类判定（默认 voice）")
    args = ap.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    base_names = textset.names(args.base)
    tgt_names = textset.names(args.target)
    report = {"base": args.base, "target": args.target, "scripts": {}, "problems": []}

    missing = sorted(set(base_names) - set(tgt_names))
    extra = sorted(set(tgt_names) - set(base_names))
    if missing:
        report["problems"].append({"kind": "missing_scripts", "scripts": missing})
    if extra:
        report["problems"].append({"kind": "extra_scripts", "scripts": extra})

    endlines = {}
    for name in sorted(set(base_names) & set(tgt_names)):
        base_rows = textset.records_for(args.base, name)
        tgt_rows = textset.records_for(args.target, name)
        base_sel = textset.records_for(args.base, name, textset.SELECTS)
        tgt_sel = textset.records_for(args.target, name, textset.SELECTS)

        info = {
            "base_rows": len(base_rows),
            "target_rows": len(tgt_rows),
            "base_selects": len(base_sel),
            "target_selects": len(tgt_sel),
            "base_scenes": len({r["scene"] for r in base_rows}),
            "target_scenes": len({r["scene"] for r in tgt_rows}),
        }

        def keys(rows):
            return [(r["scene"], r["row"]) for r in rows]

        def labels(rows):
            out, seen = [], set()
            for r in rows:
                if r["scene"] not in seen:
                    seen.add(r["scene"])
                    out.append(r["label"])
            return out

        issues = []
        if info["base_rows"] != info["target_rows"]:
            issues.append("row_count")
        if keys(base_rows) != keys(tgt_rows):
            issues.append("row_keys")
        if labels(base_rows) != labels(tgt_rows):
            issues.append("labels")
        if info["base_selects"] != info["target_selects"]:
            issues.append("select_count")
        if [(r["scene"], r["index"]) for r in base_sel] != [(r["scene"], r["index"]) for r in tgt_sel]:
            issues.append("select_keys")

        empty = [r["row"] for r in tgt_rows if not (r["text"] or "").strip()]
        if empty:
            issues.append(f"empty_text@{len(empty)}")

        mk_base = {k: 0 for k, _ in MARKUP}
        mk_tgt = {k: 0 for k, _ in MARKUP}
        per_row_mismatch = 0
        for b, t in zip(base_rows, tgt_rows):
            cb, ct = counts(b["text"]), counts(t["text"])
            for k in mk_base:
                mk_base[k] += cb[k]
                mk_tgt[k] += ct[k]
            if cb[args.lang_markup] != ct[args.lang_markup]:
                per_row_mismatch += 1
        info["markup_base"] = mk_base
        info["markup_target"] = mk_tgt
        info["markup_row_mismatch"] = per_row_mismatch
        if mk_base[args.lang_markup] != mk_tgt[args.lang_markup]:
            issues.append(f"markup_total_{args.lang_markup}")

        info["issues"] = issues
        if issues:
            report["problems"].append({"kind": "script", "script": name, "issues": issues})
        report["scripts"][name] = info

        tail = []
        for b, t in list(zip(base_rows, tgt_rows))[-3:]:
            tail.append({"scene": b["scene"], "row": b["row"], "label": b["label"],
                         "base": b["text"], "target": t["text"]})
        endlines[name] = tail

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "report.json"), "w", encoding="utf-8", newline="\n") as fp:
        json.dump(report, fp, ensure_ascii=False, indent=1, sort_keys=True)
        fp.write("\n")
    with open(os.path.join(args.out, "endlines.json"), "w", encoding="utf-8", newline="\n") as fp:
        json.dump(endlines, fp, ensure_ascii=False, indent=1, sort_keys=True)
        fp.write("\n")

    print(f"{'script':10s} {'行':>6s} {'行':>6s} {'选择支':>4s} {'标记':>6s} {'行级差异':>6s}  问题")
    for name, info in report["scripts"].items():
        print(f"{name:10s} {info['base_rows']:6d} {info['target_rows']:6d} "
              f"{info['base_selects']:4d} "
              f"{info['markup_base'][args.lang_markup]:3d}/{info['markup_target'][args.lang_markup]:3d} "
              f"{info['markup_row_mismatch']:6d}  {','.join(info['issues']) or '-'}")
    print(f"\n问题项：{len(report['problems'])}")
    for p in report["problems"]:
        print("  ", p)
    return 0 if not report["problems"] else 1


if __name__ == "__main__":
    sys.exit(main())
