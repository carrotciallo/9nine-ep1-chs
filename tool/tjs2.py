"""TJS2 字节码（TJS2100）读取 + 反汇编。

用途：本作的引擎脚本是编译后的 TJS2 字节码（`TJS2100\\0` 头）。要看 `kag`/语言/字体这类
只存在于脚本层的逻辑，只能反汇编。这里只实现「读 + 反汇编」，不做反编译（不还原 TJS 源码）。

格式（krkrz `tTJSByteCodeLoader`）：

    header : "TJS2" "100\\0" u32 filesize
    DATA   : "DATA" u32 chunk_size | 常量池（byte/short/int/long/double/string/octet，各自 u32 计数）
    OBJS   : "OBJS" u32 chunk_size | i32 toplevel, i32 objcount, 然后逐对象：
             "TJS2" u32 size, parent, name_idx, context_type,
             max_variable_count, variable_reserve_count, max_frame_count,
             func_decl_arg_count, func_decl_unnamed_arg_array_base, func_decl_collapse_base,
             prop_setter, prop_getter, super_class_getter,
             srcpos(2×i32 数组), code(i32 计数 + i16 词), data(i32 计数 + (i16 type, i16 idx)),
             scgetterps(i32 计数 + i32), properties(i32 计数 + (i32 name, i32 obj))

字对齐：DATA 里的 byte/octet 段与 code（i16 词数为奇数时）按 4 字节对齐；short/string 按 2 段对齐。

指令编码：`code` 是 i16 词序列，第一个词是 VM 码，后续操作数个数随码而定（见 `_OP_*`）。
跳转目标是**相对当前指令起始词的下标**。
"""

from __future__ import annotations

import argparse
import io
import struct
import sys

TJS_SIG = b"TJS2100\x00"

# ---- Variant 类型（tTJSByteCodeLoader）
TYPE_VOID = 0
TYPE_OBJECT = 1
TYPE_INTER_OBJECT = 2
TYPE_STRING = 3
TYPE_OCTET = 4
TYPE_REAL = 5
TYPE_BYTE = 6
TYPE_SHORT = 7
TYPE_INTEGER = 8
TYPE_LONG = 9
TYPE_INTER_GENERATOR = 10

# ---- VM 码（krkrz tjsInterCodeGen.h，仅列到 127）
OP = {
    "NOP": 0, "CONST": 1, "CP": 2, "CL": 3, "CCL": 4, "TT": 5, "TF": 6, "CEQ": 7, "CDEQ": 8,
    "CLT": 9, "CGT": 10, "SETF": 11, "SETNF": 12, "LNOT": 13, "NF": 14, "JF": 15, "JNF": 16,
    "JMP": 17, "INC": 18, "INCPD": 19, "INCPI": 20, "INCP": 21, "DEC": 22, "DECPD": 23, "DECPI": 24,
    "DECP": 25, "LOR": 26, "LORPD": 27, "LORPI": 28, "LORP": 29, "LAND": 30, "LANDPD": 31,
    "LANDPI": 32, "LANDP": 33, "BOR": 34, "BORPD": 35, "BORPI": 36, "BORP": 37, "BXOR": 38,
    "BXORPD": 39, "BXORPI": 40, "BXORP": 41, "BAND": 42, "BANDPD": 43, "BANDPI": 44, "BANDP": 45,
    "SAR": 46, "SARPD": 47, "SARPI": 48, "SARP": 49, "SAL": 50, "SALPD": 51, "SALPI": 52, "SALP": 53,
    "SR": 54, "SRPD": 55, "SRPI": 56, "SRP": 57, "ADD": 58, "ADDPD": 59, "ADDPI": 60, "ADDP": 61,
    "SUB": 62, "SUBPD": 63, "SUBPI": 64, "SUBP": 65, "MOD": 66, "MODPD": 67, "MODPI": 68, "MODP": 69,
    "DIV": 70, "DIVPD": 71, "DIVPI": 72, "DIVP": 73, "IDIV": 74, "IDIVPD": 75, "IDIVPI": 76,
    "IDIVP": 77, "MUL": 78, "MULPD": 79, "MULPI": 80, "MULP": 81, "BNOT": 82, "TYPEOF": 83,
    "TYPEOFD": 84, "TYPEOFI": 85, "EVAL": 86, "EEXP": 87, "CHKINS": 88, "ASC": 89, "CHR": 90,
    "NUM": 91, "CHS": 92, "INV": 93, "CHKINV": 94, "INT": 95, "REAL": 96, "STR": 97, "OCTET": 98,
    "CALL": 99, "CALLD": 100, "CALLI": 101, "NEW": 102, "GPD": 103, "SPD": 104, "SPDE": 105,
    "SPDEH": 106, "GPI": 107, "SPI": 108, "SPIE": 109, "GPDS": 110, "SPDS": 111, "GPIS": 112,
    "SPIS": 113, "SETP": 114, "GETP": 115, "DELD": 116, "DELI": 117, "SRV": 118, "RET": 119,
    "ENTRY": 120, "EXTRY": 121, "THROW": 122, "CHGTHIS": 123, "GLOBAL": 124, "ADDCI": 125,
    "REGMEMBER": 126, "DEBUGGER": 127,
}
OPNAME = {v: k for k, v in OP.items()}

