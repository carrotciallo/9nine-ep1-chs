"""9-nine-:Episode 1 简中补丁：长期复用库。

模块清单（纯标准库，无第三方依赖）：

- xp3:        普通 xp3 归档读写（索引/条目/段、adler32、TVP 文本打散 FE FE）
- cx:         本作的 Cx 加密层（XOR 对称，可读可写；参数在 resource/cx/profile_9nine.json）
- psb:        PSB v3 对象图读取与字符串池级重写（零改动往返逐字节一致）
- scn:        MDF 剧情脚本（.scn = `mdf\\0` + u32 + zlib + PSB）的文本模型
- textset:    按脚本分片的文本集存储（resource/<set>/scripts/<script>.jsonl）
- krkr_text:  Kirikiri TVP 加扰文本编解码（syslangtext / help 等，mode 0/1/2）

来源：xp3/psb/scn 来自本机知识库 `../../../../GalRevserse/GalRev/galrev/krkr/`（2026-11-08 复制；
引擎级结论改动需两边同步）；`cx.py` 依据 GARbro 的 `KiriKiriCx.cs` 独立移植（与 GARbro 逐字节一致）；
textset 来自纯白交响曲 FHD 移植项目；krkr_text 来自 `archive/tools/krkr_text.py`（初版补丁作者）。

本作是 **Cx 变体**（不是 Hxv4），因此没有把 galrev 的 hxv4/hxv4_write/hxv4hash 带进来。
"""
