#!/usr/bin/env python3
"""引用照合のテスト。

ここが死ぬと、この仕組みの唯一の機械的な真偽判定が死ぬ。
正規化の吸収範囲と、非対称性（水増しだけを弾き、慎重側は許す）を厚く押さえる。
"""

import unittest

from tests.fixtures import WikiTestCase
from tools import quotes

LOG_BODY = """\
## 発言

- **顧客PM**: ADに繋ぐのは、まあVPNが固定IPなんで厳しいですね
- **開発リーダ**: だとするとOIDCに寄せる手もあります
- **(沈黙 約6秒)**
- **顧客PM**: じゃあOIDCの方向でいきましょう
- **開発メンバー**: 利用者は当面50人くらいの想定でいいですか
"""


class NormalizeTest(unittest.TestCase):
    def test_句読点を吸収する(self):
        self.assertEqual(quotes.norm("はい、当面はその規模です。"), quotes.norm("はい当面はその規模です"))

    def test_鉤括弧を吸収する(self):
        self.assertEqual(quotes.norm("「OIDCで」"), quotes.norm("OIDCで"))

    def test_全角半角を吸収する(self):
        self.assertEqual(quotes.norm("ＯＩＤＣ"), quotes.norm("OIDC"))

    def test_空白を吸収する(self):
        self.assertEqual(quotes.norm("O I D C"), quotes.norm("OIDC"))

    def test_語順の違いは吸収しない(self):
        self.assertNotEqual(quotes.norm("AからB"), quotes.norm("BからA"))

    def test_語彙の違いは吸収しない(self):
        self.assertNotEqual(quotes.norm("あると思うんですよね"), quotes.norm("あるんですけどね"))


class StripQuotesTest(unittest.TestCase):
    def test_各種クォートを外す(self):
        for src in ['"x"', "'x'", "「x」", "『x』"]:
            self.assertEqual(quotes.strip_quotes(src), "x", src)

    def test_片方だけなら外さない(self):
        self.assertEqual(quotes.strip_quotes('"x'), '"x')


class CheckTest(WikiTestCase):
    def _wiki(self, **dec):
        return self.wiki([("LOG", "LOG-20260918-01", {}, LOG_BODY),
                          ("DEC", "DEC-001", dec)])

    def test_一致する引用(self):
        issues = quotes.check(self._wiki(引用="じゃあOIDCの方向でいきましょう"))
        self.assertEqual([i.status for i in issues], [quotes.OK])
        self.assertFalse(issues[0].is_problem)

    def test_句点つきでも一致する(self):
        issues = quotes.check(self._wiki(引用="じゃあOIDCの方向でいきましょう。"))
        self.assertEqual(issues[0].status, quotes.OK)

    def test_一文字違いは不一致(self):
        issues = quotes.check(self._wiki(引用="じゃあOIDCの方向でいきますか"))
        self.assertEqual(issues[0].status, quotes.FAIL)
        self.assertTrue(issues[0].is_problem)

    def test_発言の一部でも一致する(self):
        # セグメント境界をまたぐ引用を許すため、連結した本文に対する部分一致で見る
        issues = quotes.check(self._wiki(引用="VPNが固定IPなんで厳しいですね"))
        self.assertEqual(issues[0].status, quotes.OK)

    def test_derived_fromにLOGが無ければ参照なし(self):
        issues = quotes.check(self._wiki(引用="じゃあOIDCの方向でいきましょう", derived_from=[]))
        self.assertEqual(issues[0].status, quotes.NO_REF)
        self.assertTrue(issues[0].is_problem)

    def test_参照先のLOGが存在しなければ不一致(self):
        issues = quotes.check(self._wiki(引用="じゃあOIDCの方向でいきましょう",
                                         derived_from=["LOG-20260918-99"]))
        self.assertEqual(issues[0].status, quotes.FAIL)
        self.assertIn("LOG カード自体が見つからない", issues[0].detail)

    def test_既に推測なら問題にしない(self):
        # 慎重側への降格は常に許す。水増しだけを弾く（非対称）。
        issues = quotes.check(self._wiki(引用="存在しない発言", 信頼度="推測"))
        self.assertEqual(issues[0].status, quotes.ALREADY_GUESS)
        self.assertFalse(issues[0].is_problem)

    def test_逐語ありを名乗る不一致は問題(self):
        issues = quotes.check(self._wiki(引用="存在しない発言", 信頼度="逐語あり"))
        self.assertTrue(issues[0].is_problem)

    def test_沈黙の注記は照合先にならない(self):
        issues = quotes.check(self._wiki(引用="沈黙 約6秒"))
        self.assertEqual(issues[0].status, quotes.FAIL)

    def test_引用が空なら照合しない(self):
        self.assertEqual(quotes.check(self._wiki(引用="")), [])

    def test_代替案の引用も照合する(self):
        w = self.wiki([("LOG", "LOG-20260918-01", {}, LOG_BODY),
                       ("DEC", "DEC-001", {"引用": "じゃあOIDCの方向でいきましょう", "代替案": [
                           {"案": "AD直結", "却下理由": "固定IP",
                            "引用": "ADに繋ぐのは、まあVPNが固定IPなんで厳しいですね",
                            "信頼度": "逐語あり"},
                           {"案": "自前実装", "却下理由": "記録なし",
                            "引用": "自前で作る手もあると思うんですよね", "信頼度": "言及のみ"}]})])
        issues = quotes.check(w)
        self.assertEqual([i.status for i in issues], [quotes.OK, quotes.OK, quotes.FAIL])

    def test_checkはファイルを書き換えない(self):
        w = self._wiki(引用="存在しない発言")
        before = w.get("DEC-001").path.read_text(encoding="utf-8")
        quotes.check(w)
        self.assertEqual(w.get("DEC-001").path.read_text(encoding="utf-8"), before)


