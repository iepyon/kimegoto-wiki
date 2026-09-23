#!/usr/bin/env python3
"""`kime status` — いまどこにいて、次に何をするかを1枚で出す。

会議1回分の処理は Pass 1 → 議題の書き戻し → Pass 2 → Pass 3 →
引用の照合 → lint → 確認② → 議事録 と段が多い。どこまで済んだかはファイルの
有無とカードの中身から一意に決まるので、人に覚えさせず機械が数える。
「いまの会議」も同じ（最新の会議ディレクトリ）。スキルはこれを読んで `--meeting` を
埋めるので、利用者は会議 ID を打たない。

判定は「済んだか」ではなく「残りがあるか」で見る。人間の判断（粒度の確認、
確認②の記入）が済んだかは機械には分からないので、残りの数を見せるだけにして、
「済」とは言わない。
"""

import argparse
import sys

from tools import agenda, agenda_sync_cmd, kimelint, quotes, schema, scope_cmd
from tools.cards import Wiki, resolve_root

FLOW_TYPES = ("DEC", "Q", "ACT", "CON", "ASM")
EXTRACT_KINDS = ("議論", "確認")      # Pass 3 が最低1件を出す論点の種別（欠落ガード）


class Status:
    """1会議分の段ごとの状態。`rows` が表、`todo` が上から順の「残っていること」。"""

    def __init__(self, wiki, meeting_id):
        self.wiki = wiki
        self.meeting_id = meeting_id
        self.rows = []
        self.todo = []
        self._collect()

    def _row(self, stage, state, todo=None):
        self.rows.append((stage, state))
        if todo:
            self.todo.append(todo)

    def _collect(self):
        w, m = self.wiki, self.meeting_id
        meeting = w.meetings[m]

        has_transcript = (meeting.dir / "transcript.md").is_file()
        self._row("文字起こし", "あり" if has_transcript else "無い",
                  None if has_transcript else "meetings/%s/transcript.md を置く" % m)

        entry = w.segments.get(m)
        segments = None
        if entry is None:
            self._row("Pass 1 論点", "未", "Pass 1: 論点に分ける（/segment）")
        elif entry[0] is None:
            self._row("Pass 1 論点", "segments.yaml が読めない（%s）" % entry[2],
                      "segments.yaml を直す")
        else:
            segments = [r for r in (entry[0].get("segments") or []) if isinstance(r, dict)]
            tagged = sum(1 for r in segments if (r.get("議題") or "").strip())
            self._row("Pass 1 論点", "%d論点（議題つき %d）" % (len(segments), tagged))

        if segments is not None:
            plan = agenda_sync_cmd.plan(w, m)
            if plan:
                self._row("議題の書き戻し", "未: %s" % " / ".join(c.id for c, _, _ in plan),
                          "粒度の確認のあと `kime agenda-sync --meeting %s --write`" % m)
            else:
                self._row("議題の書き戻し", "差分なし")

        logs = w.logs_of(m)
        if segments is not None:
            left = len(segments) - len(logs)
            self._row("Pass 2 LOG", "%d / %d" % (len(logs), len(segments)),
                      "Pass 2: LOG を作る（/log-cards）残り %d" % left if left > 0 else None)
        else:
            self._row("Pass 2 LOG", "%d" % len(logs))

        current = w.cards_of_meeting(m, *FLOW_TYPES)
        referenced = set()
        for c in w.by_type(*FLOW_TYPES):
            referenced.update(c.list("derived_from"))
        notes = w.extraction_notes
        targets = [log for log in logs if log.get("種別") in EXTRACT_KINDS]
        remaining = [log.id for log in targets
                     if log.id not in referenced and log.id not in notes]
        waiting = [log.id for log in targets
                   if str((notes.get(log.id) or {}).get("review_required", "")).lower()
                   in ("true", "yes")]
        born = [c for c in current if self._born_in(c)]
        counts = " / ".join("%s %d" % (t, sum(1 for c in born if c.type == t))
                            for t in ("DEC", "Q", "ACT"))
        if not logs:
            self._row("Pass 3 抽出", "—")
        elif remaining:
            self._row("Pass 3 抽出", "%s。残り: %s" % (counts, " / ".join(remaining)),
                      "Pass 3: 抽出（/extract）残り %d 論点" % len(remaining))
        else:
            tail = "（`review_required`: %s）" % " / ".join(waiting) if waiting else ""
            self._row("Pass 3 抽出", "%s。議論・確認の全論点にカードか理由あり%s" % (counts, tail))

        ids = {c.id for c in current}
        issues = [i for i in quotes.check(w) if i.card.id in ids]
        problems = [i for i in issues if i.is_problem]
        ok = sum(1 for i in issues if i.status == quotes.OK)
        self._row("引用の照合", "%d件: 一致 %d / 不一致 %d" % (len(issues), ok, len(problems)),
                  "`kime verify-quotes --fix`（不一致を推測に降格）" if problems else None)

        lint = kimelint.run(w)
        errors = sum(1 for p in lint if p.level == kimelint.ERROR)
        warnings = len(lint) - errors
        self._row("lint", "error %d / warning %d" % (errors, warnings),
                  "`kime lint` の error を 0 にする" if errors else None)

        if not logs:
            return

        pending = scope_cmd.pending_scope(w)
        decisions = [c for c in current if c.type == "DEC"]
        n_scope = sum(1 for c in decisions if c.get("スコープ") == pending)
        n_guess = sum(1 for c in current if c.get("信頼度") == quotes.GUESS)
        n_why = sum(1 for c in decisions if not c.get("なぜ"))
        open_acts = [c for c in w.by_type("ACT") if c.error is None and agenda.is_open_action(c)]
        n_blank = sum(1 for c in open_acts if not c.get("担当") or not c.get("期限"))
        n_agd = len(self.agenda_items())
        left = n_scope + n_guess + n_why + n_blank + n_agd
        self._row("確認②", "スコープの判定保留 %d / 推測 %d / なぜ未記入 %d / 担当・期限の空欄 %d / 開いた議題 %d"
                  % (n_scope, n_guess, n_why, n_blank, n_agd),
                  "確認②を進める（/review）— 該当 %d件。人が判定する" % left if left
                  else "確認②で見るものは無い。議事録を出す（/minutes）")

        unconfirmed = [c.id for c in decisions if not c.get("確定日")]
        self._row("議事録", "確定日が未記入の決定 %d" % len(unconfirmed)
                  + ("（送付して異議が無ければ `kime confirm --meeting %s --sent YYYY-MM-DD`）" % m
                     if unconfirmed else ""))

    def _born_in(self, card):
        """この会議で起票されたか（`derived_from` の最初の LOG がこの会議のもの）。"""
        for ref in card.list("derived_from"):
            log = self.wiki.get(ref)
            if log is not None and log.type == "LOG":
                return log.get("meeting") == self.meeting_id
        return False

    def agenda_items(self):
        """確認② 2-5 と同じ選び方。この会議に載った／扱った／子が生えた議題。"""
        w, m = self.wiki, self.meeting_id
        current = set(w.cards_of_meeting(m, *FLOW_TYPES))
        return [item for item in agenda.agenda_items(w, m)
                if m in item.card.list("予定会議")
                or m in w.discussed_in(item.card)
                or any(x in current for x in w.children_of(item.card))]

    @property
    def next_step(self):
        return self.todo[0] if self.todo else ""


