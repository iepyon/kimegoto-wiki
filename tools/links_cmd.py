#!/usr/bin/env python3
"""`kime links` — 参照フィールドを Obsidian のリンク（`"[[ID]]"`）に揃える。

`kime new` / `kime update` はリンクで書くので、ふだんは要らない。人が素の ID で
書いたとき（Obsidian の Properties や手編集）に lint の `ref-unlinked` が拾い、
`--fix` がここで書き直す。値そのものは変えず、書き方だけを変える。

LOG は不変層なので触らない（持つ参照も会議だけで、リンクの対象にならない）。
"""

import argparse
import sys

from tools import links, schema
from tools.cards import Wiki, resolve_root
from tools.update_cmd import UpdateError, apply_updates


def plan(wiki):
    """[(カード, [(フィールド, 書く値), ...]), ...]。リンクで書かれていない参照を持つカードだけ。"""
    out = []
    for card in wiki.cards:
        if card.error is not None or card.type == "LOG" or not card.plain_refs:
            continue
        kinds = dict(links.linked_fields(wiki.ontology, card.type))
        names = list(dict.fromkeys(name for name, _ in card.plain_refs))
        out.append((card, [(n, links.render(kinds[n], card.data[n])) for n in names]))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kime links",
                                 description="参照フィールドを Obsidian のリンクに揃える")
    ap.add_argument("--fix", action="store_true", help="書き直す（既定は一覧だけ）")
    ap.add_argument("--root", default=None)
    args = ap.parse_args(argv)

    wiki = Wiki(resolve_root(args.root), schema.load())
    todo = plan(wiki)
    for card, sets in todo:
        print("%s  %s" % (card.id, " / ".join(name for name, _ in sets)))
        if not args.fix:
            continue
        try:
            text = apply_updates(card.path.read_text(encoding="utf-8"), sets=sets)
        except UpdateError as exc:
            print("  書き直せない: %s" % exc, file=sys.stderr)
            return 1
        card.path.write_text(text, encoding="utf-8")
    if args.fix:
        print("リンクに書き直した: %d枚" % len(todo))
        return 0
    print("リンクになっていない参照を持つカード: %d枚%s"
          % (len(todo), "（--fix で書き直す）" if todo else ""))
    return 1 if todo else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
