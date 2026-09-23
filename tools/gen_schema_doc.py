#!/usr/bin/env python3
"""ontology.yaml → schema.md のフィールド表を生成する。

**schema.md を全面生成はしない。** このファイルの価値の大半は「なぜ `スコープ` が
要るか」「van Lamsweerde の一文がそのまま判定テストになる」といった散文の論証で、
それを YAML の文字列に押し込むと読み物として壊れる。

そこで、機械が実際に評価する記述だけをマーカーで囲んで生成する:

    <!-- generated:fields DEC — ontology.yaml から生成。手編集禁止 -->
    （フィールド表）
    <!-- /generated -->

散文とサンプル frontmatter はマーカーの外にあり、人が書いたまま残る。
サンプルのほうは生成せず、宣言との食い違いだけを --check-samples で照合する
（コメント付きのサンプルは人間向けの説明を兼ねており、生成すると情報が落ちる）。

使い方:
    python3 tools/gen_schema_doc.py --render          # schema.md を書き換える
    python3 tools/gen_schema_doc.py --check           # 差分があれば終了コード 1
    python3 tools/gen_schema_doc.py --check-samples   # サンプルと宣言の食い違い
    python3 tools/gen_schema_doc.py --check-templates # 雛形と宣言の食い違い
"""

import argparse
import re
import sys

from tools import schema
from tools.miniyaml import MiniYamlError, parse

MARKER_OPEN = "<!-- generated:fields %s — ontology.yaml から生成。手編集禁止 -->"
MARKER_CLOSE = "<!-- /generated -->"
BLOCK_RE = re.compile(
    r"<!-- generated:fields (?P<type>\w+) [^>]*-->\n.*?\n" + re.escape(MARKER_CLOSE) + r"\n",
    re.DOTALL)

KIND_LABEL = {
    "id": "ID", "text": "自由記述", "enum": "語彙", "date": "日付",
    "ref": "参照", "ref-list": "参照の配列", "str-list": "文字列の配列",
    "struct-list": "構造化配列", "quote": "引用", "time-range": "時刻範囲",
}


def _type_heading_re(type_name):
    return re.compile(r"^## %s\b.*$" % re.escape(type_name), re.MULTILINE)


def render_table(ontology, type_name):
    rows = ["| フィールド | 種類 | 必須 | 値 | 記入主体 |", "|---|---|---|---|---|"]
    for name, spec in ontology.field_specs(type_name).items():
        kind = KIND_LABEL.get(spec.get("kind"), spec.get("kind", ""))
        required = "○" if str(spec.get("required", "")).lower() == "true" else "—"
        if spec.get("enum"):
            values = " / ".join("`%s`" % v for v in ontology.enum_values(spec["enum"]))
            if ontology.allows_free_text(type_name, name):
                values += " / 自由記述"
        elif spec.get("kind") in ("ref", "ref-list"):
            targets = ontology.relation_range(name) or [spec.get("ref", "")]
            values = " / ".join("`%s`" % t for t in targets)
        elif spec.get("kind") == "struct-list":
            struct = ontology.structs.get(spec.get("struct"), {})
            values = " / ".join("`%s`" % k for k in struct.get("keys", []))
        else:
            values = "—"
        rows.append("| `%s` | %s | %s | %s | %s |"
                    % (name, kind, required, values, spec.get("記入主体", "")))
    return "\n".join(rows)


def render_block(ontology, type_name):
    return "%s\n\n%s\n\n%s\n" % (MARKER_OPEN % type_name,
                                 render_table(ontology, type_name),
                                 MARKER_CLOSE)


def apply(text, ontology):
    """schema.md の各型節に生成ブロックを挿入 / 更新した全文を返す。"""
    # まず既存ブロックを更新する。
    def replace(m):
        type_name = m.group("type")
        if type_name not in ontology.type_names():
            return m.group(0)
        return render_block(ontology, type_name)

    text = BLOCK_RE.sub(replace, text)

    # まだブロックが無い型は、見出しの直後に差し込む。
    for type_name in ontology.type_names():
        if re.search(r"<!-- generated:fields %s\b" % type_name, text):
            continue
        heading = _type_heading_re(type_name).search(text)
        if not heading:
            continue
        insert_at = heading.end()
        text = text[:insert_at] + "\n\n" + render_block(ontology, type_name).rstrip("\n") + text[insert_at:]
    return text


