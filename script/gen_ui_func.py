"""生成简中 UI 需要的 `uipsd/sc/conf_lang.func`（语言选择页布局覆盖）。

为什么改这一行：官方 `conf_lang.func` 第一行是 `psd,conf_lang`，直接把
「语言选择页」的贴图钉死成 `uipsd/conf_lang.pimg`（英文标题，见
`script/make_ui_lang_caption.py` 的说明）。改成 `psd,&GetUIFile("conf_lang")`
后，引擎会先按当前 UI 语言找 `conf_lang_<tag>.pimg`：

    sc -> uipsd/sc/conf_lang_sc.pimg（我们造的简中图）
    jp/en/cn -> 找不到变体，回落官方 uipsd/conf_lang.pimg（原样）

所以这份覆盖对其它三轨是语义中性的。`.func` 是 TVP 加扰文本（mode 1），
这里落成 UTF-8 明文语料，打包时由 `script/build_patch.py` 编回 mode 1。

用法（从项目根执行）：

    mamba run -n GalRev python script/gen_ui_func.py
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tool import krkr_text

ORIGINAL = "psd,conf_lang"
PATCHED = 'psd,&GetUIFile("conf_lang")'


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--official", default="resource/official_uipsd/uipsd/conf_lang.func")
    ap.add_argument("--out", default="resource/ui_sc/uipsd/sc/conf_lang.func")
    args = ap.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    raw = Path(args.official).read_bytes()
    mode, text = krkr_text.decode_bytes(raw)
    if mode != 1:
        raise SystemExit(f"{args.official}: 加扰 mode={mode}，预期 1")
    if not text.startswith(ORIGINAL):
        raise SystemExit(f"{args.official}: 第一行不是 {ORIGINAL!r}，结构变了，请人工确认")
    out_text = text.replace(ORIGINAL, PATCHED, 1)

    back = krkr_text.encode_bytes(out_text, 1)
    if krkr_text.decode_bytes(back)[1] != out_text:
        raise SystemExit("TVP 加扰往返失败")

    dest = Path(args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(out_text.encode("utf-8"))
    print(f"{dest}: {len(out_text)} 字符（官方 {len(text)}），只改了 psd 行")
    return 0


if __name__ == "__main__":
    sys.exit(main())
