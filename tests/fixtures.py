#!/usr/bin/env python3
"""テスト用の案件ツリーを組み立てるヘルパ。

リポジトリにテスト用カードを大量に置かず、各テストが必要な分だけを
一時ディレクトリに書き出す。テストを読めば前提が全部見えるようにするため。
"""

import tempfile
import unittest
from pathlib import Path

from tools import schema
from tools.cards import Wiki, render_card

ROLE_MAPPING = """\
meta:
  project: テスト
  自社: ESM
  顧客: 甲社
  協力会社: [乙社]

roles:
  顧客PM:
    所属: 顧客側
    社名: 甲社
    決定権: あり
    決定の種別: 交渉可能
  顧客法務:
    所属: 顧客側
    社名: 甲社
    決定権: あり
    決定の種別: 契約制約
  開発リーダ:
    所属: 自社側
    社名: ESM
    決定権: あり
    決定の種別: 技術判断
  開発メンバー:
    所属: 自社側
    社名: ESM
    決定権: なし

unknown_role_default:
  所属: 不明
  社名: 不明
  決定権: なし
"""

# よく使う既定値。テストは変えたいキーだけを渡す。
DEFAULTS = {
    "LOG": {"type": "log", "meeting": "MTG-20260918", "title": "論点",
            "種別": "議論", "時刻": "00:00:00 - 00:10:00", "参加役割": ["顧客PM", "開発リーダ"]},
    "AGD": {"type": "agenda", "title": "決めたいこと", "status": "未着手",
            "提起者": "顧客PM", "提起日": "2026-09-11", "予定会議": ["MTG-20260918"]},
    "DEC": {"type": "decision", "title": "決定", "status": "決定", "決定日": "2026-09-18",
            "決定の所在": "顧客PM", "会議体": "定例WG", "種別": "交渉可能",
            "引用": "じゃあそれでいきましょう", "信頼度": "逐語あり",
            "derived_from": ["LOG-20260918-01"], "スコープ": "当初スコープ内"},
    "Q": {"type": "question", "title": "未決", "status": "未決", "確認先": "顧客PM",
          "初出": "2026-09-18", "最終言及": "2026-09-18",
          "引用": "そこはまだ決まっていません", "信頼度": "逐語あり",
          "derived_from": ["LOG-20260918-01"]},
    "ACT": {"type": "action", "title": "確認する", "status": "未着手",
            "引用": "こちらで確認しておきます", "信頼度": "逐語あり",
            "derived_from": ["LOG-20260918-01"]},
    "CON": {"type": "constraint", "内容": "顧客側VPNは固定IPのみ", "種類": "expectation",
            "所在": "顧客側", "硬度": "沈殿", "失効条件": "顧客のネットワーク更新",
            "derived_from": ["LOG-20260918-01"], "承認": "2026-09-18", "status": "有効"},
    "ASM": {"type": "assumption", "内容": "当面の利用者は50人規模", "脆弱性": "高",
            "signpost": "月次報告の利用者数が80人を超える", "次回確認日": "2026-10-02",
            "引用": "はい、当面はその規模です", "信頼度": "逐語あり",
            "derived_from": ["LOG-20260918-01"], "最終確認": "2026-09-18", "status": "有効"},
    "TERM": {"type": "term", "正式": "OIDC", "読み": "オーアイディーシー",
             "表記揺れ": ["オイデッシー"], "定義": "OpenID Connect"},
}

DEFAULT_LOG_BODY = """\
## 発言

- **顧客PM**: じゃあそれでいきましょう
- **開発リーダ**: 承知しました
- **顧客PM**: そこはまだ決まっていません
- **開発メンバー**: こちらで確認しておきます
- **顧客PM**: はい、当面はその規模です
"""


def card_text(type_name, card_id, body=None, **overrides):
    data = {"id": card_id}
    data.update(DEFAULTS[type_name])
    data.update(overrides)
    # None を渡したキーは「フィールドごと落とす」の意味にする。
    data = {k: v for k, v in data.items() if v is not None}
    if body is None:
        body = DEFAULT_LOG_BODY if type_name == "LOG" else ""
    return render_card(data, body)


def build(root, cards=(), role_mapping=ROLE_MAPPING, segments=None):
    """cards は (型, ID, overrides) または (型, ID, overrides, body) のタプル列。

    segments は {会議 ID: segments.yaml の中身} 。Pass 1 の出力を見るテスト用。
    """
    root = Path(root)
    ontology = schema.load()
    (root / "role-mapping.yaml").write_text(role_mapping, encoding="utf-8")
    for meeting, text in (segments or {}).items():
        directory = root / "meetings" / meeting
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "segments.yaml").write_text(text, encoding="utf-8")
    for entry in cards:
        type_name, card_id = entry[0], entry[1]
        overrides = entry[2] if len(entry) > 2 else {}
        body = entry[3] if len(entry) > 3 else None
        if type_name == "LOG":
            meeting = overrides.get("meeting", DEFAULTS["LOG"]["meeting"])
            directory = root / "meetings" / meeting / "logs"
        else:
            directory = root / ontology.dir_of(type_name)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / ("%s.md" % card_id)).write_text(
            card_text(type_name, card_id, body=body, **overrides), encoding="utf-8")
    return Wiki(root, ontology)


class WikiTestCase(unittest.TestCase):
    """一時ディレクトリに案件を組み立てて使うテストの基底。"""

    def wiki(self, cards=(), role_mapping=ROLE_MAPPING, segments=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return build(tmp.name, cards, role_mapping, segments)

    def wiki_at(self, root):
        """同じディレクトリを読み直す。カードを足したあとのキャッシュ避け。"""
        return Wiki(root, schema.load())
