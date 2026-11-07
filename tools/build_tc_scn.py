#!/usr/bin/env python3
"""官方 scn 繁中块换樱空简中：处理「块级共享」的条目。

非共享条目：原地改写繁中槽的字符串索引（2B），新串追加到池尾。
共享条目（繁中块与日文块在父列表里共用同一元素）：把该条目的 [2] 列表
整体重建——偏移数组加宽到 3B、繁中块用一份改好索引的副本追加在列表末尾，
祖先列表里指向拼接点之后的偏移逐个 += 增长量。其余字节一律不动。
"""
import struct, sys
sys.path.insert(0, ".")
from psb_parse import Psb

class S(Psb):
    def __init__(self, data):
        super().__init__(data)
        self.offset_records = []   # (value_pos, width, target_abs_start)
    def arr(self, pos):
        t = self.d[pos]; cw = t - 0x0D + 1
        count = self._int(pos + 1, cw)
        et = self.d[pos + 1 + cw]; ew = et - 0x0C
        vstart = pos + 1 + cw + 1
        vals = [self._int(vstart + i * ew, ew) for i in range(count)]
        return vals, vstart, ew, vstart + count * ew
    def parse(self, pos):
        t = self.d[pos]
        if 0x15 <= t <= 0x18:
            w = t - 0x14; idx = self._int(pos + 1, w)
            return {"k": "str", "v": ("str", idx, self.strings[idx]), "s": pos, "e": pos + 1 + w,
                    "idx_pos": pos + 1, "w": w}, pos + 1 + w
        if t == 0x20:
            offs, vstart, ew, base = self.arr(pos + 1)
            kids = []; end = base
            for j, o in enumerate(offs):
                self.offset_records.append((vstart + j * ew, ew, base + o))
                kid, e = self.parse(base + o); kids.append(kid); end = max(end, e)
            return {"k": "list", "v": kids, "s": pos, "e": end, "offs": offs, "base": base, "ew": ew}, end
        if t == 0x21:
            nameidx, p = self._array_at(pos + 1)
            offs, vstart, ew, base = self.arr(p)
            out = {}; end = base
            for j, (ni, o) in enumerate(zip(nameidx, offs)):
                self.offset_records.append((vstart + j * ew, ew, base + o))
                kid, e = self.parse(base + o); out[self.names[ni]] = kid; end = max(end, e)
            return {"k": "obj", "v": out, "s": pos, "e": end}, end
        v, e = self._unpack(pos)
        return {"k": "raw", "v": v, "s": pos, "e": e}, e

def plain(node):
    if node["k"] == "str": return node["v"]
    if node["k"] == "list": return [plain(x) for x in node["v"]]
    if node["k"] == "obj": return {k: plain(v) for k, v in node["v"].items()}
    return node["v"]

def is_strval(x): return isinstance(x, tuple) and len(x) == 3 and x[0] == "str"

