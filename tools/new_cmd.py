#!/usr/bin/env python3
"""`giji new` — 雛形から新しいカードを起こす。

採番は最大値+1。取り下げた番号は欠番のまま残し、再利用しない
（同じ ID が別のものを指すと、過去の議事録が嘘になる）。

既定は標準出力。--write を付けたときだけファイルを作る。
"""

import argparse
import sys

from tools import schema
from tools.cards import Wiki, resolve_root

# 型 -> 雛形ファイル名
TEMPLATE = {"DEC": "dec", "Q": "q", "ACT": "act", "CON": "con",
            "ASM": "asm", "TERM": "term", "LOG": "log"}

ALIAS = {"decision": "DEC", "question": "Q", "action": "ACT", "constraint": "CON",
         "assumption": "ASM", "term": "TERM", "log": "LOG"}


def new_card(wiki, type_name, meeting=None, title=None, index=None):
    """(カード ID, テキスト, 置き場のパス) を返す。ファイルは作らない。"""
    o = wiki.ontology
    path = schema.KIT_ROOT / "templates" / "card" / ("%s.md" % TEMPLATE[type_name])
    text = path.read_text(encoding="utf-8")

    if type_name == "LOG":
        if not meeting:
            raise ValueError("LOG には --meeting が要る")
        used = [o.id_number(c.id) for c in wiki.logs_of(meeting)]
        used = [n for n in used if n is not None]
        number = index if index is not None else (max(used) + 1 if used else 1)
        card_id = "LOG-%s-%02d" % (meeting.split("-")[-1], number)
        text = text.replace("LOG-YYYYMMDD-NN", card_id).replace("MTG-YYYYMMDD", meeting)
        target = wiki.root / o.meetings.get("dir", "meetings") / meeting / \
            o.meetings.get("logs-dir", "logs") / ("%s.md" % card_id)
    else:
        card_id = wiki.next_id(type_name)
        text = text.replace("%s-NNN" % type_name, card_id)
        target = wiki.root / o.dir_of(type_name) / ("%s.md" % card_id)

    if title:
        headline = o.headline_field(type_name)
        placeholder = {
            "title": {"DEC": "決定の内容を一文で", "Q": "何が決まっていないか",
                      "ACT": "誰が何をするか", "LOG": "論点の見出し"},
            "内容": {"CON": "選択肢を削る環境の性質", "ASM": "成り立っていればよい仮定"},
            "正式": {"TERM": "正式表記"},
        }.get(headline, {}).get(type_name)
        if placeholder:
            text = text.replace("%s: %s" % (headline, placeholder),
                                "%s: %s" % (headline, title))
    return card_id, text, target


def main(argv=None):
    ap = argparse.ArgumentParser(prog="giji new", description="雛形から新しいカードを起こす")
    ap.add_argument("type", help="decision | question | action | constraint | assumption | term | log")
    ap.add_argument("--meeting", default=None, help="LOG のときの会議 ID")
    ap.add_argument("--title", default=None, help="見出し")
    ap.add_argument("--write", action="store_true", help="ファイルを作る（既定は標準出力）")
    ap.add_argument("--root", default=None)
    args = ap.parse_args(argv)

    raw = args.type.lower()
    type_name = ALIAS.get(raw, raw.upper())
    if type_name not in TEMPLATE:
        print("未知の型: %s（%s のいずれか）" % (args.type, " / ".join(sorted(ALIAS))),
              file=sys.stderr)
        return 2

    wiki = Wiki(resolve_root(args.root), schema.load())
    meeting = args.meeting
    if type_name == "LOG" and not meeting:
        latest = wiki.latest_meeting()
        meeting = latest.id if latest else None

    try:
        card_id, text, target = new_card(wiki, type_name, meeting, args.title)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2

    if not args.write:
        print(text, end="")
        print("\n<!-- 置き場: %s -->" % target.relative_to(wiki.root), file=sys.stderr)
        return 0

    if target.exists():
        print("既にある: %s" % target, file=sys.stderr)
        return 1
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    print("%s を作った: %s" % (card_id, target.relative_to(wiki.root)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
