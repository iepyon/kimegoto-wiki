#!/usr/bin/env python3
"""`kime update` / `kime confirm`。

会議をまたぐ更新が手編集だけだと、回数が増えるほどドリフトする。
frontmatter を行単位で書き換え、キーの順序と空欄を壊さないことを見る。
"""

import contextlib
import datetime
import io
import pathlib
import unittest

from tests.fixtures import WikiTestCase
from tools import update_cmd
from tools.update_cmd import UpdateError, apply_updates, business_days_after

CARD = """---
id: ACT-008
type: action
title: 権限マトリクスを提供する
担当: 甲社
期限:
status: 未着手
対策種別:
引用: 探します
信頼度: 逐語あり
derived_from: [LOG-20260918-01]
関連: []
更新履歴:
  - 2026-09-18: 起票
issue:
---
"""


class ApplyUpdatesTest(unittest.TestCase):
    def test_スカラを置き換える(self):
        out = apply_updates(CARD, [("status", "完了")])
        self.assertIn("status: 完了", out)
        self.assertNotIn("status: 未着手", out)

    def test_空欄に書き込める(self):
        out = apply_updates(CARD, [("期限", "2026-10-02")])
        self.assertIn("期限: 2026-10-02", out)

    def test_空文字を渡すと空欄に戻る(self):
        out = apply_updates(apply_updates(CARD, [("期限", "2026-10-02")]), [("期限", "")])
        self.assertIn("\n期限:\n", out)

    def test_キーの順序とコメントを壊さない(self):
        out = apply_updates(CARD, [("status", "完了")])
        self.assertEqual([l.split(":")[0] for l in CARD.splitlines()],
                         [l.split(":")[0] for l in out.splitlines()])

    def test_derived_fromに追記する(self):
        out = apply_updates(CARD, add_derived=["LOG-20260918-02"])
        self.assertIn("derived_from: [LOG-20260918-01, LOG-20260918-02]", out)

    def test_derived_fromの重複は増やさない(self):
        out = apply_updates(CARD, add_derived=["LOG-20260918-01"])
        self.assertEqual(out, CARD)

    def test_更新履歴の末尾に足す(self):
        out = apply_updates(CARD, logs=["2026-10-02: 完了"])
        lines = out.splitlines()
        self.assertEqual(lines[lines.index("  - 2026-09-18: 起票") + 1],
                         "  - 2026-10-02: 完了")
        self.assertEqual(lines[lines.index("  - 2026-10-02: 完了") + 1], "issue:")

    def test_無いフィールドは拒む(self):
        # 勝手に足すと、型が持たないフィールドが静かに増える。
        with self.assertRaises(UpdateError):
            apply_updates(CARD, [("存在しない", "値")])

    def test_ネストしたキーを誤爆しない(self):
        # 代替案の中にも `引用` があるので、トップレベルだけを見る。
        text = CARD.replace("関連: []", "関連: []\n代替案:\n  - 案: A\n    引用: 別の引用")
        out = apply_updates(text, [("引用", "書き換え後")])
        self.assertIn("引用: 書き換え後", out)
        self.assertIn("    引用: 別の引用", out)


class BusinessDaysTest(unittest.TestCase):
    def test_土日を飛ばす(self):
        # 2026-09-12 は土曜。3営業日後は 09-16（水）。
        self.assertEqual(business_days_after(datetime.date(2026, 9, 12), 3),
                         datetime.date(2026, 9, 16))

    def test_平日からの3営業日(self):
        self.assertEqual(business_days_after(datetime.date(2026, 9, 14), 3),
                         datetime.date(2026, 9, 17))


class ConfirmTest(WikiTestCase):
    def _root(self, cards):
        return str(self.wiki(cards).root)

    @staticmethod
    def _run(argv):
        """標準出力はテストの関心ではないので飲み込む。"""
        with contextlib.redirect_stdout(io.StringIO()):
            return update_cmd.main_confirm(argv)

    @staticmethod
    def _read(root):
        return pathlib.Path(root, "decisions", "DEC-001.md").read_text(encoding="utf-8")

    def test_確定日を書き戻す(self):
        root = self._root([("LOG", "LOG-20260918-01", {}),
                           ("DEC", "DEC-001", {"確定日": ""})])
        code = self._run(["--meeting", "MTG-20260918",
                          "--sent", "2026-09-18", "--root", root])
        self.assertEqual(code, 0)
        self.assertIn("確定日: 2026-09-23", self._read(root))

    def test_dry_runでは書かない(self):
        root = self._root([("LOG", "LOG-20260918-01", {}),
                           ("DEC", "DEC-001", {"確定日": ""})])
        self._run(["--meeting", "MTG-20260918", "--sent", "2026-09-18",
                   "--dry-run", "--root", root])
        self.assertNotIn("確定日: 2026-09-23", self._read(root))

    def test_既に入っているものは対象にしない(self):
        root = self._root([("LOG", "LOG-20260918-01", {}),
                           ("DEC", "DEC-001", {"確定日": "2026-09-01"})])
        self._run(["--meeting", "MTG-20260918", "--sent", "2026-09-18",
                   "--root", root])
        self.assertIn("確定日: 2026-09-01", self._read(root))


if __name__ == "__main__":
    unittest.main()
