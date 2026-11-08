# 容器与格式

本作（9-nine-:Episode 1，appid 976390）用到的三种格式。结论均为实测，工具实现见 `tool/`。

## 1. `data.xp3`：XP3 的 **Cx 加密变体**

```
00: 58 50 33 0d 0a 20 0a 1a 8b 67 01 | 17 00 00 00 00 00 00 00   <- XP3 签名 + 「伪」索引偏移 0x17
0x13: 00 00 00 01 | 00 00 00 80 | ...
0x17: 80                            <- Cx 变体标记
0x20: 68 38 b4 22 00 00 00 00        <- **真索引偏移**（u64）
```

* 索引本身是明文 chunk 树，`dir_offset` 处首字节 `1` 表示 zlib 压缩的索引。
* 条目名 = `md5(UTF-16LE 全路径)` 的十六进制（如 `scn/a01.txt.scn` →
  `269c14bc5e2bf313d1e646e5d5be25e5`）；`startup.tjs` 是唯一用真名的条目。
* `adlr` 哈希 = **`adler32(明文内容)`**：既是完整性校验，也是 Cx 的密钥（实测
  `a09` 明文 adler32 = `0xbea696eb` = 索引里的 `adlr`）。
* **条目内容**是 Cx 加密（`info.flags` 带 `0x80000000`）；索引、条目名不加密。
* 段（`segm`）可能先 zlib 压缩再加密 —— 解密要作用在**解压后**的流上，且偏移按解压后的位置累计。

### 1.1 Cx 参数（每作一组）

公开方案标作 `CxEncryption(0x12B, 0x7AB)`，与本地实测一致：

| 项 | 值 |
|---|---|
| `mask` / `offset` | `0x12B` / `0x7AB`（`base_offset = (hash & mask) + offset`，越过它密钥换成 `(hash>>16)^hash`） |
| `prolog_order` | `[0, 2, 1]` |
| `odd_branch_order` / `even_branch_order` | 6 / 8 项（见 `resource/cx/profile_9nine.json`） |
| `control_block` | 1024 × u32（GARbro 的「 Encryption control block」表，取反后参与运算） |

来源：GARbro 的 `GameData/Formats.dat`（`GameRes.Formats.KiriKiri.CxEncryption`），
字段经反射导出成 `resource/cx/profile_9nine.json`；`tool/cx.py` 是 GARbro
`ArcFormats/KiriKiri/KiriKiriCx.cs` 的**逐语义移植**（Cx 程序生成 + 字节码 VM + 三层密钥）。

**验证**：对 `data.xp3` 里 21 个条目（17 个 scn + `startup.tjs` + `syslangtext_cn.ini` +
`help_conf_cn.txt` + `embfontlist.tjs`），`tool/cx.py` 的输出与 GARbro 的 `ICrypt.Decrypt`
**逐字节一致**（21/21）。加解密同一算式（XOR），因此同一实现也用来**写**补丁包。

### 1.2 明文包（`archive/releases/unencrypted.xp3`）

初版补丁作者的包是普通 XP3：`adlr=0`（不加密标记），索引未压缩，同一内容登记三别名
（全路径 / basename / `md5(UTF-16LE 全路径)`）。这种包引擎读不了，必须配
`version.dll`（KirikiriUnencryptedArchive）—— 这也是本项目改用 Cx 加密包的原因。

## 2. `.scn`：裸 PSB v3

本作的剧情脚本**没有** `mdf\0 + zlib` 外壳，直接是 `PSB\0`（版本 3，header_encrypt=0）。
`tool/psb.py` 按 FreeMote 公开规格解析；`tool/mdf.py` 给出本作的文本模型（见 `text-model.md`）。

PSB 头 `0x28` 处 4 字节是 checksum。**注意**：初版补丁包里的 scn 由作者的工具重建过，
却沿用了官方原文件的旧 checksum（`adler32`/`crc32` 都对不上任何前缀），说明**引擎不校验**
该字段；本项目重建时由 `tool/psb.py` 重新计算。

## 3. TVP 加扰文本（`main/*.tjs`、`syslangtext`、`help`）

部分文件以 `FE FE | mode | FF FE | 正文(UTF-16LE)` 存放，mode 1 对每个 uint16 做奇偶位交换
（对合）。`tool/krkr_text.py` 支持 mode 0/1/2 的 decode/encode/往返校验。

实测 `data.xp3` 里的分布：

| 文件 | 形态 | 说明 |
|---|---|---|
| `main/default.tjs`、`main/config.tjs`、`main/custom.tjs`、`main/storages.tjs`、`appconfig.tjs`、`font/embfontlist.tjs` | 加扰文本（mode 1） | **TJS 源码**，可直接读改 |
| `startup.tjs`、`system/initialize.tjs`、`system/conductor.tjs`、`system/mainwindow.tjs` | `TJS2` 编译字节码 | 只读（字符串表仍可提取） |
| `main/syslangtext_cn.ini`、`main/help_conf_cn.txt` | 加扰文本 / 明文 | UI 文案（本轮范围外） |

## 3.5 本项目补丁包的头部（与官方同构）

`script/build_patch.py` 写出的 `releases/patch3.xp3` / `releases/steam.xp3` 头部与官方 `data.xp3` 完全同构：
`0x0B` 处 u64=0x17（伪索引偏移）、`0x17` 处 u32=0x80（变体标记）、`0x1B` 5 字节填充、
`0x20` 处 u64=真索引偏移、内容区从 `0x28` 开始；索引 zlib 压缩（首字节 `1`）。
回退包 `releases/unencrypted.xp3` 则是标准 XP3 头（`0x0B` 直接是索引偏移）、`adlr=0`、不加密。

## 4. 名字反查

官方索引名是哈希，要按路径取文件就必须先算出 md5。已确认可用的候选名登记在
`resource/name_candidates.txt`；`script/unpack_xp3.py --only scn/` 会连同内置候选一起尝试。
