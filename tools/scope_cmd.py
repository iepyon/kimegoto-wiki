#!/usr/bin/env python3
"""`kime scope-questions` — `範囲: 判定保留` の決定に対する定型の問いを起票する。

受託開発では、決定が当初の合意範囲に入っていたかどうかが後の追加請求の根拠になる。
発話に明示が無ければ `範囲` は `判定保留` のまま残し、**顧客に聞く問いだけ**を Q に
起こす。この「どの決定に問いを立てるか」「その問いの題名」「誰に聞くか」は
条件も文面も一意に決まるので、LLM に書かせない。

起票の条件と題名の正本は `ontology.yaml` の `scope-question`。
lint の `scope-pending-q` は、ここを回し忘れたときの保険として残る。

範囲の問いには `議題` を写さない。範囲は契約の問いで、議題を決めるための材料では
ない。写すと `範囲: 判定保留` の決定を1つでも含む議題が、確認②の 2-5 で必ず
「継続」の目安になり、決着させると `agd-closed-open` が鳴る。

確認② の 2-0 で人間が `範囲` を判定したら、その決定の範囲の問いは答えが出ている。
閉じるのも一意に決まるので、ここで閉じる（`status: 解決` / `resolved_by: <その決定>`）。

既定は下書きの表示のみ。`--write` を付けたときだけカードを作り、問いを閉じる。
"""

import argparse
import sys

from tools import schema
from tools.cards import Wiki, resolve_root
from tools.new_cmd import new_card
from tools.update_cmd import apply_updates


def _confirm_to(wiki, decision):
    """その問いを誰に聞くか。

    決定を述べた役割が顧客側ならその役割。そうでなければ顧客側で決定権のある
    役割にフォールバックする（範囲の交渉相手は常に顧客側なので、自社側の役割に
    問いを立てても誰も答えられない）。引けなければ空欄で返す。
    """
    o = wiki.ontology
    want = (o.scope_question or {}).get("確認先-所属", "顧客側")
    role = decision.get("決定の所在")
    if role and wiki.is_known_role(role):
        if (wiki.role(role) or {}).get("所属") == want:
            return role
    for name, info in wiki.roles.items():
        if info.get("所属") == want and info.get("決定権") == "あり":
            return name
    return ""


def _askable_decisions(wiki, meeting_id=None):
    """範囲を顧客に問う種別の決定。`ontology.yaml` の `when-種別` をそのまま当てる。"""
    spec = wiki.ontology.scope_question or {}
    want_kinds = spec.get("when-種別", [])
    if not isinstance(want_kinds, list):
        want_kinds = [want_kinds]
    pool = (wiki.cards_of_meeting(meeting_id, "DEC") if meeting_id
            else wiki.by_type("DEC"))
    return sorted([c for c in pool
                   if c.error is None
                   and c.get("種別") in want_kinds
                   and c.get("status") not in ("覆された", "取り下げ")],
                  key=lambda c: c.id)


def _pending_scope(wiki):
    return (wiki.ontology.scope_question or {}).get("when-範囲", "判定保留")


def pending_decisions(wiki, meeting_id=None):
    """問いを立てるべき決定。`ontology.yaml` の条件をそのまま当てる。"""
    want_scope = _pending_scope(wiki)
    return [c for c in _askable_decisions(wiki, meeting_id)
            if c.get("範囲") == want_scope]


TITLE_SLOT = "{headline}"


def _template(wiki):
    return (wiki.ontology.scope_question or {}).get(
        "title-template", "%sは当初合意範囲内か" % TITLE_SLOT)


def question_title(wiki, decision):
    return _template(wiki).replace(TITLE_SLOT, decision.headline(wiki.ontology))


def _matches(wiki, decision):
    """(題名が完全一致する問い or None, 接尾辞と LOG だけが合う問いの一覧)。"""
    wanted = question_title(wiki, decision)
    suffix = _template(wiki).split(TITLE_SLOT)[-1]
    logs = {r for r in decision.list("derived_from")
            if wiki.ontology.type_of_id(r) == "LOG"}
    exact, loose = None, []
    for card in sorted(wiki.by_type("Q"), key=lambda c: c.id):
        if card.error is not None:
            continue
        title = card.get("title") or ""
        if title == wanted:
            exact = exact or card
            continue
        if suffix and not title.endswith(suffix):
            continue
        if logs & set(card.list("derived_from")):
            loose.append(card)
    return exact, loose


def _existing(wiki, decision):
    """この決定に対する範囲の問いが既にあるか。

    題名の完全一致では見つからない。人間は決定の見出しを縮めて書くことがあり
    （「検索の権限は部署単位に丸め、…対象外とする」→「検索の権限は部署単位に
    丸める」）、そこで取りこぼすと `--write` が二重起票する。
    **定型の接尾辞と、同じ LOG から生えていること**の2つで照合する。
    """
    exact, loose = _matches(wiki, decision)
    # 1つの LOG から複数の決定が生えることがあるので、LOG の一致だけでは
    # 決め手にならない。完全一致が見つからなかったときの控えにとどめる。
    return exact or (loose[0] if loose else None)


