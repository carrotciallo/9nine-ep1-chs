"""KiriKiri/MDF 的 TLG5「raw」贴图编解码（`*.pimg` 里的图层资源）。

来源：GARbro `ArcFormats/KiriKiri/ImageTLG.cs` 的 TLG5 分支（W.Dee 原始实现
的 C# 移植），本文件是逐语义的 Python 移植；引擎级结论，改这里要两边同步。

文件结构（v5 = "TLG5.0\\0raw\\x1a"）：

    "TLG5.0\\0raw" (10) | 0x1a | colors | width u32 | height u32
    blockheight u32 | blocksize[nblocks] u32 × nblocks
    然后逐块、逐颜色平面：
        u8 mark    0 = LZSS 压缩，非 0 = 原始字节
        u32 size   该平面本块的数据长度
        payload    （压缩或原始）

平面数据是「行差分 + 颜色相关」编码，解码时按行还原：

    g 平面：acc1 += g                       -> out_G = (acc1 + prev_G)
    b 平面：c0 = b + g；acc0 += c0           -> out_B = (acc0 + prev_B)
    r 平面：c2 = r + g；acc2 += c2           -> out_R = (acc2 + prev_R)
    a 平面：acc3 += a                        -> out_A = (acc3 + prev_A)

其中 acc* 每行从 0 开始累加，prev_* 是上一行还原后的同列值（首行按 0 处理）。
LZSS 的 4096 字节滑窗在整张图的所有块、所有平面之间**连续**复用。

已知怪癖：GARbro 的首行分支把 alpha 直接写成 0xff（忽略 a 平面），这里照搬，
encode 时也会生成与之自洽的数据（首行 alpha 值不回读）。
"""

from __future__ import annotations

import struct

SIGNATURE = b"TLG5.0\x00raw\x1a"


class TlgError(Exception):
    pass


# --------------------------------------------------------------------- LZSS
def decompress_slide(inbuf: bytes, text: bytearray, r: int, out_size: int) -> tuple[bytes, int]:
    out = bytearray(out_size)
    o = 0
    flags = 0
    i = 0
    n = len(inbuf)
    while i < n and o < out_size:
        flags >>= 1
        if not (flags & 256):
            flags = inbuf[i] | 0xFF00
            i += 1
        if flags & 1:
            mpos = inbuf[i] | ((inbuf[i + 1] & 0x0F) << 8)
            mlen = (inbuf[i + 1] & 0xF0) >> 4
            i += 2
            mlen += 3
            if mlen == 18:
                mlen += inbuf[i]
                i += 1
            while mlen:
                c = text[mpos]
                text[r] = c
                mpos = (mpos + 1) & 0xFFF
                r = (r + 1) & 0xFFF
                if o < out_size:
                    out[o] = c
                    o += 1
                mlen -= 1
        else:
            c = inbuf[i]
            i += 1
            text[r] = c
            r = (r + 1) & 0xFFF
            if o < out_size:
                out[o] = c
                o += 1
    return bytes(out), r


