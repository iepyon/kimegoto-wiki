#!/usr/bin/env python3
"""`kime agenda-sync` — 論点に付いた議題を、議題カードの側に書き戻す。

Pass 1 が `segments.yaml` の論点に `議題` を付けた時点で、その議題を
「その会議で扱った」ことは一意に決まる。だから次の2つは人に書かせない。

- `status: 未着手` → `継続`（扱ったが、決着は人間が決める）
- `予定会議` にその会議が無ければ足す（会議の場で出て、その場で扱った議題）

もう1つ、**持ち越しでアジェンダに載った会議**も `予定会議` に足す。開いた議題は
決着するまで次回のアジェンダに自動で載る（`Wiki.agenda_of`）が、載った会議は
どこにも書かれない。書かないと、その会議で扱えなかったことが消え、2回続けて
扱えなかった議題が「1回前に扱ったが結論なし」に見える（`docs/dryrun-20260923.md` の 1）。
「載っていた」は機械が決めているので、ここも機械が書く。対象は Pass 1 が済んだ
（`segments.yaml` がある）会議で、議題の `提起日` 以降のものに限る。

`決着` / `取り下げ` には触らない。閉じるのは人間（確認②の 2-5）。
lint の `agd-unsynced` は、ここを回し忘れたときの保険として残る。

既定は差分の表示のみ。`--write` を付けたときだけ書く。
"""

import argparse
import sys

from tools import schema
from tools.cards import Wiki, resolve_root
from tools.update_cmd import UpdateError, apply_updates

OPENED = "未着手"
CONTINUED = "継続"


def plan(wiki, meeting_id=None):
    """[(議題カード, [(フィールド, 値), ...], [説明, ...]), ...]。直すものが無い議題は出さない。"""
    closed = set(wiki.ontology.agenda_closed_status())
    on_agenda = _carried_meetings(wiki, meeting_id)
    out = []
    for card in sorted(wiki.by_type("AGD"), key=lambda c: c.id):
        if card.error is not None or card.get("status") in closed:
            continue
        discussed = wiki.discussed_in(card)
        if meeting_id:
            discussed = [m for m in discussed if m == meeting_id]
        sets, notes = [], []
        if discussed and card.get("status") == OPENED:
            sets.append(("status", CONTINUED))
            notes.append("status: %s → %s（%s で扱った）" % (OPENED, CONTINUED, discussed[-1]))
        planned = [m for m in card.list("予定会議") if m]
        missing = [m for m in discussed if m not in planned]
        raised = card.get("提起日") or ""
        skipped = [m for m in on_agenda.get(card.id, [])
                   if m not in planned and m not in missing
                   and wiki.meetings[m].date >= raised]
        if missing or skipped:
            sets.append(("予定会議", "[%s]" % ", ".join(sorted(planned + missing + skipped))))
        if missing:
            notes.append("予定会議に %s を足す（その会議で扱った）" % " / ".join(missing))
        if skipped:
            notes.append("予定会議に %s を足す（持ち越しでアジェンダに載ったが扱えず）"
                         % " / ".join(skipped))
        if sets:
            out.append((card, sets, notes))
    return out


def _carried_meetings(wiki, meeting_id=None):
    """{AGD id: [持ち越しでアジェンダに載った、Pass 1 済みの会議, ...]}。"""
    held = [m for m in sorted(wiki.segments) if m in wiki.meetings]
    if meeting_id:
        held = [m for m in held if m == meeting_id]
    out = {}
    for m in held:
        for card, _ in wiki.agenda_of(m):
            out.setdefault(card.id, []).append(m)
    return out


def _apply(text, sets):
    """`予定会議` の行が無いカードにも書けるようにする（任意フィールドなので省かれうる）。"""
    lines = text.splitlines()
    end = lines.index("---", 1)
    present = {line.split(":", 1)[0].strip() for line in lines[1:end] if ":" in line}
    for key, value in sets:
        if key not in present:
            lines.insert(end, "%s:" % key)
            end += 1
    return apply_updates("\n".join(lines) + "\n", sets=sets)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="kime agenda-sync",
        description="論点に付いた議題を、議題カードの status と予定会議に書き戻す")
    ap.add_argument("--meeting", default=None, help="会議 ID（既定: 全件）")
    ap.add_argument("--write", action="store_true", help="書く（既定は差分の表示）")
    ap.add_argument("--root", default=None)
    args = ap.parse_args(argv)

    wiki = Wiki(resolve_root(args.root), schema.load())
    if args.meeting and args.meeting not in wiki.meetings:
        print("会議が無い: %s" % args.meeting, file=sys.stderr)
        return 2

    rows = plan(wiki, args.meeting)
    if not rows:
        print("書き戻す議題は無い（%s）" % wiki.root)
        return 0
    for card, sets, notes in rows:
        if args.write:
            try:
                text = _apply(card.path.read_text(encoding="utf-8"), sets)
            except (UpdateError, ValueError) as exc:
                print("%s: 書けない（%s）" % (card.id, exc), file=sys.stderr)
                return 1
            card.path.write_text(text, encoding="utf-8")
        for note in notes:
            print("%s %s  %s" % ("更新" if args.write else "差分", card.id, note))
    if not args.write:
        print("\n%d件（--write で書く）" % len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
