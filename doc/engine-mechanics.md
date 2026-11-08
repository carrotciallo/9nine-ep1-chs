# 引擎机制与补丁形态（实测结论）

格式见 `file-formats.md`，文本模型见 `text-model.md`；本文 §0 是「补丁生效 SOP」（通用决策流程）。
本文只写**本项目实测成立**的结论；每条都可用文中命令/内存判据复跑。

## 0. 补丁生效 SOP（决策树）

**先找「引擎会自己注册的合法归档名」，再在合法名里找「同名冲突时优先级最高」的那个；两者都不满足时，才用「高优先级归档做 TJS hook 注入」，最后才考虑 DLL 注入。**

### ① 枚举合法名 —— 最优先事项

合法名的来源**只有三处**，逐个查：

| 来源 | 查法 | 本作实测结果 |
|---|---|---|
| **exe 硬编码** | 搜脱壳 exe 的字符串/反编译初始化代码 | `data.xp3`（唯一，加 `-forcedataxp3` 参数） |
| **启动脚本（TJS）** | 解包 `main/storages.tjs`、`system/initialize.tjs`（可能是字节码，用第 5 节的 TJS2 反汇编） | `steam.xp3`、`system.xp3`、`sysscn.xp3`、`k2compat.xp3`（`addTools = addArchive`）、`patch.xp3`（`initialize.tjs` 第 325 行无条件）、`debug.xp3`（debug 分支） |
| **配置项** | 搜 `AppendDataConfig`、`subfolders`、`addArchive("...")` | append：`patch_append0 => adult`（只认配置项）；subfolders 只注册**目录**，不注册 xp3 |

**验证「名字是否合法」的判据（不要用文本是否替换成功当判据）**：

- 首选：**内存判据**（第 4 节）—— 注册成功时进程内存里会出现 `<name>.xp3>`，数量 ≈ 该归档条目数；
- 兜底：放一个**含弹窗的 TJS**（`main/default.tjs` 之类晚期加载的脚本），看是否有 `System.inform`。**不要用正文判断**，正文同时受「注册」和「优先级」两个变量影响。

**本作被排除的名字**（真放过、真重启过、内存确认未注册）：

`patch.xp3`(25 行注册成功但优先级低) / `patch2` `patch3`（源码里 `addAutoPath` 被注释）/ `uipsd/cn.xp3`、`uipsd/en.xp3`、`scenario/staffroll.xp3`（subfolder 只注册目录）/ `debug.xp3`（debug 分支，`debugWindowEnabled` 是编译期常量，release 恒 false）/ `unencrypted.xp3`（需 DLL）

### ② 测优先级

同名文件冲突时谁赢，**必须实测**（引擎版本的 autopath 排序不可假设）。判据同样用内存：

- 搜「你的包内独有文本」是否进内存 —— 进了说明你的条目被打开；没进说明被对手包先命中。
- 本作结论：**`data.xp3`（exe 相对路径注册，最早）> `addArchive` 系（绝对路径注册）**；
  而**在启动流程内用相对路径 `addAutoPath` 注册的路径，能赢过 `data.xp3`**。
  这就是为什么 `steam.xp3>scn/` 生效、而 `patch.xp3>`（绝对路径）不生效。

### ③ 借高优先级归档做 hook 注入（推荐的最终形态）

前提：找到一个**会被引擎执行**的 TJS 载体。三种载体来源：

| 载体 | 条件 | 本作 |
|---|---|---|
| `data.xp3` 内某脚本 | 要改原生归档 | ✗（用户不允许） |
| **官方补丁/附加归档内的脚本** | 该归档内的脚本会被 `KAGLoadScript` | ✓ `steam.xp3` 的 `steam_r18hack.tjs`（由 `steam.tjs` 加载） |
| 「data 里不存在、但会被可选加载」的脚本 | `KAGLoadScriptIfExists` 之类 | ✗ 唯一候选 `scntranstempl.tjs` 在 `@if (DEBUG)` 里，release 被剔除 |

**钩子写法要点**（本作亲测有效）：

```tjs
// 1) 先执行官方原逻辑（保持执行环境一致，避免影响语言/配置）
Scripts.execStorage("<官方脚本名>_orig.tjs");   // 官方字节码原样改名保留
// 2) 再注册自己的搜索路径（相对路径！绝对路径会输给 data.xp3）
Storages.addAutoPath("patch.xp3>scn/");          // 留给第三方补丁
Storages.addAutoPath("patch2.xp3>scn/");
Storages.addAutoPath("patch3.xp3>scn/");         // 我们自己的数据归档
Storages.addAutoPath(System.exePath + "scn/");   // 松散目录，热更新
// 3) 子域限定（只影响 scn/，风险最小）
```

