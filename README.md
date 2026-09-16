# 9-nine-:Episode 1 简体中文补丁

适用于 Steam 版《9-nine-:Episode 1》（九次九日九重色，AppID `976390`）。

文本来自樱空汉化组 Ver1.0，UI 图一并替换，字体为思源黑体（简体）。**不替换游戏主程序**，Steam 成就和云存档可继续使用。

## 下载

到 [Releases](https://github.com/carrotciallo/9nine-ep1-chs/releases) 下载 `9nine-ep1-chs.7z`。

## 安装

1. 用 Steam 安装正版游戏。
2. 打开游戏目录（库里右键游戏 → 管理 → 浏览本地文件）。
3. 解压补丁，把文件拷进去，和 `nine_kokoiro.exe` 放在同一层：
   - `version.dll`
   - `unencrypted.xp3`
   - `unencrypted` 文件夹（里面是字体）
4. 若目录里已有同名文件，选覆盖。
5. 不要用其它启动器，仍用 Steam 点「开始游戏」。

### Linux / Steam Deck / Proton

游戏属性 → 启动选项：

```
WINEDLLOVERRIDES="version=n,b" %command%
```

若你本来就有启动项，把这段加在最前面即可，例如：

```
WINEDLLOVERRIDES="version=n,b" 原有内容 %command%
```

Windows 一般不用改启动项。

## 使用

- 进游戏后若设置里能选字体，选 **思源黑体**。
- **不要**点 Steam 的「验证游戏文件完整性」，否则补丁会被官方文件覆盖。
- 自动更新建议设成「仅在启动时更新」，减少被覆盖的机会。

## 包含

- 全话剧本（简体）
- 标题 / 设置 / 存档 / 对话框等 UI 图
- 警告图、帮助文本
- 思源黑体 / 思源宋体（简体）

## 不含

- 不改 `nine_kokoiro.exe`、`steam_api.dll`
- 不含 R18 补丁（`adult.xp3` 请按官方或你现有的方式自行放置）

## 卸载

删掉 `version.dll`、`unencrypted.xp3` 和 `unencrypted` 文件夹，并清空启动选项里的 `WINEDLLOVERRIDES`。

## 致谢

- 文本：樱空汉化组 Ver1.0
- 字体：[Source Han Sans / Serif](https://github.com/adobe-fonts/source-han-sans)（思源黑体 / 思源宋体）简体
- 加载： [KirikiriTools](https://github.com/arcusmaximus/KirikiriTools) `version.dll`
