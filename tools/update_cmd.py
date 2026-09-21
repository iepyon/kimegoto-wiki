#!/usr/bin/env python3
"""`giji update` / `giji confirm` — 既存カードの書き換え。

カードと会議は多対多で、同じ論点が複数の会議にまたがって更新されていく。
その更新（`status` の変化、`resolved_by`、`更新履歴`、`derived_from` への LOG 追記）が
すべて手編集だと、回数が増えるほどドリフトする。

**frontmatter を行単位で置き換える。** キーの順序・コメント・空欄をそのまま残すため、
YAML として読み書きし直さない（`tools/quotes.py` の `fix_card` と同じ方針）。
"""

import argparse
import datetime
import difflib
import re
import sys

from tools import schema
from tools.cards import Wiki, resolve_root

KEY = re.compile(r"^(?P<key>[^\s:#][^:]*?)\s*:\s*(?P<value>.*?)\s*$")

# 追記できるのはこの2つだけ。ほかは --set で置き換える。
DERIVED = "derived_from"
HISTORY = "更新履歴"


class UpdateError(Exception):
    pass


def _frontmatter_bounds(lines):
    if not lines or lines[0].strip() != "---":
        raise UpdateError("frontmatter が無い")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return 1, i
    raise UpdateError("frontmatter が閉じていない")


def _find_key(lines, start, end, key):
    """トップレベルのキーの行番号。ネストした同名キーは拾わない。"""
    for i in range(start, end):
        if lines[i][:1].isspace():
            continue
        m = KEY.match(lines[i])
        if m and m.group("key").strip() == key:
            return i
    return None


def _parse_flow_list(value):
    v = (value or "").strip()
    if v.startswith("[") and v.endswith("]"):
        v = v[1:-1]
    return [x.strip() for x in v.split(",") if x.strip()]


def apply_updates(text, sets=(), add_derived=(), logs=()):
    """カード本文（文字列）に更新を当てて返す。何も変わらなければ同じ文字列。"""
    lines = text.splitlines()
    start, end = _frontmatter_bounds(lines)

    for key, value in sets:
        idx = _find_key(lines, start, end, key)
        if idx is None:
            raise UpdateError("フィールド `%s` がこのカードに無い" % key)
        lines[idx] = "%s: %s" % (key, value) if value else "%s:" % key

    if add_derived:
        idx = _find_key(lines, start, end, DERIVED)
        if idx is None:
            raise UpdateError("フィールド `%s` がこのカードに無い" % DERIVED)
        m = KEY.match(lines[idx])
        current = _parse_flow_list(m.group("value"))
        for ref in add_derived:
            if ref not in current:
                current.append(ref)
        lines[idx] = "%s: [%s]" % (DERIVED, ", ".join(current))

    for entry in logs:
        idx = _find_key(lines, start, end, HISTORY)
        if idx is None:
            raise UpdateError("フィールド `%s` がこのカードに無い" % HISTORY)
        tail = idx + 1
        while tail < end and (lines[tail][:1].isspace() or lines[tail].strip() == ""):
            if lines[tail].strip() == "":
                break
            tail += 1
        lines.insert(tail, "  - %s" % entry)
        end += 1

    return "\n".join(lines) + "\n"


def _split_set(raw):
    if "=" not in raw:
        raise UpdateError("--set は key=value の形で渡す: %s" % raw)
    key, _, value = raw.partition("=")
    return key.strip(), value.strip()


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="giji update", description="既存カードのフィールドを書き換える")
    ap.add_argument("id", help="カード ID（DEC-014 など）")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                    help="トップレベルのフィールドを置き換える（複数可）")
    ap.add_argument("--add-derived", action="append", default=[], metavar="LOG-ID",
                    help="derived_from に LOG を足す（既にあれば何もしない）")
    ap.add_argument("--log", action="append", default=[], metavar="'YYYY-MM-DD: 内容'",
                    help="更新履歴に1行足す（複数可）")
    ap.add_argument("--dry-run", action="store_true", help="書かずに差分だけ出す")
    ap.add_argument("--root", default=None)
    args = ap.parse_args(argv)

    wiki = Wiki(resolve_root(args.root), schema.load())
    card = wiki.get(args.id)
    if card is None:
        print("カード %s が無い" % args.id, file=sys.stderr)
        return 1
    if card.error:
        print("カード %s が読めない: %s" % (args.id, card.error), file=sys.stderr)
        return 1

    try:
        sets = [_split_set(s) for s in args.set]
        before = card.path.read_text(encoding="utf-8")
        after = apply_updates(before, sets, args.add_derived, args.log)
    except UpdateError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if before == after:
        print("%s: 変更なし" % args.id)
        return 0
    if args.dry_run:
        print("--- %s（--dry-run）" % args.id)
        for line in difflib.unified_diff(before.splitlines(), after.splitlines(),
                                         lineterm="", n=1):
            if line.startswith(("---", "+++")):
                continue
            print("  %s" % line)
        return 0
    card.path.write_text(after, encoding="utf-8")
    print("%s を更新した" % args.id)
    return 0


# ------------------------------------------------------------ confirm

def business_days_after(start, days):
    """土日を飛ばして days 営業日後。祝日は見ない（案件ごとに違うため）。"""
    date = start
    while days > 0:
        date += datetime.timedelta(days=1)
        if date.weekday() < 5:
            days -= 1
    return date


def main_confirm(argv=None):
    ap = argparse.ArgumentParser(
        prog="giji confirm",
        description="みなし確定の期限を決定カードの `確定日` に書き戻す")
    ap.add_argument("--meeting", required=True, help="会議 ID")
    ap.add_argument("--sent", required=True, help="議事録を送付した日（YYYY-MM-DD）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--root", default=None)
    args = ap.parse_args(argv)

    wiki = Wiki(resolve_root(args.root), schema.load())
    if args.meeting not in wiki.meetings:
        print("会議 %s が無い" % args.meeting, file=sys.stderr)
        return 1
    try:
        sent = datetime.date.fromisoformat(args.sent)
    except ValueError:
        print("--sent は YYYY-MM-DD で渡す", file=sys.stderr)
        return 1

    days = wiki.ontology.thresholds.get("deemed-confirmation-business-days", 3)
    due = business_days_after(sent, int(days))

    targets = [c for c in wiki.cards_of_meeting(args.meeting, "DEC")
               if not c.get("確定日") and c.get("status") == "決定"]
    if not targets:
        print("対象なし（%s）" % args.meeting)
        return 0

    for card in sorted(targets, key=lambda c: c.id):
        print("%s  確定日: %s" % (card.id, due.isoformat()))
        if args.dry_run:
            continue
        text = apply_updates(card.path.read_text(encoding="utf-8"),
                             [("確定日", due.isoformat())])
        card.path.write_text(text, encoding="utf-8")
    print("%d件%s（送付 %s の %s営業日後）"
          % (len(targets), "（--dry-run）" if args.dry_run else "を更新した",
             sent.isoformat(), days))
    return 0


if __name__ == "__main__":
    sys.exit(main())
