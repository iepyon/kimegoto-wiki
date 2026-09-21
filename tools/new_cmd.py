#!/usr/bin/env python3
"""`giji new` — 雛形から新しいカードを起こす。

採番は最大値+1。取り下げた番号は欠番のまま残し、再利用しない
（同じ ID が別のものを指すと、過去の議事録が嘘になる）。

`--from-log` と `--role` を渡すと、**role-mapping と会議メタから一意に定まる
フィールドをここで埋める**（`決定の所在` / `種別` / `会議体` / `担当` / `所在` /
`硬度` / `derived_from` / 日付）。これまで LLM が書いて lint が事後照合していた
部分で、写像としては一意に決まる。解釈の要るフィールド（`なぜ`・却下理由・
`範囲`）は雛形の空欄のまま残す。

既定は標準出力。--write を付けたときだけファイルを作る。
"""

import argparse
import sys

from tools import schema
from tools.cards import Wiki, resolve_root
from tools.derive import derived_fields
from tools.update_cmd import UpdateError, apply_updates

# 型 -> 雛形ファイル名
TEMPLATE = {"DEC": "dec", "Q": "q", "ACT": "act", "CON": "con",
            "ASM": "asm", "TERM": "term", "LOG": "log"}

ALIAS = {"decision": "DEC", "question": "Q", "action": "ACT", "constraint": "CON",
         "assumption": "ASM", "term": "TERM", "log": "LOG"}


def new_card(wiki, type_name, meeting=None, title=None, index=None,
             role="", log="", kind=""):
    """(カード ID, テキスト, 置き場のパス, 注意書き) を返す。ファイルは作らない。"""
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

    fields, notes = derived_fields(wiki, type_name, role=role, log=log,
                                   meeting=meeting or "", kind=kind)
    for name, value in fields.items():
        try:
            text = apply_updates(text, sets=[(name, value)])
        except UpdateError:
            # 雛形にそのフィールドが無い型もある。埋められないだけで異常ではない。
            continue
    return card_id, text, target, notes


def main(argv=None):
    ap = argparse.ArgumentParser(prog="giji new", description="雛形から新しいカードを起こす")
    ap.add_argument("type", help="decision | question | action | constraint | assumption | term | log")
    ap.add_argument("--meeting", default=None, help="会議 ID（--from-log があれば不要）")
    ap.add_argument("--title", default=None, help="見出し")
    ap.add_argument("--from-log", dest="from_log", default=None,
                    help="生成元の LOG id。derived_from と会議・日付を埋める")
    ap.add_argument("--role", default=None,
                    help="結論を述べた役割ラベル。role-mapping から導出フィールドを埋める")
    ap.add_argument("--kind", default=None,
                    help="CON の `種類`（property | expectation）。`硬度` を導出する")
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
    log_id = args.from_log or ""
    if log_id:
        log = wiki.get(log_id)
        if log is None or log.type != "LOG":
            print("LOG が無い: %s" % log_id, file=sys.stderr)
            return 2
        meeting = meeting or log.get("meeting")
    if type_name == "LOG" and not meeting:
        latest = wiki.latest_meeting()
        meeting = latest.id if latest else None

    try:
        card_id, text, target, notes = new_card(
            wiki, type_name, meeting, args.title,
            role=args.role or "", log=log_id, kind=args.kind or "")
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2

    for note in notes:
        print("注意: %s" % note, file=sys.stderr)

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
