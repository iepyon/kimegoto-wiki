#!/usr/bin/env python3
"""lint のテスト。

1チェック = 1クラス。それぞれ最低でも
  - 鳴るべきケース
  - 鳴るべきでない隣接ケース
を置く。「鳴らない隣接ケース」が無いと、常に鳴るだけの壊れたチェックが通ってしまう。
"""

import datetime
import tempfile
import unittest
from pathlib import Path

from tests.fixtures import ROLE_MAPPING, WikiTestCase
from tools import gijilint
from tools.cards import Wiki

TODAY = datetime.date(2026, 9, 18)
LOG = ("LOG", "LOG-20260918-01", {})


class LintTestCase(WikiTestCase):
    def problems(self, cards, check_id, today=TODAY, role_mapping=ROLE_MAPPING):
        wiki = self.wiki(cards, role_mapping)
        return gijilint.run(wiki, today=today, only={check_id})

    def assertRaised(self, cards, check_id, **kw):
        found = self.problems(cards, check_id, **kw)
        self.assertTrue(found, "%s が鳴らなかった" % check_id)
        return found

    def assertQuiet(self, cards, check_id, **kw):
        found = self.problems(cards, check_id, **kw)
        self.assertFalse(found, "%s が鳴った: %s" % (check_id, [p.message for p in found]))


# ============================================================ スキーマ層

class FrontmatterTest(unittest.TestCase):
    def _wiki(self, name, text):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "decisions").mkdir(parents=True)
        (root / "decisions" / name).write_text(text, encoding="utf-8")
        return Wiki(root)

    def test_壊れたfrontmatterを名指しする(self):
        w = self._wiki("DEC-001.md", "---\nid: DEC-001\nただの文\n---\n")
        found = gijilint.run(w, today=TODAY, only={"frontmatter"})
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].where, "DEC-001")

    def test_壊れたカードは他のチェックを巻き添えにしない(self):
        # コロン1つの書き損じが、無関係な error を量産しないこと。
        w = self._wiki("DEC-001.md", "---\nid: DEC-001\nただの文\n---\n")
        others = [p for p in gijilint.run(w, today=TODAY) if p.check != "frontmatter"]
        self.assertEqual(others, [], [p.message for p in others])

    def test_健全なカードでは鳴らない(self):
        w = self._wiki("DEC-001.md", "---\nid: DEC-001\ntype: decision\n---\n")
        self.assertEqual(gijilint.run(w, today=TODAY, only={"frontmatter"}), [])

    def test_型に当たらないIDは迷子として鳴る(self):
        w = self._wiki("メモ.md", "---\nid: メモ\n---\n")
        self.assertTrue(gijilint.run(w, today=TODAY, only={"frontmatter"}))


class IdFilenameTest(LintTestCase):
    def test_食い違えば鳴る(self):
        self.assertRaised([LOG, ("DEC", "DEC-001", {"id": "DEC-002"})], "id-filename")

    def test_一致すれば鳴らない(self):
        self.assertQuiet([LOG, ("DEC", "DEC-001", {})], "id-filename")


class DirPlacementTest(LintTestCase):
    def test_typeが違えば鳴る(self):
        self.assertRaised([LOG, ("DEC", "DEC-001", {"type": "question"})], "dir-placement")

    def test_正しければ鳴らない(self):
        self.assertQuiet([LOG, ("DEC", "DEC-001", {})], "dir-placement")


class RequiredFieldTest(LintTestCase):
    def test_必須が空なら鳴る(self):
        self.assertRaised([LOG, ("DEC", "DEC-001", {"決定の所在": ""})], "required-field")

    def test_必須の参照配列が空でも鳴る(self):
        self.assertRaised([LOG, ("DEC", "DEC-001", {"derived_from": []})], "required-field")

    def test_任意フィールドが空でも鳴らない(self):
        self.assertQuiet([LOG, ("DEC", "DEC-001", {"なぜ": "", "確定日": ""})], "required-field")


