#!/usr/bin/env python3
"""`kime update` / `kime confirm` — 既存カードの書き換え。

カードと会議は多対多で、同じ論点が複数の会議にまたがって更新されていく。
その更新（`status` の変化、`resolved_by`、`更新履歴`、`derived_from` への LOG 追記）が
すべて手編集だと、回数が増えるほどドリフトする。

**frontmatter を行単位で置き換える。** キーの順序・コメント・空欄をそのまま残すため、
YAML として読み書きし直さない（`tools/quotes.py` の `fix_card` と同じ方針）。

**人が渡した値は、一字も変えずに書くか、書かずに止まる。** `なぜ: #1 は…` は
YAML ではコメントになり、空として読まれる。空になっても lint は why-missing に
戻るだけで、聞き取った言葉が黙って消える。だから値を型に応じて囲み（`render_value`）、
書いた結果を読み戻して渡した値と照合する（`verify`）。囲む規則に漏れがあっても、
照合が止める。
"""

import argparse
import datetime
import difflib
import re
import sys

from tools import links, schema
from tools.cards import Wiki, resolve_root, yaml_scalar
from tools.miniyaml import MiniYamlError, parse_frontmatter_block

KEY = re.compile(r"^(?P<key>[^\s:#][^:]*?)\s*:\s*(?P<value>.*?)\s*$")
LOG_ENTRY = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})\s*:\s*(?P<text>.*?)\s*$")

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
    """`[a, "[[b]]"]` → ["a", "b"]。リンクは剥がす。"""
    v = (value or "").strip()
    if v.startswith("[") and v.endswith("]") and not links.is_link(v):
        v = v[1:-1]
    return [links.unwrap(x.strip().strip("\"'")) for x in v.split(",") if x.strip()]


def _block_items(lines, idx, end):
    """キーの下にぶら下がるブロックシーケンスの行（`  - x`）の終わり。

    Obsidian の Properties で編集すると、配列はブロック形式で書き直される。
    キーの行だけを置き換えると、下の行が取り残されて別の値に化ける。
    """
    tail = idx + 1
    while tail < end and lines[tail][:1].isspace() and lines[tail].strip():
        tail += 1
    return tail


def _split_log(entry):
    """`YYYY-MM-DD: 内容` → (日付, 内容)。`更新履歴` は日付をキーにした行の列なので、
    日付が無いと構造が壊れる。"""
    m = LOG_ENTRY.match(entry.strip())
    if not m or not m.group("text"):
        raise UpdateError("--log は 'YYYY-MM-DD: 内容' の形で渡す: %s" % entry)
    return m.group("date"), m.group("text")


def _parses(text):
    try:
        parse_frontmatter_block(text)
    except MiniYamlError:
        return False
    return True


def apply_updates(text, sets=(), add_derived=(), logs=()):
    """カード本文（文字列）に更新を当てて返す。何も変わらなければ同じ文字列。

    `sets` の値は frontmatter にそのまま書ける形で渡す（人が渡した値は `update_text`
    を通す）。`logs` は `YYYY-MM-DD: 内容` で、内容はここで囲む。
    読めていたカードが読めなくなる書き換えは UpdateError にする。
    """
    lines = text.splitlines()
    start, end = _frontmatter_bounds(lines)

    for key, value in sets:
        idx = _find_key(lines, start, end, key)
        if idx is None:
            raise UpdateError("フィールド `%s` がこのカードに無い" % key)
        tail = _block_items(lines, idx, end)
        lines[idx:tail] = ["%s: %s" % (key, value) if value else "%s:" % key]
        end -= tail - idx - 1

    if add_derived:
        idx = _find_key(lines, start, end, DERIVED)
        if idx is None:
            raise UpdateError("フィールド `%s` がこのカードに無い" % DERIVED)
        tail = _block_items(lines, idx, end)
        m = KEY.match(lines[idx])
        current = _parse_flow_list(m.group("value"))
        current += [links.unwrap(l.strip()[1:].strip().strip("\"'"))
                    for l in lines[idx + 1:tail] if l.strip().startswith("-")]
        added = [r for r in dict.fromkeys(links.unwrap(r) for r in add_derived)
                 if r not in current]
        if added:
            lines[idx:tail] = ["%s: %s" % (DERIVED, links.flow(current + added))]
            end -= tail - idx - 1

    for entry in logs:
        idx = _find_key(lines, start, end, HISTORY)
        if idx is None:
            raise UpdateError("フィールド `%s` がこのカードに無い" % HISTORY)
        tail = idx + 1
        while tail < end and (lines[tail][:1].isspace() or lines[tail].strip() == ""):
            if lines[tail].strip() == "":
                break
            tail += 1
        date, content = _split_log(entry)
        lines.insert(tail, "  - %s: %s" % (date, yaml_scalar(content)))
        end += 1

    out = "\n".join(lines) + "\n"
    if out != text and _parses(text) and not _parses(out):
        raise UpdateError("書くとカードが読めなくなる。書かずに止めた")
    return out


