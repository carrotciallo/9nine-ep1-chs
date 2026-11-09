# 引擎机制与补丁形态

格式见 `file-formats.md`，文本模型见 `text-model.md`；本文 §0 是「补丁生效 SOP」（通用决策流程）。本文只写当前**成立**的结论；每条都可用文中命令/内存判据复跑。

## 0. 补丁生效 SOP（决策树）

**先找「引擎会自己注册的合法归档名」，再在合法名里找「同名冲突时优先级最高」的那个；两者都不满足时，才用「高优先级归档做 TJS hook 注入」，最后才考虑 DLL 注入。**

### ① 枚举合法名 —— 最优先事项

合法名的来源**只有三处**，逐个查：

| 来源 | 查法 | 本作结论 |
|---|---|---|
| **exe 硬编码** | 搜脱壳 exe 的字符串/反编译初始化代码 | `data.xp3`（唯一，加 `-forcedataxp3` 参数） |
| **启动脚本（TJS）** | 解包 `main/storages.tjs`、`system/initialize.tjs`（可能是字节码，用 §5.5.1 的 TJS2 反汇编） | `steam.xp3`、`system.xp3`、`sysscn.xp3`、`k2compat.xp3`（`addTools = addArchive`）、`patch.xp3`（`initialize.tjs` 第 325 行无条件）、`debug.xp3`（debug 分支） |
| **配置项** | 搜 `AppendDataConfig`、`subfolders`、`addArchive("...")` | append：`patch_append0 => adult`（只认配置项）；subfolders 只注册**目录**，不注册 xp3 |

**验证「名字是否合法」的判据（不要用文本是否替换成功当判据）**：

- 首选：**内存判据**（§0.1）—— 注册成功时进程内存里会出现 `<name>.xp3>`，数量 ≈ 该归档条目数；
- 兜底：放一个**含弹窗的 TJS**（`main/default.tjs` 之类晚期加载的脚本），看是否有 `System.inform`。**不要用正文判断**，正文同时受「注册」和「优先级」两个变量影响。

**本作被排除的名字**（内存确认未注册）：

`patch.xp3`(25 行注册成功但优先级低) / `patch2` `patch3`（源码里 `addAutoPath` 被注释）/ `uipsd/cn.xp3`、`uipsd/en.xp3`、`scenario/staffroll.xp3`（subfolder 只注册目录）/ `debug.xp3`（debug 分支，`debugWindowEnabled` 是编译期常量，release 恒 false）/ `unencrypted.xp3`（需 DLL）

### ② 测优先级

同名文件冲突时谁赢，**必须实测**（引擎版本的 autopath 排序不可假设）。判据同样用内存：

- 搜「你的包内独有文本」是否进内存 —— 进了说明你的条目被打开；没进说明被对手包先命中。
- 本作结论：**`data.xp3`（exe 相对路径注册，最早）> `addArchive` 系（绝对路径注册）**；**在启动流程内注册的路径能赢过 `data.xp3`**。归档子域能否覆盖多个同名文件取决于索引是否「每文件一条 `hnfn`」（§3.1）；写对了 `addAutoPath("patch3.xp3>scn/")` 就能全覆盖。

### ③ 借高优先级归档做 hook 注入（推荐的最终形态）

前提：找到一个**会被引擎执行**的 TJS 载体。三种载体来源：

| 载体 | 条件 | 本作 |
|---|---|---|
| `data.xp3` 内某脚本 | 要改原生归档 | ✗（用户不允许） |
| **官方补丁/附加归档内的脚本** | 该归档内的脚本会被 `KAGLoadScript` | ✓ `steam.xp3` 的 `steam_r18hack.tjs`（由 `steam.tjs` 加载） |
| 「data 里不存在、但会被可选加载」的脚本 | `KAGLoadScriptIfExists` 之类 | ✗ 唯一候选 `scntranstempl.tjs` 在 `@if (DEBUG)` 里，release 被剔除 |

**钩子写法要点**（落地见 §4）：

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

### 0.2 调试通道：探针只进测试构建，不进发布物

运行期判据默认用 `System.inform` 弹窗，弹出后**由人工截图/读文字**再手动关掉（不再有自动点击脚本：模拟鼠标/按键驱动游戏不可靠，实测出现过把 Config 点成 End Game 的情况，见 `lessons-learned.md` §16）。**测试构建允许任意探针**（`System.inform` / `Debug.notice` / `Storages.getPlacedPath` 输出），做法是临时改 `script/build_patch.py::HOOK_LINES` 后构建到临时目录，例如：

```powershell
mamba run -n GalRev python script/build_patch.py --scn-dir tmp/build/lang4/scn `
    --official-steam "E:/SteamLibrary/steamapps/common/nine_kokoiro/steam.xp3.orig" --out tmp/build/probe_test --allow-probe
```

发布闸：`build_patch.py` 的 `verify()` 会检查产物钩子里是否含 `System.inform` / `Debug.notice` / `getPlacedPath`，命中即判失败；只有显式 `--allow-probe` 才豁免（同时打印「不得作为发布物」）。所以正常 `--out releases` 的构建不可能夹带探针。

探针注意：`after-init` 里弹窗可能让主窗口底部留一条白边（重启即恢复）；弹窗会阻塞初始化，抓取脚本要及时关掉。

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
      └─ SetupAppendData()                          → append 机制（清单分支未执行）
```

关键点：