class UnknownFieldTest(LintTestCase):
    def test_宣言にないキーは鳴る(self):
        self.assertRaised([LOG, ("DEC", "DEC-001", {"なぜか": "typo"})], "unknown-field")

    def test_宣言どおりなら鳴らない(self):
        self.assertQuiet([LOG, ("DEC", "DEC-001", {})], "unknown-field")


class VocabTest(LintTestCase):
    def test_語彙外は鳴る(self):
        self.assertRaised([LOG, ("DEC", "DEC-001", {"status": "決定済"})], "vocab")

    def test_語彙内なら鳴らない(self):
        self.assertQuiet([LOG, ("DEC", "DEC-001", {"status": "保留"})], "vocab")

    def test_空欄は語彙違反にしない(self):
        self.assertQuiet([LOG, ("ACT", "ACT-001", {"対策種別": ""})], "vocab")

    def test_自由記述を許すフィールドは鳴らない(self):
        # `作らない` は 該当なし / 記録なし / <内容> / 未記入 の4値で、<内容> は自由
        self.assertQuiet([LOG, ("DEC", "DEC-001", {"作らない": "SSO 連携は本フェーズ対象外"})], "vocab")


class DateFormatTest(LintTestCase):
    def test_形式違反は鳴る(self):
        self.assertRaised([LOG, ("DEC", "DEC-001", {"決定日": "2026/09/18"})], "date-format")

    def test_空欄は鳴らない(self):
        self.assertQuiet([LOG, ("DEC", "DEC-001", {"確定日": ""})], "date-format")

    def test_正しい形式は鳴らない(self):
        self.assertQuiet([LOG, ("DEC", "DEC-001", {"決定日": "2026-09-18"})], "date-format")


class StructShapeTest(LintTestCase):
    def test_必須キーが無ければ鳴る(self):
        self.assertRaised([LOG, ("DEC", "DEC-001", {"代替案": [{"案": "自前実装"}]})], "struct-shape")

    def test_語彙外の信頼度は鳴る(self):
        self.assertRaised([LOG, ("DEC", "DEC-001", {"代替案": [
            {"案": "自前実装", "却下理由": "工数", "信頼度": "たぶん"}]})], "struct-shape")

    def test_揃っていれば鳴らない(self):
        self.assertQuiet([LOG, ("DEC", "DEC-001", {"代替案": [
            {"案": "自前実装", "却下理由": "工数", "信頼度": "逐語あり"}]})], "struct-shape")

    def test_更新履歴は自由キーなので鳴らない(self):
        self.assertQuiet([LOG, ("ACT", "ACT-001", {"更新履歴": [{"2026-09-18": "起票"}]})],
                         "struct-shape")


# ============================================================ 参照整合

class RefExistsTest(LintTestCase):
    def test_存在しない参照は鳴る(self):
        self.assertRaised([LOG, ("DEC", "DEC-001", {"前提": ["ASM-999"]})], "ref-exists")

    def test_実在する参照は鳴らない(self):
        self.assertQuiet([LOG, ("ASM", "ASM-001", {}), ("DEC", "DEC-001", {"前提": ["ASM-001"]})],
                         "ref-exists")

    def test_空の参照配列は鳴らない(self):
        self.assertQuiet([LOG, ("DEC", "DEC-001", {"前提": []})], "ref-exists")


class RefRangeTest(LintTestCase):
    def test_型違いの参照は鳴る(self):
        self.assertRaised([LOG, ("Q", "Q-001", {}), ("DEC", "DEC-001", {"前提": ["Q-001"]})],
                          "ref-range")

    def test_正しい型なら鳴らない(self):
        self.assertQuiet([LOG, ("ASM", "ASM-001", {}), ("DEC", "DEC-001", {"前提": ["ASM-001"]})],
                         "ref-range")


class LogRefTest(LintTestCase):
    def test_LOGを指していなければ鳴る(self):
        self.assertRaised([LOG, ("DEC", "DEC-001", {"derived_from": []})], "log-ref")

    def test_LOGを指していれば鳴らない(self):
        self.assertQuiet([LOG, ("DEC", "DEC-001", {})], "log-ref")

    def test_TERMは対象外(self):
        self.assertQuiet([LOG, ("TERM", "TERM-001", {})], "log-ref")