- **注册顺序 = 优先级**：后注册的优先。所以把别人的兼容名放前面、自己的放后面。
- **只注册子域**（`xxx.xp3>scn/`），不要注册归档根（`xxx.xp3>`），否则会插手所有裸名解析（配置、字体、素材）。
- 替换官方字节码脚本时，**必须把原字节码原样改名保留并在钩子里转发**，否则会丢官方功能。

### ④ 无合法名可用

1. hook 注入：同 ③，但注入点必须由外部提供（本作就是这种情况的变体：合法名存在但优先级都不够）。
2. DLL 注入：hook `TVPCreateStream`，把 `<exePath><任意>.xp3>内部路径` 直接打开（KirikiriTools / KrkrPatch / KrkrExtract 都是这个思路）。代价：多一个 DLL、可能触发杀软误报。

## 0.1 内存判据（本作最有价值的方法论）

游戏运行时用 x32dbg 附加到进程，用其字符串搜索功能（**UTF-16** 编码），**不下断点**（本作下断点即崩）：

| 搜什么 | 说明什么 |
|---|---|
| `<name>.xp3>` | 注册成功；命中数 ≈ 该归档条目数（`data.xp3>` 1076、`adult.xp3>` 925、`patch.xp3>` 22 = 我们包的 22 条） |
| `<name>/`（目录形式） | 该归档是否**同时**注册了松散目录（`addArchive` 会，append 不会：`adult/` = 0 处） |
| 包内独有文本 | 条目是否真正被打开（我们的简中文本 0 处 = 从未被读） |
| `System.inform` 文案 | hook 是否被执行 |
| `!appendlist.txt` 之类 | 某条代码分支是否被执行 |

这套判据把「注册」「优先级」「内容可读性」「分支是否执行」四个变量彻底分开，比"看文本变没变"可靠得多。

## 1. 启动链（源码 + 字节码双证据）

```
nine_kokoiro.exe（加壳；脱壳版仅供 IDA 静态分析）
 └─ 根域 startup.tjs（TJS2 字节码）→ Scripts.execStorage("system/initialize.tjs")
 └─ system/initialize.tjs（字节码，3271 words 的 global）
      ├─ exe 已注册 data.xp3（硬编码，脱壳 exe 内含 "data.xp3"/"forcedataxp3"）
      ├─ var addTools = addArchive
      │    if (kirikiriz) addTools("k2compat")     → k2compat.xp3
      │    addTools("system")                      → system.xp3
      │    addTools("sysscn")                      → sysscn.xp3
      ├─ setupSubFolders([...])                     → 只注册**目录**，不注册 xp3
      ├─ Scripts.execStorage("Storages.tjs")        → main/storages.tjs（TJS 源码）
      │     └─ addArchive("steam")                  → steam.xp3
      │        AppendDataConfig = %[ "patch_append0" => "adult" ]
      │        KAGLoadScript("append_init.tjs")      → append 机制
      ├─ useArchiveIfExists("patch.xp3")             → **无条件**（325 行）
      ├─ for (i=2...) 检查 patch2/patch3… 是否存在    → 源码里 addAutoPath **被注释**
      └─ if (debugWindowEnabled) { … useArchiveIfExists("debug") … }   ← 编译期常量，release 恒 false
 └─ main/default.tjs（1113 行）→ main/custom.tjs
      └─ switch(System.getArgument("-steam")) case "yes":
             KAGLoadScript("steam.tjs")             → steam.xp3 里的 steam.tjs
                 └─ if (isExistentStorage("steam_r18hack.tjs")) KAGLoadScript("steam_r18hack.tjs")
      └─ SetupAppendData()                          → append 机制（清单分支实测未执行）
```

关键点：

* **`@if (DEBUG)` 是编译期指令**，release 版整块剔除 —— `scntranstempl.tjs` 之类的 DEBUG-only 载体不可用。
* `addArchive(name)` = `Storages.addAutoPath(name + "/")` + `useArchiveIfExists(name)`；
  `useArchiveIfExists(name)` 里 `arcname = System.exePath + name + ".xp3"`（**绝对路径**）。
* 本作字节码里**没有 `arcPath`**（0 次），只有 `exePath`（1 次）→ 旧版模板。
* `.sig` **不参与引擎校验**：替换 `steam.xp3` 后游戏照常启动，`.sig` 仍是官方那份。

## 2. 合法归档名（引擎会注册的名字）

