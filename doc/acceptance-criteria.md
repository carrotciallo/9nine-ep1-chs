# 验收标准与复跑记录

所有命令都从项目根执行，环境 `GalRev`（`mamba run -n GalRev python …`）。
本轮**不启动游戏**，全部以离线证据验收。

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
**结果**：17 项通过（xp3 三别名 / adlr=0 / 17 个 scn / 零改动往返 / 重建幂等 / 单串扰动 /
textset 往返 / krkr_text mode 0-2 / cx 往返）。

## 2. Cx 实现与 GARbro 逐字节一致

```powershell
mamba run -n GalRev python script/verify_cx.py
```
**结果**：5/5 黄金向量通过（scn a01/a09、startup.tjs、syslangtext_cn.ini、embfontlist.tjs）。
黄金向量取自「GARbro 的 `ICrypt.Decrypt` 输出」，当时已逐字节比对 **21/21** 条目
（17 scn + startup.tjs + syslangtext_cn.ini + help_conf_cn.txt + embfontlist.tjs），
此后回归不依赖 .NET 宿主。

## 3. 文本提取（两侧）

```powershell
mamba run -n GalRev python script/extract_text.py --from-xp3 archive/releases/unencrypted.xp3 --lang cn --out resource/chs_text
foreach ($l in "cn","jp","en") { mamba run -n GalRev python script/extract_text.py --from-dir resource/official_scn --lang $l --out "resource/official_$l" }
```
**结果**：每侧 17 个脚本、9327 行、9 条选择支；`_index.json` 记录来源/脚本名/行数/字符数。
重复运行两次 `_index.json` 哈希相同（幂等）。

## 4. 行数严格一致 + 末尾行语义抽查

```powershell
mamba run -n GalRev python script/verify_extract.py --base resource/official_jp --target resource/chs_text --out resource/verify
```
**结果**：17/17 脚本行数、场景标签、行键、选择支全部一致，问题项 **0**；
`resource/verify/endlines.json` 是每脚本末尾 3 行的对照，人工抽查记录：
17 个脚本的末行语义一一对应（如 `a16` 末行 `%p-1;%fＭＳ ゴシック;` 控制码两侧同形）。

*已知差异（非错误）*：民汉正文 `\n` 比官方日文少 498 处（简中重排段落），ruby 少 3 处。

## 5. 回写

```powershell
mamba run -n GalRev python script/writeback.py --official resource/official_scn/scn --text resource/chs_text --out tmp/build/scn
```
**结果**：9327 行 -> 正文替换 8652 行、plain 4788 槽、显示名 0 处（民汉专名与官中一致）、
共享冲突跳过 3 行；产物比官方大 2~3%（追加字符串池）。

## 6. 回写产物校验（非目标内容逐值不变）

```powershell
mamba run -n GalRev python script/verify_patch.py --official resource/official_scn/scn --text resource/chs_text --built tmp/build/scn
```
**结果**：`{"rows": 9327, "cn_text_ok": 9324, "cn_text_skip": 3, "cn_plain_ok": 2395, "cn_text_bad": 0}`，
整数槽/字符串槽结构、jp/en 全部槽位逐值未变，问题项 **0**。

## 7. 零改动往返 + 控制码守恒

```powershell
mamba run -n GalRev python script/verify_roundtrip.py --official resource/official_scn/scn --built tmp/build/scn --text resource/chs_text
```
**结果**：34 个文件（官方 17 + 产物 17）零改动往返一致（除 header checksum）且幂等；
产物控制码与民汉源差异 **0** 行；与官方日文差异 508 行（提示项，见 `lessons-learned.md` §7）。

## 8. 打包与回读（`script/build_patch.py`）

```powershell
mamba run -n GalRev python script/build_patch.py --scn-dir tmp/build/scn `
    --official-steam "E:/SteamLibrary/steamapps/common/nine_kokoiro/steam.xp3.orig" --out releases
