"""PSB (M2 "Packaged Structure Binary") v3 reader / string-level rewriter.

Reference: FreeMote (https://github.com/UlyssesWu/FreeMote), files
  FreeMote.Psb/Psb.cs          (LoadFromStream / Unpack / LoadNames)
  FreeMote.Psb/PsbValues.cs    (PsbArray / PsbNumber / PsbString)
  FreeMote/PsbHeader.cs        (header layout, checksum)

Only what this project needs is implemented:
  * parse the whole object graph (dict / list / int / float / bool / None / str / resource)
  * rewrite the string pool in place (same string count, arbitrary new lengths)
  * MDF shell ("mdf\\0" + u32 raw length + zlib stream) used by this game's *.scn

All integers inside PSB are little-endian.
"""

from __future__ import annotations

import io
import re
import struct
import zlib

PSB_SIG = b"PSB\x00"
MDF_SIG = b"mdf\x00"

# PsbObjType
NONE = 0x00
NULL = 0x01
FALSE = 0x02
TRUE = 0x03
NUMBER_N0 = 0x04
NUMBER_N1 = 0x05
NUMBER_N8 = 0x0C
ARRAY_N1 = 0x0D
ARRAY_N8 = 0x14
STRING_N1 = 0x15
STRING_N4 = 0x18
RESOURCE_N1 = 0x19
RESOURCE_N4 = 0x1C
FLOAT0 = 0x1D
FLOAT = 0x1E
DOUBLE = 0x1F
LIST = 0x20
OBJECTS = 0x21
EXTRA_CHUNK_N1 = 0x22
EXTRA_CHUNK_N4 = 0x25


class PsbError(Exception):
    pass


class _Root:
    """Sentinel: "walk from the root" (distinct from a real `None` node)."""


_ROOT = _Root()


class PsbString:
    """A string slot: `index` is the offset-table index, `value` the decoded text."""

    __slots__ = ("index", "value")

    def __init__(self, index: int, value: str | None = None):
        self.index = index
        self.value = value

    def __repr__(self):
        return f"PsbString(#{self.index}, {self.value!r})"

    def __eq__(self, other):
        return isinstance(other, PsbString) and self.index == other.index

    def __hash__(self):
        return hash(("psbstr", self.index))


class PsbResource:
    __slots__ = ("index", "is_extra", "data")

    def __init__(self, index: int, is_extra: bool = False):
        self.index = index
        self.is_extra = is_extra
        self.data = None

    def __repr__(self):
        return f"PsbResource(#{self.index}{'x' if self.is_extra else ''})"


def _read_le(br: io.BytesIO, n: int) -> int:
    b = br.read(n)
    if len(b) != n:
        raise PsbError("unexpected EOF")
    return int.from_bytes(b, "little")


def _read_array(br: io.BytesIO) -> list[int]:
    """PsbArray: type byte (ArrayN1..N8) -> count bytes, entry-type byte -> entry width."""
    t = br.read(1)
    if not t:
        raise PsbError("unexpected EOF in array")
    t = t[0]
    if not (ARRAY_N1 <= t <= ARRAY_N8):
        raise PsbError(f"not an array type byte: 0x{t:02x} at 0x{br.tell() - 1:x}")
    count = _read_le(br, t - ARRAY_N1 + 1)
    entry_type = br.read(1)[0]
    entry_len = entry_type - NUMBER_N8
    if entry_len == 0 and count == 0:
        return []
    if not (1 <= entry_len <= 8):
        raise PsbError(f"bad array entry width {entry_len}")
    buf = br.read(entry_len * count)
    if len(buf) != entry_len * count:
        raise PsbError("unexpected EOF in array body")
    return [int.from_bytes(buf[i * entry_len:(i + 1) * entry_len], "little") for i in range(count)]


def _array_type(count: int) -> tuple[int, int]:
    """Return (type byte, count-width) for a count value."""
    for width in range(1, 9):
        if count < (1 << (8 * width)):
            return ARRAY_N1 + width - 1, width
    raise PsbError("array too long")


