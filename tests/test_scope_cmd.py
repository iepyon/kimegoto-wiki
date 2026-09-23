#!/usr/bin/env python3
"""`kime scope-questions` — 範囲の問いの定型起票。

**二重起票が最大の失敗モード。** 起票済みの問いを見落とすと、次回アジェンダが
同じ問いで埋まり、アジェンダそのものが読まれなくなる。人間が見出しを縮めて
書いた場合も拾えることを確かめる。
"""

import contextlib
import io
import unittest

from tests.fixtures import WikiTestCase
from tools.scope_cmd import main, pending_decisions, plan, question_title


def run(*argv):
    """CLI を回す。報告はテスト出力に混ぜない。"""
    with contextlib.redirect_stdout(io.StringIO()):
        return main(list(argv))


class 起票の対象(WikiTestCase):

    def test_交渉可能と契約制約だけを対象にする(self):
        w = self.wiki([
            ("LOG", "LOG-20260918-01", {}),
            ("DEC", "DEC-001", {"範囲": "判定保留", "種別": "交渉可能"}),
            ("DEC", "DEC-002", {"範囲": "判定保留", "種別": "契約制約",
                                "決定の所在": "顧客法務"}),
            ("DEC", "DEC-003", {"範囲": "判定保留", "種別": "技術判断",
                                "決定の所在": "開発リーダ"}),
        ])
        self.assertEqual([c.id for c in pending_decisions(w)], ["DEC-001", "DEC-002"])

    def test_範囲が判定済みなら対象にしない(self):
        w = self.wiki([
            ("LOG", "LOG-20260918-01", {}),
            ("DEC", "DEC-001", {"範囲": "当初合意内"}),
            ("DEC", "DEC-002", {"範囲": "範囲外(追加)"}),
        ])
        self.assertEqual(pending_decisions(w), [])

    def test_覆された決定は対象にしない(self):
        w = self.wiki([
            ("LOG", "LOG-20260918-01", {}),
            ("DEC", "DEC-001", {"範囲": "判定保留", "status": "覆された"}),
        ])
        self.assertEqual(pending_decisions(w), [])


class 題名と確認先(WikiTestCase):

    def test_題名は定型から作る(self):
        w = self.wiki([("LOG", "LOG-20260918-01", {}),
                       ("DEC", "DEC-001", {"title": "メールは検索対象に含めない",
                                           "範囲": "判定保留"})])
        self.assertEqual(question_title(w, w.get("DEC-001")),
                         "メールは検索対象に含めないは当初合意範囲内か")

    def test_決定の所在が顧客側ならその役割に聞く(self):
        w = self.wiki([("LOG", "LOG-20260918-01", {}),
                       ("DEC", "DEC-001", {"範囲": "判定保留", "決定の所在": "顧客法務",
                                           "種別": "契約制約"})])
        self.assertEqual(plan(w)[0][3], "顧客法務")

    def test_自社側の決定でも顧客側の役割に聞く(self):
        # 範囲の交渉相手は常に顧客側。自社側の役割に問いを立てても誰も答えられない。
        w = self.wiki([("LOG", "LOG-20260918-01", {}),
                       ("DEC", "DEC-001", {"範囲": "判定保留", "決定の所在": "開発リーダ",
                                           "種別": "交渉可能"})])
        self.assertEqual(plan(w)[0][3], "顧客PM")


class 二重起票を防ぐ(WikiTestCase):

    def test_題名が一致する問いがあれば済とする(self):
        w = self.wiki([
            ("LOG", "LOG-20260918-01", {}),
            ("DEC", "DEC-001", {"title": "メールは対象外", "範囲": "判定保留"}),
            ("Q", "Q-001", {"title": "メールは対象外は当初合意範囲内か"}),
        ])
        self.assertEqual(plan(w)[0][2].id, "Q-001")

    def test_見出しを縮めて書かれていても拾う(self):
        # 人間は決定の見出しを縮めて書く。完全一致だけで見ると二重起票する。
        w = self.wiki([
            ("LOG", "LOG-20260918-01", {}),
            ("DEC", "DEC-001", {"title": "検索の権限は部署単位に丸め、"
                                         "プロジェクト単位のフォルダは対象外とする",
                                "範囲": "判定保留"}),
            ("Q", "Q-001", {"title": "検索の権限は部署単位に丸めるは当初合意範囲内か"}),
        ])
        self.assertEqual(plan(w)[0][2].id, "Q-001")

    def test_接尾辞が違う問いは別物として扱う(self):
        w = self.wiki([
            ("LOG", "LOG-20260918-01", {}),
            ("DEC", "DEC-001", {"範囲": "判定保留"}),
            ("Q", "Q-001", {"title": "権限の単位をどうするか"}),
        ])
        self.assertIsNone(plan(w)[0][2])

    def test_同じLOGから生えた別の範囲問いを取り違えない(self):
        # 1つの LOG から複数の決定が生えることがある。題名の完全一致を優先する。
        w = self.wiki([
            ("LOG", "LOG-20260918-01", {}),
            ("DEC", "DEC-001", {"title": "甲を採る", "範囲": "判定保留"}),
            ("Q", "Q-001", {"title": "乙を採るは当初合意範囲内か"}),
            ("Q", "Q-002", {"title": "甲を採るは当初合意範囲内か"}),
        ])
        self.assertEqual(plan(w)[0][2].id, "Q-002")


class 起票(WikiTestCase):

    def test_writeでカードができて引用を写す(self):
        w = self.wiki([
            ("LOG", "LOG-20260918-01", {}),
            ("DEC", "DEC-001", {"title": "メールは対象外", "範囲": "判定保留",
                                "引用": "じゃあそれでいきましょう"}),
        ])
        self.assertEqual(run("--root", str(w.root), "--write"), 0)
        created = (w.root / "questions" / "Q-001.md").read_text(encoding="utf-8")
        self.assertIn("title: メールは対象外は当初合意範囲内か", created)
        self.assertIn("確認先: 顧客PM", created)
        self.assertIn("引用: じゃあそれでいきましょう", created)
        self.assertIn("derived_from: [LOG-20260918-01]", created)
        self.assertIn("初出: 2026-09-18", created)

    def test_writeなしではカードを作らない(self):
        w = self.wiki([
            ("LOG", "LOG-20260918-01", {}),
            ("DEC", "DEC-001", {"範囲": "判定保留"}),
        ])
        self.assertEqual(run("--root", str(w.root)), 0)
        self.assertFalse((w.root / "questions" / "Q-001.md").exists())

    def test_二度回しても増えない(self):
        w = self.wiki([
            ("LOG", "LOG-20260918-01", {}),
            ("DEC", "DEC-001", {"title": "メールは対象外", "範囲": "判定保留"}),
        ])
        run("--root", str(w.root), "--write")
        run("--root", str(w.root), "--write")
        self.assertEqual(len(list((w.root / "questions").glob("Q-*.md"))), 1)


if __name__ == "__main__":
    unittest.main()
