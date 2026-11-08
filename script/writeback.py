"""把民汉简中写进官方脚本的 cn（繁中）语言块，产出补丁用 scn。

用法（从项目根执行）：

    mamba run -n GalRev python script/writeback.py \\
        --official resource/official_scn/scn --text resource/chs_text --out tmp/build/scn

策略（**一律不改原槽**）：

* 官方同一条对白里三种语言各占独立字符串槽，但有 482 行 cn 的正文槽与 jp **同槽**；
  直接改槽会连累日文。因此替换方式是「追加新串 + 就地改指向」：
  新值写进字符串池尾部，只把 cn 那一处内联索引改成新下标（`PsbFile.patch_ints`）。
  相同新值在同一个脚本内只追加一次，尽量保持共享。
* 行内标记（`%p-1;` / `%f...;` / `\n` / ruby）原样保留，只做「去掉换行」得到 plain 变体。
* `length` 字段本作没有，不需要重算。

写入后的闸（不过就抛异常，不写文件）：

1. 重新解析产物：结构槽（整数/字符串引用）数量、位置、宽度与官方**完全一致**
2. 每个槽的指向与预期一一对应（目标槽指向新下标，其余槽指向原下标）
3. 目标槽读回的值等于期望值；其余槽读回的值与官方逐值相同
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tool import mdf, psb, textset

ROW_RE = re.compile(r"^(\$\.scenes\[(\d+)\]\.texts\[(\d+)\])\[2\]\[2\]\[(\d+)\]$")
SEL_RE = re.compile(r"^(\$\.scenes\[(\d+)\]\.selects\[(\d+)\]\.language)\[2\]\.(text|searchtext|speechtext)$")
RUBY = re.compile(r"\[[^\[\]]+,\d+\]")


def plain_of(text: str) -> str:
    """plain 变体：去掉 `\\n`（ruby 在简中译文里不存在，若出现只保留基字）。"""
    return RUBY.sub(lambda m: m.group(0)[1:].rsplit(",", 1)[0], text).replace("\\n", "")


def scn_name_of(path: str) -> str:
    return os.path.basename(path).removesuffix(".scn")


def load_overrides(text_dir: str) -> dict:
    path = os.path.join(text_dir, "_overrides.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fp:
        return json.load(fp).get("selects") or {}


def process(script_name: str, official_raw: bytes, rows: list[dict], selects: list[dict],
            sel_overrides: dict | None = None):
    psb_file = psb.PsbFile(official_raw)
    ints0, strs0 = psb_file.record_slots("$")
    by_key = {(r["scene"], r["row"]): r for r in rows}
    sel_by_key = {(s["scene"], s["index"]): s for s in selects}
    sel_overrides = sel_overrides or {}

    appended: list[str] = []
    slot_of_value: dict[str, int] = {}
    edits = []
    expected: dict[str, tuple[int, str]] = {}   # path -> (new index, new value)
    stats = {"rows": 0, "text": 0, "plain": 0, "name": 0, "select": 0, "skipped_missing": 0}
    skipped_shared: list[dict] = []

    def repoint(path: str, cur_index: int, cur_value: str, width: int, new_value: str) -> None:
        if new_value is None or new_value == cur_value:
            return
        if pos_of[path] in conflicted:
            skipped_shared.append({"path": path, "official": cur_value, "wanted": new_value})
            return
        if width == 0:
            raise psb.PsbError(f"{script_name}: {path} 没有内联宽度，无法改指向")
        idx = slot_of_value.get(new_value)
        if idx is None:
            idx = len(psb_file.string_offsets) + len(appended)
            appended.append(new_value)
            slot_of_value[new_value] = idx
        edits.append((pos_of[path], width, idx, "str"))
        expected[path] = (idx, new_value)

    pos_of = {slot[0]: slot[1] for slot in strs0}
    width_of = {slot[0]: slot[2] for slot in strs0}
    index_of = {slot[0]: slot[3] for slot in strs0}

    # 同一个字节位置被多处引用 = PSB 里的「对象共享」。若共享方里有非 cn 路径，
    # 改指向会连累别的语言块，只能留原样（本作仅 22 行，见 doc/text-model.md）。
    def is_cn_path(path: str) -> bool:
        m = ROW_RE.match(path)
        if m:
            return True
        return bool(SEL_RE.match(path))

    pos_paths: dict[int, list[str]] = {}
    for slot in strs0:
        pos_paths.setdefault(slot[1], []).append(slot[0])
    conflicted = {pos for pos, paths in pos_paths.items()
                  if len(paths) > 1 and any(not is_cn_path(p) for p in paths)}


    for msg in mdf.MdfScript(official_raw).iter_messages():
        key = (msg.scene, msg.row)
        row = by_key.get(key)
        if row is None:
            raise psb.PsbError(f"{script_name}: 民汉侧缺少 (scene={key[0]}, row={key[1]})")
        if len(msg.blocks) < 3:
            continue
        cn = msg.blocks[mdf.LANG_INDEX["cn"]]
        prefix = f"$.scenes[{msg.scene}].texts[{msg.row}][2][2]"
        # [0] 角色显示名，[1] 正文，[2..] plain
        official_vals = [cn.name, cn.text] + [v for v, _ in cn.plains]
        for pos, official_val in enumerate(official_vals):
            if official_val is None:
                continue            # 官方该语言块没有这一项（如 arity 2 的块没有 plain）
            path = f"{prefix}[{pos}]"
            if path not in width_of:
                stats["skipped_missing"] += 1
                continue
            cur_index = index_of[path]
            cur_value = psb_file.string_value(cur_index)
            if pos == 0:
                want = row.get("name")
                kind = "name"
            elif pos == 1:
                want = row.get("text")
                kind = "text"
            else:
                want = plain_of(row.get("text") or "")
                kind = "plain"
            if want is None:
                continue
            before = len(edits)
            repoint(path, cur_index, cur_value, width_of[path], want)
            if len(edits) > before:
                stats[kind] += 1
        stats["rows"] += 1

    for sel in mdf.MdfScript(official_raw).iter_selects():
        rec = dict(sel_by_key.get((sel.scene, sel.index)) or {})
        if not rec:
            raise psb.PsbError(f"{script_name}: 民汉侧缺少选项 selects[{sel.index}]")
        rec.update(sel_overrides.get(str(sel.index)) or {})
        for field in ("text", "searchtext", "speechtext"):
            path = f"$.scenes[{sel.scene}].selects[{sel.index}].language[2].{field}"
            if path not in width_of:
                continue
            cur_index = index_of[path]
            cur_value = psb_file.string_value(cur_index)
            want = rec.get(field) or rec.get("text")
            if want is None:
                continue
            before = len(edits)
            repoint(path, cur_index, cur_value, width_of[path], want)
            if len(edits) > before:
                stats["select"] += 1

    body = psb_file.patch_ints(edits)
    out_raw = psb_file.rebuild(extra_strings=appended, body=body)

    # ------------------------------------------------------------ 闸
    check = psb.PsbFile(out_raw)
    ints1, strs1 = check.record_slots("$")
    if len(ints0) != len(ints1) or [s[:3] for s in ints0] != [s[:3] for s in ints1] or \
            [s[3] for s in ints0] != [s[3] for s in ints1]:
        raise psb.PsbError(f"{script_name}: 整数槽在重建后发生变化")
    if len(strs0) != len(strs1) or [s[:3] for s in strs0] != [s[:3] for s in strs1]:
        raise psb.PsbError(f"{script_name}: 字符串槽结构在重建后发生变化")
    for slot0, slot1 in zip(strs0, strs1):
        path = slot0[0]
        want = expected.get(path)
        if want is None:
            if slot1[3] != slot0[3]:
                raise psb.PsbError(f"{script_name}: 非目标槽 {path} 指向被改动")
            continue
        if slot1[3] != want[0]:
            raise psb.PsbError(f"{script_name}: 目标槽 {path} 未指向新下标")
        if check.string_value(slot1[3]) != want[1]:
            raise psb.PsbError(f"{script_name}: 目标槽 {path} 读回值不符")
    stats["skipped_shared"] = len(skipped_shared)
    return out_raw, stats, len(appended), skipped_shared


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--official", required=True, help="官方 scn 目录（含 scn/ 一层）")
    ap.add_argument("--text", required=True, help="民汉文本集目录")
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", help="只处理一个脚本（调试用）")
    args = ap.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    sel_overrides = load_overrides(args.text)
    official_dir = args.official
    if not os.path.isdir(official_dir):
        raise SystemExit(f"官方 scn 目录不存在: {official_dir}")
    files = sorted(f for f in os.listdir(official_dir) if f.endswith(".scn"))
    if not files:
        raise SystemExit(f"{official_dir} 里没有 .scn")
    scn_out = os.path.join(args.out, "scn")
    os.makedirs(scn_out, exist_ok=True)

    total = {"rows": 0, "text": 0, "plain": 0, "name": 0, "select": 0,
             "skipped_missing": 0, "skipped_shared": 0}
    manifest = {}
    skipped_all = {}
    for fname in files:
        script = scn_name_of(fname)
        if args.only and args.only not in (script, fname):
            continue
        with open(os.path.join(official_dir, fname), "rb") as fp:
            official_raw = fp.read()
        rows = textset.records_for(args.text, script)
        if not rows:
            raise SystemExit(f"民汉文本集里没有脚本 {script}（{args.text}）")
        selects = textset.records_for(args.text, script, textset.SELECTS)
        out_raw, stats, added, skipped_shared = process(
            script, official_raw, rows, selects, sel_overrides.get(script))
        with open(os.path.join(scn_out, fname), "wb") as fp:
            fp.write(out_raw)
        if skipped_shared:
            skipped_all[script] = skipped_shared
        manifest[script] = {**stats, "appended_strings": added,
                            "official_bytes": len(official_raw), "out_bytes": len(out_raw)}
        for k in total:
            total[k] += stats[k]
        print(f"{script:10s} 行={stats['rows']:5d} 正文={stats['text']:5d} plain={stats['plain']:5d} "
              f"名={stats['name']:4d} 选项={stats['select']:3d} 追加串={added:5d} "
              f"共享跳过={stats['skipped_shared']:3d} "
              f"{len(official_raw)}B -> {len(out_raw)}B")

    with open(os.path.join(args.out, "_skipped_shared.json"), "w", encoding="utf-8", newline="\n") as fp:
        json.dump(skipped_all, fp, ensure_ascii=False, indent=1, sort_keys=True)
        fp.write("\n")
    with open(os.path.join(args.out, "_writeback.json"), "w", encoding="utf-8", newline="\n") as fp:
        json.dump({"total": total, "scripts": manifest, "skipped_shared": skipped_all},
                  fp, ensure_ascii=False, indent=1, sort_keys=True)
        fp.write("\n")
    print(f"\n合计：{total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