def next_agenda_line(wiki):
    """次回アジェンダの見出し行。中身は `kime agenda-input`。"""
    items = agenda.agenda_items(wiki)
    carried = sum(1 for item in items if item.carried)
    why_missing = [c for c in wiki.by_type("DEC")
                   if c.error is None and c.get("status") != "覆された" and not c.get("なぜ")]
    acts = [c for c in wiki.by_type("ACT") if c.error is None and agenda.is_open_action(c)]
    return ("議題 %d（持ち越し %d）/ `なぜ` が未記入の決定 %d / 未完了アクション %d"
            % (len(items), carried, len(why_missing), len(acts)))


def render(wiki, meeting_id=None):
    out = ["# いまの状態 — %s" % wiki.root.name, ""]
    label = "指定の会議"
    if meeting_id is None:
        latest = wiki.latest_meeting()
        meeting_id = latest.id if latest else None
        label = "最新の会議ディレクトリ"
    if meeting_id is None:
        out += ["会議が1つも無い。`meetings/MTG-YYYYMMDD/transcript.md` を置くと取り込める。", ""]
    else:
        status = Status(wiki, meeting_id)
        out += ["いまの会議: %s（%s）" % (meeting_id, label), ""]
        out += ["| 段 | 状態 |", "|---|---|"]
        out += ["| %s | %s |" % row for row in status.rows]
        out.append("")
        if status.next_step:
            out += ["**次にやること: %s**" % status.next_step, ""]
        if len(status.todo) > 1:
            out += ["その先: %s" % " → ".join(status.todo[1:]), ""]
    out += ["次回アジェンダ: %s → `kime agenda-input`" % next_agenda_line(wiki), ""]
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kime status",
                                 description="いまの会議の進み具合と、次にやることを出す")
    ap.add_argument("--meeting", default=None, help="会議 ID（既定: 最新）")
    ap.add_argument("--id", action="store_true", help="いまの会議の ID だけを出す（スキル用）")
    ap.add_argument("--root", default=None)
    args = ap.parse_args(argv)

    wiki = Wiki(resolve_root(args.root), schema.load())
    if args.meeting and args.meeting not in wiki.meetings:
        print("会議が無い: %s" % args.meeting, file=sys.stderr)
        return 2
    if args.id:
        meeting = wiki.meetings.get(args.meeting) if args.meeting else wiki.latest_meeting()
        if meeting is None:
            print("会議が1つも無い", file=sys.stderr)
            return 2
        print(meeting.id)
        return 0
    print(render(wiki, args.meeting), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
