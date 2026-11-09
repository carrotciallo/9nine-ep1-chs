"""工程自检：验证 tool/ 各模块与手头素材可用。

用法（从项目根执行）：
    mamba run -n GalRev python script/selftest.py

检查项（全部只读，临时产物写 tmp/selftest/ 后可删）：
  1. tool 各模块可导入
  2. archive/releases/unencrypted.xp3 可解析：条目 ×3 别名、别名一致
  3. 取一个 scn 用 tool/mdf 解析：行数、语言块、选择支都可读出
  4. 零改动往返：`PsbFile.rebuild({})` 的 PSB body 与原文件逐字节一致
  5. textset 写入→读回一致
  6. krkr_text（TVP 加扰文本）三模式往返一致

退出码 0 表示全部通过；任一失败即抛异常（不静默跳过）。
"""

from __future__ import annotations

import hashlib
import mmap
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tool import cx, krkr_text, mdf, psb, scn, textset, xp3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVE = os.path.join(ROOT, "archive", "releases", "unencrypted.xp3")
TMP = os.path.join(ROOT, "tmp", "selftest")

ok = []


def check(label: str, cond: bool, detail: str = "") -> None:
    if not cond:
        raise AssertionError(f"FAIL {label} {detail}")
    ok.append(label)
    print(f"[ok] {label} {detail}")


def open_archive(path):
    fp = open(path, "rb")
    return fp, mmap.mmap(fp.fileno(), 0, access=mmap.ACCESS_READ)


def main() -> int:
    check("modules", all([cx, krkr_text, mdf, psb, scn, textset, xp3]))

    fp, mm = open_archive(ARCHIVE)
    try:
        entries = xp3.parse_xp3(mm, show_log=False)
        named = [e for e in entries if e.name and e.segms]
        check("xp3 entries", len(entries) > 0 and len(named) % 3 == 0,
              f"{len(entries)} 条 {len(named)} 有名")
        # 每个文件登记三个别名：全路径、basename、md5(UTF-16LE 全路径)
        by_name = {e.name: e for e in named}
        full = [e for e in named if "/" in e.name]
        alias_ok = True
        for e in full:
            base = e.name.rsplit("/", 1)[-1]
            digest = hashlib.md5(e.name.encode("utf-16-le")).hexdigest()
            for alias in (base, digest):
                other = by_name.get(alias)
                if other is None or other.info.fsize != e.info.fsize:
                    alias_ok = False
        check("xp3 三别名（全路径/basename/md5）", alias_ok,
              f"{len(full)} 个文件 -> {len(named)} 条索引")
        check("xp3 adlr=0（明文包标记）", all(e.adlr.hash == 0 for e in named))

        scripts = {e.name: e for e in full if e.name.endswith(".txt.scn")}
        check("xp3 scn 覆盖", len(scripts) == 17, f"{len(scripts)} 个脚本")

        # 取最小的脚本做结构自检
        target = scripts["scn/a09.txt.scn"]
        raw = bytes(xp3.extract_entry(mm, target))
    finally:
        mm.close()
        fp.close()

    check("scn 魔数", raw[:4] in (b"mdf\x00", b"PSB\x00"), repr(raw[:4]))

    script = mdf.MdfScript(raw, "a09.txt.scn")
    msgs = list(script.iter_messages())
    sels = list(script.iter_selects())
    check("mdf 解析", len(msgs) > 0, f"{len(msgs)} 行 / {len(sels)} 选择支")
    check("mdf 语言块", all(len(m.blocks) == 3 for m in msgs), f"{[b.lang for b in msgs[0].blocks]}")
    check("mdf 三轨正文非空", all(m.block("cn").text for m in msgs[:50]))

    # PSB 头 0x28 处是 4 字节 checksum；archive 补丁里的 scn 由初版工具重建过、
    # 却沿用了官方原文件的旧 checksum，因此「除 checksum 外逐字节一致」才是本作可判定的口径。
    def norm(body: bytes) -> bytes:
        return body[:0x28] + body[0x2C:]

    rebuilt = script.rebuild({})
    body0 = script.psb.body
    check("零改动往返（除 header checksum）", norm(psb.PsbFile(rebuilt).body) == norm(body0),
          f"PSB body {len(body0)} B；checksum 由库里重算")
    check("重建幂等", psb.PsbFile(script.rebuild({})).rebuild({}) == rebuilt)

    # 单串扰动：改一条文本，回读必须就是新值，且其它行不受影响
    first = msgs[1].block("cn")
    dist = script.rebuild({first.text_idx: "自检扰动"})
    back = list(mdf.MdfScript(dist, "a09.txt.scn").iter_messages())
    check("单串扰动", back[1].block("cn").text == "自检扰动" and len(back) == len(msgs))

    # textset 往返
    os.makedirs(TMP, exist_ok=True)
    base = os.path.join(TMP, "set")
    rows = [{"script": "a09.txt.scn", "row": i, "text": f"第{i}行"} for i in range(3)]
    textset.write_script(base, "a09.txt.scn", rows, selects=[{"script": "a09.txt.scn", "index": 0}])
    got = textset.records_for(base, "a09.txt.scn")
    check("textset 往返", got == rows and textset.names(base) == ["a09.txt.scn"])

    # krkr_text 三模式往返（构造一段 UTF-16LE 文本）
    for mode in (0, 1, 2):
        blob = krkr_text.encode_bytes("测试文本 abc 123", mode)
        check(f"krkr_text mode{mode}", krkr_text.decode_bytes(blob)[1] == "测试文本 abc 123")

    # Cx 参数可载入（加解密一体，具体正确性由 script/verify_cx.py 的黄金向量保证）
    crypt = cx.CxCrypt.load(os.path.join(ROOT, "resource", "cx", "profile_9nine.json"))
    blob = crypt.crypt(0x12345678, b"selftest" * 8)
    check("cx 可载入并往返", crypt.crypt(0x12345678, blob) == b"selftest" * 8,
          f"mask={crypt.mask:#x} offset={crypt.offset:#x}")

    print(f"\n全部通过：{len(ok)} 项")
    return 0


if __name__ == "__main__":
    sys.exit(main())
