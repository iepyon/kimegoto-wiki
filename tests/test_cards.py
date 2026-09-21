#!/usr/bin/env python3
"""記録層のテスト。"""

import tempfile
import unittest
from pathlib import Path

from tests.fixtures import WikiTestCase, build, card_text
from tools.cards import Wiki, dump_frontmatter, parse_card, render_card, resolve_root
from tools import schema


class LoadTest(WikiTestCase):
    def test_型ごとに数えられる(self):
        w = self.wiki([("LOG", "LOG-20260918-01", {}), ("DEC", "DEC-001", {}),
                       ("DEC", "DEC-002", {}), ("Q", "Q-001", {})])
        self.assertEqual(w.counts()["DEC"], 2)
        self.assertEqual(w.counts()["TERM"], 0)

    def test_IDで引ける(self):
        w = self.wiki([("DEC", "DEC-001", {})])
        self.assertEqual(w.get("DEC-001").type, "DEC")
        self.assertIsNone(w.get("DEC-999"))

    def test_見出しは型ごとに違うフィールドから取る(self):
        w = self.wiki([("DEC", "DEC-001", {"title": "OIDC に寄せる"}),
                       ("CON", "CON-001", {}), ("TERM", "TERM-001", {})])
        o = w.ontology
        self.assertEqual(w.get("DEC-001").headline(o), "OIDC に寄せる")
        self.assertEqual(w.get("CON-001").headline(o), "顧客側VPNは固定IPのみ")
        self.assertEqual(w.get("TERM-001").headline(o), "OIDC")

    def test_会議を拾う(self):
        w = self.wiki([("LOG", "LOG-20260918-01", {})])
        self.assertEqual(list(w.meetings), ["MTG-20260918"])
        self.assertEqual(w.meetings["MTG-20260918"].date, "2026-09-18")
        self.assertEqual(len(w.logs_of("MTG-20260918")), 1)

    def test_複数会議は最新を取れる(self):
        w = self.wiki([("LOG", "LOG-20260918-01", {}),
                       ("LOG", "LOG-20261002-01", {"meeting": "MTG-20261002"})])
        self.assertEqual(w.latest_meeting().id, "MTG-20261002")

    def test_採番は最大値プラス1(self):
        w = self.wiki([("DEC", "DEC-001", {}), ("DEC", "DEC-014", {})])
        self.assertEqual(w.next_id("DEC"), "DEC-015")

    def test_カードが無ければ001から(self):
        self.assertEqual(self.wiki().next_id("ACT"), "ACT-001")

    def test_欠番は詰めない(self):
        # 取り下げた番号は欠番として残す規約。003 を消しても 004 は再利用されない。
        w = self.wiki([("DEC", "DEC-001", {}), ("DEC", "DEC-004", {})])
        self.assertEqual(w.next_id("DEC"), "DEC-005")


class ValueContractTest(WikiTestCase):
    """素の文字列契約 — None を返さない。"""

    def test_空欄は空文字(self):
        w = self.wiki([("DEC", "DEC-001", {"なぜ": ""})])
        self.assertEqual(w.get("DEC-001").get("なぜ"), "")

    def test_宣言に無いキーも空文字(self):
        w = self.wiki([("DEC", "DEC-001", {})])
        self.assertEqual(w.get("DEC-001").get("存在しない"), "")

    def test_listは必ずリスト(self):
        w = self.wiki([("DEC", "DEC-001", {"前提": []})])
        card = w.get("DEC-001")
        self.assertEqual(card.list("前提"), [])
        self.assertEqual(card.list("制約"), [])

    def test_単一値でもリストで返す(self):
        w = self.wiki([("DEC", "DEC-001", {"前提": "ASM-001"})])
        self.assertEqual(w.get("DEC-001").list("前提"), ["ASM-001"])

    def test_structsはdictのリスト(self):
        w = self.wiki([("DEC", "DEC-001", {"代替案": [
            {"案": "自前実装", "却下理由": "記録なし", "信頼度": "推測"}]})])
        alts = w.get("DEC-001").structs("代替案")
        self.assertEqual(alts[0]["案"], "自前実装")
        self.assertEqual(w.get("DEC-001").structs("存在しない"), [])


class BrokenFrontmatterTest(WikiTestCase):
    """壊れたカードを握りつぶさない。"""

    def _broken(self, text):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "decisions").mkdir(parents=True)
        (root / "decisions" / "DEC-001.md").write_text(text, encoding="utf-8")
        return Wiki(root)

    def test_壊れたカードもカードとして残る(self):
        w = self._broken("---\nid: DEC-001\nこれはただの文\n---\n")
        self.assertEqual(len(w.cards), 1)
        self.assertEqual(len(w.broken), 1)
        self.assertEqual(w.broken[0].id, "DEC-001")

    def test_壊れたカードは行番号を持つ(self):
        w = self._broken("---\nid: DEC-001\nこれはただの文\n---\n")
        self.assertEqual(w.broken[0].error.line, 3)

    def test_frontmatterが無ければ壊れ扱い(self):
        w = self._broken("# 見出しだけ\n")
        self.assertEqual(len(w.broken), 1)

    def test_健全なカードは壊れに入らない(self):
        w = self.wiki([("DEC", "DEC-001", {})])
        self.assertEqual(w.broken, [])


class StrayTest(unittest.TestCase):
    def test_IDが型に合わないファイルは迷子になる(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "decisions").mkdir(parents=True)
            (root / "decisions" / "メモ.md").write_text("---\nid: メモ\n---\n", encoding="utf-8")
            w = Wiki(root)
            self.assertEqual(w.cards, [])
            self.assertEqual([p.name for p in w.stray], ["メモ.md"])

    def test_READMEは迷子に数えない(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "decisions").mkdir(parents=True)
            (root / "decisions" / "README.md").write_text("# 説明\n", encoding="utf-8")
            self.assertEqual(Wiki(root).stray, [])