def _read_array_style(br: io.BytesIO) -> tuple[list[int], int, int]:
    """Like _read_array but also reports (count_width, entry_width)."""
    t = br.read(1)[0]
    if not (ARRAY_N1 <= t <= ARRAY_N8):
        raise PsbError(f"not an array type byte: 0x{t:02x}")
    count_width = t - ARRAY_N1 + 1
    count = _read_le(br, count_width)
    entry_width = br.read(1)[0] - NUMBER_N8
    if entry_width == 0 and count == 0:
        return [], count_width, 0
    if not (1 <= entry_width <= 8):
        raise PsbError(f"bad array entry width {entry_width}")
    buf = br.read(entry_width * count)
    if len(buf) != entry_width * count:
        raise PsbError("unexpected EOF in array body")
    return ([int.from_bytes(buf[i * entry_width:(i + 1) * entry_width], "little") for i in range(count)],
            count_width, entry_width)


def _pack_array_styled(values: list[int], count_width: int | None = None,
                       entry_width: int | None = None) -> bytes:
    """Encode a PsbArray, keeping the original field widths when they still fit."""
    needed_entry = 0
    for v in values:
        for w in range(1, 9):
            if v < (1 << (8 * w)):
                needed_entry = max(needed_entry, w)
                break
    if entry_width is not None:
        needed_entry = max(needed_entry, entry_width)
    needed_count = 1
    for w in range(1, 9):
        if len(values) < (1 << (8 * w)):
            needed_count = w
            break
    if count_width is not None:
        needed_count = max(needed_count, count_width)
    out = bytearray([ARRAY_N1 + needed_count - 1])
    out += len(values).to_bytes(needed_count, "little")
    out.append(NUMBER_N8 + needed_entry)
    for v in values:
        out += v.to_bytes(needed_entry, "little")
    return bytes(out)


def _pack_array(values: list[int]) -> bytes:
    if not values:
        return bytes([ARRAY_N1, 0, NUMBER_N1])
    width = 1
    for v in values:
        for w in range(1, 9):
            if v < (1 << (8 * w)):
                width = max(width, w)
                break
    type_byte, count_width = _array_type(len(values))
    out = bytearray([type_byte])
    out += len(values).to_bytes(count_width, "little")
    out.append(NUMBER_N8 + width)
    for v in values:
        out += v.to_bytes(width, "little")
    return bytes(out)


