#!/usr/bin/env python3
"""schema.md の生成ブロックの生成と、散文・サンプルの照合のテスト。"""

import unittest

from tools import gen_schema_doc as g
from tools import schema


def marker(arg):
    return "<!-- generated:%s — ontology.yaml から生成。手編集禁止 -->\n<!-- /generated -->\n" % arg


class RenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.o = schema.load()

    def test_ID_形式を人が読む形にする(self):
        self.assertEqual(g.id_pattern(r"^LOG-\d{8}-\d{2}$"), "LOG-YYYYMMDD-NN")
        self.assertEqual(g.id_pattern(r"^DEC-\d{3}$"), "DEC-NNN")

    def test_空のマーカーが後ろの散文を飲み込まない(self):
        # 本文の無いマーカーのあとに別のブロックがあっても、間の散文は残る。
        text = marker("types") + "\n残す散文\n\n" + marker("derivation 硬度")
        out = g.apply(text, self.o)
        self.assertIn("残す散文", out)
        self.assertIn("| フロー | DEC | 決定事項 | `DEC-NNN` |", out)
        self.assertIn("| property | 契約 | 岩盤 |", out)

    def test_生成は冪等(self):
        text = "## DEC — 決定事項\n\n散文\n\n" + marker("words assumption-trigger-words")
        once = g.apply(text, self.o)
        self.assertEqual(g.apply(once, self.o), once)
        self.assertIn("<!-- generated:fields DEC", once)
        self.assertIn(" / ".join(self.o.assumption_trigger_words), once)

    def test_未知のマーカーには触らない(self):
        text = marker("derivation 存在しない") + marker("unknown-kind")
        self.assertEqual(g.apply(text, self.o), text)

    def test_フィールド表に意味の列が出る(self):
        table = g.render_fields(self.o, "DEC")
        self.assertIn("| `スコープ` | 当初の合意に入っていたか |", table)

    def test_schema_md_は最新(self):
        text = (schema.KIT_ROOT / "schema.md").read_text(encoding="utf-8")
        self.assertEqual(g.apply(text, self.o), text)


if __name__ == "__main__":
    unittest.main()