class FixTest(WikiTestCase):
    def _wiki(self, **dec):
        return self.wiki([("LOG", "LOG-20260918-01", {}, LOG_BODY),
                          ("DEC", "DEC-001", dec)])

    def test_不一致を推測に降格する(self):
        w = self._wiki(引用="存在しない発言", 信頼度="逐語あり")
        fixed, _ = quotes.fix(w)
        self.assertEqual(fixed, 1)
        self.assertIn("信頼度: 推測", w.get("DEC-001").path.read_text(encoding="utf-8"))

    def test_一致するものは触らない(self):
        w = self._wiki(引用="じゃあOIDCの方向でいきましょう", 信頼度="逐語あり")
        fixed, _ = quotes.fix(w)
        self.assertEqual(fixed, 0)
        self.assertIn("信頼度: 逐語あり", w.get("DEC-001").path.read_text(encoding="utf-8"))

    def test_二度実行しても二重に処理しない(self):
        w = self._wiki(引用="存在しない発言", 信頼度="逐語あり")
        self.assertEqual(quotes.fix(w)[0], 1)
        self.assertEqual(quotes.fix(w)[0], 0)

    def test_降格しても他の行を壊さない(self):
        w = self._wiki(引用="存在しない発言", 信頼度="逐語あり", なぜ="")
        quotes.fix(w)
        text = w.get("DEC-001").path.read_text(encoding="utf-8")
        self.assertIn("id: DEC-001", text)
        self.assertIn("なぜ:", text)
        self.assertIn("決定の所在: 顧客PM", text)

    def test_代替案の信頼度だけを降格する(self):
        w = self.wiki([("LOG", "LOG-20260918-01", {}, LOG_BODY),
                       ("DEC", "DEC-001", {"引用": "じゃあOIDCの方向でいきましょう", "代替案": [
                           {"案": "自前実装", "却下理由": "記録なし",
                            "引用": "存在しない発言", "信頼度": "言及のみ"}]})])
        quotes.fix(w)
        text = w.get("DEC-001").path.read_text(encoding="utf-8")
        self.assertIn("信頼度: 逐語あり", text)   # 本体の引用は一致しているので据え置き
        self.assertIn("信頼度: 推測", text)       # 代替案の側だけ降格


class ConfidencePositionTest(WikiTestCase):
    def test_信頼度が引用の直後にあれば問題なし(self):
        w = self.wiki([("LOG", "LOG-20260918-01", {}, LOG_BODY), ("DEC", "DEC-001", {})])
        self.assertEqual(quotes.confidence_out_of_position(w), [])

    def test_信頼度が離れていると拾う(self):
        w = self.wiki([("LOG", "LOG-20260918-01", {}, LOG_BODY),
                       ("DEC", "DEC-001", {"信頼度": None})])
        found = quotes.confidence_out_of_position(w)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0][0].id, "DEC-001")


if __name__ == "__main__":
    unittest.main()