# ------------------------------------------------------- サンプルの照合

SAMPLE_RE = re.compile(r"```yaml\n(?P<body>.*?)```", re.DOTALL)


def _sections(text, ontology):
    """型ごとの節の本文を切り出す。"""
    positions = []
    for type_name in ontology.type_names():
        m = _type_heading_re(type_name).search(text)
        if m:
            positions.append((m.start(), type_name))
    positions.sort()
    out = {}
    for i, (start, type_name) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        out[type_name] = text[start:end]
    return out


def check_samples(text, ontology):
    """サンプル frontmatter のキーが宣言と食い違っていないか。"""
    problems = []
    for type_name, section in _sections(text, ontology).items():
        m = SAMPLE_RE.search(section)
        if not m:
            continue
        body = m.group("body")
        if body.lstrip().startswith("---"):
            body = body.split("---", 2)[1]
        try:
            data = parse(body)
        except MiniYamlError as exc:
            problems.append("%s のサンプルが読めない: %s" % (type_name, exc))
            continue
        if not isinstance(data, dict):
            continue
        declared = set(ontology.field_specs(type_name))
        for key in data:
            if key not in declared:
                problems.append("%s のサンプルに宣言にないキー `%s` がある" % (type_name, key))
        for key in ontology.required_fields(type_name):
            if key not in data:
                problems.append("%s のサンプルに必須フィールド `%s` が無い" % (type_name, key))
    return problems


def check_templates(ontology):
    """templates/card/*.md の雛形が宣言と食い違っていないか。"""
    from tools.cards import parse_card

    problems = []
    directory = schema.KIT_ROOT / "templates" / "card"
    if not directory.is_dir():
        return problems
    for path in sorted(directory.glob("*.md")):
        type_name = path.stem.upper()
        if type_name not in ontology.type_names():
            problems.append("%s は既知の型に対応しない" % path.name)
            continue
        card = parse_card(path, ontology)
        if card.error is not None:
            problems.append("%s が読めない: %s" % (path.name, card.error))
            continue
        declared = set(ontology.field_specs(type_name))
        for key in card.data:
            if key not in declared:
                problems.append("%s に宣言にないキー `%s` がある" % (path.name, key))
        for key in ontology.required_fields(type_name):
            if key not in card.data:
                problems.append("%s に必須フィールド `%s` が無い" % (path.name, key))
    return problems


# ------------------------------------------------------------ CLI

def main(argv=None):
    ap = argparse.ArgumentParser(prog="kime schema",
                                 description="ontology.yaml と schema.md / 雛形の同期")
    ap.add_argument("--render", action="store_true", help="schema.md の生成ブロックを書き換える")
    ap.add_argument("--check", action="store_true", help="生成ブロックが最新かを見る")
    ap.add_argument("--check-samples", action="store_true", help="サンプル frontmatter を照合する")
    ap.add_argument("--check-templates", action="store_true", help="templates/card/ を照合する")
    args = ap.parse_args(argv)

    if not any([args.render, args.check, args.check_samples, args.check_templates]):
        args.check = True

    ontology = schema.load()
    path = schema.KIT_ROOT / "schema.md"
    text = path.read_text(encoding="utf-8")
    failed = False

    if args.render:
        updated = apply(text, ontology)
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            print("schema.md の生成ブロックを更新した")
        else:
            print("schema.md は既に最新")
        text = updated

    if args.check:
        if apply(text, ontology) != text:
            print("schema.md の生成ブロックが ontology.yaml と一致しない"
                  "（`python3 tools/gen_schema_doc.py --render` で更新する）")
            failed = True
        else:
            print("schema.md: 最新")

    if args.check_samples:
        problems = check_samples(text, ontology)
        for p in problems:
            print("サンプル: %s" % p)
        print("サンプル: %d件の食い違い" % len(problems))
        failed = failed or bool(problems)

    if args.check_templates:
        problems = check_templates(ontology)
        for p in problems:
            print("雛形: %s" % p)
        print("雛形: %d件の食い違い" % len(problems))
        failed = failed or bool(problems)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
