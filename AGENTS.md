# 9-nine-:Episode 1 简中补丁

## 项目目的

为 Steam 版《9-nine-:Episode 1》（appid 976390，九次九日九重色）产出**简体中文文本替换补丁**。

文本来源：樱空汉化组 Ver1.0。

本项目把剧情正文与选项换成民汉简中。

**分阶段目标**：
1. 工程骨架与约定（已完成）
2. 提取官方/民汉脚本文本到 `resource/`（一次）
3. 逐脚本行数严格一致校验 + 末尾行语义抽查
4. 机制判定：新增第四语言轨 vs 覆盖 cn(繁) 轨（结论：覆盖）；生效通路（结论：hook 注入，见 doc/engine-mechanics.md §0）
5. 回写、打包、安装脚本
6. 验收证据与文档收尾

UI 文案（`syslangtext`、`help_*`、界面贴图）**不在本轮范围**，作为后续独立目标。

## 技术背景（结论速查）

| 项 | 结论 |
|---|---|
| 引擎 | krkrz + M2「MDF」脚本层（剧情不是 `.ks`/`.tjs`，是编译后的 PSB） |
| 剧情脚本 | `*.scn` = `PSB\0` 或 `mdf\0 + u32 + zlib(PSB v3)`；本作实测**裸 PSB 外壳**（archive 补丁里 17 个脚本头 `PSB\0`） |
| 文本模型 | 一行对白 = `[speaker_jp, speaker_alt, blocks[3], attrs, flag, commands]`；语言块 = `[显示名, 正文, plain, plain2]`；**无 `length` 字段** |
| 语言轨 | `blocks` 恒 3 个：jp / en / cn；cn 轨官方内容是**繁中**，本项目覆盖为简中并改显示名 |
| 选项 | `scenes[].selects[] = {exp, language[3]{searchtext,speechtext,text}, render, selidx, storage, target, text}`，`text` 是日文 |
| 补丁形态 | **`steam.xp3`(19 KB, hook 注入) + `patch3.xp3`(2 MB, 简中剧本)**；`patch.xp3`/`patch2.xp3` 留给第三方。见 `doc/engine-mechanics.md` §0/§3/§4 |
| 归档优先级 | `data.xp3`(exe 相对路径) > `addArchive` 系(绝对路径) ；**启动流程内手动 `addAutoPath(<相对路径> + ">scn/")` 才能覆盖** |
| Steam 归档 | `data.xp3` 等为 **XP3 的 Cx 加密变体**（`0x17` 处 `0x80`，真索引偏移在 `0x20`）：索引明文（zlib），条目名 = `md5(UTF-16LE 全路径)`，`adlr` = `adler32(明文)`，**条目内容** Cx 加密。参数在 `resource/cx/profile_9nine.json`，`tool/cx.py` 可离线加解密（不是 Hxv4！详见 `doc/lessons-learned.md` §1） |
| 民汉归档 | `archive/releases/unencrypted.xp3` **明文 xp3**（`adlr=0`），17 个 scn + 贴图 + help，每个文件登记三个别名（全路径 / basename / `md5(UTF-16LE 全路径)`） |
| 初版补丁 | 作者已归档于 `archive/`：文本 + 设置页 + 字体均已完成，用 `version.dll`（KirikiriUnencryptedArchive）+ `unencrypted.xp3`；本项目**只按需采纳**，不继承其结构 |
| 回写方式 | 只改字符串池：`PsbFile.rebuild({slot: text})`（字符串数量不变），不需要完整序列化器 |
| 归档优先级（实测） | `data.xp3`(exe 注册，相对路径) 最高；`addArchive` 系（绝对路径）压不住它；**启动流程内手动 `addAutoPath("<相对路径>scn/")` 可以**（详见 `doc/engine-mechanics.md` §3） |

细节见 `doc/`：`file-formats.md`（容器/PSB）、`text-model.md`（本文模型）、`engine-mechanics.md`
（启动链/优先级/语言轨/字体）、`lessons-learned.md`、`acceptance-criteria.md`。

> 引擎级通用结论另有一份在本机知识库 `../../../../GalRevserse/GalRev/docs/engines/krkr/`
> （配套库 `galrev/krkr/`）。`tool/` 里 xp3/psb/scn 是从该库复制的（cx 依据 GARbro 独立移植），
> 改动引擎级结论要**两边同步**；本项目专属取值只写在本仓库 `doc/`。

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

- **不修改**游戏安装目录里的原始文件（只读解析）；所有产物写到项目目录。
- 覆盖任何已产出补丁前先备份（`*.bak`）并在 `doc/` 记录原因。
- 不把游戏素材（xp3、字体以外的资源）提交进仓库。

### 6. 测试与验收

每个阶段结束前：跑该阶段校验脚本 → 抽样人工比对 → 更新文档 → 清理 `tmp/`。
验收标准见 `doc/acceptance-criteria.md`；本轮**不启动游戏实测**，以离线证据判定。

## 环境

- Python：miniforge 的 **GalRev** 环境（3.11），本项目只用这一个。执行：`mamba run -n GalRev python script/xxx.py`。
- shell 初始化不可写，mamba 每次固定打印几行 `libmamba Error opening for writing ...: Permission denied`，不影响执行；批量跑时用 `2>&1 | grep -v libmamba` 过滤。
- 依赖：全部标准库（`zlib`/`struct`/`mmap`/`hashlib`/`json`/`re`/`ctypes`）。**新增第三方库需先申请**，只在 GalRev 里装。
- 动态分析：x32dbg（附加到运行中的游戏进程，**只读内存、不下断点** —— 本作下断点即崩）。
- 静态分析：IDA Pro，脱壳文件 `nine_kokoiro.exe.unpacked.exe` 已建库（脱壳版只能用于静态分析，不能用于动态调试）。
- 游戏目录（只读）：`E:\SteamLibrary\steamapps\common\nine_kokoiro`。
- 交叉验证用 GARbro：`../../../../GalRevserse/unpack/GARbro-v1.5.44.2904`（GUI，人工导出官方 `scn/`）。

## 参考资料

- `GalRev`：krkr/MDF 引擎通用文档 + `galrev/krkr/` 库（`tool/` 的来源）。
- `YuaExtract`：Hxv4 / CxdecV2 的提取与 key 派生参考实现。
- `MashiroiroSymphonyFHD_Retranslation_Patch`：本项目的工程架构来源（目录、脚本规范、文档分工）。