# ------------------------------------------------------------------- decode
def decode(data: bytes) -> tuple[int, int, bytes]:
    """TLG5 平面 -> RGBA8。（TLG 内部是 BGRA 顺序，这里换回 RGBA）"""
    if data[:11] != SIGNATURE:
        raise TlgError(f"不是 TLG5 raw：{data[:11]!r}")
    colors = data[11]
    if colors not in (3, 4):
        raise TlgError(f"不支持的颜色数 {colors}")
    width, height, blockheight = struct.unpack_from("<III", data, 12)
    nblocks = (height - 1) // blockheight + 1
    pos = 24
    sizes = struct.unpack_from("<" + "I" * nblocks, data, pos)
    pos += 4 * nblocks

    stride = width * 4
    image = bytearray(height * stride)
    text = bytearray(4096)
    r = 0
    planes = [bytearray(blockheight * width + 10) for _ in range(colors)]
    prev_off = None          # 上一行的行首偏移（跨块保留；首行按 0 基准）
    y_blk = 0
    for b in range(nblocks):
        start = pos
        rows = min(blockheight, height - y_blk)
        for c in range(colors):
            mark = data[pos]
            (size,) = struct.unpack_from("<I", data, pos + 1)
            pos += 5
            buf = data[pos: pos + size]
            if len(buf) != size:
                raise TlgError("平面数据截断")
            pos += size
            out = bytearray(rows * width)
            if mark == 0:
                out, r = decompress_slide(buf, text, r, rows * width)
            else:
                out[: len(buf)] = buf
            planes[c][:rows * width] = out
        if pos - start != sizes[b]:
            raise TlgError(f"块 {b} 长度 {pos - start} != 表里 {sizes[b]}")
        # 还原像素
        for y in range(rows):
            row_off = (y_blk + y) * stride
            o = y * width
            acc_b = acc_g = acc_r = acc_a = 0
            for x in range(width):
                g = planes[1][o + x]
                b_ = planes[0][o + x] + g
                r_ = planes[2][o + x] + g
                acc_b = (acc_b + b_) & 0xFF
                acc_g = (acc_g + g) & 0xFF
                acc_r = (acc_r + r_) & 0xFF
                if colors == 4:
                    acc_a = (acc_a + planes[3][o + x]) & 0xFF
                if prev_off is None:
                    image[row_off + x * 4 + 0] = acc_r
                    image[row_off + x * 4 + 1] = acc_g
                    image[row_off + x * 4 + 2] = acc_b
                    image[row_off + x * 4 + 3] = acc_a if colors == 4 else 0xFF
                else:
                    p = prev_off + x * 4
                    image[row_off + x * 4 + 0] = (acc_r + image[p + 0]) & 0xFF
                    image[row_off + x * 4 + 1] = (acc_g + image[p + 1]) & 0xFF
                    image[row_off + x * 4 + 2] = (acc_b + image[p + 2]) & 0xFF
                    image[row_off + x * 4 + 3] = ((acc_a if colors == 4 else 0) + image[p + 3]) & 0xFF
            prev_off = row_off
        y_blk += rows
    return width, height, bytes(image)



# ------------------------------------------------------------------- encode
def encode(width: int, height: int, rgba: bytes, blockheight: int = 4) -> bytes:
    """RGBA8 -> TLG5（平面用 TLG5 自带的 LZSS 压缩，mark=0）。

    下发到 xp3 时条目本身还会被 zlib 压一遍，所以不做 LZSS；省掉编码器这一层
    风险。**注意**：解码端把图像首行的 alpha 固定成 0xff（GARbro/TVP 的实现），
    所以首行的 alpha 目标值必须给 0xff，否则往返不成立。
    """
    if len(rgba) != width * height * 4:
        raise TlgError("像素长度与尺寸不符")
    colors = 4
    nblocks = (height - 1) // blockheight + 1
    stride = width * 4
    bodies = bytearray()
    sizes = []
    text = bytearray(4096)
    r = 0
    y_blk = 0
    for _ in range(nblocks):
        start = len(bodies)
        rows = min(blockheight, height - y_blk)
        planes = [bytearray(rows * width) for _ in range(colors)]
        for y in range(rows):
            row_off = (y_blk + y) * stride
            o = y * width
            first = (y_blk + y) == 0
            prev = None if first else row_off - stride
            acc_b = acc_g = acc_r = acc_a = 0
            for x in range(width):
                p = row_off + x * 4
                R, G, B, A = rgba[p], rgba[p + 1], rgba[p + 2], rgba[p + 3]
                if first:
                    # 解码端首行：B/G/R 从 0 累加，alpha 硬写 0xff
                    pr = pg = pb = 0
                else:
                    q = prev + x * 4
                    pr, pg, pb = rgba[q], rgba[q + 1], rgba[q + 2]
                # 目标累计值（相对上一行）
                c_b = (B - pb) & 0xFF
                c_g = (G - pg) & 0xFF
                c_r = (R - pr) & 0xFF
                i_b = (c_b - acc_b) & 0xFF
                i_g = (c_g - acc_g) & 0xFF
                i_r = (c_r - acc_r) & 0xFF
                acc_b, acc_g, acc_r = c_b, c_g, c_r
                planes[0][o + x] = (i_b - i_g) & 0xFF   # B 平面（TLG 内部 BGRA）
                planes[1][o + x] = i_g                  # G 平面
                planes[2][o + x] = (i_r - i_g) & 0xFF   # R 平面
                if first:
                    c_a = A & 0xFF                      # 首行 alpha 基准是 0
                else:
                    q = prev + x * 4
                    c_a = (A - rgba[q + 3]) & 0xFF
                i_a = (c_a - acc_a) & 0xFF
                acc_a = c_a
                planes[3][o + x] = i_a
        for c in range(colors):
            payload, r = compress_slide_simple(bytes(planes[c]), text, r)
            bodies += bytes([0]) + struct.pack("<I", len(payload)) + payload
        sizes.append(len(bodies) - start)
        y_blk += rows

    head = bytearray(SIGNATURE)
    head.append(colors)
    head += struct.pack("<III", width, height, blockheight)
    head += b"".join(struct.pack("<I", s) for s in sizes)
    return bytes(head) + bytes(bodies)


