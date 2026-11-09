# 踩坑与返工教训

每条格式：规则（结论）+ 为什么（症状/依据）。

## 1. 「Hxv4」这个标签是错的，判型只看事实

初版补丁的文档把本作归档称作 Hxv4（wamsoft XChaCha20 + DRIP），实际是 **Cx 变体**：索引明文、条目名是 md5、`adlr = adler32(明文)`、条目内容走 Cx 的字节码 VM 密钥流。
症状：Hxv4 的 `hxv4.py` 在这份 `data.xp3` 上完全用不上。
⇒ 规则：`0x17` 处 `0x80` + 索引可解析 + 内容解不开 = 名字哈希加密变体，再去对 GARbro 的方案库（实现见 `tool/cx.py`）。

## 2. 别自己造密钥：参数在 GARbro 的 `Formats.dat` 里

公开方案 `CxEncryption(0x12B, 0x7AB)` 只是 mask/offset，真正要跑的是 `prolog/odd/even_branch_order` + 1024 项 `control_block`。这些都在 GARbro 的 `GameData/Formats.dat`（BinaryFormatter + deflate）里，按游戏标题索引。
⇒ 规则：用 `reflection` 从 `ArcFormats.dll` 直接取字段（`tmp/garbo_host/cxtool.cs --dump`），一次导出成 `resource/cx/profile_9nine.json`；从 exe 静态推导拿不到这套参数。

## 3. `GARbro.Console.exe` 认不出本作，但方案就在它自己的数据库里

症状：`GARbro.Console data.xp3` 报 `unknown format` —— `Xp3Opener.GuessCryptAlgorithm` 只按 `FormatCatalog.LookupGame()`（存档文件名 / 同目录 exe 名 → 游戏标题）查方案，而 `m_game_map` 里没有 `nine_kokoiro.exe`。
⇒ 规则：走反射 + 自己的解包路径（`tool/cx.py`），别在 Console 上耗时间。

## 4. C# 一次性宿主不可入库，密钥逻辑必须移植回 Python

症状：用 `csc.exe` + GARbro DLL 的宿主（`cxtool.exe --decrypt`）只能放在 `tmp/` 里、且依赖 .NET Framework，既不复跑也不可交付。
⇒ 规则：`tool/cx.py` 按语义逐条移植，等价性以 C# 宿主的输出为基准（21 个条目逐字节比对一致）。

## 5. 共享字符串槽会让「只改一处」变成改一片

症状：官方 482 行的 jp 与 cn 正文**同槽**（同一偏移），`patch_ints` 改指向会连累日文。
⇒ 规则：写操作先按「字节位置」分组判定共享，再决定跳过；本项目对 3 行无可避免的冲突保留原文，并在产物里列清单（`_skipped_shared.json`）。

## 6. 初版包的 checksum 不可当等价性基准

症状：`archive/releases/unencrypted.xp3` 里的 scn 重建过，但保留了官方原文件的旧 header checksum（`adler32`、`crc32` 都对不上任何前缀）⇒ 引擎不校验它。
⇒ 规则：零改动往返按「除 `0x28` 4 字节 checksum 外逐字节一致」判定。

## 7. 逻辑行数一致不等于可翻译位置一致：还要看控制码

症状：行数、场景标签、选择支都对得上，但民汉正文的 `\\n` 比官方日文少 498 处、ruby 少 3 处（简中重排段落）。
⇒ 规则：控制码守恒按「产物 == 民汉源」判定，与日文的差异只作提示（`script/verify_roundtrip.py` 报 508 行提示）。

## 8. 民汉源本身有缺口，缺口不是 bug

* 选择支（9 条）在民汉包里仍是**官方繁中**（初版补丁没翻选项），本项目依日文原文**就地翻译**一份写进语料（`resource/chs_text/scripts/*.selects.jsonl`，见 `doc/text-model.md` §4）；
* 民汉正文残留少量繁体字形（本语料命中 27 个），同样**直接改在语料里**，不做旁路覆盖表（见 `doc/text-model.md` §6）；
* 482 行共享槽里另有 19 行的民汉文本与官中不同但能正常替换，真正无法处理的只有 3 行。