_BINARY = ["LOR", "LAND", "BOR", "BXOR", "BAND", "SAR", "SAL", "SR", "ADD", "SUB", "MOD", "DIV",
           "IDIV", "MUL"]
_ONE_REG = ["CL", "SRV", "GLOBAL", "THROW", "TT", "TF", "SETF", "SETNF", "LNOT", "BNOT", "ASC",
            "CHR", "NUM", "CHS", "INV", "CHKINV", "TYPEOF", "EVAL", "EEXP", "INT", "REAL", "STR",
            "OCTET"]
_REG_REG = ["CP", "CEQ", "CDEQ", "CLT", "CGT", "CHKINS", "ADDCI", "CHGTHIS"]
_NO_OPERAND = ["RET", "NOP", "NF", "EXTRY", "REGMEMBER", "DEBUGGER"]
_JUMP = ["JF", "JNF", "JMP"]


class Tjs2Error(Exception):
    pass


class Variant:
    """一条 vdata：类型 + 池下标（或 void/null）。"""

    __slots__ = ("type", "index")

    def __init__(self, type_: int, index: int = 0):
        self.type = type_
        self.index = index

    def readable(self, pools: "Pools") -> str:
        t = self.type
        if t == TYPE_VOID:
            return "void"
        if t == TYPE_OBJECT:
            return "null"
        if t == TYPE_INTER_OBJECT:
            return f"#inter_object({self.index})"
        if t == TYPE_INTER_GENERATOR:
            return f"#inter_generator({self.index})"
        if t == TYPE_STRING:
            return '"' + pools.strings[self.index].replace("\\", "\\\\").replace('"', '\\"') + '"'
        if t == TYPE_OCTET:
            return f"#octet(len={len(pools.octets[self.index])})"
        if t == TYPE_REAL:
            return f"#real({pools.doubles[self.index]})"
        if t == TYPE_BYTE:
            return f"#byte({pools.bytes[self.index]})"
        if t == TYPE_SHORT:
            return f"#short({pools.shorts[self.index]})"
        if t == TYPE_INTEGER:
            return f"#int({pools.ints[self.index]})"
        if t == TYPE_LONG:
            return f"#long({pools.longs[self.index]})"
        return f"#unknown(type={t})"

    def string_value(self, pools: "Pools") -> str | None:
        return pools.strings[self.index] if self.type == TYPE_STRING else None


class Pools:
    def __init__(self):
        self.bytes: list[int] = []
        self.shorts: list[int] = []
        self.ints: list[int] = []
        self.longs: list[int] = []
        self.doubles: list[float] = []
        self.strings: list[str] = []
        self.octets: list[bytes] = []


