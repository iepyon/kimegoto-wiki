#!/usr/bin/env python3
"""入力バンドルのテスト。

顧客提出版のフィルタは、漏れたら契約上の事故になる。ここは厚く押さえる。
"""

import datetime
import unittest

from tests.fixtures import WikiTestCase
from tools.bundle import Bundle

TODAY = datetime.date(2026, 9, 18)
LOG = ("LOG", "LOG-20260918-01", {})
MTG = "MTG-20260918"


class BundleTestCase(WikiTestCase):
    def bundle(self, cards):
        return Bundle(self.wiki(cards), TODAY)


class MinutesInputTest(BundleTestCase):
    CARDS = [
        LOG,
        ("DEC", "DEC-001", {"title": "OIDC に寄せる", "代替案": [
            {"案": "AD直結", "却下理由": "固定IPのみ", "引用": "そこは厳しいですね",
             "信頼度": "逐語あり"},
            {"案": "自前実装", "却下理由": "記録なし", "引用": "自前もありますね",
             "信頼度": "推測"}]}),
        ("DEC", "DEC-002", {"title": "推測の決定", "信頼度": "推測"}),
        ("Q", "Q-001", {}),
        ("ACT", "ACT-001", {"担当": "甲社", "期限": "2026-10-02"}),
        ("CON", "CON-001", {"内容": "自社の制約", "所在": "自社側", "種類": "expectation",
                            "硬度": "懸濁"}),
        ("CON", "CON-002", {"内容": "顧客側の制約"}),
    ]

    def test_社内版はすべて出す(self):
        text = self.bundle(self.CARDS).minutes_input(MTG, "internal")
        self.assertIn("DEC-001", text)
        self.assertIn("推測の決定", text)
        self.assertIn("自社の制約", text)
        self.assertIn("そこは厳しいですね", text)
        self.assertIn("## 議論の経緯（LOG）", text)

    def test_顧客版は推測の決定を落とす(self):
        text = self.bundle(self.CARDS).minutes_input(MTG, "customer")
        self.assertNotIn("推測の決定", text)

    def test_顧客版は自社側の制約を落とす(self):
        text = self.bundle(self.CARDS).minutes_input(MTG, "customer")
        self.assertNotIn("自社の制約", text)
        self.assertIn("顧客側の制約", text)

    def test_顧客版は記録なしの代替案を落とす(self):
        text = self.bundle(self.CARDS).minutes_input(MTG, "customer")
        self.assertIn("AD直結", text)
        self.assertNotIn("自前実装", text)

    def test_顧客版はカードIDを出さない(self):
        text = self.bundle(self.CARDS).minutes_input(MTG, "customer")
        for card_id in ("DEC-001", "Q-001", "ACT-001", "CON-002", "LOG-20260918-01"):
            self.assertNotIn(card_id, text, card_id)

    def test_顧客版は逐語引用を出さない(self):
        text = self.bundle(self.CARDS).minutes_input(MTG, "customer")
        self.assertNotIn("そこは厳しいですね", text)
        self.assertNotIn("## 議論の経緯", text)

    def test_顧客版は役割を社名に丸める(self):
        text = self.bundle(self.CARDS).minutes_input(MTG, "customer")
        self.assertNotIn("顧客PM", text)
        self.assertIn("甲社", text)

    def test_顧客版は落とした件数だけを脚注に残す(self):
        bundle = self.bundle(self.CARDS)
        text = bundle.minutes_input(MTG, "customer")
        self.assertIn("機械的に落としたもの（3件）", text)
        self.assertEqual(len(bundle.dropped), 3)   # 推測の決定 / 自社側の制約 / 記録なしの代替案

    def test_脚注に落としたものの中身を書かない(self):
        # この束はそのまま顧客提出版の材料になる。脚注に ID や名前を残すと
        # LLM がそれを本文に混ぜうる。内訳は標準エラーへ。
        text = self.bundle(self.CARDS).minutes_input(MTG, "customer")
        footer = text.split("機械的に落としたもの")[1]
        for leaked in ("DEC-001", "DEC-002", "CON-001", "自前実装", "自社の制約", "推測の決定"):
            self.assertNotIn(leaked, footer, leaked)

    def test_顧客版で担当の社名が不明にならない(self):
        # `担当` は schema.md の定義どおり社名で持つ。役割として引き当てると
        # unknown_role_default に落ちて「不明」になり、対外文書から約束の主体が消える。
        text = self.bundle([LOG, ("ACT", "ACT-001", {"担当": "ESM"})]).minutes_input(MTG, "customer")
        self.assertIn("担当: ESM", text)
        self.assertNotIn("担当: 不明", text)

    def test_顧客版で担当が空なら空のまま(self):
        text = self.bundle([LOG, ("ACT", "ACT-001", {"担当": ""})]).minutes_input(MTG, "customer")
        self.assertNotIn("不明", text)

    def test_顧客版はみなし確定の一文を入れる(self):
        text = self.bundle(self.CARDS).minutes_input(MTG, "customer")
        self.assertIn("3営業日以内にご異議のない場合", text)

    def test_社内版にみなし確定の一文は要らない(self):
        self.assertNotIn("営業日以内", self.bundle(self.CARDS).minutes_input(MTG, "internal"))

    def test_繰越アクションを拾う(self):
        cards = [LOG, ("LOG", "LOG-20261002-01", {"meeting": "MTG-20261002"}),
                 ("ACT", "ACT-001", {"status": "進行中", "title": "前回からの宿題"})]
        text = self.bundle(cards).minutes_input("MTG-20261002", "internal")
        self.assertIn("## 前回からの繰越アクション", text)
        self.assertIn("前回からの宿題", text)

    def test_完了したアクションは繰り越さない(self):
        cards = [LOG, ("LOG", "LOG-20261002-01", {"meeting": "MTG-20261002"}),
                 ("ACT", "ACT-001", {"status": "完了", "title": "済んだ宿題"})]
        text = self.bundle(cards).minutes_input("MTG-20261002", "internal")
        self.assertNotIn("済んだ宿題", text)

    def _section(self, text, title):
        """`## title` から次の `## ` までの本文。"""
        body = text.split("## %s\n" % title, 1)[1]
        return body.split("\n## ", 1)[0]

    def test_前回のアクションの完了は今回のアクションに混ぜない(self):
        # 前回起票した ACT を今回完了にすると、今回の LOG が derived_from に足される。
        # それでも「今回のアクション」ではなく「前回アクションの結果」に出す。
        cards = [LOG, ("LOG", "LOG-20261002-01", {"meeting": "MTG-20261002"}),
                 ("ACT", "ACT-001", {"status": "完了", "title": "前回の宿題",
                                     "derived_from": ["LOG-20260918-01", "LOG-20261002-01"]}),
                 ("ACT", "ACT-002", {"title": "今回の宿題",
                                     "derived_from": ["LOG-20261002-01"]})]
        text = self.bundle(cards).minutes_input("MTG-20261002", "internal")
        self.assertIn("前回の宿題", self._section(text, "前回アクションの結果"))
        self.assertNotIn("前回の宿題", self._section(text, "今回のアクション"))
        self.assertIn("今回の宿題", self._section(text, "今回のアクション"))

    def test_解決した問いは未決事項に並べない(self):
        cards = [LOG, ("DEC", "DEC-001", {}),
                 ("Q", "Q-001", {"title": "解けた問い", "status": "解決",
                                 "resolved_by": "DEC-001"}),
                 ("Q", "Q-002", {"title": "残る問い"})]
        text = self.bundle(cards).minutes_input(MTG, "internal")
        self.assertNotIn("解けた問い", self._section(text, "未決事項"))
        self.assertIn("解けた問い", self._section(text, "この会議で解決した問い"))
        self.assertIn("残る問い", self._section(text, "未決事項"))

    def test_議題の節に扱ったか扱えずかと状態を出す(self):
        segments = {MTG: ("meeting: %s\nsegments:\n  - seq: 1\n    title: 論点\n"
                          "    種別: 議論\n    議題: AGD-001\n" % MTG)}
        cards = [LOG,
                 ("AGD", "AGD-001", {"title": "甲を決めたい", "status": "決着",
                                     "予定会議": [MTG]}),
                 ("AGD", "AGD-002", {"title": "乙を決めたい", "status": "継続",
                                     "予定会議": [MTG]}),
                 ("DEC", "DEC-001", {"title": "甲にする", "議題": "AGD-001"})]
        w = self.wiki(cards, segments=segments)
        internal = self._section(Bundle(w).minutes_input(MTG, "internal"), "議題")
        self.assertIn("### AGD-001 甲を決めたい", internal)
        self.assertIn("- この会議で: 扱った", internal)
        self.assertIn("- いまの状態: 決着", internal)
        self.assertIn("- 決定: DEC-001 甲にする", internal)
        self.assertIn("### AGD-002 乙を決めたい", internal)
        self.assertIn("- この会議で: 扱えず", internal)
        customer = self._section(Bundle(w).minutes_input(MTG, "customer"), "議題")
        self.assertIn("### 甲を決めたい", customer)
        self.assertNotIn("AGD-", customer)
        self.assertNotIn("DEC-", customer)

    def test_後の会議で起票したアクションを繰り越さない(self):
        cards = [LOG, ("LOG", "LOG-20261002-01", {"meeting": "MTG-20261002"}),
                 ("ACT", "ACT-001", {"title": "後で生えた宿題",
                                     "derived_from": ["LOG-20261002-01"]})]
        text = self.bundle(cards).minutes_input(MTG, "internal")
        self.assertNotIn("後で生えた宿題", text)

    def test_存在しない会議は例外(self):
        with self.assertRaises(KeyError):
            self.bundle([LOG]).minutes_input("MTG-20991231")


