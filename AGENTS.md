# 9-nine-:Episode 1 简中补丁

## 项目目的

为 Steam 版《9-nine-:Episode 1》（appid 976390，九次九日九重色）产出**简体中文文本替换补丁**。

文本来源：樱空汉化组 Ver1.0。

本项目把剧情正文与选项换成民汉简中。

**分阶段目标**：
1. 工程骨架与约定
2. 提取官方/民汉脚本文本到 `resource/`（一次）
3. 逐脚本行数严格一致校验 + 末尾行语义抽查
4. 机制判定：语言轨方案（新增第 4 轨 `sc`，官方 jp/en/cn 原样保留）与生效通路（hook 注入，见 `doc/engine-mechanics.md` §0）
5. 回写、打包、安装步骤（安装 = 复制交付物进游戏目录，不提供安装脚本）
6. 验收证据与文档收尾

UI 文案（`syslangtext`、`help_*`、界面贴图）**不在补丁范围**，作为后续独立目标。

## 技术背景（结论速查）

| 项 | 结论 |
|---|---|
| 引擎 | krkrz + M2「MDF」脚本层（剧情不是 `.ks`/`.tjs`，是编译后的 PSB） |
| 剧情脚本 | `*.scn` = `PSB\0` 或 `mdf\0 + u32 + zlib(PSB v3)`；本作为**裸 PSB 外壳**（archive 补丁里 17 个脚本头 `PSB\0`） |
| 文本模型 | 一行对白 = `[speaker_jp, speaker_alt, blocks, attrs, flag, commands]`；语言块 = `[显示名, 正文, plain, plain2]`；**无 `length` 字段**；官方 scn 的 `blocks` 恒 3 个（jp/en/cn），产物为 4 个 |
| 语言轨 | 官方 3 轨 jp / en / cn（cn=繁中）原样保留；本项目**新增第 4 轨 `sc`（简中）**，`blocks` 按 `multiLangLanguageTags` 的序号取块（`GetScnConvertLangList()` 返回 `en,cn,sc`）。第 4 块由 `script/extend_lang.py` 追加（PSB 整图重排），语言表由钩子在运行时注入（`SystemConfig.multiLangLanguageTags.add("sc")` + `LanguageTags.add("sc")` + `multiLangParamsMap["sc"]` 的菜单 caption） |
| 选项 | `scenes[].selects[] = {exp, language[4]{searchtext,speechtext,text}, render, selidx, storage, target, text}`（第 4 项 = `sc`），`text` 是日文；语料里 9 条选项依日文原文**就地翻译**（无旁路覆盖表），产物作为第 4 项 `sc` 追加，前 3 项（jp/en/cn）原样保留 |
| 补丁形态 | **`steam.xp3`(20 KB, hook 注入) + `patch3.xp3`(2.2 MB, 17 个四块 scn) + 松散 `font/`(思源黑体 CN Bold/Medium, 运行期注册)**；多文件归档可用，但索引必须**每文件一条 `hnfn`**。见 `doc/engine-mechanics.md` §3.1/§5/§6 |
| 注册形态 | 引擎脚本里只有三种：整包根域 `addAutoPath("name>")`、松散目录 `addAutoPath(System.exePath + "dir/")`、子域 `addAutoPath("name>dir/")`。整包根域只匹配**全路径**请求，而 scn 是**裸名**请求；子域别名只对 exe 注册过的 `data.xp3` 正常，对我们后加的 patch 归档退化（四种写法都试过，见 `doc/engine-mechanics.md` §3.1）。**scn 交付必须走松散目录** |
| Steam 归档 | `data.xp3` 等为 **XP3 的 Cx 加密变体**（`0x17` 处 `0x80`，真索引偏移在 `0x20`）：索引明文（zlib），条目名 = `md5(UTF-16LE 全路径)`，`adlr` = `adler32(明文)`，**条目内容** Cx 加密。参数在 `resource/cx/profile_9nine.json`，`tool/cx.py` 可离线加解密（不是 Hxv4！详见 `doc/lessons-learned.md` §1） |
| 民汉归档 | `archive/releases/unencrypted.xp3` **明文 xp3**（`adlr=0`），17 个 scn + 贴图 + help，每个文件登记三个别名（全路径 / basename / `md5(UTF-16LE 全路径)`） |
| 初版补丁 | `archive/` 存有作者初版补丁：文本 + 设置页 + 字体，用 `version.dll`（KirikiriUnencryptedArchive）+ `unencrypted.xp3`；本项目**只按需采纳**，不继承其结构 |
| 回写方式 | 两步：`script/writeback.py` 只改字符串池（`PsbFile.rebuild({slot: text})`，字符串数量不变）；`script/extend_lang.py` 用 `tool/psb.PsbGraph` 整图重排（`parse_graph()` → `build()`）追加第 4 块，零改动重建逐字节一致 |