class InverseSyncTest(LintTestCase):
    def test_片側だけなら鳴る(self):
        self.assertRaised([LOG, ("ASM", "ASM-001", {"崩れたら見直す決定": ["DEC-001"]}),
                           ("DEC", "DEC-001", {"前提": []})], "inverse-sync")

    def test_双方向なら鳴らない(self):
        self.assertQuiet([LOG, ("ASM", "ASM-001", {"崩れたら見直す決定": ["DEC-001"]}),
                          ("DEC", "DEC-001", {"前提": ["ASM-001"]})], "inverse-sync")


class ResolvedStatusTest(LintTestCase):
    def test_解決済みでないのにresolved_byがあれば鳴る(self):
        self.assertRaised([LOG, ("DEC", "DEC-001", {}),
                           ("Q", "Q-001", {"status": "未決", "resolved_by": "DEC-001"})],
                          "resolved-status")

    def test_状態が追随していれば鳴らない(self):
        self.assertQuiet([LOG, ("DEC", "DEC-001", {}),
                          ("Q", "Q-001", {"status": "解決", "resolved_by": "DEC-001"})],
                         "resolved-status")

    def test_覆された決定も同じ扱い(self):
        self.assertRaised([LOG, ("DEC", "DEC-001", {}),
                           ("DEC", "DEC-002", {"status": "決定", "superseded_by": "DEC-001"})],
                          "resolved-status")


class LogFormatTest(LintTestCase):
    def test_発言行の形が違えば鳴る(self):
        self.assertRaised([("LOG", "LOG-20260918-01", {}, "## 発言\n\n- 顧客PM: 太字でない\n")],
                          "log-format")

    def test_沈黙の注記は鳴らない(self):
        self.assertQuiet([("LOG", "LOG-20260918-01", {},
                           "## 発言\n\n- **顧客PM**: 発言\n- **(沈黙 約6秒)**\n")], "log-format")

    def test_確定した事実の節は見ない(self):
        self.assertQuiet([("LOG", "LOG-20260918-01", {}, """\
## 発言

- **顧客PM**: 発言

## 確定した事実

- 利用者規模：当面50人（顧客PM, 00:33:40）
""")], "log-format")


# ============================================ 会議との多対多

class MeetingAnchorTest(LintTestCase):
    """カード ↔ 会議は多対多。日付はその射影なので、ずれたら鳴る。"""

    def test_最終言及が最新の会議より古ければ鳴る(self):
        self.assertRaised([
            ("LOG", "LOG-20260918-01", {}),
            ("LOG", "LOG-20261002-01", {"meeting": "MTG-20261002"}),
            ("Q", "Q-001", {"derived_from": ["LOG-20260918-01", "LOG-20261002-01"],
                            "初出": "2026-09-18", "最終言及": "2026-09-18"}),
        ], "meeting-anchor")

    def test_両端が合っていれば鳴らない(self):
        self.assertQuiet([
            ("LOG", "LOG-20260918-01", {}),
            ("LOG", "LOG-20261002-01", {"meeting": "MTG-20261002"}),
            ("Q", "Q-001", {"derived_from": ["LOG-20260918-01", "LOG-20261002-01"],
                            "初出": "2026-09-18", "最終言及": "2026-10-02"}),
        ], "meeting-anchor")

    def test_単一会議なら初出も最終言及も同じ(self):
        self.assertQuiet([LOG, ("Q", "Q-001", {})], "meeting-anchor")

    def test_複数会議にまたがること自体は正常(self):
        w = self.wiki([
            ("LOG", "LOG-20260918-01", {}),
            ("LOG", "LOG-20261002-01", {"meeting": "MTG-20261002"}),
            ("DEC", "DEC-001", {"derived_from": ["LOG-20260918-01", "LOG-20261002-01"]}),
        ])
        self.assertEqual(w.meetings_of(w.get("DEC-001")), ["MTG-20260918", "MTG-20261002"])


