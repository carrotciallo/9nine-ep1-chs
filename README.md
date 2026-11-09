# 9-nine-:Episode 1 简中补丁

Steam 版《9-nine-:Episode 1》（appid 976390）的简体中文文本补丁。

- 文本来源：樱空汉化组 Ver1.0（经初版补丁归档转手）+ 官方简中界面素材
- 目标：**四语言轨**——官方 `jp` / `en` / `cn`（繁中）三轨原样保留，新增第 4 轨 `sc`（简中，正文 + 选项 + UI 文案 + 界面贴图）
- 不替换 `nine_kokoiro.exe` / `steam_api.dll` / `.sig`，也不带第三方 DLL，从 Steam 正常启动

> 本仓库只包含分析与构建工具，不含游戏本体资源。补丁仅供已购买正版的用户使用。

## 目录

```
tool/        长期复用库（xp3 / cx / psb / mdf / scn / tlg / pngio / textset / krkr_text / tjs2）
script/      流程脚本（解包、提取、校验、回写、UI 语料、打包）
resource/    文本集、UI 语料、名称清单、校验字表、第三方模板
doc/         格式、文本模型、引擎机制、教训、验收标准
releases/    交付物（不入库）
archive/     初版补丁作者的归档（只读，不入库）
```

补丁产物（`releases/*.xp3`、`releases/font/`）**不入库**（二进制 + 含游戏素材），按上面管线在本地构建；发行说明按需临时书写，不入库。

## 补丁形态

| 文件 | 大小 | 作用 |
|---|---|---|
| `releases/steam.xp3` | 19 KB | **hook 注入**：官方 4 条 + `steam_r18hack.tjs`（源码钩子：转发官方 → 逐槽位注册根域并加载 `<slot>_boot.tjs`）+ 官方原字节码副本 |
| `releases/patch3.xp3` | 12.2 MB | **简中内容归档**：17 个四块 scn（jp/en/cn 官方原文 + 第 4 块简中）+ UI 语料（`main/syslangtext_sc.ini`、`main/help_conf_sc.txt`、`main/help_exch_sc.txt`）+ 21 张 `uipsd/sc/*_sc.pimg` + 2 张 `image/attention*_sc.png` + 运行期逻辑 `sc_hook.tjs`（归档根） + 路径清单 `patch3_boot.tjs`（都在归档里，日常更新只换这个包） |
| `releases/font/` | 17 MB | **思源黑体 CN**（Bold/Medium，OFL）：运行期注册成 `9nineSC-B/M`；字体只能放松散文件，复制成 `<游戏目录>/font/` |
| 安装 | 官方 `steam.xp3` 改名 `steam.xp3.orig`；复制 `steam.xp3` + `patch3.xp3` 进游戏目录；`releases/font/` 整目录复制成 `<游戏目录>/font/` |
| 卸载 | 删 `patch3.xp3` 与 `<游戏目录>/font/`，把 `steam.xp3.orig` 改名回 `steam.xp3` |

`patch.xp3` / `patch2.xp3` 留给第三方补丁：钩子按 `patch → patch2 → patch3` 的顺序注册根域并加载各自的`<slot>_boot.tjs`，所以第三方只要遵循同一约定即可叠加，不需要改 `steam.xp3`（见下一节）。

为什么必须动 `steam.xp3`：本作引擎只注册固定名单的归档，且 `addArchive` 系相对 `data.xp3` 优先级不足；唯一稳定做法是在「会被执行的脚本」（`steam_r18hack.tjs`）里注入一次注册 + 引导加载。详见 `doc/engine-mechanics.md` §0/§3/§4.1。

## 新增合法名：`<slot>.xp3>` 与 `<slot>_boot.tjs`

本作引擎只会自动注册固定名单的归档名（`data`/`steam`/`system`/`patch`/…）。这套约定做的事就是**在不改引擎的前提下扩展合法名**，并**提升目标归档的优先级**：任何补丁只要提供 `<名>.xp3` + 该归档根目录的 `<名>_boot.tjs`，就等于向引擎新增了一个可用的归档名，且加载路径/优先级由它自己声明。

钩子（`steam.xp3` 里的 `steam_r18hack.tjs`）只做两件事：转发官方、对每个补丁槽位 `patch` / `patch2` / `patch3` 依次「注册 `<slot>.xp3>` 根域 + 加载归档内存在的 `<slot>_boot.tjs`」。**它不注册任何子目录**——目录布局由各补丁自己在 boot 里决定，互不代劳。

- 模板：[`resource/patch_boot.tjs.template`](resource/patch_boot.tjs.template)。复制成 `patch_boot.tjs` / `patch2_boot.tjs` / `patch3_boot.tjs`，放在**补丁归档的根目录**，文件存成 **UTF-16LE + BOM**，打包成同名 `patch*.xp3` 即可。
- 必须自己注册的内容：归档内每个**子目录**（`scn/`、`main/`、`image/`、`uipsd/cn/` …）；归档**根**下的条目靠根域就能被裸名命中（扁平包零配置）。
- 优先级 = 注册顺序（后注册优先）：槽位顺序 `patch < patch2 < patch3`，boot 内部的先后由你决定。
- 限制：槽位名是引擎侧约定，新增第 4 个槽位需要重建一次 `steam.xp3`；字体只能放松散目录（`System.addFont` 读不了 `archive://`）；不要让 `main/*.tjs` 或 `ConfigEx.tjs` 之类"更早加载"的脚本走覆盖（实测无效 / 会崩）。

