# 踩坑与返工教训

## 1. 「Hxv4」这个标签是错的，别照搬别作结论

初版补丁的文档把本作归档称作 Hxv4（wamsoft XChaCha20 + DRIP）。实测本作是 **Cx 变体**：
索引明文、条目名是 md5、`adlr = adler32(明文)`、条目内容走 Cx 的字节码 VM 密钥流。
Hxv4 的 `hxv4.py` 在这份 `data.xp3` 上完全用不上。
⇒ 判型只看事实：`0x17` 处 `0x80` + 索引可解析 + 内容解不开 = 名字哈希加密变体，再去对 GARbro 的方案库。

## 2. 别自己造密钥：参数在 GARbro 的 `Formats.dat` 里

公开方案 `CxEncryption(0x12B, 0x7AB)` 只是 mask/offset，真正要跑的是
`prolog/odd/even_branch_order` + 1024 项 `control_block`。这些都在 GARbro 的
`GameData/Formats.dat`（BinaryFormatter + deflate）里，按游戏标题索引。
⇒ 用 `reflection` 从 `ArcFormats.dll` 直接取字段（`tmp/garbo_host/cxtool.cs --dump`），
一次导出成 `resource/cx/profile_9nine.json`；不要试图从 exe 静态推导。

## 3. `GARbro.Console.exe` 认不出本作，但方案就在它自己的数据库里

`GARbro.Console data.xp3` 报 `unknown format`：`Xp3Opener.GuessCryptAlgorithm` 只按
`FormatCatalog.LookupGame()`（存档文件名 / 同目录 exe 名 → 游戏标题）查方案，而
`m_game_map` 里没有 `nine_kokoiro.exe`。所以走反射 + 自己的解包路径，别在 Console 上耗时间。

## 4. C# 一次性宿主不可入库，必须移植回 Python

先用 `csc.exe` + GARbro DLL 做了宿主（`cxtool.exe --decrypt`），它只在 `tmp/` 里、且依赖
.NET Framework。真正可复跑的是 `tool/cx.py`（逐语义移植）：拿 C# 的输出当基准，
21 个条目逐字节比对通过后才删掉对宿主的依赖。

## 5. 共享字符串槽会让「只改一处」变成改一片

官方 482 行的 jp 与 cn 正文**同槽**（同一偏移），`patch_ints` 改指向会连累日文。
写操作必须先按「字节位置」分组判定共享，再决定跳过。本项目对 3 行无可避免的冲突保留原文，
并在产物里列清单（`_skipped_shared.json`）。

## 6. 初版包的 checksum 是陈旧的，别拿它当等价性基准

`archive/releases/unencrypted.xp3` 里的 scn 重建过，但保留了官方原文件的旧 header checksum
（`adler32`、`crc32` 都对不上任何前缀）⇒ 引擎不校验它；零改动往返要按
「除 `0x28` 4 字节 checksum 外逐字节一致」判定。

## 7. 逻辑行数一致不等于可翻译位置一致：还要看控制码

行数、场景标签、选择支都对得上，但民汉正文的 `\\n` 比官方日文少 498 处、ruby 少 3 处
（简中重排段落）。所以控制码守恒只能按「产物 == 民汉源」判定，
与日文的差异只作提示（`script/verify_roundtrip.py` 会报 508 行提示）。

## 8. 民汉源本身有缺口，别把缺口当 bug

* 选择支（9 条）在民汉包里仍是**官方繁中**（初版补丁没翻选项）；
* 482 行共享槽里另有 19 行的民汉文本与官中不同但能正常替换，真正无法处理的只有 3 行。

## 9. 文档要写明「未实测」的部分

本项目的验收全部是离线证据。`patch.xp3` 能否被引擎直接接受（免 DLL）**没有**离线证明，
交付物必须**真的**带上 `version.dll` 回退路径（不是只在文档里写一句），并在
`releases/README.txt` 里写明。

## 10. 归档内**路径前缀**丢过两次，回读自证掩盖了它

第一版打包脚本（`pack_patch.py`，现已合并进 `build_patch.py`）用 `os.path.relpath(file, indir)` 当归档路径，而 `--indir` 指向的是
`tmp/build/scn/`（只含文件名）⇒ 别名退化成 `a01.txt.scn` 两次 + `md5("a01.txt.scn")`，
**引擎真正查找的 `md5("scn/a01.txt.scn")` 根本不存在**。更糟的是回读校验复用了同一个
`aliases()`，于是「三别名齐备、回读通过」变成了自证。

教训（已固化成硬闸）：

* 归档内路径必须显式带前缀（`--prefix scn`），别名 = `全路径 / basename / md5(全路径)` 且去重；
* 命名约定必须拿**别人的归档**核对：`md5(全路径)` 要同时存在于官方 `data.xp3` 与本补丁；
* 回读校验不能只验「我写了什么」，还要验「引擎会按什么键找」。

## 11. 注册与优先级（本次实测，2026-11）

1. **XP3 索引必须有 `hnfn` 表**（`adlr → 真名`），否则引擎按真名找不到条目（表现为 `steam.tjs not found`）。条目名 = `md5(UTF-16LE 真名)`。
2. **`File` 内 chunk 顺序**：`time, adlr, segm, info`；加密条目 `segm.flags = 1`（zlib），`info.zsize` 同步。
3. **`.sig` 不参与引擎校验**（替换 `steam.xp3` 后游戏照常启动，`.sig` 仍是官方的）。
4. **`adult.xp3` 不是"覆盖"而是"补充"**：925 条里 924 条是 `data.xp3` 没有的新文件，唯一重叠是那个 `$$$ This is a protected archive…txt` 占位。
5. **`@if (DEBUG)` 是编译期指令**，release 版整块剔除 —— 别指望 DEBUG 分支里的脚本会加载。
6. **语言菜单/系统设置**：`main/default.tjs` 的 `multiLangFirstTag = "en"`，首次启动（或配置丢失）会回落英文；玩家手动切一次「繁體中文」后即保持，与补丁无关。
