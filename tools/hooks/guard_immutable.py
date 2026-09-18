#!/usr/bin/env python3
"""PreToolUse — 不変層への書き込みを止める。

守るのは2つ。

- `meetings/*/transcript.md` — 観測した生データ。後から書き換えない
- `meetings/*/logs/LOG-*.md` — **すべての引用の照合先**。ここが書き換えられると、
  引用検証が「カードに合うように LOG を直す」ことを許してしまい、機構そのものが
  無意味になる

**境界は「コミット済みかどうか」に置く。** ファイルの存在で判定すると、Pass 2 が
いま生成した未コミットの LOG すら直せなくなる（フックのほうが pre-commit より
厳しいという非対称が生まれる）。生成中は自由に直せて、記録として確定した
（＝コミットした）瞬間から凍る、が正しい。

判定できないとき（リポジトリ外・git が無い・タイムアウト）は**凍結側に倒す**。
"""

import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _bootstrap import KIT_ROOT, is_this_kit  # noqa: E402

IMMUTABLE = [
    re.compile(r"meetings/[^/]+/transcript\.md$"),
    re.compile(r"meetings/[^/]+/logs/LOG-[^/]+\.md$"),
]


def is_immutable(path):
    normalized = path.replace(os.sep, "/")
    return any(p.search(normalized) for p in IMMUTABLE)


def is_committed(path):
    """git が知っているファイルか。判定できなければ True（凍結側）。"""
    try:
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", path],
            cwd=os.path.dirname(path) or ".",
            capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return True
    return result.returncode == 0


def main():
    if not is_this_kit():
        return 0
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0

    tool_input = payload.get("tool_input") or {}
    path = tool_input.get("file_path") or tool_input.get("path") or ""
    if not path or not is_immutable(path):
        return 0

    absolute = path if os.path.isabs(path) else os.path.join(KIT_ROOT, path)
    if not os.path.exists(absolute):
        return 0          # 新規作成は許す（Pass 2 が LOG を生成する）
    if not is_committed(absolute):
        return 0          # 未コミット＝まだ生成中。直してよい

    name = os.path.basename(absolute)
    kind = "文字起こし原本" if name == "transcript.md" else "LOG カード"
    print(
        "%s は不変層です。コミット済みの %s は書き換えられません。\n"
        "\n"
        "LOG はこの会議から生まれるすべての引用の照合先です。ここを直すと、"
        "引用検証が「カードに合わせて記録のほうを変える」ことを許してしまい、"
        "機構そのものが意味を失います。\n"
        "\n"
        "記録の側が誤っていたと判断したなら、人間が直接（フックを介さずに）"
        "直したうえで、その変更を明示的にコミットしてください。"
        % (name, kind), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