* **`@if (DEBUG)` 是编译期指令**，release 版整块剔除 —— `scntranstempl.tjs` 之类的 DEBUG-only 载体不可用。
* `addArchive(name)` = `Storages.addAutoPath(name + "/")` + `useArchiveIfExists(name)`；`useArchiveIfExists(name)` 里 `arcname = System.exePath + name + ".xp3"`（**绝对路径**）。
* 本作字节码里**没有 `arcPath`**（0 次），只有 `exePath`（1 次）→ 旧版模板。
* `.sig` **不参与引擎校验**：替换 `steam.xp3` 后游戏照常启动，`.sig` 仍是官方那份。

## 2. 合法归档名（引擎会注册的名字）

| 名字 | 来源 | 结论 |
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

## 3. 优先级（关键结论）

同名文件冲突时谁赢，由**分组 + 注册时机**决定：

| 注册方式 | 例子 | 对 `data.xp3` 同名的覆盖能力 |
|---|---|---|
| exe 硬编码（相对路径，最早） | `data.xp3>` | 最高（其它都输给它） |
| `addAutoPath(<绝对路径> + ">")`（`addArchive` 系） | `patch.xp3>`、`steam.xp3>`、`system.xp3>` | **输**（我们的简中文本在内存 0 处，官方繁中 15 处） |
| `addAutoPath(<相对路径> + ">scn/")`（启动流程内手动注册） | `steam.xp3>scn/` | **赢** ✓ |

即：**"后注册优先"只在同为相对路径的注册之间成立**；`addArchive` 注册的绝对路径整体劣于 `data.xp3` 的相对路径。这就是 `patch.xp3` 注册成功却压不住官方文本的原因。

**相对路径之间本身的顺序也实测过了**（同一归档、两个子域、同名文件；示例里的 `sc/` 只是任意子域名，本补丁现在不用它）：钩子里先 `addAutoPath("patch3.xp3>main/")`，再 `addAutoPath("patch3.xp3>sc/")`，`Storages.getPlacedPath("order_probe.txt")` 返回`archive://patch3.xp3/sc/order_probe.txt`（后注册的那份赢）。复跑方式：`tmp/probe/{main,sc}/order_probe.txt` 两个同名文件 + 上面两条注册 + 探针打印 `getPlacedPath`（测试构建 `--allow-probe`）。所以「注册顺序 = 优先级」在同一个钩子里可以直接拿来排序，见 §4.1。

> 因此「注册成功但正文不变」的现象全部源于此；`addAutoPath` 的**重排无效**（`removeAutoPath` + 重新注册也压不过 `data.xp3`）。

### 3.1 根因：归档索引的 `hnfn` 必须「每个文件一条」，否则子域别名只认第一个文件

现象：把 17 个四块 scn 打进 `patch3.xp3` 并用 `addAutoPath("patch3.xp3>scn/")` 注册后，只有 `a01.txt.scn` 命中，`a02` 起的裸名请求全部落到 `data.xp3`。换归档内顺序就换赢家（a02 排第一则只有 a02 命中），`getPlacedPath` 也一样；用真实名字（非 md5）重建、换成 `patch.xp3`（引擎启动时自己注册的归档）都一样。

根因在**索引结构**：官方打包器写的是「**每个文件一条 `hnfn`**」，`hnfn` 全部在前、`File` 在后（`data.xp3`：943 条 hnfn / 944 个 File；`adult.xp3`：925/925）。本项目早期把全部名字塞进**一条** `hnfn`，引擎只认得出第一条条目的名字，于是子域别名只暴露一个文件。

判据（可复跑）：`python tmp/index_layout.py` 的等价检查，或用 `tool/xp3.py` 解析索引后统计顶层块；修法见 `script/build_patch.py::write_archive`（每个 placed 文件各写一条 `hnfn`）。修复后 `patch3.xp3>scn/` 对 `a01/a02/a09/a17.txt.scn` 全部命中 `archive://patch3.xp3/scn/…`，并且给 a02 第 4 块加 `SC2|` 前缀后游戏内能看到该前缀（端到端确认）。

⇒ 所以「patch 又能用了」不是改了注册写法，而是把**索引写对**：`patch3.xp3>scn/` 现在覆盖全部 17 个脚本，交付回到单 `patch3.xp3`。松散 `scn/` 目录**不进钩子**（避免多一条隐式兜底），只作为可选排障路线记录：临时把某个 scn 放进 `<游戏目录>/scn/` 并在钩子里加 `addAutoPath(System.exePath + "scn/")` 即可覆盖。

⇒ 结论：**多文件归档本是正常可用的**（`adult.xp3` 的 925 条、`data.xp3` 的 17 个 scn 都是整包+子域全覆盖）；之前「只第一条」是本项目索引写法的 bug，不是引擎限制。scn 交付因此回到**单个 `patch3.xp3`**。

### 3.2 解析模型：autopath 就是「字符串前缀」，归档条目名是 `md5(UTF-16LE 全路径)`

autopath 的解析只有一条规则：**把 autopath 字符串和请求名直接拼起来**，再去存储里找这个拼接结果。

* 目录型：`System.exePath + "scn/"` + `a02.txt.scn` = `<游戏目录>/scn/a02.txt.scn`，文件存在即命中，整目录都有效。
* 归档型：`patch3.xp3>scn/` + `a02.txt.scn` = 归档内名字 `scn/a02.txt.scn`；而本作归档条目名是 **`md5(UTF-16LE 全路径)`**，拼接结果必须能 hash 命中索引项，否则继续试下一条 autopath。

由此得到三类必错情形：