class PsbFile:
    """Parsed PSB (optionally wrapped in an MDF shell)."""

    def __init__(self, data: bytes):
        self.raw = data
        self.is_mdf = data[:3].lower() == b"mdf"
        body = data
        if self.is_mdf:
            self.mdf_length = struct.unpack_from("<I", data, 4)[0]
            body = zlib.decompress(data[8:])
            if len(body) != self.mdf_length:
                raise PsbError(f"mdf length mismatch: {len(body)} != {self.mdf_length}")
        self.body = body
        self.int_slots: list[tuple[str, int, int, int]] = []
        self.str_slots: list[tuple[str, int, int, int]] = []
        self._record_ints = False
        self._parse()

    # ---------------------------------------------------------------- parse
    def _parse(self):
        body = self.body
        if body[:4] != PSB_SIG:
            raise PsbError(f"not a PSB: {body[:4]!r}")
        self.version = struct.unpack_from("<H", body, 4)[0]
        self.header_encrypt = struct.unpack_from("<H", body, 6)[0]
        if self.header_encrypt:
            raise PsbError("encrypted header is not supported")
        if self.version != 3:
            raise PsbError(f"unsupported PSB version {self.version}")
        (self.header_length, self.offset_names, self.offset_strings,
         self.offset_strings_data, self.offset_chunk_offsets, self.offset_chunk_lengths,
         self.offset_chunk_data, self.offset_entries, self.checksum) = struct.unpack_from("<9I", body, 8)

        br = io.BytesIO(body)
        # --- names (charset / trie data / trie roots)
        br.seek(self.offset_names)
        self.charset = _read_array(br)
        self.names_data = _read_array(br)
        self.name_indexes = _read_array(br)
        self.names = [self._decode_name(i) for i in self.name_indexes]

        # --- string offset table
        br.seek(self.offset_strings)
        self.string_offsets, self._str_count_width, self._str_entry_width = _read_array_style(br)
        self.strings: dict[int, PsbString] = {}
        self.string_order: list[int] = []

        # --- resources
        br.seek(self.offset_chunk_offsets)
        self.chunk_offsets = _read_array(br)
        br.seek(self.offset_chunk_lengths)
        self.chunk_lengths = _read_array(br)
        self.resources: dict[object, PsbResource] = {}

        # --- object graph
        br.seek(self.offset_entries)
        self.root = self._unpack(br)

    def _note_int(self, path, pos, width, value):
        if self._record_ints:
            self.int_slots.append((path, pos, width, value))

    def _note_str(self, path, pos, width, index):
        if self._record_ints:
            self.str_slots.append((path, pos, width, index))

    def record_slots(self, prefix: str = "$"):
        """One traversal -> (int_slots, str_slots), both filtered by `prefix`.

        Use this instead of calling `find_ints` and `find_str_refs` one after the other:
        each of those re-walks the whole object graph (with a path string per node), which
        dominates the cost of a write-back run.
        """
        self.int_slots = []
        self.str_slots = []
        self._record_ints = True
        br = io.BytesIO(self.body)
        br.seek(self.offset_entries)
        try:
            self._unpack(br, "$")
        finally:
            self._record_ints = False
        ints = [s for s in self.int_slots if s[0].startswith(prefix)]
        strs = [s for s in self.str_slots if s[0].startswith(prefix)]
        return ints, strs

    def find_ints(self, prefix: str = "$") -> list[tuple[str, int, int, int]]:
        """[(path, byte_pos, byte_width, value)] for every integer in the graph.

        The positions are absolute offsets inside `body`; the type byte sits at `byte_pos`
        and the little-endian value follows it (`byte_width` bytes, 0 for the value 0 type).
        """
        self.int_slots = []
        self.str_slots = []
        self._record_ints = True
        br = io.BytesIO(self.body)
        br.seek(self.offset_entries)
        try:
            self._unpack(br, "$")
        finally:
            self._record_ints = False
        return [slot for slot in self.int_slots if slot[0].startswith(prefix)]

    def find_str_refs(self, prefix: str = "$") -> list[tuple[str, int, int, int]]:
        """[(path, byte_pos, byte_width, string_index)] for every string *reference*.

        Same shape as `find_ints`; lets a caller re-point one reference at another slot
        provided the new index fits the existing inline width.
        """
        if not self._record_ints:
            self.find_ints(prefix)
        return [slot for slot in self.str_slots if slot[0].startswith(prefix)]

    def _decode_name(self, root_idx: int) -> str:
        out = []
        node = self.names_data[root_idx]
        for _ in range(4096):
            if node == 0:
                break
            nxt = self.names_data[node]
            delta = self.charset[nxt]
            out.append((node - delta) & 0xFF)
            node = nxt
        else:
            raise PsbError("name trie loop")
        out.reverse()
        return bytes(out).decode("utf-8", errors="replace")

    def get_string(self, index: int) -> PsbString:
        """Resolve a string slot by index (cached)."""
        s = self.strings.get(index)
        if s is not None:
            return s
        start = self.offset_strings_data + self.string_offsets[index]
        end = self.body.index(b"\x00", start)
        s = PsbString(index, self.body[start:end].decode("utf-8", errors="replace"))
        self.strings[index] = s
        self.string_order.append(index)
        return s

    def string_value(self, index: int) -> str:
        return self.get_string(index).value

    def _unpack(self, br: io.BytesIO, path: str = "$"):
        pos = br.tell()
        t = br.read(1)
        if not t:
            raise PsbError("unexpected EOF in object")
        t = t[0]
        if t in (NONE, NULL):
            return None
        if t == FALSE:
            return False
        if t == TRUE:
            return True
        if t == NUMBER_N0:
            self._note_int(path, pos, 0, 0)
            return 0
        if NUMBER_N1 <= t <= NUMBER_N8:
            width = t - NUMBER_N0
            value = _read_le(br, width)
            self._note_int(path, pos, width, value)
            return value
        if ARRAY_N1 <= t <= ARRAY_N8:
            br.seek(pos)
            return _read_array(br)
        if STRING_N1 <= t <= STRING_N4:
            width = t - STRING_N1 + 1
            index = _read_le(br, width)
            self._note_str(path, pos, width, index)
            return self.get_string(index)
        if RESOURCE_N1 <= t <= RESOURCE_N4:
            idx = _read_le(br, t - RESOURCE_N1 + 1)
            res = self.resources.get(idx)
            if res is None:
                res = self.resources[idx] = PsbResource(idx)
            return res
        if t == FLOAT0:
            return 0.0
        if t == FLOAT:
            return struct.unpack("<f", br.read(4))[0]
        if t == DOUBLE:
            return struct.unpack("<d", br.read(8))[0]
        if t == LIST:
            offsets = _read_array(br)
            base = br.tell()
            out = []
            for i, off in enumerate(offsets):
                br.seek(base + off)
                out.append(self._unpack(br, f"{path}[{i}]"))
            br.seek(base)
            return out
        if t == OBJECTS:
            name_refs = _read_array(br)
            offsets = _read_array(br)
            base = br.tell()
            out = {}
            for i, nref in enumerate(name_refs):
                br.seek(base + offsets[i])
                key = self.names[nref]
                out[key] = self._unpack(br, f"{path}.{key}")
            br.seek(base)
            return out
        if EXTRA_CHUNK_N1 <= t <= EXTRA_CHUNK_N4:
            idx = _read_le(br, t - EXTRA_CHUNK_N1 + 1)
            key = ("x", idx)
            res = self.resources.get(key)
            if res is None:
                res = self.resources[key] = PsbResource(idx, True)
            return res
        raise PsbError(f"unknown object type 0x{t:02x} at 0x{pos:x}")

    # ---------------------------------------------------------------- write
    def rebuild(self, new_strings: dict[int, str] | None = None,
                extra_strings: list[str] | None = None, body: bytes | None = None) -> bytes:
        """Re-emit the file, replacing the given slots and optionally appending new ones.

        Everything except the string pool is copied verbatim, so the object graph,
        name trie and resource chunks stay byte-identical. Appended slots take the indexes
        `len(string_offsets) + k`; a caller that wants to use them must re-point the
        referencing inline index in place (same byte width) before calling rebuild.
        """
        new_strings = new_strings or {}
        extra_strings = extra_strings or []
        # `body` lets a caller hand over a copy whose graph was already patched in place
        # (e.g. re-pointed string references); the layout is unchanged, only values differ.
        src = self.body if body is None else body
        count = len(self.string_offsets)
        data = bytearray()
        offsets = []
        for i in range(count + len(extra_strings)):
            offsets.append(len(data))
            if i >= count:
                raw = extra_strings[i - count].encode("utf-8")
                data += raw + b"\x00"
                continue
            value = new_strings.get(i)
            if value is None:
                start = self.offset_strings_data + self.string_offsets[i]
                end = self.body.index(b"\x00", start)
                raw = self.body[start:end]
            else:
                raw = value.encode("utf-8")
            data += raw + b"\x00"

        offsets_blob = _pack_array_styled(offsets, self._str_count_width, self._str_entry_width)
        header = bytearray(src[:self.header_length])
        names_region = src[self.header_length:self.offset_strings]
        tail = src[self.offset_chunk_offsets:]

        new_offsets_strings_data = self.offset_strings + len(offsets_blob)
        shift = (len(offsets_blob) - (self.offset_strings_data - self.offset_strings)) + \
                (len(data) - (self.offset_chunk_offsets - self.offset_strings_data))

        # `offset_entries` points *inside* the names region (before the string tables), so it
        # must NOT be shifted -- shifting it silently corrupted every grown file while the
        # zero-change round-trip (shift == 0) still looked perfect.
        if self.offset_entries >= self.offset_strings:
            raise PsbError("unexpected layout: object graph is not inside the names region")
        vals = [self.header_length, self.offset_names, self.offset_strings,
                new_offsets_strings_data,
                self.offset_chunk_offsets + shift, self.offset_chunk_lengths + shift,
                self.offset_chunk_data + shift, self.offset_entries]
        struct.pack_into("<8I", header, 8, *vals)
        checksum = zlib.adler32(bytes(header[8:8 + 32])) & 0xFFFFFFFF
        struct.pack_into("<I", header, 0x28, checksum)

        body = bytes(header) + names_region + offsets_blob + bytes(data) + tail
        if self.is_mdf:
            return MDF_SIG + struct.pack("<I", len(body)) + zlib.compress(body, 9)
        return body

    def patch_ints(self, edits) -> bytes:
        """Rewrite inline integer / string-index slots in place (same byte width).

        `edits` = iterable of (byte_pos, byte_width, new_value) for an integer slot, or
        (byte_pos, byte_width, new_value, "str") for a string-reference slot. Raises when the
        new value does not fit the existing width -- growing it would move every following
        offset and would need a full object-graph serialiser.
        """
        body = bytearray(self.body)
        for edit in edits:
            pos, width, value = edit[0], edit[1], edit[2]
            kind = edit[3] if len(edit) > 3 else "int"
            if kind == "str":
                if width == 0:
                    raise PsbError(f"string slot at 0x{pos:x} has no inline width")
                if not 0 <= value < (1 << (8 * width)):
                    raise PsbError(f"string index {value} does not fit {width} byte(s) "
                                   f"at 0x{pos:x}")
                body[pos] = STRING_N1 + width - 1
            else:
                if width == 0:
                    if value != 0:
                        raise PsbError(f"slot at 0x{pos:x} is the constant 0, cannot store {value}")
                    continue
                if not 0 <= value < (1 << (8 * width)):
                    raise PsbError(f"value {value} does not fit {width} byte(s) at 0x{pos:x}")
                body[pos] = NUMBER_N0 + width
            body[pos + 1:pos + 1 + width] = value.to_bytes(width, "little")
        return bytes(body)

    # ---------------------------------------------------------------- helpers
    def iter_strings(self, node=_ROOT, path: str = "$"):
        """Yield (path, PsbString) for every string slot in the graph.

        Iterative on purpose: a `node=None` default would collide with the many
        real `null` values inside the graph and silently restart the walk from
        the root, which recurses until the stack dies.
        """
        if node is _ROOT:
            node = self.root
        stack = [(node, path)]
        while stack:
            cur, cur_path = stack.pop()
            if isinstance(cur, PsbString):
                yield cur_path, cur
            elif isinstance(cur, dict):
                for k, v in reversed(list(cur.items())):
                    stack.append((v, f"{cur_path}.{k}"))
            elif isinstance(cur, list):
                for i in range(len(cur) - 1, -1, -1):
                    stack.append((cur[i], f"{cur_path}[{i}]"))


