"""生成简中「语言选择页」标题贴图 `uipsd/sc/conf_lang_sc.pimg`。

背景：官方 `uipsd/conf_lang.pimg` 的 `@caps_lang/layer`（221×199）里直接把
「System Language / Main Text Language / Sub Text Language」烘死在位图上，
而且这一页的 `conf_lang.func` 用的是 `psd,conf_lang`（不经过 `&GetUIFile`），
官方也没有 `conf_lang_{jp,en,cn}.pimg`，所以三条官方语言轨看到的都是同一张
英文图。要出简中只能自己造这张图。

做法（幂等，可复跑）：
  1. 从官方 `uipsd/conf_lang.pimg` 里取出 `14.tlg`（= `@caps_lang/layer` 的位图）；
  2. 保留左侧圆点（x<20），把英文文字区域的 alpha 清零；
  3. 用 `script/render_ui_labels.ps1`（GDI+ + 随包思源黑体 CN Bold）把
     `resource/ui_sc/conf_lang_labels.json` 里的简中标题渲染成透明 PNG；
  4. 合成后重编码 TLG，替换进 pimg，写出
     `resource/ui_sc/uipsd/sc/conf_lang_sc.pimg`；
  5. 回读校验：pimg 只有这条 chunk 变化、标题行有实际像素、其余资源逐字节一致。

配套：`resource/ui_sc/uipsd/sc/conf_lang.func` 把 `psd,conf_lang` 换成
`psd,&GetUIFile("conf_lang")`（由 `script/gen_ui_func.py` 生成），这样
sc 轨才会请求 `conf_lang_sc.pimg`，其它三轨因为找不到变体名自动回落到原图。

用法（从项目根执行）：

    mamba run -n GalRev python script/make_ui_lang_caption.py
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tool import pngio, psb, tlg

CAPTION_KEY = "14.tlg"          # @caps_lang/layer 的位图资源
TEXT_LEFT = 20                  # 这个 x 以左是圆点，保留；以右是英文文字，清掉
EXPECTED_BANDS = 3              # 三行标题


def render_labels(spec_path: str, out_png: str) -> None:
    script = os.path.join("script", "render_ui_labels.ps1")
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script,
           "-Spec", os.path.abspath(spec_path), "-Out", os.path.abspath(out_png)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit("渲染失败：\n" + (proc.stdout or "") + (proc.stderr or ""))


def erase_text(rgba: bytearray, w: int, h: int, x_from: int) -> None:
    for y in range(h):
        row = y * w * 4
        for x in range(x_from, w):
            rgba[row + x * 4 + 3] = 0


def composite(base: bytes, w: int, h: int, over_rgba: bytes) -> bytes:
    """直通 alpha 的 over 合成（底图在上层透明处不变）。"""
    out = bytearray(base)
    for i in range(w * h):
        sa = over_rgba[i * 4 + 3]
        if not sa:
            continue
        p = i * 4
        sr, sg, sb = over_rgba[p], over_rgba[p + 1], over_rgba[p + 2]
        if out[p + 3] == 0 or sa == 255:
            out[p:p + 4] = bytes((sr, sg, sb, sa))
            continue
        ba = out[p + 3]
        na = sa + ba * (255 - sa) // 255
        for c, sv in enumerate((sr, sg, sb)):
            out[p + c] = (sv * sa + out[p + c] * ba * (255 - sa) // 255) // max(na, 1)
        out[p + 3] = na
    return bytes(out)


def downsample(rgba: bytes, w: int, h: int, k: int) -> bytes:
    """盒式降采样（预乘加权），用于超采样渲染：scale=k 的大图 -> 目标尺寸。"""
    ow, oh = w // k, h // k
    out = bytearray(ow * oh * 4)
    for oy in range(oh):
        for ox in range(ow):
            sa = sr = sg = sb = 0
            for dy in range(k):
                for dx in range(k):
                    i = ((oy * k + dy) * w + (ox * k + dx)) * 4
                    a = rgba[i + 3]
                    sa += a
                    sr += rgba[i] * a
                    sg += rgba[i + 1] * a
                    sb += rgba[i + 2] * a
            o = (oy * ow + ox) * 4
            n = k * k
            out[o + 3] = sa // n
            if sa:
                out[o] = sr // sa
                out[o + 1] = sg // sa
                out[o + 2] = sb // sa
    return bytes(out)


def band_rows(rgba: bytes, w: int, h: int) -> list[tuple[int, int]]:
    rows = [y for y in range(h) if any(rgba[(y * w + x) * 4 + 3] > 8 for x in range(w))]
    bands, cur = [], None
    for y in rows:
        if cur and y == cur[1] + 1:
            cur = (cur[0], y)
        else:
            if cur:
                bands.append(cur)
            cur = (y, y)
    if cur:
        bands.append(cur)
    return bands


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--official", default="resource/official_uipsd/uipsd/conf_lang.pimg")
    ap.add_argument("--spec", default="resource/ui_sc/conf_lang_labels.json")
    ap.add_argument("--out", default="resource/ui_sc/uipsd/sc/conf_lang_sc.pimg")
    ap.add_argument("--font", default="", help="覆盖 JSON 里的字体文件（TTF/OTF/TTC，取第一个字族）")
    ap.add_argument("--preview", default="tmp/ui/conf_lang_sc_preview.png",
                    help="把合成后的标题图另存一份 PNG，便于人工检查")
    args = ap.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    spec = json.load(open(args.spec, encoding="utf-8"))
    # 字体优先取 --font，其次 JSON 里的 font；缺省回落到随包思源黑体（字形和民汉贴图不完全一致，
    # 但保证可构建）。字体文件不入库，见 doc/engine-mechanics.md §5.7。
    font = args.font or spec.get("font") or "resource/fonts_sc/SourceHanSansCN-Bold.otf"
    spec["font"] = os.path.abspath(font)
    if not os.path.exists(spec["font"]):
        raise SystemExit(f"缺少字体：{spec['font']}"
                         f"（用 --font 指定，或改 resource/ui_sc/conf_lang_labels.json 的 font）")

    tmpdir = tempfile.mkdtemp(prefix="ui_labels_")
    spec_path = os.path.join(tmpdir, "spec.json")
    png_path = os.path.join(tmpdir, "labels.png")
    json.dump(spec, open(spec_path, "w", encoding="utf-8"), ensure_ascii=False)
    render_labels(spec_path, png_path)

    with open(args.official, "rb") as fp:
        official = fp.read()
    f = psb.PsbFile(official)
    res = f.root[CAPTION_KEY]
    cap = f.resource_bytes(res.index)
    w, h, base_rgba = tlg.decode(cap)

    base = bytearray(base_rgba)
    erase_text(base, w, h, TEXT_LEFT)
    lw, lh, over = pngio.read(open(png_path, "rb").read())
    scale = int(spec.get("scale", 1))
    if scale > 1:
        over = downsample(over, lw, lh, scale)
        lw, lh = lw // scale, lh // scale
    if (lw, lh) != (w, h):
        raise SystemExit(f"渲染尺寸 {lw}x{lh} 与官方图 {w}x{h} 不一致")
    merged = composite(bytes(base), w, h, over)

    bands = band_rows(merged, w, h)
    if len(bands) < EXPECTED_BANDS:
        raise SystemExit(f"合成后只找到 {len(bands)} 行标题，期望 {EXPECTED_BANDS}")
    texts = [b for b in bands if any(merged[(y * w + x) * 4 + 3] > 8 for y in range(b[0], b[1] + 1)
                                     for x in range(TEXT_LEFT + 4, w))]
    if len(texts) < EXPECTED_BANDS:
        raise SystemExit("合成后标题行没有文字像素")

    new_tlg = tlg.encode(w, h, merged)
    out = f.replace_resources({res.index: new_tlg})
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "wb") as fp:
        fp.write(out)

    # 回读闸
    f2 = psb.PsbFile(open(args.out, "rb").read())
    got = f2.resource_bytes(f2.root[CAPTION_KEY].index)
    w2, h2, back = tlg.decode(got)
    if (w2, h2) != (w, h) or back != merged:
        raise SystemExit("回读不一致：重编码后的标题位图与预期不符")
    changed = [i for i in range(len(f.chunk_offsets))
               if f2.resource_bytes(i) != f.resource_bytes(i)]
    if changed != [res.index]:
        raise SystemExit(f"除 caption 外还有资源变化：{changed}")

    if args.preview:
        os.makedirs(os.path.dirname(args.preview), exist_ok=True)
        with open(args.preview, "wb") as fp:
            fp.write(pngio.write(w, h, merged))

    print(f"{args.out}: {len(out)} B（官方 {len(official)} B），caption {len(cap)} -> {len(new_tlg)} B")
    print(f"标题行: {bands}")
    if args.preview:
        print(f"预览: {args.preview}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