```
**结果**：`patch3.xp3` 2,052,230 B（17 个 scn，回读逐条一致）、`steam.xp3` 19,102 B
（官方 4 条保留 + 源码钩子 + 官方原字节码 13,976 B），三项校验全过。

## 9. 交付物

| 产物 | 说明 |
|---|---|
| `releases/steam.xp3` | **hook 注入**（19 KB）：官方 4 条 + `steam_r18hack.tjs` 源码钩子 + `steam_r18hack_orig.tjs`（官方字节码） |
| `releases/patch3.xp3` | **简中剧本**（2 MB）：只装 `scn/a01..a17.txt.scn`；日常更新只换它 |
| `releases/README.txt` | 安装 / 语言 / 兼容 / 卸载说明 |

`patch.xp3` / `patch2.xp3` 留给第三方补丁（钩子已按顺序注册，互不冲突）。

## 10. 验收记录（游戏内已实测）

1. **文本替换生效**：开场第一句 `a01` scene0 row0 = 「有一部名为《轮回转生的莫比乌斯环》的动画。」✓
2. **语言**：游戏默认首语言是 `en`（`main/default.tjs` 的 `multiLangFirstTag`），首次启动需在设置里切一次「繁體中文」，之后保持 ✓
3. **R18 功能保留**：官方 `steam_r18hack.tjs` 字节码改名 `steam_r18hack_orig.tjs` 并在钩子里转发执行 ✓
4. **纯 scn 包可用**：`patch3.xp3` 不含官方条目副本，仅 17 个 scn，仍正常生效 ✓

## 11. 内存判据（x32dbg 附加运行中的游戏，用其字符串搜索功能，UTF-16 编码）

不下断点（本作断点即崩），只读内存即可判定四件事：

| 判据 | 实测数据 |
|---|---|
| 归档是否注册 | `data.xp3>` 1076 处、`adult.xp3>` 925（= adult 条目数）、`patch.xp3>` 22（= 我们包的条目数）、`steam.xp3>` 4（= steam 条目数）、`system.xp3>` 22 |
| 是否注册目录 | `system/` 281 处（`addArchive` 会注册）、`adult/` **0** 处（append 不注册目录） |
| 条目内容是否被采用 | 我们的简中文本（`有一部名为` 等）**0 处**，官方繁中（`以前有一部`）15 处 → `patch.xp3>` 的 scn 从未被打开 |
| 某代码分支是否执行 | `appendlist` **0 处**（`!appendlist.txt` 分支从未执行）、`append_setup.tjs` 1 处（仅 TJS 常量） |

结论：`patch.xp3` / `steam.xp3` / `system.xp3` 都被成功注册，但**同名文件输给 `data.xp3`**；
append 清单分支从未执行。

## 12. hook 注入验证（游戏内实测通过）

`steam.xp3`（19 KB）内把 `steam_r18hack.tjs` 换成 TJS 源码钩子（官方字节码改名保留并转发）：

1. 弹窗 `STEAM-HOOK` / `STEAM-HOOK-DONE` 出现 → 钩子被执行；
2. 正文第一句 `a01` scene0 row0 = 「有一部名为《轮回转生的莫比乌斯环》的动画。」→ `addAutoPath("steam.xp3>scn/")` 生效，**压过 `data.xp3`**；
3. 交付形态拆分为 `steam.xp3`(19 KB, hook) + `patch3.xp3`(2 MB, 数据)，日常只换 `patch3.xp3`；
4. 副作用与处理：先 `addAutoPath` 后转发时语言回落英文（`multiLangFirstTag="en"`）→ 改为**先转发、后注册**即恢复；首次启动仍需在设置里切一次「繁體中文」。

## 13. 纯追加归档的排除结论

| 名字/形态 | 结果 |
|---|---|
| `patch.xp3`（任意位置/头型/索引名/`hnfn`） | 注册成功，但被 `data.xp3` 压制（简中文本 0 处） |
| `patch2.xp3`/`patch3.xp3` 自动注册 | 源码里 `addAutoPath` 被注释 → 不注册 |
| `system.xp3`/`sysscn.xp3`/`k2compat.xp3`/`debug.xp3` | 前三个注册但优先级不足；`debug.xp3` 在编译期剔除的 debug 分支里 |
| subfolder `<name>.xp3`（`uipsd/cn` 等） | 只注册目录，不注册 xp3 |
| `append/!appendlist.txt` + `patch_append<ID>.xp3` + `append_setup*.tjs` | 均未注册（`appendlist` 0 处，`patch_append1.xp3>` 0 处） |
| 纯白式「在包里放延迟注册的 TJS」 | 唯一可选载体 `scntranstempl.tjs` 在 `@if (DEBUG)` 内，release 剔除 |
| 钩子放 `patch.xp3` 内 + `removeAutoPath` 重注册 | 钩子执行成功，但重排无效（`data.xp3` 仍先命中） |

即：**必须有一个由引擎执行的注入点**；本作可用的只有 `steam.xp3` 里的 `steam_r18hack.tjs`。