def load(path: str) -> PsbFile:
    with open(path, "rb") as fp:
        return PsbFile(fp.read())


# --------------------------------------------------------------------------- 整图重排
# PSB 的容器体是「相对偏移 + 顺序嵌套」布局：
#   LIST    : type | offsets（相对 base 的数组） | base = 子对象 0 的起点 | 子对象按序紧排
#   OBJECTS : type | name_refs 数组 | offsets（相对 base） | base | 子对象按序紧排
# 因此「给列表加一个元素」会移动其后所有字节。`PNode` / `PsbGraph` 把整图读成可改写的树
# 再重新序列化；字段宽度按原样记录，保证「零改动 = 逐字节一致」。

_NUM_TYPES = range(NUMBER_N0, NUMBER_N8 + 1)
_STR_TYPES = range(STRING_N1, STRING_N4 + 1)
_RES_TYPES = range(RESOURCE_N1, RESOURCE_N4 + 1)
_XRES_TYPES = range(EXTRA_CHUNK_N1, EXTRA_CHUNK_N4 + 1)


class PNode:
    """重排用的节点：保留原始类型字节与字段宽度，便于零改动逐字节还原。"""

    __slots__ = ("kind", "type_byte", "value", "values", "name_refs", "children", "style")

    def __init__(self, kind: str, type_byte: int = 0, value=None, values=None,
                 name_refs=None, children=None, style=None):
        self.kind = kind
        self.type_byte = type_byte
        self.value = value
        self.values = values or []
        self.name_refs = name_refs or []
        self.children = children or []
        self.style = style or {}

    def clone(self) -> "PNode":
        return PNode(self.kind, self.type_byte, self.value, list(self.values),
                     list(self.name_refs), [c.clone() for c in self.children], dict(self.style))

    def __repr__(self):
        if self.kind in ("none", "null"):
            return "None"
        if self.kind in ("true", "false"):
            return self.kind
        if self.kind == "num":
            return f"num({self.value})"
        if self.kind in ("list", "objects"):
            return f"{self.kind}[{len(self.children)}]"
        return f"{self.kind}({self.value})"