| 情形 | 拼接结果 | 结果 |
|---|---|---|
| 请求名本身带目录（`scn/a02.txt.scn`） | `patch3.xp3>scn/scn/a02.txt.scn` | 前缀重复，未命中，落到 `data.xp3>scn/` |
| 名字扩展名/大小写与打包时不一致 | `md5(...)` 不同 | 未命中（`getPlacedPath("a01.txt")` 恒空，`("a01.txt.scn")` 才有值） |
| 归档用绝对路径注册（`addArchive("patch3")`） | 同名文件与 `data.xp3` 冲突 | `data.xp3`（exe 相对路径注册、最早）胜 |

叠加 §3.1：归档子域覆盖多个文件的前提是索引「每文件一条 `hnfn`」；`main/`、`uipsd/` 这类目前没有走归档覆盖，必要时用松散目录（钩子里注册目录型 autopath）最省事。

**根域 vs 子域（实测，`Storages.getPlacedPath` 四次采样）**

| 钩子里注册的 autopath | `getPlacedPath("rootprobe.txt")`（归档根条目） | `getPlacedPath("a01.txt.scn")`（裸名） | `getPlacedPath("scn/a01.txt.scn")`（全路径） |
|---|---|---|---|
| 只有 `patch3.xp3>` | `archive://patch3.xp3/rootprobe.txt` ✓ | `data.xp3/scn/a01.txt.scn` ✗ | `data.xp3/scn/a01.txt.scn` ✗ |
| 再加 `patch3.xp3>scn/`、`>main/` | — | `archive://patch3.xp3/scn/a01.txt.scn` ✓ | — |

三条结论：

1. autopath 是**纯前缀**：`patch3.xp3>` 的前缀就是 `patch3.xp3>`，只能命中「条目名 = 请求名」的归档根条目；`scn/…`、`uipsd/…` 这类**目录下的条目必须用带目录的前缀**（`patch3.xp3>scn/`）。反过来说，**归档根下的条目确实能被根域命中**：把 `a01.txt.scn` 直接放在 `patch3.xp3` 根、只注册 `patch3.xp3>`，`getPlacedPath("a01.txt.scn")` 返回 `archive://patch3.xp3/a01.txt.scn` —— 这正是 §4.1 里「引导脚本 `<slot>_boot.tjs` 放在归档根、由根域加载」能成立的原因。
2. 注册根域**不能**覆盖 `data.xp3` 里已有的同名条目——即使请求方给的是全路径 `scn/a01.txt.scn` 也一样（exe 硬编码的 `data.xp3` 仍然赢）。想覆盖只能走子域：`patch3.xp3>scn/` 既能命中裸名、又能压过 `data.xp3`。
3. 这条结论与归档无关、**对所有 xp3 通用**：`system/initialize.tjs` 的 `addArchiveWithSubFolder(name, subs[])`就是**逐个子目录**注册两种写法（`name/sub/` 与 `name.xp3>sub/`），可见「一个归档的每个目录一条 autopath」是引擎设计本身；`main/storages.tjs` 的 `setupSubFolders(["uipsd/en", "uipsd/cn", …])` 同理。

复跑方式（测试构建，`--allow-probe`）：在两个目录放同名文件（如 `rootprobe.txt` 放归档根、`scn/` 下放`order_probe.txt`），钩子里只注册根域 → 探针打印 `getPlacedPath`；再加子域 → 再打印一次，对比即可。

## 4. 本作采用的补丁形态：hook 注入

唯一稳定可控的注入点：`steam_r18hack.tjs`（由 `steam.tjs` 的 `KAGLoadScript` 触发，启动流程内必然执行；替换为 TJS 源码后 `System.inform` 弹窗成功）。

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

* **先转发、后注册**。先 `addAutoPath` 再转发会导致语言回落英文（`multiLangFirstTag="en"`）。
* **只注册子域** `xxx.xp3>scn/`，不注册归档根，避免插手所有裸名解析。
* 注册顺序 = 优先级（后注册优先），所以自己的路径放在兼容名之后。
* `patch3.xp3` 用**官方 `steam.xp3` 索引 + 追加**的形态，不用纯自建索引。


### 4.1 补丁槽位约定：`steam.xp3` 只「转发 + 逐槽位注册根域 + 加载 `<slot>_boot.tjs`」

`steam.xp3` 里的 `steam_r18hack.tjs` 全文：

```tjs
Scripts.execStorage("steam_r18hack_orig.tjs");                 // 转发官方原逻辑
var __slots = ["patch", "patch2", "patch3"];                   // 引擎侧补丁槽位（顺序=优先级，后注册优先）
for (var __i = 0; __i < __slots.count; __i++) {
    try { Storages.addAutoPath(__slots[__i] + ".xp3>"); } catch(e) {}          // 只注册根域
    try { if (Storages.isExistentStorage(__slots[__i] + "_boot.tjs"))          // 该槽位自带引导脚本就加载
              KAGLoadScript(__slots[__i] + "_boot.tjs"); } catch(e) {}
}
```

**约定本身**（钩子里**不写任何目录名**）：

- **模板**：`resource/patch_boot.tjs.template`（含用法、编码要求、禁止事项），第三方复制成 `patch_boot.tjs` / `patch2_boot.tjs` 即可；README 的「新增合法名」一节按扩展点列出成本（改目录/加内容/叠加他人 = 只重打自己的包；新增槽位 = 一次性重建 `steam.xp3`）。
- 谁提供 `<slot>.xp3`，谁就负责在同名归档的**根目录**放 `<slot>_boot.tjs`；boot 里注册自己需要的目录。
  本补丁是 `patch3.xp3` + `patch3_boot.tjs`（源语料 `resource/ui_sc/patch3_boot.tjs`）。
- 第三方补丁照抄这个形状即可，例如 `patch.xp3` 里放 `patch_boot.tjs`：