class PromoteInputTest(BundleTestCase):
    """昇格の門は、プロンプトの注意書きではなく入力の欠落で閉じる。"""

    def test_なぜ未記入の決定は材料に入らない(self):
        text = self.bundle([LOG, ("DEC", "DEC-001",
                                  {"title": "理由のない決定", "なぜ": ""})]).promote_input(MTG)
        self.assertNotIn("## 決定と却下理由", text.split("昇格の門で落とした")[1])
        self.assertIn("昇格の門で落とした決定（1件）", text)
        self.assertIn("理由のない決定", text.split("昇格の門で落とした")[1])

    def test_なぜが書かれた決定は材料に入る(self):
        text = self.bundle([LOG, ("DEC", "DEC-001", {
            "title": "理由のある決定", "なぜ": "失効保証を IdP 側に寄せるため"})]).promote_input(MTG)
        head = text.split("昇格の門で落とした")[0]
        self.assertIn("理由のある決定", head)
        self.assertIn("失効保証を IdP 側に寄せるため", head)
        self.assertIn("昇格の門で落とした決定（0件）", text)

    def test_却下理由が記録されていればなぜ未記入でも材料に入る(self):
        # CON の中身は「捨てた案の理由」であって「採った案の理由」ではない。
        # なぜ だけで門を閉じると、逐語で取れている制約まで落ちる。
        text = self.bundle([LOG, ("DEC", "DEC-001", {
            "title": "外部SaaSを使わない", "なぜ": "",
            "代替案": [{"案": "外部SaaS", "却下理由": "社外にデータを出せない",
                        "引用": "社外にデータを出すのは規程上できません",
                        "信頼度": "逐語あり"}]})]).promote_input(MTG)
        head = text.split("昇格の門で落とした")[0]
        self.assertIn("外部SaaSを使わない", head)
        self.assertIn("社外にデータを出せない", head)
        self.assertIn("昇格の門で落とした決定（0件）", text)

    def test_なぜが記録なしだけなら材料に入らない(self):
        # 「記録なし」と答えたか空欄のままにしたかで、門の開閉が変わってはいけない。
        text = self.bundle([LOG, ("DEC", "DEC-001", {
            "title": "理由のない決定", "なぜ": "記録なし"})]).promote_input(MTG)
        self.assertIn("昇格の門で落とした決定（1件）", text)
        self.assertIn("理由のない決定", text.split("昇格の門で落とした")[1])

    def test_契約制約の決定は理由が無くても引用を材料に出す(self):
        text = self.bundle([LOG, ("DEC", "DEC-001", {
            "title": "スキャン保存にはタイムスタンプを必須にする", "なぜ": "",
            "種別": "契約制約", "決定の所在": "顧客法務",
            "引用": "じゃあそれでいきましょう"})]).promote_input(MTG)
        head = text.split("昇格の門で落とした")[0]
        self.assertIn("スキャン保存にはタイムスタンプを必須にする", head)
        self.assertIn("契約制約の決定（顧客法務）: じゃあそれでいきましょう", head)
        self.assertIn("昇格の門で落とした決定（0件）", text)

    def test_推測の契約制約は通さない(self):
        text = self.bundle([LOG, ("DEC", "DEC-001", {
            "title": "照合できない決定", "なぜ": "", "種別": "契約制約",
            "信頼度": "推測"})]).promote_input(MTG)
        self.assertIn("昇格の門で落とした決定（1件）", text)

    def test_却下理由が記録なしだけなら材料に入らない(self):
        text = self.bundle([LOG, ("DEC", "DEC-001", {
            "title": "理由のない決定", "なぜ": "",
            "代替案": [{"案": "別案", "却下理由": "記録なし",
                        "引用": "別案もあるんですけどね",
                        "信頼度": "推測"}]})]).promote_input(MTG)
        self.assertIn("昇格の門で落とした決定（1件）", text)

    def test_カードを作れとは書かない(self):
        text = self.bundle([LOG]).promote_input(MTG)
        self.assertIn("カードは作らない", text)

    def test_既存の用語を渡す(self):
        text = self.bundle([LOG, ("TERM", "TERM-001", {})]).promote_input(MTG)
        self.assertIn("OIDC", text)
        self.assertIn("オイデッシー", text)