# ============================================ 引用・信頼度（非対称）

class QuoteVerbatimTest(LintTestCase):
    def test_照合できない引用は鳴る(self):
        self.assertRaised([LOG, ("DEC", "DEC-001", {"引用": "言っていない発言"})], "quote-verbatim")

    def test_照合できれば鳴らない(self):
        self.assertQuiet([LOG, ("DEC", "DEC-001", {})], "quote-verbatim")

    def test_推測を名乗っていれば鳴らない(self):
        # 慎重側への降格は常に許す。水増しだけを弾く（非対称）。
        self.assertQuiet([LOG, ("DEC", "DEC-001",
                                {"引用": "言っていない発言", "信頼度": "推測"})], "quote-verbatim")


class SilenceConfidenceTest(LintTestCase):
    def test_記録なしで逐語ありを名乗れば鳴る(self):
        self.assertRaised([LOG, ("DEC", "DEC-001", {"代替案": [
            {"案": "自前実装", "却下理由": "記録なし", "信頼度": "逐語あり"}]})], "silence-confidence")

    def test_推測なら鳴らない(self):
        self.assertQuiet([LOG, ("DEC", "DEC-001", {"代替案": [
            {"案": "自前実装", "却下理由": "記録なし", "信頼度": "推測"}]})], "silence-confidence")

    def test_却下理由があるなら鳴らない(self):
        self.assertQuiet([LOG, ("DEC", "DEC-001", {"代替案": [
            {"案": "自前実装", "却下理由": "工数が合わない", "信頼度": "逐語あり"}]})],
            "silence-confidence")


class QuoteMissingTest(LintTestCase):
    def test_引用が空なら鳴る(self):
        self.assertRaised([LOG, ("DEC", "DEC-001", {"引用": ""})], "quote-missing")

    def test_TERMは引用を持たない(self):
        self.assertQuiet([LOG, ("TERM", "TERM-001", {})], "quote-missing")


# ============================================================ 役割・導出

class DecisionAuthorityTest(LintTestCase):
    def test_決定権のない役割なら鳴る(self):
        self.assertRaised([LOG, ("DEC", "DEC-001",
                                 {"決定の所在": "開発メンバー", "種別": "技術判断"})],
                          "decision-authority")

    def test_決定権があれば鳴らない(self):
        self.assertQuiet([LOG, ("DEC", "DEC-001", {"決定の所在": "顧客PM"})], "decision-authority")

    def test_未登録の役割は別のチェックに任せる(self):
        self.assertQuiet([LOG, ("DEC", "DEC-001", {"決定の所在": "謎の役割"})], "decision-authority")


class DecTypeDerivedTest(LintTestCase):
    def test_導出と食い違えば鳴る(self):
        self.assertRaised([LOG, ("DEC", "DEC-001",
                                 {"決定の所在": "顧客PM", "種別": "技術判断"})], "dec-type-derived")

    def test_一致すれば鳴らない(self):
        self.assertQuiet([LOG, ("DEC", "DEC-001",
                                {"決定の所在": "顧客法務", "種別": "契約制約"})], "dec-type-derived")


class RoleUnknownTest(LintTestCase):
    def test_未登録の役割は鳴る(self):
        self.assertRaised([LOG, ("DEC", "DEC-001", {"決定の所在": "情シス部長"})], "role-unknown")

    def test_参加役割も見る(self):
        self.assertRaised([("LOG", "LOG-20260918-01", {"参加役割": ["謎の役割"]})], "role-unknown")

    def test_登録済みなら鳴らない(self):
        self.assertQuiet([LOG, ("DEC", "DEC-001", {})], "role-unknown")


class ActOwnerTest(LintTestCase):
    def test_社名でなければ鳴る(self):
        self.assertRaised([LOG, ("ACT", "ACT-001", {"担当": "顧客PM"})], "act-owner")

    def test_社名なら鳴らない(self):
        self.assertQuiet([LOG, ("ACT", "ACT-001", {"担当": "甲社"})], "act-owner")

    def test_空欄は鳴らない(self):
        self.assertQuiet([LOG, ("ACT", "ACT-001", {"担当": ""})], "act-owner")


