# 验收标准与复跑方式

所有命令都从项目根执行，环境 `GalRev`（`mamba run -n GalRev python …`）。

## 0. 前置：官方文件在本地解包

```powershell
mamba run -n GalRev python script/unpack_xp3.py "E:/SteamLibrary/steamapps/common/nine_kokoiro/data.xp3" `
    --cx-profile resource/cx/profile_9nine.json --only scn/ --out resource/official_scn
```
（产物 `resource/official_scn/` 是游戏本体内容，已 gitignore，可随时重建。）

## 1. 工程自检（tool/ 全部模块）

```powershell
mamba run -n GalRev python script/selftest.py
```
**判据**：17 项全部通过（xp3 三别名 / adlr=0 / 17 个 scn / 零改动往返 / 重建幂等 / 单串扰动 / textset 往返 / krkr_text mode 0-2 / cx 往返）。依据：`script/selftest.py`。

## 2. Cx 实现与 GARbro 逐字节一致

```powershell
mamba run -n GalRev python script/verify_cx.py
```
**判据**：5/5 黄金向量通过（scn a01/a09、startup.tjs、syslangtext_cn.ini、embfontlist.tjs）。黄金向量取自 GARbro 的 `ICrypt.Decrypt` 输出，21/21 条目逐字节一致（17 scn + startup.tjs + syslangtext_cn.ini + help_conf_cn.txt + embfontlist.tjs），回归不依赖 .NET 宿主。依据：`script/verify_cx.py`。

## 3. 文本提取（两侧）

> 语料是**唯一来源**：`resource/chs_text` 与 `resource/official_{jp,en,cn}` 已入库、并经人工修订（繁体字形、显示名、选项译文，见 `doc/text-model.md` §4/§6）。本节的 `script/extract_text.py` **仅留档、不参与交付**——重跑会把语料覆盖回民汉原件/官方原件，要改文本请直接改语料。

```powershell
mamba run -n GalRev python script/extract_text.py --from-xp3 archive/releases/unencrypted.xp3 --lang cn --out resource/chs_text
foreach ($l in "cn","jp","en") { mamba run -n GalRev python script/extract_text.py --from-dir resource/official_scn --lang $l --out "resource/official_$l" }
```
**判据**：每侧 17 个脚本、9327 行、9 条选择支；`_index.json` 记录来源/脚本名/行数/字符数；重复运行 `_index.json` 哈希相同（幂等）。

> ⚠️ `resource/chs_text` **不是**民汉原件：繁体字形、显示名、选项译文经人工修订（见 `doc/text-model.md` §4/§6）；误跑 `extract_text.py --lang cn` 会把它覆盖回民汉原件，回头要 `git checkout -- resource/chs_text` 取回修订版；正常流程不需要跑它。

## 4. 行数严格一致 + 末尾行语义抽查

```powershell
mamba run -n GalRev python script/verify_extract.py --base resource/official_jp --target resource/chs_text --out resource/verify
```
**判据**：17/17 脚本行数、场景标签、行键、选择支全部一致，问题项 **0**；`resource/verify/endlines.json` 是每脚本末尾 3 行的对照，17 个脚本的末行语义一一对应（如 `a16` 末行 `%p-1;%fＭＳ ゴシック;` 控制码两侧同形）。依据：`script/verify_extract.py`、`resource/verify/endlines.json`。

*已知差异（非错误）*：民汉正文 `\n` 比官方日文少 498 处（简中重排段落），ruby 少 3 处。

## 5. 四轨产物（`script/extend_lang.py`）

```powershell
mamba run -n GalRev python script/extend_lang.py --official resource/official_scn/scn --text resource/chs_text --out tmp/build/lang4
```
**判据**：9327 行各追加第 4 块（`sc`）、9 条选择支各追加第 4 项；每行前 3 块逐值等于官方、第 4 块的 `name`/`text`/`plain` 等于语料、选择支前 3 项不变。依据：`script/extend_lang.py` 内置闸。

## 6. 四轨产物复核（`script/verify_lang4.py`）

```powershell
mamba run -n GalRev python script/verify_lang4.py --official resource/official_scn/scn --built tmp/build/lang4/scn --text resource/chs_text
```
**判据**：`{"rows": 9327, "blocks4": 9327, "selects": 9, "text_ok": 9327, "plain_ok": 2395, "name_ok": 5900}`；另含「产物幂等（再解析再序列化逐字节一致）」与「前 3 块未改动」，问题项 0 才算过。依据：`script/verify_lang4.py`。

## 7. 打包（`script/build_patch.py`）

```powershell
mamba run -n GalRev python script/build_patch.py --scn-dir tmp/build/lang4/scn `
    --official-steam（默认 resource/official_steam/steam.xp3） "E:/SteamLibrary/steamapps/common/nine_kokoiro/steam.xp3.orig" --out releases
```
**判据**：产出 `releases/patch3.xp3`（17 个四块 scn）与 `releases/steam.xp3`（官方 4 条保留 + 源码钩子 + 官方原字节码 13,976 B）；钩子里不得含 `System.inform` / `Debug.notice` / `getPlacedPath` 探针（测试构建用 `--allow-probe` 豁免）；脚本自带闸：官方条目字节不变、钩子内容正确、原字节码副本一致、patch3 回读逐条与源 scn 一致（任一不过就不写出）。索引必须每文件一条 `hnfn`（`doc/engine-mechanics.md` §3.1）。依据：`script/build_patch.py`。

