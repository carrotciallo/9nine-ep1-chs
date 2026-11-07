# 构建工具

本目录是把官方繁中轨道替换为简中所需的全部构建工具。定位是**汉化构建
工具**：输入为使用者自备的正版游戏文件与樱空原汉化包，输出为补丁包；
仓库不包含任何游戏素材或解密后的官方资源。

| 工具 | 作用 |
|---|---|
| `unpack_momo.py` + `momo_xor1024.bin` | 解包樱空汉化包 momo.bin（XOR-1024，内置本作索引表） |
| `psb_parse.py` | PSB 二进制解析器（按 FreeMote 公开规格独立实现） |
| `build_tc_scn.py` | 剧本重构：官方 scn 繁中块替换为樱空简中，自带结构校验 |
| `krkr_text.py` | Kirikiri TVP 加扰文本编解码（syslangtext、help 等，mode 0/1/2） |
| `xp3pack.py` | XP3 打包库（与 KirikiriTools 的 Xp3Pack 对齐，索引 adlr=0） |
| `make_patch_xp3.py` | 按引擎实际请求名（含 _cn 变体）组装 unencrypted.xp3 |

格式细节见 `docs/formats.md`，完整管线见 `docs/building.md`。
