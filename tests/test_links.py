#!/usr/bin/env python3
"""参照フィールドの Obsidian リンク（`tools/links.py` / `kime links` / `ref-unlinked`）。

ファイル上は `"[[ID]]"` で書き、読むときに素の ID に戻す。下流（wiki・lint・議事録）が
素の ID しか見ないこと、素の ID で書かれたものを lint が拾い `kime links --fix` が
値を変えずに書き直すことを見る。
"""

import contextlib
import io
import unittest

from tests.fixtures import WikiTestCase
from tools import kimelint, links, links_cmd, schema
from tools.cards import Wiki
from tools.update_cmd import apply_updates

LOG = ("LOG", "LOG-20260918-01", {})
AGD = ("AGD", "AGD-001", {})


class UnwrapTest(unittest.TestCase):
    def test_リンクを剥がす(self):
        self.assertEqual(links.unwrap("[[DEC-001]]"), "DEC-001")
        self.assertEqual(links.unwrap("[[DEC-001|別名]]"), "DEC-001")
        self.assertEqual(links.unwrap("[[DEC-001#補足]]"), "DEC-001")

    def test_素のIDはそのまま(self):
        self.assertEqual(links.unwrap("DEC-001"), "DEC-001")

    def test_クォートし忘れた入れ子の配列も剥がす(self):
        # `議題: [[AGD-001]]` は YAML では [["AGD-001"]] になる
        self.assertEqual(links.unwrap([["AGD-001"]]), "AGD-001")

    def test_会議はリンクにしない(self):
        o = schema.load()
        self.assertFalse(links.linkable(o, "LOG", "meeting"))
        self.assertFalse(links.linkable(o, "AGD", "予定会議"))
        self.assertTrue(links.linkable(o, "DEC", "derived_from"))
        self.assertTrue(links.linkable(o, "DEC", "議題"))

    def test_書く形(self):
        self.assertEqual(links.render("ref", "DEC-001"), '"[[DEC-001]]"')
        self.assertEqual(links.render("ref-list", "[DEC-001, DEC-002]"),
                         '["[[DEC-001]]", "[[DEC-002]]"]')
        self.assertEqual(links.render("ref-list", '["[[DEC-001]]"]'), '["[[DEC-001]]"]')


class ReadTest(WikiTestCase):
    def test_リンクで書いた参照は素のIDで読める(self):
        w = self.wiki([LOG, AGD, ("DEC", "DEC-001", {"derived_from": ["[[LOG-20260918-01]]"],
                                                      "議題": "[[AGD-001]]"})])
        card = w.get("DEC-001")
        self.assertEqual(card.list("derived_from"), ["LOG-20260918-01"])
        self.assertEqual(card.get("議題"), "AGD-001")
        self.assertEqual(card.plain_refs, [])
        self.assertEqual([c.id for c in w.children_of("AGD-001")], ["DEC-001"])
        self.assertEqual(w.meetings_of(card), ["MTG-20260918"])

    def test_素のIDも読めるが記録する(self):
        w = self.wiki([LOG, ("DEC", "DEC-001", {})])
        card = w.get("DEC-001")
        self.assertEqual(card.list("derived_from"), ["LOG-20260918-01"])
        self.assertEqual(card.plain_refs, [("derived_from", "LOG-20260918-01")])


class LintTest(WikiTestCase):
    def test_素のIDを拾う(self):
        w = self.wiki([LOG, ("DEC", "DEC-001", {})])
        found = kimelint.run(w, only={"ref-unlinked"})
        self.assertEqual([p.where for p in found], ["DEC-001"])

    def test_リンクなら何も言わない(self):
        w = self.wiki([LOG, ("DEC", "DEC-001", {"derived_from": ["[[LOG-20260918-01]]"]})])
        self.assertFalse(kimelint.run(w, only={"ref-unlinked"}))

    def test_LOGの会議は対象外(self):
        w = self.wiki([LOG])
        self.assertFalse(kimelint.run(w, only={"ref-unlinked"}))


class FixTest(WikiTestCase):
    def test_値を変えずにリンクへ書き直す(self):
        w = self.wiki([LOG, AGD, ("DEC", "DEC-001", {"議題": "AGD-001"})])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(links_cmd.main(["--root", str(w.root), "--fix"]), 0)
        text = w.get("DEC-001").path.read_text(encoding="utf-8")
        self.assertIn('derived_from: ["[[LOG-20260918-01]]"]', text)
        self.assertIn('議題: "[[AGD-001]]"', text)
        again = Wiki(w.root, w.ontology)
        self.assertEqual(again.get("DEC-001").get("議題"), "AGD-001")
        self.assertEqual(again.get("DEC-001").plain_refs, [])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(links_cmd.main(["--root", str(w.root)]), 0)

    def test_ブロック形式の配列を取り残さない(self):
        # Obsidian の Properties で編集すると配列はブロック形式に書き直される
        text = ("---\nid: DEC-001\nderived_from:\n  - LOG-20260918-01\n  - LOG-20260918-02\n"
                "議題:\n---\n")
        out = apply_updates(text, add_derived=["LOG-20260918-03"])
        self.assertIn('derived_from: ["[[LOG-20260918-01]]", "[[LOG-20260918-02]]", '
                      '"[[LOG-20260918-03]]"]\n議題:', out)
        self.assertNotIn("  - ", out)


if __name__ == "__main__":
    unittest.main()
