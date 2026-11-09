"""KiriKiri「Cx」加密层（CxEncryption）：按 GalGbro 的 CxScheme 参数做逐字节加/解密。

本作（9-nine-:Episode 1）的 `data.xp3` 是 Cx 变体：
XP3 头 `0x17` 处是 `0x80`，真索引偏移在 `0x20`；索引明文（zlib），**条目内容**加密：
每条按 `adlr` 哈希生成字节密钥流，`Encrypt` 与 `Decrypt` 同一算式（XOR）。

参数（每作一组，参考实现见 `docs/engines/krkr/` 与 GARbro `ArcFormats/KiriKiri/KiriKiriCx.cs`）：

    mask / offset          —— 决定 base_offset = (hash & mask) + offset，
                              越过 base_offset 后密钥换成 (hash >> 16) ^ hash
    prolog_order[3]        —— 程序生成期「入口指令」三选一的分支顺序
    odd_branch_order[6]    —— 奇分支的六种运算顺序
    even_branch_order[8]   —— 偶分支的八种运算顺序
    control_block[1024]    —— 「 Encryption control block」表（取反后参与运算）

本模块是 GARbro C# 实现的**逐语义移植**，用 `resource/cx/profile_9nine.json`
（由 `cxtool.exe --dump` 从 GARbro 的 `GameData/Formats.dat` 反射导出）注入参数。
一条测试闸：对同一段密文，本模块与 GARbro 的 `ICrypt.Decrypt` 必须逐字节一致
（见 `script/verify_cx.py`）。
"""

from __future__ import annotations

import json

M32 = 0xFFFFFFFF

# CxByteCode（低 8 位是操作码，0x100 是「下一条是立即数」标记）
NOP = 0
RETN = 1
MOV_EDI_ARG = 2
PUSH_EBX = 3
POP_EBX = 4
PUSH_ECX = 5
POP_ECX = 6
MOV_EAX_EBX = 7
MOV_EBX_EAX = 8
MOV_ECX_EBX = 9
MOV_EAX_CONTROL_BLOCK = 10
MOV_EAX_EDI = 11
MOV_EAX_INDIRECT = 12
ADD_EAX_EBX = 13
SUB_EAX_EBX = 14
IMUL_EAX_EBX = 15
AND_ECX_0F = 16
SHR_EBX_1 = 17
SHL_EAX_1 = 18
SHR_EAX_CL = 19
SHL_EAX_CL = 20
OR_EAX_EBX = 21
NOT_EAX = 22
NEG_EAX = 23
DEC_EAX = 24
INC_EAX = 25

IMMED = 0x100
MOV_EAX_IMMED = 0x100 + 1
AND_EBX_IMMED = 0x100 + 2
AND_EAX_IMMED = 0x100 + 3
XOR_EAX_IMMED = 0x100 + 4
ADD_EAX_IMMED = 0x100 + 5
SUB_EAX_IMMED = 0x100 + 6

LENGTH_LIMIT = 0x80


class CxProgramError(Exception):
    pass