```tjs
try { Storages.addAutoPath("patch.xp3>scn/"); } catch(e) {}
try { Storages.addAutoPath("patch.xp3>uipsd/cn/"); } catch(e) {}
```

- - boot 只注册**当前包里真的有**的目录：四个主目录（`scn/ main/ uipsd/sc/ image/`）+ 松散 `font/` + 加载 `sc_hook.tjs`；`sound/ voice/ bgimage/ fgimage/ rule/ others/ uipsd/{cn,en}/` 以注释形式留在文件里当模板，真要替换时去掉注释并重打 `patch3.xp3`。理由：boot 是给第三方看的**可读路径清单**，多余的一行会让人误以为包里有那个目录；而注册一个空目录既无收益也掩盖真实布局。
本补丁的 `patch3_boot.tjs` 做四件事：注册 `patch3.xp3>scn/ main/ uipsd/sc/ image/` → 注册松散 `font/`（字体只能读真实文件，放最后=最高）→ `KAGLoadScript("sc_hook.tjs")` 进简中逻辑（语言表、`LoadSysLangText(["sc"])`、字体钩子）。

**为什么这样拆**：`steam.xp3` 是唯一不可被第三方替换的注入点，里面越少越好；把「目录布局/优先级/新子域」都下放到各补丁自己的 boot 后——改这些只重打 `patch3.xp3`（或第三方重打自己的包），`steam.xp3` 不必再动，也不必替别人做决定。代价是槽位名（`patch`/`patch2`/`patch3`）与 `<slot>_boot.tjs` 的命名是**引擎侧约定**，写死在钩子里；增加第 4 个槽位需要重建一次 `steam.xp3`（这是注入点本身的成本，不是设计缺陷）。

**优先级不属于冲突**：注册顺序即优先级（§3 实测后注册优先），槽位顺序 `patch → patch2 → patch3`、boot 内部按各补丁自己的书写顺序，都是**明确的、可预期的**引擎语义；不同补丁写同名文件时由这个顺序决定归属，不需要仲裁机制。

可行性与实测（测试构建 `--allow-probe`，钩子加了 `System.inform` 探针）：

- `P0 hook start` → `P2 no boot patch` → `P2 no boot patch2` → `P2 boot loaded patch3` → `P3 after loop, sc=取消`：槽位循环逐个注册根域、只有 patch3 有 boot 并被加载，`sc` 语的 UI 文案随即可读。
- 只注册根域时 `getPlacedPath("patch3_boot.tjs")`、`("a01.txt.scn")`（归档根条目）都能命中 patch3；`scn/…` 这类子目录条目必须由 boot 再加 `patch3.xp3>scn/` 才命中（§3.2）。
- 实机：设置页与确认框全部简中（`patch3_boot.tjs` → `sc_hook.tjs` 链路生效）。

其它约定：

- 归档里的脚本/文本编码：`.ini`/`.txt`/`.func` 用 TVP 加扰文本（`FE FE` + mode 1，`krkr_text.encode_bytes(text, 1)`），`.tjs` 用 **UTF-16LE + BOM**（与钩子同构，引擎按内容自识别）；`.tjs` 当明文 UTF-8 塞进归档会报 `Cannot convert given narrow string to wide string`。依据：`script/build_patch.py::collect_ui_files` 的 `TEXT_EXT`/`TJS_EXT` 分支 + `doc/lessons-learned.md` §13。
- `steam.xp3` 仍需重建**一次**：本作唯一会被启动流程执行、且我们能改的脚本是 `steam_r18hack.tjs`（§0 ③）。官方原件放仓库 `resource/official_steam/steam.xp3`（`build_patch.py` 默认值，不再从游戏目录取；该目录 gitignore，可用 `<游戏>/steam.xp3.orig` 重建）。
- 发布闸（`build_patch.py` / `verify_ui_sc.py`）：钩子必须含槽位数组、`Storages.addAutoPath(__slots[__i] + ".xp3>")`、`KAGLoadScript(__slots[__i] + "_boot.tjs")`，且**不得**出现 `LoadSysLangText` / `drawTextKinsokuRect` / `AddTrueTypeFont` / `patch3.xp3>scn/` / `System.exePath`；`patch3_boot.tjs` 必须含四条启用子域 + `font/` + `KAGLoadScript("sc_hook.tjs")`；任何产物都不许带探针。

## 5. 语言轨：新增第 4 轨 `sc`（简中），官方 jp/en/cn 三轨原样保留

`main/default.tjs` 是**加扰 TJS 源码**（`FE FE 01` + mode 1 奇偶位交换，`tool/krkr_text.py` 可解码/编码，往返逐字节一致），关键字段：

```tjs
.multiLangLanguageTags = [ "jp", "en", "cn" ];
.multiLangFirstTag     = "en";
.multiLangParamsMap    = %[ en: %[...], cn: %[ "menu_caption" => "&Traditional Chinese" ] ];
function GetScnConvertLangList() { var r = []; r.assign(SystemConfig.multiLangLanguageTags); r.shift(); return r.join(","); }
```

`GetScnConvertLangList()` 没有任何 TJS 调用者 ⇒ 它由**引擎（M2 层）**调用，返回值就是「除 jp 之外要取的语言块列表」，这也说明 **row 的 `blocks` 是按 `multiLangLanguageTags` 的序号定位取块的**，加第四条必须给 9327 行各插一个块。

### 5.1 运行时注入语言表

在 `steam.xp3` 的钩子里执行下面三行，语言表在游戏内变成 4 条（依据：钩子内探针输出 `cfg=jp/en/cn/sc ui=jp/en/cn/sc scn=en,cn,sc`）：

