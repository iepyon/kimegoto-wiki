#!/usr/bin/env python3
"""`giji unknown-terms` — 未知語の候補拾い。

**計数を機械に寄せるのが目的**なので、回数がずれないことを一番に見る。
判断（一般語かどうか、表記崩れか新規か）はここではしない。
"""

import unittest

from tests.fixtures import WikiTestCase
from tools.terms_cmd import candidates


def log(body):
    return ("LOG", "LOG-20260918-01", {}, "## 発言\n\n" + body)


class 計数と閾値(WikiTestCase):

    def test_閾値未満は出さない(self):
        w = self.wiki([log("- **顧客PM**: オイデッシーの話\n"
                           "- **顧客PM**: オイデッシーはどうか\n")])
        self.assertEqual([r["語"] for r in candidates(w, "MTG-20260918")], [])

    def test_閾値に達したら出す(self):
        w = self.wiki([log("- **顧客PM**: オイデッシーの話\n"
                           "- **顧客PM**: オイデッシーはどうか\n"
                           "- **開発リーダ**: オイデッシーで進めます\n")])
        rows = candidates(w, "MTG-20260918")
        self.assertEqual([r["語"] for r in rows], ["オイデッシー"])
        self.assertEqual(rows[0]["出現回数"], 3)

    def test_同じ発言に2回出ても数える(self):
        w = self.wiki([log("- **顧客PM**: オイデッシーとオイデッシーを比べる\n"
                           "- **顧客PM**: オイデッシーにします\n")])
        self.assertEqual(candidates(w, "MTG-20260918")[0]["出現回数"], 3)

    def test_初出と文脈は最初に現れたLOGと発言(self):
        w = self.wiki([
            ("LOG", "LOG-20260918-01", {}, "## 発言\n\n- **顧客PM**: pgvectorの件です\n"),
            ("LOG", "LOG-20260918-02", {}, "## 発言\n\n"
             "- **顧客PM**: pgvectorは使えない\n- **開発リーダ**: pgvectorの代わりを探す\n"),
        ])
        row = candidates(w, "MTG-20260918")[0]
        self.assertEqual(row["初出"], "LOG-20260918-01")
        self.assertEqual(row["文脈"], "pgvectorの件です")


class 対象の絞り込み(WikiTestCase):

    def test_用語集にある語は出さない(self):
        w = self.wiki([
            ("TERM", "TERM-001", {"正式": "OIDC", "表記揺れ": ["オイデッシー"]}),
            log("- **顧客PM**: オイデッシーの話\n"
                "- **顧客PM**: オイデッシーはどうか\n"
                "- **顧客PM**: オイデッシーにします\n"),
        ])
        self.assertEqual(candidates(w, "MTG-20260918"), [])

    def test_漢字とカタカナの複合語を割らない(self):
        w = self.wiki([log("- **顧客PM**: 権限マトリクスを送ります\n"
                           "- **顧客PM**: 権限マトリクスは確認しました\n"
                           "- **顧客PM**: 権限マトリクスの続きです\n")])
        self.assertEqual([r["語"] for r in candidates(w, "MTG-20260918")],
                         ["権限マトリクス"])

    def test_独立して多く出る短い語は残す(self):
        w = self.wiki([log("- **顧客PM**: 権限マトリクスを送ります\n"
                           "- **顧客PM**: 権限マトリクスは確認しました\n"
                           "- **顧客PM**: 権限マトリクスの続きです\n"
                           "- **顧客PM**: マトリクスだけ見ます\n"
                           "- **顧客PM**: マトリクスが要ります\n")])
        self.assertEqual({r["語"] for r in candidates(w, "MTG-20260918")},
                         {"権限マトリクス", "マトリクス"})

    def test_ひらがなだけの語は拾わない(self):
        w = self.wiki([log("- **顧客PM**: そうですね\n" * 4)])
        self.assertEqual(candidates(w, "MTG-20260918"), [])

    def test_英字の製品名を拾う(self):
        w = self.wiki([log("- **顧客PM**: pgvectorです\n"
                           "- **顧客PM**: pgvectorを入れます\n"
                           "- **顧客PM**: pgvectorは無理です\n")])
        self.assertIn("pgvector", [r["語"] for r in candidates(w, "MTG-20260918")])

    def test_多い順に並ぶ(self):
        w = self.wiki([log("- **顧客PM**: pgvectorとベクタディービー\n"
                           "- **顧客PM**: pgvectorとベクタディービー\n"
                           "- **顧客PM**: pgvectorとベクタディービー\n"
                           "- **顧客PM**: pgvectorだけ\n")])
        rows = candidates(w, "MTG-20260918")
        self.assertEqual(rows[0]["語"], "pgvector")
        self.assertGreaterEqual(rows[0]["出現回数"], rows[-1]["出現回数"])


if __name__ == "__main__":
    unittest.main()