def compress_slide_simple(plane: bytes, text: bytearray, r: int) -> tuple[bytes, int]:
    """把一段平面数据编成 TLG5 的 LZSS 流（贪心，3..273 字节匹配）。

    `text`/`r` 是跨平面、跨块复用的 4096 字节滑窗状态，调用方负责传回。
    匹配允许与自己重叠（解码端是逐字节复制，天然支持 run-length）。
    """
    n = len(plane)
    out = bytearray()
    index: dict[int, list[int]] = {}
    flags = 0
    flagpos = -1
    bit = 0
    i = 0
    while i < n:
        if bit == 0:
            flagpos = len(out)
            out.append(0)
        best_len = 0
        best_dist = 0
        if i + 3 <= n:
            key = plane[i] | (plane[i + 1] << 8) | (plane[i + 2] << 16)
            cands = index.get(key)
            if cands:
                for cand in reversed(cands[-48:]):
                    dist = i - cand
                    if dist <= 0 or dist > 4095:
                        continue
                    maxlen = min(18 + 255, n - i)
                    ln = 0
                    while ln < maxlen and plane[cand + ln] == plane[i + ln]:
                        ln += 1
                        if cand + ln > i:      # 重叠部分：解码端逐字节复制仍然成立
                            continue
                    if ln > best_len:
                        best_len = ln
                        best_dist = dist
                        if ln >= maxlen:
                            break
        if best_len >= 3:
            mpos = (r - best_dist) & 0xFFF
            if best_len >= 18:          # nibble 15 是「扩展长度」标记，真实长度-18 另存 1 字节
                nib = 15
                extra = best_len - 18
            else:
                nib = best_len - 3
                extra = None
            out.append(mpos & 0xFF)
            out.append(((mpos >> 8) & 0x0F) | (nib << 4))
            if extra is not None:
                out.append(extra)
            flags |= 1 << bit
            for k in range(best_len):
                text[r] = plane[i + k]
                r = (r + 1) & 0xFFF
                j = i + k
                if j + 3 <= n:
                    kk = plane[j] | (plane[j + 1] << 8) | (plane[j + 2] << 16)
                    index.setdefault(kk, []).append(j)
            i += best_len
        else:
            out.append(plane[i])
            text[r] = plane[i]
            r = (r + 1) & 0xFFF
            if i + 3 <= n:
                kk = plane[i] | (plane[i + 1] << 8) | (plane[i + 2] << 16)
                index.setdefault(kk, []).append(i)
            i += 1
        bit += 1
        if bit == 8:
            out[flagpos] = flags
            flags = 0
            bit = 0
    if bit:
        out[flagpos] = flags
    return bytes(out), r
