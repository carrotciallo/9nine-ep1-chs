"""生成交付补丁包：`steam.xp3`（hook 注入）+ `patch3.xp3`（简中剧本）。

用法（从项目根执行）：

    mamba run -n GalRev python script/build_patch.py \\
        --scn-dir tmp/build/scn \\
        --official-steam "E:/SteamLibrary/steamapps/common/nine_kokoiro/steam.xp3.orig" \\
        --out releases

两个产物：

1. `steam.xp3`（约 19 KB）—— 只做 hook 注入
   * 官方 4 个条目原样保留（`steam.tjs` / `achievement.ini` / 警告文本 / `steam_r18hack.tjs`）
   * `steam_r18hack.tjs` 换成 TJS 源码钩子（先转发官方原逻辑，再注册剧本搜索路径）
   * 官方 `steam_r18hack.tjs` 的字节码原样改名为 `steam_r18hack_orig.tjs` 保留

2. `patch3.xp3`（约 2 MB）—— 只装 `scn/*.scn`（17 个简中剧本），日常更新只需替换它

为什么必须动 `steam.xp3`：见 `doc/engine-mechanics.md` §0/§3/§4
（`addArchive` 系注册的是绝对路径，压不住 `data.xp3`；只有启动流程内手动
`addAutoPath("<相对路径>scn/")` 才能覆盖，而本作可用的注入点只有 `steam_r18hack.tjs`）。

闸（任一不过就不写出）：官方条目字节不变、钩子内容正确、原字节码副本一致、
`patch3.xp3` 回读逐条与源 scn 一致。
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import io
import mmap
import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tool import cx, krkr_text, xp3

PROT = 0x80000000
HOOK_LINES = [
    "// 简中补丁钩子：patch3 子域（scn）+ 四轨语言表 + 松散 font/ 的思源黑体 CN",
    'Scripts.execStorage("steam_r18hack_orig.tjs");',
    "// 归档索引为「每文件一条 hnfn」，patch3.xp3>scn/ 才能覆盖全部 scn",
    'try { Storages.addAutoPath("patch3.xp3>scn/"); } catch(e) {}',
    "// 字体必须是松散文件：运行期注册走的 System.addFont 只能读真实文件，读不了 archive://",
    'try { Storages.addAutoPath(System.exePath + "font/"); } catch(e) {}',
    "// 第三方补丁位",
    'try { Storages.addAutoPath("patch.xp3>scn/"); } catch(e) {}',
    'try { Storages.addAutoPath("patch2.xp3>scn/"); } catch(e) {}',
    "// 1) 语言表加第 4 条（sc）",
    'try { if (SystemConfig.multiLangLanguageTags.find("sc") < 0) SystemConfig.multiLangLanguageTags.add("sc"); } catch(e) {}',
    'try { SystemConfig.multiLangParamsMap["sc"] = %[ "menu_caption" => "&Simplified Chinese" ]; } catch(e) {}',
    'try { if (typeof global.LanguageTags != "undefined" && LanguageTags.find("sc") < 0) LanguageTags.add("sc"); } catch(e) {}',
    "// 2) 字体：after-init 注册松散 font/ 里的思源黑体 CN（Bold 正文 / Medium 名字）",
    "//    注册失败不设硬编码回落：别名解析不到时由引擎自己的默认字体承载",
    "var __fontReady = false;",
    'function __ensureFonts() { if (__fontReady) return true; try { PreRenderFontEx.AddTrueTypeFont("9nineSC-B", "Source Han Sans CN", "SourceHanSansCN-Bold.otf", 0); PreRenderFontEx.AddTrueTypeFont("9nineSC-M", "Source Han Sans CN", "SourceHanSansCN-Medium.otf", 0); __fontReady = true; } catch(e) { __fontReady = false; } return __fontReady; }',
    'function __chsFontBold() { __ensureFonts(); return "9nineSC-B"; }',
    'function __chsFontMedium() { __ensureFonts(); return "9nineSC-M"; }',
    'try { addAfterInitCallback(function() { try { global.LanguageDefaultFontFaceMap["sc"] = __chsFontBold(); } catch(e) {} try { global.LanguageNameFontFaceMap["sc"] = __chsFontMedium(); } catch(e) {} try { objectHookInjection(%[ target: global.kag, method: "setMessageLayerUserFont", func: function(orig, *) { try { if (global.kag.languageType == 3) { var f = __chsFontBold(); global.kag.chDefaultFace = f; try { global.kag.scflags["langUserFontFace3"] = f; } catch(e2) {} } } catch(e) {} return orig(*); } ]); } catch(e) {} }); } catch(e) {}',
]
HOOK = chr(10).join(HOOK_LINES) + chr(10)
def md5_name(path: str) -> str:
    return hashlib.md5(path.encode("utf-16-le")).hexdigest()


def write_archive(path: str, files: list[tuple[str, bytes]], crypt) -> int:
    """变体头 + Cx 加密 + hnfn + zlib 索引（与官方 data.xp3/steam.xp3 同构）。"""
    out = io.BytesIO()
    out.write(xp3.XP3_SIG)
    out.write(struct.pack("<q", 0x17))
    out.write(struct.pack("<I", 1))
    out.write(struct.pack("<I", 0x80))
    out.write(bytes(5))
    idx_pos = out.tell()
    out.write(struct.pack("<q", 0))

    placed = []
    for name, plain in files:
        adlr = zlib.adler32(plain) & 0xFFFFFFFF
        packed = zlib.compress(crypt.crypt(adlr, plain), 9)
        off = out.tell()
        out.write(packed)
        placed.append((name, plain, adlr, packed, off))

    # 官方打包器是「每个文件一条 hnfn」，hnfn 全部在前、File 在后。写成一条大 hnfn 时，
    # 引擎只认得出第一条条目的名字 → `addAutoPath("x.xp3>sub/")` 只暴露一个文件（实测差异的根因）。
    index = io.BytesIO()
    for name, _plain, adlr, _packed, _off in placed:
        hn = struct.pack("<Ih", adlr, len(name)) + name.encode("utf-16-le")
        index.write(b"hnfn" + struct.pack("<q", len(hn)) + hn)

    for name, plain, adlr, packed, off in placed:
        nh = md5_name(name)
        nbytes = nh.encode("utf-16-le") + bytes(2)
        info = xp3.Xp3Info_t()
        info.flags = PROT
        info.fsize, info.zsize, info.namelen = len(plain), len(packed), len(nh)
        segm = xp3.Xp3Segm_t()
        segm.flags = xp3.TVP_XP3_SEGM_ENCODE_ZLIB
        segm.offset, segm.fsize, segm.zsize = off, len(plain), len(packed)
        adlr_b = xp3.Xp3Adlr_t()
        adlr_b.hash = adlr
        chunks = (b"time" + struct.pack("<q", 8) + bytes(8)
                  + b"adlr" + struct.pack("<q", 4) + bytes(adlr_b)
                  + b"segm" + struct.pack("<q", ctypes.sizeof(xp3.Xp3Segm_t)) + bytes(segm)
                  + b"info" + struct.pack("<q", ctypes.sizeof(xp3.Xp3Info_t) + len(nbytes))
                  + bytes(info) + nbytes)
        index.write(b"File" + struct.pack("<q", len(chunks)) + chunks)

    idx_off = out.tell()
    out.seek(idx_off)
    packed_index = zlib.compress(index.getvalue(), 6)
    out.write(bytes([1]))
    out.write(struct.pack("<QQ", len(packed_index), index.getvalue().__len__()))
    out.write(packed_index)
    out.seek(idx_pos)
    out.write(struct.pack("<q", idx_off))
    blob = out.getvalue()
    with open(path, "wb") as fp:
        fp.write(blob)
    return len(blob)


def build_steam(official: str, out_path: str, crypt,
                extra_files: list[tuple[str, bytes]] | None = None) -> tuple[int, int]:
    """在官方 steam.xp3 上替换 steam_r18hack.tjs，并把官方字节码另存一份。"""
    with open(official, "rb") as fp:
        data = fp.read()
    if data[0x17] != 0x80:
        raise SystemExit(f"{official}: 不是 Cx 变体头")
    idx_off = struct.unpack_from("<Q", data, 0x20)[0]
    zsize = struct.unpack_from("<Q", data, idx_off + 1)[0]
    index = bytearray(zlib.decompress(data[idx_off + 17: idx_off + 17 + zsize]))
    content = bytearray(data[0x28:idx_off])

    # 官方 steam_r18hack.tjs 明文（字节码）
    fp = open(official, "rb")
    mm = mmap.mmap(fp.fileno(), 0, access=mmap.ACCESS_READ)
    ents = {e.name: e for e in xp3.parse_xp3(mm, show_log=False) if e.name}
    e_r18 = ents[md5_name("steam_r18hack.tjs")]
    orig_r18 = crypt.crypt(e_r18.adlr.hash, bytes(xp3.extract_entry(mm, e_r18)))
    mm.close()
    fp.close()
    if orig_r18[:8] != b"TJS2100\x00":
        raise SystemExit("steam_r18hack.tjs 不是 TJS2 字节码，中止")

    # 定位 adlr 与 hnfn 槽
    name_of, pos = {}, 0
    while pos + 12 <= len(index):
        tag = bytes(index[pos:pos + 4])
        size = struct.unpack_from("<q", index, pos + 4)[0]
        if tag == b"hnfn":
            inner, end = pos + 12, pos + 12 + size
            while inner + 6 <= end:
                a = struct.unpack_from("<I", index, inner)[0]
                nl = struct.unpack_from("<h", index, inner + 4)[0]
                if nl <= 0 or inner + 6 + 2 * nl > end:
                    break
                name_of[a] = bytes(index[inner + 6: inner + 6 + 2 * nl]).decode("utf-16-le")
                inner += 6 + 2 * nl
        pos += 12 + size
    r18_adlr = next(a for a, n in name_of.items() if n == "steam_r18hack.tjs")

    hook_plain = bytes([0xFF, 0xFE]) + HOOK.encode("utf-16-le")
    hook_adlr = zlib.adler32(hook_plain) & 0xFFFFFFFF
    hook_packed = zlib.compress(crypt.crypt(hook_adlr, hook_plain), 9)
    hook_off = 0x28 + len(content)
    content += hook_packed

    pos = 0
    while pos + 12 <= len(index):
        tag = bytes(index[pos:pos + 4])
        size = struct.unpack_from("<q", index, pos + 4)[0]
        body = pos + 12
        if tag == b"hnfn":
            inner, end = body, body + size
            while inner + 6 <= end:
                if struct.unpack_from("<I", index, inner)[0] == r18_adlr:
                    struct.pack_into("<I", index, inner, hook_adlr)
                nl = struct.unpack_from("<h", index, inner + 4)[0]
                if nl <= 0:
                    break
                inner += 6 + 2 * nl
        elif tag == b"File":
            p, adlr = body, None
            while p < body + size:
                ct = bytes(index[p:p + 4])
                cs = struct.unpack_from("<q", index, p + 4)[0]
                if ct == b"adlr":
                    adlr = struct.unpack_from("<I", index, p + 12)[0]
                p += 12 + cs
            if adlr == r18_adlr:
                p = body
                while p < body + size:
                    ct = bytes(index[p:p + 4])
                    cs = struct.unpack_from("<q", index, p + 4)[0]
                    b = p + 12
                    if ct == b"adlr":
                        struct.pack_into("<I", index, b, hook_adlr)
                    elif ct == b"segm":
                        struct.pack_into("<I", index, b, xp3.TVP_XP3_SEGM_ENCODE_ZLIB)
                        struct.pack_into("<Q", index, b + 4, hook_off)
                        struct.pack_into("<Q", index, b + 12, len(hook_plain))
                        struct.pack_into("<Q", index, b + 20, len(hook_packed))
                    elif ct == b"info":
                        struct.pack_into("<q", index, b + 4, len(hook_plain))
                        struct.pack_into("<q", index, b + 12, len(hook_packed))
                    p += 12 + cs
        pos = body + size

    # 追加条目：官方字节码副本 + 额外文件（实验用，如 ConfigEx.tjs）
    entries = [("steam_r18hack_orig.tjs", orig_r18)] + list(extra_files or [])
    new_hn, new_file = [], []
    for name, plain in entries:
        adlr = zlib.adler32(plain) & 0xFFFFFFFF
        pk = zlib.compress(crypt.crypt(adlr, plain), 9)
        off = 0x28 + len(content)
        content += pk
        rec = struct.pack("<Ih", adlr, len(name)) + name.encode("utf-16-le")
        new_hn.append(b"hnfn" + struct.pack("<q", len(rec)) + rec)
        nh = md5_name(name)
        nbytes = nh.encode("utf-16-le") + bytes(2)
        info = xp3.Xp3Info_t()
        info.flags = PROT
        info.fsize, info.zsize, info.namelen = len(plain), len(pk), len(nh)
        segm = xp3.Xp3Segm_t()
        segm.flags = xp3.TVP_XP3_SEGM_ENCODE_ZLIB
        segm.offset, segm.fsize, segm.zsize = off, len(plain), len(pk)
        a = xp3.Xp3Adlr_t()
        a.hash = adlr
        chunks = (b"time" + struct.pack("<q", 8) + bytes(8)
                  + b"adlr" + struct.pack("<q", 4) + bytes(a)
                  + b"segm" + struct.pack("<q", ctypes.sizeof(xp3.Xp3Segm_t)) + bytes(segm)
                  + b"info" + struct.pack("<q", ctypes.sizeof(xp3.Xp3Info_t) + len(nbytes))
                  + bytes(info) + nbytes)
        new_file.append(b"File" + struct.pack("<q", len(chunks)) + chunks)

    blocks, p2 = [], 0
    while p2 + 12 <= len(index):
        t = bytes(index[p2:p2 + 4])
        s = struct.unpack_from("<q", index, p2 + 4)[0]
        blocks.append((t, bytes(index[p2:p2 + 12 + s])))
        p2 += 12 + s
    final = b"".join([b for t, b in blocks if t == b"hnfn"] + new_hn
                     + [b for t, b in blocks if t == b"File"] + new_file)

    out = io.BytesIO()
    out.write(data[:0x28])
    out.write(content)
    new_idx = 0x28 + len(content)
    pi = zlib.compress(final, 6)
    out.write(bytes([1]))
    out.write(struct.pack("<QQ", len(pi), len(final)))
    out.write(pi)
    blob = bytearray(out.getvalue())
    struct.pack_into("<Q", blob, 0x20, new_idx)
    with open(out_path, "wb") as fp:
        fp.write(bytes(blob))
    return len(blob), len(orig_r18)


def collect_text_overrides(root: str) -> list[tuple[str, bytes]]:
    """把 `<root>/<逻辑路径>` 下的覆盖文件编码成游戏可读的字节。

    ⚠️ 实测限制（`doc/engine-mechanics.md` §5.2）：`patch3.xp3` 的 `main/` 等域注册后**不生效**，
    新名字（如 `ml_chs.tjs`）一律解析不到；只有 `scn/` 域里、且**已存在于 `data.xp3`** 的名字能命中。
    所以这个开关目前只适合「替换已有资源」，改 tjs 请改 `HOOK_LINES`（钩子本身在 steam.xp3 里）。

    规则：
      * `.tjs` / `.txt` / `.ini`：按 UTF-8 源读取，用 TVP 文本加扰（默认 mode 1，
        可用同名 `.kmode` 覆盖）编码后放进归档；
      * 其它扩展名：原样按二进制放进归档（例如已经加扰好的文件、贴图、PSB）。
    """
    TEXT_EXT = (".tjs", ".txt", ".ini")
    out = []
    for dirpath, _dirs, names in os.walk(root):
        for name in sorted(names):
            if name.endswith(".kmode"):
                continue
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            raw = open(path, "rb").read()
            if name.lower().endswith(TEXT_EXT) and raw[:2] != krkr_text.MAGIC:
                mode = 1
                sidecar = path + ".kmode"
                if os.path.exists(sidecar):
                    mode = int(open(sidecar, encoding="utf-8").read().strip())
                text = open(path, encoding="utf-8", newline="").read()
                out.append((rel, krkr_text.encode_bytes(text, mode)))
            else:
                out.append((rel, raw))
    return out


def collect_font_payload(root: str) -> list[tuple[str, bytes]]:
    """把字体文件装进 patch3.xp3 的 `font/` 子域（裸文件名仍可被 `SourceHanSansCN-Bold.otf` 命中）。"""
    out = []
    if not root or not os.path.isdir(root):
        return out
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        if os.path.isfile(path):
            out.append((f"font/{name}", open(path, "rb").read()))
    return out


def verify(steam_path: str, patch_path: str, patch_files: list[tuple[str, bytes]], crypt) -> list[str]:
    problems = []
    # steam.xp3：官方 3 条不变 + 钩子正确 + 原字节码一致
    fp = open(steam_path, "rb")
    mm = mmap.mmap(fp.fileno(), 0, access=mmap.ACCESS_READ)
    ents = {e.name: e for e in xp3.parse_xp3(mm, show_log=False) if e.name}

    def read(logical):
        e = ents[md5_name(logical)]
        return crypt.crypt(e.adlr.hash, bytes(xp3.extract_entry(mm, e)))

    hook_text = read("steam_r18hack.tjs").decode("utf-16-le", "ignore")
    for probe in ("System.inform", "Debug.notice", "getPlacedPath"):
        if probe in hook_text:
            problems.append(f"钩子里仍有探针：{probe}")
    if "addAutoPath" not in hook_text:
        problems.append("钩子缺少 addAutoPath")
    if "steam_r18hack_orig.tjs" not in hook_text:
        problems.append("钩子缺少转发")
    for keep in ("steam.tjs", "achievement.ini"):
        if md5_name(keep) not in ents:
            problems.append(f"steam.xp3 缺少官方条目 {keep}")
    mm.close()
    fp.close()

    if patch_path is None:
        mm.close()
        fp.close()
        return problems

    # patch3.xp3（可选）：条目逐条一致
    fp = open(patch_path, "rb")
    mm = mmap.mmap(fp.fileno(), 0, access=mmap.ACCESS_READ)
    got = {e.name: e for e in xp3.parse_xp3(mm, show_log=False) if e.name}
    if len(got) != len(patch_files):
        problems.append(f"patch3.xp3 条目数 {len(got)} != {len(patch_files)}")
    for logical, plain in patch_files:
        e = got.get(md5_name(logical))
        if e is None:
            problems.append(f"patch3.xp3 缺少 {logical}")
            continue
        if crypt.crypt(e.adlr.hash, bytes(xp3.extract_entry(mm, e))) != plain:
            problems.append(f"patch3.xp3 内容不一致 {logical}")
    mm.close()
    fp.close()
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scn-dir", default="tmp/build/scn", help="writeback 产物目录（含 aXX.txt.scn）")
    ap.add_argument("--official-steam", required=True, help="官方 steam.xp3（未改动的原版）")
    ap.add_argument("--profile", default="resource/cx/profile_9nine.json")
    ap.add_argument("--tjs-dir", default="resource/tjs_patch",
                    help="要覆盖进 patch3.xp3 的 tjs/文本源目录（UTF-8，按相对路径落条目；空字符串禁用）")
    ap.add_argument("--font-dir", default="resource/fonts_sc",
                    help="要随包发布的字体文件目录（空的或不存在则跳过）；会复制成 <out>/font/")
    ap.add_argument("--allow-probe", action="store_true",
                    help="测试构建：允许 HOOK 里带 System.inform 等探针（不得用于发布）")
    ap.add_argument("--out", default="releases")
    args = ap.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if not os.path.isdir(args.scn_dir):
        raise SystemExit(f"scn 目录不存在: {args.scn_dir}")
    scn_files = [(f"scn/{f}", open(os.path.join(args.scn_dir, f), "rb").read())
                 for f in sorted(os.listdir(args.scn_dir)) if f.endswith(".scn")]
    if not scn_files:
        raise SystemExit(f"{args.scn_dir} 里没有 .scn")
    tjs_files = collect_text_overrides(args.tjs_dir) if args.tjs_dir else []
    patch_files = scn_files + tjs_files

    crypt = cx.CxCrypt.load(args.profile)
    os.makedirs(args.out, exist_ok=True)
    steam_out = os.path.join(args.out, "steam.xp3")

    # 交付形态：scn 装进 patch3.xp3；字体放松散 <out>/font/（运行期用 AddTrueTypeFont 注册）
    font_dir = os.path.join(args.out, "font")
    n_fonts = 0
    if args.font_dir and os.path.isdir(args.font_dir):
        os.makedirs(font_dir, exist_ok=True)
        for name in sorted(os.listdir(args.font_dir)):
            src = os.path.join(args.font_dir, name)
            if not os.path.isfile(src):
                continue
            plain = open(src, "rb").read()
            dest = os.path.join(font_dir, name)
            with open(dest, "wb") as fp:
                fp.write(plain)
            if open(dest, "rb").read() != plain:
                raise SystemExit(f"字体回读不一致：{dest}")
            n_fonts += 1
        total_mb = sum(os.path.getsize(os.path.join(font_dir, n)) for n in os.listdir(font_dir)) / 1e6
        print(f"font/       {n_fonts} 个文件（{total_mb:.1f} MB，松散目录）")

    patch_out = os.path.join(args.out, "patch3.xp3")
    n_patch = write_archive(patch_out, patch_files, crypt)
    print(f"patch3.xp3  {n_patch} B  ({len(scn_files)} 个 scn)")

    n_steam, n_orig = build_steam(args.official_steam, steam_out, crypt)
    print(f"steam.xp3   {n_steam} B  (官方 4 条 + 钩子 + 原字节码 {n_orig} B)")

    problems = verify(steam_out, patch_out, patch_files, crypt)
    if args.allow_probe:
        problems = [p for p in problems if "钩子里仍有探针" not in p]
        print("注意：--allow-probe，本次产物带探针，不得作为发布物")
    if problems:
        for p in problems:
            print("FAIL", p)
        raise SystemExit("校验失败，产物已写出但不合格")
    print("校验通过：官方条目保留 / 钩子正确 / patch3 回读逐条一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
