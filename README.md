# 9-nine-:Episode 1 简中补丁

Steam 版《9-nine-:Episode 1》（九次九日九重色）。

剧本用的是樱空汉化组 Ver1.0，菜单图也换过了，字体是思源黑体。从 Steam 启动就行，成就和云存档还能用。

[点这里下 7z](https://github.com/carrotciallo/9nine-ep1-chs/releases/latest)

## 怎么装

Steam 装好正版，右键游戏 → 管理 → 浏览本地文件。把补丁解压进去，跟 `nine_kokoiro.exe` 放一起：

- `version.dll`
- `unencrypted.xp3`
- `unencrypted`（字体）

有同名的就覆盖。别用别的 exe 开，点 Steam 的开始游戏。

Proton / Linux / Deck 要加启动项，写在原有内容前面：

```
WINEDLLOVERRIDES="version=n,b" %command%
```

Windows 不用改这项。

进游戏如果能选字体，选思源黑体。别点「验证游戏文件完整性」，官方文件会把补丁顶掉。自动更新最好改成「仅在启动时更新」。

R18 的 `adult.xp3` 这个包里没有，有的话自己丢进游戏目录。

卸的时候删掉上面那三个，启动项里的 `WINEDLLOVERRIDES` 也清掉。

文本是樱空汉化组的。字体是 [思源黑体 / 思源宋体](https://github.com/adobe-fonts/source-han-sans)。`version.dll` 来自 [KirikiriTools](https://github.com/arcusmaximus/KirikiriTools)。
