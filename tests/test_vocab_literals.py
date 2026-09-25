#!/usr/bin/env python3
"""コードに語彙の値を直書きしていないかを見る。

語彙の正本は `ontology.yaml`。コードが `c.get("status") not in ("完了", "取り下げ")`
のように値を写すと、語彙を変えたときにコードだけが古い値で動き続ける（しかも
黙って空の結果を返すので気づけない）。

見るのは、語彙の値が**判定に使われている**箇所だけ:

- 比較（`==` / `!=` / `in` / `not in`）の相手になっている
- 定数への代入（`X = "推測"`、`X = ("議論", "確認")`）
- `.get(キー, 既定値)` の既定値

表の見出しのような表示用の文字列は対象外。どうしても直書きが要る箇所は、
その行に `# 直書き: 理由` を書いて明示する（1箇所でしか使わない値を宣言に
上げるより、ここで理由を残すほうが安い）。
"""

import ast
import unittest

from tools import schema

MARKER = "# 直書き:"


def _strings(node, flat_only=False):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        if flat_only and not all(isinstance(e, ast.Constant) for e in node.elts):
            return []
        return [s for e in node.elts for s in _strings(e, flat_only)]
    return []


def find_literals(source, values):
    """[(行番号, 値), ...]。抑止コメントの付いた行は除く。"""
    lines = source.split("\n")
    out = []
    for node in ast.walk(ast.parse(source)):
        found = []
        if isinstance(node, ast.Compare):
            for side in [node.left] + node.comparators:
                found += _strings(side)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            found += _strings(node.value, flat_only=True)
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
              and node.func.attr == "get" and len(node.args) == 2):
            found += _strings(node.args[1])
        hits = [s for s in found if s in values]
        if not hits:
            continue
        span = lines[node.lineno - 1:(node.end_lineno or node.lineno)]
        if any(MARKER in line for line in span):
            continue
        out.extend((node.lineno, s) for s in hits)
    return out


class VocabLiteralTest(unittest.TestCase):
    def test_tools_に語彙の値を直書きしていない(self):
        o = schema.load()
        values = {v for vs in o.enums.values() for v in vs}
        problems = []
        for path in sorted((schema.KIT_ROOT / "tools").rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            for lineno, value in find_literals(source, values):
                problems.append("%s:%d `%s`" % (path.relative_to(schema.KIT_ROOT), lineno, value))
        self.assertEqual(problems, [], "語彙の値の直書き（ontology.yaml から引くか、"
                         "`%s 理由` を付ける）:\n  %s" % (MARKER, "\n  ".join(problems)))

    def test_判定に使う直書きを捕まえる(self):
        values = {"完了", "取り下げ"}
        src = 'x = c.get("status") not in ("完了", "取り下げ")\n'
        self.assertEqual(find_literals(src, values), [(1, "完了"), (1, "取り下げ")])

    def test_表示用の文字列と抑止コメント付きの行は見ない(self):
        values = {"決定"}
        src = ('rows = [["ID", "決定"]]\n'
               'ok = c.get("status") == "決定"  # 直書き: みなし確定の対象はこの値だけ\n')
        self.assertEqual(find_literals(src, values), [])


if __name__ == "__main__":
    unittest.main()