## 8. 交付物

| 产物 | 说明 |
|---|---|
| `releases/steam.xp3` | **hook 注入**（约 20 KB）：官方 4 条 + `steam_r18hack.tjs` 源码钩子（注册 `patch3.xp3>scn/`、松散 `scn/`/`font/`、四轨语言表、运行期注册字体）+ `steam_r18hack_orig.tjs`（官方字节码） |
| `releases/patch3.xp3` | **简中剧本**（约 2.2 MB）：`scn/a01..a17.txt.scn` 17 个四块脚本；索引每文件一条 `hnfn`（`doc/engine-mechanics.md` §3.1） |
| `releases/font/` | **思源黑体 CN**（Bold/Medium，OFL，约 17 MB）：运行期由钩子注册成 `9nineSC-B/M`（`doc/engine-mechanics.md` §6） |

安装：把官方 `steam.xp3` 改名 `steam.xp3.orig`（备份），复制 `steam.xp3` + `patch3.xp3` 到游戏目录，`font/` 整个目录复制成 `<游戏目录>/font/`。日常更新只换 `patch3.xp3`。`patch.xp3` / `patch2.xp3` 留给第三方补丁（钩子按顺序注册，互不冲突）。

## 10. 内存判据（x32dbg 附加运行中的游戏，用其字符串搜索功能，UTF-16 编码）

不下断点（本作断点即崩），只读内存即可判定四件事：

| 判据 | 数据 |
|---|---|
| 归档是否注册 | `data.xp3>` 1076 处、`adult.xp3>` 925（= adult 条目数）、`patch.xp3>` 22（= 我们包的条目数）、`steam.xp3>` 4（= steam 条目数）、`system.xp3>` 22 |
| 是否注册目录 | `system/` 281 处（`addArchive` 会注册）、`adult/` **0** 处（append 不注册目录） |
| 条目内容是否被采用 | 我们的简中文本（`有一部名为` 等）**0 处**，官方繁中（`以前有一部`）15 处 → `patch.xp3>` 的 scn 从未被打开 |
| 某代码分支是否执行 | `appendlist` **0 处**（`!appendlist.txt` 分支从未执行）、`append_setup.tjs` 1 处（仅 TJS 常量） |

结论：`patch.xp3` / `steam.xp3` / `system.xp3` 都被成功注册，但**同名文件输给 `data.xp3`**；append 清单分支从未执行。

## 11. hook 注入判据

`steam.xp3`（19 KB）内把 `steam_r18hack.tjs` 换成 TJS 源码钩子（官方字节码改名保留并转发），判定依据三条：

1. 弹窗 `STEAM-HOOK` / `STEAM-HOOK-DONE` 出现 → 钩子被执行；
2. 正文第一句 `a01` scene0 row0 = 「有一部名为《轮回转生的莫比乌斯环》的动画。」→ `addAutoPath("steam.xp3>scn/")` 生效，**压过 `data.xp3`**；
3. 副作用与处理：先 `addAutoPath` 后转发时语言回落英文（`multiLangFirstTag="en"`）→ 改为**先转发、后注册**即恢复；首次启动仍需在设置里切一次「繁體中文」。

## 12. 纯追加归档的排除结论

| 名字/形态 | 结论 |
|---|---|
| `patch.xp3`（任意位置/头型/索引名/`hnfn`） | 注册成功，但被 `data.xp3` 压制（简中文本 0 处） |
| `patch2.xp3`/`patch3.xp3` 自动注册 | 源码里 `addAutoPath` 被注释 → 不注册 |
| `system.xp3`/`sysscn.xp3`/`k2compat.xp3`/`debug.xp3` | 前三个注册但优先级不足；`debug.xp3` 在编译期剔除的 debug 分支里 |
| subfolder `<name>.xp3`（`uipsd/cn` 等） | 只注册目录，不注册 xp3 |
| `append/!appendlist.txt` + `patch_append<ID>.xp3` + `append_setup*.tjs` | 均未注册（`appendlist` 0 处，`patch_append1.xp3>` 0 处） |
| 纯白式「在包里放延迟注册的 TJS」 | 唯一可选载体 `scntranstempl.tjs` 在 `@if (DEBUG)` 内，release 剔除 |
| 钩子放 `patch.xp3` 内 + `removeAutoPath` 重注册 | 钩子执行成功，但重排无效（`data.xp3` 仍先命中） |

