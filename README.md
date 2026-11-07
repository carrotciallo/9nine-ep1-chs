# 9-nine-:Episode 1 简中补丁

Steam 版《9-nine-:Episode 1》（九次九日九重色）的简体中文补丁。

[![Release](https://img.shields.io/github/v/release/carrotciallo/9nine-ep1-chs)](https://github.com/carrotciallo/9nine-ep1-chs/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/carrotciallo/9nine-ep1-chs/total)](https://github.com/carrotciallo/9nine-ep1-chs/releases)

- 文本基于樱空汉化组 Ver1.0，菜单图已汉化，字体为思源黑体
- 不替换 `nine_kokoiro.exe` 和 `steam_api.dll`，从 Steam 正常启动，成就和云存档照常可用

## 下载

**[⬇ 下载 v1.1.0（7z，约 86 MB）](https://github.com/carrotciallo/9nine-ep1-chs/releases/download/v1.1.0/9nine-ep1-chs-v1.1.0.7z)**

历史版本见 [Releases](https://github.com/carrotciallo/9nine-ep1-chs/releases)。

## 安装

1. 在 Steam 库里右键游戏 →「管理」→「浏览本地文件」，打开游戏目录。
2. 解压下载的 7z，把里面三项直接放进游戏目录，和 `nine_kokoiro.exe` 放在同一层，提示覆盖时选覆盖：
   - `version.dll`
   - `unencrypted.xp3`
   - `unencrypted` 文件夹
3. 从 Steam 启动游戏。游戏里能选字体时，选思源黑体。

### Linux / Steam Deck（Proton）

在游戏的启动选项里，把下面这行加在原有内容的最前面（Windows 不用加）：

```
WINEDLLOVERRIDES="version=n,b" %command%
```

## 注意事项

- 别对游戏点「验证游戏文件完整性」，Steam 会把补丁文件顶回官方原版；真点了，重新按上面步骤拷一遍即可。
- 自动更新建议改成「仅在启动时更新」，避免更新把补丁覆盖掉。
- 补丁不包含 R18 的 `adult.xp3`，已有这个文件的自己放进游戏目录。

## 卸载

删掉装进去的三项（`version.dll`、`unencrypted.xp3`、`unencrypted` 文件夹），Proton 用户再把启动选项里的 `WINEDLLOVERRIDES` 清掉。

## 常见问题

**点开始游戏没反应，或报错缺 `VCRUNTIME140.dll` / `MSVCP140.dll`？**
这是 1.0 版的问题：旧版 `version.dll` 需要微软 VC++ 运行库，系统里没装就起不来。更新到 v1.1.0 即可（1.1 起不再需要运行库）；暂时不想更新的话，装一下 [VC++ 2015–2022 运行库（x86 版）](https://aka.ms/vs/17/release/vc_redist.x86.exe) 再开游戏，注意要 x86 版。

**装完进游戏还是日文？**
先看三项是不是和 `nine_kokoiro.exe` 在同一层目录，放进子文件夹不会生效；Linux / Deck 再检查启动选项有没有加对。

**游戏更新后汉化没了？**
更新覆盖了补丁文件，重新解压拷一遍三项就行，存档不受影响。

**`version.dll` 被杀毒软件隔离了？**
这个 DLL 没有数字签名，个别杀软会误报。先核对它的 SHA-256，对得上就从杀软的隔离区恢复，并把游戏目录加入白名单：

```
09d19ed2c5f472a7aaef893f7380ba44b65ea5d8bf416d67b65c100446d55270
```

## 更新日志

### v1.1.0

- 换了新的 `version.dll`：不再依赖微软 VC++ 运行库，没装运行库的电脑也能直接启动（1.0 最常见的起不来就是这个）。
- 修复繁体中文轨道的字体：繁中轨之前用不上补丁自带的思源简中、会掉回系统繁体字体，现在会正确加载简体思源。
- 剧本内容与 1.0 相同（三条语言轨仍都显示简体中文），设置页仍是官方繁体。这两处放到 v1.2：剧本改为只覆盖繁中轨（日/英轨恢复官方原文）、设置页简体化。

## 来源

| 内容 | 出处 |
| --- | --- |
| 汉化文本 | 樱空汉化组 Ver1.0 |
| 字体 | [思源黑体](https://github.com/adobe-fonts/source-han-sans) |
| `version.dll` | [KirikiriTools](https://github.com/arcusmaximus/KirikiriTools) |

## 免责声明

非官方补丁，与游戏开发商、发行商无关。游戏本体请自行在 Steam 购买。汉化文本版权归原汉化组所有，如有侵权请联系删除。

## 构建工具

本仓库同时提供从头构建本补丁的工具与格式文档（`tools/`、`docs/`）：
剧本重构、系统文本编解码、樱空汉化包解包与打包脚本。需要自备正版游戏
文件与樱空原汉化包，仓库不包含游戏素材。管线说明见 `docs/building.md`。
