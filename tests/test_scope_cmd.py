#!/usr/bin/env python3
"""`kime scope-questions` — スコープの確認は決定の `スコープ: 判定保留` の射影で、カードにしない。

条件・文面・確認先が一意に決まることと、アジェンダ・議事録・確認②が同じ写像を
使うことを確かめる。決定の `スコープ` を書けば消える（閉じる操作が要らない）。
"""

import contextlib
import io
import unittest

from tests.fixtures import WikiTestCase
from tools import gen_views
from tools.bundle import Bundle
from tools.scope_cmd import confirm_to, main, pending_decisions, plan, question_title

LOG = ("LOG", "LOG-20260918-01", {})


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = main(list(argv))
    return code, out.getvalue()


class 対象(WikiTestCase):

    def test_交渉可能と契約制約だけを対象にする(self):
        w = self.wiki([LOG,
                       ("DEC", "DEC-001", {"スコープ": "判定保留", "種別": "交渉可能"}),
                       ("DEC", "DEC-002", {"スコープ": "判定保留", "種別": "契約制約",
                                           "決定の所在": "顧客法務"}),
                       ("DEC", "DEC-003", {"スコープ": "判定保留", "種別": "技術判断",
                                           "決定の所在": "開発リーダ"})])
        self.assertEqual([c.id for c in pending_decisions(w)], ["DEC-001", "DEC-002"])

    def test_スコープを書けば消える(self):
        w = self.wiki([LOG, ("DEC", "DEC-001", {"スコープ": "当初スコープ内"}),
                       ("DEC", "DEC-002", {"スコープ": "スコープ外(追加)"})])
        self.assertEqual(pending_decisions(w), [])

    def test_覆された決定は対象にしない(self):
        w = self.wiki([LOG, ("DEC", "DEC-001", {"スコープ": "判定保留", "status": "覆された"})])
        self.assertEqual(pending_decisions(w), [])

    def test_会議で絞れる(self):
        w = self.wiki([LOG, ("LOG", "LOG-20260904-01", {"meeting": "MTG-20260904"}),
                       ("DEC", "DEC-001", {"スコープ": "判定保留"}),
                       ("DEC", "DEC-002", {"スコープ": "判定保留",
                                           "derived_from": ["LOG-20260904-01"]})])
        self.assertEqual([c.id for c in pending_decisions(w, "MTG-20260918")], ["DEC-001"])


class 文面と確認先(WikiTestCase):

    def test_題名は定型から作る(self):
        w = self.wiki([LOG, ("DEC", "DEC-001", {"title": "メールは検索対象に含めない",
                                                "スコープ": "判定保留"})])
        self.assertEqual(question_title(w, w.get("DEC-001")),
                         "メールは検索対象に含めないは当初スコープ内か")

    def test_決定の所在が顧客側ならその役割に聞く(self):
        w = self.wiki([LOG, ("DEC", "DEC-001", {"スコープ": "判定保留", "決定の所在": "顧客法務",
                                                "種別": "契約制約"})])
        self.assertEqual(confirm_to(w, w.get("DEC-001")), "顧客法務")

    def test_自社側の決定でも顧客側の役割に聞く(self):
        w = self.wiki([LOG, ("DEC", "DEC-001", {"スコープ": "判定保留", "決定の所在": "開発リーダ",
                                                "種別": "交渉可能"})])
        self.assertEqual(confirm_to(w, w.get("DEC-001")), "顧客PM")

    def test_planは決定と文面と確認先を返す(self):
        w = self.wiki([LOG, ("DEC", "DEC-001", {"title": "画面は10本", "スコープ": "判定保留"})])
        [(c, title, to)] = plan(w)
        self.assertEqual((c.id, title, to), ("DEC-001", "画面は10本は当初スコープ内か", "顧客PM"))


class 射影(WikiTestCase):
    """カードは作らない。アジェンダ・議事録・確認②・ビューが同じ写像で出す。"""

    def cards(self):
        return [LOG, ("DEC", "DEC-001", {"title": "画面は10本", "スコープ": "判定保留"})]

    def test_CLIはカードを作らず一覧だけ出す(self):
        w = self.wiki(self.cards())
        code, out = run("--root", str(w.root))
        self.assertEqual(code, 0)
        self.assertIn("DEC-001  画面は10本は当初スコープ内か（確認先: 顧客PM）", out)
        self.assertEqual(self.wiki_at(w.root).by_type("Q"), [])

    def test_アジェンダの材料にスコープの確認の節が出る(self):
        text = Bundle(self.wiki(self.cards())).agenda_input()
        section = text.split("## スコープの確認")[1].split("\n## ")[0]
        self.assertIn("DEC-001 画面は10本は当初スコープ内か（確認先: 顧客PM", section)

    def test_アジェンダのビューにも出る(self):
        text = gen_views.render(self.wiki(self.cards()), "agenda-next")
        self.assertIn("画面は10本は当初スコープ内か", text.split("## 1.")[1].split("## 2.")[0])

    def test_議事録の未決事項の末尾に出る(self):
        text = Bundle(self.wiki(self.cards())).minutes_input("MTG-20260918")
        section = text.split("## 未決事項")[1].split("\n## ")[0]
        self.assertIn("### スコープの確認", section)
        self.assertIn("DEC-001 画面は10本は当初スコープ内か（確認先: 顧客PM）", section)

    def test_顧客提出版ではIDを落とし社名に丸める(self):
        text = Bundle(self.wiki(self.cards())).minutes_input("MTG-20260918", "customer")
        section = text.split("## 未決事項")[1].split("\n## ")[0]
        self.assertIn("画面は10本は当初スコープ内か（確認先: 甲社）", section)
        self.assertNotIn("DEC-001", section)

    def test_確認2の2_0に確認先が出る(self):
        text = Bundle(self.wiki(self.cards())).review("MTG-20260918")
        section = text.split("## 2-0")[1].split("## 2-1")[0]
        self.assertIn("| DEC-001 | 画面は10本 | 交渉可能 | 顧客PM |", section)
        self.assertNotIn("scope-questions", section)

    def test_スコープを書けば全部から消える(self):
        w = self.wiki([LOG, ("DEC", "DEC-001", {"title": "画面は10本", "スコープ": "当初スコープ内"})])
        self.assertNotIn("当初スコープ内か", Bundle(w).agenda_input())
        self.assertNotIn("当初スコープ内か", Bundle(w).minutes_input("MTG-20260918"))


if __name__ == "__main__":
    unittest.main()