class ConHardnessTest(LintTestCase):
    """導出表の全組み合わせ。ここが狂うと制約の重みが全部ずれる。"""

    def _con(self, kind, location, hardness):
        return [LOG, ("CON", "CON-001", {"種類": kind, "所在": location, "硬度": hardness,
                                         "失効条件": "何か"})]

    def test_導出どおりなら鳴らない(self):
        for kind, location, expected in [
            ("property", "契約", "岩盤"), ("property", "顧客側", "沈殿"),
            ("property", "自社側", "沈殿"), ("property", "協力会社", "沈殿"),
            ("expectation", "顧客側", "沈殿"), ("expectation", "自社側", "懸濁"),
            ("expectation", "協力会社", "懸濁"),
        ]:
            self.assertQuiet(self._con(kind, location, expected), "con-hardness")

    def test_導出と違えば鳴る(self):
        self.assertRaised(self._con("property", "契約", "溶液"), "con-hardness")

    def test_表にない組み合わせは警告にとどめる(self):
        # expectation × 契約 は schema.md の表が定めていない。推測で埋めない。
        found = self.assertRaised(self._con("expectation", "契約", "岩盤"), "con-hardness")
        self.assertEqual(found[0].level, gijilint.WARNING)


# ============================================================ 二層構造・運用

class PromoteGateTest(LintTestCase):
    def test_紐づく決定がすべて理由未記入なら鳴る(self):
        self.assertRaised([LOG, ("DEC", "DEC-001", {"なぜ": "", "前提": ["ASM-001"]}),
                           ("ASM", "ASM-001", {"崩れたら見直す決定": ["DEC-001"]})], "promote-gate")

    def test_ひとつでも理由があれば鳴らない(self):
        self.assertQuiet([LOG, ("DEC", "DEC-001", {"なぜ": "失効保証を IdP に寄せるため",
                                                   "前提": ["ASM-001"]}),
                          ("ASM", "ASM-001", {"崩れたら見直す決定": ["DEC-001"]})], "promote-gate")

    def test_紐づく決定が無ければ対象外(self):
        self.assertQuiet([LOG, ("ASM", "ASM-001", {"崩れたら見直す決定": [], "脆弱性": "低"})],
                         "promote-gate")


class ScopePendingQTest(LintTestCase):
    def test_判定保留なのに未決Qが無ければ鳴る(self):
        self.assertRaised([LOG, ("DEC", "DEC-001", {"範囲": "判定保留"})], "scope-pending-q")

    def test_同じ論点に未決Qがあれば鳴らない(self):
        self.assertQuiet([LOG, ("DEC", "DEC-001", {"範囲": "判定保留"}),
                          ("Q", "Q-001", {"status": "未決"})], "scope-pending-q")

    def test_判定保留でなければ鳴らない(self):
        self.assertQuiet([LOG, ("DEC", "DEC-001", {"範囲": "当初合意内"})], "scope-pending-q")


class AsmGateTest(LintTestCase):
    def test_脆弱性高で逆リンクが空なら鳴る(self):
        self.assertRaised([LOG, ("ASM", "ASM-001",
                                 {"脆弱性": "高", "崩れたら見直す決定": []})], "asm-loadbearing")

    def test_脆弱性が高でなければ鳴らない(self):
        self.assertQuiet([LOG, ("ASM", "ASM-001",
                                {"脆弱性": "低", "崩れたら見直す決定": []})], "asm-loadbearing")

    def test_signpostが空なら鳴る(self):
        self.assertRaised([LOG, ("ASM", "ASM-001", {"脆弱性": "高", "signpost": "",
                                                    "崩れたら見直す決定": ["DEC-001"]}),
                           ("DEC", "DEC-001", {"前提": ["ASM-001"]})], "asm-signpost-empty")

    def test_曖昧なsignpostは警告(self):
        self.assertRaised([LOG, ("ASM", "ASM-001", {"signpost": "利用者数に注意する"})],
                          "asm-signpost-vague")

    def test_閾値が書かれていれば鳴らない(self):
        self.assertQuiet([LOG, ("ASM", "ASM-001",
                                {"signpost": "月次報告の利用者数が80人を超える"})],
                         "asm-signpost-vague")