class TjsObject:
    def __init__(self, index: int):
        self.index = index
        self.parent = 0
        self.name_index = -1
        self.name: str | None = None
        self.context_type = 0
        self.max_variable_count = 0
        self.variable_reserve_count = 0
        self.max_frame_count = 0
        self.func_decl_arg_count = 0
        self.func_decl_unnamed_arg_array_base = 0
        self.func_decl_collapse_base = 0
        self.prop_setter = 0
        self.prop_getter = 0
        self.super_class_getter = 0
        self.code: list[int] = []
        self.data: list[Variant] = []
        self.properties: list[tuple[int, int]] = []


class Tjs2File:
    def __init__(self):
        self.pools = Pools()
        self.toplevel = 0
        self.objects: list[TjsObject] = []

    # --- 便于分析的小工具 -------------------------------------------------
    def object_by_name(self, name: str) -> TjsObject | None:
        for obj in self.objects:
            if obj.name == name:
                return obj
        return None

    def const_strings(self, obj: TjsObject) -> list[str]:
        out = []
        for v in obj.data:
            s = v.string_value(self.pools)
            if s is not None and s not in out:
                out.append(s)
        return out


class _Reader:
    def __init__(self, buf: bytes):
        self.buf = buf
        self.pos = 0

    def take(self, n: int) -> bytes:
        if self.pos + n > len(self.buf):
            raise Tjs2Error(f"truncated: need {n} at 0x{self.pos:x}")
        out = self.buf[self.pos:self.pos + n]
        self.pos += n
        return out

    def u16(self) -> int:
        return struct.unpack("<H", self.take(2))[0]

    def i16(self) -> int:
        return struct.unpack("<h", self.take(2))[0]

    def u32(self) -> int:
        return struct.unpack("<I", self.take(4))[0]

    def i32(self) -> int:
        return struct.unpack("<i", self.take(4))[0]

    def i64(self) -> int:
        return struct.unpack("<q", self.take(8))[0]

    def u64(self) -> int:
        return struct.unpack("<Q", self.take(8))[0]

    def align4(self) -> None:
        rem = self.pos & 3
        if rem:
            self.take(4 - rem)


def _read_pools(reader: _Reader) -> Pools:
    pools = Pools()
    n = reader.u32()
    if n:
        pools.bytes = list(reader.take(n))
        reader.align4()
    n = reader.u32()
    if n:
        pools.shorts = [reader.i16() for _ in range(n)]
        if n & 1:
            reader.u16()
    n = reader.u32()
    if n:
        pools.ints = [reader.i32() for _ in range(n)]
    n = reader.u32()
    if n:
        pools.longs = [reader.i64() for _ in range(n)]
    n = reader.u32()
    if n:
        pools.doubles = [struct.unpack("<d", reader.take(8))[0] for _ in range(n)]
    n = reader.u32()
    for _ in range(n):
        length = reader.u32()
        raw = reader.take(length * 2)
        pools.strings.append(raw.decode("utf-16-le", "replace"))
        if length & 1:
            reader.u16()
    n = reader.u32()
    for _ in range(n):
        size = reader.u32()
        pools.octets.append(reader.take(size))
        reader.align4()
    if reader.pos != len(reader.buf):
        raise Tjs2Error(f"DATA 未读完：pos={reader.pos}, size={len(reader.buf)}")
    return pools


