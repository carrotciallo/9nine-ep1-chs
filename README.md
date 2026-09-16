# 9-nine-:Episode 1 简中补丁

Steam 版《9-nine-:Episode 1》（九次九日九重色）的汉化补丁。文本基于樱空汉化组 Ver1.0，菜单图换过了，字体是思源黑体。

不换 `nine_kokoiro.exe` 和 `steam_api.dll`。Steam 点开始游戏就行，成就和云存档还能用。

[下载 7z](https://github.com/carrotciallo/9nine-ep1-chs/releases/latest)

## 怎么装

Steam 库里右键游戏 → 管理 → 浏览本地文件。解压后把这三个丢进游戏目录，跟 `nine_kokoiro.exe` 放一起，提示覆盖就覆盖：

- `version.dll`
- `unencrypted.xp3`
- `unencrypted` 文件夹

进游戏如果能选字体，选思源黑体。

Proton / Linux / Deck 要加启动项，写在原有内容前面：

```
WINEDLLOVERRIDES="version=n,b" %command%
```

Windows 不用改这项。

别点「验证游戏文件完整性」，官方文件会把补丁顶掉。自动更新最好改成「仅在启动时更新」。

包里没有 R18 的 `adult.xp3`，有的话自己丢进游戏目录。

卸的时候删掉上面那三个，启动项里的 `WINEDLLOVERRIDES` 也清掉。

文本：樱空汉化组  
字体：[思源黑体](https://github.com/adobe-fonts/source-han-sans)  
`version.dll`：[KirikiriTools](https://github.com/arcusmaximus/KirikiriTools)