细节见 `doc/`：`file-formats.md`（容器/PSB）、`text-model.md`（本文模型）、`engine-mechanics.md`（启动链/优先级/语言轨/字体）、`lessons-learned.md`、`acceptance-criteria.md`。

> 引擎级通用结论另有一份在本机知识库 `../../../../GalRevserse/GalRev/docs/engines/krkr/`（配套库 `galrev/krkr/`）。`tool/` 里 xp3/psb/scn 是从该库复制的（cx 依据 GARbro 独立移植），改动引擎级结论要**两边同步**；本项目专属取值只写在本仓库 `doc/`。

## 工程约定

### 1. 文档同步要求

任何结论性修改都必须落到 `doc/`，不要只留在对话里：

| 改动 | 必须更新 |
|---|---|
| 容器/加密/PSB 细节 | `doc/file-formats.md` |
| 脚本文本模型、可翻译范围 | `doc/text-model.md` |
| 引擎行为、合法归档名、优先级、hook 注入、SOP、内存判据、字体 | `doc/engine-mechanics.md` |
| 踩坑与返工教训 | `doc/lessons-learned.md` |
| 验收标准与复跑方式 | `doc/acceptance-criteria.md` |

文档只写**当前成立的最新结论**，每条结论必须带验证依据（可复跑的命令或文件指针）。

### 2. 目录与脚本组织

```
tool/        长期复用的库（xp3 / cx / psb / scn / mdf / textset / krkr_text）
script/      项目流程脚本（提取、校验、回写、打包），从项目根执行
resource/    可复用的数据产物（文本集、清单、Cx 参数 profile）
doc/         知识文档
tmp/         临时文件，任务结束即清理（不入库）
releases/    交付物
```

- `tool/` 是 **Python 包**（`__init__.py`），脚本用 `from tool import psb, mdf, xp3`。
- 一次性脚本、调试输出、解包出来的原始资源、一次性任务 prompt / 工作清单一律放 `tmp/`，任务结束删除；需要保留的中间结果移入 `resource/`。
- 所有脚本用相对于项目根的路径；从项目根执行。
- 文本集一律一脚本一文件：`resource/<set>/scripts/<script>.jsonl`（读写统一走 `tool/textset.py`）。

### 3. 脚本开发规范

- **幂等**：重复运行不得产生不同结果，运行前先判断「已满足则跳过」。
- **语料即源**：译文、字形、专名的修正一律**直接改 `resource/<set>/` 语料**；禁止建旁路覆盖表（如 `_overrides.json`），避免回写与校验两处各维护一份规则。
- **回读校验**：任何写操作（重建 `.scn`、打包 xp3）之后必须重新解析产物并断言与预期一致。
- **零改动等价**：改写工具必须支持「不改任何内容」的往返重建；PSB body 除 header checksum（`0x28`，4 B）外逐字节一致。
- **报错优先**：不认识的结构、长度不符、校验失败，一律抛异常并给出文件名+偏移，禁止静默跳过。
- **槽位共享先判定**：本作同一行内 cn 块的三槽通常同源、块内显示名跨行共享；替换前先确认目标槽没有被别的语言/行引用。

