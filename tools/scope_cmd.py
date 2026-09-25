#!/usr/bin/env python3
"""`kime scope-questions` — `スコープ: 判定保留` の決定を、顧客に聞く問いとして出す。

受託開発では、決定が当初のスコープに入っていたかどうかが後の追加請求の根拠になる。
発話に明示が無ければ `スコープ` は `判定保留` のまま残し、**顧客に聞く問いだけ**を出す。
「どの決定を聞くか」「問いの文面」「誰に聞くか」は条件も文面も一意に決まるので、
LLM に書かせない。正本は `ontology.yaml` の `scope-question`。

**カードにはしない。** `スコープ: 判定保留` という決定の状態がそのまま「まだ聞いていない」を
表している。以前はここから Q カードを起票していたが、同じ事実が2箇所（決定の `スコープ` と
Q の `status`）に書かれ、閉じ忘れの lint・`resolved_by` の流用・題名の一致で元の決定を
推定する照合が要った。射影にすれば、2-0 で人が `スコープ` を書いた時点で消える。

同じ写像を、アジェンダの「スコープの確認」節・議事録の未決事項／確認事項・確認② 2-0 が使う。
"""

import argparse
import sys

from tools import schema
from tools.cards import Wiki, resolve_root


def confirm_to(wiki, decision):
    """その問いを誰に聞くか。

    決定を述べた役割が顧客側ならその役割。そうでなければ顧客側で決定権のある
    役割にフォールバックする（スコープの交渉相手は常に顧客側なので、自社側の役割に
    問いを立てても誰も答えられない）。引けなければ空欄で返す。
    """
    o = wiki.ontology
    want = o.scope_question_value("確認先-所属")
    role = decision.get("決定の所在")
    if role and wiki.is_known_role(role):
        if (wiki.role(role) or {}).get("所属") == want:
            return role
    for name, info in wiki.roles.items():
        if info.get("所属") == want and info.get("決定権") == "あり":
            return name
    return ""


def _askable_decisions(wiki, meeting_id=None):
    """スコープを顧客に問う種別の決定。`ontology.yaml` の `when-種別` をそのまま当てる。"""
    want_kinds = wiki.ontology.scope_question_value("when-種別")
    if not isinstance(want_kinds, list):
        want_kinds = [want_kinds]
    pool = (wiki.cards_of_meeting(meeting_id, "DEC") if meeting_id
            else wiki.by_type("DEC"))
    return sorted([c for c in pool
                   if c.error is None
                   and c.get("種別") in want_kinds
                   and wiki.is_open(c)],
                  key=lambda c: c.id)


def pending_scope(wiki):
    """まだ聞いていないことを表す `スコープ` の値（正本は `ontology.yaml` の `scope-question`）。"""
    return wiki.ontology.scope_question_value("when-スコープ")


def pending_decisions(wiki, meeting_id=None):
    """顧客にスコープを聞くべき決定。`ontology.yaml` の条件をそのまま当てる。"""
    want_scope = pending_scope(wiki)
    return [c for c in _askable_decisions(wiki, meeting_id)
            if c.get("スコープ") == want_scope]


TITLE_SLOT = "{headline}"


def question_title(wiki, decision):
    template = wiki.ontology.scope_question_value("title-template")
    return template.replace(TITLE_SLOT, decision.headline(wiki.ontology))


def plan(wiki, meeting_id=None):
    """[(決定, 問いの文面, 確認先), ...]。アジェンダ・議事録・確認②が同じ写像を使う。"""
    return [(c, question_title(wiki, c), confirm_to(wiki, c))
            for c in pending_decisions(wiki, meeting_id)]


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="kime scope-questions",
        description="`スコープ: 判定保留` の決定を、顧客に聞く問いとして一覧する（カードは作らない）")
    ap.add_argument("--meeting", default=None, help="会議 ID（既定: 全件）")
    ap.add_argument("--root", default=None)
    args = ap.parse_args(argv)

    wiki = Wiki(resolve_root(args.root), schema.load())
    if args.meeting and args.meeting not in wiki.meetings:
        print("会議が無い: %s" % args.meeting, file=sys.stderr)
        return 2

    rows = plan(wiki, args.meeting)
    if not rows:
        print("`スコープ: 判定保留` で顧客に聞くべき決定は無い（%s）" % wiki.root)
        return 0
    for decision, title, to in rows:
        print("%s  %s（確認先: %s）" % (decision.id, title, to or "—"))
    print()
    print("%d件。判定したら `kime update DEC-NNN --set スコープ=…` に書く（Q は立てない）。" % len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