```tjs
SystemConfig.multiLangLanguageTags.add("sc");                                              // 引擎侧（GetScnConvertLangList）
SystemConfig.multiLangParamsMap["sc"] = %[ "menu_caption" => "&Simplified Chinese" ];      // 菜单 caption
LanguageTags.add("sc");                                                                   // UI 侧（设置菜单语言项）
```

证据：钩子里 `System.inform("LANGPROBE cfg=" + … + " ui=" + LanguageTags.join("/") + " scn=" + GetScnConvertLangList())` 一次启动即可读出三处都是 4 条。**前提是 row 里已经有 `sc` 块**，否则引擎取第 4 块时无内容。

### 5.2 `patch3.xp3` 不能用来覆盖 `*.tjs`

`Storages.addAutoPath("patch3.xp3>main/")` 对 `main/` 域**完全无效**：注册返回 ok，但 `Storages.getPlacedPath("default.tjs")` 仍指向 `data.xp3/main/default.tjs`，新名字（`ml_chs.tjs`）一律解析为空。同一归档的 `patch3.xp3>scn/` 域却正常（`a01.txt.scn` → `archive://patch3.xp3/scn/a01.txt.scn`）。

排除过的变体（均在游戏内读 `getPlacedPath` / `isExistentStorage` 判定）：

| 尝试 | 结果 |
|---|---|
| `patch3.xp3>main/`（主域） | 覆盖 `default.tjs` 无效、新名字不可见 |
| `patch3.xp3>main`（无尾斜杠） | 同上 |
| `patch3.xp3>`（归档根） | 裸名/全路径都不可见，且仍指向 `data.xp3` |
| `Storages.addAutoToolsPath("patch3.xp3>main/")` | 返回 ok，仍是不可见 |
| 同域新增名字（`scn/zz5.txt.scn`、`scn/zz1..4.{txt,bin,tjs}`） | 全部解析为空；只有**已存在于 `data.xp3>scn/` 的 17 个 scn 名**能命中 patch3 |
| `addArchive` / `System.addArchive` / `Storages.addArchive` | 都不存在（`Member ... does not exist`；全局 `addArchive` 内部报 `useArchiveIfExists` 缺失） |
| 归档内放 `ml_chs.tjs` 再 `KAGLoadScript("ml_chs.tjs")` / `("main/ml_chs.tjs")` | `Cannot find storage …` |

结论：**需要新名字的 tjs 只能放在 `steam.xp3`（钩子自身）或游戏目录的松散文件里**，patch3 只能用来替换 `data.xp3` 里已存在的同名资源（scn 就是这种情况）。注入逻辑因此写在钩子里（`HOOK_LINES`）。

### 5.3 第 4 个块：整图重排（`tool/psb.PsbGraph`）

PSB 的容器体是「相对偏移 + 顺序嵌套」布局（`LIST`/`OBJECTS` 读完 offsets 数组后，子对象紧跟基址顺序排布），插一个子对象会移动其后所有字节，因此必须整图重排。`tool/psb.py` 有 `PsbGraph`（`parse_graph()` → `PNode` 树 → `build()`），关键细节两条：

* 字段宽度按原样记录（`PNode.style`），零改动重建才能逐字节一致；
* **同一容器内结构相同的子对象共享偏移**（原始写出器就这么去重，例：`$.scenes[0].lines[0][1].env.action` 两个子项 offsets 都是 0），emit 时按「子对象字节」去重才能还原。

闸：17 个官方 scn **全部逐字节一致**（`PsbFile(raw).parse_graph().build() == raw`）。

`script/extend_lang.py` 用它给每行追加第 4 个语言块 + 给每个选择支追加第 4 项（前 3 块逐值不变，产物幂等）。依据：`a01` 378 行 + 2 选项扩成 4 块后，游戏内切到第 4 项，正文来自第 4 块 ⇒ 引擎按 `multiLangLanguageTags` 序号取块这一判断成立。

### 5.4 字体：官方只带 JP/TC，简中字形覆盖不足

`data.xp3` 里的字体是**小写路径**的 10 个 OTF：`font/sourcehansans{jp,tc}-{medium,bold,heavy}.otf`、`font/sourcehanserif{jp,tc}-{bold,heavy}.otf`，**没有 CN/SC 字体**。`font/embfontlist.tjs` 里 CN（简体）那一段本来就是注释掉的；民汉初版补丁的 `font/embfontlist.tjs` 与官方**完全一致**（他们只是把 TC 字体又打进了自己的包），也没有 CN 字体文件。

**cmap 覆盖 ≠ 游戏内渲染正确**：`script/check_font_coverage.py` 读 cmap 会给出「TC 字体对 2460 个语料字符缺字 0」这种数字（JP 缺 613），但第 4 轨即使指向 TC 字体仍然乱码/缺字，离线覆盖率不能当作结论（见 `lessons-learned.md` §8.2）。

⇒ **简中需要独立的 CN/SC 字体**（即官方注释掉的 `思源黑体{M,B,H}` / `思源宋体{B,H}` 那一段 + `sourcehansanscn-*.otf` 文件），按需引入（只引入实际用到的字重，不必全部）。字体注册与绑定见 §5.5、§6。

### 5.5 第 4 轨的字体怎么设（落地见 §6）

钩子作用域里 `kag` / `global.kag` 都还不存在（`Member "kag" does not exist`），必须用 `addAfterInitCallback` 在 KAG init 之后再动。after-init 里读到的状态（`AFTERINIT` 探针）：

```
set=ok ; f0=3 ; f1=源ノ角ゴシックB ; f2=思源黑體B ; f3=源ノ角ゴシックB
```

