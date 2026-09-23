#!/usr/bin/env python3
"""議題（AGD）と次回アジェンダのテスト。

議題は DEC / Q / ACT の親。子が `議題` で親を指し、親は子を持たない。
アジェンダは「その会議に載る議題と、その下のカード」の射影。
"""

import contextlib
import datetime
import io
import unittest

from tests.fixtures import WikiTestCase
from tools import agenda, agenda_sync_cmd, gen_views, kimelint
from tools.bundle import Bundle
from tools.derive import derived_fields
from tools.new_cmd import new_card

TODAY = datetime.date(2026, 9, 18)
LOG = ("LOG", "LOG-20260918-01", {})
SEGMENTS = """\
meeting: MTG-20260918
segments:
  - seq: 1
    title: 認証方式
    種別: 議論
    議題: AGD-001
"""


def agd(card_id, **overrides):
    return ("AGD", card_id, overrides)


class 議題の逆引き(WikiTestCase):
    def test_子が指している議題から子を引く(self):
        w = self.wiki([LOG, agd("AGD-001"),
                       ("DEC", "DEC-001", {"議題": "AGD-001"}),
                       ("Q", "Q-001", {"議題": "AGD-001"}),
                       ("Q", "Q-002", {})])
        self.assertEqual([c.id for c in w.children_of("AGD-001")], ["DEC-001", "Q-001"])


class 載る議題(WikiTestCase):
    def ids(self, cards, meeting):
        return [(c.id, carried) for c, carried in self.wiki([LOG] + cards).agenda_of(meeting)]

    def test_予定会議に対象会議を含む(self):
        self.assertEqual(self.ids([agd("AGD-001", 予定会議=["MTG-20261002"])], "MTG-20261002"),
                         [("AGD-001", False)])

    def test_前の会議で決着しなければ持ち越す(self):
        self.assertEqual(self.ids([agd("AGD-001", status="継続")], "MTG-20261002"),
                         [("AGD-001", True)])

    def test_予定会議が空なら次回に載る(self):
        self.assertEqual(self.ids([agd("AGD-001", 予定会議=[])], "MTG-20261002"),
                         [("AGD-001", False)])

    def test_先の会議の予定は載せない(self):
        self.assertEqual(self.ids([agd("AGD-001", 予定会議=["MTG-20261016"])], "MTG-20261002"), [])

    def test_決着と取り下げは載せない(self):
        self.assertEqual(self.ids([agd("AGD-001", status="決着"),
                                   agd("AGD-002", status="取り下げ")], "MTG-20260918"), [])


class 議題の導出(WikiTestCase):
    def test_議題は提起者と提起日と予定会議を埋める(self):
        w = self.wiki([LOG])
        _, text, target, _ = new_card(w, "AGD", meeting="MTG-20261002",
                                      title="帳票を今期に入れるか", role="顧客PM",
                                      today="2026-09-23")
        self.assertIn("title: 帳票を今期に入れるか", text)
        self.assertIn("提起者: 顧客PM", text)
        self.assertIn("提起日: 2026-09-23", text)
        self.assertIn("予定会議: [MTG-20261002]", text)
        self.assertEqual(target.parent.name, "agenda")

    def test_論点の議題を子カードへ写す(self):
        w = self.wiki([LOG, agd("AGD-001")], segments={"MTG-20260918": SEGMENTS})
        fields, _ = derived_fields(w, "DEC", role="顧客PM", log="LOG-20260918-01",
                                   meeting="MTG-20260918")
        self.assertEqual(fields["議題"], "AGD-001")

    def test_論点に議題が無ければ埋めない(self):
        w = self.wiki([LOG, agd("AGD-001")])
        fields, _ = derived_fields(w, "Q", role="顧客PM", log="LOG-20260918-01",
                                   meeting="MTG-20260918")
        self.assertNotIn("議題", fields)

    def test_実在しない議題は写さず注意を出す(self):
        w = self.wiki([LOG], segments={"MTG-20260918": SEGMENTS})
        fields, notes = derived_fields(w, "ACT", role="顧客PM", log="LOG-20260918-01",
                                       meeting="MTG-20260918")
        self.assertNotIn("議題", fields)
        self.assertTrue(any("AGD-001" in n for n in notes))