def _parse_node(br: io.BytesIO) -> PNode:
    pos = br.tell()
    t = br.read(1)[0]
    if t == NONE:
        return PNode("none", t)
    if t == NULL:
        return PNode("null", t)
    if t == FALSE:
        return PNode("false", t)
    if t == TRUE:
        return PNode("true", t)
    if t in _NUM_TYPES:
        width = t - NUMBER_N0
        node = PNode("num", t, 0 if width == 0 else _read_le(br, width))
        node.style["width"] = width
        return node
    if t in _STR_TYPES:
        width = t - STRING_N1 + 1
        node = PNode("str", t, _read_le(br, width))
        node.style["width"] = width
        return node
    if t in _RES_TYPES:
        width = t - RESOURCE_N1 + 1
        node = PNode("res", t, _read_le(br, width))
        node.style["width"] = width
        return node
    if t in _XRES_TYPES:
        width = t - EXTRA_CHUNK_N1 + 1
        node = PNode("xres", t, _read_le(br, width))
        node.style["width"] = width
        return node
    if t == FLOAT0:
        return PNode("float0", t, 0.0)
    if t == FLOAT:
        return PNode("float", t, struct.unpack("<f", br.read(4))[0])
    if t == DOUBLE:
        return PNode("double", t, struct.unpack("<d", br.read(8))[0])
    if ARRAY_N1 <= t <= ARRAY_N8:
        br.seek(pos)
        values, cw, ew = _read_array_style(br)
        node = PNode("array", t, None, values)
        node.style.update(count_width=cw, entry_width=ew)
        return node
    if t == LIST:
        offsets, cw, ew = _read_array_style(br)
        base = br.tell()
        kids = []
        for off in offsets:
            br.seek(base + off)
            kids.append(_parse_node(br))
        br.seek(base)
        node = PNode("list", t, None, None, None, kids)
        node.style.update(count_width=cw, entry_width=ew)
        return node
    if t == OBJECTS:
        name_refs, ncw, new = _read_array_style(br)
        offsets, cw, ew = _read_array_style(br)
        base = br.tell()
        kids = []
        for off in offsets:
            br.seek(base + off)
            kids.append(_parse_node(br))
        br.seek(base)
        node = PNode("objects", t, None, None, name_refs, kids)
        node.style.update(count_width=cw, entry_width=ew,
                          name_count_width=ncw, name_entry_width=new)
        return node
    raise PsbError(f"unknown object type 0x{t:02x} at 0x{pos:x}")


