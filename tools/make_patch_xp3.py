#!/usr/bin/env python3
"""打包 unencrypted.xp3（补丁主体）。

构成：重构 scn（build_tc_scn 的输出）＋樱空素材（贴图等）＋简中系统文本
（syslangtext / help_conf）＋思源字体替身。每个文件按引擎实际请求名登记三份
别名：全路径、文件名、md5(UTF-16LE 全路径) —— 与发行版构成一致。

注意 uipsd 贴图要同时登记 uipsd/cn/ 下的 _cn 变体名：Steam 版按 UI 语言
请求变体名（conf_sys_cn、dialog_cn、attention_cn 等），只放通用名的文件
永远不会被读到。详见 docs/formats.md。

索引 adlr 固定为 0，配合 version.dll（KirikiriUnencryptedArchive 系）
让引擎跳过对本包的解密。打包格式与 KirikiriTools 的 Xp3Pack 对齐。
"""
import argparse, hashlib, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from xp3pack import list_xp3, pack_xp3
from krkr_text import encode_bytes

def md5_u16(s): return hashlib.md5(s.encode("utf-16le")).hexdigest()

PIMG = ["9_voicedialog.pimg", "backlog.pimg", "bgmtitle.pimg", "conf.pimg", "conf_dlg.pimg",
        "conf_key.pimg", "conf_mes.pimg", "conf_snd.pimg", "conf_sys.pimg", "conf_voice.pimg",
        "dialog.pimg", "exchview.pimg", "extra.pimg", "file.pimg", "file_load.pimg",
        "file_save.pimg", "message.pimg", "qlpopup.pimg", "quickconf.pimg", "title.pimg"]
# 有语言变体槽的贴图：除通用名外再登记一份 _cn 名（内容同樱空版）
CN_VARIANTS = ["conf", "conf_sys", "conf_mes", "conf_snd", "conf_voice", "conf_dlg", "conf_key",
               "dialog", "file", "file_load", "file_save", "message", "backlog",
               "extra", "exchview", "bgmtitle", "9_voicedialog", "quickconf", "qlpopup"]
FONT_FILES = ["sourcehansanstc-medium.otf", "sourcehansanstc-bold.otf", "sourcehansanstc-heavy.otf",
              "sourcehanseriftc-bold.otf", "sourcehanseriftc-heavy.otf"]

def main():
    ap = argparse.ArgumentParser(description="打包 unencrypted.xp3")
    ap.add_argument("--sakura", required=True, help="樱空素材目录（unpack_momo 的输出）")
    ap.add_argument("--scn", required=True, help="重构 scn 目录（build_tc_scn 的输出，a01.scn …）")
    ap.add_argument("--fonts", required=True, help="字体目录：embfontlist.tjs（官方原版）、许可证、5 个 TC 名替身 otf")
    ap.add_argument("--ini", required=True, help="简中 syslangtext 二进制（krkr_text encode 的产物）")
    ap.add_argument("--help-text", required=True, help="简中 help_conf 文本稿（UTF-8、CRLF），打包时编码为加扰格式")
    ap.add_argument("--out", default="unencrypted.xp3")
    a = ap.parse_args()
    SAK, SCN, FNT = Path(a.sakura), Path(a.scn), Path(a.fonts)
    items = []  # (arc_path, bytes)
    for i in range(1, 18):
        items.append((f"scn/a{i:02d}.txt.scn", (SCN / f"a{i:02d}.scn").read_bytes()))
    for src, arc in [("attention.png", "image/attention.png"), ("attention2.png", "image/attention2.png"),
                     ("help_conf.txt", "main/help_conf.txt"), ("help_exch.txt", "main/help_exch.txt")]:
        items.append((arc, (SAK / src).read_bytes()))
    for name in PIMG:
        items.append((f"uipsd/{name}", (SAK / name).read_bytes()))
    items.append(("font/embfontlist.tjs", (FNT / "embfontlist.tjs").read_bytes()))
    items.append(("font/SourceHanSansAndSerifCN-LICENSE.txt",
                  (FNT / "SourceHanSansAndSerifCN-LICENSE.txt").read_bytes()))
    for fn in FONT_FILES:
        items.append((f"font/{fn}", (FNT / fn).read_bytes()))
    items.append(("main/syslangtext_cn.ini", Path(a.ini).read_bytes()))
    help_txt = Path(a.help_text).read_text(encoding="utf-8", newline="")
    items.append(("main/help_conf_cn.txt", encode_bytes(help_txt, 1)))
    for x in CN_VARIANTS:
        items.append((f"uipsd/cn/{x}_cn.pimg", (SAK / f"{x}.pimg").read_bytes()))
    items.append(("image/attention_cn.png", (SAK / "attention.png").read_bytes()))
    items.append(("image/attention2_cn.png", (SAK / "attention2.png").read_bytes()))

    entries, seen = [], set()
    for arc, data in items:
        for nm in (arc, Path(arc).name, md5_u16(arc)):
            if nm in seen: continue
            seen.add(nm); entries.append((nm, data))
    pack_xp3(entries, Path(a.out))
    lst = list_xp3(Path(a.out))
    print(f"{a.out}: {len(lst)} 条目")

if __name__ == "__main__":
    main()