def build(name, off_bytes, sak_bytes):
    off = S(off_bytes)
    root, _ = off.parse(off.off_entries)
    sak = Psb(sak_bytes)
    new_idx_of = {}; new_values = []
    inplace = []        # (idx_pos, new_idx)
    splices = []        # (list_start, list_end, new_list_bytes)
    n_shared = 0
    scenes = root["v"]["scenes"]["v"]
    for si, sc in enumerate(scenes):
        texts_node = sc["v"].get("texts")
        if texts_node is None: continue
        stexts = sak.root["scenes"][si].get("texts") or [] if si < len(sak.root["scenes"]) else []
        entries = texts_node["v"]
        assert len(entries) == len(stexts), f"{name} scene{si} texts 数不一致"
        for eo, es in zip(entries, stexts):
            blocks_node = eo["v"][2]
            sval = es[2][2]
            if sval not in new_idx_of:
                new_idx_of[sval] = len(off.strings) + len(new_values)
                new_values.append(sval)
            nidx = new_idx_of[sval]
            boffs = blocks_node["offs"]
            shared = boffs[2] == boffs[0] or boffs[2] == boffs[1]
            tc_block = blocks_node["v"][2]
            if not shared:
                for slot in tc_block["v"][1:]:
                    assert slot["k"] == "str" and slot["w"] == 2
                    inplace.append((slot["idx_pos"], nidx))
            else:
                n_shared += 1
                # 副本：原块字节 + 相对位置改索引
                bs, be = tc_block["s"], tc_block["e"]
                copy = bytearray(off_bytes[bs:be])
                for slot in tc_block["v"][1:]:
                    assert slot["k"] == "str" and slot["w"] == 2
                    struct.pack_into("<H", copy, slot["idx_pos"] - bs, nidx)
                # 重建 [2] 列表：偏移加宽 3B，元素顺序打包，块2 指向末尾副本
                kids = blocks_node["v"]
                ls, le = blocks_node["s"], blocks_node["e"]
                hdr_t = off_bytes[ls + 1]; cw = hdr_t - 0x0D + 1
                cnt = len(kids)
                elems = []
                for j, kid in enumerate(kids):
                    if j == 2: continue
                    elems.append(bytes(off_bytes[kid["s"]:kid["e"]]))
                new_offs = []; acc = 0; body = bytearray()
                # 先按 [块0, 块1] 打包，再接副本；offs 按原槽序回填
                pos_of = {}
                for j, kid in enumerate(kids):
                    if j == 2: continue
                    pos_of[j] = acc; b = bytes(off_bytes[kid["s"]:kid["e"]]); body += b; acc += len(b)
                pos_of[2] = acc; body += copy
                arr = bytearray([0x0D + cw - 1]) + cnt.to_bytes(cw, "little") + bytes([0x0C + 3])
                for j in range(cnt): arr += pos_of[j].to_bytes(3, "little")
                new_list = bytes([0x20]) + bytes(arr) + bytes(body)
                splices.append((ls, le, new_list))
    data = bytearray(off_bytes)
    for p, idx in inplace:
        struct.pack_into("<H", data, p, idx)
    # 拼接（从后往前），每次按祖先记录修正偏移
    records = list(off.offset_records)
    for ls, le, new_list in sorted(splices, key=lambda x: -x[0]):
        growth = len(new_list) - (le - ls)
        cur = bytes(data)
        for (vp, w, tgt) in records:
            if vp < ls and tgt >= le:
                val = int.from_bytes(cur[vp:vp + w], "little") + growth
                assert val < (1 << (8 * w)), f"{name} 祖先偏移溢出 @{vp}"
                data[vp:vp + w] = val.to_bytes(w, "little")
        data[ls:le] = new_list
        # 后续（更靠前）拼接的坐标不受影响（它们都在 ls 之前）
    growth_total = len(data) - len(off_bytes)
    # 字符串池（同 v1）
    pool = off.strings + new_values
    blob = bytearray(); offs = []
    for s in pool:
        offs.append(len(blob)); blob += s.encode("utf-8") + b"\x00"
    t = off_bytes[off.off_str_off]; cw = t - 0x0D + 1
    et = off_bytes[off.off_str_off + 1 + cw]; ew = et - 0x0C
    while (1 << (8 * ew)) <= offs[-1]: ew += 1
    arr = bytearray([0x0D + cw - 1]) + len(pool).to_bytes(cw, "little") + bytes([0x0C + ew])
    for o in offs: arr += o.to_bytes(ew, "little")
    out = bytearray()
    out += data[:off.off_str_off + growth_total]
    out += arr
    new_str_data = len(out)
    out += blob
    delta = len(out) - (off.off_chunk_off + growth_total)
    out += data[off.off_chunk_off + growth_total:]
    struct.pack_into("<I", out, 16, off.off_str_off + growth_total)  # off_str_off
    struct.pack_into("<I", out, 20, new_str_data)
    struct.pack_into("<I", out, 24, off.off_chunk_off + growth_total + delta)
    struct.pack_into("<I", out, 28, off.off_chunk_len + growth_total + delta)
    struct.pack_into("<I", out, 32, off.off_chunk_data + growth_total + delta)
    return bytes(out), {"patches": len(inplace), "shared": n_shared, "appended": len(new_values)}

def strip(x):
    if is_strval(x): return ("str", x[2])
    if isinstance(x, list): return [strip(y) for y in x]
    if isinstance(x, dict): return {k: strip(v) for k, v in x.items()}
    return x

def verify(name, off_bytes, sak_bytes, new_bytes):
    off = Psb(off_bytes); sak = Psb(sak_bytes); new = Psb(new_bytes)
    so, ss, sn = off.root["scenes"], sak.root["scenes"], new.root["scenes"]
    assert len(so) == len(sn)
    for si, sc in enumerate(so):
        ot, nt = sc.get("texts") or [], sn[si].get("texts") or []
        st = ss[si].get("texts") or [] if si < len(ss) else []
        assert len(ot) == len(nt) == len(st)
        for eo, en, es in zip(ot, nt, st):
            a, b = strip(eo), strip(en)
            for k in range(len(a)):
                if k == 2: continue
                assert a[k] == b[k], f"{name} s{si} 非[2]字段变了"
            assert a[2][0] == b[2][0] and a[2][1] == b[2][1], f"{name} s{si} 日/英块变了"
            for slot in b[2][2][1:]:
                assert slot == ("str", es[2][2]), f"{name} s{si} 繁中槽未对齐"
    assert new_bytes[new.off_chunk_off:] == off_bytes[off.off_chunk_off:], f"{name} chunk 尾变了"
    return True

if __name__ == "__main__":
    import argparse, os
    ap = argparse.ArgumentParser(description="官方 scn 繁中块换简中（樱空译文），日/英块与结构原样保留")
    ap.add_argument("--official", default="official", help="官方 scn 目录（a01.scn … a17.scn）")
    ap.add_argument("--sakura", default="sakura", help="樱空 scn 目录（a01.txt.scn … a17.txt.scn，unpack_momo 的输出）")
    ap.add_argument("--out", default="build-scn", help="输出目录")
    ap.add_argument("names", nargs="*", help="只处理指定文件（如 a01 a02），默认全部 17 个")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    names = a.names or [f"a{i:02d}" for i in range(1, 18)]
    for n in names:
        ob = open(f"{a.official}/{n}.scn", "rb").read()
        sb = open(f"{a.sakura}/{n}.txt.scn", "rb").read()
        out, st = build(n, ob, sb)
        verify(n, ob, sb, out)
        open(f"{a.out}/{n}.scn", "wb").write(out)
        print(n, "OK", st, f"大小 {len(ob)} → {len(out)}")
    print("全部验证通过")
