"""一次性提取脚本（**仅留档，不要用来覆盖 resource/**）。

> ⚠️ 语料是唯一来源：`resource/chs_text` 与 `resource/official_{jp,en,cn}` 已入库并经人工修订
> （繁体字形、显示名、选项译文，见 `doc/text-model.md` §4/§6）。重跑 `--lang cn` 会把 `resource/chs_text`
> 覆盖回民汉原件，重跑官方侧会覆盖 `resource/official_*`；要改文本请直接改语料。
> 需要重新提取时再看这个脚本，它是从 `archive/releases/unencrypted.xp3` / 官方 scn 出发的参考实现。

实现：把一条语言轨的脚本正文提取成按脚本分片的文本集。

用法（从项目根执行）：

    # 明文 xp3（archive/ 里的初版补丁包）
    mamba run -n GalRev python script/extract_text.py --from-xp3 archive/releases/unencrypted.xp3 \\
        --lang cn --out resource/chs_text

    # 松散目录（GARbro 导出的官方 scn/，或任何解包产物）
    mamba run -n GalRev python script/extract_text.py --from-dir tmp/official_scn \\
        --lang cn --out resource/official_zh

输出（落在 --out 下）：

    scripts/<script>.jsonl          一行一条对白（--lang 那条轨的文本）
    scripts/<script>.selects.jsonl  选项（没有就不建文件）
    _index.json                     清单：来源、语言、脚本名/哈希/场景数/行数/选择支数/字符数

`<script>` 是 PSB `name` 字段（如 `a01.txt`），引擎请求 `<script>.scn`。
xp3 里同一份内容登记三个别名，提取时按 `(adlr 哈希, 文件大小)` 去重、只取全路径那条。
"""

from __future__ import annotations

import argparse
import json
import mmap
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tool import mdf, psb, textset, xp3

SCRIPT_MAGIC = (b"PSB\x00", b"mdf\x00")


def as_script(data: bytes, arcname: str):
    """把字节读成 MdfScript；不是剧情脚本（如 PSB v2 的 .pimg 图片容器）则返回 None。"""
    try:
        script = mdf.MdfScript(data, os.path.basename(arcname))
    except (psb.PsbError, ValueError) as exc:
        print(f"skip {arcname}: {exc}", file=sys.stderr)
        return None
    if not script.scenes:
        print(f"skip {arcname}: 无 scenes（非剧情脚本）", file=sys.stderr)
        return None
    return script


def iter_scn_from_xp3(path):
    """按去重后的全路径别名逐个产出 (容器内路径, scn 字节)。"""
    with open(path, "rb") as fp:
        mm = mmap.mmap(fp.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            named = [e for e in xp3.parse_xp3(mm, show_log=False) if e.name and e.segms]
            groups = {}
            for e in named:
                groups.setdefault((e.adlr.hash, e.info.fsize), []).append(e)
            for entries in groups.values():
                canonical = [e for e in entries if "/" in e.name] or entries
                entry = max(canonical, key=lambda e: len(e.name))
                data = bytes(xp3.extract_entry(mm, entry))
                if data[:4] not in SCRIPT_MAGIC:
                    continue
                yield entry.name, data
        finally:
            mm.close()


def iter_scn_from_dir(path):
    for root, dirs, files in os.walk(path):
        dirs.sort()
        for name in sorted(files):
            full = os.path.join(root, name)
            try:
                with open(full, "rb") as fp:
                    if fp.read(4) not in SCRIPT_MAGIC:
                        continue
                    fp.seek(0)
                    data = fp.read()
            except OSError as exc:
                print(f"skip {full}: {exc}", file=sys.stderr)
                continue
            yield os.path.relpath(full, path).replace("\\", "/"), data


def message_records(script: mdf.MdfScript, lang: str):
    rows = []
    for msg in script.iter_messages():
        blk = msg.blocks[mdf.LANG_INDEX[lang]] if len(msg.blocks) > mdf.LANG_INDEX[lang] else None
        if blk is None:
            continue
        rows.append({
            "script": script.name,
            "scene": msg.scene,
            "label": msg.label,
            "row": msg.row,
            "speaker": msg.speaker,
            "name": blk.name,
            "text": blk.text,
            "plain": [value for value, _idx in blk.plains if value is not None],
            "flag": msg.flag,
        })
    return rows


def select_records(script: mdf.MdfScript, lang: str):
    rows = []
    for sel in script.iter_selects():
        if lang == "jp":
            rec = {"text": sel.text, "searchtext": None, "speechtext": None}
        else:
            rec = sel.langs.get(lang) or {}
            rec = {key: (rec.get(key) or {}).get("text") for key in ("text", "searchtext", "speechtext")}
        rows.append({
            "script": script.name,
            "scene": sel.scene,
            "label": sel.label,
            "index": sel.index,
            "target": sel.target,
            "storage": sel.storage,
            **rec,
        })
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--from-xp3", metavar="XP3", help="明文 xp3 归档")
    src.add_argument("--from-dir", metavar="DIR", help="松散目录（递归找 scn）")
    ap.add_argument("--lang", default="cn", choices=mdf.LANGS, help="提取哪条语言轨（默认 cn）")
    ap.add_argument("--out", required=True, help="文本集目录，如 resource/chs_text")
    args = ap.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    source = args.from_xp3 or args.from_dir
    if not os.path.exists(source):
        raise SystemExit(f"来源不存在: {source}")
    it = iter_scn_from_xp3(source) if args.from_xp3 else iter_scn_from_dir(source)

    scripts = {}
    seen_names = {}
    for arcname, data in it:
        script = as_script(data, arcname)
        if script is None:
            continue
        name = script.script_name or os.path.basename(arcname).removesuffix(".scn")
        if name in seen_names:
            raise SystemExit(f"脚本名重复: {name}（{seen_names[name]} 与 {arcname}），拒绝静默覆盖")
        seen_names[name] = arcname

        rows = message_records(script, args.lang)
        selects = select_records(script, args.lang)
        textset.write_script(args.out, name, rows, selects=selects)
        scripts[name] = {
            "source": arcname,
            "hash": script.script_hash,
            "scenes": len(script.scenes),
            "messages": len(rows),
            "selects": len(selects),
            "chars": sum(len(r["text"] or "") for r in rows),
            "empty_texts": sum(1 for r in rows if not r["text"]),
        }
        print(f"{name:16s} 行={len(rows):5d} 选择支={len(selects):3d} 字符={scripts[name]['chars']:7d} <- {arcname}")

    os.makedirs(args.out, exist_ok=True)
    index = {
        "set": os.path.basename(os.path.normpath(args.out)),
        "lang": args.lang,
        "source": os.path.abspath(source),
        "source_kind": "xp3" if args.from_xp3 else "dir",
        "scripts": scripts,
        "totals": {
            "scripts": len(scripts),
            "messages": sum(v["messages"] for v in scripts.values()),
            "selects": sum(v["selects"] for v in scripts.values()),
            "chars": sum(v["chars"] for v in scripts.values()),
        },
    }
    with open(os.path.join(args.out, "_index.json"), "w", encoding="utf-8", newline="\n") as fp:
        json.dump(index, fp, ensure_ascii=False, indent=2, sort_keys=True)
        fp.write("\n")
    print(f"\n{len(scripts)} 个脚本 -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