class 選定(WikiTestCase):
    def test_節の順は_ontology_のとおりで冒頭はなぜ未記入(self):
        sections = agenda.select(self.wiki([LOG]))
        self.assertEqual(sections[0].key, "why-missing")
        self.assertEqual([s.key for s in sections],
                         [k for k, _, _ in self.wiki([LOG]).ontology.agenda_sections()])

    def test_議題の下の未決は紐づかない節に重ねて出さない(self):
        w = self.wiki([LOG, agd("AGD-001"),
                       ("Q", "Q-001", {"議題": "AGD-001"}), ("Q", "Q-002", {})])
        by_key = {s.key: s for s in agenda.select(w, "MTG-20260918")}
        self.assertEqual([q.id for q in by_key["agenda-items"].items[0].questions], ["Q-001"])
        self.assertEqual([c.id for c in by_key["loose-questions"].cards], ["Q-002"])

    def test_閉じた議題の未決は紐づかない節に落ちて消えない(self):
        w = self.wiki([LOG, agd("AGD-001", status="決着"),
                       ("Q", "Q-001", {"議題": "AGD-001"})])
        by_key = {s.key: s for s in agenda.select(w, "MTG-20260918")}
        self.assertEqual([c.id for c in by_key["loose-questions"].cards], ["Q-001"])


class ビュー(WikiTestCase):
    def test_次回アジェンダに議題と配下の未決が出る(self):
        text = gen_views.render(self.wiki([LOG, agd("AGD-001", title="認証方式を決めたい"),
                                           ("Q", "Q-001", {"議題": "AGD-001"})]),
                                "agenda-next", TODAY)
        section = text.split("## 2. 議題\n")[1].split("\n## ")[0]
        self.assertIn("認証方式を決めたい", section)
        self.assertIn("Q-001", section)

    def test_開いているものに閉じていない議題が出る(self):
        text = gen_views.render(self.wiki([LOG, agd("AGD-001", title="認証方式を決めたい")]),
                                "open-items", TODAY)
        self.assertIn("## 閉じていない議題", text)
        self.assertIn("認証方式を決めたい", text)


class 材料(WikiTestCase):
    def test_未作成の会議でも組み立てられる(self):
        w = self.wiki([LOG, agd("AGD-001", title="帳票を今期に入れるか",
                                予定会議=["MTG-20261002"])])
        text = Bundle(w, TODAY).agenda_input("MTG-20261002")
        self.assertIn("### AGD-001 帳票を今期に入れるか", text)
        self.assertIn("## アジェンダの骨格", text)

    def test_骨格は_ontology_の順(self):
        w = self.wiki([LOG])
        text = Bundle(w, TODAY).agenda_input()
        titles = [t for _, t, _ in w.ontology.agenda_sections()]
        positions = [text.index("## %s" % t) for t in titles]
        self.assertEqual(positions, sorted(positions))

    def test_顧客提出版で議題の_ID_を落とす(self):
        w = self.wiki([LOG, agd("AGD-001"), ("DEC", "DEC-001", {"議題": "AGD-001"})])
        internal = Bundle(w, TODAY).minutes_input("MTG-20260918")
        customer = Bundle(w, TODAY).minutes_input("MTG-20260918", "customer")
        self.assertIn("議題: AGD-001 決めたいこと", internal)
        self.assertNotIn("AGD-001", customer)

    def test_確認2に議題の締めが出る(self):
        w = self.wiki([LOG, agd("AGD-001", title="認証方式を決めたい")])
        self.assertIn("認証方式を決めたい", Bundle(w, TODAY).review("MTG-20260918"))


class 検査(WikiTestCase):
    def problems(self, cards, check_id, segments=None):
        return kimelint.run(self.wiki(cards, segments=segments), today=TODAY, only={check_id})

    def test_予定会議が会議_ID_の形でないと鳴る(self):
        self.assertTrue(self.problems([LOG, agd("AGD-001", 予定会議=["来週"])], "agd-meeting-id"))

    def test_未来の会議でも形が合っていれば鳴らない(self):
        self.assertFalse(self.problems([LOG, agd("AGD-001", 予定会議=["MTG-20991231"])],
                                       "agd-meeting-id"))

    def test_決着なのに未決が残ると鳴る(self):
        self.assertTrue(self.problems([LOG, agd("AGD-001", status="決着"),
                                       ("Q", "Q-001", {"議題": "AGD-001"})], "agd-closed-open"))

    def test_決着して未決が無ければ鳴らない(self):
        self.assertFalse(self.problems([LOG, agd("AGD-001", status="決着"),
                                        ("Q", "Q-001", {"議題": "AGD-001", "status": "解決",
                                                        "resolved_by": "DEC-001"}),
                                        ("DEC", "DEC-001", {"議題": "AGD-001"})],
                                       "agd-closed-open"))

    def test_議題が議題以外を指すと鳴る(self):
        self.assertTrue(self.problems([LOG, ("Q", "Q-001", {}),
                                       ("DEC", "DEC-001", {"議題": "Q-001"})], "ref-range"))

    def test_論点の議題が実在しないと鳴る(self):
        self.assertTrue(self.problems([LOG], "segment-format",
                                      segments={"MTG-20260918": SEGMENTS}))

    def test_論点の議題が実在すれば鳴らない(self):
        self.assertFalse(self.problems([LOG, agd("AGD-001")], "segment-format",
                                       segments={"MTG-20260918": SEGMENTS}))

    def test_提起者が未登録の役割だと鳴る(self):
        self.assertTrue(self.problems([LOG, agd("AGD-001", 提起者="営業部長")], "role-unknown"))

    def test_議題カードは標準の検査で_error_を出さない(self):
        errors = [p for p in kimelint.run(self.wiki([LOG, agd("AGD-001")]), today=TODAY)
                  if p.level == "error"]
        self.assertEqual(errors, [], [p.message for p in errors])



