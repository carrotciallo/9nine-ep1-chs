"""本作（9-nine-:Episode 1）MDF 脚本的文本模型。

一个 `.scn` 是 `mdf\\0 + u32 原文长度 + zlib(PSB v3)`（与《纯白交响曲 FHD》同壳），
差异在**行内布局**：本作的对白行把三种语言放在同一行里，每条语言一个「语言块」。

对白行 `scenes[].texts[i]`（实测 17 个脚本 9327 行，arity 6，1 行 arity 7）：

    [0] speaker_jp    角色原名（日文，如 "翔"），语言无关，保留不译
    [1] speaker_alt   次名槽（多为 null；75 行非 null），语义待定，不译
    [2] blocks        语言块列表，**恒为 3 个**：jp / en / cn
    [3] attrs         属性列表（[{name,pan,type,voice}] | null），无文本
    [4] flag          int（80 / 110 等），非文本
    [5] commands      引擎指令容器，无文本
    [6] （仅 1 行）    额外整数

语言块 `blocks[k]`（arity 2 或 4）：

    [0] name          该语言下的角色显示名（"コスプレイヤー" / "Cosplayer" / "角色扮演者"）
    [1] text          正文（含行内标记 `%NNN;` / `#RRGGBBAA;` / `#;`、ruby `[よみ,3]`、换行 `\\n`）
    [2] plain         正文去掉 ruby 后的形态（arity 4 才有；因为有 `\\n`、与 [1] 不同槽时占多数）
    [3] plain2        正文只保留 ruby 基字的形态（与 [2] 通常同槽；4836/4839 相同，仅 3 处不同）

选择支 `scenes[].selects[i]`（实测 9 条）：

    {exp, language, render, selidx, storage, target, text}
    text        = 日文选项文本
    language    = [null, {searchtext,speechtext,text}(en), {searchtext,speechtext,text}(cn)]

槽位共享（回写前必须判定）：

* 同一行内，cn 块的 [1]/[2]/[3] **恒为同一槽**（9327/9327）；jp 块 6883 行三槽同源、
  2441 行 [1] 与 [2][3] 分槽（ruby 形态）、3 行三槽各自独立。
* 跨语言：三语言的主文本槽**从不共享**（9327 行均为 3 个不同槽）。
* 块内 [0]（角色显示名）跨行共享（如「？？？」），替换时若与日文槽同源需先拆槽。

`length` 字段：本作**没有**（《纯白》那套页 length 在本作不存在），替换文本只改字符串池，
因此不需要重算长度，也不需要完整对象图序列化器。

写入方式：`PsbFile.rebuild({slot: new_text})`（字符串数量不变），零改动往返必须逐字节一致。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import psb

LANGS = ("jp", "en", "cn", "sc")  # 前三轨是官方；"sc" 是简中补丁新增的第 4 轨
LANG_INDEX = {name: i for i, name in enumerate(LANGS)}


def _s(node):
    return node.value if isinstance(node, psb.PsbString) else None


def _i(node):
    return node.index if isinstance(node, psb.PsbString) else None


@dataclass
class Block:
    """一条语言块：显示名 + 正文 + 若干 plain 变体。"""

    lang: str
    name: str | None
    name_idx: int | None
    text: str | None
    text_idx: int | None
    plains: list = field(default_factory=list)  # [(str, slot_idx)]

    @property
    def slots(self) -> list[tuple[int, str, str]]:
        """(槽号, 值, 角色) —— 本块的**可翻译槽**（name / text / plain）。"""
        out = []
        if self.name_idx is not None and self.name is not None:
            out.append((self.name_idx, self.name, "name"))
        if self.text_idx is not None and self.text is not None:
            out.append((self.text_idx, self.text, "text"))
        for value, idx in self.plains:
            if idx is not None and value is not None:
                out.append((idx, value, "plain"))
        return out


@dataclass
class Message:
    scene: int
    label: str
    row: int
    speaker: str | None
    speaker_alt: str | None
    flag: int
    blocks: list[Block]

    def block(self, lang: str) -> Block:
        return self.blocks[LANG_INDEX[lang]]


@dataclass
class Select:
    scene: int
    label: str
    index: int
    target: str | None
    storage: str | None
    text: str | None            # 日文
    text_idx: int | None
    langs: dict = field(default_factory=dict)  # {"en"|"cn": {"text":..,"text_idx":..,...}}


class MdfScript:
    """一个 `.scn` 的读取模型。"""

    def __init__(self, data: bytes, name: str = ""):
        self.psb = psb.PsbFile(data)
        self.raw = data
        self.name = name or self.script_name

    # ------------------------------------------------------------------ meta
    @property
    def root(self):
        return self.psb.root

    @property
    def script_name(self) -> str:
        return _s(self.psb.root.get("name")) or ""

    @property
    def script_hash(self) -> str:
        return _s(self.psb.root.get("hash")) or ""

    @property
    def scenes(self) -> list:
        return self.psb.root.get("scenes") or []

    # ------------------------------------------------------------------ text
    def iter_messages(self):
        for si, scene in enumerate(self.scenes):
            label = _s(scene.get("label")) or ""
            for ri, row in enumerate(scene.get("texts") or []):
                if not isinstance(row, list) or len(row) < 3:
                    continue
                raw_blocks = row[2] if isinstance(row[2], list) else []
                blocks = []
                for li, blk in enumerate(raw_blocks):
                    lang = LANGS[li] if li < len(LANGS) else f"lang{li}"
                    if not isinstance(blk, list):
                        continue
                    plains = []
                    for node in blk[2:]:
                        plains.append((_s(node), _i(node)))
                    blocks.append(Block(
                        lang=lang,
                        name=_s(blk[0]) if blk else None,
                        name_idx=_i(blk[0]) if blk else None,
                        text=_s(blk[1]) if len(blk) > 1 else None,
                        text_idx=_i(blk[1]) if len(blk) > 1 else None,
                        plains=plains,
                    ))
                yield Message(
                    scene=si,
                    label=label,
                    row=ri,
                    speaker=_s(row[0]),
                    speaker_alt=_s(row[1]),
                    flag=row[4] if len(row) > 4 and isinstance(row[4], int) else -1,
                    blocks=blocks,
                )

    def iter_selects(self):
        for si, scene in enumerate(self.scenes):
            label = _s(scene.get("label")) or ""
            for ci, sel in enumerate(scene.get("selects") or []):
                if not isinstance(sel, dict):
                    continue
                langs = {}
                blocks = sel.get("language")
                if isinstance(blocks, list):
                    for li, blk in enumerate(blocks):
                        if not isinstance(blk, dict):
                            continue
                        lang = LANGS[li] if li < len(LANGS) else f"lang{li}"
                        langs[lang] = {
                            key: {"text_idx": _i(blk.get(key)), "text": _s(blk.get(key))}
                            for key in ("searchtext", "speechtext", "text")
                            if blk.get(key) is not None
                        }
                yield Select(
                    scene=si,
                    label=label,
                    index=ci,
                    target=_s(sel.get("target")),
                    storage=_s(sel.get("storage")),
                    text=_s(sel.get("text")),
                    text_idx=_i(sel.get("text")),
                    langs=langs,
                )

    # ------------------------------------------------------------- slots
    def translatable(self, lang: str = "cn"):
        """该语言的 (槽号, 值, 角色, 键) 列表。

        键 = (场景序号, 行号) 表示对白行；(场景序号, "sel", 选项序号) 表示选择支。
        角色名槽跨行共享时会重复出现，去重由调用方负责。
        """
        out = []
        for msg in self.iter_messages():
            for b in msg.blocks:
                if b.lang != lang:
                    continue
                for idx, value, role in b.slots:
                    out.append((idx, value, role, (msg.scene, msg.row)))
        for sel in self.iter_selects():
            key = (sel.scene, "sel", sel.index)
            if lang == "jp":
                if sel.text_idx is not None and sel.text is not None:
                    out.append((sel.text_idx, sel.text, "select", key))
                continue
            for role, rec in (sel.langs.get(lang) or {}).items():
                if rec["text_idx"] is not None and rec["text"] is not None:
                    out.append((rec["text_idx"], rec["text"], "select:" + role, key))
        return out

    def rebuild(self, new_strings: dict[int, str]) -> bytes:
        return self.psb.rebuild(new_strings)


def load(path: str, name: str = "") -> MdfScript:
    with open(path, "rb") as fp:
        return MdfScript(fp.read(), name)
