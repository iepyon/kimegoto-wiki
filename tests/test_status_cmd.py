#!/usr/bin/env python3
"""`kime status` — いまの会議と、次にやることを機械が決める。

利用者に会議 ID と手順の順番を覚えさせないための道具。「済んだ」とは言わず、
残っているものだけを数えることを確かめる（人間の判断が済んだかは機械に分からない）。
"""

import contextlib
import io
import unittest

from tests.fixtures import WikiTestCase
from tools.status_cmd import Status, main, render

SEGMENTS = """\
meeting: MTG-20260918
segments:
  - seq: 1
    title: 認証方式の選定
    種別: 議論
    時刻: "00:00:00 - 00:10:00"
    参加役割: [顧客PM, 開発リーダ]
  - seq: 2
    title: 次回日程
    種別: 確認
    時刻: "00:10:00 - 00:11:00"
    参加役割: [顧客PM, 開発リーダ]
"""


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = main(list(argv))
    return code, out.getvalue()


def rows(status):
    return dict(status.rows)


class いまの会議(WikiTestCase):

    def test_最新の会議ディレクトリを使う(self):
        w = self.wiki([("LOG", "LOG-20260904-01", {"meeting": "MTG-20260904"}),
                       ("LOG", "LOG-20260918-01", {})])
        code, out = run("--root", str(w.root), "--id")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "MTG-20260918")

    def test_会議が無くても落ちずに置き場を案内する(self):
        w = self.wiki([])
        text = render(w)
        self.assertIn("会議が1つも無い", text)
        self.assertIn("transcript.md", text)
        self.assertIn("次回アジェンダ", text)

    def test_無い会議を指すと_2_で止まる(self):
        w = self.wiki([("LOG", "LOG-20260918-01", {})])
        with contextlib.redirect_stderr(io.StringIO()):
            code, _ = run("--root", str(w.root), "--meeting", "MTG-20990101")
        self.assertEqual(code, 2)