# 2回の会議のうち、1回目だけで議題を扱った。
TWO_MEETINGS = {
    "MTG-20260904": """\
meeting: MTG-20260904
segments:
  - seq: 1
    title: 認証方式
    種別: 議論
    議題: AGD-001
""",
    "MTG-20260918": """\
meeting: MTG-20260918
segments:
  - seq: 1
    title: 別の話
    種別: 議論
""",
}


class 結論が出なかった議題(WikiTestCase):
    def item(self, cards, segments, meeting="MTG-20261002"):
        w = self.wiki([LOG] + cards, segments=segments)
        return agenda.agenda_items(w, meeting)[0]

    def test_扱ったが結論なしと出る(self):
        item = self.item([agd("AGD-001", status="継続", 予定会議=["MTG-20260904"])],
                         {"MTG-20260904": TWO_MEETINGS["MTG-20260904"]})
        self.assertEqual(item.label, "持ち越し（MTG-20260904 で扱ったが結論なし）")

    def test_予定したのに扱えなかったと出る(self):
        item = self.item([agd("AGD-001", status="継続",
                              予定会議=["MTG-20260904", "MTG-20260918"])], TWO_MEETINGS)
        self.assertEqual(item.label, "持ち越し（MTG-20260918 で扱えず）")

    def test_会議の場で出て扱った議題も持ち越す(self):
        # 予定会議が空でも、論点に付いていれば扱った会議として数える
        item = self.item([agd("AGD-001", 予定会議=[])],
                         {"MTG-20260904": TWO_MEETINGS["MTG-20260904"]})
        self.assertTrue(item.carried)

    def test_未決があれば継続を示す(self):
        item = self.item([agd("AGD-001"), ("Q", "Q-001", {"議題": "AGD-001"})], {},
                         "MTG-20260918")
        self.assertEqual(agenda.closing_hint(item), "継続（Q-001 が未決）")

    def test_未決が無く決定があれば決着候補(self):
        item = self.item([agd("AGD-001"), ("DEC", "DEC-001", {"議題": "AGD-001"})], {},
                         "MTG-20260918")
        self.assertEqual(agenda.closing_hint(item), "決着候補")

    def test_確認2に扱ったかと目安が出る(self):
        w = self.wiki([LOG, agd("AGD-001", 予定会議=["MTG-20260918"]),
                       ("DEC", "DEC-001", {"議題": "AGD-001"})])
        text = Bundle(w, TODAY).review("MTG-20260918")
        row = next(l for l in text.splitlines() if l.startswith("| AGD-001"))
        self.assertIn("扱えず", row)
        self.assertIn("決着候補", row)


def quiet(func, *args):
    with contextlib.redirect_stdout(io.StringIO()):
        return func(*args)