def _owned(wiki, decision):
    """この決定の範囲の問いだと**言い切れる**もの。閉じるときに使う。

    起票の重複を避けるだけなら控え（接尾辞と LOG の一致）で足りるが、閉じるときに
    取り違えると、別の決定の範囲の問いが答えの無いまま消える。控えで見つかったものは、
    候補が1つだけで、かつ別の決定の定型の題名と一致しないときに限る。
    """
    exact, loose = _matches(wiki, decision)
    if exact is not None:
        return exact
    if len(loose) != 1:
        return None
    other_titles = {question_title(wiki, d) for d in wiki.by_type("DEC")
                    if d.error is None and d.id != decision.id}
    return None if loose[0].get("title") in other_titles else loose[0]


def closable(wiki, meeting_id=None):
    """範囲が判定済みなのに、範囲の問いが開いたままの決定。[(決定, 問い), ...]。"""
    out = []
    pending = _pending_scope(wiki)
    for decision in _askable_decisions(wiki, meeting_id):
        if decision.get("範囲") in ("", pending):
            continue
        question = _owned(wiki, decision)
        if question is not None and question.get("status") == "未決":
            out.append((decision, question))
    return out


def plan(wiki, meeting_id=None):
    """[(決定, 問いの題名, 既存の Q or None, 確認先), ...]。"""
    out = []
    for decision in pending_decisions(wiki, meeting_id):
        out.append((decision, question_title(wiki, decision),
                    _existing(wiki, decision), _confirm_to(wiki, decision)))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="kime scope-questions",
        description="`範囲: 判定保留` の決定に対する定型の問いを起票する")
    ap.add_argument("--meeting", default=None, help="会議 ID（既定: 全件）")
    ap.add_argument("--write", action="store_true", help="カードを作る（既定は下書きの表示）")
    ap.add_argument("--root", default=None)
    args = ap.parse_args(argv)

    wiki = Wiki(resolve_root(args.root), schema.load())
    if args.meeting and args.meeting not in wiki.meetings:
        print("会議が無い: %s" % args.meeting, file=sys.stderr)
        return 2

    rows = plan(wiki, args.meeting)
    to_close = closable(wiki, args.meeting)
    if not rows and not to_close:
        print("`範囲: 判定保留` で問いを立てるべき決定も、閉じるべき範囲の問いも無い（%s）"
              % wiki.root)
        return 0

    closed = 0
    for decision, question in to_close:
        verb = "閉じた" if args.write else "閉"
        print("%s  %s → %s（範囲: %s）" % (verb, decision.id, question.id, decision.get("範囲")))
        if args.write:
            text = apply_updates(question.path.read_text(encoding="utf-8"),
                                 sets=[("status", "解決"), ("resolved_by", decision.id)])
            question.path.write_text(text, encoding="utf-8")
        closed += 1

    created, skipped = 0, 0
    for decision, title, existing, confirm_to in rows:
        if existing is not None:
            print("済  %s → %s（%s）" % (decision.id, existing.id, title))
            skipped += 1
            continue
        if not args.write:
            print("新  %s → %s（確認先: %s）" % (decision.id, title, confirm_to or "—"))
            created += 1
            continue
        log = next((r for r in decision.list("derived_from")
                    if wiki.ontology.type_of_id(r) == "LOG"), "")
        log_card = wiki.get(log) if log else None
        meeting = log_card.get("meeting") if log_card is not None else ""
        card_id, text, target, notes = new_card(
            wiki, "Q", meeting=meeting, title=title, role=confirm_to, log=log)
        # 引用は決定のものをそのまま写す。この問いは「その決定が成立したこと」を
        # 根拠に立つので、照合先も決定と同じ発話になる。新しい引用は作らない。
        carried = [(name, decision.get(name))
                   for name in ("引用", "信頼度") if decision.get(name)]
        # 論点から写った `議題` は外す（範囲は議題を決める材料ではない。冒頭の説明）。
        carried.append(("議題", ""))
        text = apply_updates(text, sets=carried)
        if target.exists():
            print("既にある: %s" % target, file=sys.stderr)
            return 1
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        print("作成 %s → %s（%s）" % (decision.id, card_id, title))
        for note in notes:
            print("  注意: %s" % note, file=sys.stderr)
        created += 1
        wiki.__dict__.pop("_scanned", None)
        wiki.__dict__.pop("_by_id", None)
        wiki.__dict__.pop("_by_type", None)

    print()
    if args.write:
        print("%d件を起票、%d件は既にある、%d件を閉じた" % (created, skipped, closed))
    else:
        print("%d件が未起票、%d件は既にある、%d件を閉じる（--write で書く）"
              % (created, skipped, closed))
        print("`引用` と `信頼度` は決定のものを写す。新しい引用は作らない。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