class CxProgram:
    """一份「加密程序」：由种子生成字节码，再对 hash 求值得到密钥三元组。"""

    def __init__(self, seed: int, control_block: list[int]):
        self.seed = seed & M32
        self.control_block = control_block
        self.code: list[int] = []
        self.length = 0

    # ------------------------------------------------------------- emit
    def clear(self) -> None:
        self.length = 0
        self.code.clear()

    def emit_nop(self, count: int) -> bool:
        if self.length + count > LENGTH_LIMIT:
            return False
        self.length += count
        return True

    def emit(self, code: int, length: int = 1) -> bool:
        if self.length + length > LENGTH_LIMIT:
            return False
        self.length += length
        self.code.append(code)
        return True

    def emit_uint32(self, value: int) -> bool:
        if self.length + 4 > LENGTH_LIMIT:
            return False
        self.length += 4
        self.code.append(value & M32)
        return True

    def get_random(self) -> int:
        seed = self.seed
        self.seed = (1103515245 * seed + 12345) & M32
        return (self.seed ^ ((seed << 16) & M32) ^ (seed >> 16)) & M32

    def emit_random(self) -> bool:
        return self.emit_uint32(self.get_random())

    # ---------------------------------------------------------- execute
    def execute(self, arg: int) -> int:
        eax = ebx = ecx = edi = 0
        stack: list[int] = []
        code = self.code
        i = 0
        n = len(code)
        while i < n:
            bytecode = code[i]
            i += 1
            immed = 0
            if bytecode & IMMED == IMMED:
                if i >= n:
                    raise CxProgramError("incomplete IMMED bytecode")
                immed = code[i]
                i += 1
            if bytecode == NOP or bytecode == IMMED:
                pass
            elif bytecode == MOV_EDI_ARG:
                edi = arg & M32
            elif bytecode == PUSH_EBX:
                stack.append(ebx)
            elif bytecode == POP_EBX:
                ebx = stack.pop()
            elif bytecode == PUSH_ECX:
                stack.append(ecx)
            elif bytecode == POP_ECX:
                ecx = stack.pop()
            elif bytecode == MOV_EBX_EAX:
                ebx = eax
            elif bytecode == MOV_EAX_EDI:
                eax = edi
            elif bytecode == MOV_ECX_EBX:
                ecx = ebx
            elif bytecode == MOV_EAX_EBX:
                eax = ebx
            elif bytecode == AND_ECX_0F:
                ecx &= 0x0F
            elif bytecode == SHR_EBX_1:
                ebx >>= 1
            elif bytecode == SHL_EAX_1:
                eax = (eax << 1) & M32
            elif bytecode == SHR_EAX_CL:
                eax = (eax >> (ecx & 0xFF)) & M32
            elif bytecode == SHL_EAX_CL:
                eax = (eax << (ecx & 0xFF)) & M32
            elif bytecode == OR_EAX_EBX:
                eax = (eax | ebx) & M32
            elif bytecode == NOT_EAX:
                eax = (~eax) & M32
            elif bytecode == NEG_EAX:
                eax = (-eax) & M32
            elif bytecode == DEC_EAX:
                eax = (eax - 1) & M32
            elif bytecode == INC_EAX:
                eax = (eax + 1) & M32
            elif bytecode == ADD_EAX_EBX:
                eax = (eax + ebx) & M32
            elif bytecode == SUB_EAX_EBX:
                eax = (eax - ebx) & M32
            elif bytecode == IMUL_EAX_EBX:
                eax = (eax * ebx) & M32
            elif bytecode == ADD_EAX_IMMED:
                eax = (eax + immed) & M32
            elif bytecode == SUB_EAX_IMMED:
                eax = (eax - immed) & M32
            elif bytecode == AND_EBX_IMMED:
                ebx &= immed
            elif bytecode == AND_EAX_IMMED:
                eax &= immed
            elif bytecode == XOR_EAX_IMMED:
                eax = (eax ^ immed) & M32
            elif bytecode == MOV_EAX_IMMED:
                eax = immed
            elif bytecode == MOV_EAX_INDIRECT:
                if eax >= len(self.control_block):
                    raise CxProgramError("index out of bounds in CxEncryption program")
                eax = (~self.control_block[eax]) & M32
            elif bytecode == RETN:
                if stack:
                    raise CxProgramError("imbalanced stack in CxEncryption program")
                return eax
            else:
                raise CxProgramError(f"invalid bytecode {bytecode:#x}")
        raise CxProgramError("CxEncryption program without RETN bytecode")


