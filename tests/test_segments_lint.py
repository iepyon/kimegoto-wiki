#!/usr/bin/env python3
"""segments.yaml の機械検査（Pass 1 の出力）。

ここが崩れたまま Pass 2 に進むと、LOG の分割ごとやり直しになる。
これまでスキルの禁止事項として LLM の自制に賭けていた部分。
"""

import unittest

from tests.fixtures import WikiTestCase
from tools import kimelint

GOOD = """\
meeting: MTG-20260918
segments:
  - seq: 1
    title: 前回アクションの確認
    種別: 確認
    時刻: "00:00:00 - 00:06:40"
    参加役割: [顧客PM, 開発リーダ]

  - seq: 2
    title: 認証方式の選定
    種別: 議論
    時刻: "00:06:40 - 00:21:10"
    参加役割: [顧客PM, 開発リーダ]

  - seq: 3
    title: 移行スケジュール
    種別: 議論
    時刻: "00:21:10 - 00:34:52"
    参加役割: [顧客PM]
"""


def ids(problems, check):
    return [p for p in problems if p.check == check]


class 形式(WikiTestCase):

    def run_lint(self, text, check):
        w = self.wiki(segments={"MTG-20260918": text})
        return ids(kimelint.run(w, only={check}), check)

    def test_正しいsegmentsは何も出ない(self):
        self.assertEqual(self.run_lint(GOOD, "segment-format"), [])

    def test_seqが連番でないと落とす(self):
        bad = GOOD.replace("  - seq: 2", "  - seq: 5")
        found = self.run_lint(bad, "segment-format")
        self.assertTrue(any("連番" in p.message for p in found))

    def test_種別が語彙になければ落とす(self):
        bad = GOOD.replace("種別: 議論", "種別: 相談", 1)
        found = self.run_lint(bad, "segment-format")
        self.assertTrue(any("語彙にない" in p.message for p in found))

    def test_時刻の形が違えば落とす(self):
        bad = GOOD.replace('"00:06:40 - 00:21:10"', '"6:40〜21:10"')
        found = self.run_lint(bad, "segment-format")
        self.assertTrue(any("時刻" in p.message for p in found))

    def test_titleが空なら落とす(self):
        bad = GOOD.replace("    title: 認証方式の選定\n", "    title: \n")
        found = self.run_lint(bad, "segment-format")
        self.assertTrue(any("`title` が空" in p.message for p in found))

    def test_会議IDがディレクトリと食い違えば落とす(self):
        bad = GOOD.replace("meeting: MTG-20260918", "meeting: MTG-20260901")
        found = self.run_lint(bad, "segment-format")
        self.assertTrue(any("食い違う" in p.message for p in found))

    def test_壊れたYAMLでも他を巻き添えにしない(self):
        w = self.wiki(segments={"MTG-20260918": "segments:\n\t- seq: 1\n"})
        found = ids(kimelint.run(w, only={"segment-format"}), "segment-format")
        self.assertEqual(len(found), 1)
        self.assertIn("読めない", found[0].message)


class 論点の数と見出し(WikiTestCase):

    def test_範囲内なら鳴らない(self):
        w = self.wiki(segments={"MTG-20260918": GOOD})
        self.assertEqual(ids(kimelint.run(w, only={"segment-count"}), "segment-count"), [])

    def test_少なすぎれば鳴る(self):
        few = """\
meeting: MTG-20260918
segments:
  - seq: 1
    title: 雑談
    種別: 雑談
    時刻: "00:00:00 - 00:01:00"
    参加役割: [顧客PM]
"""
        w = self.wiki(segments={"MTG-20260918": few})
        found = ids(kimelint.run(w, only={"segment-count"}), "segment-count")
        self.assertTrue(any("論点が 1件" in p.message for p in found))

    def test_逸脱理由が書かれていれば鳴らない(self):
        few = """\
meeting: MTG-20260918
segments:
  - seq: 1
    title: 雑談
    種別: 雑談
    時刻: "00:00:00 - 00:01:00"
    参加役割: [顧客PM]
# 逸脱理由: 5分で流会になった
"""
        w = self.wiki(segments={"MTG-20260918": few})
        self.assertEqual(ids(kimelint.run(w, only={"segment-count"}), "segment-count"), [])

    def test_見出しが長すぎれば鳴る(self):
        long_title = "認証方式とデータ移行のスケジュールと権限設計の話をまとめて扱う論点"
        bad = GOOD.replace("title: 認証方式の選定", "title: %s" % long_title)
        w = self.wiki(segments={"MTG-20260918": bad})
        found = ids(kimelint.run(w, only={"segment-count"}), "segment-count")
        self.assertTrue(any("文字を超える" in p.message for p in found))


class 未登録の役割(WikiTestCase):

    def test_未登録の役割で鳴る(self):
        bad = GOOD.replace("参加役割: [顧客PM, 開発リーダ]",
                           "参加役割: [顧客PM, インフラ担当]", 1)
        w = self.wiki(segments={"MTG-20260918": bad})
        found = ids(kimelint.run(w, only={"segment-role"}), "segment-role")
        self.assertEqual(len(found), 1)
        self.assertIn("インフラ担当", found[0].message)

    def test_同じ役割は会議ごとに1件にまとめる(self):
        bad = GOOD.replace("参加役割: [顧客PM, 開発リーダ]",
                           "参加役割: [顧客PM, インフラ担当]")
        w = self.wiki(segments={"MTG-20260918": bad})
        found = ids(kimelint.run(w, only={"segment-role"}), "segment-role")
        self.assertEqual(len(found), 1)

    def test_登録済みなら鳴らない(self):
        w = self.wiki(segments={"MTG-20260918": GOOD})
        self.assertEqual(ids(kimelint.run(w, only={"segment-role"}), "segment-role"), [])


if __name__ == "__main__":
    unittest.main()