### 4. 编码约定

- PSB 字符串池是 **UTF-8**，中文直接写入，无需转换。
- 脚本名/资源名在 xp3 索引里是 **UTF-16LE**，在 PSB `name` 字段里是 UTF-8，不要混用。
- 行内标记必须原样保留：`%NNN;`（语音/角色标记）、`#RRGGBBAA;` / `#;`（颜色）、`[よみ,3]`（ruby）、`\\n`（换行）。
- 控制台输出：`sys.stdout.reconfigure(encoding="utf-8")` 或保持 ASCII。

### 5. 安全与备份

- **原生归档只读，唯一例外是 `steam.xp3`**。
- 只读、绝不修改：`data.xp3` / `evimage.xp3` / `fgimage.xp3` / `voice.xp3` / `video.xp3` / `adult.xp3` 及所有 `*.sig`（也不做「只改索引 + 尾部追加」式重写）。
- `steam.xp3` **允许替换**：它是本作唯一「会被启动流程执行且我们能改」的 hook 注入点（`steam.tjs` 用 `KAGLoadScript` 加载 `steam_r18hack.tjs`），替换后交付 19 KB 的 `releases/steam.xp3`（官方 4 条原样 + 源码钩子 + 官方字节码 `steam_r18hack_orig.tjs`）。
- 替换 `steam.xp3` **前**必须把官方原件备份为 `steam.xp3.orig`；`.sig` 引擎不校验，不需要同步。理由见 `doc/engine-mechanics.md` §0/§4 与 `doc/lessons-learned.md` §11。
- `patch3.xp3` 是本项目自己的产物，修改它不算修改原生文件；scn 交付走松散 `scn/`（见「技术背景」表的「补丁形态」行）。
- 所有构建产物先写到项目目录（`tmp/build` → `releases/`），再按安装步骤复制进游戏目录。
- 覆盖任何已产出补丁前先备份（`*.bak`）并在 `doc/` 记录原因。
- 不把游戏素材（xp3、字体以外的资源）提交进仓库。

### 6. 测试与验收

每个阶段结束前：跑该阶段校验脚本 → 抽样人工比对 → 更新文档 → 清理 `tmp/`。
验收标准见 `doc/acceptance-criteria.md`；判定 = 离线闸（行数 / 槽位 / 往返 / 回读）+ 游戏内确认。

## 环境

- Python：miniforge 的 **GalRev** 环境（3.11），本项目只用这一个。执行：`mamba run -n GalRev python script/xxx.py`。
- shell 初始化不可写，mamba 每次固定打印几行 `libmamba Error opening for writing ...: Permission denied`，不影响执行；批量跑时用 `2>&1 | grep -v libmamba` 过滤。
- 依赖：全部标准库（`zlib`/`struct`/`mmap`/`hashlib`/`json`/`re`/`ctypes`）。**新增第三方库需先申请**，只在 GalRev 里装。
- 动态分析：x32dbg（附加到运行中的游戏进程，**只读内存、不下断点** —— 本作下断点即崩）。
- 静态分析：IDA Pro 打开脱壳文件 `nine_kokoiro.exe.unpacked.exe`（脱壳版只能用于静态分析，不能用于动态调试）。
- 游戏目录（原生归档只读，**例外 `steam.xp3`**，见 §5）：`E:\SteamLibrary\steamapps\common\nine_kokoiro`。
- 交叉验证用 GARbro：`../../../../GalRevserse/unpack/GARbro-v1.5.44.2904`（GUI，人工导出官方 `scn/`）。

## 参考资料

- `GalRev`：krkr/MDF 引擎通用文档 + `galrev/krkr/` 库（`tool/` 的来源）。
- `YuaExtract`：Hxv4 / CxdecV2 的提取与 key 派生参考实现。
- `MashiroiroSymphonyFHD_Retranslation_Patch`：本项目的工程架构来源（目录、脚本规范、文档分工）。
