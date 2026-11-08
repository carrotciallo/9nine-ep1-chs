# 9-nine-:Episode 1 简中补丁

Steam 版《9-nine-:Episode 1》（appid 976390）的简体中文文本补丁。文本替换已完成并通过离线验收，引擎内的实测由用户自行完成（见下方「当前状态」）。

- 文本来源：樱空汉化组 Ver1.0（经初版补丁归档转手）
- 目标：把官方 **繁中轨道**（`cn`）的剧情正文与选项换成民汉简中；日/英轨保持官方原文
- 不替换 `nine_kokoiro.exe` / `steam_api.dll`，从 Steam 正常启动

> 本仓库只包含分析与构建工具，不含游戏本体资源。补丁仅供已购买正版的用户使用。

## 目录

```
tool/        长期复用库（xp3 / hxv4 / psb / mdf / textset / krkr_text）
script/      流程脚本（提取、校验、回写、打包）
resource/    文本集与清单
doc/         格式、文本模型、引擎机制、教训、验收标准
releases/    交付物
archive/     初版补丁作者的归档（只读）
```

补丁产物（`releases/*.xp3`、`*.dll`）**不入库**（20 MB 级二进制 + 含游戏素材），
按上面管线在本地构建；`releases/README.txt` 入库。

## 当前状态

| 阶段 | 状态 |
|---|---|
| 工程骨架与约定 | 完成（`script/selftest.py` 17 项通过） |
| 官方/民汉文本提取 | 完成（两侧各 17 脚本 / 9327 行 / 9 选项） |
| 行数严格一致校验 | 完成（0 差异，末尾行语义抽查 17/17 一致） |
| 语言轨与生效通路判定 | 完成（覆盖 cn 轨；**hook 注入**，见下） |
| 回写与打包 | 完成（`releases/steam.xp3` + `releases/patch3.xp3`） |
| 游戏内验证 | **已实测**：正文简中生效（首启需在设置里切一次「繁體中文」） |

## 补丁形态

| 文件 | 大小 | 作用 |
|---|---|---|
| `releases/steam.xp3` | 19 KB | **hook 注入**：官方 4 条 + `steam_r18hack.tjs`(源码钩子) + 官方原字节码副本 |
| `releases/patch3.xp3` | 2 MB | **简中剧本归档**（17 个 scn）；日常更新只换这一个 |
| 安装 | 把官方 `steam.xp3` 改名 `steam.xp3.orig`，再把上面两个文件复制进游戏目录 |

`patch.xp3` / `patch2.xp3` 留给第三方补丁（钩子已按顺序注册，互不冲突）；想临时替换某一话剧本，
把 `a01.txt.scn` 之类直接放进游戏目录的 `scn/` 即可（钩子也注册了这个松散目录，优先级最高）。
为什么必须动 `steam.xp3`：本作引擎只注册固定名单的归档，且 `addArchive` 系相对 `data.xp3` 优先级不足，
唯一稳定做法是在「会被执行的脚本」（`steam_r18hack.tjs`）里注入一次 `addAutoPath`。
详见 `doc/engine-mechanics.md` §0/§3/§4。

## 快速开始

```powershell
mamba run -n GalRev python script/selftest.py        # 工程自检
mamba run -n GalRev python script/verify_cx.py       # Cx 解密黄金向量
```

完整构建管线（需要自备正版游戏文件）：

```powershell
mamba run -n GalRev python script/unpack_xp3.py "E:/SteamLibrary/steamapps/common/nine_kokoiro/data.xp3" --cx-profile resource/cx/profile_9nine.json --only scn/ --out resource/official_scn
mamba run -n GalRev python script/extract_text.py --from-xp3 archive/releases/unencrypted.xp3 --lang cn --out resource/chs_text
foreach ($l in "cn","jp","en") { mamba run -n GalRev python script/extract_text.py --from-dir resource/official_scn --lang $l --out "resource/official_$l" }
mamba run -n GalRev python script/verify_extract.py --base resource/official_jp --target resource/chs_text --out resource/verify
mamba run -n GalRev python script/writeback.py --official resource/official_scn/scn --text resource/chs_text --out tmp/build/scn
mamba run -n GalRev python script/verify_patch.py --official resource/official_scn/scn --text resource/chs_text --built tmp/build/scn
mamba run -n GalRev python script/verify_roundtrip.py --official resource/official_scn/scn --built tmp/build/scn --text resource/chs_text
mamba run -n GalRev python script/build_patch.py --scn-dir tmp/build/scn --official-steam "E:/SteamLibrary/steamapps/common/nine_kokoiro/steam.xp3.orig" --out releases
```

详细约定见 `AGENTS.md`，技术结论见 `doc/`。

## 来源与致谢

| 内容 | 出处 |
|---|---|
| 汉化文本 | 樱空汉化组 Ver1.0（版权归原汉化组） |
| 引擎分析 | `GalRev`（krkr/MDF 卷） |
| 工程架构 | `MashiroiroSymphonyFHD_Retranslation_Patch` |
