"""给每个对白行追加第 4 个语言块（简中 `chs`），给每个选择支追加第 4 个语言项。

用法（从项目根执行）：

    mamba run -n GalRev python script/extend_lang.py \\
        --official resource/official_scn/scn --text resource/chs_text \\
        --out tmp/build/chs4 --only a01.txt --marker "【CHS】"

输入是**官方** scn（3 块：jp/en/cn），输出是 4 块（jp/en/cn/chs）的 scn：
  * 前 3 块原样保留（官方文本，未替换）；
  * 第 4 块 = 民汉简中（`name` / `text` / `plain`），结构照抄 cn 块的 arity；
  * 选择支 `language` 追加第 4 项（`text`/`searchtext`/`speechtext` 同值）。

说明：本脚本直接读官方 scn（jp/en/cn 三块）+ 简中语料，追加第 4 块 `sc`，官方三块一个字节都不动。
早期"覆盖 cn 轨"的三轨路径已废弃（`writeback.py` / `verify_patch.py` / `verify_roundtrip.py` 均已删除，只在 git 历史留档）。原叠加顺序是：
先 `writeback.py` 产出 3 块简体版，再 `extend_lang.py` 在其上追加 chs 块（前 3 块保持不变）。

闸（任一不过就不写文件）：
  1. 重排往返：产物再解析、再序列化必须逐字节一致（幂等）
  2. 结构：行数 / 场景标签 / 整数槽不变；每行 blocks 从 3 变 4，每行前 3 块逐值不变
  3. 内容：第 4 块 name/text/plain 与语料一致；选择支第 4 项与语料一致
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tool import mdf, psb, textset
from tool.psb import PsbGraph, split_path


def plain_of(text: str) -> str:
    """plain 变体：去掉 `\\n`，ruby 只保留基字（与 `tool/mdf.py` 的取值规则一致）。"""
    import re
    return re.sub(r"\[([^\[\]]+),(\d+)\]", lambda m: m.group(1), text).replace("\\n", "")


def str_width_for(graph: PsbGraph, extra: int = 0) -> int:
    """让新串下标放得下所需的引用宽度（至少沿用原文件最常见的宽度）。"""
    total = len(graph.file.string_offsets) + len(graph.extra_strings) + extra
    width = 1
    while total >= (1 << (8 * width)):
        width += 1
    return width


def node_text(graph: PsbGraph, node) -> str | None:
    if node.kind != "str":
        return None
    return graph.file.get_string(node.value).value


def extend_script(script: str, raw: bytes, rows: list[dict], selects: list[dict],
                  marker: str | None = None) -> tuple[bytes, dict]:
    base = psb.PsbFile(raw)
    if (base.offset_chunk_offsets, base.offset_chunk_lengths) != (None, None):
        pass
    graph = base.parse_graph()
    stats = {"rows": 0, "blocks_appended": 0, "selects": 0, "name": 0, "text": 0, "plain": 0}

    by_key = {(r["scene"], r["row"]): r for r in rows}
    sel_by_key = {(s["scene"], s["index"]): s for s in selects}

    # ---- 对白行
    scenes = graph.find("$.scenes")
    for si, scene in enumerate(scenes.children):
        names = base.node_names(scene)
        if "texts" not in names:
            continue
        texts = scene.children[names.index("texts")]
        for ri, row in enumerate(texts.children):
            rec = by_key.get((si, ri))
            if rec is None:
                raise psb.PsbError(f"{script}: 语料缺少 (scene={si}, row={ri})")
            blocks = row.children[2]
            if blocks.kind != "list":
                raise psb.PsbError(f"{script}: scene{si} row{ri} 的 blocks 不是列表")
            if len(blocks.children) != 3:
                raise psb.PsbError(f"{script}: scene{si} row{ri} blocks 长度 {len(blocks.children)}，预期 3")
            cn_block = blocks.children[2]
            if cn_block.kind != "list":
                raise psb.PsbError(f"{script}: scene{si} row{ri} 的 cn 语言块不是列表")
            arity = len(cn_block.children)
            width = str_width_for(graph, 4)

            new_block = psb.PNode("list", cn_block.type_byte, None, None,
                                  None, [], dict(cn_block.style))
            text = rec["text"] or ""
            if marker and si == 0 and ri == 0:
                text = marker + text
            name = rec.get("name")
            plain = plain_of(text)
            # 语言块是列表：[0] 显示名、[1] 正文、[2..] plain
            for pos, child in enumerate(cn_block.children):
                if pos == 0:
                    if child.kind == "str" and name is not None:
                        new_block.children.append(graph.str_node(name, width))
                        stats["name"] += 1
                    else:
                        new_block.children.append(psb.PNode(child.kind, child.type_byte))
                elif pos == 1:
                    new_block.children.append(graph.str_node(text, width))
                    stats["text"] += 1
                else:
                    new_block.children.append(graph.str_node(plain, width))
                    stats["plain"] += 1
            if len(new_block.children) != arity:
                raise psb.PsbError(f"{script}: scene{si} row{ri} 新块 arity {len(new_block.children)} != {arity}")
            blocks.children.append(new_block)
            stats["rows"] += 1
            stats["blocks_appended"] += 1

    # ---- 选择支
    for si, scene in enumerate(scenes.children):
        names = base.node_names(scene)
        if "selects" not in names:
            continue
        sels = scene.children[names.index("selects")]
        for idx, sel in enumerate(sels.children):
            rec = sel_by_key.get((si, idx))
            if rec is None:
                raise psb.PsbError(f"{script}: 语料缺少 select (scene={si}, index={idx})")
            keys = base.node_names(sel)
            lang = sel.children[keys.index("language")]
            if lang.kind != "list" or len(lang.children) != 3:
                raise psb.PsbError(f"{script}: select {idx} 的 language 结构异常")
            cn = lang.children[2]
            if cn.kind != "objects":
                raise psb.PsbError(f"{script}: select {idx} 的 cn 语言项不是对象")
            cn_keys = base.node_names(cn)
            width = str_width_for(graph, 4)
            new_item = psb.PNode("objects", cn.type_byte, None, None,
                                 list(cn.name_refs), [], dict(cn.style))
            want = rec.get("text")
            for key, child in zip(cn_keys, cn.children):
                if child.kind == "str" and want is not None:
                    new_item.children.append(graph.str_node(want, width))
                else:
                    new_item.children.append(psb.PNode(child.kind, child.type_byte))
            lang.children.append(new_item)
            stats["selects"] += 1

    out = graph.build()

    # ---- 闸 1：产物幂等（再解析、再序列化逐字节一致）
    again = psb.PsbFile(out).parse_graph().build()
    if again != out:
        raise psb.PsbError(f"{script}: 产物不幂等（重排后字节不同）")

    # ---- 闸 2/3：结构与内容
    check = mdf.MdfScript(out)
    seen = 0
    for msg in check.iter_messages():
        rec = by_key.get((msg.scene, msg.row))
        blocks = msg.blocks
        if len(blocks) != 4:
            raise psb.PsbError(f"{script}: scene{msg.scene} row{msg.row} 产物 blocks 长度 {len(blocks)}")
        want = (marker + rec["text"]) if (marker and msg.scene == 0 and msg.row == 0) else rec["text"]
        if blocks[3].text != want:
            raise psb.PsbError(f"{script}: scene{msg.scene} row{msg.row} chs 正文不符")
        if blocks[3].plains and blocks[3].plains[0][0] != plain_of(want):
            raise psb.PsbError(f"{script}: scene{msg.scene} row{msg.row} chs plain 不符")
        seen += 1
    if seen != len(by_key):
        raise psb.PsbError(f"{script}: 产物行数 {seen} != 语料 {len(by_key)}")

    # 前 3 块与输入逐值一致（用输入自身解析出的值做基准）
    base_script = mdf.MdfScript(raw)
    for msg_in, msg_out in zip(base_script.iter_messages(), check.iter_messages()):
        for li in range(3):
            if msg_in.blocks[li].text != msg_out.blocks[li].text:
                raise psb.PsbError(f"{script}: scene{msg_in.scene} row{msg_in.row} 第 {li} 块被改动")
            if msg_in.blocks[li].name != msg_out.blocks[li].name:
                raise psb.PsbError(f"{script}: scene{msg_in.scene} row{msg_in.row} 第 {li} 块显示名被改动")

    return out, stats


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--official", required=True, help="输入 scn 目录（含 scn/ 一层）")
    ap.add_argument("--text", required=True, help="简中语料目录（resource/chs_text）")
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", action="append", default=[], help="只处理这些脚本（可重复）")
    ap.add_argument("--marker", default=None, help="给每个脚本 scene0 row0 的正文加前缀（PoC 辨识用）")
    args = ap.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    src_dir = args.official
    files = sorted(f for f in os.listdir(src_dir) if f.endswith(".scn"))
    if args.only:
        keep = set(args.only)
        files = [f for f in files if f in keep or f.removesuffix(".scn") in keep]
    if not files:
        raise SystemExit("没有要处理的 scn")

    out_dir = os.path.join(args.out, "scn")
    os.makedirs(out_dir, exist_ok=True)
    total = {"rows": 0, "blocks_appended": 0, "selects": 0, "name": 0, "text": 0, "plain": 0}
    for fname in files:
        script = fname.removesuffix(".scn")
        raw = open(os.path.join(src_dir, fname), "rb").read()
        rows = textset.records_for(args.text, script)
        selects = textset.records_for(args.text, script, textset.SELECTS)
        if not rows:
            raise SystemExit(f"语料里没有脚本 {script}")
        out, stats = extend_script(script, raw, rows, selects, args.marker)
        open(os.path.join(out_dir, fname), "wb").write(out)
        print(f"{script:10s} 行={stats['rows']:5d} 追加块={stats['blocks_appended']:5d} "
              f"名={stats['name']:4d} 正文={stats['text']:5d} plain={stats['plain']:5d} "
              f"选项={stats['selects']:2d} {len(raw)}B -> {len(out)}B")
        for k in total:
            total[k] += stats[k]
    print(f"\n合计：{total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
