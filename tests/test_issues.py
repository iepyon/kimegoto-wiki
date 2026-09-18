#!/usr/bin/env python3
"""Issue 下書きのテスト。gh は呼ばない。"""

import unittest

from tests.fixtures import WikiTestCase
from tools import issues

LOG = ("LOG", "LOG-20260918-01", {})


class RenderTest(WikiTestCase):
    def test_由来を必ず入れる(self):
        w = self.wiki([LOG, ("DEC", "DEC-001", {"なぜ": "失効保証を IdP に寄せるため"}),
                       ("ACT", "ACT-001", {"title": "情シスに確認する", "関連": ["DEC-001"],
                                           "担当": "甲社", "期限": "2026-10-02"})])
        body = issues.render(w, w.get("ACT-001"))
        self.assertIn("情シスに確認する", body)
        self.assertIn("失効保証を IdP に寄せるため", body)
        self.assertIn("ACT-001", body)
        self.assertIn("DEC-001", body)
        self.assertIn("LOG-20260918-01", body)
        self.assertIn("MTG-20260918", body)

    def test_関連が無くても壊れない(self):
        w = self.wiki([LOG, ("ACT", "ACT-001", {})])
        self.assertIn("関連するカードの記録なし", issues.render(w, w.get("ACT-001")))

    def test_引用を完了条件に置く(self):
        w = self.wiki([LOG, ("ACT", "ACT-001", {"引用": "こちらで確認しておきます"})])
        self.assertIn("> こちらで確認しておきます", issues.render(w, w.get("ACT-001")))


class TargetTest(WikiTestCase):
    def test_IDで選べる(self):
        w = self.wiki([LOG, ("ACT", "ACT-001", {}), ("ACT", "ACT-002", {})])
        self.assertEqual([c.id for c in issues.targets(w, ["ACT-002"])], ["ACT-002"])

    def test_未完了だけを選べる(self):
        w = self.wiki([LOG, ("ACT", "ACT-001", {"status": "完了"}),
                       ("ACT", "ACT-002", {"status": "進行中"})])
        self.assertEqual([c.id for c in issues.targets(w, all_open=True)], ["ACT-002"])

    def test_存在しないIDは例外(self):
        w = self.wiki([LOG, ("ACT", "ACT-001", {})])
        with self.assertRaises(KeyError):
            issues.targets(w, ["ACT-999"])

    def test_指定が無ければ空(self):
        w = self.wiki([LOG, ("ACT", "ACT-001", {})])
        self.assertEqual(issues.targets(w), [])


class WriteBackTest(WikiTestCase):
    def test_issueを書き戻す(self):
        w = self.wiki([LOG, ("ACT", "ACT-001", {})])
        card = w.get("ACT-001")
        self.assertTrue(issues.write_back(card, "https://example.com/1"))
        self.assertIn("issue: https://example.com/1",
                      card.path.read_text(encoding="utf-8"))

    def test_フィールドが無くても足せる(self):
        w = self.wiki([LOG, ("ACT", "ACT-001", {"issue": None})])
        card = w.get("ACT-001")
        self.assertNotIn("issue", card.data)
        self.assertTrue(issues.write_back(card, "https://example.com/1"))
        self.assertIn("issue: https://example.com/1", card.path.read_text(encoding="utf-8"))

    def test_他の行を壊さない(self):
        w = self.wiki([LOG, ("ACT", "ACT-001", {"担当": "甲社"})])
        card = w.get("ACT-001")
        issues.write_back(card, "https://example.com/1")
        text = card.path.read_text(encoding="utf-8")
        self.assertIn("id: ACT-001", text)
        self.assertIn("担当: 甲社", text)


class DryRunTest(WikiTestCase):
    def test_createなしでは何も起票しない(self):
        w = self.wiki([LOG, ("ACT", "ACT-001", {})])
        before = w.get("ACT-001").path.read_text(encoding="utf-8")
        issues.main(["--root", str(w.root), "--act", "ACT-001"])
        self.assertEqual(w.get("ACT-001").path.read_text(encoding="utf-8"), before)

    def test_起票済みは飛ばす(self):
        w = self.wiki([LOG, ("ACT", "ACT-001", {"issue": "owner/repo#1"})])
        self.assertEqual(issues.main(["--root", str(w.root), "--act", "ACT-001"]), 0)

    def test_createにはrepoが要る(self):
        w = self.wiki([LOG, ("ACT", "ACT-001", {})])
        self.assertEqual(issues.main(["--root", str(w.root), "--act", "ACT-001", "--create"]), 2)


if __name__ == "__main__":
    unittest.main()