class 次にやること(WikiTestCase):

    def _transcript(self, w, meeting="MTG-20260918"):
        d = w.root / "meetings" / meeting
        d.mkdir(parents=True, exist_ok=True)
        (d / "transcript.md").write_text("# %s\n" % meeting, encoding="utf-8")

    def test_文字起こしだけなら_Pass_1(self):
        w = self.wiki([])
        self._transcript(w)
        s = Status(self.wiki_at(w.root), "MTG-20260918")
        self.assertEqual(rows(s)["Pass 1 論点"], "未")
        self.assertIn("/segment", s.next_step)

    def test_論点より_LOG_が少なければ_Pass_2(self):
        w = self.wiki([("LOG", "LOG-20260918-01", {})], segments={"MTG-20260918": SEGMENTS})
        self._transcript(w)
        s = Status(self.wiki_at(w.root), "MTG-20260918")
        self.assertEqual(rows(s)["Pass 2 LOG"], "1 / 2")
        self.assertIn("/log-cards", s.next_step)
        self.assertIn("残り 1", s.next_step)

    def test_カードも理由も無い論点が残りに出る(self):
        w = self.wiki([("LOG", "LOG-20260918-01", {}),
                       ("LOG", "LOG-20260918-02", {"種別": "確認"}),
                       ("DEC", "DEC-001", {"derived_from": ["LOG-20260918-01"]})],
                      segments={"MTG-20260918": SEGMENTS})
        self._transcript(w)
        s = Status(self.wiki_at(w.root), "MTG-20260918")
        self.assertIn("残り: LOG-20260918-02", rows(s)["Pass 3 抽出"])
        self.assertIn("/extract", s.next_step)

    def test_報告の論点は_Pass_3_の残りに数えない(self):
        w = self.wiki([("LOG", "LOG-20260918-01", {}),
                       ("LOG", "LOG-20260918-02", {"種別": "報告"}),
                       ("DEC", "DEC-001", {"derived_from": ["LOG-20260918-01"]})],
                      segments={"MTG-20260918": SEGMENTS})
        self._transcript(w)
        s = Status(self.wiki_at(w.root), "MTG-20260918")
        self.assertNotIn("残り", rows(s)["Pass 3 抽出"])

    def test_理由が書かれた論点は残りに数えず_review_required_は注記する(self):
        w = self.wiki([("LOG", "LOG-20260918-01", {}),
                       ("LOG", "LOG-20260918-02", {"種別": "確認"}),
                       ("DEC", "DEC-001", {"derived_from": ["LOG-20260918-01"]})],
                      segments={"MTG-20260918": SEGMENTS})
        self._transcript(w)
        (w.root / "meetings" / "MTG-20260918" / "extraction-notes.yaml").write_text(
            "meeting: MTG-20260918\nnotes:\n  - log: LOG-20260918-02\n    review_required: true\n",
            encoding="utf-8")
        s = Status(self.wiki_at(w.root), "MTG-20260918")
        self.assertNotIn("残り", rows(s)["Pass 3 抽出"])
        self.assertIn("review_required", rows(s)["Pass 3 抽出"])
        self.assertNotIn("/extract", s.next_step)

    def test_範囲の問いが未起票なら_scope_questions(self):
        w = self.wiki([("LOG", "LOG-20260918-01", {}),
                       ("LOG", "LOG-20260918-02", {"種別": "確認"}),
                       ("DEC", "DEC-001", {"範囲": "判定保留"}),
                       ("ACT", "ACT-001", {"derived_from": ["LOG-20260918-02"]})],
                      segments={"MTG-20260918": SEGMENTS})
        self._transcript(w)
        s = Status(self.wiki_at(w.root), "MTG-20260918")
        self.assertIn("未起票 1", rows(s)["範囲の問い"])
        self.assertIn("scope-questions", s.next_step)

    def test_機械の段が全部通れば確認2へ(self):
        w = self.wiki([("LOG", "LOG-20260918-01", {}),
                       ("LOG", "LOG-20260918-02", {"種別": "確認"}),
                       ("DEC", "DEC-001", {}),
                       ("ACT", "ACT-001", {"derived_from": ["LOG-20260918-02"]})],
                      segments={"MTG-20260918": SEGMENTS})
        self._transcript(w)
        s = Status(self.wiki_at(w.root), "MTG-20260918")
        self.assertIn("/review", s.next_step)
        self.assertIn("なぜ未記入 1", rows(s)["確認②"])
        self.assertIn("担当・期限の空欄 1", rows(s)["確認②"])
        self.assertIn("確定日が未記入の決定 1", rows(s)["議事録"])

    def test_確認2で見るものが無ければ議事録へ(self):
        w = self.wiki([("LOG", "LOG-20260918-01", {}),
                       ("LOG", "LOG-20260918-02", {"種別": "確認"}),
                       ("DEC", "DEC-001", {"なぜ": "固定IPなので", "確定日": "2026-09-25"}),
                       ("ACT", "ACT-001", {"derived_from": ["LOG-20260918-02"],
                                           "担当": "ESM", "期限": "2026-10-02"})],
                      segments={"MTG-20260918": SEGMENTS})
        self._transcript(w)
        s = Status(self.wiki_at(w.root), "MTG-20260918")
        self.assertIn("/minutes", s.next_step)

    def test_出力は表と次回アジェンダの行を持つ(self):
        w = self.wiki([("LOG", "LOG-20260918-01", {}), ("DEC", "DEC-001", {})],
                      segments={"MTG-20260918": SEGMENTS})
        self._transcript(w)
        code, out = run("--root", str(w.root))
        self.assertEqual(code, 0)
        self.assertIn("| 段 | 状態 |", out)
        self.assertIn("**次にやること:", out)
        self.assertIn("次回アジェンダ: 議題 0", out)


if __name__ == "__main__":
    unittest.main()
