#!/usr/bin/env python3
"""次回アジェンダの選定 — 何を載せるかを1か所で決める。

アジェンダは議事録と同じく**カードの射影**。載せるものの選び方がビュー
（`views/agenda-next.md`）と材料（`kime agenda-input`）で食い違わないよう、
選定だけをここに置き、並べ方はそれぞれが持つ。

節の順と見出しの正本は `ontology.yaml` の `agenda.sections`。
冒頭は `なぜ` 未記入の決定（書かないことに付けたコスト）。

lint に依存させない（gen_views と同じ理由）。
"""

from tools import scope_cmd


class Item:
    """アジェンダに載る議題1件と、その下にぶら下がるカード。"""

    def __init__(self, card, carried, decisions, questions, actions, history=""):
        self.card = card
        self.carried = carried        # 前回までに載り、決着していない
        self.decisions = decisions    # これまでの決定（経緯として）
        self.questions = questions    # 未決の問い
        self.actions = actions        # 未完了のアクション
        self.history = history        # 「MTG-… で扱ったが結論なし」「MTG-… で扱えず」

    @property
    def label(self):
        if not self.carried:
            return self.card.get("status")
        return "持ち越し（%s）" % self.history if self.history else "持ち越し"


class Section:
    def __init__(self, key, title, note, cards=None, items=None):
        self.key = key
        self.title = title
        self.note = note
        self.cards = cards or []
        self.items = items or []

    def __len__(self):
        return len(self.items) if self.key == "agenda-items" else len(self.cards)


def _sound(wiki, *types):
    return [c for c in wiki.by_type(*types) if c.error is None]


def why_missing(wiki):
    return sorted((c for c in _sound(wiki, "DEC")
                   if not c.get("なぜ") and wiki.is_open(c)),
                  key=lambda c: c.id)


def open_actions(wiki):
    return sorted((c for c in _sound(wiki, "ACT") if wiki.is_open(c)), key=lambda c: c.id)


def open_questions(wiki):
    return sorted((c for c in _sound(wiki, "Q") if wiki.is_open(c)), key=lambda c: c.id)


def fragile_assumptions(wiki):
    """棚卸しの対象になる前提だけ。全件は追跡しない（2週25分では破綻する）。"""
    return sorted((c for c in _sound(wiki, "ASM")
                   if wiki.is_active(c) and c.get("脆弱性") in wiki.ontology.tracked_vulnerability()
                   and c.list("崩れたら見直す決定")),
                  key=lambda c: c.id)


def history(wiki, card, meeting_id=None):
    """持ち越しの中身。直近の会議で「扱ったが結論なし」か「扱えず」か。

    扱ったかどうかは `segments.yaml` の論点に `議題` が付いたかで決まる（Pass 1）。
    予定していた会議が開かれたのに論点が無ければ、扱えなかったということ。
    会議がまだ開かれていない（ディレクトリが無い）予定は数えない。
    """
    def before(m):
        return m in wiki.meetings and (meeting_id is None or m < meeting_id)

    discussed = [m for m in wiki.discussed_in(card) if before(m)]
    planned = [m for m in card.list("予定会議") if before(m)]
    last_discussed = discussed[-1] if discussed else ""
    last_planned = max(planned) if planned else ""
    if last_planned and last_planned > last_discussed:
        return "%s で扱えず" % last_planned
    if last_discussed:
        return "%s で扱ったが結論なし" % last_discussed
    return ""


def closing_hint(item):
    """確認②で議題を締めるときの目安。判定するのは人間で、これは候補を示すだけ。"""
    if item.questions:
        return "継続（%s が未決）" % " / ".join(c.id for c in item.questions)
    if item.decisions:
        return "決着候補"
    return ""


def agenda_items(wiki, meeting_id=None):
    out = []
    for card, carried in wiki.agenda_of(meeting_id):
        children = wiki.children_of(card)
        out.append(Item(
            card, carried,
            [c for c in children if c.type == "DEC" and wiki.is_open(c)],
            [c for c in children if c.type == "Q" and wiki.is_open(c)],
            [c for c in children if c.type == "ACT" and wiki.is_open(c)],
            history(wiki, card, meeting_id) if carried else ""))
    return out


def loose_questions(wiki, meeting_id=None):
    """議題に紐づかない未決の問い（議題の節に載らないもの）。

    子が指している議題が閉じている／今回載らない場合も、ここに落とす。
    未決の問いがアジェンダから消えることは無い。
    """
    shown = {q.id for item in agenda_items(wiki, meeting_id) for q in item.questions}
    return [c for c in open_questions(wiki) if c.id not in shown]


def select(wiki, meeting_id=None):
    """`ontology.agenda.sections` の順に Section を返す。"""
    builders = {
        "why-missing": lambda: {"cards": why_missing(wiki)},
        "scope-pending": lambda: {"cards": scope_cmd.pending_decisions(wiki)},
        "open-actions": lambda: {"cards": open_actions(wiki)},
        "agenda-items": lambda: {"items": agenda_items(wiki, meeting_id)},
        "loose-questions": lambda: {"cards": loose_questions(wiki, meeting_id)},
        "assumptions": lambda: {"cards": fragile_assumptions(wiki)},
    }
    out = []
    for key, title, note in wiki.ontology.agenda_sections():
        build = builders.get(key)
        if build is None:
            raise KeyError("ontology.yaml の agenda.sections に未知のキー: %s" % key)
        out.append(Section(key, title, note, **build()))
    return out

