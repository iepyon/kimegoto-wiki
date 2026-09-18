#!/usr/bin/env python3
"""ontology.yaml 自体の健全性テスト。

スキーマのタイポは、それを使うすべてのチェックを静かに壊す。
lint を書く前に、宣言が自己整合していることを機械で確かめる。
"""

import re
import unittest

from tools import schema


class OntologyIntegrityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.o = schema.load()

    def test_七種そろっている(self):
        self.assertEqual(set(self.o.type_names()), {"LOG", "DEC", "Q", "ACT", "CON", "ASM", "TERM"})

    def test_すべての型にフィールド宣言がある(self):
        for t in self.o.type_names():
            self.assertTrue(self.o.field_specs(t), "%s のフィールド宣言が無い" % t)

    def test_すべての型にidとtypeが必須(self):
        for t in self.o.type_names():
            required = self.o.required_fields(t)
            self.assertIn("id", required, t)
            self.assertIn("type", required, t)

    def test_headline_が実在のフィールドを指す(self):
        for t in self.o.type_names():
            self.assertIn(self.o.headline_field(t), self.o.field_specs(t), t)

    def test_ID_正規表現がコンパイルできる(self):
        for t in self.o.type_names():
            re.compile(self.o.spec(t)["id"])

    def test_enum_参照はすべて解決する(self):
        for t in self.o.type_names():
            for name, spec in self.o.field_specs(t).items():
                if "enum" in spec:
                    self.assertIn(spec["enum"], self.o.enums, "%s.%s" % (t, name))

    def test_struct_参照はすべて解決する(self):
        for t in self.o.type_names():
            for name, spec in self.o.field_specs(t).items():
                if "struct" in spec:
                    self.assertIn(spec["struct"], self.o.structs, "%s.%s" % (t, name))

    def test_struct_の_enums_も解決する(self):
        for name, spec in self.o.structs.items():
            for key, enum_name in (spec.get("enums") or {}).items():
                self.assertIn(enum_name, self.o.enums, "%s.%s" % (name, key))

    def test_struct_の_required_は_keys_の部分集合(self):
        for name, spec in self.o.structs.items():
            keys, required = spec.get("keys", []), spec.get("required", [])
            if keys:
                self.assertTrue(set(required) <= set(keys), name)

    def test_kind_は既知のものだけ(self):
        known = {"id", "text", "enum", "date", "ref", "ref-list", "str-list",
                 "struct-list", "quote", "time-range"}
        for t in self.o.type_names():
            for name, spec in self.o.field_specs(t).items():
                self.assertIn(spec.get("kind"), known, "%s.%s" % (t, name))

    def test_記入主体は三値のいずれか(self):
        for t in self.o.type_names():
            for name, spec in self.o.field_specs(t).items():
                self.assertIn(spec.get("記入主体"), {"自動", "人間", "導出"}, "%s.%s" % (t, name))

    def test_relations_の_domain_range_は実在の型(self):
        known = set(self.o.type_names()) | {"MTG", "any"}
        for name, rel in self.o.relations.items():
            for side in ("domain", "range"):
                for t in rel.get(side, []):
                    self.assertIn(t, known, "%s.%s" % (name, side))

    def test_inverse_は対になっている(self):
        for name, rel in self.o.relations.items():
            inverse = rel.get("inverse")
            if not inverse:
                continue
            self.assertIn(inverse, self.o.relations, "%s の inverse %s が宣言されていない" % (name, inverse))
            self.assertEqual(self.o.inverse_of(inverse), name,
                             "%s と %s が相互に指していない" % (name, inverse))

    def test_ref_フィールドは_relations_に宣言がある(self):
        for t in self.o.type_names():
            for name, spec in self.o.field_specs(t).items():
                if spec.get("kind") in ("ref", "ref-list"):
                    self.assertIn(name, self.o.relations, "%s.%s" % (t, name))

    def test_relations_の_domain_と_fields_が一致する(self):
        for name, rel in self.o.relations.items():
            for t in rel.get("domain", []):
                if t == "MTG":
                    continue
                self.assertIn(name, self.o.field_specs(t),
                              "relations の %s が %s の domain だが、%s にフィールドが無い" % (name, t, t))

    def test_status_implications_は実在の型とフィールドと語彙を指す(self):
        for imp in self.o.status_implications:
            t = imp["type"]
            self.assertIn(t, self.o.type_names())
            self.assertIn(imp["when-filled"], self.o.field_specs(t))
            self.assertIn(imp["status"], self.o.enum_for(t, "status"), imp["status"])

    def test_硬度の導出表は語彙の値だけを返す(self):
        hardness = self.o.enum_values("硬度")
        for combo, value in self.o.hardness_table().items():
            self.assertIn(value, hardness, combo)

    def test_硬度の導出表のキーは語彙の組み合わせ(self):
        kinds, locations = self.o.enum_values("制約種類"), self.o.enum_values("所在")
        for combo in self.o.hardness_table():
            kind, _, location = combo.partition("/")
            self.assertIn(kind, kinds, combo)
            self.assertIn(location, locations, combo)

    def test_導出表に無い組み合わせは_None_を返す(self):
        # schema.md の表は expectation × 契約 を定めていない。
        # 推測で埋めず、未定義のままであることをここで固定する。
        self.assertIsNone(self.o.derive_hardness("expectation", "契約"))
        self.assertEqual(self.o.derive_hardness("property", "契約"), "岩盤")
        self.assertEqual(self.o.derive_hardness("expectation", "自社側"), "懸濁")

    def test_顧客版の除外規則は実在の型とフィールドを指す(self):
        customer = self.o.edition("customer")
        for rule in customer.get("exclude", []):
            t = rule["type"]
            self.assertIn(t, self.o.type_names())
            self.assertIn(rule["field"], self.o.field_specs(t))
            values = self.o.enum_for(t, rule["field"])
            if values:
                self.assertIn(rule["value"], values)

    def test_顧客版のdrop_fieldsは実在のフィールド名(self):
        known = {n for t in self.o.type_names() for n in self.o.field_specs(t)}
        for name in self.o.edition("customer").get("drop-fields", []):
            self.assertIn(name, known, name)

    def test_顧客版は逐語引用とIDを落とす(self):
        # render_minutes.md の「出さないもの」表。漏れたら契約上の事故になる。
        drop = set(self.o.edition("customer").get("drop-fields", []))
        for name in ("id", "引用", "信頼度", "derived_from", "硬度", "所在"):
            self.assertIn(name, drop, name)

    def test_版は内部版と顧客版がある(self):
        self.assertEqual(set(self.o.edition_names()), {"internal", "customer"})

    def test_閾値はすべて整数として読める(self):
        for name in self.o.thresholds:
            self.assertIsInstance(self.o.threshold(name), int, name)


class TypeOfIdTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.o = schema.load()

    def test_各型のIDを判定できる(self):
        cases = {
            "LOG-20260918-03": "LOG", "DEC-014": "DEC", "Q-031": "Q",
            "ACT-008": "ACT", "CON-007": "CON", "ASM-003": "ASM",
            "TERM-012": "TERM", "MTG-20260918": "MTG",
        }
        for card_id, expected in cases.items():
            self.assertEqual(self.o.type_of_id(card_id), expected, card_id)

    def test_未知のIDは_None(self):
        for bad in ["", None, "DEC-14", "DEC-0014", "XXX-001", "LOG-20260918-3"]:
            self.assertIsNone(self.o.type_of_id(bad), repr(bad))

    def test_採番用の数値を取れる(self):
        self.assertEqual(self.o.id_number("DEC-014"), 14)
        self.assertEqual(self.o.id_number("LOG-20260918-03"), 3)
        self.assertIsNone(self.o.id_number("なし"))


if __name__ == "__main__":
    unittest.main()