def _emit_node(node: PNode) -> bytes:
    kind = node.kind
    if kind == "none":
        return bytes([NONE])
    if kind == "null":
        return bytes([NULL])
    if kind == "false":
        return bytes([FALSE])
    if kind == "true":
        return bytes([TRUE])
    if kind == "num":
        width = node.style.get("width", 0)
        if width == 0:
            return bytes([NUMBER_N0])
        return bytes([NUMBER_N0 + width]) + int(node.value).to_bytes(width, "little")
    if kind == "str":
        width = node.style.get("width", 1)
        return bytes([STRING_N1 + width - 1]) + int(node.value).to_bytes(width, "little")
    if kind == "res":
        width = node.style.get("width", 1)
        return bytes([RESOURCE_N1 + width - 1]) + int(node.value).to_bytes(width, "little")
    if kind == "xres":
        width = node.style.get("width", 1)
        return bytes([EXTRA_CHUNK_N1 + width - 1]) + int(node.value).to_bytes(width, "little")
    if kind == "float0":
        return bytes([FLOAT0])
    if kind == "float":
        return bytes([FLOAT]) + struct.pack("<f", node.value)
    if kind == "double":
        return bytes([DOUBLE]) + struct.pack("<d", node.value)
    if kind == "array":
        return _pack_array_styled(node.values, node.style.get("count_width"),
                                  node.style.get("entry_width"))
    if kind in ("list", "objects"):
        # 同一容器内**结构相同的子对象共享同一位置**（原始写出器就是这么去重的：
        # 例 scenes[0].lines[0][1].env.action 的两个子项 offsets 都是 0）。
        parts, seen, offsets, acc = [], {}, [], 0
        for child in node.children:
            blob = _emit_node(child)
            if blob in seen:
                offsets.append(seen[blob])
                continue
            seen[blob] = acc
            offsets.append(acc)
            parts.append(blob)
            acc += len(blob)
        head = bytes([LIST if kind == "list" else OBJECTS])
        if kind == "objects":
            head += _pack_array_styled(node.name_refs, node.style.get("name_count_width"),
                                       node.style.get("name_entry_width"))
        head += _pack_array_styled(offsets, node.style.get("count_width"),
                                   node.style.get("entry_width"))
        return head + b"".join(parts)
    raise PsbError(f"cannot emit node kind {kind}")


def split_path(path: str) -> list:
    """'$.scenes[0].texts[3][2]' -> ['scenes', 0, 'texts', 3, 2]"""
    parts = []
    for name, idx in re.findall(r"\.([A-Za-z_][A-Za-z0-9_]*)|\[(\d+)\]", path):
        parts.append(name if name else int(idx))
    return parts


