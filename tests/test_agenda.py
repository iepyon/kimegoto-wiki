#!/usr/bin/env python3
"""議題（AGD）と次回アジェンダのテスト。

議題は DEC / Q / ACT の親。子が `議題` で親を指し、親は子を持たない。
アジェンダは「その会議に載る議題と、その下のカード」の射影。
"""

import datetime
import unittest

from tests.fixtures import WikiTestCase
from tools import agenda, gen_views, kimelint
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


if __name__ == "__main__":
    unittest.main()