即 `kag.setLanguageFont(3, "思源黑體B")` 返回成功但 `getLanguageFont(3)` 仍是 JP 字体。

**`sysscn/multilang.tjs` 的反汇编结果**（`tool/tjs2.py`，见 §5.5.1）：

* `KAGWindow.getLanguageFont(index)` 的取值顺序：`scflags[ sprintf(multiLangUserFontFaceFmt, index) ]` → `MessageDefaultFontFaceMap[LanguageTags[index]]` → `chDefaultFace`；
* 那个 `scflags` 是 **`kag.scflags`（KAGWindow 上的字典）**，不是 `SystemConfig.scflags` —— 写成 `SystemConfig["langUserFontFace3"]` / `SystemConfig.scflags[...]` 都不生效，就是这个原因（`SystemConfig.scflags` 是 void，被守卫条件跳过，静默无效）；
* `kag` 在钩子作用域里不存在，必须在 `addAfterInitCallback` 回调里取 `global.kag`。

⇒ 修法：after-init 里 `global.kag.scflags["langUserFontFace3"] = scflags["langUserFontFace2"]`（继承玩家给繁中轨选的字体），不要弹 `System.inform`（会留白边）。

切到第 4 项（idx=3）时探针打印：`TAGS n=4 [jp|en|cn|sc] cur=sc kagLang=3 uiLang=3 cfgTags=jp|en|cn|sc MsgFace=思源黑体B chFace=源ノ角ゴシックB`

* **语言轨本身完全正常**：`LanguageTags`/`CurrentLanguageTag`/`SystemConfig.multiLangLanguageTags` 都是 4 条，当前 tag 就是 `sc`；
* `MessageDefaultFontFace`（消息层真正用的字体）= **`思源黑体B`** —— 官方 `main/config.tjs` 里 `LanguageDefaultFontFaceMap = %[ sc:"思源黑体B", cn:"思源黑體B" ]` 生效，但 **`思源黑体B` 这个 CN 字体本作没随包**（`data.xp3` 只有 JP/TC 十个 OTF，`embfontlist.tjs` 的 CN 段是注释掉的）⇒ 缺字；
* `kag.chDefaultFace`（消息层直接取的字段）= `源ノ角ゴシックB`；
* 在钩子**顶层**改 `LanguageDefaultFontFaceMap["sc"]` / `MessageDefaultFontFaceMap["sc"]` **不生效** —— `main/config.tjs` 在 `custom.tjs` 之后才执行，会把这两处重新写回；`MessageDefaultFontFaceMap` 还是个 getter，每次访问都用 `MakeFontFaceMap(LanguageDefaultFontFaceMap, …)` 重建，改了缓存也没用。

### 5.5.1 `tool/tjs2.py`：TJS2 字节码读取 + 反汇编（自写，非移植代码）

引擎脚本是 `TJS2100` 字节码，要读 `multilang.tjs` 这类逻辑只能反汇编。`tool/tjs2.py` 实现 DATA 常量池 + OBJS 对象表解析与逐指令反汇编（操作数布局按 TJS2 VM 的规则；跳转是相对词下标），命令行：

```powershell
mamba run -n GalRev python tool/tjs2.py tmp/multilang.tjs --out tmp/multilang.dis.txt   # 全量反汇编
mamba run -n GalRev python tool/tjs2.py tmp/multilang.tjs --strings                       # 只列字符串池
```

遇到未知指令直接抛错（不猜长度），保证输出不会错位。参考实现 `xmoezzz/tjs2Decompiler`（Rust，未随附 license，只当格式参考，**没有拷贝其代码**）。

### 5.6 探针文字别用 `[...]`

行内 `[...]` 是 ruby 语法，探针前缀写成 `[CHS]` 会被渲染成注音（显示成 `{有:CHS}` 之类），排查时先怀疑自己的标记。

### 5.7 UI 文案：`syslangtext` / `help` / 界面贴图（`_<tag>` 变体名）

UI 文案与剧情脚本走**两套完全不同**的通路，别混着排查。

**① 文本（`syslangtext_<tag>.ini` / `help_conf_<tag>.txt` / `help_exch_<tag>.txt`）**

- 加载者是 `sysscn/syslangtext.tjs`（字节码）：`sysscn/multilang.tjs` 顶层 `KAGLoadScript("syslangtext.tjs")` 之后调用 `LoadSysLangText()`。签名大致为 `LoadSysLangText(name="syslangtext_", ext=".ini", tags=LanguageTags, parse?, ?)`：对 `tags` 里每个非空 tag 拼 `<name><tag><ext>`，先用 `Storages.isExistentStorage` 判存在再解析。
- **时机坑**：`multilang.tjs` 由 `main/custom.tjs` 顶层 `KAGLoadScript` 载入，而我们的钩子 `steam_r18hack.tjs` 在同一文件末尾的 `switch (System.getArgument("-steam"))` 里，**晚于**它。所以钩子里加完 `sc` 后必须再补一次 `LoadSysLangText("syslangtext_", ".ini", ["sc"])`，否则 `sc` 永远读不到。探针依据：补载前 `GetSysLangText("DialogCancel","sc")` 为空，补载后为 `取消`。
- `help_conf` / `help_exch` 不预加载，是打开设置页时 `CustomHelpTextManager` → `loadHelpTexts` 被 `objectHookInjection` 转成 `GetUIFile(name, ".txt")` 按需读取；钩子里注册好路径就够。
- 侧栏快捷存读提示语是 `EzSaveHelpText`，`main/ezsave.tjs` 会 `text.replace(/,/, "\\n")`，**值里的逗号不能删**。

**② 界面贴图（`uipsd/*.pimg` + `uipsd/*.func`）**