### 8.1 语料即源：禁止旁路覆盖表

症状：给选项加一张 `_overrides.json`、由 `writeback.py` 在回写时套用，会让同一套规则在两处维护（`writeback.py` 套表、`verify_patch.py` 也得读同一张表），而且繁体字形只改了选项，正文与显示名仍在。
⇒ 规则：错的是**语料本身**就该修 —— 改语料、回写只负责拍过去；表与双份规则全部删掉。

### 8.2 别把「字体 cmap 覆盖率」当渲染结论

症状：`script/check_font_coverage.py` 读 OTF 的 cmap 能算出「TC 字体对语料 2460 个字符缺字 0、JP 缺 613」，而第 4 轨即便指向 TC 字体仍然乱码。
⇒ 规则：cmap 覆盖只说明「码位在表里」，不说明引擎真用它画、也不说明该语言变体的字形能被接受；字形问题以游戏内截图/人工确认为准，离线结果只能当线索。

### 8.3 运行期探针可以随便用，但只能在测试构建里

`System.inform` 是最可靠的运行期判据（能直接读出 `LanguageTags`、`getPlacedPath`、`kag.chDefaultFace` 之类的内部状态），测试阶段尽管用。代价是：`after-init` 里弹窗会让主窗口底部留一条白边（重启恢复），弹窗还会阻塞初始化，所以抓取脚本要即时关闭。
⇒ 边界：**发布物里不许出现探针**。`script/build_patch.py` 的 `verify()` 会对钩子做 `System.inform` / `Debug.notice` / `getPlacedPath` 检查并判失败，只有 `--allow-probe` 的测试构建才豁免。另外运行期试验前备份 `%APPDATA%\ぱれっと\nine_kokoiro`，收尾一律 `WM_CLOSE` 优雅退出，不 `Stop-Process -Force`。

### 8.4 别脚本化连点启动游戏：会撞 0xc0000142

症状：脚本反复 `Start-Process` 启动游戏（还夹着 `tasklist` 判定失误导致的重复拉起），Windows 报 `应用程序无法正常启动(0xc0000142)`（DLL 初始化失败），进程挂着不退；同一时刻 `steam.xp3`/`patch3.xp3` 的 md5 与构建产物一致。
⇒ 规则：这类错误是**运行环境/进程堆积**问题（桌面堆耗尽、单实例锁、残留实例），不是归档损坏；一次只跑一个实例，启动前先确认无残留（`tasklist | findstr nine_kokoiro`），不在循环里自动重启；玩家端遇到 0xc0000142 先杀干净进程（或重启机器）。

### 8.5 归档域别名只对归档里第一条条目生效，scn 交付必须走松散目录

症状：加了第 4 轨后，开场 `a01` 是简中，`a02` 起回日文。查法：给 patch3 里 `a02` 的**日文块**首句加 `JPMARK:` —— 游戏里看不到，说明引擎**根本没读 patch3 的 a02**；把同一批 scn 放进 `<游戏目录>/scn/`（钩子注册 `System.exePath + "scn/"`）后 `JPMARK` 与四轨简中都生效。
⇒ 规则：`patch3.xp3>scn/` 的域别名只对「开场那种裸名请求」有效；后续章节的取法不同（`getPlacedPath`：裸名 → patch3，`scn/xxx.scn` 全路径 → data.xp3），双前缀别名 `scn/scn/xxx.scn` 也无效（结构依据见 `doc/engine-mechanics.md` §3.1）。
⇒ 规则：别拿一个脚本的生效情况推断整包生效；覆盖类方案要用「在官方文件里埋标记」验证覆盖面（JPMARK 法），而不是看某一句对不对。

### 8.6 自建 xp3 的索引：`hnfn` 必须每个文件一条

官方打包器写的是「每个文件一条 `hnfn`」（hnfn 全部在前、File 在后；`data.xp3` 943/944、`adult.xp3` 925/925）。本项目早期把全部名字塞进一条 `hnfn`，引擎只认第一条，于是 `addAutoPath("patch3.xp3>scn/")` 只暴露第一个 scn，其余裸名请求全落回 `data.xp3` —— 表现像「域别名只认第一条」，实则是自己把索引写坏了。
⇒ 自建归档一律照官方结构写；判据用「换顺序看赢家」+「给目标文件埋标记看游戏内是否出现」，不要只看某个脚本是否生效。