def load(data: bytes) -> Tjs2File:
    """解析一个 TJS2100 字节码文件。"""
    if not data.startswith(TJS_SIG):
        raise Tjs2Error(f"不是 TJS2 字节码：{data[:8]!r}")
    reader = _Reader(data)
    reader.take(8)
    size = reader.u32()
    if size != len(data):
        raise Tjs2Error(f"文件长度不符：头 {size} != 实际 {len(data)}")

    tag = reader.take(4)
    if tag != b"DATA":
        raise Tjs2Error(f"缺少 DATA 段：{tag!r}")
    data_chunk = reader.u32()
    data_reader = _Reader(reader.take(data_chunk - 8))

    tag = reader.take(4)
    if tag != b"OBJS":
        raise Tjs2Error(f"缺少 OBJS 段：{tag!r}")
    objs_chunk = reader.u32()
    objs_reader = _Reader(reader.take(objs_chunk - 8))

    f = Tjs2File()
    f.pools = _read_pools(data_reader)

    f.toplevel = objs_reader.i32()
    count = objs_reader.i32()
    if count < 0:
        raise Tjs2Error(f"对象数为负：{count}")
    for index in range(count):
        tag = objs_reader.take(4)
        if tag != b"TJS2":
            raise Tjs2Error(f"对象 {index} 头不符：{tag!r}")
        objs_reader.u32()  # 对象块长度（含头），按字段顺序继续读即可
        obj = TjsObject(index)
        obj.parent = objs_reader.i32()
        obj.name_index = objs_reader.i32()
        obj.context_type = objs_reader.i32()
        obj.max_variable_count = objs_reader.i32()
        obj.variable_reserve_count = objs_reader.i32()
        obj.max_frame_count = objs_reader.i32()
        obj.func_decl_arg_count = objs_reader.i32()
        obj.func_decl_unnamed_arg_array_base = objs_reader.i32()
        obj.func_decl_collapse_base = objs_reader.i32()
        obj.prop_setter = objs_reader.i32()
        obj.prop_getter = objs_reader.i32()
        obj.super_class_getter = objs_reader.i32()
        srcpos = objs_reader.i32()
        if srcpos < 0:
            raise Tjs2Error(f"对象 {index} srcpos 为负：{srcpos}")
        for _ in range(srcpos * 2):
            objs_reader.i32()
        code_count = objs_reader.i32()
        if code_count < 0:
            raise Tjs2Error(f"对象 {index} code 计数为负：{code_count}")
        for _ in range(code_count):
            obj.code.append(objs_reader.i16())
        if code_count & 1:
            objs_reader.u16()
        data_count = objs_reader.i32()
        if data_count < 0:
            raise Tjs2Error(f"对象 {index} data 计数为负：{data_count}")
        for _ in range(data_count):
            obj.data.append(Variant(objs_reader.i16(), objs_reader.i16()))
        scg_count = objs_reader.i32()
        if scg_count < 0:
            raise Tjs2Error(f"对象 {index} scgetterps 为负：{scg_count}")
        for _ in range(scg_count):
            objs_reader.i32()
        prop_count = objs_reader.i32()
        if prop_count < 0:
            raise Tjs2Error(f"对象 {index} properties 为负：{prop_count}")
        for _ in range(prop_count):
            name_idx = objs_reader.i32()
            prop_obj = objs_reader.i32()
            obj.properties.append((name_idx, prop_obj))
        if 0 <= obj.name_index < len(f.pools.strings):
            obj.name = f.pools.strings[obj.name_index]
        f.objects.append(obj)

    if objs_reader.pos != len(objs_reader.buf):
        raise Tjs2Error(f"OBJS 未读完：pos={objs_reader.pos}, size={len(objs_reader.buf)}")
    return f


# ------------------------------------------------------------------ 反汇编
def _need(code: list[int], i: int, n: int) -> None:
    if i + n > len(code):
        raise Tjs2Error(f"指令被截断：pos={i} 需要 {n} 词，共 {len(code)}")


def _fmt_reg(x: int) -> str:
    return f"%{x}"


def _fmt_target(i: int, rel: int) -> str:
    return f"{i + rel:06d}"


def _data_comment(obj: TjsObject, pools: Pools, idx: int) -> str:
    if 0 <= idx < len(obj.data):
        return f"*{idx} = {obj.data[idx].readable(pools)}"
    return ""