- `.pimg` = PSB v3：`layers` 里每个图层的位图是一份 chunk 资源，键名 = `<layer_id>.tlg`（结构见 `file-formats.md` §5）。
- `.func` 是 KAG 的 UI 布局脚本，**同样是 TVP 加扰文本（mode 1）**，首行 `psd,<名字>` 决定用哪张图；写成 `psd,&GetUIFile("名字")` 才按当前 UI 语言找变体。
- 变体规则即 `custom.tjs` 的 `GetUIFile`：`<chop>_<CurrentLanguageUITag><ext>` 存在则用，否则回落原名。目录子域由 `system/initialize.tjs` 的 `setupSubFolders(["uipsd/en", "uipsd/cn", ...])` 注册（只注册**目录**，不注册同名 xp3）。
- 因此第 4 轨要新增 `uipsd/sc/<名>_sc.pimg`，并在钩子里 `addAutoPath("patch3.xp3>uipsd/sc/")`；`main/`（syslangtext、help）与 `image/`（`attention_sc.png`）同理。运行时逻辑（含 `LoadSysLangText` 补载、字体）在 `patch3.xp3` 的 `sc_hook.tjs`（归档根），见 §4.1。

**③ `conf_lang` 特例：语言选择页的标题是「一张英文位图」**

- 官方 `uipsd/conf_lang.pimg` 的 `@caps_lang/layer`（221×199，资源 `14.tlg`）把 `System Language / Main Text Language / Sub Text Language` 直接烘在图上；`data.xp3` 全文与所有脚本字符串池搜 `System Language` 命中 **0**，改 `syslangtext` 无效。验证：把 `14.tlg` 换成别的图，标题随之变化。
- `conf_lang.func` 首行是 `psd,conf_lang`（不经过 `&GetUIFile`），且官方没有 `conf_lang_{jp,en,cn}.pimg` —— **官方三条语言轨看到的本来就是同一张英文图**，不是补丁「强制成英文」。
- sc 轨要中文只能自造图：`script/make_ui_lang_caption.py`（取官方 `14.tlg` → 保留左侧圆点、清掉英文 → GDI+ 渲染简中标题 → 重编码 TLG → 替换进 pimg）+ `script/gen_ui_func.py`（`psd,conf_lang` → `psd,&GetUIFile("conf_lang")`）。后者对 jp/en/cn 语义中性：找不到 `conf_lang_<tag>.pimg` 就回落官方原图。
- 字形按**民汉贴图**的实测量选定：同一句「简易保存、读取功能」16 px 下量「每像素墨覆盖率」（把不同背景归一化后可比），民汉 art = 0.400、华康圆体 W9(P) = 0.437、W7/W5 ≈ 0.30、思源圆黑体（Gen Jyuu Gothic）≈ 0.20、思源黑体 ≈ 0.22。所以用**华康圆体 W9**（真实字重，非合成），并以 2 倍超采样渲染后盒式降采样，让边缘与 art 一样柔。对照图与实机截图属一次性产物，不进 `resource/`；需要复核时按本节方法重跑 `script/make_ui_lang_caption.py` 并用 GDI+ 重渲染候选即可。
- **字体文件不入库**（第三方商业字体）：`resource/ui_sc/conf_lang_labels.json` 的 `font` 指到本机路径，缺失时脚本直接报错而不是悄悄换字体；`--font/--style/--scale` 可覆盖。仓库默认回退是随包思源黑体（字形不完美但可构建）。
- **禁止用 GDI+ 合成粗体凑字重**：`FontStyle::Bold` 在字体没有粗体面时会被 GDI+ 硬加粗（笔画变钝、字宽变化），和真实粗体不是一回事。`script/render_ui_labels.ps1` 现在对「非该字体真实字重」的请求直接 `exit 2`。
- 标题摆放与页面其它标签对齐：文字左边缘 x=25、三行行带顶端 y=1/90/179（脚本会打印实测行带），字号 16 px、颜色 `(19,86,130)`（从民汉简中标签实色量出来）。官方英文原图行带是 1/90/179、文字左边缘 25，两者一致。

**④ UI 里硬编码的日文字体别名**

`main/custom.tjs` 有几处写死 `fontface:"源ノ明朝B"`（语言名标签）与 `"マルベリ"`（帮助提示、鉴赏页名字）。这两个是 JP 子集：`sourcehanserifjp-bold.otf` 缺 `简/苏/亚`，`mtlmr3m.ttf` 缺 `简/苏/亚/风/戏/设`（`script/check_font_coverage.py` 读 cmap 可复现），sc 下会画成「口」。钩子因此在 after-init 里包了 `global.drawTextKinsokuRect`：UI 语言或正文语言为 `sc` 且 `elm.fontface` 命中这些别名时换成随包思源黑体 CN（Bold/Medium），画完还原 `fontface`，jp/en/cn 三轨不受影响。


## 6. 字体：运行期注册松散 `font/` 里的思源黑体 CN（可用）

官方 `font/embfontlist.tjs` 由 `LoadEmbeddedFontList()`（位于 `data.xp3` 的一个 6.7 KB TJS 字节码里）在启动时读入，逐条调用 `EntryFont()`：`PreRenderFontEx.AddTrueTypeFont(name, face, file, 0)`（`.tft` 走 `AddFont`），`file` 先用 `Storages.isExistentStorage` 判存在。`PreRenderFontEx` 类由 `sysscn/PreRenderFontEx.tjs` 定义（该脚本全局初始化只把**类**挂到 `global.PreRenderFontEx`；实例由游戏启动流程创建）。