def _split_list(raw):
    """`a, b` / `[a, b]` / `[[A]], [[B]]` → 要素の列。外側の `[ ]` はリンクと区別して剥がす。"""
    items = [x.strip() for x in raw.split(",")]
    if items and items[0].startswith("[") and not links.is_link(items[0]):
        items[0] = items[0][1:].strip()
    if items and items[-1].endswith("]") and not links.is_link(items[-1]):
        items[-1] = items[-1][:-1].strip()
    return [x.strip("\"'") for x in items if x.strip("\"'")]


def render_value(ontology, type_name, key, raw):
    """人が渡した値を (frontmatter に書く形, 読み戻したときに得られるべき値) にする。

    書き方はフィールドの kind（正本は ontology.yaml）で決まる。参照はリンクで、
    文字列の列はフロー形式で、それ以外は1つのスカラーとして囲む。
    """
    if raw == "":
        return "", ""
    kind = ontology.field_specs(type_name).get(key, {}).get("kind")
    linked = dict(links.linked_fields(ontology, type_name))
    if key in linked and kind == "ref-list":
        ids = [links.unwrap(x) for x in _split_list(raw)]
        return links.flow(ids), ["[[%s]]" % i for i in ids]
    if key in linked:
        card_id = links.unwrap(raw.strip("\"'"))
        return links.scalar(card_id), ("[[%s]]" % card_id if card_id else "")
    if kind == "str-list":
        items = _split_list(raw)
        return "[%s]" % ", ".join(yaml_scalar(i) for i in items), items
    if kind == "struct-list":
        raise UpdateError("`%s` は --set では書けない（更新履歴は --log で足す。"
                          "それ以外はカードを直接直す）" % key)
    return yaml_scalar(raw), raw


def verify(text, expected=(), logs=()):
    """書いた結果を読み戻し、渡した値と一字でも違えば UpdateError。

    `expected` は {フィールド: 読み戻したときの値}、`logs` は足した更新履歴の行。
    """
    try:
        data, _ = parse_frontmatter_block(text)
    except MiniYamlError as exc:
        raise UpdateError("書くとカードが読めなくなる（%s）。書かずに止めた" % exc)
    for key, want in dict(expected).items():
        got = data.get(key, "")
        if got != want:
            raise UpdateError("`%s` が %r として読まれる（渡した値: %r）。書かずに止めた"
                              % (key, got, want))
    if logs:
        want = [dict([_split_log(e)]) for e in logs]
        history = data.get(HISTORY) or []
        got = history[-len(want):] if isinstance(history, list) else history
        if got != want:
            raise UpdateError("`%s` が %r として読まれる（渡した値: %r）。書かずに止めた"
                              % (HISTORY, got, want))


def update_text(text, ontology, type_name, sets=(), add_derived=(), logs=()):
    """人が渡した値でカードを書き換え、読み戻して照合してから返す。"""
    rendered, expected = [], {}
    for key, raw in sets:
        value, want = render_value(ontology, type_name, key, raw)
        rendered.append((key, value))
        expected[key] = want
    out = apply_updates(text, rendered, add_derived, logs)
    verify(out, expected, logs)
    return out


def _split_set(raw):
    if "=" not in raw:
        raise UpdateError("--set は key=value の形で渡す: %s" % raw)
    key, _, value = raw.partition("=")
    return key.strip(), value.strip()


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="kime update", description="既存カードのフィールドを書き換える")
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
        after = update_text(before, wiki.ontology, card.type,
                            sets, args.add_derived, args.log)
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
        prog="kime confirm",
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

    days = wiki.ontology.threshold("deemed-confirmation-business-days")
    due = business_days_after(sent, days)

    targets = [c for c in wiki.cards_of_meeting(args.meeting, "DEC")
               if not c.get("確定日") and wiki.is_active(c)]
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
