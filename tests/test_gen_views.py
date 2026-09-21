#!/usr/bin/env python3
"""ビュー射影のテスト。"""

import datetime
import unittest

from tests.fixtures import WikiTestCase
from tools import gen_views

TODAY = datetime.date(2026, 9, 18)
LOG = ("LOG", "LOG-20260918-01", {})


class ViewTestCase(WikiTestCase):
    def render(self, cards, name):
        return gen_views.render(self.wiki(cards), name, TODAY)


class HeaderTest(ViewTestCase):
    def test_すべてのビューに手編集禁止の断りがある(self):
        for name in gen_views.VIEWS:
            text = self.render([LOG], name)
            self.assertIn("手編集禁止", text, name)
            self.assertIn("生成基準日: 2026-09-18", text, name)


class OpenItemsTest(ViewTestCase):
    def test_なぜ未記入の決定を出す(self):
        text = self.render([LOG, ("DEC", "DEC-001", {"title": "理由のない決定", "なぜ": ""})],
                           "open-items")
        self.assertIn("理由のない決定", text)

    def test_理由が書かれていれば出さない(self):
        text = self.render([LOG, ("DEC", "DEC-001", {"title": "理由のある決定",
                                                     "なぜ": "狙いがある"})], "open-items")
        section = text.split("## `なぜ` が未記入の決定")[1].split("##")[0]
        self.assertNotIn("理由のある決定", section)

    def test_未決の問いを確認先ごとに束ねる(self):
        text = self.render([LOG, ("Q", "Q-001", {"確認先": "顧客PM"}),
                            ("Q", "Q-002", {"確認先": "顧客法務"})], "open-items")
        self.assertIn("### 確認先: 顧客PM", text)
        self.assertIn("### 確認先: 顧客法務", text)

    def test_解決済みの問いは出さない(self):
        text = self.render([LOG, ("DEC", "DEC-001", {}),
                            ("Q", "Q-001", {"status": "解決", "resolved_by": "DEC-001",
                                            "title": "済んだ問い"})], "open-items")
        self.assertNotIn("済んだ問い", text)

    def test_期限超過のアクションを強調する(self):
        text = self.render([LOG, ("ACT", "ACT-001", {"担当": "甲社", "期限": "2026-09-01"})],
                           "open-items")
        self.assertIn("**超過**", text)

    def test_棚卸し対象は脆弱性高かつ逆リンクありのみ(self):
        text = self.render([LOG,
                            ("DEC", "DEC-001", {"前提": ["ASM-001"]}),
                            ("ASM", "ASM-001", {"内容": "追跡する前提", "脆弱性": "高",
                                                "崩れたら見直す決定": ["DEC-001"]}),
                            ("ASM", "ASM-002", {"内容": "追跡しない前提", "脆弱性": "低",
                                                "崩れたら見直す決定": []})], "open-items")
        section = text.split("## 棚卸し対象の前提")[1].split("##")[0]
        self.assertIn("追跡する前提", section)
        self.assertNotIn("追跡しない前提", section)

    def test_件数のまとめを冒頭に出す(self):
        text = self.render([LOG, ("DEC", "DEC-001", {"範囲": "判定保留"})], "open-items")
        self.assertIn("| 区分 | 件数 |", text)

    def test_空でも壊れない(self):
        text = self.render([], "open-items")
        self.assertIn("（なし）", text)


class AgendaTest(ViewTestCase):
    def test_なぜ未記入を最初に置く(self):
        text = self.render([LOG, ("DEC", "DEC-001", {"なぜ": ""}), ("Q", "Q-001", {})],
                           "agenda-next")
        self.assertLess(text.index("## 0."), text.index("## 1."))
        self.assertIn("`なぜ` が未記入の決定", text.split("## 1.")[0])

    def test_所要の目安を出す(self):
        self.assertIn("所要の目安", self.render([LOG], "agenda-next"))


class IndexTest(ViewTestCase):
    def test_会議ごとの件数を出す(self):
        text = self.render([LOG, ("DEC", "DEC-001", {})], "index")
        self.assertIn("MTG-20260918", text)

    def test_多対多であることを注記する(self):
        self.assertIn("複数の会議に現れるのは正常", self.render([LOG], "index"))

    def test_型ごとの一覧を出す(self):
        text = self.render([LOG, ("DEC", "DEC-001", {})], "index")
        self.assertIn("DEC — 決定事項（1件）", text)
        self.assertIn("TERM — 用語（0件）", text)


class MetricsTest(ViewTestCase):
    def test_なぜの記入率を出す(self):
        text = self.render([LOG, ("DEC", "DEC-001", {"なぜ": "理由"}),
                            ("DEC", "DEC-002", {"なぜ": ""})], "metrics")
        self.assertIn("50% (1/2)", text)

    def test_却下理由記録なしの比率を出す(self):
        text = self.render([LOG, ("DEC", "DEC-001", {"代替案": [
            {"案": "A", "却下理由": "記録なし"}, {"案": "B", "却下理由": "工数"}]})], "metrics")
        self.assertIn("50% (1/2)", text)

    def test_沈黙由来の代替案を数える(self):
        # README の「上乗せ分の取り分」そのもの。カードの信頼度とは別に数える。
        text = self.render([LOG, ("DEC", "DEC-001", {"代替案": [
            {"案": "A", "却下理由": "記録なし", "信頼度": "推測"},
            {"案": "B", "却下理由": "工数", "信頼度": "逐語あり"}]})], "metrics")
        self.assertIn("沈黙由来の代替案", text)
        self.assertRegex(text, r"沈黙由来の代替案.*\| 1 \|")

    def test_引用一致率を品質指標として出さない(self):
        # README が AutoMin 2025 の負の相関を根拠に明確に禁じている。
        text = self.render([LOG], "metrics")
        self.assertIn("引用一致率をここに置かない", text)

    def test_カードが無くても割り算で落ちない(self):
        self.assertIn("—", self.render([], "metrics"))


class GenerateTest(WikiTestCase):
    def test_書き出して二度目は変わらない(self):
        wiki = self.wiki([LOG, ("DEC", "DEC-001", {})])
        written, _ = gen_views.generate(wiki, today=TODAY)
        self.assertEqual(sorted(written), sorted(gen_views.VIEWS))
        written, _ = gen_views.generate(wiki, today=TODAY)
        self.assertEqual(written, [])

    def test_checkは書かずに鮮度を返す(self):
        wiki = self.wiki([LOG, ("DEC", "DEC-001", {})])
        _, stale = gen_views.generate(wiki, today=TODAY, check=True)
        self.assertEqual(sorted(stale), sorted(gen_views.VIEWS))
        self.assertFalse(wiki.views_dir.exists())

    def test_生成後はcheckが通る(self):
        wiki = self.wiki([LOG, ("DEC", "DEC-001", {})])
        gen_views.generate(wiki, today=TODAY)
        _, stale = gen_views.generate(wiki, today=TODAY, check=True)
        self.assertEqual(stale, [])


if __name__ == "__main__":
    unittest.main()