class ReviewTest(BundleTestCase):
    def test_判定保留を最初に出す(self):
        text = self.bundle([LOG, ("DEC", "DEC-001", {"範囲": "判定保留"})]).review(MTG)
        self.assertLess(text.index("2-0"), text.index("2-1"))
        self.assertIn("範囲: 判定保留", text)
        self.assertIn("DEC-001", text)

    def test_該当0件の節は0件とだけ出す(self):
        text = self.bundle([LOG, ("DEC", "DEC-001", {"範囲": "当初合意内",
                                                     "なぜ": "理由"})]).review(MTG)
        self.assertIn("0件", text)

    def test_なぜ未記入の決定に穴埋め形を添える(self):
        text = self.bundle([LOG, ("DEC", "DEC-001", {"なぜ": ""})]).review(MTG)
        self.assertIn("〈場面〉で〈懸念〉に直面し", text)

    def test_LLMに理由を書かせない旨を冒頭に置く(self):
        text = self.bundle([LOG]).review(MTG)
        head = text.split("## 2-0")[0]
        self.assertIn("LLM に書かせない", head)

    def test_記録なしの代替案を提示する(self):
        text = self.bundle([LOG, ("DEC", "DEC-001", {"代替案": [
            {"案": "自前実装", "却下理由": "記録なし", "引用": "自前もありますね"}]})]).review(MTG)
        self.assertIn("記録なし", text)
        self.assertIn("自前実装", text)

    def test_時間配分を出す(self):
        text = self.bundle([LOG]).review(MTG)
        for minutes in ("3分", "4分", "8分", "6分"):
            self.assertIn(minutes, text)

    def test_未完了アクションを出す(self):
        text = self.bundle([LOG, ("ACT", "ACT-001", {"担当": "", "期限": ""})]).review(MTG)
        self.assertIn("ACT-001", text)