class ConExpiryTest(LintTestCase):
    def test_expectationで失効条件が空なら鳴る(self):
        self.assertRaised([LOG, ("CON", "CON-001",
                                 {"種類": "expectation", "失効条件": ""})], "con-expiry")

    def test_propertyなら空でよい(self):
        self.assertQuiet([LOG, ("CON", "CON-001", {"種類": "property", "所在": "契約",
                                                   "硬度": "岩盤", "失効条件": ""})], "con-expiry")


class TermConflictTest(LintTestCase):
    def test_表記揺れが重複すれば鳴る(self):
        self.assertRaised([("TERM", "TERM-001", {"正式": "OIDC", "表記揺れ": ["オイデッシー"]}),
                           ("TERM", "TERM-002", {"正式": "SAML", "表記揺れ": ["オイデッシー"]})],
                          "term-variant-conflict")

    def test_他の用語の正式と衝突すれば鳴る(self):
        self.assertRaised([("TERM", "TERM-001", {"正式": "OIDC", "表記揺れ": []}),
                           ("TERM", "TERM-002", {"正式": "SAML", "表記揺れ": ["OIDC"]})],
                          "term-variant-conflict")

    def test_重複が無ければ鳴らない(self):
        self.assertQuiet([("TERM", "TERM-001", {"正式": "OIDC", "表記揺れ": ["オイデッシー"]}),
                          ("TERM", "TERM-002", {"正式": "SAML", "表記揺れ": ["サムル"]})],
                         "term-variant-conflict")


class WhyMissingTest(LintTestCase):
    def test_未記入なら鳴る(self):
        found = self.assertRaised([LOG, ("DEC", "DEC-001", {"なぜ": ""})], "why-missing")
        self.assertEqual(found[0].level, gijilint.WARNING, "必須フィールド化すると作話を招く")

    def test_記入済みなら鳴らない(self):
        self.assertQuiet([LOG, ("DEC", "DEC-001", {"なぜ": "失効保証を IdP 側に寄せるため"})],
                         "why-missing")

    def test_覆された決定は対象外(self):
        self.assertQuiet([LOG, ("DEC", "DEC-002", {"なぜ": "後継の決定"}),
                          ("DEC", "DEC-001", {"なぜ": "", "status": "覆された",
                                              "superseded_by": "DEC-002"})], "why-missing")


class DecDeferralTest(LintTestCase):
    def test_保留の表現がDECになっていれば鳴る(self):
        self.assertRaised([LOG, ("DEC", "DEC-001", {"引用": "前向きに検討します"})], "dec-deferral")

    def test_確定の表現なら鳴らない(self):
        self.assertQuiet([LOG, ("DEC", "DEC-001", {"引用": "じゃあそれでいきましょう"})],
                         "dec-deferral")


class ActLifecycleTest(LintTestCase):
    def test_未完了で担当と期限が空なら鳴る(self):
        self.assertRaised([LOG, ("ACT", "ACT-001", {"担当": "", "期限": ""})], "act-open-fields")

    def test_完了していれば鳴らない(self):
        self.assertQuiet([LOG, ("ACT", "ACT-001", {"status": "完了", "担当": "", "期限": ""})],
                         "act-open-fields")

    def test_期限超過は鳴る(self):
        self.assertRaised([LOG, ("ACT", "ACT-001", {"期限": "2026-09-01"})], "act-overdue")

    def test_期限前なら鳴らない(self):
        self.assertQuiet([LOG, ("ACT", "ACT-001", {"期限": "2026-10-02"})], "act-overdue")

    def test_完了していれば期限超過でも鳴らない(self):
        self.assertQuiet([LOG, ("ACT", "ACT-001", {"期限": "2026-09-01", "status": "完了"})],
                         "act-overdue")


