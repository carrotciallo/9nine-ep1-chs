# 构建管线

从两份原始材料从头构建补丁 `unencrypted.xp3`。全过程只需要 Python 3。

## 前置材料（自备，仓库不提供）

- 正版 Steam 版《9-nine-:Episode 1》游戏文件（提供官方 scn 与字体登记表）
- 樱空汉化组原汉化包（提供简中译文与贴图素材；译文与素材的权利归原作者）
- [GARbro](https://github.com/morkt/GARbro)（从正版 data.xp3 提取官方文件）

## 步骤

1. **解包樱空素材**
   `python3 tools/unpack_momo.py momo.bin -o sakura/`
   得到 45 个文件：17 个 scn、20 张 pimg 贴图、attention 图、帮助文本等。

2. **提取官方 scn**
   用 GARbro 打开正版 `data.xp3`，导出 `scn/` 下 17 个 `aXX.txt.scn`，
   改名为 `official/a01.scn … a17.scn`。

3. **重构剧本**
   `python3 tools/build_tc_scn.py --official official/ --sakura sakura/ --out build-scn/`
   把官方 scn 的繁中块换成樱空简中（日/英块原样保留）。脚本自带结构校验：
   非目标字段逐值不变、繁中槽全部对齐樱空、chunk 尾逐字节相同，不过不写出。

4. **准备简中系统文本**
   - `syslangtext`：以官方 `main/syslangtext_cn.ini` 为骨架（键名、结构、
     换行不动），值替换为简中译文，语言名键 `textLanguageMenuItem_cn` /
     `subLanguageMenuItem_cn` 改为「简体中文」；用
     `python3 tools/krkr_text.py encode` 编回加扰二进制。
     转换前先 `roundtrip` 子命令验证官方原文件可无损往返。
   - `help_conf`：官方 `main/help_conf_cn.txt` 同法解码、转简中，保留
     UTF-8 文本稿即可，打包时由打包脚本编码。

5. **准备字体目录**（`fonts/`）
   - `embfontlist.tjs`：官方原版登记表（从正版文件提取，不要用改过的）。
   - 思源黑体/宋体共 5 个文件：取简中版字体文件，把内部字体名中的
     `SansCN`/`SerifCN` 等长字节替换为 `SansTC`/`SerifTC`，改名成
     `sourcehansanstc-*.otf` 等 TC 文件名——引擎按繁中名找字体、按简中
     内容渲染。另附字体许可证文件。

6. **打包**
   `python3 tools/make_patch_xp3.py --sakura sakura/ --scn build-scn/ --fonts fonts/ --ini syslangtext_cn.chs.ini --help-text help_conf_cn.chs.txt --out unencrypted.xp3`

发行包 = 本 xp3 + `unencrypted/` 字体散文件夹 + version.dll
（KirikiriUnencryptedArchive 的静态链接重编版，不依赖 VC++ 运行库）
+ 一键安装脚本，见 Release 说明。
