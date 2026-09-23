#!/usr/bin/env python3
"""tools/miniyaml.py の単体テスト。

このパーサはキット全体の単一障害点なので、実際に読む形（カードの
frontmatter・role-mapping.yaml・ontology.yaml）を網羅的に押さえる。
"""

import unittest

from tools.miniyaml import MiniYamlError, parse, parse_frontmatter_block, split_frontmatter


class ScalarTest(unittest.TestCase):
    def test_値はすべて文字列(self):
        got = parse("a: 1\nb: true\nc: 2026-09-18\nd: はい")
        self.assertEqual(got, {"a": "1", "b": "true", "c": "2026-09-18", "d": "はい"})

    def test_空値は空文字(self):
        self.assertEqual(parse("なぜ:\n確定日:"), {"なぜ": "", "確定日": ""})

    def test_null_とチルダも空文字(self):
        self.assertEqual(parse("a: null\nb: ~"), {"a": "", "b": ""})

    def test_値の中のコロンは切らない(self):
        self.assertEqual(parse('時刻: "00:21:10 - 00:34:52"'), {"時刻": "00:21:10 - 00:34:52"})

    def test_クォート無しでも時刻は切れない(self):
        # コロンの直後が空白でないので区切りにならない
        self.assertEqual(parse("時刻: 00:21:10"), {"時刻": "00:21:10"})

    def test_日本語の値にコロンが混ざる(self):
        got = parse("却下理由: 顧客側VPNが固定IPのみ")
        self.assertEqual(got, {"却下理由": "顧客側VPNが固定IPのみ"})

    def test_行末コメントを落とす(self):
        got = parse("信頼度: 推測          # 沈黙由来の却下は 推測 固定")
        self.assertEqual(got, {"信頼度": "推測"})

    def test_クォート内のシャープは残す(self):
        self.assertEqual(parse('a: "x # y"'), {"a": "x # y"})

    def test_シャープが語中にあるならコメントでない(self):
        self.assertEqual(parse("a: C#入門"), {"a": "C#入門"})

    def test_シングルクォートのエスケープ(self):
        self.assertEqual(parse("a: 'it''s'"), {"a": "it's"})

    def test_ダブルクォートのエスケープ(self):
        self.assertEqual(parse(r'a: "1\n2"'), {"a": "1\n2"})


class SequenceTest(unittest.TestCase):
    def test_インラインシーケンス(self):
        self.assertEqual(parse("derived_from: [LOG-20260918-03]"),
                         {"derived_from": ["LOG-20260918-03"]})

    def test_インラインシーケンスは複数要素(self):
        self.assertEqual(parse("前提: [ASM-003, ASM-004]"), {"前提": ["ASM-003", "ASM-004"]})

    def test_空のインラインシーケンス(self):
        self.assertEqual(parse("制約: []"), {"制約": []})

    def test_ブロックシーケンス(self):
        got = parse("参加役割:\n  - 顧客PM\n  - 開発リーダ")
        self.assertEqual(got, {"参加役割": ["顧客PM", "開発リーダ"]})

    def test_キーと同じインデントのシーケンス(self):
        got = parse("参加役割:\n- 顧客PM\n- 開発リーダ\n次: 1")
        self.assertEqual(got, {"参加役割": ["顧客PM", "開発リーダ"], "次": "1"})

    def test_ハイフン始まりの値をシーケンスと誤認しない(self):
        self.assertEqual(parse("a: -1"), {"a": "-1"})


class AlternativesTest(unittest.TestCase):
    """DEC の `代替案`。配列 of マッピングで、最も壊れやすい形。"""

    SRC = """\
代替案:
  - 案: 顧客の既存ADに直結
    却下理由: 顧客側VPNが固定IPのみ
    引用: ADに繋ぐのは、まあVPNが固定IPなんで厳しいですね
    信頼度: 逐語あり
  - 案: 自社でID基盤を実装
    却下理由: 記録なし
    引用: 自前で作る手もあるんですけどね
    信頼度: 推測               # 沈黙由来の却下は 推測 固定
"""

    def test_二件のマッピングとして読める(self):
        got = parse(self.SRC)["代替案"]
        self.assertEqual(len(got), 2)
        self.assertEqual(got[0]["案"], "顧客の既存ADに直結")
        self.assertEqual(got[0]["却下理由"], "顧客側VPNが固定IPのみ")
        self.assertEqual(got[1]["信頼度"], "推測")

    def test_代替案の後に別のキーが続いても崩れない(self):
        got = parse(self.SRC + "status: 決定\n")
        self.assertEqual(got["status"], "決定")
        self.assertEqual(len(got["代替案"]), 2)

    def test_更新履歴の形(self):
        got = parse("更新履歴:\n  - 2026-09-18: 起票\n  - 2026-10-02: 完了")
        self.assertEqual(got["更新履歴"], [{"2026-09-18": "起票"}, {"2026-10-02": "完了"}])


class NestedTest(unittest.TestCase):
    ROLE_MAPPING = """\
meta:
  project: トータル
  自社: ESM
  協力会社: []

roles:
  顧客PM:
    所属: 顧客側
    決定権: あり
    決定の種別: 交渉可能
  開発メンバー:
    所属: 自社側
    決定権: なし
"""

    def test_三階層のマッピング(self):
        got = parse(self.ROLE_MAPPING)
        self.assertEqual(got["meta"]["自社"], "ESM")
        self.assertEqual(got["meta"]["協力会社"], [])
        self.assertEqual(got["roles"]["顧客PM"]["決定の種別"], "交渉可能")
        self.assertEqual(got["roles"]["開発メンバー"]["決定権"], "なし")
        self.assertNotIn("決定の種別", got["roles"]["開発メンバー"])

    def test_インラインマッピング(self):
        got = parse('DEC: { dir: decisions, id: "^DEC-\\\\d{3}$", layer: flow }')
        self.assertEqual(got["DEC"]["dir"], "decisions")
        self.assertEqual(got["DEC"]["id"], "^DEC-\\d{3}$")
        self.assertEqual(got["DEC"]["layer"], "flow")

    def test_インラインマッピングの中のインラインシーケンス(self):
        got = parse("前提: { domain: [DEC], range: [ASM], inverse: 崩れたら見直す決定 }")
        self.assertEqual(got["前提"]["domain"], ["DEC"])
        self.assertEqual(got["前提"]["inverse"], "崩れたら見直す決定")


