#!/usr/bin/env python3
"""ACT から GitHub Issue の下書きを作る。

**既定は本文を出すところまで。起票は --create を明示したときだけ。**

理由は2つ。

1. ACT は「会社間の約束」の記録で、Issue は自社のタスク管理。粒度も寿命も違う。
   全 ACT が自動で起票されると Issue のほうが壊れる。どれを起票するかは人が選ぶ。

2. ただし二重起票は事故になるので、そこは機械が防ぐ。起票済みの ACT は
   `issue` フィールドを持ち、再実行しても飛ばされる。

使い方:
    kime issue --act ACT-008                      # 本文と gh コマンドを出すだけ
    kime issue --all-open --repo owner/repo       # 未完了のもの全部（起票はしない）
    kime issue --act ACT-008 --repo owner/repo --create
"""

import argparse
import re
import subprocess
import sys

from tools import schema
from tools.cards import Wiki, resolve_root

ISSUE_LINE = re.compile(r"^(?P<indent>\s*)issue\s*[:：]\s*(?P<value>.*?)\s*$")


def render(wiki, card):
    """Issue 本文。由来を必ず入れて、カードへ戻れるようにする。"""
    o = wiki.ontology
    logs = [wiki.get(r) for r in card.list("derived_from")]
    logs = [l for l in logs if l is not None and l.type == "LOG"]
    related = [wiki.get(r) for r in card.list("関連")]
    related = [c for c in related if c is not None]

    out = ["## 背景", ""]
    if related:
        for c in related:
            out.append("- %s %s" % (c.id, c.headline(o)))
            if c.type == "DEC" and c.get("なぜ"):
                out.append("  - なぜ: %s" % c.get("なぜ"))
    else:
        out.append("（関連するカードの記録なし）")
    out.append("")

    for log in logs:
        out.append("この約束が出た論点: %s %s" % (log.id, log.headline(o)))
        out.append("")

    out.append("## やること")
    out.append("")
    out.append(card.headline(o))
    out.append("")

    out.append("## 完了条件")
    out.append("")
    if card.get("引用"):
        out.append("> %s" % card.get("引用"))
        out.append("")
    if card.get("期限"):
        out.append("- 期限: %s" % card.get("期限"))
    if card.get("担当"):
        out.append("- 担当: %s" % card.get("担当"))
    out.append("")

    out.append("---")
    out.append("")
    out.append("出典: %s" % " / ".join(
        [card.id] + [c.id for c in related] + [l.id for l in logs] + wiki.meetings_of(card)))
    return "\n".join(out).rstrip() + "\n"


def title(wiki, card):
    return card.headline(wiki.ontology)


def write_back(card, value):
    """ACT の `issue` に URL / 参照を書き戻す。行単位で、他を壊さない。"""
    lines = card.path.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        m = ISSUE_LINE.match(line)
        if m:
            lines[i] = "%sissue: %s" % (m.group("indent"), value)
            card.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return True
    # フィールドが無ければ frontmatter の末尾に足す。
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            lines.insert(i, "issue: %s" % value)
            card.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return True
    return False


def targets(wiki, ids=None, all_open=False):
    cards = [c for c in wiki.by_type("ACT") if c.error is None]
    if ids:
        by_id = {c.id: c for c in cards}
        missing = [i for i in ids if i not in by_id]
        if missing:
            raise KeyError("存在しない ACT: %s" % ", ".join(missing))
        return [by_id[i] for i in ids]
    if all_open:
        return [c for c in cards if wiki.is_open(c)]
    return []


def create(repo, heading, body):
    """gh issue create を呼ぶ。戻り値は URL。"""
    result = subprocess.run(
        ["gh", "issue", "create", "--repo", repo, "--title", heading, "--body", body],
        capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "gh issue create に失敗した")
    return result.stdout.strip().splitlines()[-1]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kime issue",
                                 description="ACT から GitHub Issue の下書きを作る")
    ap.add_argument("--act", action="append", default=[], help="対象の ACT（複数可）")
    ap.add_argument("--all-open", action="store_true", help="未完了の ACT すべて")
    ap.add_argument("--repo", default=None, help="owner/repo")
    ap.add_argument("--create", action="store_true", help="gh issue create を実行する")
    ap.add_argument("--root", default=None)
    args = ap.parse_args(argv)

    wiki = Wiki(resolve_root(args.root), schema.load())
    try:
        cards = targets(wiki, args.act, args.all_open)
    except KeyError as exc:
        print(exc, file=sys.stderr)
        return 2

    if not cards:
        print("対象がない（--act か --all-open を指定する）", file=sys.stderr)
        return 2
    if args.create and not args.repo:
        print("--create には --repo が要る", file=sys.stderr)
        return 2

    created = skipped = 0
    for card in cards:
        if card.get("issue"):
            print("%s: 起票済み（%s）。飛ばす" % (card.id, card.get("issue")))
            skipped += 1
            continue
        heading, body = title(wiki, card), render(wiki, card)
        print("=" * 60)
        print("%s  %s" % (card.id, heading))
        print("=" * 60)
        print(body)
        if not args.create:
            repo = args.repo or "<owner/repo>"
            print("起票するなら:")
            print("  gh issue create --repo %s --title %s --body-file -"
                  % (repo, _quote(heading)))
            print()
            continue
        try:
            url = create(args.repo, heading, body)
        except RuntimeError as exc:
            print("%s: 起票に失敗した — %s" % (card.id, exc), file=sys.stderr)
            return 1
        write_back(card, url)
        print("起票した: %s → %s" % (card.id, url))
        created += 1

    print("対象 %d件 / 起票 %d件 / 起票済みで飛ばした %d件" % (len(cards), created, skipped))
    if not args.create:
        print("（--create を付けるまで何も起票しない）")
    return 0


def _quote(text):
    return "'%s'" % text.replace("'", "'\\''")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