class UtteranceTest(WikiTestCase):
    def test_発言行を拾う(self):
        w = self.wiki([("LOG", "LOG-20260918-01", {}, """\
## 発言

- **顧客PM**: ADに繋ぐのは厳しいですね
- **(沈黙 約6秒)**
- **開発リーダ**: OIDCに寄せる手もあります
""")])
        utterances = w.get("LOG-20260918-01").utterances
        self.assertEqual(len(utterances), 2)
        self.assertEqual(utterances[0], ("顧客PM", "ADに繋ぐのは厳しいですね"))

    def test_沈黙の注記は発言でも違反でもない(self):
        w = self.wiki([("LOG", "LOG-20260918-01", {}, "## 発言\n\n- **(沈黙 約6秒)**\n")])
        card = w.get("LOG-20260918-01")
        self.assertEqual(card.utterances, [])
        self.assertEqual(card.malformed_utterance_lines, [])

    def test_形式違反の行を拾う(self):
        w = self.wiki([("LOG", "LOG-20260918-01", {}, "## 発言\n\n- 顧客PM: 役割が太字でない\n")])
        self.assertEqual(len(w.get("LOG-20260918-01").malformed_utterance_lines), 1)

    def test_発言節の外は見ない(self):
        w = self.wiki([("LOG", "LOG-20260918-01", {}, """\
## 発言

- **顧客PM**: 本物の発言

## 確定した事実

- 利用者規模：当面50人
""")])
        card = w.get("LOG-20260918-01")
        self.assertEqual(len(card.utterances), 1)
        self.assertEqual(card.malformed_utterance_lines, [])

    def test_LOG以外は発言を持たない(self):
        w = self.wiki([("DEC", "DEC-001", {})])
        self.assertEqual(w.get("DEC-001").utterances, [])


class RoleMappingTest(WikiTestCase):
    def test_役割を引ける(self):
        w = self.wiki()
        self.assertEqual(w.role("顧客PM")["決定権"], "あり")
        self.assertEqual(w.role("開発メンバー")["決定権"], "なし")

    def test_未登録の役割は既定値にフォールバック(self):
        w = self.wiki()
        self.assertFalse(w.is_known_role("謎の役割"))
        self.assertEqual(w.role("謎の役割")["決定権"], "なし")

    def test_社名を集められる(self):
        self.assertEqual(self.wiki().companies, {"ESM", "甲社", "乙社"})


class RenderTest(unittest.TestCase):
    def test_書き出して読み直せる(self):
        data = {"id": "DEC-001", "type": "decision", "title": "決定",
                "前提": ["ASM-001", "ASM-002"], "制約": [], "なぜ": "",
                "代替案": [{"案": "自前実装", "却下理由": "記録なし"}]}
        text = render_card(data, "## 補足\n\n本文。\n")
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "DEC-001.md"
            path.write_text(text, encoding="utf-8")
            card = parse_card(path, schema.load())
        self.assertIsNone(card.error)
        self.assertEqual(card.list("前提"), ["ASM-001", "ASM-002"])
        self.assertEqual(card.list("制約"), [])
        self.assertEqual(card.get("なぜ"), "")
        self.assertEqual(card.structs("代替案")[0]["案"], "自前実装")
        self.assertIn("## 補足", card.body)

    def test_コロンを含む値はクォートされる(self):
        text = dump_frontmatter({"時刻": "00:21:10 - 00:34:52"})
        self.assertEqual(text, '時刻: "00:21:10 - 00:34:52"')

    def test_日本語の値はクォートしない(self):
        self.assertEqual(dump_frontmatter({"却下理由": "顧客側VPNが固定IPのみ"}),
                         "却下理由: 顧客側VPNが固定IPのみ")

    def test_空欄はキーだけ残す(self):
        self.assertEqual(dump_frontmatter({"なぜ": ""}), "なぜ:")

    def test_順序を指定できる(self):
        got = dump_frontmatter({"b": "2", "a": "1"}, order=["a", "b", "無い"])
        self.assertEqual(got, "a: 1\nb: 2")


class ResolveRootTest(unittest.TestCase):
    def test_明示指定が最優先(self):
        self.assertEqual(resolve_root("/tmp"), Path("/tmp").resolve())

    def test_環境変数を見る(self):
        import os
        os.environ["GIJI_ROOT"] = "/tmp"
        self.addCleanup(os.environ.pop, "GIJI_ROOT", None)
        self.assertEqual(resolve_root(), Path("/tmp").resolve())

    def test_既定はexample案件(self):
        # 開発者の手元の .env に引きずられないよう、キットのルートごと差し替える。
        import os
        from unittest import mock
        os.environ.pop("GIJI_ROOT", None)
        with tempfile.TemporaryDirectory() as tmp:
            kit = Path(tmp)
            (kit / "projects" / "example").mkdir(parents=True)
            with mock.patch.object(schema, "KIT_ROOT", kit):
                self.assertEqual(resolve_root().name, "example")

    def test_envのCURRENT_PROJECTを見る(self):
        import os
        from unittest import mock
        os.environ.pop("GIJI_ROOT", None)
        with tempfile.TemporaryDirectory() as tmp:
            kit = Path(tmp)
            (kit / "projects" / "other").mkdir(parents=True)
            (kit / ".env").write_text("CURRENT_PROJECT=other\n", encoding="utf-8")
            with mock.patch.object(schema, "KIT_ROOT", kit):
                self.assertEqual(resolve_root().name, "other")


if __name__ == "__main__":
    unittest.main()