def disasm_instruction(obj: TjsObject, pools: Pools, i: int) -> tuple[str, str, int]:
    """返回 (助记符+操作数, 注释, 本指令占多少词)。"""
    code = obj.code
    op = code[i]
    name = OPNAME.get(op, f"<op{op}>")

    if name in _NO_OPERAND:
        return name.lower(), "", 1

    if name == "CONST":
        _need(code, i, 3)
        dst, src = code[i + 1], code[i + 2]
        return f"const {_fmt_reg(dst)}, *{src}", _data_comment(obj, pools, src), 3

    if name in _REG_REG:
        _need(code, i, 3)
        return f"{name.lower()} {_fmt_reg(code[i+1])}, {_fmt_reg(code[i+2])}", "", 3

    if name in _ONE_REG:
        _need(code, i, 2)
        return f"{name.lower()} {_fmt_reg(code[i+1])}", "", 2

    if name == "CCL":
        _need(code, i, 3)
        r0, cnt = code[i + 1], code[i + 2]
        return f"ccl %{r0}-%{r0 + cnt - 1}", "", 3

    if name in _JUMP:
        _need(code, i, 2)
        return f"{name.lower()} {_fmt_target(i, code[i+1])}", "", 2

    if name == "ENTRY":
        _need(code, i, 3)
        return f"entry {_fmt_target(i, code[i+1])}, {_fmt_reg(code[i+2])}", "", 3

    if name in ("SETP", "GETP"):
        _need(code, i, 3)
        return f"{name.lower()} {_fmt_reg(code[i+1])}, {_fmt_reg(code[i+2])}", "", 3

    if name in ("DELD", "TYPEOFD"):
        _need(code, i, 4)
        idx = code[i + 3]
        return (f"{name.lower()} {_fmt_reg(code[i+1])}, {_fmt_reg(code[i+2])}.*{idx}",
                _data_comment(obj, pools, idx), 4)

    if name in ("DELI", "TYPEOFI"):
        _need(code, i, 4)
        return (f"{name.lower()} {_fmt_reg(code[i+1])}, {_fmt_reg(code[i+2])}.{_fmt_reg(code[i+3])}",
                "", 4)

    if name in ("GPD", "GPDS"):
        _need(code, i, 4)
        dst, objreg, idx = code[i + 1], code[i + 2], code[i + 3]
        return (f"{name.lower()} {_fmt_reg(dst)}, {_fmt_reg(objreg)}.*{idx}",
                _data_comment(obj, pools, idx), 4)

    if name in ("SPD", "SPDE", "SPDEH", "SPDS"):
        _need(code, i, 4)
        objreg, idx, src = code[i + 1], code[i + 2], code[i + 3]
        return (f"{name.lower()} {_fmt_reg(objreg)}.*{idx}, {_fmt_reg(src)}",
                _data_comment(obj, pools, idx), 4)

    if name in ("GPI", "GPIS"):
        _need(code, i, 4)
        return (f"{name.lower()} {_fmt_reg(code[i+1])}, {_fmt_reg(code[i+2])}.{_fmt_reg(code[i+3])}",
                "", 4)

    if name in ("SPI", "SPIE", "SPIS"):
        _need(code, i, 4)
        return (f"{name.lower()} {_fmt_reg(code[i+1])}.{_fmt_reg(code[i+2])}, {_fmt_reg(code[i+3])}",
                "", 4)

    # INC/DEC 及其 *(PD/PI/P) 变体
    for base, word in ((OP["INC"], "inc"), (OP["DEC"], "dec")):
        if base <= op <= base + 3:
            variant = op - base
            if variant == 0:
                _need(code, i, 2)
                return f"{word} {_fmt_reg(code[i+1])}", "", 2
            if variant == 1:
                _need(code, i, 4)
                idx = code[i + 3]
                return (f"{word}pd {_fmt_reg(code[i+1])}, {_fmt_reg(code[i+2])}.*{idx}",
                        _data_comment(obj, pools, idx), 4)
            if variant == 2:
                _need(code, i, 4)
                return (f"{word}pi {_fmt_reg(code[i+1])}, {_fmt_reg(code[i+2])}.{_fmt_reg(code[i+3])}",
                        "", 4)
            _need(code, i, 3)
            return f"{word}p {_fmt_reg(code[i+1])}, {_fmt_reg(code[i+2])}", "", 3

    # 二元运算及其变体
    for word in _BINARY:
        base = OP[word]
        if base <= op <= base + 3:
            variant = op - base
            low = word.lower()
            if variant == 0:
                _need(code, i, 3)
                return f"{low} {_fmt_reg(code[i+1])}, {_fmt_reg(code[i+2])}", "", 3
            if variant == 1:
                _need(code, i, 5)
                idx = code[i + 3]
                return (f"{low}pd {_fmt_reg(code[i+1])}, {_fmt_reg(code[i+2])}.*{idx}, "
                        f"{_fmt_reg(code[i+4])}", _data_comment(obj, pools, idx), 5)
            if variant == 2:
                _need(code, i, 5)
                return (f"{low}pi {_fmt_reg(code[i+1])}, {_fmt_reg(code[i+2])}."
                        f"{_fmt_reg(code[i+3])}, {_fmt_reg(code[i+4])}", "", 5)
            _need(code, i, 4)
            return (f"{low}p {_fmt_reg(code[i+1])}, {_fmt_reg(code[i+2])}, {_fmt_reg(code[i+3])}",
                    "", 4)

    if name in ("CALL", "CALLD", "CALLI", "NEW"):
        if name == "CALL":
            _need(code, i, 4)
            head, st, data_idx = f"call {_fmt_reg(code[i+1])}, {_fmt_reg(code[i+2])}(", 4, None
        elif name == "NEW":
            _need(code, i, 4)
            head, st, data_idx = f"new {_fmt_reg(code[i+1])}, {_fmt_reg(code[i+2])}(", 4, None
        elif name == "CALLD":
            _need(code, i, 5)
            data_idx = code[i + 3]
            head = f"calld {_fmt_reg(code[i+1])}, {_fmt_reg(code[i+2])}.*{data_idx}("
            st = 5
        else:
            _need(code, i, 5)
            head = (f"calli {_fmt_reg(code[i+1])}, {_fmt_reg(code[i+2])}."
                    f"{_fmt_reg(code[i+3])}(")
            st, data_idx = 5, None
        argc = code[i + st - 1]
        if argc == -1:
            size, tail = st, "...)"
        elif argc == -2:
            _need(code, i, st + 1)
            num = code[i + st]
            size = st + 1 + num * 2
            args = []
            for j in range(num):
                ty = code[i + st + 1 + j * 2]
                val = code[i + st + 1 + j * 2 + 1]
                if ty == 0:
                    args.append(_fmt_reg(val))
                elif ty == 1:
                    args.append(f"{_fmt_reg(val)}*")
                elif ty == 2:
                    args.append("*")
                else:
                    args.append(f"<fat:{ty}>")
            tail = ", ".join(args) + ")"
        else:
            size = st + argc
            tail = ", ".join(_fmt_reg(code[i + st + j]) for j in range(argc)) + ")"
        comment = ""
        if data_idx is not None:
            comment = _data_comment(obj, pools, data_idx)
        return head + tail, comment, size

    raise Tjs2Error(f"未知指令 {op} @ {i}（拒绝猜测长度）")


