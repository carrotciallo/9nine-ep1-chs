# 格式说明

本项目涉及的四种文件格式。均为逆向分析结论，工具实现见 `tools/`。

## 1. PSB / .scn（剧本）

游戏剧本是 PSB 二进制（`PSB` 魔数，v2/v3）。头部依次为版本号与 8 个区段
偏移：名称表、字符串偏移表、字符串数据、chunk 表、入口。字符串池是排序
去重表，条目以「类型字节 + 池索引」引用字符串；列表/对象以偏移数组组织，
同一父列表内完全相同的元素只存一份字节（共享）。

剧本根对象含 `scenes` 数组，每个 scene 有 `texts` 列表，一条 texts 对应
一行正文。Steam 版官方条目的正文槽是三元组 `[语言块索引, …]`，实际结构
为 `[None 占位, ……]` ——准确地说，`texts[i][2]` 是语言块列表：

```
[None, 主文本, 变体…]   # 日 / 英 / 繁中各一块，块内 [None, 主文本, ruby 变体…]
```

樱空版 scn 的 `texts[i][2]` 则是单个简中字符串。`build_tc_scn.py` 的做法：
只替换官方条目的繁中块（全部槽位换成对应樱空简中串），日/英块与其它
字段逐字节保留；繁中块与日文块共享同一元素时（全 17 个文件共 20 处），
把该条目的语言块列表整体重建以解开共享。细节见该脚本头注释。

PSB 解析器 `psb_parse.py` 按 FreeMote 公开的 PSB 规格独立实现。

## 2. TVP 加扰文本（syslangtext / help 等）

Kirikiri 的系统文本（菜单、设置帮助等）以加扰二进制存放：

```
FE FE | mode | FF FE | 正文
```

正文是 UTF-16LE。mode 1（本作使用）对每个 uint16 做偶奇比特对换：

```
ch = ((ch & 0xAAAA) >> 1) | ((ch & 0x5555) << 1)
```

该变换是对合，编解码同一公式。mode 0 是旧式 XOR，mode 2 是 zlib 压缩。
`krkr_text.py` 支持三模式的 decode / encode / roundtrip 校验。

注意：引擎只认加扰二进制形态，明文放进去不生效。代表文件：
`main/syslangtext_<lang>.ini`（菜单与语言名）、`main/help_conf_<lang>.txt`
（设置页帮助文本，按选项名键控）。

语言的显示名也在 syslangtext 里（`textLanguageMenuItem_cn` 等键）。
引擎启用的语言集合由 SystemConfig 的 `multiLangLanguageTags` 定义
（本作是 `["jp", "en", "cn"]`），补丁将 cn 轨道内容整体换为简中后，
把该轨道的显示名改为「简体中文」与内容一致。

## 3. 樱空 momo.bin

樱空汉化包（2017，X'moe-Core）的资源容器。文件索引不在包内，而是
`kokoiro_chs.dll` 运行时文件系统中的一张表：每条 0x30 字节
（宽字符串名 + 偏移 + 大小）。载荷整体与一张 1024 字节表循环 XOR，
该表取自 dll 解包后映像。`unpack_momo.py` 内置了本作的 45 条索引与
密钥表（`momo_xor1024.bin`），可直接解出全部文件（scn、贴图、tjs）。

## 4. XP3 索引与「变体名」

补丁包 `unencrypted.xp3` 的索引 adlr 置 0，配合 version.dll
（KirikiriUnencryptedArchive 系实现）使引擎跳过包内解密。每个文件登记
三份别名：全路径、文件名、`md5(UTF-16LE 编码的全路径)`，与原版
data.xp3 的哈希命名互通。

关键点：Steam 版按当前 UI 语言请求**语言变体名**。例如界面贴图
`uipsd/conf_sys.pimg` 在中文界面下实际请求的是
`uipsd/cn/conf_sys_cn.pimg`；同理 `uipsd/cn/dialog_cn.pimg`（确认弹窗）、
`image/attention_cn.png`（启动警告屏）、`main/help_conf_cn.txt`。
樱空原包只有通用名，直接沿用通用名打包时这些文件永远不会被读到——
补丁自 1.0 起长期「内容在包里但不生效」正是这个原因。打包脚本
`make_patch_xp3.py` 对有变体槽的文件同时登记通用名与 _cn 名。

从正版 `data.xp3` 提取官方文件（scn 等）不在本仓库工具范围内：
GARbro 的公开格式库已收录本作的条目解密方案（"9 -Nine-: Episode 1"），
用它提取即可。