class StaleTest(LintTestCase):
    def test_未決のまま放置されたQは鳴る(self):
        self.assertRaised([LOG, ("Q", "Q-001", {"status": "未決", "最終言及": "2026-07-01"})],
                          "q-stale")

    def test_最近言及されていれば鳴らない(self):
        self.assertQuiet([LOG, ("Q", "Q-001", {"status": "未決", "最終言及": "2026-09-18"})],
                         "q-stale")

    def test_解決済みなら鳴らない(self):
        self.assertQuiet([LOG, ("DEC", "DEC-001", {}),
                          ("Q", "Q-001", {"status": "解決", "resolved_by": "DEC-001",
                                          "最終言及": "2026-07-01"})], "q-stale")

    def test_次回確認日を過ぎた前提は鳴る(self):
        self.assertRaised([LOG, ("ASM", "ASM-001", {"次回確認日": "2026-09-01"})], "asm-review-due")

    def test_確定日が空のまま日がたてば鳴る(self):
        self.assertRaised([LOG, ("DEC", "DEC-001", {"決定日": "2026-08-01", "確定日": ""})],
                          "dec-unconfirmed")

    def test_確定日が入っていれば鳴らない(self):
        self.assertQuiet([LOG, ("DEC", "DEC-001",
                                {"決定日": "2026-08-01", "確定日": "2026-08-06"})],
                         "dec-unconfirmed")


class LogBarrenTest(LintTestCase):
    """欠落ガードの事後検出。引用検証は幻覚しか捕まえないので、こちらが要る。"""

    def test_議論から何も生えていなければ鳴る(self):
        self.assertRaised([("LOG", "LOG-20260918-01", {"種別": "議論"})], "log-barren")

    def test_カードが生えていれば鳴らない(self):
        self.assertQuiet([LOG, ("DEC", "DEC-001", {})], "log-barren")

    def test_報告や雑談は対象外(self):
        self.assertQuiet([("LOG", "LOG-20260918-01", {"種別": "報告"})], "log-barren")
        self.assertQuiet([("LOG", "LOG-20260918-01", {"種別": "雑談"})], "log-barren")


class IssueOrphanTest(LintTestCase):
    def test_完了なのにissueが残れば鳴る(self):
        self.assertRaised([LOG, ("ACT", "ACT-001",
                                 {"status": "完了", "issue": "owner/repo#1"})], "issue-orphan")

    def test_未完了なら鳴らない(self):
        self.assertQuiet([LOG, ("ACT", "ACT-001",
                                {"status": "進行中", "issue": "owner/repo#1"})], "issue-orphan")


# ============================================================ 全体

class SuiteTest(LintTestCase):
    def test_健全な案件ではerrorが出ない(self):
        wiki = self.wiki([
            ("LOG", "LOG-20260918-01", {}),
            ("DEC", "DEC-001", {"なぜ": "失効保証を IdP 側に寄せるため", "前提": ["ASM-001"]}),
            ("Q", "Q-001", {}),
            ("ACT", "ACT-001", {"担当": "甲社", "期限": "2026-10-02"}),
            ("ASM", "ASM-001", {"崩れたら見直す決定": ["DEC-001"]}),
            ("CON", "CON-001", {"影響する決定": ["DEC-001"]}),
            ("TERM", "TERM-001", {}),
        ])
        errors = [p for p in gijilint.run(wiki, today=TODAY) if p.level == gijilint.ERROR]
        self.assertEqual(errors, [], [str(p.message) for p in errors])

    def test_すべてのチェックが登録されている(self):
        self.assertEqual(len(gijilint.check_ids()), len(set(gijilint.check_ids())))
        self.assertGreater(len(gijilint.check_ids()), 30)

    def test_チェックIDで絞れる(self):
        found = self.problems([LOG, ("DEC", "DEC-001", {"status": "決定済"})], "vocab")
        self.assertTrue(all(p.check == "vocab" for p in found))


if __name__ == "__main__":
    unittest.main()