| 名字 | 来源 | 实测 |
|---|---|---|
| `data.xp3` | exe 硬编码 | 注册（`data.xp3>` 内存 1076 处） |
| `steam.xp3` | `addArchive("steam")` | 注册（4 处，= 4 条目） |
| `system.xp3` / `sysscn.xp3` / `k2compat.xp3` | `addTools(...)` | 放上即注册（22 处 = 22 条目） |
| `patch.xp3` | `useArchiveIfExists("patch.xp3")`（325 行） | 放上即注册（22 处） |
| `debug.xp3` | debug 分支 | **不注册**（release 恒 false） |
| `patch2.xp3` / `patch3.xp3` | 源码里 `addAutoPath` 被注释 | **不自动注册**（需 hook 手动注册） |
| `uipsd/cn.xp3`、`scenario/staffroll.xp3` … | `setupSubFolders` | **不注册 xp3**（只注册目录） |
| `unencrypted.xp3` | 无（需 `version.dll`） | 需 DLL |
| append 包（`adult.xp3`） | `AppendDataConfig` 配置项 | 注册（925 处），但**只认配置里登记的项** |

## 3. 优先级实测（关键结论）

同名文件冲突时谁赢，实测结论是**分组 + 注册时机**决定的：

| 注册方式 | 例子 | 对 `data.xp3` 同名的覆盖能力 |
|---|---|---|
| exe 硬编码（相对路径，最早） | `data.xp3>` | 最高（其它都输给它） |
| `addAutoPath(<绝对路径> + ">")`（`addArchive` 系） | `patch.xp3>`、`steam.xp3>`、`system.xp3>` | **输**（我们的简中文本在内存 0 处，官方繁中 15 处） |
| `addAutoPath(<相对路径> + ">scn/")`（启动流程内手动注册） | `steam.xp3>scn/` | **赢** ✓ |

即：**"后注册优先"只在同为相对路径的注册之间成立**；`addArchive` 注册的绝对路径整体劣于 `data.xp3` 的相对路径。这就是 `patch.xp3` 明明注册成功却压不住官方文本的原因。

> 这也解释了 13 轮实测里「注册成功但正文不变」的全部现象；`addAutoPath` 的**重排无效**（`removeAutoPath` + 重新注册也压不过 `data.xp3`）。

## 4. 本作采用的补丁形态：hook 注入

唯一稳定可控的注入点：`steam_r18hack.tjs`（由 `steam.tjs` 的 `KAGLoadScript` 触发，启动流程内必然执行；实测替换为 TJS 源码后弹窗成功）。

`steam.xp3`（19 KB）内容：

| 条目 | 处理 |
|---|---|
| `steam.tjs` / `achievement.ini` / 警告文本 | 官方原样 |
| `steam_r18hack.tjs` | 替换为 TJS 源码钩子 |
| `steam_r18hack_orig.tjs` | 官方字节码原样（13976 B，逐字节校验一致） |

钩子内容（顺序很重要）：

```tjs
Scripts.execStorage("steam_r18hack_orig.tjs");   // 先跑官方原逻辑，执行环境与官方一致
Storages.addAutoPath("patch.xp3>scn/");          // 留给第三方补丁
Storages.addAutoPath("patch2.xp3>scn/");         // 留给第三方补丁
Storages.addAutoPath("patch3.xp3>scn/");         // 我们自己的数据归档
Storages.addAutoPath(System.exePath + "scn/");   // 松散目录，热更新
```

要点：

* **先转发、后注册**。先 `addAutoPath` 再转发曾导致语言回落英文（`multiLangFirstTag="en"`）。
* **只注册子域** `xxx.xp3>scn/`，不注册归档根，避免插手所有裸名解析。
* 注册顺序 = 优先级（后注册优先），所以自己的路径放在兼容名之后。
* `patch3.xp3` 用**官方 `steam.xp3` 索引 + 追加**的形态（已验证可读），不用纯自建索引。

## 5. 语言轨：不新增第四条

`main/default.tjs`（TJS 源码）：

```tjs
.multiLangLanguageTags = [ "jp", "en", "cn" ];
.multiLangFirstTag     = "en";
.multiLangParamsMap    = %[ en: %[...], cn: %[ "menu_caption" => "&Traditional Chinese" ] ];
```

* 每条对白的 `blocks` **恒为 3 个**（jp/en/cn），新增第四条需要给 9327 行各插一个列表元素（等价于完整 PSB 序列化器）→ 判定高风险，**采用覆盖 cn 轨**。
* `multiLangFirstTag = "en"`：首次启动（或配置丢失）会回落**英文**，玩家切一次「繁體中文」后保持 —— 与补丁无关。

## 6. 字体

本轮未处理：换简中正文后沿用官方 cn 轨的字体映射，游戏内显示正常（未换字体）。

## 7. 安装 / 卸载

* 安装：把官方 `steam.xp3` 改名为 `steam.xp3.orig`（备份），再把 `releases/steam.xp3` + `releases/patch3.xp3` 复制进游戏目录。
* 日常更新：只替换 `patch3.xp3`。
* 卸载：删 `patch3.xp3`，把 `steam.xp3.orig` 改名回 `steam.xp3`。
* 不替换 `nine_kokoiro.exe` / `steam_api.dll`，成就与云存档不受影响。
