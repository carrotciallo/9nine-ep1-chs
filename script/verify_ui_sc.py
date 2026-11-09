"""校验 UI 简中语料与补丁产物（`patch3.xp3` + `steam.xp3` 钩子）。

用法（从项目根执行）：

    mamba run -n GalRev python script/verify_ui_sc.py \\
        --patch tmp/build/uitest/patch3.xp3 --steam tmp/build/uitest/steam.xp3 \\
        --corpus resource/ui_sc \\
        --official-cn resource/official_tjs/main/syslangtext_cn.ini \\
        --official-help resource/official_tjs/main/help_conf_cn.txt

检查项（任一不过即失败）：

1. `patch3.xp3` 里存在语料目录下的全部 UI 条目，且回读逐字节等于「语料按打包规则编码」
   （`main/**` 的 `.ini`/`.txt` = TVP mode 1；其余原样）
2. `main/syslangtext_sc.ini` 的 `!section` 结构、键序、行数与官方 `syslangtext_cn.ini`
   完全一致（只允许值变化），且 `textLanguageMenuItem_cn` 仍是「繁体中文」、
   `_sc` 是「简体中文」
3. `main/help_conf_sc.txt` 的键序/行数与官方 `help_conf_cn.txt` 一致
4. 文本里没有残留繁中专用字（内置常用字表，只作粗筛线索）
5. 钩子里有 UI 子域注册（`patch3.xp3>main/`、`>uipsd/sc/`、`>image/`）、
   `LoadSysLangText("syslangtext_", ".ini", ["sc"])`，且没有探针

依据：语言变体名与加载链见 `doc/engine-mechanics.md`「UI 文案」。
"""

from __future__ import annotations

import argparse
import mmap
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tool import krkr_text, xp3

PROT = 0x80000000


# 繁中/日文专用字表：`resource/verify/ui_sc_trad_chars.txt`（来源与复跑说明见文件头）。
# 该表 = 官方繁中 UI 文本的 CJK 字符 减去 简中正文语料出现过的字符，因此每条
# 都应是「转简后不可能再出现」的字；命中说明该行没转成简中。
def load_trad(path: str = "resource/verify/ui_sc_trad_chars.txt") -> set[str]:
    if not os.path.exists(path):
        raise SystemExit(f"缺少繁中字表: {path}（说明见文件头，或从 doc/acceptance-criteria.md 复跑）")
    chars = set()
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#"):
            chars |= set(line)
    return chars


TRAD_ONLY = load_trad()

UI_ENTRY_KEYS = [
    "patch3.xp3>main/",
    "patch3.xp3>uipsd/sc/",
    "patch3.xp3>image/",
]
HOOK_NEEDLES = [
    "steam_r18hack_orig.tjs",
    '__slots = ["patch", "patch2", "patch3"]',
    'Storages.addAutoPath(__slots[__i] + ".xp3>")',
    'KAGLoadScript(__slots[__i] + "_boot.tjs")',
]
HOOK_MUST_NOT = ["LoadSysLangText", "drawTextKinsokuRect", "AddTrueTypeFont",
                 "patch3.xp3>scn/", "System.exePath"]
BOOT_NEEDLES = [
    "patch3.xp3>scn/", "patch3.xp3>main/", "patch3.xp3>uipsd/sc/",
    "patch3.xp3>image/", 'System.exePath + "font/"',
    'KAGLoadScript("sc_hook.tjs")',
]
BOOT_REL = "patch3_boot.tjs"
PROBES = ("System.inform", "Debug.notice", "getPlacedPath")


def md5_name(path: str) -> str:
    import hashlib

    return hashlib.md5(path.encode("utf-16-le")).hexdigest()


def entries_of(archive: str) -> dict[str, bytes]:
    fp = open(archive, "rb")
    mm = mmap.mmap(fp.fileno(), 0, access=mmap.ACCESS_READ)
    from tool import cx

    crypt = cx.CxCrypt.load("resource/cx/profile_9nine.json")
    out = {}
    for e in xp3.parse_xp3(mm, show_log=False):
        if not e.name or not e.segms:
            continue
        data = bytes(xp3.extract_entry(mm, e))
        if e.info.flags & PROT:
            data = crypt.crypt(e.adlr.hash, data)
        out[e.name] = data
    mm.close()
    fp.close()
    return out