### 扩展点与成本

| 想扩展什么 | 怎么改 | 成本 |
|---|---|---|
| 新增/调整包内目录（`scn/`、`foo/`…） | 改自己归档里的 `<slot>_boot.tjs`，加一行 `addAutoPath("<slot>.xp3>foo/")` | 重打自己的包，**不动** `steam.xp3` |
| 新增内容（文本/贴图/字体映射/运行期逻辑） | 只改自己的包（逻辑脚本用 `KAGLoadScript` 从包内加载） | 重打自己的包 |
| 与其它补丁叠加 | 各自提供 `<slot>_boot.tjs`，互不代劳；冲突由槽位顺序（`patch < patch2 < patch3`）表达 | 同上 |
| 新增第 4 个槽位（`patch4`…）或换槽位名 | 改钩子里的 `__slots` 数组 | **一次性**重建 `steam.xp3` |
| 让补丁用任意归档名（连槽位名也不约定） | 需要"运行时读取清单/扫描目录"能力：TJS 能否读游戏目录文本**待验证**；彻底方案是 DLL 在 open 层拦截（`KirikiriTools` 的做法，本项目不采用） | 现状边界，见下 |

**已知边界**：槽位名与 `<slot>_boot.tjs` 的命名是引擎侧约定、写死在钩子里；`main/*.tjs` 这类"更早执行"的脚本无法通过覆盖生效（官方脚本在钩子之前就跑完了）；字体只能放松散 `<游戏目录>/font/`（`System.addFont` 读不了 `archive://`）。

机制与实测依据见 `doc/engine-mechanics.md` §3.2（autopath = 纯前缀）、§4.1（槽位约定、探针输出）。

## 快速开始

```powershell
mamba run -n GalRev python script/selftest.py        # 工程自检
mamba run -n GalRev python script/verify_cx.py       # Cx 解密黄金向量
```

完整构建管线（需要自备正版游戏文件）：

> 语料（`resource/chs_text`、`resource/official_{jp,en,cn}`、`resource/ui_sc` 的文本与贴图）**不在本仓库内**（见 NOTICE），并已被 `.gitignore` 排除：构建前请自备并放入上述本地路径。下面两条 `extract_text.py` 是语料的生成方式（从自备的正版游戏文件与初版补丁包提取）。

```powershell
mamba run -n GalRev python script/unpack_xp3.py "E:/SteamLibrary/steamapps/common/nine_kokoiro/data.xp3" --cx-profile resource/cx/profile_9nine.json --only scn/ --out resource/official_scn
mamba run -n GalRev python script/extract_text.py --from-xp3 archive/releases/unencrypted.xp3 --lang cn --out resource/chs_text
foreach ($l in "cn","jp","en") { mamba run -n GalRev python script/extract_text.py --from-dir resource/official_scn --lang $l --out "resource/official_$l" }
mamba run -n GalRev python script/verify_extract.py --base resource/official_jp --target resource/chs_text --out resource/verify
mamba run -n GalRev python script/extend_lang.py --official resource/official_scn/scn --text resource/chs_text --out tmp/build/lang4
mamba run -n GalRev python script/verify_lang4.py --official resource/official_scn/scn --built tmp/build/lang4/scn --text resource/chs_text
# UI 语料（可从初版补丁包抽取贴图；标题贴图需要本机装有华康圆体 W9，见 doc/engine-mechanics.md §5.7）
mamba run -n GalRev python script/extract_ui_sc.py                  # 20 张 pimg + 2 张 attention -> resource/ui_sc/
mamba run -n GalRev python script/gen_ui_func.py                    # conf_lang.func 覆盖（psd 行改 GetUIFile）
mamba run -n GalRev python script/make_ui_lang_caption.py           # 语言页三行标题 conf_lang_sc.pimg
mamba run -n GalRev python script/gen_ui_trad_chars.py              # 繁中残留字表（校验用）
# 打包（官方 steam.xp3 默认取 resource/official_steam/steam.xp3）
mamba run -n GalRev python script/build_patch.py --scn-dir tmp/build/lang4/scn --out releases
mamba run -n GalRev python script/verify_ui_sc.py --patch releases/patch3.xp3 --steam releases/steam.xp3
```

详细约定见 `AGENTS.md`，技术结论见 `doc/`。

## 来源与致谢

| 内容 | 出处 |
|---|---|
| 汉化文本 | 樱空汉化组 Ver1.0 |
| 引擎分析 | `GalRev`（krkr/MDF 卷） |
| 工程架构 | `MashiroiroSymphonyFHD_Retranslation_Patch` |