class 議事録の骨格(BundleTestCase):
    """節構成の正本は ontology.yaml。スキルの散文に持たせない。"""

    def test_社内版は8節を出す(self):
        text = self.bundle([LOG]).minutes_input(MTG)
        for title in ("前回アクションの結果", "議題", "決定事項", "未決事項", "今回のアクション",
                      "新たに記録した制約・前提", "議論の経緯", "記録の状態"):
            self.assertIn("**%s**" % title, text)

    def test_顧客提出版は内部向けの節を出さない(self):
        text = self.bundle([LOG]).minutes_input(MTG, "customer")
        self.assertIn("**確認事項**", text)
        self.assertNotIn("**議論の経緯**", text)
        self.assertNotIn("**記録の状態**", text)

    def test_骨格は順番つきで出る(self):
        text = self.bundle([LOG]).minutes_input(MTG, "customer")
        self.assertIn("1. **前回アクションの結果**", text)
        self.assertIn("2. **議題**", text)
        self.assertIn("5. **アクション**", text)


class 前提のトリガー語(BundleTestCase):
    """検出は機械、昇格の可否は人間。ここは印を付けるところまで。"""

    def test_なぜに含まれるトリガー語を拾う(self):
        text = self.bundle([LOG, ("DEC", "DEC-001", {
            "なぜ": "当面は50人規模なので、シンプルな構成で足りると判断した"})]
        ).promote_input(MTG)
        self.assertIn("DEC-001 の なぜ に `当面`", text)

    def test_却下理由に含まれるトリガー語を拾う(self):
        text = self.bundle([LOG, ("DEC", "DEC-001", {"代替案": [
            {"案": "専用DB", "却下理由": "今回は台数を増やせない", "引用": "増やせません",
             "信頼度": "逐語あり"}]})]).promote_input(MTG)
        self.assertIn("却下理由 に `今回は`", text)

    def test_トリガー語が無ければ何も出さない(self):
        text = self.bundle([LOG, ("DEC", "DEC-001", {"なぜ": "移行コストが低いため"})]
                           ).promote_input(MTG)
        section = text.split("## 前提のトリガー語が出ている決定")[1].split("##")[0]
        self.assertIn("（なし）", section)

    def test_門で落ちた決定は走査しない(self):
        # 理由がどこにも記録されていない決定は材料に入らない。
        text = self.bundle([LOG, ("DEC", "DEC-001", {})]).promote_input(MTG)
        section = text.split("## 前提のトリガー語が出ている決定")[1].split("##")[0]
        self.assertIn("（なし）", section)

    def test_候補の上限を材料に書く(self):
        text = self.bundle([LOG]).promote_input(MTG)
        self.assertIn("**10件まで**", text)


if __name__ == "__main__":
    unittest.main()