class CxCrypt:
    """一份 Cx 方案：可以加密也可以解密（同一算式）。"""

    def __init__(self, mask: int, offset: int, prolog_order: list[int],
                 odd_branch_order: list[int], even_branch_order: list[int],
                 control_block: list[int]):
        self.mask = mask & M32
        self.offset = offset & M32
        self.prolog_order = list(prolog_order)
        self.odd_branch_order = list(odd_branch_order)
        self.even_branch_order = list(even_branch_order)
        self.control_block = list(control_block)
        self._programs: dict[int, CxProgram] = {}

    @classmethod
    def load(cls, path: str) -> "CxCrypt":
        with open(path, encoding="utf-8") as fp:
            prof = json.load(fp)
        return cls(
            mask=prof["mask"],
            offset=prof["offset"],
            prolog_order=prof["prolog_order"],
            odd_branch_order=prof["odd_branch_order"],
            even_branch_order=prof["even_branch_order"],
            control_block=prof["control_block"],
        )

    # ------------------------------------------------------- byte layer
    def _tweak(self, buf: bytearray, pos: int, count: int, offset: int,
               ret1: int, ret2: int) -> None:
        key1 = ret2 >> 16
        key2 = ret2 & 0xFFFF
        key3 = ret1 & 0xFF
        if key1 == key2:
            key2 = (key2 + 1) & M32
        if key3 == 0:
            key3 = 1
        if offset <= key2 < offset + count:
            buf[pos + key2 - offset] ^= (ret1 >> 16) & 0xFF
        if offset <= key1 < offset + count:
            buf[pos + key1 - offset] ^= (ret1 >> 8) & 0xFF
        for i in range(count):
            buf[pos + i] ^= key3

    def _execute(self, key: int) -> tuple[int, int]:
        seed = key & 0x7F
        program = self._programs.get(seed)
        if program is None:
            program = self._generate_program(seed)
            self._programs[seed] = program
        src = key >> 7
        return program.execute(src), program.execute((~src) & M32)

    # -------------------------------------------------------- public
    def crypt(self, entry_hash: int, data: bytes) -> bytes:
        """对整条内容加/解密（offset 从 0 起，与引擎的流式解密等价）。"""
        buf = bytearray(data)
        key = entry_hash & M32
        base_offset = (key & self.mask) + self.offset
        if base_offset > 0:
            head = min(base_offset, len(buf))
            self._tweak(buf, 0, head, 0, *self._execute(key))
            if head == len(buf):
                return bytes(buf)
            pos, offset = head, head
            key = ((key >> 16) ^ key) & M32
        else:
            pos, offset = 0, 0
        left = len(buf) - pos
        if left:
            self._tweak(buf, pos, left, offset, *self._execute(key))
        return bytes(buf)

    # ------------------------------------------------- program builder
    def _generate_program(self, seed: int) -> CxProgram:
        program = CxProgram(seed, self.control_block)
        for stage in (5, 4, 3, 2, 1):
            if self._emit_code(program, stage):
                return program
            program.clear()
        raise CxProgramError(f"overly large CxEncryption bytecode (seed {seed})")

    def _emit_code(self, p: CxProgram, stage: int) -> bool:
        return (p.emit_nop(5)
                and p.emit(MOV_EDI_ARG, 4)
                and self._emit_body(p, stage)
                and p.emit_nop(5)
                and p.emit(RETN))

    def _emit_body(self, p: CxProgram, stage: int) -> bool:
        if stage == 1:
            return self._emit_prolog(p)
        if not p.emit(PUSH_EBX):
            return False
        if p.get_random() & 1:
            if not self._emit_body(p, stage - 1):
                return False
        elif not self._emit_body2(p, stage - 1):
            return False
        if not p.emit(MOV_EBX_EAX, 2):
            return False
        if p.get_random() & 1:
            if not self._emit_body(p, stage - 1):
                return False
        elif not self._emit_body2(p, stage - 1):
            return False
        return self._emit_odd_branch(p) and p.emit(POP_EBX)

    def _emit_body2(self, p: CxProgram, stage: int) -> bool:
        if stage == 1:
            return self._emit_prolog(p)
        if p.get_random() & 1:
            rc = self._emit_body(p, stage - 1)
        else:
            rc = self._emit_body2(p, stage - 1)
        return rc and self._emit_even_branch(p)

    def _emit_prolog(self, p: CxProgram) -> bool:
        order = self.prolog_order[p.get_random() % 3]
        if order == 2:
            return (p.emit_nop(5)
                    and p.emit(MOV_EAX_IMMED, 2)
                    and p.emit_uint32(p.get_random() & 0x3FF)
                    and p.emit(MOV_EAX_INDIRECT, 0))
        if order == 1:
            return p.emit(MOV_EAX_EDI, 2)
        if order == 0:
            return p.emit(MOV_EAX_IMMED) and p.emit_random()
        return True

    def _emit_even_branch(self, p: CxProgram) -> bool:
        order = self.even_branch_order[p.get_random() & 7]
        if order == 0:
            return p.emit(NOT_EAX, 2)
        if order == 1:
            return p.emit(DEC_EAX)
        if order == 2:
            return p.emit(NEG_EAX, 2)
        if order == 3:
            return p.emit(INC_EAX)
        if order == 4:
            return (p.emit_nop(5)
                    and p.emit(AND_EAX_IMMED)
                    and p.emit_uint32(0x3FF)
                    and p.emit(MOV_EAX_INDIRECT, 3))
        if order == 5:
            return (p.emit(PUSH_EBX)
                    and p.emit(MOV_EBX_EAX, 2)
                    and p.emit(AND_EBX_IMMED, 2)
                    and p.emit_uint32(0xAAAAAAAA)
                    and p.emit(AND_EAX_IMMED)
                    and p.emit_uint32(0x55555555)
                    and p.emit(SHR_EBX_1, 2)
                    and p.emit(SHL_EAX_1, 2)
                    and p.emit(OR_EAX_EBX, 2)
                    and p.emit(POP_EBX))
        if order == 6:
            return p.emit(XOR_EAX_IMMED) and p.emit_random()
        if order == 7:
            rc = p.emit(ADD_EAX_IMMED) if p.get_random() & 1 else p.emit(SUB_EAX_IMMED)
            return rc and p.emit_random()
        return True

    def _emit_odd_branch(self, p: CxProgram) -> bool:
        order = self.odd_branch_order[p.get_random() % 6]
        if order == 0:
            return (p.emit(PUSH_ECX)
                    and p.emit(MOV_ECX_EBX, 2)
                    and p.emit(AND_ECX_0F, 3)
                    and p.emit(SHR_EAX_CL, 2)
                    and p.emit(POP_ECX))
        if order == 1:
            return (p.emit(PUSH_ECX)
                    and p.emit(MOV_ECX_EBX, 2)
                    and p.emit(AND_ECX_0F, 3)
                    and p.emit(SHL_EAX_CL, 2)
                    and p.emit(POP_ECX))
        if order == 2:
            return p.emit(ADD_EAX_EBX, 2)
        if order == 3:
            return p.emit(NEG_EAX, 2) and p.emit(ADD_EAX_EBX, 2)
        if order == 4:
            return p.emit(IMUL_EAX_EBX, 3)
        if order == 5:
            return p.emit(SUB_EAX_EBX, 2)
        return True