class 議題の書き戻し(WikiTestCase):
    def test_扱った議題を継続にし予定会議に足す(self):
        w = self.wiki([LOG, agd("AGD-001", 予定会議=[])],
                      segments={"MTG-20260904": TWO_MEETINGS["MTG-20260904"]})
        (card, sets, _), = agenda_sync_cmd.plan(w)
        self.assertEqual(dict(sets), {"status": "継続", "予定会議": "[MTG-20260904]"})

    def test_書き戻すとカードが変わる(self):
        w = self.wiki([LOG, agd("AGD-001", 予定会議=["MTG-20260904"])],
                      segments={"MTG-20260904": TWO_MEETINGS["MTG-20260904"]})
        self.assertEqual(quiet(agenda_sync_cmd.main, ["--root", str(w.root), "--write"]), 0)
        again = self.wiki_at(w.root)
        self.assertEqual(again.get("AGD-001").get("status"), "継続")
        self.assertEqual(agenda_sync_cmd.plan(again), [])

    def test_予定会議の行が無いカードにも書ける(self):
        w = self.wiki([LOG, agd("AGD-001", 予定会議=None)],
                      segments={"MTG-20260904": TWO_MEETINGS["MTG-20260904"]})
        quiet(agenda_sync_cmd.main, ["--root", str(w.root), "--write"])
        self.assertEqual(self.wiki_at(w.root).get("AGD-001").list("予定会議"), ["MTG-20260904"])

    def test_閉じた議題には触らない(self):
        w = self.wiki([LOG, agd("AGD-001", status="決着", 予定会議=[])],
                      segments={"MTG-20260904": TWO_MEETINGS["MTG-20260904"]})
        self.assertEqual(agenda_sync_cmd.plan(w), [])

    def test_書き戻し漏れを_lint_が拾う(self):
        w = self.wiki([LOG, agd("AGD-001", 予定会議=["MTG-20260904"])],
                      segments={"MTG-20260904": TWO_MEETINGS["MTG-20260904"]})
        self.assertTrue(kimelint.run(w, today=TODAY, only={"agd-unsynced"}))

    def test_扱っていなければ鳴らない(self):
        w = self.wiki([LOG, agd("AGD-001")])
        self.assertFalse(kimelint.run(w, today=TODAY, only={"agd-unsynced"}))


class 持ち越しで載った会議の書き戻し(WikiTestCase):
    """開いた議題は次回に自動で載るが、載った会議はどこにも書かれていなかった。

    書き戻さないと、2回続けて扱えなかった議題が「1回前に扱ったが結論なし」に見える。
    """

    def _wiki(self, segments=TWO_MEETINGS, **overrides):
        card = dict(status="継続", 予定会議=["MTG-20260904"], 提起日="2026-08-28")
        card.update(overrides)
        return self.wiki([LOG, agd("AGD-001", **card)], segments=segments)

    def test_載ったが扱えなかった会議を予定会議に足す(self):
        w = self._wiki()
        (card, sets, notes), = agenda_sync_cmd.plan(w)
        self.assertEqual(dict(sets), {"予定会議": "[MTG-20260904, MTG-20260918]"})
        self.assertIn("扱えず", notes[0])

    def test_書き戻すと次回に扱えずと出る(self):
        w = self._wiki()
        quiet(agenda_sync_cmd.main, ["--root", str(w.root), "--write"])
        item = agenda.agenda_items(self.wiki_at(w.root), "MTG-20261002")[0]
        self.assertEqual(item.label, "持ち越し（MTG-20260918 で扱えず）")

    def test_確認の2_5に扱えずで出る(self):
        w = self._wiki()
        quiet(agenda_sync_cmd.main, ["--root", str(w.root), "--write"])
        text = Bundle(self.wiki_at(w.root), TODAY).review("MTG-20260918")
        row = next(l for l in text.splitlines() if l.startswith("| AGD-001"))
        self.assertIn("扱えず", row)

    def test_提起より前の会議には足さない(self):
        w = self._wiki(segments={"MTG-20260918": TWO_MEETINGS["MTG-20260918"]},
                       予定会議=[], status="未着手", 提起日="2026-09-20")
        self.assertEqual(agenda_sync_cmd.plan(w), [])

    def test_会議を指定すればその会議だけ(self):
        w = self._wiki()
        self.assertEqual(agenda_sync_cmd.plan(w, "MTG-20260904"), [])

    def test_先の会議に予定した議題は足さない(self):
        w = self._wiki(segments={"MTG-20260918": TWO_MEETINGS["MTG-20260918"]},
                       予定会議=["MTG-20261002"], status="未着手")
        self.assertEqual(agenda_sync_cmd.plan(w), [])


class 議題の言い換え(WikiTestCase):
    def problems(self, q_title, agd_title="図面PDFを検索対象に入れるかを決めたい"):
        w = self.wiki([LOG, agd("AGD-001", title=agd_title),
                       ("Q", "Q-001", {"議題": "AGD-001", "title": q_title})])
        return kimelint.run(w, today=TODAY, only={"q-restates-agenda"})

    def test_議題と同じ問いは鳴る(self):
        self.assertTrue(self.problems("図面PDFを検索対象に入れるか"))

    def test_足りないものを問う_Q_は鳴らない(self):
        self.assertFalse(self.problems("図面PDF対応の追加費用をどう扱うか"))

    def test_議題に紐づかない_Q_は見ない(self):
        w = self.wiki([LOG, agd("AGD-001", title="図面PDFを検索対象に入れるか"),
                       ("Q", "Q-001", {"title": "図面PDFを検索対象に入れるか"})])
        self.assertFalse(kimelint.run(w, today=TODAY, only={"q-restates-agenda"}))


if __name__ == "__main__":
    unittest.main()
