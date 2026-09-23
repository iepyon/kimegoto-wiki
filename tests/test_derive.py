#!/usr/bin/env python3
"""導出フィールドの適用（`tools/derive.py` と `kime new`）。

見ているのは「機械が書く」側。これまで LLM が書いて lint が事後照合していた
写像が、ここで一意に決まることを確かめる。同時に、**埋めてはいけないものを
埋めていない**ことも確かめる（`なぜ` / `期限` / `範囲`）。
"""

import unittest

from tests.fixtures import WikiTestCase
from tools.derive import derived_fields
from tools.new_cmd import new_card


class 決定の導出(WikiTestCase):

    def setUp(self):
        self.w = self.wiki([("LOG", "LOG-20260918-01", {})])

    def test_役割から種別と所在と会議体を引く(self):
        fields, _ = derived_fields(self.w, "DEC", role="顧客PM",
                                   log="LOG-20260918-01", meeting="MTG-20260918")
        self.assertEqual(fields["決定の所在"], "顧客PM")
        self.assertEqual(fields["種別"], "交渉可能")
        self.assertEqual(fields["決定日"], "2026-09-18")
        self.assertEqual(fields["derived_from"], "[LOG-20260918-01]")

    def test_役割ごとに種別が変わる(self):
        for role, kind in (("顧客PM", "交渉可能"), ("顧客法務", "契約制約"),
                           ("開発リーダ", "技術判断")):
            fields, _ = derived_fields(self.w, "DEC", role=role)
            self.assertEqual(fields["種別"], kind, role)

    def test_未登録の役割からは引かない(self):
        fields, notes = derived_fields(self.w, "DEC", role="インフラ担当")
        self.assertNotIn("種別", fields)
        self.assertEqual(fields["決定の所在"], "インフラ担当")
        self.assertTrue(any("role-mapping.yaml に無い" in n for n in notes))

    def test_決定権のない役割では注意を出す(self):
        _, notes = derived_fields(self.w, "DEC", role="開発メンバー")
        self.assertTrue(any("Q に落とす" in n for n in notes))

    def test_決定権のある役割では注意を出さない(self):
        _, notes = derived_fields(self.w, "DEC", role="顧客PM")
        self.assertEqual(notes, [])


class アクションと問いの導出(WikiTestCase):

    def setUp(self):
        self.w = self.wiki([("LOG", "LOG-20260918-01", {})])

    def test_担当は役割の社名になる(self):
        fields, _ = derived_fields(self.w, "ACT", role="開発リーダ")
        self.assertEqual(fields["担当"], "ESM")

    def test_期限は埋めない(self):
        fields, _ = derived_fields(self.w, "ACT", role="開発リーダ",
                                   meeting="MTG-20260918")
        self.assertNotIn("期限", fields)

    def test_未登録の役割では担当を空欄にする(self):
        fields, _ = derived_fields(self.w, "ACT", role="インフラ担当")
        self.assertNotIn("担当", fields)

    def test_問いの日付は会議日になる(self):
        fields, _ = derived_fields(self.w, "Q", role="顧客PM", meeting="MTG-20260918")
        self.assertEqual(fields["初出"], "2026-09-18")
        self.assertEqual(fields["最終言及"], "2026-09-18")


class 制約の硬度(WikiTestCase):

    def setUp(self):
        self.w = self.wiki([("LOG", "LOG-20260918-01", {})])

    def test_種類と所在から硬度が決まる(self):
        fields, _ = derived_fields(self.w, "CON", role="顧客PM", kind="expectation")
        self.assertEqual(fields["所在"], "顧客側")
        self.assertEqual(fields["硬度"], "沈殿")

    def test_自社側の期待は懸濁になる(self):
        fields, _ = derived_fields(self.w, "CON", role="開発リーダ", kind="expectation")
        self.assertEqual(fields["硬度"], "懸濁")

    def test_導出表にない組み合わせは埋めずに注意を出す(self):
        # expectation × 契約 は ontology.yaml の表にない（推測で埋めない）。
        w = self.wiki([("LOG", "LOG-20260918-01", {})], role_mapping="""\
meta:
  自社: ESM
roles:
  顧客法務:
    所属: 契約
    社名: 甲社
    決定権: あり
    決定の種別: 契約制約
""")
        fields, notes = derived_fields(w, "CON", role="顧客法務", kind="expectation")
        self.assertNotIn("硬度", fields)
        self.assertTrue(any("導出表にない" in n for n in notes))


class 雛形への書き込み(WikiTestCase):

    def test_new_card_が導出フィールドを埋める(self):
        w = self.wiki([("LOG", "LOG-20260918-01", {})])
        _, text, _, _ = new_card(w, "DEC", meeting="MTG-20260918", title="OIDC に寄せる",
                                 role="顧客PM", log="LOG-20260918-01")
        self.assertIn("決定の所在: 顧客PM", text)
        self.assertIn("種別: 交渉可能", text)
        self.assertIn("決定日: 2026-09-18", text)
        self.assertIn("derived_from: [LOG-20260918-01]", text)
        self.assertIn("title: OIDC に寄せる", text)

    def test_解釈の要るフィールドは空欄のまま残す(self):
        w = self.wiki([("LOG", "LOG-20260918-01", {})])
        _, text, _, _ = new_card(w, "DEC", meeting="MTG-20260918", title="t",
                                 role="顧客PM", log="LOG-20260918-01")
        self.assertIn("なぜ:\n", text)
        self.assertIn("範囲: 判定保留", text)
        self.assertIn("代替案: []", text)

    def test_役割を渡さなければ雛形のまま(self):
        w = self.wiki([("LOG", "LOG-20260918-01", {})])
        _, text, _, _ = new_card(w, "DEC", meeting="MTG-20260918", title="t")
        self.assertIn("決定の所在: 役割", text)


if __name__ == "__main__":
    unittest.main()