### 8.7 字体运行期注册可以，但要把「谁实例化 PreRenderFontEx」算进时机

`PreRenderFontEx.AddTrueTypeFont` 依赖 `global.PreRenderFontEx` 与 `System.addFont`：前者在 `sysscn/PreRenderFontEx.tjs` 里只被赋成**类**，实例由游戏启动流程创建；后者在本作是现成的（`typeof System.addFont == "Object"`，不需要 `addFont.dll`）。
⇒ 在 `addAfterInitCallback` 里注册（此时两者就绪）会成功；若在实例就绪前调用、或重复 `KAGLoadScript("PreRenderFontEx.tjs")` 把实例覆盖回类，就会抛 `Cannot convert the variable type ((void) to Object)`。注册成功后别名可直接被 `kag.chDefaultFace` / `scflags["langUserFontFace3"]` 使用。

### 8.8 「更早注入」要先证明时机，不是证明路径

`patch3.xp3>main/` 在索引修好后确实能被解析到（`getPlacedPath` 返回 patch3 路径），但 `main/*.tjs` 的加载早于钩子，覆盖**无效**；把 `ConfigEx.tjs` 放进更早注册的 `steam.xp3` 则直接把引擎打到 Access Violation（空文件、两种编码都试过）。
⇒ 判据顺序应是「先证实该文件在注入点之后才被加载（埋标记看是否生效），再谈能不能放进去」；只验证路径解析会得出错误结论。

## 9. 无离线证据的路径必须真的带回退实现

症状：本项目的验收全部是离线证据，`patch.xp3` 能否被引擎直接接受（免 DLL）没有离线证明。
⇒ 规则：交付物必须**真的**带上 `version.dll` 回退路径（不是只在文档里写一句），并在 `releases/README.txt` 里写明。

## 10. 归档内**路径前缀**会丢，回读自证会掩盖它

症状：用 `os.path.relpath(file, indir)` 当归档路径、而 `--indir` 指向只含文件名的目录（`tmp/build/scn/`）时，别名退化成 `a01.txt.scn` + `md5("a01.txt.scn")`，引擎真正查找的 `md5("scn/a01.txt.scn")` 根本不存在；更糟的是回读校验复用同一个 `aliases()`，于是「三别名齐备、回读通过」变成了自证。

⇒ 硬闸（`script/build_patch.py`）：

* 归档内路径必须显式带前缀（`scn/` 域即 `scn/<名>`），别名 = `全路径 / basename / md5(全路径)` 且去重；
* 命名约定必须拿**别人的归档**核对：`md5(全路径)` 要同时存在于官方 `data.xp3` 与本补丁；
* 回读校验不能只验「我写了什么」，还要验「引擎会按什么键找」。

## 11. 注册与优先级

依据：`doc/engine-mechanics.md` §3/§4。

1. **XP3 索引必须有 `hnfn` 表**（`adlr → 真名`），否则引擎按真名找不到条目（表现为 `steam.tjs not found`）。条目名 = `md5(UTF-16LE 真名)`。
2. **`File` 内 chunk 顺序**：`time, adlr, segm, info`；加密条目 `segm.flags = 1`（zlib），`info.zsize` 同步。
3. **`.sig` 不参与引擎校验**（替换 `steam.xp3` 后游戏照常启动，`.sig` 仍是官方的）。
4. **`adult.xp3` 不是"覆盖"而是"补充"**：925 条里 924 条是 `data.xp3` 没有的新文件，唯一重叠是那个 `$$$ This is a protected archive…txt` 占位。
5. **`@if (DEBUG)` 是编译期指令**，release 版整块剔除 —— 别指望 DEBUG 分支里的脚本会加载。
6. **语言菜单/系统设置**：`main/default.tjs` 的 `multiLangFirstTag = "en"`，首次启动（或配置丢失）会回落英文；玩家手动切一次「繁體中文」后即保持，与补丁无关。