即：**必须有一个由引擎执行的注入点**；本作可用的只有 `steam.xp3` 里的 `steam_r18hack.tjs`。

## 13. UI 简中闸（`script/verify_ui_sc.py`）

```powershell
mamba run -n GalRev python script/verify_ui_sc.py `
    --patch releases/patch3.xp3 --steam releases/steam.xp3
```

**判据**（任一不过即失败，期望 `问题项：0`）：

1. `patch3.xp3` 里存在 `resource/ui_sc/` 下的全部条目，且回读逐字节等于「语料按打包规则编码」
   （`main/**` 的 `.ini`/`.txt`/`.func` = TVP mode 1，其余原样）；
2. `main/syslangtext_sc.ini` 的 `!section` 结构、键序、行数与官方 `syslangtext_cn.ini` 完全一致，
   且 `textLanguageMenuItem_cn`/`subLanguageMenuItem_cn` 仍是「繁体中文」、`_sc` 是「简体中文」、`EzSaveHelpText` 里保留逗号（`ezsave.tjs` 靠逗号换行）；
3. `main/help_conf_sc.txt` 的键序与官方 `help_conf_cn.txt` 一致；
4. 译文里没有残留繁中/日文专用字（字表 `resource/verify/ui_sc_trad_chars.txt`，由 `script/gen_ui_trad_chars.py` 生成：官方繁中 UI 文本与初版简中版逐字对齐取「被换掉的字」，再减去简中正文语料 `resource/chs_text` 的白名单；命中即说明没转干净——只作线索，最终人工比对）；
5. 钩子只留「转发官方 + 槽位循环（注册 `<slot>.xp3>` 根域、加载 `<slot>_boot.tjs`）」，不含任何目录名/字体/简中逻辑；`patch3.xp3` 根目录的 `patch3_boot.tjs` 负责四条子域 + `font/` + `KAGLoadScript("sc_hook.tjs")`，`sc_hook.tjs`（归档根） 负责语言表、`LoadSysLangText(["sc"])` 与字体钩子；三者都不许带探针。

配套生成/复跑：

```powershell
mamba run -n GalRev python script/extract_ui_sc.py          # 从初版包取 20 张 pimg + 2 张 attention
mamba run -n GalRev python script/gen_ui_func.py            # conf_lang.func 覆盖（psd 行改 GetUIFile）
mamba run -n GalRev python script/make_ui_lang_caption.py   # 语言页三行标题贴图 conf_lang_sc.pimg
```

不入库的material：`resource/ui_sc/{uipsd,image}/`（民汉贴图，`extract_ui_sc.py` 重建）、`resource/official_*/`（官方解包，`unpack_xp3.py` 重建）、`resource/fonts_sc/`（字体）；入库的只有 `resource/ui_sc/{main,sc}/`、`conf_lang_labels.json` 与 `resource/verify/` 下的证据。
```


```

字体前置：`script/make_ui_lang_caption.py` 读 `resource/ui_sc/conf_lang_labels.json` 的 `font`（华康圆体 W9，第三方字体不入库）；缺字体时脚本报错退出，不会悄悄换字体。只想验证管线可用 `--font resource/fonts_sc/SourceHanSansCN-Bold.otf`（字形不是民汉那套）。渲染器会拒绝非真实字重（`FontStyle` 未被字体支持时 `exit 2`）。

语言页标题的位置/样式校验：脚本会打印实测行带，期望标题行带顶端 `1/90/179`、文字左边缘 `x=25`（与官方英文原图行带一致）；预览 PNG 写在 `tmp/ui/conf_lang_sc_preview.png`。
- 钩子/脚本解耦闸（`script/build_patch.py` + `verify_ui_sc.py` 内置）：钩子只允许「转发官方 + 注册子域 + `KAGLoadScript("sc_hook.tjs")`」；
  一旦 `LoadSysLangText` / `drawTextKinsokuRect` / `AddTrueTypeFont` 出现在钩子里即判失败（这类逻辑属于 `patch3.xp3` 的 `sc_hook.tjs`（归档根））。