def disasm_object(obj: TjsObject, pools: Pools) -> list[str]:
    lines = []
    i = 0
    while i < len(obj.code):
        text, comment, size = disasm_instruction(obj, pools, i)
        line = f"{i:06d}  {text}"
        if comment:
            line += f"    ; {comment}"
        lines.append(line)
        i += size
    return lines


def disasm(f: Tjs2File, only: str | None = None) -> str:
    out = [f"toplevel: {f.toplevel}", f"objects: {len(f.objects)}", ""]
    for obj in f.objects:
        if only and obj.name != only:
            continue
        props = ", ".join(
            f"{f.pools.strings[n] if 0 <= n < len(f.pools.strings) else '?'}->{o}"
            for n, o in obj.properties)
        out.append(f"== object {obj.index}: name={obj.name!r} parent={obj.parent} "
                   f"context_type={obj.context_type} props=[{props}]")
        out.extend(disasm_object(obj, f.pools))
        out.append("")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", help="TJS2 字节码文件（TJS2100 头）")
    ap.add_argument("--out", help="输出文件（默认 stdout）")
    ap.add_argument("--only", help="只反汇编这个名字的函数/对象")
    ap.add_argument("--strings", action="store_true", help="只列出字符串常量池")
    args = ap.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    data = open(args.path, "rb").read()
    f = load(data)
    if args.strings:
        text = "\n".join(f"{i:4d}  {s}" for i, s in enumerate(f.pools.strings))
    else:
        text = disasm(f, args.only)
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as fp:
            fp.write(text + "\n")
        print(f"写出 {args.out}（{len(text.splitlines())} 行）")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