def corpus_files(root: str) -> list[tuple[str, bytes]]:
    TEXT_EXT = (".ini", ".txt", ".func")
    out = []
    for dirpath, _dirs, names in os.walk(root):
        for name in sorted(names):
            if name.endswith(".kmode"):
                continue
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            if name.lower().endswith((".tjs",)):
                text = open(path, encoding="utf-8-sig", newline="").read()
                out.append((rel, bytes([0xFF, 0xFE]) + text.encode("utf-16-le")))
            elif name.lower().endswith(TEXT_EXT):
                text = open(path, encoding="utf-8-sig", newline="").read()
                out.append((rel, krkr_text.encode_bytes(text, 1)))
            else:
                out.append((rel, open(path, "rb").read()))
    return out


def parse_ini(text: str):
    """返回 [(section, key)] 顺序表；`!section` 切换节，`#` 注释与空行忽略。"""
    seq = []
    section = ""
    for line in text.replace("\r\n", "\n").split("\n"):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("!"):
            section = s
            continue
        name = line.split("\t")[0].strip()
        if name:
            seq.append((section, name))
    return seq


def parse_help(text: str):
    """帮助文本：键行（不以 tab 开头）与说明块。返回键序表。"""
    seq = []
    for line in text.replace("\r\n", "\n").split("\n"):
        if not line or line.startswith("\t") or line.startswith("#"):
            continue
        seq.append(line.strip())
    return seq


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--patch", default="releases/patch3.xp3")
    ap.add_argument("--steam", default="releases/steam.xp3")
    ap.add_argument("--corpus", default="resource/ui_sc")
    ap.add_argument("--official-cn", default="resource/official_tjs/main/syslangtext_cn.ini")
    ap.add_argument("--official-help", default="resource/official_tjs/main/help_conf_cn.txt")
    args = ap.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    problems: list[str] = []
    corpus = corpus_files(args.corpus)
    if not corpus:
        raise SystemExit(f"语料目录为空: {args.corpus}")

    # 1) 产物条目与语料逐字节一致
    got = entries_of(args.patch)
    for rel, raw in corpus:
        entry = got.get(md5_name(rel))
        if entry is None:
            problems.append(f"patch3.xp3 缺 {rel}")
        elif entry != raw:
            problems.append(f"patch3.xp3 内容不一致 {rel}")
    texts = {rel: raw for rel, raw in corpus if rel.lower().endswith((".ini", ".txt", ".func"))}

    # 2) syslangtext 结构不变
    rel_ini = "main/syslangtext_sc.ini"
    if rel_ini not in texts:
        problems.append(f"语料缺 {rel_ini}")
    else:
        mode, sc_text = krkr_text.decode_bytes(texts[rel_ini])
        if mode != 1:
            problems.append(f"{rel_ini} 加扰 mode={mode}，应为 1")
        if os.path.exists(args.official_cn):
            cn_text = krkr_text.decode_file(Path(args.official_cn))[1]
            cn_seq, sc_seq = parse_ini(cn_text), parse_ini(sc_text)
            if cn_seq != sc_seq:
                problems.append(f"{rel_ini} 键序/键集合与官方 cn 不一致"
                                f"（官方 {len(cn_seq)} 项，产物 {len(sc_seq)} 项）")
                for a, b in zip(cn_seq, sc_seq):
                    if a != b:
                        problems.append(f"  首个差异: 官方 {a} / 产物 {b}")
                        break
            if len(cn_text.replace(chr(13) + chr(10), chr(10)).split(chr(10))) != \
                    len(sc_text.replace(chr(13) + chr(10), chr(10)).split(chr(10))):
                problems.append(f"{rel_ini} 行数与官方 cn 不一致")
        values = {}
        for line in sc_text.replace(chr(13) + chr(10), chr(10)).split(chr(10)):
            if line.startswith("#") or chr(9) not in line:
                continue
            key, value = line.split(chr(9), 1)
            values.setdefault(key.strip(), value.strip())
        if "简体" not in values.get("textLanguageMenuItem_sc", ""):
            problems.append("textLanguageMenuItem_sc 不是简体中文")
        if "繁体" not in values.get("textLanguageMenuItem_cn", ""):
            problems.append("textLanguageMenuItem_cn 被改写（官方 cn 轨仍是繁中，菜单名必须是繁体中文）")
        if "简体" not in values.get("subLanguageMenuItem_sc", ""):
            problems.append("subLanguageMenuItem_sc 不是简体中文")
        if not values.get("EzSaveHelpText"):
            problems.append("EzSaveHelpText 缺失")
        elif "," not in values["EzSaveHelpText"]:
            # ezsave.tjs 用 replace(/,/, "\n") 把它拆成两行，逗号不能丢
            problems.append("EzSaveHelpText 缺逗号（ezsave.tjs 靠逗号换行）")

    # 3) help 文本键序不变 + 4) 繁中残留粗筛
    for rel_corpus, official in [("main/help_conf_sc.txt", args.official_help)]:
        if rel_corpus not in texts:
            problems.append(f"语料缺 {rel_corpus}")
            continue
        _, sc_help = krkr_text.decode_bytes(texts[rel_corpus])
        if os.path.exists(official):
            cn_help = krkr_text.decode_file(Path(official))[1]
            if parse_help(cn_help) != parse_help(sc_help):
                problems.append(f"{rel_corpus} 键序与官方 cn 不一致")

    checked = 0
    for rel, raw in texts.items():
        if rel.lower().endswith(".func"):
            # .func 是 UI 布局脚本，里面的图层名是官方的日文（如「言語選択」），不算译文
            continue
        _, text = krkr_text.decode_bytes(raw)
        for i, line in enumerate(text.replace(chr(13) + chr(10), chr(10)).split(chr(10)), 1):
            if line.lstrip().startswith("#"):
                continue
            # 只查译文：`.ini` 查值，`.txt`（帮助）查以制表符开头的说明行；
            # 键名是官方的（如 `FontFace_思源黑體M`、`ConfigRenameChar春風`）不可改动。
            if rel.lower().endswith(".ini"):
                if chr(9) not in line:
                    continue
                body = line.split(chr(9), 1)[1]
            else:
                if not line.startswith(chr(9)):
                    continue
                body = line
            checked += 1
            bad = sorted({c for c in body if c in TRAD_ONLY})
            if bad:
                problems.append(f"{rel}:{i} 疑似繁中残留 {''.join(bad)} -> {body.strip()[:60]}")
    # 5) 钩子
    steam = entries_of(args.steam)
    hook_raw = steam.get(md5_name("steam_r18hack.tjs"))
    if hook_raw is None:
        problems.append("steam.xp3 缺 steam_r18hack.tjs")
        hook_text = ""
    else:
        hook_text = hook_raw.decode("utf-16-le", "ignore")
        for needle in HOOK_NEEDLES:
            if needle not in hook_text:
                problems.append(f"钩子缺 {needle}")
        for probe in PROBES:
            if probe in hook_text:
                problems.append(f"钩子含探针 {probe}")
        for leaked in HOOK_MUST_NOT:
            if leaked in hook_text:
                problems.append(f"钩子夹带了本该在 sc_hook.tjs 里的逻辑：{leaked}")

    # 归档根 patch3_boot.tjs：路径与优先级都在这里（便于以后改而不动 steam.xp3）；逻辑在 sc_hook.tjs
    boot = dict(corpus).get(BOOT_REL)
    if boot is None:
        problems.append(f"语料缺归档根的 {BOOT_REL}")
    else:
        tjs = boot.decode("utf-16-le", "ignore")
        for needle in BOOT_NEEDLES:
            if needle not in tjs:
                problems.append(f"{BOOT_REL} 缺 {needle}")
        for probe in PROBES:
            if probe in tjs:
                problems.append(f"{BOOT_REL} 含探针 {probe}")

    # sc_hook.tjs（归档根）：简中逻辑必须在这里，且同样不许带探针
    hook_rel = "sc_hook.tjs"
    raw = dict(corpus).get(hook_rel)
    if raw is None:
        problems.append(f"语料缺 {hook_rel}")
    else:
        tjs = raw.decode("utf-16-le", "ignore")
        for needle in ("LoadSysLangText(\"syslangtext_\", \".ini\", [\"sc\"])",
                       "multiLangLanguageTags", "drawTextKinsokuRect", "AddTrueTypeFont"):
            if needle not in tjs:
                problems.append(f"{hook_rel} 缺 {needle}")
        for probe in PROBES:
            if probe in tjs:
                problems.append(f"{hook_rel} 含探针 {probe}")

    n_pimg = sum(1 for rel, _ in corpus if rel.startswith("uipsd/sc/") and rel.endswith(".pimg"))
    n_png = sum(1 for rel, _ in corpus if rel.startswith("image/") and rel.endswith(".png"))
    print(f"语料：{len(corpus)} 个条目（文本 {len(texts)} / pimg {n_pimg} / png {n_png}）")
    print(f"patch3.xp3 条目 {len(got)} 个；steam.xp3 条目 {len(steam)} 个；文本行检查 {checked} 行")
    for p in problems[:30]:
        print("  FAIL", p)
    print(f"问题项：{len(problems)}")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
