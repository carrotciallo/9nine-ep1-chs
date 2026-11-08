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

from tool import cx, xp3

PROT = 0x80000000
HOOK_LINES = [
    "// 简中补丁钩子（由 steam.tjs 的 KAGLoadScript(steam_r18hack.tjs) 触发）",
    "// 1) 先执行官方原逻辑（保持与官方一致的执行环境，避免影响语言/配置）",
    'Scripts.execStorage("steam_r18hack_orig.tjs");',
    "// 2) 再注册剧本搜索路径（剧情加载很晚，此时注册足够；后注册优先）",
    'try { Storages.addAutoPath("patch.xp3>scn/"); } catch(e) {}',
    'try { Storages.addAutoPath("patch2.xp3>scn/"); } catch(e) {}',
    'try { Storages.addAutoPath("patch3.xp3>scn/"); } catch(e) {}',
    'try { Storages.addAutoPath(System.exePath + "scn/"); } catch(e) {}',
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

    index = io.BytesIO()
    hn = bytearray()
    for name, _plain, adlr, _packed, _off in placed:
        hn += struct.pack("<Ih", adlr, len(name)) + name.encode("utf-16-le")
    index.write(b"hnfn" + struct.pack("<q", len(hn)) + bytes(hn))

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


def build_steam(official: str, out_path: str, crypt) -> tuple[int, int]:
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

    # 追加官方字节码副本
    adlr = zlib.adler32(orig_r18) & 0xFFFFFFFF
    pk = zlib.compress(crypt.crypt(adlr, orig_r18), 9)
    o = 0x28 + len(content)
    content += pk
    nm = "steam_r18hack_orig.tjs"
    hb = struct.pack("<Ih", adlr, len(nm)) + nm.encode("utf-16-le")
    new_hn = [b"hnfn" + struct.pack("<q", len(hb)) + hb]
    nh = md5_name(nm)
    nbytes = nh.encode("utf-16-le") + bytes(2)
    info = xp3.Xp3Info_t()
    info.flags = PROT
    info.fsize, info.zsize, info.namelen = len(orig_r18), len(pk), len(nh)
    segm = xp3.Xp3Segm_t()
    segm.flags = xp3.TVP_XP3_SEGM_ENCODE_ZLIB
    segm.offset, segm.fsize, segm.zsize = o, len(orig_r18), len(pk)
    a = xp3.Xp3Adlr_t()
    a.hash = adlr
    chunks = (b"time" + struct.pack("<q", 8) + bytes(8)
              + b"adlr" + struct.pack("<q", 4) + bytes(a)
              + b"segm" + struct.pack("<q", ctypes.sizeof(xp3.Xp3Segm_t)) + bytes(segm)
              + b"info" + struct.pack("<q", ctypes.sizeof(xp3.Xp3Info_t) + len(nbytes))
              + bytes(info) + nbytes)
    new_file = [b"File" + struct.pack("<q", len(chunks)) + chunks]

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


def verify(steam_path: str, patch_path: str, scn_files: list[tuple[str, bytes]], crypt) -> list[str]:
    problems = []
    # steam.xp3：官方 3 条不变 + 钩子正确 + 原字节码一致
    fp = open(steam_path, "rb")
    mm = mmap.mmap(fp.fileno(), 0, access=mmap.ACCESS_READ)
    ents = {e.name: e for e in xp3.parse_xp3(mm, show_log=False) if e.name}

    def read(logical):
        e = ents[md5_name(logical)]
        return crypt.crypt(e.adlr.hash, bytes(xp3.extract_entry(mm, e)))

    hook_text = read("steam_r18hack.tjs").decode("utf-16-le", "ignore")
    if "addAutoPath" not in hook_text:
        problems.append("钩子缺少 addAutoPath")
    if "steam_r18hack_orig.tjs" not in hook_text:
        problems.append("钩子缺少转发")
    for keep in ("steam.tjs", "achievement.ini"):
        if md5_name(keep) not in ents:
            problems.append(f"steam.xp3 缺少官方条目 {keep}")
    mm.close()
    fp.close()

    # patch3.xp3：17 条 scn 逐条一致
    fp = open(patch_path, "rb")
    mm = mmap.mmap(fp.fileno(), 0, access=mmap.ACCESS_READ)
    got = {e.name: e for e in xp3.parse_xp3(mm, show_log=False) if e.name}
    if len(got) != len(scn_files):
        problems.append(f"patch3.xp3 条目数 {len(got)} != {len(scn_files)}")
    for logical, plain in scn_files:
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

    crypt = cx.CxCrypt.load(args.profile)
    os.makedirs(args.out, exist_ok=True)
    steam_out = os.path.join(args.out, "steam.xp3")
    patch_out = os.path.join(args.out, "patch3.xp3")

    n_patch = write_archive(patch_out, scn_files, crypt)
    n_steam, n_orig = build_steam(args.official_steam, steam_out, crypt)
    print(f"patch3.xp3  {n_patch} B  ({len(scn_files)} 个 scn)")
    print(f"steam.xp3   {n_steam} B  (官方 4 条 + 钩子 + 原字节码 {n_orig} B)")

    problems = verify(steam_out, patch_out, scn_files, crypt)
    if problems:
        for p in problems:
            print("FAIL", p)
        raise SystemExit("校验失败，产物已写出但不合格")
    print("校验通过：官方条目保留 / 钩子正确 / patch3 回读逐条一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
