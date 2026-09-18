#!/usr/bin/env python3
"""`giji verify-quotes` / `verify_quotes.py` の本体。

検出だけなら lint でも見えるが、**降格の書き戻しはここにしかない**。
運用手順①が「Pass 3 のあとに --fix」で確定しているため、単体で叩ける入口を
残している。lint 側はファイルを一切書き換えない。
"""

import argparse
import sys

from tools import quotes, schema
from tools.cards import Wiki, resolve_root

_LABEL = {
    quotes.OK: "一致",
    quotes.FAIL: "不一致",
    quotes.NO_REF: "参照なし",
    quotes.ALREADY_GUESS: "不一致（既に推測）",
    quotes.FIXED: "推測に降格",
}


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="verify_quotes.py",
        description="llm-wiki の引用を LOG カードと照合する")
    ap.add_argument("--root", default=None, help="案件ディレクトリ（既定: .env の CURRENT_PROJECT）")
    ap.add_argument("--fix", action="store_true",
                    help="一致しない引用の信頼度を「推測」に降格して書き戻す")
    ap.add_argument("--quiet", action="store_true", help="一致したものを表示しない")
    args = ap.parse_args(argv)

    wiki = Wiki(resolve_root(args.root), schema.load())

    if args.fix:
        fixed, issues = quotes.fix(wiki)
    else:
        fixed, issues = 0, quotes.check(wiki)

    by_card = {}
    for issue in issues:
        by_card.setdefault(issue.card.id, []).append(issue)

    unresolved = 0
    for card_id in sorted(by_card):
        items = by_card[card_id]
        shown = [i for i in items if not (args.quiet and i.status == quotes.OK)]
        if not shown:
            continue
        print("%s  (%s)" % (card_id, items[0].card.path))
        for issue in shown:
            print("  %d行目 [%s] %s" % (issue.line, _LABEL.get(issue.status, issue.status), issue.quote))
            if issue.status != quotes.OK:
                print("      %s" % issue.detail)
            if issue.is_problem:
                unresolved += 1
        print()

    total = len(issues)
    ok = sum(1 for i in issues if i.status == quotes.OK)
    print("引用 %d件: 一致 %d / 不一致 %d" % (total, ok, total - ok))
    if fixed:
        print("信頼度を「推測」に降格: %d件" % fixed)
    if unresolved:
        print("未解決の不一致: %d件（--fix で降格できる）" % unresolved)
    else:
        print("未解決の不一致はない")
    return 1 if unresolved else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