可行做法（`script/build_patch.py::HOOK_LINES`）：

* 松散字体目录：`Storages.addAutoPath(System.exePath + "font/")`（钩子里同时注册 `patch3.xp3>font/`，两者都用松散目录优先）；
* `addAfterInitCallback` 里（此时 `global.PreRenderFontEx` 与 `System.addFont` 都已是 Object）：
  `PreRenderFontEx.AddTrueTypeFont("9nineSC-B", "Source Han Sans CN", "SourceHanSansCN-Bold.otf", 0)`、Medium 同理注册 `9nineSC-M`；
* 第 4 轨映射：`LanguageDefaultFontFaceMap["sc"] = "9nineSC-B"`、`LanguageNameFontFaceMap["sc"] = "9nineSC-M"`；消息层真正吃 `kag.chDefaultFace`，所以在 `setMessageLayerUserFont` 前置 hook 里 `if (kag.languageType == 3) { kag.chDefaultFace = "9nineSC-B"; kag.scflags["langUserFontFace3"] = "9nineSC-B"; }`（`scflags` 在 `kag` 上，不在 `SystemConfig` 上；`multiLangUserFontFaceFmt = "langUserFontFace%d"`）；
* 要点：**注册调用要放在 after-init 之后**，且不要在钩子里重复 `KAGLoadScript("PreRenderFontEx.tjs")` 把实例换成类。
**为什么字体必须放松散目录、不能塞进 patch3**：`PreRenderFontEx.AddTrueTypeFont` 最终调用 `System.addFont(file, 0)`（原生字体加载），它只认**真实文件**。归档内条目虽然 `Storages` 能看到（`isExistentStorage` = 1、`getPlacedPath` = `archive://patch3.xp3/font/…`），但原生加载器打不开 `archive://`，取不到字体信息（void），在内部 `.xxx` 上抛 `Cannot convert the variable type ((void) to Object)`；把 `placed`（`archive://…`）当 `file` 传进去同样失败。官方随包字体（JP/TC）能放在 `data.xp3` 里，是因为它们走**引擎启动时的原生嵌入字体机制**（`embfontlist.tjs` → 引擎侧加载），不是这条运行期 TJS 通道。

**判定「别名 → 字体文件」真的生效**：把 `9nineSC-B` 临时注册到游戏自带的宋体（`SourceHanSerifTC-Bold.otf`，face 写 `Source Han Serif TC`），游戏内第 4 轨正文变成衬线即证明链路成立——只换文件、不改其它代码，排除了「其实还是官方字体」的可能。本作按此法确认过：默认（Sans CN）时是思源黑体的黑体形态，不是官方 TC 字体。

* 回落策略：注册失败时第 4 轨用**系统字体 `Microsoft YaHei`**（保证字形完整、不出现缺字方框）。**不回落官方繁中字体**（`思源黑體B/M`）：它是繁体字形风格，且一旦遇到覆盖不到的字就会渲染成方框，属于不可接受的结果。

字体载荷：`resource/fonts_sc/`（Adobe「Source Han Sans CN」SubsetOTF 的 Bold/Medium + `LICENSE.txt`，OFL，共约 17 MB），`build_patch.py` 默认复制成 `releases/font/`。字形覆盖用 `script/check_font_coverage.py` 复核（两个字重对语料 2460 字缺 0），最终以游戏内截图为准。

### 6.1 更早注入点的调查结论：没有可用位置，字体只能松散放

想把字体塞回 `patch3.xp3` 就需要比 `main/custom.tjs` 更早的执行点，实际排查结果：

* **`patch3.xp3>main/` 现在能用**（逐文件 `hnfn` 修复后）：钩子里 `Storages.getPlacedPath("default.tjs")` 返回 `archive://patch3.xp3/main/default.tjs`。但把官方 `main/default.tjs` 加个 `System.inform("DEFHOOK")` 放进 patch3 后，游戏内**没有弹窗** ⇒ 这些 main 脚本在钩子注册之前就已加载，覆盖无效。
* **`SystemConfig.EmbeddedFontList` 恒为 void**（钩子时、after-init 都是），说明 TJS 侧那个 `LoadEmbeddedFontList()` 清单并未生效，官方嵌入字体走的是引擎原生路径；没有可扩展的 TJS 清单。
* **用 `steam.xp3` 做「新名字」早期脚本会崩**：`main/config.tjs` 里有 `if (Storages.isExistentStorage("ConfigEx.tjs")) KAGLoadScript(exconf)`，把 `ConfigEx.tjs` 放进 `steam.xp3`（该归档由 `main/storages.tjs` 在更早阶段 `addArchive("steam")` 注册）后，游戏启动即 **Access Violation**；换成空注释文件、或改用 `FE FE` 加扰编码，都一样崩 ⇒ 这条路不可用。

⇒ 结论：**当前唯一可控的注入点是 `main/custom.tjs` 末尾的 `steam_r18hack.tjs`**，比它更早的位置要么不归我们控制、要么会崩。字体因此保持**松散 `font/`**，`patch3.xp3` 只装 scn。

## 7. 安装 / 卸载

* 安装：把官方 `steam.xp3` 改名 `steam.xp3.orig`（备份），复制 `releases/steam.xp3` + `releases/patch3.xp3` 进游戏目录，再把 `releases/font/` 整目录复制成 `<游戏目录>/font/`。
* 日常更新：只替换 `patch3.xp3`。
* 卸载：删 `patch3.xp3` 与 `<游戏目录>/font/`，把 `steam.xp3.orig` 改名回 `steam.xp3`。
* 不替换 `nine_kokoiro.exe` / `steam_api.dll`，成就与云存档不受影响。
