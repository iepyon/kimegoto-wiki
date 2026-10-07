#!/usr/bin/env python3
"""カード間の参照を Obsidian のリンクで書く（docs/obsidian.md 案 B）。

参照フィールド（`ontology.yaml` で ref / ref-list と宣言したもの）は、ファイルの上では
`"[[AGD-001]]"` と書く。`ID = ファイル名` なので Obsidian がそのまま解決し、
バックリンクとグラフが効く。逆方向を書かずに済むので「リンクは片方向」も崩れない。

**読むときに剥がす。** `cards.parse_card` が素の ID に戻すので、`wiki.*`・lint・
議事録はどれも素の ID しか見ない。顧客提出版に `[[ ]]` が漏れないのもこのため。
素の ID で書かれていても読めるが、Obsidian はリンクと見なさないので lint
（`ref-unlinked`）が拾い、`kime links --fix` が書き直す。

会議（MTG）はファイルではなくディレクトリなのでリンクにしない（`meeting` / `予定会議`）。
LOG は不変層で、持つ参照も MTG だけなので対象にならない。
"""

import re

# `[[DEC-001]]`、`[[DEC-001|別名]]`、`[[DEC-001#見出し]]`
WIKILINK = re.compile(r"^\[\[(?P<target>[^\]|#]+)(?:[|#][^\]]*)?\]\]$")


def is_link(value):
    return isinstance(value, str) and WIKILINK.match(value.strip()) is not None


def unwrap(value):
    """`[[X]]` → `X`。リンクでなければそのまま。

    クォートせずに `議題: [[AGD-001]]` と書くと YAML では入れ子の配列（[["AGD-001"]]）に
    なる。人が手で書きがちなので、1要素の入れ子も剥がして読む（lint は拾う）。
    """
    while isinstance(value, list) and len(value) == 1:
        value = value[0]
    if isinstance(value, list):
        return value
    text = (value or "").strip() if isinstance(value, str) else value
    m = WIKILINK.match(text) if isinstance(text, str) else None
    return m.group("target").strip() if m else value


def linkable(ontology, type_name, field_name):
    """その参照フィールドをリンクで書くか。参照先がすべてファイルを持つ型なら書く。"""
    targets = ontology.ref_targets(type_name, field_name)
    names = set(ontology.type_names())
    return bool(targets) and all(t in names for t in targets)


def linked_fields(ontology, type_name):
    """(フィールド名, kind) の列。リンクで書く参照フィールドだけ。"""
    specs = ontology.field_specs(type_name)
    return [(name, specs[name].get("kind")) for name, _ in ontology.ref_fields(type_name)
            if linkable(ontology, type_name, name)]


def normalize(data, ontology, type_name):
    """frontmatter の dict の参照値を素の ID に戻す（その場で書き換える）。

    戻り値はリンクで書かれていなかった (フィールド名, 値) の列。lint と
    `kime links` が使う。
    """
    plain = []
    for name, kind in linked_fields(ontology, type_name):
        if name not in data:
            continue
        raw = data[name]
        if kind == "ref-list":
            items = raw if isinstance(raw, list) else ([] if raw in ("", None) else [raw])
            ids = []
            for item in items:
                value = unwrap(item)
                if isinstance(value, str) and value:
                    ids.append(value)
                    if not is_link(item):
                        plain.append((name, value))
            data[name] = ids
        else:
            value = unwrap(raw)
            if isinstance(value, str):
                data[name] = value
                if value and not is_link(raw):
                    plain.append((name, value))
    return plain


def scalar(card_id):
    """1件の参照を frontmatter の値として書く形。空なら空。"""
    return '"[[%s]]"' % card_id if card_id else ""


def flow(ids):
    """ref-list を frontmatter の値として書く形。"""
    return "[%s]" % ", ".join(scalar(i) for i in ids if i)


def render(kind, value):
    """kind に応じて書く形を返す。value は素の ID か、その list。"""
    if kind == "ref-list":
        ids = value if isinstance(value, list) else [v.strip() for v in
                                                   str(value).strip("[]").split(",")]
        return flow([unwrap(v.strip().strip('"\'')) if isinstance(v, str) else v
                     for v in ids if v and str(v).strip()])
    return scalar(unwrap(str(value).strip().strip('"\'')))
