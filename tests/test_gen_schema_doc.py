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


class CheckTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.o = schema.load()

    def test_散文の旧い語彙の値を捕まえる(self):
        # 「当初合意内 → 当初スコープ内」のような改名で散文に旧語が残る場合。
        problems = g.check_prose("迷ったら `スコープ: 当初合意内` にする。", self.o)
        self.assertEqual(len(problems), 1)
        self.assertIn("当初合意内", problems[0])

    def test_同名フィールドはどの型の語彙でもよい(self):
        # `種別` は LOG では LOG種別、DEC では決定種別。最初の型の語彙だけで見ない。
        self.assertEqual(g.check_prose("`種別: 契約制約` と `種別: 報告`", self.o), [])
        self.assertEqual(len(g.check_prose("`種別: 存在しない`", self.o)), 1)

    def test_自由記述を許すフィールドの値は照合しない(self):
        self.assertEqual(g.check_prose("`作らない: 管理画面`", self.o), [])

    def test_散文の旧いフィールド名を捕まえる(self):
        problems = g.check_prose("`範囲` が空なら聞く。", self.o)
        self.assertEqual(len(problems), 1)

    def test_宣言どおりの語と英字の表記は通す(self):
        text = ("`スコープ: 判定保留` のあいだ `kime scope-questions` に出る。"
                "`なぜ` と `記録なし` と `決定事項` と `却下理由`。")
        self.assertEqual(g.check_prose(text, self.o), [])

    def test_生成ブロックとコードフェンスの中は見ない(self):
        text = ("```\n`範囲`\n```\n"
                "<!-- generated:types — x -->\n`範囲`\n<!-- /generated -->\n")
        self.assertEqual(g.check_prose(text, self.o), [])

    def test_サンプルの語彙の値を照合する(self):
        text = ("## DEC — 決定事項\n\n```yaml\n---\n"
                "id: DEC-001\ntype: decision\ntitle: t\nstatus: 確定\n決定日: 2026-09-18\n"
                "決定の所在: 顧客PM\n会議体: 定例\n種別: 交渉可能\n引用: q\n信頼度: 逐語あり\n"
                "derived_from: [LOG-20260918-01]\nスコープ: 判定保留\n作らない: 自由に書いた内容\n"
                "代替案:\n  - 案: a\n    却下理由: 記録なし\n    信頼度: たぶん\n---\n```\n")
        problems = g.check_samples(text, self.o)
        self.assertEqual(len(problems), 2, problems)
        self.assertIn("status: 確定", problems[0])
        self.assertIn("信頼度: たぶん", problems[1])

    def test_周辺ファイルのキーと語彙は散文で使ってよい(self):
        text = "`決定権: あり` の役割。`review_required` を立てる。`種別: 新規制約` と `不明`。"
        self.assertEqual(g.check_prose(text, self.o), [])
        self.assertEqual(len(g.check_prose("`決定権: 有り`", self.o)), 1)

    def test_スキルと規約の散文に食い違いが無い(self):
        self.assertEqual(g.check_docs(self.o), [])

    def test_schema_md_の散文とサンプルに食い違いが無い(self):
        text = (schema.KIT_ROOT / "schema.md").read_text(encoding="utf-8")
        self.assertEqual(g.check_samples(text, self.o), [])
        self.assertEqual(g.check_prose(text, self.o), [])


if __name__ == "__main__":
    unittest.main()