class PsbGraph:
    """整图读写：`PsbFile.parse_graph()` 得到可改写的树，`build()` 重新拼回完整 PSB。"""

    def __init__(self, psb_file: "PsbFile"):
        self.file = psb_file
        if psb_file.chunk_offsets or psb_file.chunk_lengths:
            raise PsbError("带资源 chunk 的 PSB 暂不支持整图重排")
        br = io.BytesIO(psb_file.body)
        br.seek(psb_file.offset_entries)
        self.root = _parse_node(br)
        self.extra_strings: list[str] = []

    # ---------------------------------------------------------------- 遍历
    def walk(self, node: "PNode | None" = None, path: str = "$"):
        node = self.root if node is None else node
        yield path, node
        if node.kind == "list":
            for i, child in enumerate(node.children):
                yield from self.walk(child, f"{path}[{i}]")
        elif node.kind == "objects":
            names = self.file.node_names(node)
            for key, child in zip(names, node.children):
                yield from self.walk(child, f"{path}.{key}")

    def find(self, path: str) -> "PNode":
        node = self.root
        for part in split_path(path):
            if isinstance(part, int):
                node = node.children[part]
            else:
                node = node.children[self.file.node_names(node).index(part)]
        return node

    # -------------------------------------------------------------- 字符串
    def add_string(self, value: str) -> int:
        if value is None:
            raise PsbError("add_string(None)")
        idx = len(self.file.string_offsets) + len(self.extra_strings)
        self.extra_strings.append(value)
        return idx

    def str_node(self, value: str, width: int | None = None) -> "PNode":
        """新建一个字符串引用节点（指向追加进字符串池的新串）。"""
        idx = self.add_string(value)
        if width is None:
            width = self.file.str_ref_width()
        node = PNode("str", STRING_N1 + width - 1, idx)
        node.style["width"] = width
        return node

    # ---------------------------------------------------------------- 输出
    def build(self) -> bytes:
        f = self.file
        graph = _emit_node(self.root)
        count = len(f.string_offsets)
        data = bytearray()
        offsets = []
        for i in range(count + len(self.extra_strings)):
            offsets.append(len(data))
            if i >= count:
                data += self.extra_strings[i - count].encode("utf-8") + b"\x00"
                continue
            start = f.offset_strings_data + f.string_offsets[i]
            end = f.body.index(b"\x00", start)
            data += f.body[start:end] + b"\x00"
        offsets_blob = _pack_array_styled(offsets, f._str_count_width, f._str_entry_width)

        prefix = f.body[f.header_length:f.offset_entries]
        tail = f.body[f.offset_chunk_offsets:]
        header = bytearray(f.body[:f.header_length])
        offset_strings = f.header_length + len(prefix) + len(graph)
        offset_strings_data = offset_strings + len(offsets_blob)
        offset_chunk_offsets = offset_strings_data + len(data)
        struct.pack_into(
            "<8I", header, 8, f.header_length, f.offset_names, offset_strings,
            offset_strings_data, offset_chunk_offsets,
            offset_chunk_offsets + (f.offset_chunk_lengths - f.offset_chunk_offsets),
            offset_chunk_offsets + (f.offset_chunk_data - f.offset_chunk_offsets),
            f.offset_entries)
        checksum = zlib.adler32(bytes(header[8:40])) & 0xFFFFFFFF
        struct.pack_into("<I", header, 0x28, checksum)
        body = bytes(header) + prefix + graph + offsets_blob + bytes(data) + tail
        if f.is_mdf:
            return MDF_SIG + struct.pack("<I", len(body)) + zlib.compress(body, 9)
        return body


# ---------------------------------------------------------------- PsbFile 侧入口
def _psb_parse_graph(self):
    return PsbGraph(self)


def _psb_node_names(self, node: PNode) -> list:
    return [self.names[i] for i in node.name_refs]


def _psb_str_ref_width(self) -> int:
    """字符串引用节点的最小安全宽度（保证追加后的下标放得下）。"""
    total = len(self.string_offsets)
    width = 1
    while total >= (1 << (8 * width)):
        width += 1
    return width


PsbFile.parse_graph = _psb_parse_graph
PsbFile.node_names = _psb_node_names
PsbFile.str_ref_width = _psb_str_ref_width
