# 脚本文本模型

一个 `.scn` 的根对象是 `{hash, name, outlines, scenes}`。文本都在 `scenes[]` 里。

## 1. 对白行 `scenes[].texts[i]`

17 个脚本共 **9327 行**，arity 恒为 6（1 行为 7）。依据：`resource/official_scn/scn` 的 17 个脚本经 `tool/mdf.py`（`MdfScript.iter_messages()`）逐行解析，行数合计与 `resource/official_jp/_index.json` 的 `messages` 合计 9327 一致。

```
[0] speaker_jp     角色原名（日文），语言无关，保留不译
[1] speaker_alt    次名槽（多为 null），不译
[2] blocks         语言块列表，官方的**恒为 3 个**：jp / en / cn；补丁产物为 4 个（见 §7）
[3] attrs          属性（[{name,pan,type,voice}] | null），语音文件在这里，不是行内标记
[4] flag           整数（80 / 110 …）
[5] commands       引擎指令容器（bg/bgm/face/…），无文本
```

## 2. 语言块 `blocks[k]`

```
[0] name      该语言下的角色显示名（コスプレイヤー / Cosplayer / 角色扮演者），可为 null
[1] text      正文：含 ruby `[よみ,3]`、换行 `\\n`、控制码 `%p-1;` / `%f...;` / `#;`
[2] plain     正文去 ruby、去 `\\n` 的变体（仅 arity 4 的块有）
[3] plain2    与 [2] 同槽（官方 4836/4839 相同，3 处不同）
```

官方脚本的 `blocks` 长度恒为 3；按 cn 块的 arity 分：6932 行为 2（只有名+正文）、2395 行为 4。依据：`resource/official_scn/scn`（`scenes[].texts[i][2]` 是 `blocks`，取 `blocks[2]` 的子项数）。

**本作没有 `length` 字段**（与《纯白交响曲 FHD》的页 length 不同），换文本只改字符串池，不需要重算长度，也就不需要完整对象图序列化器。

## 3. 槽位共享（回写必须处理）

| 现象 | 计数 | 影响 |
|---|---|---|
| 跨语言主文本槽互不相同 | 8845 / 9327 | 常规情形：追加新串 + 改指向即可 |
| **jp 与 cn 的正文槽同槽** | 482 / 9327 | 该行 jp/cn 本就是同一份文本（官方未译的短句）；其中 460 行的民汉文本与官中相同，无需改动 |
| 同一块内三槽同源（cn） | 6932（arity 2 的块天然只有一个串） | 一次替换即可 |
| 块内 `[2]`/`[3]` 同槽 | 4836 / 4839 | 同时指向新 plain |
| 显示名槽跨行共享 | 常见 | 只在值真的不同时才改；765 行需改（5 种显示名，民汉源是繁中字形，见 §6） |

同槽 = PSB 里**同一个偏移数组元素**（解析后两个路径指向同一字节位置）。这类位置无法只改一处指向，必须重建父列表（需要偏移加宽/重算，等价于完整序列化器）。这条限制只约束「覆盖 cn 轨」的三轨回写路径：该路径对这类行**保留官方原文**，影响 3 行（`a01` scene0 row62、`a05` scene0 row62、`a13` scene0 row156）；四轨路径（§7）不动官方三块、只追加新块，不受此限。依据：`script/writeback.py` 的 `conflicted` 判定与 `skipped_shared` 记录（写到产物目录的 `_skipped_shared.json`）—— 同一字节位置被非 cn 路径引用即跳过，`script/verify_patch.py` 以 `cn_text_skip` 复核这些行；未被共享的槽走「追加新串 + 就地改指向」（`script/writeback.py` 模块 docstring）。

## 4. 选择支 `scenes[].selects[i]`

```
{exp, language, render, selidx, storage, target, text}
text       = 日文选项文本
language   = [null, {searchtext,speechtext,text}(en), {searchtext,speechtext,text}(cn)]
```

全作共 9 条。依据：`resource/official_jp/_index.json` 的 `selects` 合计 9。**cn 轨的选项文本在民汉源里就是官方繁中**（民汉初版补丁未翻选项），本项目依日文原文**就地翻译一份简中，直接写进语料**（`resource/chs_text/scripts/*.selects.jsonl` 的 `text`/`searchtext`/`speechtext` 三字段同值）；回写只是照语料取值，**不存在旁路覆盖表**。产物侧 27 个槽（9 条 × text/searchtext/speechtext）逐值校验，依据：`script/verify_patch.py` 的 `select_slots` 统计。

| 脚本 | 索引 | 日文原文 | 简中译文 |
|---|---|---|---|
| `a01` | 0 | フォローする。 | 过去帮忙解围。 |
| `a01` | 1 | 余計なお節介はしない。 | 不多管闲事。 |
| `a02` | 0 | じゃあ校門集合で。 | 那就在校门口集合。 |
| `a02` | 1 | 送った方がいいか？ | 要我送你回去吗？ |
| `a04` | 0 | 素早く伏せる。 | 迅速趴下。 |
| `a04` | 1 | 九條を庇う。 | 替九条挡下。 |
| `a06` | 0 | 手を振り払う。 | 甩开她的手。 |
| `a06` | 1 | 身を委ねる。 | 顺从她的摆布。 |
| `a10` | 0 | はじめからやり直す。 | 从头再来。 |

## 5. 可翻译范围（本项目取值）

| 范围 | 处理 |
|---|---|
| `blocks[2][1]` 正文 | 换成民汉简中 |
| `blocks[2][2..]` plain | 由新正文推导：去 ruby、去 `\\n` |
| `blocks[2][0]` 显示名 | 民汉值不同才换，并做繁->简字形归一（765 行 / 5 种） |
| `blocks[0]`/`blocks[1]`（jp/en） | **不动**（逐值校验） |
| `speaker_jp`、`attrs`、`flag`、`commands`、`exp` | **不动** |
| 选择支 | 新增第 4 项（`sc`），前 3 项（jp/en/cn）原样保留 |

## 6. 语料字形归一（民汉残留）

民汉正文大体是简中，但残留少量繁体字形，一律**直接改在语料里**（`resource/chs_text/scripts/*.jsonl`），不做旁路覆盖：正文 8 行 + 词级 `执著`->`执着` 1 行 + 显示名 5 种（`与一` / `苏菲堤雅` / `春风` / `希亚` / `发狂的男学生`，共 765 行）。

判定方法（可复跑）：用 Windows 自带的 `Microsoft.VisualBasic.Strings.StrConv(…, SimplifiedChinese)` 逐字转换，转换结果与自身不同的字即繁体字形候选；本语料命中 27 字：`亞來別動嗎圍妳學幫從條現發結聽與著蘇話護過門開閒間頭風`。其中 `著` 在简体里合法（`原著`），只做词级替换。

> `script/extract_text.py` 是**一次性**步骤：重跑 `--lang cn` 会把语料覆盖回民汉原件，须 `git checkout -- resource/chs_text` 取回修订版再回写。

## 7. 四轨方案

官方三轨 jp/en/cn 全部保留，**新增第 4 轨 `sc`**：每行 `blocks` 从 3 个扩到 4 个（第 4 个是简中块，结构照抄 cn 块的 arity），每个选择支 `language` 追加第 4 项。工具链：

* `tool/psb.PsbGraph`：整图重排（`parse_graph()` → `PNode` → `build()`），17 个官方 scn 零改动**逐字节一致**；
* `script/extend_lang.py`：在官方 scn 上追加第 4 块 + 第 4 项，自带三道闸（幂等 / 前 3 块逐值不变 / 第 4 块等于语料）；
* `script/verify_lang4.py`：产物侧独立复核（`问题项 0` 才算过）。

第 4 轨在引擎里的定位：`LanguageTags` 追加 `sc`（索引 3），引擎按 `multiLangLanguageTags` 的序号取块（`GetScnConvertLangList()` 由引擎调用，返回 `en,cn,sc`）。字体固定在 `kag.chDefaultFace`（见 `engine-mechanics.md` §6）。
