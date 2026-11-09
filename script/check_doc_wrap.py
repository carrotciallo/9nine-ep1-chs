"""检查文档里的「逻辑行被硬折行」：一句话被拆到两行就报错。

规则（对应 `AGENTS.md` 的「每个逻辑行必须整行输出，禁止按固定字符数自动换行」）：
一行既不是块首（标题/列表/表格/引用/代码围栏/缩进代码），而**上一行又不以句末标点结尾**，
说明上一行的话还没说完就被断行了。

用法（从项目根执行）：

    mamba run -n GalRev python script/check_doc_wrap.py            # 扫描 README.md + doc/*.md
    mamba run -n GalRev python script/check_doc_wrap.py --fix      # 自动并回上一行

退出码：0 = 干净，1 = 有硬折行。
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import sys

# 句末标点：出现这些结尾说明这是一个完整的逻辑行
SENTENCE_END = "。！？：；、，）)」』】》…—~”’\"'`：:;,.!?|"
START = re.compile(r"^(#{1,6} |\| |```|- |\* |> |⇒|[0-9]+[.、] |    )")


def wrapped_lines(text: str) -> list[tuple[int, str, str]]:
    out = []
    in_fence = False
    prev_no = 0
    prev = ""
    for i, line in enumerate(text.replace("\r\n", "\n").split("\n"), 1):
        if line.startswith("```"):
            in_fence = not in_fence
            prev, prev_no = line, i
            continue
        if in_fence or not line.strip():
            prev, prev_no = line, i
            continue
        if not START.match(line) and prev.strip() and not START.match(prev) and prev.rstrip()[-1:] not in SENTENCE_END:
            out.append((i, prev_no, line.strip()))
        prev, prev_no = line, i
    return out


def check(path: str) -> list[tuple[int, str, str]]:
    with open(path, encoding="utf-8") as fp:
        return wrapped_lines(fp.read())


def fix(path: str) -> int:
    with open(path, encoding="utf-8") as fp:
        lines = fp.read().replace("\r\n", "\n").split("\n")
    fixes = {i for i, _, _ in check(path)}
    merged = 0
    for i in sorted(fixes, reverse=True):
        idx = i - 1
        if idx <= 0:
            continue
        joiner = "" if not lines[idx].startswith((" ", "\t")) else " "
        lines[idx - 1] = lines[idx - 1].rstrip() + joiner + lines[idx].strip()
        del lines[idx]
        merged += 1
    if merged:
        with open(path, "w", encoding="utf-8", newline="") as fp:
            fp.write("\n".join(lines).replace("\n", "\r\n"))
    return merged


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", help="默认 README.md + doc/*.md")
    ap.add_argument("--fix", action="store_true", help="自动把断行并回上一行")
    args = ap.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    paths = args.paths or ["README.md"] + sorted(glob.glob(os.path.join("doc", "*.md")))
    problems = 0
    for path in paths:
        found = check(path)
        if not found:
            continue
        if args.fix:
            n = fix(path)
            print(f"{path}: 已并回 {n} 处")
            continue
        problems += len(found)
        for lineno, prev_lineno, text in found:
            print(f"{path}:{lineno}: 上一行（L{prev_lineno}）没说完就断行 -> {text[:60]}")
    if not args.fix:
        print(f"硬折行：{problems} 处")
    return 0 if (args.fix or not problems) else 1


if __name__ == "__main__":
    sys.exit(main())