class BlockScalarTest(unittest.TestCase):
    def test_リテラル(self):
        got = parse("context: |\n  一行目\n  二行目\nnext: x")
        self.assertEqual(got["context"], "一行目\n二行目\n")
        self.assertEqual(got["next"], "x")

    def test_リテラルのチョンプ(self):
        self.assertEqual(parse("a: |-\n  一行目")["a"], "一行目")

    def test_折りたたみ(self):
        self.assertEqual(parse("a: >\n  一行目\n  二行目")["a"], "一行目 二行目\n")

    def test_ブロックスカラー内のシャープはコメントでない(self):
        self.assertEqual(parse("a: |\n  # 見出し\n  本文")["a"], "# 見出し\n本文\n")


class CommentAndBlankTest(unittest.TestCase):
    def test_コメント行と空行を飛ばす(self):
        src = "# 先頭コメント\n\na: 1\n\n  # 途中のコメント\nb: 2\n"
        self.assertEqual(parse(src), {"a": "1", "b": "2"})

    def test_空文書(self):
        self.assertEqual(parse(""), {})
        self.assertEqual(parse("# コメントだけ\n"), {})


class FailClosedTest(unittest.TestCase):
    """読めないものは黙って通さない。"""

    def _err(self, src):
        with self.assertRaises(MiniYamlError) as cm:
            parse(src)
        return cm.exception

    def test_アンカーは例外(self):
        self.assertIn("アンカー", str(self._err("a: &x 1")))

    def test_エイリアスは例外(self):
        self.assertIn("エイリアス", str(self._err("a: *x")))

    def test_タグは例外(self):
        self.assertIn("タグ", str(self._err("a: !!str 1")))

    def test_複数ドキュメントは例外(self):
        self.assertIn("複数ドキュメント", str(self._err("a: 1\n---\nb: 2")))

    def test_タブインデントは例外(self):
        self.assertIn("タブ", str(self._err("a:\n\tb: 1")))

    def test_キー重複は例外(self):
        self.assertIn("重複", str(self._err("a: 1\na: 2")))

    def test_コロンの無い行は例外(self):
        self.assertIn("key: value", str(self._err("a: 1\nこれはただの文\n")))

    def test_インデントの乱れは例外(self):
        self.assertIn("インデント", str(self._err("a: 1\n  b: 2\nc: 3")))

    def test_閉じないクォートは例外(self):
        self.assertIn("クォート", str(self._err('a: ["x, y]')))

    def test_閉じない角括弧は例外(self):
        self.assertIn("閉じていない", str(self._err("a: [x, y")))

    def test_例外は行番号を持つ(self):
        self.assertEqual(self._err("a: 1\nb: 2\nc: &x").line, 3)


class FrontmatterTest(unittest.TestCase):
    CARD = """\
---
id: DEC-014
type: decision
引用: じゃあOIDCの方向でいきましょう
---

## 補足

本文。
"""

    def test_frontmatter_と本文を分ける(self):
        data, body = parse_frontmatter_block(self.CARD)
        self.assertEqual(data["id"], "DEC-014")
        self.assertIn("## 補足", body)
        self.assertNotIn("id:", body)

    def test_frontmatter_が無ければ例外(self):
        with self.assertRaises(MiniYamlError):
            parse_frontmatter_block("# 見出しだけ\n")

    def test_行番号はファイル先頭からの通し番号(self):
        broken = "---\nid: DEC-014\nこれはただの文\n---\n"
        with self.assertRaises(MiniYamlError) as cm:
            parse_frontmatter_block(broken)
        self.assertEqual(cm.exception.line, 3)

    def test_split_frontmatter_は無ければ_None(self):
        fm, body, _ = split_frontmatter("本文のみ")
        self.assertIsNone(fm)
        self.assertEqual(body, "本文のみ")


if __name__ == "__main__":
    unittest.main()


class TrailingCommentOnParentTest(unittest.TestCase):
    """値の位置に行末コメントしか無い行の直後に子ブロックが続く形。

    schema.md の DEC サンプルが実際にこの形で、ここを取り落とすと
    `代替案` が丸ごと空になる（しかも例外にならない）。
    """

    def test_マッピングの親キーに行末コメント(self):
        got = parse("代替案:   # WinWin の option と同一概念\n  - 案: 自前実装\n    却下理由: 記録なし")
        self.assertEqual(got["代替案"], [{"案": "自前実装", "却下理由": "記録なし"}])

    def test_シーケンスの親キーに行末コメント(self):
        got = parse("参加役割:  # 話者分離の出力\n  - 顧客PM\n  - 開発リーダ")
        self.assertEqual(got["参加役割"], ["顧客PM", "開発リーダ"])

    def test_コメント専用行が途中に挟まっても崩れない(self):
        src = "スコープ: 判定保留   # 当初スコープ内 | スコープ外(追加) | 判定保留\n" \
              "                 # 判定保留 は自動で Q を起票する\n" \
              "確定日:\n"
        self.assertEqual(parse(src), {"スコープ": "判定保留", "確定日": ""})
